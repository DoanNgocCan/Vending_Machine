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
import numpy as np
import pickle
from collections import Counter
# Thêm code này để Python tìm thấy thư mục 'core' và 'config.py'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..') # Đi lùi 2 cấp (từ /core/ui/ -> /)
sys.path.append(project_root)

# --- Imports từ project ---
import core.Camera_AI.face_recognition_library
from core.Camera_AI.face_recognition_library import FaceRecognitionSystemWebcam
from core.features.shopping_logic import ShoppingLogic
from core.database.local_database_manager import db_manager
from core.drivers.audio_driver import AudioDriver
from config import TEMP_MESSAGE_DURATION, IMAGE_BASE_PATH, AD_IMAGES_CONFIG

# --- Imports các màn hình UI đã tách ---
from core.ui.ui_welcome import WelcomeScreen
from core.ui.ai_face_login_screen import AIFaceLoginScreen
from core.ui.ai_face_register_screen import AIFaceRegistrationScreen
from core.ui.ui_login import LoginScreen
from core.ui.ui_register import RegisterScreen
from core.ui.ui_confirmation import ConfirmationScreen
from core.ui.ui_thankyou import ThankYouScreen
from core.ui.ui_main import MainView
from core.features.background_sync import sync_manager

class AdvancedUIManager:
    # --- Cấu hình (giữ nguyên) ---
    CAPTURE_WIDTH = 1280
    CAPTURE_HEIGHT = 720
    TARGET_FPS = 30
    BLUR_THRESHOLD = 60.0
    BRIGHTNESS_MIN = 40
    BRIGHTNESS_MAX = 210
    
    def __init__(self, root, shopping_logic_instance, api_manager_instance):
        self.root = root
        self.logic = shopping_logic_instance
        self.api_manager = api_manager_instance
        self.audio_driver = AudioDriver()

        # Thêm db_manager vào self để LoginScreen có thể truy cập
        self.db_manager = db_manager
        print("UI_INIT: Khởi tạo Hệ thống AI Camera (FaceRecognitionSystemWebcam)...")
        try:
            # Dòng này sẽ khởi tạo model EdgeFace, MediaPipe, FAISS
            # và tự khởi động luồng webcam (daemon)
            self.camera_ai_system = FaceRecognitionSystemWebcam()
            print("UI_INIT: Hệ thống AI Camera đã sẵn sàng.")
            self.stop_camera_service()
        except FileNotFoundError as e:
            print(f"LỖI NGHIÊM TRỌNG: Không tìm thấy file model: {e}")
            messagebox.showerror("Lỗi AI", f"Không tìm thấy file model AI: {e}\nVui lòng kiểm tra thư mục 'checkpoints'. Ứng dụng sẽ thoát.")
            self.root.destroy()
            return
        except Exception as e:
            print(f"LỖI NGHIÊM TRỌNG: Không thể khởi tạo FaceRecognitionSystemWebcam: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Lỗi AI", f"Không thể tải model AI: {e}\nỨng dụng sẽ thoát.")
            self.root.destroy()
            return
        
        self.root.withdraw()
        self.root.title("Máy bán hàng tự động")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        try:
            self.root.attributes('-fullscreen', True)
        except tk.TclError:
            self.root.geometry(f"{screen_width}x{screen_height}")

        # --- Trạng thái giao diện chính ---
        self.selected_product = None
        self.selected_quantity = 1
        self.max_available_quantity = 1
        self.quantity_var = tk.StringVar(value="1")
        self.status_message_var = tk.StringVar(value="Chọn sản phẩm để mua hàng")
        self.welcome_message_var = tk.StringVar(value="Chào mừng quý khách!")
        self.selected_button = None
        
        # --- Trạng thái khách hàng & Giao dịch ---
        self.customer_info = None
        self.customer_name = ""
        self.points_used_in_transaction = 0 

        # --- Cache hình ảnh (dùng chung) ---
        self.cached_ad_images = []
        self.cached_product_images = {}
        self.ad_imgs_cycle = None # Vòng lặp này sẽ được WelcomeScreen sử dụng

        # --- Quản lý Keyboard & Taskbar ---
        self.keyboard_process = None 
        self.keyboard_launched = False
        self.hide_keyboard_timer = None
        self.keyboard_visible_state = False
        
        self.is_closing = False
        self.enable_post_register_embedding = True

        print("UI_INIT: Bắt đầu kiểm tra và khởi tạo cache nhận diện...")
        self._preload_all_images()
        
        self.main_view = MainView(self.root, self)
        try:
            from core.features.mqtt_client import mqtt_manager
            mqtt_manager.setup(
                db_manager=self.db_manager,
                api_manager=self.api_manager,
                ui_refresh_callback=lambda: self.root.after(100, self.main_view.refresh_product_grid),
                # SỬA DÒNG BÊN DƯỚI: Đổi từ main_view.hot_update_ui sang self._on_hot_update
                product_update_callback=lambda old, new, p, q: self.root.after(100, lambda: self._on_hot_update(old, new, p, q))
            )
            mqtt_manager.connect()
        except Exception as e:
            print(f"Lỗi khởi tạo MQTT: {e}")
        
        self.update_welcome_message()
        self._update_auth_frame_visibility() # Bây giờ hàm này sẽ hoạt động
        
        self._hide_system_taskbar()
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.root.bind_all("<Escape>", lambda event: self.on_app_close())
        
        # --- BẮT ĐẦU ỨNG DỤNG ---
        self.show_welcome_screen() # <--- Bắt đầu bằng màn hình chào mừng

    # ==================================================================
    # CÁC PHƯƠNG THỨC GỌI HIỂN THỊ MÀN HÌNH (ĐÃ ĐƯỢC REFACTOR)
    # ==================================================================

    def show_welcome_screen(self):
        """
        Hiển thị màn hình quảng cáo.
        Class WelcomeScreen sẽ tự xử lý vòng đời của nó.
        """
        WelcomeScreen(self.root, self)
        self.root.withdraw()
        print("UI: Chuyển sang màn hình Welcome -> Trigger Sync Data")
        sync_manager.trigger_sync()
        if hasattr(self, 'main_view'):
            print("UI_CONTROLLER: Đang cập nhật lại giá và tồn kho cho MainView...")
            self.main_view.refresh_product_grid()

    def show_loading_screen(self):
        """
        Hiển thị màn hình nhận diện.
        """
        AIFaceLoginScreen(self.root, self)
        self.root.withdraw()
    def show_login_screen(self):
        """Hiển thị màn hình đăng nhập SĐT/Mật khẩu."""
        LoginScreen(self.root, self)
        self.root.withdraw()
    def show_register_screen(self):
        """Hiển thị màn hình đăng ký."""
        RegisterScreen(self.root, self) 
        self.root.withdraw()
    def show_face_capture_screen(self, local_user_id, name, phone, email, password, original_register_window):
        """
        Hiển thị màn hình chụp ảnh (được gọi bởi RegisterScreen).
        """
        AIFaceRegistrationScreen(self.root, self, local_user_id, name, phone, email, password, original_register_window)

    def _show_confirmation_screen(self):
        """
        Hiển thị màn hình xác nhận (được gọi bởi on_ok_handler).
        """
        ConfirmationScreen(self.root, self)
        self.root.withdraw()

    def show_thank_you_screen(self):
        """
        Hiển thị màn hình cảm ơn (được gọi khi thanh toán thành công).
        """
        self.audio_driver.play_thank_you_async(self.customer_name)
        ThankYouScreen(self.root, self)
        self.root.withdraw()

    # ==================================================================
    # CÁC PHƯƠNG THỨC CALLBACK VÀ LOGIC (DÙNG CHUNG)
    # ==================================================================
    def _close_all_toplevels(self):
        """Đóng tất cả cửa sổ con (Toplevel) để tránh chồng lấn giao diện."""
        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Toplevel):
                try:
                    widget.destroy()
                except Exception:
                    pass
        # Đảm bảo root được ẩn đúng cách nếu dùng Toplevel làm màn hình chính
        self.root.withdraw()

    def start_camera_service(self):
        """Bật camera"""
        if hasattr(self.camera_ai_system, "start_capture"):
            self.camera_ai_system.start_capture()

    def stop_camera_service(self):
        """Tắt camera"""
        if hasattr(self.camera_ai_system, "stop_capture"):
            self.camera_ai_system.stop_capture()
    def handle_login_success(self, customer_data):
        """
        Xử lý logic chung khi đăng nhập thành công (từ bất kỳ màn hình nào).
        """
        print(f"UI-MAIN: Đăng nhập thành công, chào {customer_data['name']}")
        self.customer_info = customer_data
        self.customer_name = customer_data.get('name', '')
        self.logic.set_customer(customer_data)
        
        self.update_welcome_message()
        self._update_auth_frame_visibility()
        
        self.root.deiconify()

    def _on_recognition_finished(self, recognized_user_id):
        """
        Callback khi luồng nhận diện (từ AIFaceLoginScreen) hoàn tất.
        Hàm này giữ nguyên logic, chỉ cần AIFaceLoginScreen gọi nó.
        """
        if not self.root.winfo_exists(): return

        print(f"UI-MAIN: Nhận diện xong, output user_id: {recognized_user_id}")
        
        # recognized_user_id bây giờ là string (từ FAISS)
        # Cần đảm bảo nó khớp với 'code' trong DB
        if recognized_user_id and recognized_user_id != "Unknown":
            # Thử tìm user bằng 'code' (là user_id)
            customer_data = db_manager.get_customer_by_id(recognized_user_id)
            if customer_data:
                print(f"UI-MAIN: Lấy thông tin từ DB cục bộ thành công: {customer_data['name']}")
                self.handle_login_success(customer_data) 
                self.root.deiconify() # Đảm bảo màn hình chính hiện lên
                return 
            else:
                print(f"UI-MAIN: Lỗi: FAISS trả về ID {recognized_user_id} nhưng không có trong DB local.")
        
        print("UI-MAIN: Nhận diện không thành công hoặc người dùng hủy, vào màn hình chính.")
        self.root.deiconify()
        self.update_welcome_message()
        self._update_auth_frame_visibility()


    def _background_registration_and_embedding(self, name, phone, email, password, register_window, local_user_id):
        """
        (CHẠY TRÊN LUỒNG NỀN)
        Hàm này được gọi bởi AIFaceRegistrationScreen SAU KHI chụp ảnh.
        Nó chỉ còn nhiệm vụ đồng bộ lên server.
        """
        registration_data = None
        error_message = None

        try:
            print(f"[REGISTER_BG] Bước 3 (sau khi chụp ảnh): Bắt đầu đồng bộ user {name} (ID: {local_user_id}) lên server...")
            
            # Lấy lại thông tin user vừa đăng ký
            registration_data = db_manager.get_customer_by_id(local_user_id)
            if not registration_data:
                raise Exception(f"Không tìm thấy user {local_user_id} trong DB local sau khi đăng ký.")
                
            sync_thread = threading.Thread(
                target=db_manager.sync_customer_to_server,
                args=(name, phone, email, password, local_user_id),
                daemon=True
            )
            sync_thread.start()
            
            print("[REGISTER_BG] Luồng nền (đồng bộ) hoàn tất thành công.")

        except Exception as e:
            error_message = str(e)
            print(f"[REGISTER_BG] LỖI trong luồng nền đồng bộ: {error_message}")
        finally:
            # Không cần xóa captured_images_dir nữa vì thư viện AI tự xử lý
            pass
        pass
    
    def get_latest_inventory(self):
        """Hàm bridge để UI gọi lấy tồn kho từ DB"""
        return self.db_manager.get_inventory_map()
    
    def _on_background_task_complete(self, registration_data, error_message, register_window):
        """
        Luồng UI: Xử lý kết quả đăng ký (Được gọi bởi AIFaceRegistrationScreen).
        """
        # Đảm bảo cửa sổ AI register đã đóng
        for w in self.root.winfo_children():
            if isinstance(w, AIFaceRegistrationScreen):
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
            self.root.deiconify() # Hiển thị màn hình chính

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

    # --- TRONG FILE: core/ui/ui_controller.py ---

    def _hide_system_taskbar(self):
        # print("Đang tắt thanh taskbar hệ thống (pkill panel)...") 
        try:
            # [SỬA ĐỔI] Dùng Popen thay vì run để KHÔNG chặn giao diện
            subprocess.Popen(['pkill', 'panel'])
        except Exception as e:
            print(f"Lỗi khi tắt taskbar: {e}")

    def _show_system_taskbar(self):
        print("Đang khởi động lại thanh taskbar hệ thống (lxpanel)...")
        try:
            # [SỬA ĐỔI] Dùng Popen thay vì run/Popen cũ để đảm bảo mượt mà
            subprocess.Popen(['lxpanel', '--profile', 'LXDE-pi'])
        except Exception as e:
            print(f"Lỗi khi bật lại taskbar: {e}")

    def _show_keyboard(self):
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
        print("Dọn dẹp bàn phím: Tắt hoàn toàn tiến trình 'onboard'...")
        try:
            subprocess.run(['pkill', 'onboard'], check=False)
        except FileNotFoundError:
            print("Cảnh báo: Lệnh 'pkill' không tìm thấy.")
        finally:
            # Reset lại toàn bộ cờ trạng thái để lần sau mở lại nó sẽ tự khởi động lại
            self.keyboard_launched = False
            self.keyboard_visible_state = False
            if self.hide_keyboard_timer:
                self.root.after_cancel(self.hide_keyboard_timer)
                self.hide_keyboard_timer = None

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

    # ==================================================================
    # PRELOAD HÌNH ẢNH
    # ==================================================================
    
    def _preload_all_images(self):
        print("Bắt đầu tải trước và xử lý hình ảnh...")
        screen_width = 1920
        screen_height = 1080
        
        # 1. Tải ảnh quảng cáo
        for img_file in AD_IMAGES_CONFIG:
            try:
                img = Image.open(f"{IMAGE_BASE_PATH}{img_file}")
                img = img.resize((screen_width, screen_height), Image.Resampling.LANCZOS)
                self.cached_ad_images.append(ImageTk.PhotoImage(img))
            except Exception as e:
                print(f"Lỗi tải ảnh quảng cáo {img_file}: {e}")
                
        # 2. Tải ảnh sản phẩm TỪ DATABASE LOCAL
        img_size = (150, 200)
        try:
            # Lấy map tồn kho mới nhất (Key là slot, Value là data sản phẩm)
            current_inventory = self.get_latest_inventory()
            
            for slot, product_data in current_inventory.items():
                img_path = product_data.get("image_path")
                item_name = product_data.get("item_name")
                
                # Kiểm tra xem đường dẫn ảnh có tồn tại trên máy client không
                if img_path and os.path.exists(img_path):
                    try:
                        current_mtime = os.path.getmtime(img_path)
                        img = Image.open(img_path)
                        img = img.resize(img_size, Image.Resampling.LANCZOS)
                        
                        # LƯU Ý THAY ĐỔI Ở ĐÂY: Lưu dạng dictionary thay vì chỉ lưu đối tượng PhotoImage
                        self.cached_product_images[slot] = {
                            "path": img_path,
                            "mtime": current_mtime,
                            "image": ImageTk.PhotoImage(img)
                        }
                    except Exception as e:
                        print(f"Lỗi tải ảnh sản phẩm '{item_name}' (Ô số {slot}): {e}")
                        self.cached_product_images[slot] = None
                else:
                    self.cached_product_images[slot] = None
                    
        except Exception as e:
            print(f"Lỗi khi preload ảnh sản phẩm từ DB: {e}")
            
        print("Tải trước hình ảnh hoàn tất!")

    # ==================================================================
    # LOGIC NGHIỆP VỤ CỦA MÀN HÌNH CHÍNH
    # ==================================================================
    
    def _update_auth_frame_visibility(self):
        # === SỬA LỖI KẾT NỐI ===
        # Truy cập các widget thông qua self.main_view
        if not hasattr(self, 'main_view'): return # Chưa khởi tạo, bỏ qua
        
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
        current_inventory = self.get_latest_inventory()
        
        product_data = {}
        for slot, data in current_inventory.items():
            if data.get('item_name') == name:
                product_data = data
                break
                
        real_stock = product_data.get('qty', 0)
        qty_in_cart = 0
        for item in self.logic.cart:
            if item['id'] == product_id:
                qty_in_cart += item['quantity']
                
        # Số lượng thực sự có thể thêm vào giỏ lúc này
        available_stock = real_stock - qty_in_cart 
        # Gán giới hạn mới cho các nút tăng/giảm số lượng
        self.max_available_quantity = available_stock
        
        if available_stock > 0:
            self.selected_quantity = 1
            self.status_message_var.set(f"✅ ĐÃ CHỌN: {name} - {price:,}đ (Còn lại: {available_stock})")
        else:
            self.selected_quantity = 0
            if real_stock > 0:
                # Trường hợp kho còn nhưng đã gom hết vào giỏ
                self.status_message_var.set(f"⚠️ Bạn đã gom toàn bộ {real_stock} {name} vào giỏ!")
            else:
                # Trường hợp kho trống rỗng từ đầu
                self.status_message_var.set(f"❌ {name} hiện đang hết hàng!")
            
        self.quantity_var.set(str(self.selected_quantity))

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
        """
        Tăng số lượng nhưng không vượt quá tồn kho (Đã vá lỗi crash).
        """
        if not self.selected_product:
            return

        # Kiểm tra logic: Không được tăng quá 99 VÀ không được quá tồn kho thực tế
        if self.selected_quantity < 99 and self.selected_quantity < self.max_available_quantity:
            self.selected_quantity += 1
            self.quantity_var.set(str(self.selected_quantity))
        elif self.selected_quantity >= self.max_available_quantity:
            # Thông báo cho người dùng biết đã max
            self.status_message_var.set(f"⚠️ Chỉ còn {self.max_available_quantity} sản phẩm trong máy!")
            
            # --- CƠ CHẾ KHÔI PHỤC AN TOÀN ---
            # Lấy tên sản phẩm ra một biến cục bộ để tránh bị mất dữ liệu nếu user hủy chọn
            current_name = self.selected_product[1]
            
            def reset_msg():
                # Chỉ khôi phục text nếu khách vẫn ĐANG CHỌN đúng sản phẩm đó
                if self.selected_product and self.selected_product[1] == current_name:
                    self.status_message_var.set(f"Chọn số lượng cho {current_name}")
            
            # Đặt lịch chạy hàm an toàn sau 2 giây
            self.root.after(2000, reset_msg)

    def decrease_quantity(self):
        """
        Giảm số lượng nhưng không nhỏ hơn 1 (Đã vá lỗi crash).
        """
        if not self.selected_product:
            return
            
        if self.selected_quantity > 1:
            self.selected_quantity -= 1
            self.quantity_var.set(str(self.selected_quantity))
        else:
            self.status_message_var.set("⚠️ Số lượng tối thiểu là 1")
            
            # --- CƠ CHẾ KHÔI PHỤC AN TOÀN ---
            current_name = self.selected_product[1]
            
            def reset_msg():
                if self.selected_product and self.selected_product[1] == current_name:
                    self.status_message_var.set(f"Chọn số lượng cho {current_name}")
            
            self.root.after(2000, reset_msg)

    def on_confirm_add(self):
        if not self.selected_product:
            self.status_message_var.set("Vui lòng chọn sản phẩm trước!")
            self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        
        # Lấy thông tin sản phẩm đang chọn
        product_id, name, price = self.selected_product
        selected_slot = product_id
        
        # Kiểm tra tồn kho
        if self.selected_quantity > self.max_available_quantity:
             self.status_message_var.set(f"Lỗi: Không đủ hàng (Còn {self.max_available_quantity})")
             return
        if self.selected_quantity <= 0:
             self.status_message_var.set("Sản phẩm đã hết hàng")
             return

        found = False
        for item in self.logic.cart:
            if item['id'] == product_id:
                item['quantity'] += self.selected_quantity
                item['total'] = item['quantity'] * item['price']
                found = True
                break
        
        if not found:
            self.logic.cart.append({
                'id': product_id,
                'name': name,
                'price': price,
                'quantity': self.selected_quantity,
                'total': price * self.selected_quantity,
                'slot': selected_slot
            })
                
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
            
        # --- [SỬA] TRUY CẬP TRỰC TIẾP VÀO self.logic.cart ---
        items_in_cart = self.logic.cart 
        # ----------------------------------------------------
        
        if not items_in_cart:
             cart_display.tag_configure("center", justify='center')
             cart_display.insert(tk.END, "Giỏ hàng trống\n", "center")
        else:
            total_price = 0
            # Duyệt qua từng item (dạng Dict)
            for item in items_in_cart:
                name = item['name']
                quantity = item['quantity']
                price = item['price']
                total = item['total']
                total_price += total
                
                # Hiển thị chi tiết: Tên: SL x Giá
                cart_display.insert(tk.END, f"{name}: {quantity} x {int(price):,}đ\n")
            
            cart_display.insert(tk.END, "--------------------\n")
            cart_display.insert(tk.END, f"Tổng cộng: {int(total_price):,}đ")
        
        cart_display.config(state=tk.DISABLED)

    def on_ok_handler(self):
        """Nút THANH TOÁN"""
        # [SỬA] Kiểm tra self.logic.cart
        if not self.logic.cart:
            self.status_message_var.set("⚠️ Giỏ hàng trống!")
            self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        self._show_confirmation_screen()

    def on_clear_cart_handler(self):
        """Nút RESET"""
        # [SỬA] Xóa trực tiếp self.logic.cart
        self.logic.cart.clear()
        
        self.update_cart_display_handler()
        self._deselect_product()
        self.status_message_var.set("✅ Đã xóa giỏ hàng")
        self.root.after(TEMP_MESSAGE_DURATION, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
    def return_to_welcome(self):
        """
        Nút THOÁT trên UI sẽ gọi hàm này để:
        1. Xóa giỏ hàng.
        2. Đăng xuất tài khoản khách hàng.
        3. Quay về màn hình quảng cáo (Welcome Screen).
        """
        print("UI: Đang reset phiên làm việc và quay về màn hình chờ...")
        
        self.logic.cart.clear()
        self.update_cart_display_handler()
        self._deselect_product()
        self.status_message_var.set("Chọn sản phẩm để mua hàng")

        self.customer_info = None
        self.customer_name = ""
        self.points_used_in_transaction = 0
        self.logic.set_customer(None) 
        
        self.update_welcome_message()
        self._update_auth_frame_visibility()
        
        self.show_welcome_screen()
    def update_welcome_message(self):
        """Cập nhật lời chào với tên khách hàng"""
        if self.customer_name:
            self.welcome_message_var.set(f"Xin chào {self.customer_name}!")
        else:
            self.welcome_message_var.set("Chào mừng quý khách!")

    def _on_hot_update(self, old_name, new_name, price, quantity):
        """Cập nhật Giỏ hàng và Trạng thái chọn khi có Hot Update từ MQTT"""
        
        # 1. Cập nhật nút bấm trên Giao diện (UI)
        self.main_view.hot_update_ui(old_name, new_name, price, quantity)
        
        # 2. Cập nhật lại giá tiền NẾU sản phẩm đó đang nằm trong giỏ hàng
        cart_changed = False
        qty_in_cart = 0
        for item in self.logic.cart:
            if item['name'] == old_name:
                item['name'] = new_name
                item['price'] = float(price)
                item['total'] = item['quantity'] * item['price'] # Tính lại tổng tiền
                qty_in_cart = item['quantity']
                cart_changed = True
                
        # Nếu giỏ hàng có thay đổi, vẽ lại giỏ hàng ngay lập tức
        if cart_changed:
            self.update_cart_display_handler()

        # 3. Cập nhật trạng thái NẾU khách hàng đang click chọn sẵn sản phẩm này
        if self.selected_product and self.selected_product[1] == old_name:
            product_id = self.selected_product[0]
            # Cập nhật tuple bộ nhớ với tên và giá mới
            self.selected_product = (product_id, new_name, float(price))
            
            # Tính lại tồn kho thực tế (trừ đi phần đã lỡ cho vào giỏ)
            self.max_available_quantity = quantity - qty_in_cart
            
            if self.selected_quantity > self.max_available_quantity:
                self.selected_quantity = max(1, self.max_available_quantity)
                
            if self.max_available_quantity > 0:
                self.status_message_var.set(f"✅ ĐÃ CHỌN: {new_name} - {int(price):,}đ (Còn lại: {self.max_available_quantity})")
                if self.selected_quantity == 0: self.selected_quantity = 1
            else:
                self.status_message_var.set(f"❌ {new_name} hiện đang hết hàng!")
                self.selected_quantity = 0
                
            self.quantity_var.set(str(self.selected_quantity))
    # ==================================================================
    # XỬ LÝ GIAO DỊCH VÀ ĐÓNG ỨNG DỤNG
    # ==================================================================

    def _finalize_and_sync_transaction(self):
        print("UI: Bắt đầu hoàn tất giao dịch...")
        
        # --- [SỬA] LẤY DỮ LIỆU TỪ self.logic.cart ---
        items_in_cart = self.logic.cart
        if not items_in_cart: return

        # Tính tổng tiền trực tiếp từ giỏ
        gross_total_amount = sum(item['total'] for item in items_in_cart)
        # ---------------------------------------------
        
        # Xử lý giảm giá (Logic cũ giữ nguyên)
        bulk_discount_amount = 2000 if gross_total_amount > 20000 else 0
        points_redemption_cash_value = self.points_used_in_transaction * 100
        total_discount_value = bulk_discount_amount + points_redemption_cash_value
        
        customer_name = self.customer_name or "Khách vãng lai"
        user_id = self.customer_info.get('code') if self.customer_info else None
        points_used = self.points_used_in_transaction
        
        # Chuẩn bị dữ liệu cho DB Local
        items_detail_parts = []
        items_sold_list_for_local_db = []
        
        # --- [SỬA] DUYỆT QUA LIST DICT ---
        for item in items_in_cart:
            p_name = item['name']
            p_qty = item['quantity']
            # p_id = item['id'] # Nếu cần dùng ID
            
            items_detail_parts.append(f"{p_name} x{p_qty}")
            items_sold_list_for_local_db.append({"product_name": p_name, "quantity": p_qty})
        # ---------------------------------
            
        items_detail_str = ", ".join(items_detail_parts)

        # Worker Thread (Giữ nguyên logic luồng)
        def transaction_worker():
            try:
                # 1. Lưu DB Local
                order_code = self.db_manager.save_transaction(
                    gross_total_amount, user_id, items_detail_str, items_sold_list_for_local_db
                )
                if not order_code: return

                # Cập nhật điểm
                final_new_points = 0
                if user_id:
                    eligible_amount = max(0, gross_total_amount - total_discount_value)
                    self.db_manager.update_customer_points(user_id, points_used, eligible_amount)
                    user = self.db_manager.get_customer_by_id(user_id)
                    if user: final_new_points = user['points']

                # 2. Hardware LED
                items_slot_list = []
                for item in items_in_cart:
                    items_slot_list.extend([item['slot']] * item['quantity'])
                
                try:
                    from core.drivers.PCF8574T import show_payment_leds
                    show_payment_leds(items_slot_list)
                except ImportError: pass

                # 3. Sync Server
                final_api_items = []
                for item in items_in_cart:
                    final_api_items.append({
                        'product_name': item['name'],
                        'product_id': item['id'],                   
                        'quantity': item['quantity']
                    })
                
                cust_api = None
                if user_id:
                    cust_api = {"user_id": user_id, "name": customer_name, "new_total_points": final_new_points}

                if self.api_manager.report_transaction(gross_total_amount, final_api_items, cust_api):
                    self.db_manager.mark_transaction_as_synced(order_code)

            except Exception as e:
                print(f"WORKER ERROR: {e}")

        threading.Thread(target=transaction_worker, daemon=True).start()
    def on_app_close(self, is_welcome_close=False):
        if self.is_closing:
            return
        
        print("UI: Bắt đầu quy trình đóng ứng dụng an toàn...")
        self.is_closing = True

        try:
            # Lấy danh sách tất cả các ID sự kiện 'after' đang chờ
            pending_afters = self.root.tk.call('after', 'info')
            for after_id in pending_afters:
                self.root.after_cancel(after_id)
            print("UI: Đã dọn dẹp sạch các bộ đếm thời gian chạy ngầm.")
        except Exception as e:
            print(f"UI: Lỗi dọn dẹp after events (có thể bỏ qua): {e}")
            
        try:
            from core.features.mqtt_client import mqtt_manager
            mqtt_manager.disconnect()
        except: pass
        print("UI: Dừng camera handler...")
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

# ==================================================================
# KHỐI CHẠY CHÍNH CỦA ỨNG DỤNG (KHÔNG THAY ĐỔI)
# ==================================================================

if __name__ == "__main__":
    # Đây là điểm khởi đầu của toàn bộ ứng dụng.
    
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
        print("Khởi động ứng dụng chính...")
        
        # 1. Khởi tạo root window
        root = ctk.CTk()
        root.withdraw() 
        
        # 2. Khởi tạo các logic nghiệp vụ
        shopping_logic = ShoppingLogic()
        api_manager = MockAPIManager() 
        
        # 3. Khởi tạo Controller chính (AdvancedUIManager)
        app_controller = AdvancedUIManager(root, shopping_logic, api_manager)
        
        # 4. Bắt đầu vòng lặp
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
        print("Ứng dụng đã đóng.")