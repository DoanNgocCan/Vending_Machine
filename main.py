# -*- coding: utf-8 -*-
# File: main.py
import tkinter as tk
import threading
import queue
import sys
import os

# Đảm bảo các module trong 'core' có thể được import
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

# --- Import các thành phần chính của ứng dụng ---
from core.features.shopping_logic import ShoppingLogic
from core.ui.ui_controller import AdvancedUIManager
from core.features.api_manager import VendingAPIManager 
from core.features.flask_QR import app, set_shared_queue, run_flask_app
from core.features.payment_handler import check_payment_queue
from core.features.background_sync import sync_manager
from core.features.mqtt_client import mqtt_manager
from core.database.local_database_manager import db_manager
from core.utils.system_utils import force_kill_system

# --- Import driver phần cứng (với kiểm tra lỗi) ---
try:
    from core.drivers.PCF8574T import initialize_led_controller, close_led_controller
    LED_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    print(f"⚠️  Cảnh báo: Driver PCF8574T không khả dụng: {e}")
    LED_AVAILABLE = False
    # Tạo các hàm giả để chương trình không bị lỗi khi gọi
    def initialize_led_controller(): return False
    def close_led_controller(): pass

def main():
    """
    Hàm chính, là điểm khởi đầu của toàn bộ ứng dụng.
    Nhiệm vụ: Khởi tạo và điều phối các module chính.

    Thứ tự khởi động:
        1. Khởi tạo cấu hình và thành phần logic cơ bản.
        2. Khởi tạo driver phần cứng.
        3. Kết nối MQTT broker (bất đồng bộ, graceful fallback).
        4. Đồng bộ dữ liệu sản phẩm ban đầu từ server qua HTTP.
        5. Khởi tạo giao diện người dùng với dữ liệu đã sẵn sàng.
        6. Khởi động các dịch vụ nền (Flask, sync định kỳ, payment listener).
        7. Chạy vòng lặp chính Tkinter.
    """
    ui_instance = None  # Khai báo trước để dùng trong khối finally

    try:
        print("--- BẮT ĐẦU KHỞI TẠO ỨNG DỤNG MÁY BÁN HÀNG ---")

        # 1. Khởi tạo các thành phần logic cơ bản (không giao diện)
        root = tk.Tk()
        root.bind_all("<Control-Escape>", lambda e: force_kill_system())
        print("[SYSTEM] Đã kích hoạt phím tắt khẩn cấp: Ctrl + Esc")
        shopping_logic = ShoppingLogic()
        api_manager = VendingAPIManager()
        flask_to_tkinter_queue = queue.Queue()
        set_shared_queue(flask_to_tkinter_queue)

        # 2. Khởi tạo driver phần cứng
        if LED_AVAILABLE:
            initialize_led_controller()

        # 3. Configurar MQTT uma única vez com todos os callbacks.
        #    Use a mutable container to reference ui_instance before it is created.
        #    Os callbacks verificam ui_ref[0] no momento da chamada, não no momento da criação.
        ui_ref = [None]

        def _mqtt_ui_refresh():
            """Yêu cầu UI vẽ lại toàn bộ lưới sản phẩm (thread-safe qua root.after)."""
            try:
                view = ui_ref[0]
                if view and hasattr(view, 'main_view') and view.main_view:
                    root.after(0, view.main_view.refresh_product_grid)
            except Exception as e:
                print(f"[MQTT] Lỗi khi yêu cầu refresh UI: {e}")

        def _mqtt_product_update(item_name, price, quantity):
            """Cập nhật một sản phẩm cụ thể trên UI (thread-safe)."""
            try:
                view = ui_ref[0]
                if view and hasattr(view, 'main_view') and view.main_view:
                    root.after(0, lambda: view.main_view.update_single_product(
                        item_name, price, quantity
                    ))
            except Exception as e:
                print(f"[MQTT] Lỗi khi yêu cầu cập nhật sản phẩm '{item_name}': {e}")

        mqtt_manager.setup(
            db_manager=db_manager,
            api_manager=api_manager,
            ui_refresh_callback=_mqtt_ui_refresh,
            product_update_callback=_mqtt_product_update,
        )
        print("[MAIN] Đang kết nối MQTT broker...")
        mqtt_connected = mqtt_manager.connect()
        if mqtt_connected:
            print("[MAIN] Kết nối MQTT thành công.")
        else:
            print("[MAIN] Không kết nối được MQTT. Sẽ dùng HTTP polling làm fallback.")

        # 4. Đồng bộ dữ liệu ban đầu TRƯỚC KHI UI khởi động
        #    Đảm bảo UI bắt đầu với dữ liệu sản phẩm mới nhất từ server.
        print("[MAIN] Chạy đồng bộ dữ liệu ban đầu...")
        sync_manager.sync_now()
        print("[MAIN] Đồng bộ ban đầu hoàn tất.")

        # 5. Khởi tạo UI Manager
        #    AdvancedUIManager sẽ tự động khởi tạo thư viện FaceRecognitionSystem bên trong nó.
        #    Đây là điểm duy nhất mà logic AI/Camera được kích hoạt.
        print("[MAIN] Đang khởi tạo giao diện người dùng và hệ thống AI/Camera...")
        ui_instance = AdvancedUIManager(
            root=root,
            shopping_logic_instance=shopping_logic,
            api_manager_instance=api_manager
        )
        # Gán ui_instance vào container để các MQTT callback có thể truy cập
        ui_ref[0] = ui_instance

        # 6. Khởi động các luồng nền hỗ trợ
        print("[MAIN] Đang khởi động các dịch vụ nền...")
        
        # Khởi động server thanh toán Flask
        flask_thread = threading.Thread(target=run_flask_app, daemon=True)
        flask_thread.start()
        
        # Bắt đầu luồng đồng bộ định kỳ (chạy sau mỗi X phút)
        sync_manager.start()

        # Bắt đầu luồng lắng nghe tín hiệu thanh toán từ Flask
        check_payment_queue(root, ui_instance, shopping_logic, flask_to_tkinter_queue)

        # 7. Chạy vòng lặp chính của giao diện Tkinter
        print("[MAIN] Khởi tạo hoàn tất. Bắt đầu vòng lặp chính của ứng dụng.")
        root.mainloop()

    except Exception as e:
        import traceback
        print(f"LỖI NGHIÊM TRỌNG TRONG HÀM MAIN: {e}")
        traceback.print_exc()
        
    finally:
        # Dọn dẹp tài nguyên khi ứng dụng thoát (dù thành công hay thất bại)
        print("[MAIN] Bắt đầu dọn dẹp tài nguyên trước khi thoát...")
        sync_manager.stop()
        mqtt_manager.disconnect()
        
        if LED_AVAILABLE:
            close_led_controller()
        
        # Dọn dẹp UI một cách an toàn
        if ui_instance and not ui_instance.is_closing:
            ui_instance.on_app_close()
        
        print("--- ỨNG DỤNG ĐÃ ĐÓNG HOÀN TOÀN ---")

if __name__ == "__main__":
    main() 