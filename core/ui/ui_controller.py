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
from config import TEMP_MESSAGE_DURATION, IMAGE_BASE_PATH, PRODUCT_IMAGES_CONFIG, AD_IMAGES_CONFIG

# --- Imports các màn hình UI đã tách ---
from core.ui.ui_welcome import WelcomeScreen
from .ai_face_login_screen import AIFaceLoginScreen
from .ai_face_register_screen import AIFaceRegistrationScreen
from core.ui.ui_login import LoginScreen
from core.ui.ui_register import RegisterScreen
from core.ui.ui_confirmation import ConfirmationScreen
from core.ui.ui_thankyou import ThankYouScreen
from core.ui.ui_main import MainView

class AdvancedUIManager:
    # --- Cấu hình (giữ nguyên) ---
    CAPTURE_WIDTH = 1280
    CAPTURE_HEIGHT = 720
    TARGET_FPS = 30
    BLUR_THRESHOLD = 60.0
    BRIGHTNESS_MIN = 40
    BRIGHTNESS_MAX = 210
    
    # --- Biến toàn cục (để dùng chung) ---
    PRODUCT_IMAGES_CONFIG = PRODUCT_IMAGES_CONFIG


    def __init__(self, root, shopping_logic_instance, api_manager_instance):
        self.root = root
        self.logic = shopping_logic_instance
        self.api_manager = api_manager_instance
        
        # Thêm db_manager vào self để LoginScreen có thể truy cập
        self.db_manager = db_manager
        print("UI_INIT: Khởi tạo Hệ thống AI Camera (FaceRecognitionSystemWebcam)...")
        try:
            # Dòng này sẽ khởi tạo model EdgeFace, MediaPipe, FAISS
            # và tự khởi động luồng webcam (daemon)
            self.camera_ai_system = FaceRecognitionSystemWebcam()
            print("UI_INIT: Hệ thống AI Camera đã sẵn sàng.")
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
        
        self.is_closing = False
        self.enable_post_register_embedding = True

        print("UI_INIT: Bắt đầu kiểm tra và khởi tạo cache nhận diện...")
        self._preload_all_images()
        
        # === SỬA LỖI KẾT NỐI ===
        # Khởi tạo MainView và lưu tham chiếu
        self.main_view = MainView(self.root, self)
        # =========================
        
        self.update_welcome_message()
        self._update_auth_frame_visibility() # Bây giờ hàm này sẽ hoạt động
        
        self._hide_system_taskbar()
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        
        
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
        self._hide_system_taskbar()
        WelcomeScreen(self.root, self)
        self.root.withdraw()

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
    def show_face_capture_screen(self, local_user_id, name, phone, dob, password, original_register_window):
        """
        Hiển thị màn hình chụp ảnh (được gọi bởi RegisterScreen).
        """
        AIFaceRegistrationScreen(self.root, self, local_user_id, name, phone, dob, password, original_register_window)

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
        ThankYouScreen(self.root, self)
        self.root.withdraw()

    # ==================================================================
    # CÁC PHƯƠNG THỨC CALLBACK VÀ LOGIC (DÙNG CHUNG)
    # ==================================================================

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


    def _background_registration_and_embedding(self, name, phone, dob, password, register_window, local_user_id):
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
                args=(name, phone, dob, password, local_user_id),
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

        # Hàm này sẽ được gọi từ AIFaceRegistrationScreen
        # self.root.after(0, lambda: self._on_background_task_complete(registration_data, error_message, register_window))
        
        # Thay vào đó, chúng ta sẽ cho AIFaceRegistrationScreen tự gọi
        # _on_background_task_complete sau khi nó hoàn tất.
        # Hàm này chỉ để chạy luồng đồng bộ.
        pass
    
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

    def _hide_system_taskbar(self):
        print("Đang tắt thanh taskbar hệ thống (pkill panel)...")
        try:
            subprocess.run(['pkill', 'panel'], check=False)
        except Exception as e:
            print(f"Lỗi khi tắt taskbar: {e}")

    def _show_system_taskbar(self):
        print("Đang khởi động lại thanh taskbar hệ thống (lxpanel)...")
        try:
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
        # === SỬA LỖI KẾT NỐI ===
        # Truy cập các widget thông qua self.main_view
        if not hasattr(self, 'main_view'): return # Chưa khởi tạo
        
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
        """Nút "THANH TOÁN" được nhấn."""
        if not self.logic.get_selected_items():
            self.status_message_var.set("⚠️ Chưa có sản phẩm nào để thanh toán!")
            self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        self._show_confirmation_screen()

    def on_clear_cart_handler(self):
        """Nút "RESET" giỏ hàng."""
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
        """Cập nhật lời chào với tên khách hàng"""
        if self.customer_name:
            self.welcome_message_var.set(f"Xin chào {self.customer_name}!")
        else:
            self.welcome_message_var.set("Chào mừng quý khách!")

    # ==================================================================
    # XỬ LÝ GIAO DỊCH VÀ ĐÓNG ỨNG DỤNG
    # ==================================================================

    def _finalize_and_sync_transaction(self):
        """
        Hàm cốt lõi: Được gọi bởi ThankYouScreen để lưu giao dịch và đồng bộ.
        Đã sửa: Tính toán và gửi điểm mới nhất lên Server.
        """
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

        # 1. LƯU GIAO DỊCH VÀO DB LOCAL
        order_code = db_manager.save_transaction(
            total_amount, customer_name, items_detail_str, items_sold_list_for_local_db
        )
        if not order_code:
            print("UI ERROR: Không thể lưu giao dịch vào DB local.")
            return
        print(f"UI: Giao dịch {order_code} đã được lưu vào DB local.")

        final_new_points = 0
        if user_id:
            # --- FIX: TÍNH SỐ TIỀN THỰC TRẢ ĐỂ TÍNH ĐIỂM ---
            # Giá trị 1 điểm = 100 VNĐ (theo logic file confirmation)
            discount_value = self.points_used_in_transaction * 100 
            
            # Số tiền dùng để tính điểm thưởng = Giá gốc - Tiền được giảm
            amount_eligible_for_reward = max(0, total_amount - discount_value)

            print(f"DEBUG: Giá gốc: {total_amount}, Giảm: {discount_value}, Tính điểm trên: {amount_eligible_for_reward}")

            # Truyền amount_eligible_for_reward vào thay vì total_amount
            db_manager.update_customer_points(user_id, self.points_used_in_transaction, amount_eligible_for_reward)
            
            # Lấy lại thông tin user từ DB Local để có số điểm chính xác nhất
            updated_user_data = db_manager.get_customer_by_id(user_id)
            if updated_user_data:
                final_new_points = updated_user_data['points']
                self.customer_info['points'] = final_new_points 
            
            print(f"UI: Đã cập nhật điểm Local. Điểm mới: {final_new_points}")

        # 3. ĐỒNG BỘ LÊN SERVER (NỀN) - GỬI KÈM ĐIỂM MỚI
        def sync_transaction_task():
            print(f"SYNC: Bắt đầu đồng bộ đơn hàng {order_code} lên server...")
            final_api_items = [{'product_id': pid, 'quantity': count} for pid, count in product_counts.items()]
            
            # Chuẩn bị thông tin khách hàng gửi lên API
            customer_info_for_api = None
            if self.customer_info and user_id:
                customer_info_for_api = {
                    "user_id": user_id,
                    "name": self.customer_name,
                    "new_total_points": final_new_points  # <--- QUAN TRỌNG: Server cần field này để update
                }

            success = self.api_manager.report_transaction(
                total_amount, final_api_items, customer_info_for_api
            )
            
            if success:
                print(f"SYNC: Đồng bộ đơn hàng {order_code} và cập nhật điểm lên server THÀNH CÔNG.")
                db_manager.mark_transaction_as_synced(order_code)
            else:
                print(f"SYNC: Đồng bộ đơn hàng {order_code} THẤT BẠI. Sẽ thử lại sau.")
                
        threading.Thread(target=sync_transaction_task, daemon=True).start()

        # 4. ĐIỀU KHIỂN LED
        try:
            from core.drivers.PCF8574T import show_payment_leds
            purchased_products_list = list(items_in_cart)
            show_payment_leds(purchased_products_list)
        except Exception as e:
            print(f"I2C ERROR: {e}")
            
        # 5. ĐIỀU KHIỂN MÁY CƠ KHÍ
        try:
            from core.drivers.VendingMotors import dispense_products
            dispense_products(items_in_cart)
        except ImportError:
            pass
        except Exception as e:
            print(f"MOTOR ERROR: {e}")
            
    def on_app_close(self, is_welcome_close=False):
        if self.is_closing:
            return
        
        print("UI: Bắt đầu quy trình đóng ứng dụng an toàn...")
        self.is_closing = True

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