# SHOPPING_KEYPAD_APP/core/ui/ui_controller.py

# --- Imports cơ bản ---
import tkinter as tk
from tkinter import PhotoImage, messagebox
from PIL import Image, ImageTk
import os, itertools, sys, requests, webbrowser, re, datetime
import customtkinter as ctk
import subprocess, signal, time, threading
import cv2
import json
import numpy as np # Cần cho Mock Camera
import pickle
from collections import Counter
# Thêm code này để Python tìm thấy thư mục 'core' và 'config.py'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..') # Đi lùi 2 cấp (từ /core/ui/ -> /)
sys.path.append(project_root)
# --- Imports từ project ---
try:
    from core.Camera_AI.model import ModelModule
except Exception:
    ModelModule = None
from core.features.shopping_logic import ShoppingLogic
from core.features.face_recognition_handler import FaceRecognitionHandler
from core.database.local_database_manager import db_manager
from config import TEMP_MESSAGE_DURATION, IMAGE_BASE_PATH, PRODUCT_IMAGES_CONFIG, AD_IMAGES_CONFIG

# --- Imports các màn hình UI đã tách ---
from core.ui.ui_welcome import WelcomeScreen
from core.ui.ui_loading import LoadingScreen
from core.ui.ui_login import LoginScreen
from core.ui.ui_register import RegisterScreen
from core.ui.ui_face_capture import FaceCaptureScreen
from core.ui.ui_confirmation import ConfirmationScreen
from core.ui.ui_thankyou import ThankYouScreen
from core.ui.ui_main import MainView


class AdvancedUIManager:
    # (Các hằng số giữ nguyên)
    PRODUCT_IMAGES_CONFIG = PRODUCT_IMAGES_CONFIG

    # === SỬA ĐỔI 1: Thêm cờ test_mode ===
    def __init__(self, root, shopping_logic_instance, api_manager_instance, test_mode=False):
        self.root = root
        self.logic = shopping_logic_instance
        self.api_manager = api_manager_instance
        self.test_mode = test_mode # <-- LƯU CỜ TEST
        
        self.db_manager = db_manager
        
        # === SỬA ĐỔI 2: Chọn Handler dựa trên test_mode ===
        if self.test_mode:
            # Chạy ở chế độ TEST, dùng mock (Mock class được định nghĩa ở __main__)
            print("UI_INIT: Chạy ở chế độ TEST MODE.")
            self.camera_handler = MockCameraHandler() 
            self.recognition_handler = MockRecognitionHandler(self.camera_handler)
        else:
            # Chạy ở chế độ THẬT (giống như file main.py gọi)
            print("UI_INIT: Khởi tạo SerialCameraHandler...")
            self.camera_handler = SerialCameraHandler()
            self.camera_handler.start(cv2_module=cv2)
            self.recognition_handler = FaceRecognitionHandler(camera_handler=self.camera_handler)
        
        # (Phần còn lại của __init__ giữ nguyên)
        
        self.root.withdraw()
        self.root.title("Máy bán hàng tự động")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        try:
            self.root.attributes('-fullscreen', True)
        except tk.TclError:
            self.root.geometry(f"{screen_width}x{screen_height}")

        self.selected_product = None
        self.selected_quantity = 1
        self.quantity_var = tk.StringVar(value="1")
        self.status_message_var = tk.StringVar(value="Chọn sản phẩm để mua hàng")
        self.welcome_message_var = tk.StringVar(value="Chào mừng quý khách!")
        self.selected_button = None
        
        self.customer_info = None
        self.customer_name = ""
        self.points_used_in_transaction = 0 

        self.cached_ad_images = []
        self.cached_product_images = {}
        self.ad_imgs_cycle = None 

        self.keyboard_process = None 
        self.keyboard_launched = False
        self.hide_keyboard_timer = None
        
        self.is_closing = False
        self.enable_post_register_embedding = True

        print("UI_INIT: Bắt đầu kiểm tra và khởi tạo cache nhận diện...")
        self._preload_all_images()
        
        self.main_view = MainView(self.root, self) 
        
        self.update_welcome_message()
        self.update_cart_display_handler() # Cập nhật giỏ hàng lần đầu
        self._update_auth_frame_visibility() 
        
        self._hide_system_taskbar()
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        
        # Chỉ reload cache thật khi không ở test mode
        if not self.test_mode:
            self.recognition_handler.reload_cache()
        
        self.show_welcome_screen() 

    # (Tất cả các hàm từ show_welcome_screen đến _on_background_task_complete giữ nguyên)
    # ==================================================================
    # CÁC PHƯƠNG THỨC GỌI HIỂN THỊ MÀN HÌNH
    # ==================================================================
    def show_welcome_screen(self):
        self._hide_system_taskbar()
        self.root.withdraw()
        WelcomeScreen(self.root, self)

    def show_loading_screen(self):
        LoadingScreen(self.root, self)

    def show_login_screen(self):
        self.root.withdraw()
        LoginScreen(self.root, self) 

    def show_register_screen(self):
        self.root.withdraw()
        RegisterScreen(self.root, self) 

    def show_face_capture_screen(self, name, phone, dob, password, original_register_window):
        FaceCaptureScreen(self.root, self, name, phone, dob, password, original_register_window)

    def _show_confirmation_screen(self):
        self.root.withdraw()
        ConfirmationScreen(self.root, self)

    def show_thank_you_screen(self):
        self.root.withdraw()
        ThankYouScreen(self.root, self)

    # ==================================================================
    # CÁC PHƯƠNG THỨC CALLBACK VÀ LOGIC
    # ==================================================================
    def handle_login_success(self, customer_data):
        print(f"UI-MAIN: Đăng nhập thành công, chào {customer_data['name']}")
        self.customer_info = customer_data
        self.customer_name = customer_data.get('name', '')
        self.logic.set_customer(customer_data)
        self.update_welcome_message()
        self._update_auth_frame_visibility()
        self.root.deiconify()

    def _on_recognition_finished(self, recognized_user_id):
        if not self.root.winfo_exists(): return
        print(f"UI-MAIN: Nhận diện xong, output user_id: {recognized_user_id}")
        
        if recognized_user_id:
            customer_data = db_manager.get_customer_by_id(recognized_user_id)
            if customer_data:
                print(f"UI-MAIN: Lấy thông tin từ DB cục bộ thành công: {customer_data['name']}")
                self.handle_login_success(customer_data) 
                return 
        
        print("UI-MAIN: Nhận diện không thành công hoặc người dùng hủy, vào màn hình chính.")
        messagebox.showwarning("Nhận diện thất bại", "Không nhận diện được khuôn mặt. Vui lòng thử lại sau.")
        self.root.deiconify()
        self.update_welcome_message()
        self._update_auth_frame_visibility()

    def _background_registration_and_embedding(self, name, phone, dob, password, register_window, captured_images_dir):
        registration_data = None
        error_message = None
        try:
            print("[REGISTER_BG] Bước 1: Đăng ký vào DB local...")
            result = db_manager.register_customer(name, phone, dob, password, face_encoding=None)
            if "error" in result:
                raise Exception("Số điện thoại này đã được đăng ký." if result["error"] == "duplicate_phone" else "Lỗi cơ sở dữ liệu.")
            
            registration_data = result
            local_user_id = registration_data['code']
            print(f"[REGISTER_BG] Đăng ký DB local thành công, local_id: {local_user_id}")

            print(f"[REGISTER_BG] Bước 2: Bắt đầu tạo embeddings cho {local_user_id}...")
            # Hàm này sẽ gọi Mock Handler nếu ở test mode
            success = self.recognition_handler.add_new_user_to_db(local_user_id, captured_images_dir)
            if not success:
                db_manager.delete_customer(local_user_id) 
                raise Exception("Không thể tạo dữ liệu khuôn mặt. Vui lòng thử lại.")
            
            print("[REGISTER_BG] Tạo embeddings và cập nhật DB thành công.")
            
            print(f"[REGISTER_BG] Bước 3: Bắt đầu đồng bộ user {name} lên server...")
            sync_thread = threading.Thread(
                target=db_manager.sync_customer_to_server,
                args=(name, phone, dob, password, local_user_id),
                daemon=True
            )
            sync_thread.start()
            print("[REGISTER_BG] Luồng nền hoàn tất thành công.")
        except Exception as e:
            error_message = str(e)
            print(f"[REGISTER_BG] LỖI trong luồng nền: {error_message}")
        finally:
            if captured_images_dir and os.path.exists(captured_images_dir):
                import shutil
                shutil.rmtree(captured_images_dir, ignore_errors=True)

        self.root.after(0, lambda: self._on_background_task_complete(registration_data, error_message, register_window))
    
    def _on_background_task_complete(self, registration_data, error_message, register_window):
        for w in self.root.winfo_children():
            if isinstance(w, FaceCaptureScreen):
                w.destroy()
                break
        if error_message:
            messagebox.showerror("Đăng ký thất bại", f"Đã xảy ra lỗi: {error_message}\nVui lòng thử lại.")
            if register_window and register_window.winfo_exists():
                register_window.deiconify() 
                register_window.lift()
            else:
                self.root.deiconify() 
        elif registration_data:
            print(f"UI: Đăng ký thành công. Tự động đăng nhập cho: {registration_data['name']}")
            self.handle_login_success(registration_data)
            if register_window and register_window.winfo_exists():
                register_window.destroy()
            self.status_message_var.set(f"Đăng ký thành công! Chào mừng {self.customer_name}!")
            self.root.after(5000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))

    # (Tất cả các hàm quản lý Bàn phím/Taskbar/Browser giữ nguyên)
    # ==================================================================
    # CÁC HÀM QUẢN LÝ TASKBAR, KEYBOARD, BROWSER
    # ==================================================================
    def _open_browser_kiosk_mode(self, url):
        print(f"UI: Đang mở trình duyệt ở chế độ kiosk với URL: {url}")
        try:
            command = ['chromium-browser', '--kiosk', '--no-first-run', '--disable-infobars', '--disable-session-crashed-bubble', '--incognito', '--disable-gpu', url]
            subprocess.Popen(command)
        except FileNotFoundError:
            print("LỖI: Lệnh 'chromium-browser' không tìm thấy. Sử dụng webbrowser.open() thay thế.")
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            print(f"Lỗi không xác định khi mở trình duyệt: {e}")

    def _hide_system_taskbar(self):
        if self.test_mode:
            print("[Test Mode] Bỏ qua ẩn taskbar.")
            return
        print("Đang tắt thanh taskbar hệ thống (pkill panel)...")
        try:
            subprocess.run(['pkill', 'panel'], check=False)
        except Exception as e:
            print(f"Lỗi khi tắt taskbar: {e}")

    def _show_system_taskbar(self):
        if self.test_mode:
            print("[Test Mode] Bỏ qua hiện taskbar.")
            return
        print("Đang khởi động lại thanh taskbar hệ thống (lxpanel)...")
        try:
            subprocess.Popen(['lxpanel', '--profile', 'LXDE-pi'])
        except Exception as e:
            print(f"Lỗi khi bật lại taskbar: {e}")

    def _show_keyboard(self):
        if self.test_mode:
            print("[Test Mode] Yêu cầu hiện bàn phím (giả lập).")
            return
        print("Yêu cầu HIỆN bàn phím...")
        if not self.keyboard_launched:
            print("Lần đầu gọi: Đang khởi động tiến trình 'onboard'...")
            try:
                subprocess.Popen(['onboard'])
                self.keyboard_launched = True
            except FileNotFoundError:
                print("LỖI: Lệnh 'onboard' không tìm thấy.")
                return
            print("Đang chờ dịch vụ D-Bus của 'onboard' sẵn sàng...")
            for _ in range(20): 
                result = subprocess.run(
                    ['dbus-send', '--print-reply', '--dest=org.onboard.Onboard',
                     '/org/onboard/Onboard/Keyboard', 'org.freedesktop.DBus.Peer.Ping'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    print("Dịch vụ D-Bus đã sẵn sàng!")
                    break
                time.sleep(0.1)
            else:
                print("Cảnh báo: Hết thời gian chờ, D-Bus của 'onboard' không phản hồi.")
                return
        try:
            print("Gửi lệnh 'Show' qua D-Bus...")
            subprocess.run(
                ['dbus-send', '--type=method_call', '--dest=org.onboard.Onboard',
                 '/org/onboard/Onboard/Keyboard', 'org.onboard.Onboard.Keyboard.Show'],
                check=True, capture_output=True, timeout=1
            )
        except Exception:
            print("Cảnh báo: Không thể gửi lệnh 'Show' qua D-Bus.")

    def _hide_keyboard(self):
        if self.test_mode:
            print("[Test Mode] Yêu cầu ẩn bàn phím (giả lập).")
            return
        print("Yêu cầu ẨN bàn phím...")
        try:
            subprocess.run(
                ['dbus-send', '--type=method_call', '--dest=org.onboard.Onboard',
                 '/org/onboard/Onboard/Keyboard', 'org.onboard.Onboard.Keyboard.Hide'],
                check=True, capture_output=True, timeout=2
            )
        except Exception:
            print("Cảnh báo: Không thể gửi lệnh 'Hide' qua D-Bus.")

    def _cleanup_keyboard(self):
        if self.test_mode:
            print("[Test Mode] Bỏ qua dọn dẹp bàn phím.")
            return
        print("Dọn dẹp cuối cùng: Tắt tất cả tiến trình 'onboard'...")
        try:
            subprocess.run(['pkill', 'onboard'], check=False)
        except FileNotFoundError:
            print("Cảnh báo: Lệnh 'pkill' không tìm thấy.")

    def _handle_focus_in(self, event):
        if self.hide_keyboard_timer:
            self.root.after_cancel(self.hide_keyboard_timer)
            self.hide_keyboard_timer = None
        the_entry = event.widget
        self._show_keyboard()
        self.root.after(10, lambda: the_entry.focus_force())
    
    def _handle_background_click(self, event):
        try:
            event.widget.winfo_toplevel().focus_set()
        except Exception:
            self.root.focus_set()
        self._hide_keyboard()

    def _on_enter_key(self, current_widget, all_widgets):
        try:
            current_index = all_widgets.index(current_widget)
            if current_index == len(all_widgets) - 1:
                self._hide_keyboard()
            else:
                all_widgets[current_index + 1].focus_set()
        except ValueError:
            pass

    # (Hàm _preload_all_images giữ nguyên)
    # ==================================================================
    # PRELOAD HÌNH ẢNH
    # ==================================================================
    def _preload_all_images(self):
        print("Bắt đầu tải trước và xử lý hình ảnh...")
        screen_width = 1920
        screen_height = 1080
        for img_file in AD_IMAGES_CONFIG:
            try:
                img = Image.open(f"{IMAGE_BASE_PATH}{img_file}")
                img = img.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
                self.cached_ad_images.append(ImageTk.PhotoImage(img))
            except Exception as e:
                print(f"Lỗi tải ảnh quảng cáo {img_file}: {e}")
        img_size = (150, 200)
        for product_id, (_, img_file, _) in PRODUCT_IMAGES_CONFIG.items():
            try:
                img_path = f"{IMAGE_BASE_PATH}{img_file}"
                img = Image.open(img_path)
                img = img.resize(img_size, Image.Resampling.LANCZOS)
                self.cached_product_images[product_id] = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"Lỗi tải ảnh sản phẩm {img_file}: {e}")
                self.cached_product_images[product_id] = None
        print("Tải trước hình ảnh hoàn tất!")

    # (Các hàm logic của màn hình chính giữ nguyên)
    # ==================================================================
    # LOGIC NGHIỆP VỤ CỦA MÀN HÌNH CHÍNH
    # ==================================================================
    def _update_auth_frame_visibility(self):
        if not hasattr(self, 'main_view'): return 
        customer_info = self.logic.get_customer()
        if customer_info:
            self.main_view.auth_frame.pack_forget()
        else:
            self.main_view.auth_frame.pack(pady=(10, 15), padx=10, fill=tk.X, before=self.main_view.status_frame)

    def on_product_select(self, product, button):
        if self.selected_product == product:
            self._deselect_product()
            return
        if self.selected_button and self.selected_button.winfo_exists():
            try:
                self.selected_button.config(relief=tk.RAISED, bg="lightyellow", activebackground="lightyellow")
            except: pass
        if button and button.winfo_exists():
            try:
                button.config(relief=tk.SUNKEN, bg="lightgreen", activebackground="lightgreen")
                self.selected_button = button
            except: pass
        self.selected_product = product
        product_id, name, price = product
        self.status_message_var.set(f"✅ ĐÃ CHỌN: {name} - {price:,}đ")
        self.selected_quantity = 1
        self.quantity_var.set("1")

    def _deselect_product(self):
        if self.selected_button and self.selected_button.winfo_exists():
            try:
                self.selected_button.config(relief=tk.RAISED, bg="lightyellow", activebackground="lightyellow")
            except: pass
        self.selected_button = None
        self.selected_product = None
        self.selected_quantity = 1
        self.quantity_var.set("1")
        self.status_message_var.set("Chọn sản phẩm để mua hàng")

    def increase_quantity(self):
        if self.selected_quantity < 99:
            self.selected_quantity += 1
            self.quantity_var.set(str(self.selected_quantity))

    def decrease_quantity(self):
        if self.selected_quantity > 1:
            self.selected_quantity -= 1
            self.quantity_var.set(str(self.selected_quantity))

    def on_confirm_add(self):
        if not self.selected_product:
            self.status_message_var.set("Vui lòng chọn sản phẩm trước!")
            self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        product_id, name, price = self.selected_product
        for _ in range(self.selected_quantity):
            self.logic.current_entry_buffer = product_id
            success, message, _ = self.logic.add_item_from_entry()
            if not success:
                self.status_message_var.set(f"Lỗi: {message}")
                self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
                return
        self.update_cart_display_handler()
        self.status_message_var.set(f"Đã thêm {self.selected_quantity} {name} vào giỏ hàng!")
        self._deselect_product()
        self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))

    def update_cart_display_handler(self, temporary_message=None):
        if not hasattr(self, 'main_view'): return
        
        cart_display = self.main_view.selected_items_display
        cart_display.config(state=tk.NORMAL)
        cart_display.delete(1.0, tk.END)
        
        if temporary_message:
            cart_display.insert(tk.END, temporary_message)
            cart_display.config(state=tk.DISABLED)
            self.root.after(TEMP_MESSAGE_DURATION, lambda: self.update_cart_display_handler())
            return
            
        items_from_logic = self.logic.get_selected_items()
        if not items_from_logic:
             cart_display.tag_configure("center", justify='center')
             cart_display.insert(tk.END, "Chưa có sản phẩm nào\n", "center")
        else:
            product_count = {}
            total_price = 0
            for item_str in items_from_logic:
                for product_id, (name, _, price) in PRODUCT_IMAGES_CONFIG.items():
                    if product_id == item_str:
                        if name in product_count:
                            product_count[name]["count"] += 1
                        else:
                            product_count[name] = {"count": 1, "price": price}
                        total_price += price
                        break
            for name, data in product_count.items():
                cart_display.insert(tk.END, f"{name}: {data['count']} x {data['price']:,}đ\n")
            cart_display.insert(tk.END, "--------------------\n")
            cart_display.insert(tk.END, f"Tổng cộng: {total_price:,}đ")
        
        cart_display.config(state=tk.DISABLED)

    def on_ok_handler(self):
        if not self.logic.get_selected_items():
            self.status_message_var.set("⚠️ Chưa có sản phẩm nào để thanh toán!")
            self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        self._show_confirmation_screen()

    def on_clear_cart_handler(self):
        if not self.logic.get_selected_items():
            self.status_message_var.set("Giỏ hàng đã trống!")
            self.root.after(TEMP_MESSAGE_DURATION, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        message, _ = self.logic.reset_all()
        self.update_cart_display_handler()
        self._deselect_product()
        self.status_message_var.set("✅ Giỏ hàng đã được xóa!")
        self.root.after(TEMP_MESSAGE_DURATION, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))

    def update_welcome_message(self):
        if self.customer_name:
            self.welcome_message_var.set(f"Xin chào {self.customer_name}!")
        else:
            self.welcome_message_var.set("Chào mừng quý khách!")

    # === SỬA ĐỔI 3: Thêm kiểm tra test_mode khi gọi phần cứng ===
    def _finalize_and_sync_transaction(self):
        print("UI: Bắt đầu hoàn tất và đồng bộ giao dịch...")
        items_in_cart = self.logic.get_selected_items()
        if not items_in_cart:
            print("UI WARN: Không có sản phẩm để hoàn tất giao dịch.")
            return

        total_amount = self.logic.get_total_price()
        customer_name = self.customer_name or "Khách vãng lai"
        user_id = self.customer_info.get('code') if self.customer_info else None
        product_counts = Counter(items_in_cart)
        
        items_detail_parts = []
        items_sold_list_for_local_db = []
        for product_id, quantity in product_counts.items():
            name, _, _ = PRODUCT_IMAGES_CONFIG.get(product_id, ("Sản phẩm lỗi", "", 0))
            items_detail_parts.append(f"{name} x{quantity}")
            items_sold_list_for_local_db.append({"product_name": name, "quantity": quantity})
        items_detail_str = ", ".join(items_detail_parts)

        order_code = db_manager.save_transaction(
            total_amount, customer_name, items_detail_str, items_sold_list_for_local_db
        )
        if not order_code:
            print("UI ERROR: Không thể lưu giao dịch vào DB local.")
            return
        print(f"UI: Giao dịch {order_code} đã được lưu vào DB local.")

        if user_id:
            db_manager.update_customer_points(user_id, self.points_used_in_transaction, total_amount)
            print(f"UI: Đã cập nhật điểm cho user {user_id}.")
            self.points_used_in_transaction = 0 

        def sync_transaction_task():
            print(f"SYNC: Bắt đầu đồng bộ đơn hàng {order_code} lên server...")
            final_api_items = [{'product_id': pid, 'quantity': count} for pid, count in product_counts.items()]
            customer_info_for_api = {"user_id": user_id, "name": self.customer_name} if self.customer_info else None
            # Hàm này sẽ gọi MockAPIManager (nếu ở test mode)
            success = self.api_manager.report_transaction(
                total_amount, final_api_items, customer_info_for_api
            )
            if success:
                print(f"SYNC: Đồng bộ đơn hàng {order_code} lên server THÀNH CÔNG.")
                db_manager.mark_transaction_as_synced(order_code)
            else:
                print(f"SYNC: Đồng bộ đơn hàng {order_code} THẤT BẠI. Sẽ thử lại sau.")
        threading.Thread(target=sync_transaction_task, daemon=True).start()

        # 6. ĐIỀU KHIỂN LED (Chỉ khi không ở test mode)
        if not self.test_mode:
            try:
                from core.drivers.PCF8574T import show_payment_leds
                purchased_products_list = list(items_in_cart)
                show_payment_leds(purchased_products_list)
                print(f"I2C: Đã gửi tín hiệu LED cho các sản phẩm: {purchased_products_list}")
            except Exception as e:
                print(f"I2C ERROR: Không thể gửi tín hiệu cho driver LED: {e}")
        else:
            print("[Test Mode] Bỏ qua điều khiển LED.")
            
        # === ĐIỀU KHIỂN MÁY CƠ KHÍ === (Chỉ khi không ở test mode)
        if not self.test_mode:
            try:
                from core.drivers.VendingMotors import dispense_products
                print(f"MOTOR: Bắt đầu đẩy sản phẩm: {items_in_cart}")
                dispense_products(items_in_cart)
                print("MOTOR: Đẩy sản phẩm hoàn tất.")
            except ImportError:
                print("MOTOR WARN: Không tìm thấy file 'core/drivers/VendingMotors.py'. Bỏ qua điều khiển cơ khí.")
            except Exception as e:
                print(f"MOTOR ERROR: Lỗi khi điều khiển máy cơ khí: {e}")
        else:
            print("[Test Mode] Bỏ qua điều khiển máy cơ khí.")
            
    def on_app_close(self, is_welcome_close=False):
        if self.is_closing:
            return
        
        print("UI: Bắt đầu quy trình đóng ứng dụng an toàn...")
        self.is_closing = True

        print("UI: Dừng camera handler...")
        self.camera_handler.stop() # Sẽ gọi MockCamera.stop() nếu ở test mode
        self._cleanup_keyboard()
        self.logic.close_resources()

        if self.hide_keyboard_timer:
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after_cancel(self.hide_keyboard_timer)
            except tk.TclError: pass

        for window in self.root.winfo_children():
            if isinstance(window, tk.Toplevel):
                try:
                    if window.winfo_exists():
                        window.destroy()
                except tk.TclError: pass
        
        try:
            if self.root and self.root.winfo_exists():
                if is_welcome_close:
                    self.root.quit() 
                else:
                    self.root.destroy()
        except tk.TclError:
            pass

        self._show_system_taskbar()

    # (Các hàm preview/build embedding giữ nguyên)
    # ==================================================================
    # CÁC HÀM KHÁC
    # ==================================================================
    def _build_and_save_embeddings_for_user(self, user_id, images_dir):
        return self.recognition_handler.add_new_user_to_db(user_id, images_dir)
        
    def capture_and_preview_5_images(self):
        import os, cv2, numpy as np
        tmp_dir = os.path.join('core', 'Camera_AI', 'database', 'tmp', 'preview_5_images')
        os.makedirs(tmp_dir, exist_ok=True)
        for f in os.listdir(tmp_dir):
            try: os.remove(os.path.join(tmp_dir, f))
            except Exception: pass
        captured = 0
        last_frame = None
        frame_diff_threshold = 1200
        image_paths = []
        print(f"[PREVIEW] Bắt đầu chụp 5 ảnh vào {tmp_dir}")
        while captured < 5:
            frame_bgr = self.camera_handler.get_frame() # Sẽ gọi MockCamera.get_frame()
            if frame_bgr is None: continue
            if last_frame is None or np.sum(np.abs(frame_bgr.astype(np.int16) - last_frame.astype(np.int16))) > frame_diff_threshold:
                img_path = os.path.join(tmp_dir, f"preview_{captured+1}.jpg")
                cv2.imwrite(img_path, frame_bgr)
                image_paths.append(img_path)
                last_frame = frame_bgr.copy()
                captured += 1
                print(f"[PREVIEW] Đã lưu ảnh: {img_path}")
        print(f"[PREVIEW] Hoàn tất, đã lưu 5 ảnh: {image_paths}")
        return image_paths

    def show_preview_5_images_ui(self):
        import os
        from PIL import Image, ImageTk
        import tkinter as tk
        tmp_dir = os.path.join('core', 'Camera_AI', 'database', 'tmp', 'preview_5_images')
        image_files = [os.path.join(tmp_dir, f) for f in sorted(os.listdir(tmp_dir)) if f.endswith('.jpg')]
        if len(image_files) < 5:
            print(f"[PREVIEW_UI] Không đủ 5 ảnh để hiển thị: {image_files}")
            return
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Xem trước 5 ảnh nhận diện")
        preview_window.geometry("1200x300")
        frame = tk.Frame(preview_window)
        frame.pack(expand=True, fill="both")
        
        image_references = []
        for idx, img_path in enumerate(image_files):
            try:
                img = Image.open(img_path)
                img = img.resize((200, 200), Image.Resampling.LANCZOS)
                photo_img = ImageTk.PhotoImage(img)
                
                label = tk.Label(frame, image=photo_img, text=f"Ảnh {idx+1}", compound="bottom")
                label.image = photo_img
                label.pack(side="left", padx=10, pady=10)
                image_references.append(photo_img)
            except Exception as e:
                print(f"Lỗi khi tải ảnh xem trước {img_path}: {e}")
                label = tk.Label(frame, text=f"Lỗi ảnh {idx+1}")
                label.pack(side="left", padx=10, pady=10)
        
        preview_window.lift()
        preview_window.focus_force()

# ==================================================================
# KHỐI CHẠY CHÍNH CỦA ỨNG DỤNG (ĐÃ SỬA ĐỔI)
# ==================================================================

# === SỬA ĐỔI 4: Thêm các Mock Class vào khối __main__ ===

class MockCameraHandler:
    """Giả lập camera, chỉ trả về ảnh xám."""
    def start(self, cv2_module):
        print("[Mock Camera] Đã khởi động.")
    
    def get_frame(self):
        # Trả về một ảnh 112x112 màu xám
        return np.full((112, 112, 3), 128, dtype=np.uint8)
        
    def stop(self):
        print("[Mock Camera] Đã dừng.")

class MockRecognitionHandler:
    """Giả lập hệ thống AI, không nhận diện ai cả."""
    def __init__(self, camera_handler):
        print("[Mock Recognition] Đã khởi động.")
        self._faiss_index = None # Giả lập là không có CSDL
        self._labels = []

    def reload_cache(self):
        print("[Mock Recognition] Đã tải lại cache (không làm gì cả).")
    
    def get_embedding(self, frame):
        print("[Mock Recognition] Lấy embedding (trả về None).")
        return None
    
    def add_new_user_to_db(self, user_id, images_dir):
        print(f"[Mock Recognition] Giả lập thêm user {user_id} thành công.")
        return True # Giả lập thành công

if __name__ == "__main__":
    
    class MockAPIManager:
        def report_transaction(self, total, items, customer):
            print(f"[Mock API] Báo cáo giao dịch: {total}đ, {items}, {customer}")
            return True 
        
        def login_customer(self, phone, password):
            print(f"[Mock API] Thử đăng nhập: {phone}")
            return None 

        def get_customer_by_id(self, user_id):
            print(f"[Mock API] Lấy thông tin: {user_id}")
            return None 
            
    try:
        print("Khởi động ứng dụng chính (CHẾ ĐỘ TEST GIAO DIỆN)...")       
        root = ctk.CTk()
        root.withdraw() 
        
        shopping_logic = ShoppingLogic()
        api_manager = MockAPIManager() 
        
        # === SỬA ĐỔI 5: Truyền test_mode=True ===
        app_controller = AdvancedUIManager(
            root, 
            shopping_logic, 
            api_manager, 
            test_mode=True # <-- BẬT CHẾ ĐỘ TEST
        )
        
        root.mainloop()
        
    except Exception as e:
        print(f"LỖI NGHIÊM TRỌNG KHI KHỞI ĐỘNG: {e}")
        import traceback
        traceback.print_exc()
        try:
            if 'app_controller' in locals():
                app_controller.on_app_close()
        except Exception:
            pass
    finally:
        print("Ứng dụng (test mode) đã đóng.")