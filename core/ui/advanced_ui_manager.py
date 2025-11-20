# SHOPPING_KEYPAD_APP/core/ui/advanced_ui_manager.py
import tkinter as tk
from tkinter import PhotoImage
from PIL import Image, ImageTk
from tkinter import messagebox
import os
import itertools
import sys
import requests
import webbrowser
import re 
import datetime
import customtkinter as ctk
import subprocess 
import signal 
import time
import threading
import cv2  # Thêm OpenCV để dùng camera
import json # Đảm bảo đã import json
from collections import Counter # Import Counter để tối ưu code
from core.camera.serial_camera_handler import SerialCameraHandler
try:
    # Import tùy chọn mô hình nhận diện nâng cao
    from core.Camera_AI.model import ModelModule
except Exception:
    ModelModule = None
import numpy as np
import pickle
from core.features.shopping_logic import ShoppingLogic
from core.features.face_recognition_handler import FaceRecognitionHandler
from core.database.local_database_manager import db_manager

# Lấy các cấu hình từ config.py nếu muốn, ví dụ: TEMP_MESSAGE_DURATION
from config import TEMP_MESSAGE_DURATION, IMAGE_BASE_PATH, PRODUCT_IMAGES_CONFIG, AD_IMAGES_CONFIG

class AdvancedUIManager:
    def _build_and_save_embeddings_for_user(self, user_id, images_dir):
        """
        Tạo embeddings cho user và lưu vào database .pkl thông qua FaceRecognitionHandler.
        """
        return self.recognition_handler.add_new_user_to_db(user_id, images_dir)
    # === Cấu hình hình ảnh quảng cáo và sản phẩm ===
    # Dữ liệu được lấy từ config.py
    # --- Thêm cấu hình chất lượng camera ---
    CAPTURE_WIDTH = 1280  # Có thể nâng lên 1920 nếu camera hỗ trợ
    CAPTURE_HEIGHT = 720
    TARGET_FPS = 30
    BLUR_THRESHOLD = 60.0  # Ngưỡng độ nét tối thiểu (variance of Laplacian)
    BRIGHTNESS_MIN = 40    # Ngưỡng sáng tối thiểu (0-255)
    BRIGHTNESS_MAX = 210   # Ngưỡng sáng tối đa

    def __init__(self, root, shopping_logic_instance, api_manager_instance):
        self.root = root
        self.logic = shopping_logic_instance  # Tham chiếu đến shopping_logic
        self.api_manager = api_manager_instance  # Tham chiếu đến api_manager
        print("UI_INIT: Khởi tạo SerialCameraHandler...")
        self.camera_handler = SerialCameraHandler()
        self.camera_handler.start(cv2_module=cv2) # Truyền module cv2 vào
        self.recognition_handler = FaceRecognitionHandler(camera_handler=self.camera_handler)
        # ... (giữ nguyên code trong __init__) ...
        self.root.withdraw()
        self.root.title("Máy bán hàng tự động")
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        try:
            self.root.attributes('-fullscreen', True)
        except tk.TclError:
            if screen_width >= 1920:
                self.root.geometry("1920x1080")
            else:
                self.root.geometry(f"{screen_width}x{screen_height}")
        self._register_capture_running = False
        self._captured_images_dir = None
        self._captured_images_saved = 0
        self._captured_images_target = 20 # Giảm xuống vì ảnh từ ESP32 đã chuẩn
        self.selected_product = None
        self.selected_quantity = 1
        self.quantity_var = tk.StringVar(value="1")
        self.status_message_var = tk.StringVar(value="Chọn sản phẩm để mua hàng")
        self.ad_thumb_label = None
        self.selected_items_display = None
        self.thumb_imgs_cycle = None
        self.highlighted_frame = None
        self.selected_button = None
        self.welcome_window = None
        self.thank_you_window = None
        self.confirmation_window = None
        self.customer_info = None
        self.customer_name = ""
        self.welcome_message_var = tk.StringVar(value="Chào mừng quý khách!")
        self.points_used_in_transaction = 0 
        self.cached_ad_images = []
        self.cached_thumb_ad_images = []
        self.cached_product_images = {}
        self.thumb_imgs_cycle = None
        self.ad_imgs_cycle = None
        self.keyboard_process = None 
        self.keyboard_launched = False
        self.hide_keyboard_timer = None # Để lưu ID của lịch trình ẩn bàn phím
        self.is_closing = False 
        self.recognition_complete = False # Cờ báo hiệu luồng nhận diện đã xong
        self.min_loading_time_passed = False # Cờ báo hiệu 5 giây đã trôi qua
        self.loading_window = None
        self.face_capture_window = None # Thêm thuộc tính này
        self.feedback_label = None # Thêm thuộc tính này
        self.after_ids = []
        # Thuộc tính phục vụ quy trình chụp khuôn mặt khi đăng ký
        self.register_cap = None
        self._register_capture_running = False
        self._register_frames_captured = 0
        self._register_max_frames = 40  # Số frame đọc tối đa trước khi tự kết thúc
        # Lưu nhiều ảnh khuôn mặt
        self._captured_images_dir = None
        self._captured_images_saved = 0
        # self._captured_images_target đã được khai báo ở trên, không cần lặp lại ở đây
        # Bật/tắt tạo embedding ngay sau đăng ký (mặc định tắt theo yêu cầu)
        self.enable_post_register_embedding = True

        print("UI_INIT: Bắt đầu kiểm tra và khởi tạo cache nhận diện...")
        self._preload_all_images()
        self._setup_main_ui_elements()
        self.update_welcome_message()
        self._update_auth_frame_visibility()	
        self.show_welcome_screen()
        self._hide_system_taskbar()
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        # Khởi tạo mô hình nhận diện nâng cao (tùy chọn, lazy)
        self._face_model_module = None
        self.recognition_handler.reload_cache()
    def _return_to_register_after_error(self, register_window):
        """
        Hiện lại form đăng ký sau lỗi để người dùng nhập lại.
        """
        try:
            if self.face_capture_window and self.face_capture_window.winfo_exists():
                self.face_capture_window.destroy()
        except Exception:
            pass
        try:
            if register_window and register_window.winfo_exists():
                register_window.deiconify()
                register_window.lift()
                register_window.focus_force()
        except Exception:
            pass
   
    def show_preview_5_images_ui(self):
        """
        Hiển thị 5 ảnh vừa chụp ra UI để kiểm tra trực quan.
        """
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

        for idx, img_path in enumerate(image_files):
            try:
                img = Image.open(img_path)
                img = img.resize((220, 220), Image.Resampling.LANCZOS)
                imgtk = ImageTk.PhotoImage(img)
                lbl = tk.Label(frame, image=imgtk)
                lbl.image = imgtk
                lbl.grid(row=0, column=idx, padx=10, pady=10)
                tk.Label(frame, text=f"Ảnh {idx+1}").grid(row=1, column=idx)
            except Exception as e:
                tk.Label(frame, text=f"Lỗi ảnh {idx+1}").grid(row=1, column=idx)
                print(f"[PREVIEW_UI] Lỗi mở ảnh {img_path}: {e}")
    def capture_and_preview_5_images(self):
        """
        Chụp và lưu đúng 5 ảnh khác nhau từ camera vào thư mục tạm, trả về danh sách đường dẫn.
        """
        import os, cv2, numpy as np
        tmp_dir = os.path.join('core', 'Camera_AI', 'database', 'tmp', 'preview_5_images')
        os.makedirs(tmp_dir, exist_ok=True)
        # Xóa ảnh cũ nếu có
        for f in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, f))
            except Exception:
                pass

        captured = 0
        last_frame = None
        frame_diff_threshold = 1200
        image_paths = []

        print(f"[PREVIEW] Bắt đầu chụp 5 ảnh vào {tmp_dir}")
        while captured < 5:
            frame_bgr = self.camera_handler.get_frame()
            if frame_bgr is None:
                continue
            if last_frame is None or np.sum(np.abs(frame_bgr.astype(np.int16) - last_frame.astype(np.int16))) > frame_diff_threshold:
                img_path = os.path.join(tmp_dir, f"preview_{captured+1}.jpg")
                cv2.imwrite(img_path, frame_bgr)
                image_paths.append(img_path)
                last_frame = frame_bgr.copy()
                captured += 1
                print(f"[PREVIEW] Đã lưu ảnh: {img_path}")
        print(f"[PREVIEW] Hoàn tất, đã lưu 5 ảnh: {image_paths}")
        return image_paths
    def _on_recognition_finished(self, recognized_user_id):
        """
        Callback khi luồng nhận diện hoàn tất.
        Hàm này giờ sẽ là hàm duy nhất chịu trách nhiệm đóng màn hình loading.
        """
        # Đảm bảo hàm này chạy trên luồng UI chính
        if not self.root.winfo_exists(): return

        print(f"UI-MAIN: Nhận diện xong, output user_id: {recognized_user_id}")
        
        if recognized_user_id:
            # Đóng cửa sổ loading và chuyển sang màn hình mua hàng
            if self.loading_window and self.loading_window.winfo_exists():
                self.loading_window.destroy()
                self.loading_window = None
            customer_data = db_manager.get_customer_by_id(recognized_user_id)
            if customer_data:
                print(f"UI-MAIN: Lấy thông tin từ DB cục bộ thành công: {customer_data['name']}")
                self.logic.set_customer(customer_data)
                self.customer_info = self.logic.get_customer()
                self.customer_name = self.customer_info.get('name', '') if self.customer_info else ""
                self.update_welcome_message()
                self._update_auth_frame_visibility()
        else:
            # Nếu không nhận diện được thì giữ lại màn loading và thông báo thử lại
            if self.loading_window and self.loading_window.winfo_exists():
                self.recognition_status_var.set("Không nhận diện được khuôn mặt, vui lòng thử lại!")
                # Hiển thị màn hình chính
                self.update_welcome_message()
                self.root.deiconify()
                return
        # Nếu nhận diện thất bại hoặc không tìm thấy user, quay về màn hình chính ở trạng thái chưa đăng nhập
        print("UI-MAIN: Nhận diện không thành công hoặc người dùng hủy, vào màn hình chính.")
        self.root.deiconify()
        self.update_welcome_message()
    def _open_browser_kiosk_mode(self, url):
        """
        Mở trình duyệt Chromium ở chế độ kiosk, toàn màn hình và
        với các cờ để tối ưu hóa và tránh các thông báo lỗi.
        """
        print(f"UI: Đang mở trình duyệt ở chế độ kiosk với URL: {url}")
        try:
            # Danh sách các lệnh và đối số
            command = [
                'chromium-browser',
                '--kiosk',             # Chế độ toàn màn hình kiosk
                '--no-first-run',      # Bỏ qua màn hình chào mừng lần đầu
                '--disable-infobars',  # Ẩn thanh thông báo "Chrome is being controlled..."
                '--disable-session-crashed-bubble', # Tắt thông báo "didn't shut down correctly"
                '--incognito',         # Chế độ ẩn danh để không lưu cache, cookie
                '--disable-gpu',       # <<< QUAN TRỌNG: Thử tắt GPU để tránh lỗi gbm_wrapper.cc
                url                    # URL để mở
            ]
        
            # Chạy trình duyệt trong một tiến trình nền riêng biệt
            subprocess.Popen(command)
            print("UI: Đã gửi lệnh mở trình duyệt.")

        except FileNotFoundError:
            print("LỖI: Lệnh 'chromium-browser' không tìm thấy. Sử dụng webbrowser.open() thay thế.")
            # Phương án dự phòng nếu chromium-browser không có sẵn
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            print(f"Lỗi không xác định khi mở trình duyệt: {e}")
    def _hide_system_taskbar(self):
        """Dùng pkill để tắt (kill) tiến trình của taskbar."""
        print("Đang tắt thanh taskbar hệ thống (pkill panel)...")
        try:
            # Lệnh pkill sẽ tìm và dừng tất cả các tiến trình có tên 'panel'.
            # check=False để chương trình không báo lỗi và dừng lại nếu taskbar đã được tắt từ trước.
            subprocess.run(['pkill', 'panel'], check=False)
            print("Đã gửi lệnh tắt taskbar.")
        except FileNotFoundError:
            print("Cảnh báo: Lệnh 'pkill' không tồn tại. Hãy chắc chắn rằng pkill đã được cài đặt (thường có sẵn trên Linux).")
        except Exception as e:
            print(f"Lỗi khi tắt taskbar: {e}")

    def _show_system_taskbar(self):
        """Dùng lxpanel để khởi động lại taskbar."""
        print("Đang khởi động lại thanh taskbar hệ thống (lxpanel)...")
        try:
            # Dùng subprocess.Popen để chạy lệnh trong nền (tương tự dấu '&' trong terminal).
            # Nếu dùng subprocess.run, chương trình của bạn sẽ bị treo và đợi cho đến khi taskbar bị tắt.
            subprocess.Popen(['lxpanel', '--profile', 'LXDE-pi'])
            print("Đã gửi lệnh bật lại taskbar.")
        except FileNotFoundError:
            print("Cảnh báo: Lệnh 'lxpanel' không tồn tại. Đây có phải là môi trường LXDE/Raspberry Pi OS không?")
        except Exception as e:
            print(f"Lỗi khi bật lại taskbar: {e}")

    # --- Đặt các hàm này vào trong Class của bạn ---

    def _show_keyboard(self):
        """
        Hiện bàn phím theo mô hình "Launch Once, Show Many".
        - Chỉ khởi động onboard ở lần gọi đầu tiên.
        - Các lần sau chỉ gửi lệnh Show.
        """
        print("Yêu cầu HIỆN bàn phím...")

        # --- CHỈ KHỞI ĐỘNG ONBOARD NẾU CHƯA BAO GIỜ KHỞI ĐỘNG TRƯỚC ĐÓ ---
        if not self.keyboard_launched:
            print("Lần đầu gọi: Đang khởi động tiến trình 'onboard'...")
            try:
                # Chạy onboard trong nền
                subprocess.Popen(['onboard'])
                self.keyboard_launched = True # Đặt cờ ngay để lần sau không chạy lại
            except FileNotFoundError:
                print("LỖI: Lệnh 'onboard' không tìm thấy.")
                return

            # --- VÒNG LẶP "CHỜ ĐỢI THÔNG MINH" THAY CHO time.sleep() ---
            # Chờ tối đa 2 giây để dịch vụ D-Bus của onboard sẵn sàng
            print("Đang chờ dịch vụ D-Bus của 'onboard' sẵn sàng...")
            for _ in range(20): # Lặp 20 lần, mỗi lần 0.1 giây
                # Gửi một lệnh "Ping" tới D-Bus của onboard
                result = subprocess.run(
                    ['dbus-send', '--print-reply', '--dest=org.onboard.Onboard',
                     '/org/onboard/Onboard/Keyboard', 'org.freedesktop.DBus.Peer.Ping'],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    print("Dịch vụ D-Bus đã sẵn sàng!")
                    break # Thoát khỏi vòng lặp khi đã sẵn sàng
                time.sleep(0.1)
            else:
                # Nếu vòng lặp chạy hết mà không thành công
                print("Cảnh báo: Hết thời gian chờ, D-Bus của 'onboard' không phản hồi.")
                return

        # --- LUÔN GỬI LỆNH "SHOW" ---
        # Dù là lần đầu hay các lần sau, cuối cùng đều gửi lệnh Show
        try:
            print("Gửi lệnh 'Show' qua D-Bus...")
            subprocess.run(
                ['dbus-send', '--type=method_call', '--dest=org.onboard.Onboard',
                 '/org/onboard/Onboard/Keyboard', 'org.onboard.Onboard.Keyboard.Show'],
                check=True, capture_output=True, timeout=1
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            print("Cảnh báo: Không thể gửi lệnh 'Show' qua D-Bus.")
    def _hide_keyboard(self):
        """
        Ẩn bàn phím. Luôn gửi lệnh Hide qua D-Bus.
        """
        print("Yêu cầu ẨN bàn phím...")
        try:
            print("Gửi lệnh 'Hide' qua D-Bus...")
            subprocess.run(
                ['dbus-send', '--type=method_call', '--dest=org.onboard.Onboard',
                 '/org/onboard/Onboard/Keyboard', 'org.onboard.Onboard.Keyboard.Hide'],
                check=True, capture_output=True, timeout=2
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            # Lỗi này khá phổ biến nếu onboard chưa sẵn sàng, nhưng không sao.
            print("Cảnh báo: Không thể gửi lệnh 'Hide' qua D-Bus. Có thể onboard chưa chạy.")

    def _cleanup_keyboard(self):
        """
        Dọn dẹp cuối cùng khi ứng dụng thoát: Dùng pkill để tắt hẳn onboard.
        """
        print("Dọn dẹp cuối cùng: Tắt tất cả tiến trình 'onboard'...")
        try:
            # Dùng pkill để đảm bảo tất cả các instance của onboard đều bị tắt.
            subprocess.run(['pkill', 'onboard'], check=False)
        except FileNotFoundError:
            print("Cảnh báo: Lệnh 'pkill' không tìm thấy.")

    # --- CÁC HÀM XỬ LÝ SỰ KIỆN ---

    def _handle_focus_in(self, event):
        """Khi focus vào ô nhập liệu, gọi hàm show."""
        if self.hide_keyboard_timer:
            self.root.after_cancel(self.hide_keyboard_timer)
            self.hide_keyboard_timer = None

        the_entry = event.widget
        self._show_keyboard()
        self.root.after(10, lambda: the_entry.focus_force())
    
    def _handle_background_click(self, event):
        """Khi nhấn ra ngoài, bỏ focus và gọi hàm hide."""
        # Bỏ focus
        try:
            event.widget.winfo_toplevel().focus_set()
        except Exception:
            self.root.focus_set()
        
        # Gọi hàm ẩn
        self._hide_keyboard()

    def _on_enter_key(self, current_widget, all_widgets):
        """Xử lý phím Enter."""
        try:
            current_index = all_widgets.index(current_widget)
            if current_index == len(all_widgets) - 1:
                # Ô cuối, ẩn bàn phím
                self._hide_keyboard()
            else:
                # Chuyển ô tiếp theo
                all_widgets[current_index + 1].focus_set()
        except ValueError:
            pass
             

    ## <<< CẢI TIẾN: Hàm tải và xử lý tất cả ảnh khi khởi động
    def _preload_all_images(self):
        # ... (giữ nguyên code của hàm này) ...
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

        
    ctk.set_appearance_mode("light") 
    ctk.set_default_color_theme("blue")
    # Hàm này sẽ hiển thị màn hình chụp khuôn mặt và bắt đầu quá trình mô phỏng.
    def show_face_capture_screen(self, name, phone, dob, password, original_register_window):
        """
        Hiển thị màn hình chụp khuôn mặt, lấy ảnh từ SerialCameraHandler.
        """
        try:
            original_register_window.withdraw()
        except Exception:
            pass

        self.face_capture_window = tk.Toplevel(self.root)
        self.face_capture_window.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.face_capture_window.overrideredirect(True)
        self.face_capture_window.configure(bg="black")
        self.face_capture_window.lift()
        self.face_capture_window.focus_force()

        camera_label = tk.Label(self.face_capture_window, bg="black")
        camera_label.pack(expand=True, fill="both")

        self.feedback_label = ctk.CTkLabel(
            self.face_capture_window, text="Nhìn thẳng vào camera", font=("Arial", 30, "bold"),
            text_color="white", fg_color="black"
        )
        self.feedback_label.place(relx=0.5, rely=0.08, anchor="center")

        # Tạo thư mục tạm để lưu ảnh
        try:
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_phone = ''.join(ch for ch in phone if ch.isalnum()) or 'unknown'
            base_dir = os.path.join('core', 'Camera_AI', 'database', 'tmp')
            os.makedirs(base_dir, exist_ok=True)
            self._captured_images_dir = os.path.join(base_dir, f'reg_{ts}_{safe_phone}')
            os.makedirs(self._captured_images_dir, exist_ok=True)
            print(f"[REGISTER_CAM] Thư mục lưu ảnh tạm: {self._captured_images_dir}")
        except Exception as e:
            self.feedback_label.configure(text=f"Lỗi tạo thư mục: {e}", text_color="red")
            self.root.after(3000, lambda: self._abort_face_capture(original_register_window))
            return


        self._register_capture_running = True
        self._captured_images_saved = 0
        self._last_saved_frame = None
        self._frame_diff_threshold = 1200  # Ngưỡng khác biệt, có thể chỉnh lại cho phù hợp

        def is_frame_different(frame1, frame2):
            if frame1 is None or frame2 is None:
                return True
            # So sánh trực tiếp bằng numpy, tính tổng khác biệt tuyệt đối
            diff = np.sum(np.abs(frame1.astype(np.int16) - frame2.astype(np.int16)))
            return diff > self._frame_diff_threshold

        def capture_loop():
            if not self._register_capture_running or not self.face_capture_window.winfo_exists():
                return

            frame_bgr = self.camera_handler.get_frame()

            if frame_bgr is not None:
                # Hiển thị ảnh lên UI
                frame_display = cv2.resize(frame_bgr, (640, 480)) # Phóng to để dễ nhìn
                frame_rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)
                camera_label.imgtk = imgtk
                camera_label.configure(image=imgtk)

                # Lưu ảnh gốc (112x112) nếu chưa đủ và khác biệt đủ lớn
                if self._captured_images_saved < self._captured_images_target:
                    if is_frame_different(frame_bgr, self._last_saved_frame):
                        img_path = os.path.join(self._captured_images_dir, f"{self._captured_images_saved:03d}.jpg")
                        cv2.imwrite(img_path, frame_bgr)
                        self._captured_images_saved += 1
                        self._last_saved_frame = frame_bgr.copy()
                        self.feedback_label.configure(text=f"Đang chụp... {self._captured_images_saved}/{self._captured_images_target}")

                # Điều kiện kết thúc
                if self._captured_images_saved >= self._captured_images_target:
                    self._register_capture_running = False
                    self._finish_capture_and_register(name, phone, dob, password, original_register_window)
                    return

            # Lặp lại sau khoảng 33ms (~30 FPS)
            self.face_capture_window.after(33, capture_loop)

        capture_loop() # Bắt đầu vòng lặp

        def on_cancel(event=None):
            self._abort_face_capture(original_register_window)
        self.face_capture_window.bind("<Escape>", on_cancel)

    def _abort_face_capture(self, original_register_window):
        """Hủy quy trình chụp và quay lại form đăng ký."""
        self._register_capture_running = False
        if self.face_capture_window and self.face_capture_window.winfo_exists():
            self.face_capture_window.destroy()
        try:
            if original_register_window and original_register_window.winfo_exists():
                original_register_window.deiconify()
                original_register_window.lift()
        except Exception:
            pass
        # Dọn dẹp thư mục tạm nếu có
        if self._captured_images_dir and os.path.exists(self._captured_images_dir):
            import shutil
            shutil.rmtree(self._captured_images_dir, ignore_errors=True)

    def _finish_capture_and_register(self, name, phone, dob, password, original_register_window):
        """
        Bắt đầu quá trình xử lý nền sau khi chụp đủ ảnh.
        """
        print("[REGISTER] Chụp ảnh hoàn tất. Bắt đầu xử lý nền...")
        if self.feedback_label and self.feedback_label.winfo_exists():
            self.feedback_label.configure(text="Đang xử lý dữ liệu, vui lòng chờ...", text_color="yellow")

        threading.Thread(
            target=self._background_registration_and_embedding, 
            args=(name, phone, dob, password, original_register_window), 
            daemon=True
        ).start()
        
    # === BƯỚC 4: SỬA LẠI `_background_registration_and_embedding` ===
    def _background_registration_and_embedding(self, name, phone, dob, password, register_window):
        """
        (CHẠY TRÊN LUỒNG NỀN) Đăng ký user và tạo embeddings.
        """
        registration_data = None
        error_message = None

        try:
            # 1. Đăng ký vào DB local
            print("[REGISTER_BG] Bước 1: Đăng ký vào DB local...")
            result = db_manager.register_customer(name, phone, dob, password, face_encoding=None)
            if "error" in result:
                raise Exception("Số điện thoại này đã được đăng ký." if result["error"] == "duplicate_phone" else "Lỗi cơ sở dữ liệu.")
            
            registration_data = result
            local_user_id = registration_data['code']
            print(f"[REGISTER_BG] Đăng ký DB local thành công, local_id: {local_user_id}")

            # 2. Tạo embeddings và cập nhật database
            print(f"[REGISTER_BG] Bước 2: Bắt đầu tạo embeddings cho {local_user_id}...")
            # Sử dụng hàm mới trong FaceRecognitionHandler
            success = self.recognition_handler.add_new_user_to_db(local_user_id, self._captured_images_dir)
            if not success:
                # Nếu tạo embedding thất bại, cần rollback (xóa user khỏi db)
                db_manager.delete_customer(local_user_id) # Cần thêm hàm này vào db_manager
                raise Exception("Không thể tạo dữ liệu khuôn mặt. Vui lòng thử lại.")
            
            print("[REGISTER_BG] Tạo embeddings và cập nhật DB thành công.")
            
            # 3. Đồng bộ khách hàng lên server
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
            # Dọn dẹp thư mục ảnh tạm dù thành công hay thất bại
            if self._captured_images_dir and os.path.exists(self._captured_images_dir):
                import shutil
                shutil.rmtree(self._captured_images_dir, ignore_errors=True)

        # Gửi kết quả về luồng UI
        self.root.after(0, lambda: self._on_background_task_complete(registration_data, error_message, register_window))
    
    # ... (Các hàm khác như _on_background_task_complete, show_register_screen, ... giữ nguyên) ...

    # === BƯỚC 5: CẬP NHẬT HÀM ĐÓNG ỨNG DỤNG ===
    def on_app_close(self, is_welcome_close=False):
        if self.is_closing:
            return
        
        print("UI: Bắt đầu quy trình đóng ứng dụng an toàn...")
        self.is_closing = True

        # Dừng luồng camera serial
        print("UI: Dừng camera handler...")
        self.camera_handler.stop()

        # Dọn dẹp tài nguyên khác
        self._cleanup_keyboard()
        self.logic.close_resources()

        # ... (phần còn lại của hàm giữ nguyên) ...
        # Hủy các lịch trình 'after' đang chờ
        if self.hide_keyboard_timer:
            try:
                if self.root and self.root.winfo_exists():
                    self.root.after_cancel(self.hide_keyboard_timer)
            except tk.TclError:
                pass

        windows_to_close = [
            self.welcome_window, self.thank_you_window, self.confirmation_window,
            self.loading_window, self.face_capture_window
        ]
        for window in windows_to_close:
            try:
                if window and window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

        try:
            if self.root and self.root.winfo_exists():
                if is_welcome_close:
                    self.root.quit()
                else:
                    self.root.destroy()
        except tk.TclError:
            pass

        self._show_system_taskbar()

    def _abort_face_capture(self, original_register_window):
        """Hủy quy trình chụp và quay lại form đăng ký."""
        self._register_capture_running = False
        try:
            if self.register_cap and self.register_cap.isOpened():
                self.register_cap.release()
        except Exception:
            pass
        self.register_cap = None
        if self.face_capture_window and self.face_capture_window.winfo_exists():
            self.face_capture_window.destroy()
        try:
            if original_register_window and original_register_window.winfo_exists():
                original_register_window.deiconify()
                original_register_window.lift()
        except Exception:
            pass

    def _finish_capture_and_register(self, name, phone, dob, password, original_register_window):
        """
        Bước 1: Đóng camera và bắt đầu quá trình xử lý nền.
        """
        print("[REGISTER] Chụp ảnh hoàn tất. Bắt đầu xử lý nền...")
        self._register_capture_running = False
        try:
            if self.register_cap and self.register_cap.isOpened():
                self.register_cap.release()
        except Exception:
            pass
        self.register_cap = None
    
        # Gọi hàm tiếp theo trong chuỗi, truyền đủ các tham số
        self._on_face_capture_finished(name, phone, dob, password, original_register_window)

    def _on_face_capture_finished(self, name, phone, dob, password, register_window):
        """
        Bước 2: Cập nhật UI và khởi động luồng nền.
        """
        if self.feedback_label and self.feedback_label.winfo_exists():
            self.feedback_label.configure(text="Đang xử lý dữ liệu, vui lòng chờ...", text_color="yellow")
    
        threading.Thread(
            target=self._background_registration_and_embedding, 
            args=(name, phone, dob, password, register_window), 
            daemon=True
        ).start()

    def _return_to_register_screen(self, error_message=""):
        if self.face_capture_window and self.face_capture_window.winfo_exists():
            self.face_capture_window.destroy()
        if register_window and register_window.winfo_exists():
            register_window.deiconify() # Hiện lại
            register_window.lift() # Đưa lên trên cùng
            register_window.focus_force() # Ép focus
            # Cập nhật thông báo lỗi (nếu có)
            if error_message:
                for widget in register_window.winfo_children():
                    if isinstance(widget, ctk.CTkFrame):
                        for child in widget.winfo_children():
                            if isinstance(child, ctk.CTkLabel) and hasattr(child, 'textvariable'):
                                child.textvariable.set(error_message)
                                break
                        break
        self.root.after(100, self._show_keyboard)

    def _background_registration_and_embedding(self, name, phone, dob, password, register_window):
        """
        Bước 3 (CHẠY TRÊN LUỒNG NỀN): Thực hiện TẤT CẢ các tác vụ nặng một cách tuần tự.
        """
        registration_data = None
        error_message = None
        final_user_dir = None # Biến để lưu đường dẫn thư mục cuối cùng

        try:
            # Tác vụ 1: Đăng ký người dùng vào DB local
            print("[REGISTER_BG] Bước 1: Đăng ký vào DB local...")
            result = db_manager.register_customer(name, phone, dob, password, face_encoding=None)
            if "error" in result:
                raise Exception("Số điện thoại này đã được đăng ký." if result["error"] == "duplicate_phone" else "Lỗi cơ sở dữ liệu.")
            
            registration_data = result
            local_user_id = registration_data['code']
            print(f"[REGISTER_BG] Đăng ký DB local thành công, local_id: {local_user_id}")

            # Tác vụ 2: Đổi tên thư mục ảnh theo local_user_id
            print("[REGISTER_BG] Bước 2: Di chuyển và đổi tên thư mục ảnh...")
            base_db_dir = 'core/Camera_AI/database'
            final_user_dir = os.path.join(base_db_dir, str(local_user_id))
            if self._captured_images_dir and os.path.exists(self._captured_images_dir):
                if os.path.exists(final_user_dir):
                    import shutil
                    for f in os.listdir(self._captured_images_dir):
                        shutil.move(os.path.join(self._captured_images_dir, f), final_user_dir)
                    shutil.rmtree(self._captured_images_dir)
                else:
                    os.rename(self._captured_images_dir, final_user_dir)
                print(f"[REGISTER_BG] Đã di chuyển ảnh vào thư mục: {final_user_dir}")
            
            # Tác vụ 3: Đồng bộ khách hàng lên server (chạy song song, không ảnh hưởng đến tạo embedding)
            print(f"[REGISTER_BG] Bước 3: Bắt đầu đồng bộ user {name} lên server...")
            sync_thread = threading.Thread(
                target=db_manager.sync_customer_to_server,
                args=(name, phone, dob, password, local_user_id),
                daemon=True
            )
            sync_thread.start()

            # Tác vụ 4: Tạo embeddings (tuần tự, sau khi đã có thư mục ảnh)
            # DÙ BẠN ĐANG TẮT TÍNH NĂNG NÀY, ĐẶT NÓ Ở ĐÂY LÀ ĐÚNG LOGIC
            print("[REGISTER_BG] Bước 4: Kiểm tra và tạo embeddings (nếu được bật)...")
            if self.enable_post_register_embedding and final_user_dir and os.path.isdir(final_user_dir):
                print(f"[REGISTER_BG] Bắt đầu tạo embeddings cho {local_user_id}...")
                self._build_and_save_embeddings_for_user(local_user_id, final_user_dir)
                print(f"[REGISTER_BG] Tạo embeddings hoàn tất.")
            else:
                print("[REGISTER_BG] Tạo embeddings sau đăng ký đang bị tắt hoặc không có thư mục ảnh, bỏ qua.")
            
            print("[REGISTER_BG] Luồng nền hoàn tất thành công.")

        except Exception as e:
            error_message = str(e)
            print(f"[REGISTER_BG] LỖI trong luồng nền: {error_message}")
            if self._captured_images_dir and os.path.exists(self._captured_images_dir):
                import shutil
                shutil.rmtree(self._captured_images_dir, ignore_errors=True)

        # Tác vụ cuối: Gửi kết quả về luồng UI
        self.root.after(0, lambda: self._on_background_task_complete(registration_data, error_message, register_window))
    def _on_background_task_complete(self, registration_data, error_message, register_window):
        """
        Luồng UI: Chỉ xử lý kết quả và tự động đăng nhập.
        Việc tạo cache sẽ được thực hiện ở màn hình welcome.
        """
        if self.face_capture_window and self.face_capture_window.winfo_exists():
            self.face_capture_window.destroy()
    
        if error_message:
            self._return_to_register_after_error(register_window)
            messagebox.showerror("Đăng ký thất bại", f"Đã xảy ra lỗi: {error_message}\nVui lòng thử lại.")
        elif registration_data:
            print(f"UI: Đăng ký thành công. Tự động đăng nhập cho: {registration_data['name']}")
            
            # Tự động đăng nhập
            self.logic.set_customer(registration_data)
            self.customer_info = registration_data
            self.customer_name = registration_data.get('name', '')
            
            # Cập nhật giao diện và hiển thị màn hình chính
            self.update_welcome_message()
            self._update_auth_frame_visibility()
            if register_window and register_window.winfo_exists():
                register_window.destroy()
            self.root.deiconify()
            self.status_message_var.set(f"Đăng ký thành công! Chào mừng {self.customer_name}!")
            self.root.after(5000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
    def show_register_screen(self):
        self.root.withdraw()
        register_window = tk.Toplevel(self.root)
        screen_width = register_window.winfo_screenwidth()
        screen_height = register_window.winfo_screenheight()
        register_window.geometry(f"{screen_width}x{screen_height}+0+0")
        register_window.lift()          # Đưa cửa sổ lên lớp trên cùng
        register_window.focus_force()   # Buộc hệ thống phải tập trung (focus) vào cửa sổ này
        try:
            register_window.attributes('-type', 'dock')
        except tk.TclError:
            print("Cảnh báo: Không thể đặt thuộc tính '-type'. WM có thể không hỗ trợ.")
        register_window.configure(bg="lightgray")
        
        content_frame = tk.Frame(register_window, width=800, height=700, bg="white", relief=tk.RAISED, bd=3)
        content_frame.place(relx=0.5, rely=0.35, anchor="center")
        content_frame.pack_propagate(False)

        tk.Label(content_frame, text="Đăng ký khách hàng", font=("Arial", 32, "bold"), bg="white", fg="#014b91").pack(pady=(40, 30))

        form_frame = ctk.CTkFrame(content_frame, fg_color="white", corner_radius=100)
        form_frame.pack(pady=10, padx=60, fill="x", expand=True)

        name_label = ctk.CTkLabel(form_frame, text="Họ và tên", font=("Arial", 16), text_color="black")
        name_label.pack(anchor="w", padx=5)
        name_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="Nguyễn Văn A", placeholder_text_color="gray")
        name_entry.pack(fill="x", pady=(5, 20))

        phone_label = ctk.CTkLabel(form_frame, text="Số điện thoại", font=("Arial", 16), text_color="black")
        phone_label.pack(anchor="w", padx=5)
        phone_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="Nhập SĐT 10 số", placeholder_text_color="gray")
        phone_entry.pack(fill="x", pady=(5, 20))

        dob_label = ctk.CTkLabel(form_frame, text="Ngày sinh", font=("Arial", 16), text_color="black")
        dob_label.pack(anchor="w", padx=5)
        dob_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="dd/mm/yyyy", placeholder_text_color="gray")
        dob_entry.pack(fill="x", pady=(5, 20))

        password_label = ctk.CTkLabel(form_frame, text="Mật khẩu", font=("Arial", 16), text_color="black")
        password_label.pack(anchor="w", padx=5)
        password_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        password_frame.pack(fill="x", pady=(5, 20))

        password_entry = ctk.CTkEntry(password_frame, # <<< Đặt Entry vào trong Frame mới
                                  font=("Arial", 18), 
                                  height=48, 
                                  corner_radius=15, 
                                  border_width=2, 
                                  border_color="#014b91", 
                                  fg_color="white", 
                                  text_color="black", 
                                  placeholder_text="Mật khẩu (ít nhất 6 ký tự)", 
                                  placeholder_text_color="gray",
                                  show="*")
        password_entry.pack(side="left", fill="x", expand=True)

        def toggle_password_visibility():
            if password_entry.cget("show") == "*":
                password_entry.configure(show="")
                show_hide_button.configure(text="Ẩn")
            else:
                password_entry.configure(show="*")
                show_hide_button.configure(text="Hiện")

        show_hide_button = ctk.CTkButton(password_frame, 
                                     text="Hiện", 
                                     font=("Arial", 14),
                                     width=40, # Chiều rộng nhỏ
                                     height=30, # Chiều cao nhỏ
                                     fg_color="transparent", # Nền trong suốt
                                     text_color="#014b91", # Màu chữ
                                     hover=False, # Bỏ hiệu ứng hover để gọn gàng hơn
                                     command=toggle_password_visibility)
    
        show_hide_button.place(relx=1.0, rely=0.5, x=-10, anchor="e")


        input_widgets = [name_entry, phone_entry, dob_entry, password_entry]
        background_widgets = [register_window, content_frame, form_frame, 
                            name_label, phone_label, dob_label, password_label]
        
        # --- PHẦN BIND SỰ KIỆN HOÀN CHỈNH ---

        # 1. Gắn sự kiện FocusIn
        for widget in input_widgets:
            widget.bind("<FocusIn>", self._handle_focus_in)
        
        # 2. Gắn sự kiện nhấn Enter (giữ nguyên)
        for widget in input_widgets:
            widget.bind("<Return>", lambda e, w=widget: self._on_enter_key(w, input_widgets))
            
        # 3. Gắn sự kiện click cho các widget NỀN (giữ nguyên)
        for widget in background_widgets:
            widget.bind("<Button-1>", self._handle_background_click)
        message_var = tk.StringVar(value="")
        message_label = ctk.CTkLabel(content_frame, textvariable=message_var, font=("Arial", 16), text_color="red", fg_color="white")
        message_label.pack(pady=(0, 10))

        def save_registration():
            self._hide_keyboard() 
            name = name_entry.get().strip()
            if name == "Nguyễn Văn A" or not name: name = ""
            phone = phone_entry.get().strip()
            if phone == "Nhập SĐT 10 số" or not phone: phone = ""
            dob = dob_entry.get().strip()
            password = password_entry.get().strip()
            if dob == "dd/mm/yyyy" or not dob: dob = ""
            if not name or not phone or not dob:
                message_var.set("Vui lòng nhập đầy đủ thông tin.")
                message_label.configure(text_color="red")
                return
            if any(char.isdigit() for char in name):
                message_var.set("Tên không hợp lệ. Chỉ chứa chữ cái và khoảng trắng.")
                message_label.configure(text_color="red")
                return
            if not phone.isdigit() or not (8 <= len(phone) <= 10):
                message_var.set("Số điện thoại không hợp lệ.")
                message_label.configure(text_color="red")
                return
            if len(password) < 6:
                message_var.set("Mật khẩu phải có ít nhất 6 ký tự.")
                message_label.configure(text_color="red")
                password_entry.focus()
                return
            if not re.match(r"^\d{2}/\d{2}/\d{4}$", dob):
                message_var.set("Ngày sinh không đúng định dạng dd/mm/yyyy.")
                message_label.configure(text_color="red")
                dob_entry.configure(fg_color="#ffcccc")
                dob_entry.focus()
                return
            try:
                day, month, year = map(int, dob.split("/"))
                dob_date = datetime.datetime(year, month, day)
                today = datetime.datetime.now()
                if dob_date > today:
                    message_var.set("Năm sinh không được lớn hơn hiện tại.")
                    message_label.configure(text_color="red")
                    dob_entry.configure(fg_color="#ffcccc")
                    dob_entry.focus()
                    return
                dob_entry.configure(fg_color="white")
            except Exception:
                message_var.set("Ngày sinh không hợp lệ.")
                message_label.configure(text_color="red")
                dob_entry.configure(fg_color="#ffcccc")
                dob_entry.focus()
                return
            register_window.withdraw() # Ẩn màn hình form đi
            self.show_face_capture_screen(name, phone, dob, password, register_window)


        btn_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=(0, 40), fill="x", padx=60)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        register_btn = ctk.CTkButton(btn_frame, text="Tiếp tục", font=("Arial", 18, "bold"), fg_color="#014b91", text_color="white", height=50, corner_radius=100, command=save_registration)
        register_btn.grid(row=0, column=0, padx=(0,10), sticky="ew")

        def cancel_and_hide_keyboard():
            self._hide_keyboard()
            register_window.destroy()
            self.root.deiconify()

        register_window.protocol("WM_DELETE_WINDOW", cancel_and_hide_keyboard)
        cancel_button = ctk.CTkButton(btn_frame, text="Hủy", font=("Arial", 18, "bold"), fg_color="transparent", text_color="#014b91", border_width=2, border_color="#014b91", height=50, corner_radius=100, command=cancel_and_hide_keyboard)
        cancel_button.grid(row=0, column=1, padx=(10, 0), sticky="ew")

    def show_welcome_screen(self):
        """
        Hiển thị màn hình quảng cáo và kích hoạt kiểm tra/tạo cache embedding trong nền.
        """
        if self.welcome_window and self.welcome_window.winfo_exists():
            self.welcome_window.destroy()
        self._hide_system_taskbar()
        self.root.withdraw()
        
        self.welcome_window = tk.Toplevel(self.root)
        self.welcome_window.overrideredirect(True)
        # ... (phần còn lại của hàm để hiển thị quảng cáo giữ nguyên) ...
        self.welcome_window.geometry("1920x1080+0+0")
        try:
            self.welcome_window.attributes('-fullscreen', True)
        except tk.TclError:
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.welcome_window.geometry(f"{screen_width}x{screen_height}+0+0")
        self.welcome_window.configure(bg="white")
        self.welcome_window.title("Chào mừng")

        clickable_frame = tk.Frame(self.welcome_window, width=1920, height=1080, bg="white")
        clickable_frame.pack_propagate(False)
        clickable_frame.pack(expand=True, fill="both")

        ad_label = tk.Label(clickable_frame, bg="white")
        ad_label.pack(fill="both", expand=True)

        if not self.cached_ad_images:
            ad_label.config(text="Không có ảnh quảng cáo!", font=("Arial", 24))
        else:
            if self.ad_imgs_cycle is None:
                self.ad_imgs_cycle = itertools.cycle(self.cached_ad_images)

            def update_ad():
                if not self.welcome_window or not self.welcome_window.winfo_exists():
                    return
                try:
                    img = next(self.ad_imgs_cycle)
                    ad_label.config(image=img)
                    ad_label.image = img
                    self.welcome_window.after(4000, update_ad)
                except (StopIteration, tk.TclError):
                    pass
            update_ad()

        def on_welcome_click(event):
            if self.welcome_window and self.welcome_window.winfo_exists():
                self.welcome_window.destroy()
            self.welcome_window = None
            self.show_loading_screen()
        
        clickable_frame.bind("<Button-1>", on_welcome_click)
        ad_label.bind("<Button-1>", on_welcome_click)
        self.welcome_window.protocol("WM_DELETE_WINDOW", lambda: self.on_app_close(is_welcome_close=True))

    def show_loading_screen(self):
        """
        Hiển thị màn hình nhận diện khuôn mặt - chụp 5 ảnh khác nhau và nhận diện trên tất cả.
        """
        if self.loading_window and self.loading_window.winfo_exists():
            self.loading_window.destroy()

        self.loading_window = tk.Toplevel(self.root)
        self.loading_window.geometry(f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0")
        self.loading_window.overrideredirect(True)
        self.loading_window.configure(bg="black")
        self.loading_window.lift()
        self.loading_window.focus_force()

        camera_label = tk.Label(self.loading_window, bg="black")
        camera_label.pack(expand=True, fill="both")

        self.feedback_label = ctk.CTkLabel(
            self.loading_window, text="Nhìn thẳng vào camera để nhận diện khuôn mặt",
            font=("Arial", 30, "bold"), text_color="white", fg_color="black"
        )
        self.feedback_label.place(relx=0.5, rely=0.08, anchor="center")

        # Khởi tạo các biến để chụp ảnh
        self._recognition_capture_running = True
        self._captured_recognition_frames = []
        self._last_recognition_frame = None
        self._frame_diff_threshold = 1200
        self._recognition_target = 5  # Chụp 5 ảnh

        def is_frame_different(frame1, frame2):
            if frame1 is None or frame2 is None:
                return True
            diff = np.sum(np.abs(frame1.astype(np.int16) - frame2.astype(np.int16)))
            return diff > self._frame_diff_threshold

        def capture_recognition_loop():
            if not self._recognition_capture_running or not self.loading_window.winfo_exists():
                return

            frame_bgr = self.camera_handler.get_frame()

            if frame_bgr is not None:
                # Hiển thị ảnh lên UI
                frame_display = cv2.resize(frame_bgr, (640, 480))
                frame_rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(frame_rgb)
                imgtk = ImageTk.PhotoImage(image=img)
                camera_label.imgtk = imgtk
                camera_label.configure(image=imgtk)

                # Lưu frame vào danh sách nếu chưa đủ và khác biệt đủ lớn
                if len(self._captured_recognition_frames) < self._recognition_target:
                    if is_frame_different(frame_bgr, self._last_recognition_frame):
                        self._captured_recognition_frames.append(frame_bgr.copy())
                        self._last_recognition_frame = frame_bgr.copy()
                        self.feedback_label.configure(
                            text=f"Đang chụp... {len(self._captured_recognition_frames)}/{self._recognition_target}",
                            text_color="white"
                        )

                # Điều kiện kết thúc - đã chụp đủ ảnh
                if len(self._captured_recognition_frames) >= self._recognition_target:
                    self._recognition_capture_running = False
                    self._start_recognition_on_captured_frames()
                    return

            # Lặp lại sau khoảng 33ms (~30 FPS)
            self.loading_window.after(33, capture_recognition_loop)

        def _start_recognition_on_captured_frames():
            """Bắt đầu nhận diện trên 5 ảnh đã chụp"""
            self.feedback_label.configure(text="Đang nhận diện trên 5 ảnh đã chụp...", text_color="yellow")
            
            # Chạy nhận diện trong thread riêng để không block UI
            def recognition_task():
                recognition_results = []
                
                for idx, frame in enumerate(self._captured_recognition_frames):
                    try:
                        # Sử dụng FaceRecognitionHandler để nhận diện
                        emb = self.recognition_handler.get_embedding(frame)
                        if emb is not None and self.recognition_handler._faiss_index is not None:
                            distances, indices = self.recognition_handler._faiss_index.search(emb, 1)
                            if len(distances[0]) > 0 and distances[0][0] >= 0.5:  # Ngưỡng nhận diện
                                user_id = self.recognition_handler._labels[indices[0][0]]
                                recognition_results.append(user_id)
                            else:
                                recognition_results.append('unknown')
                        else:
                            recognition_results.append('unknown')
                    except Exception as e:
                        print(f"[RECOGNITION] Lỗi nhận diện ảnh {idx}: {e}")
                        recognition_results.append('unknown')
                
                # Tìm kết quả xuất hiện nhiều nhất
                from collections import Counter
                if recognition_results:
                    counter = Counter(recognition_results)
                    most_common = counter.most_common(1)
                    if most_common:
                        result_id, count = most_common[0]
                        print(f"[RECOGNITION] Kết quả: {result_id} xuất hiện {count}/{len(recognition_results)} lần")
                        
                        # Chỉ chấp nhận kết quả nếu không phải 'unknown' và xuất hiện ít nhất 2 lần
                        if result_id != 'unknown' and count >= 2:
                            final_result = result_id
                        else:
                            final_result = None
                    else:
                        final_result = None
                else:
                    final_result = None
                
                # Trả kết quả về UI thread
                self.loading_window.after(0, lambda: self._on_recognition_finished(final_result))
            
            threading.Thread(target=recognition_task, daemon=True).start()

        # Bắt đầu vòng lặp chụp ảnh
        capture_recognition_loop()

        # Nút hủy
        def cancel_recognition():
            self._recognition_capture_running = False
            if self.loading_window and self.loading_window.winfo_exists():
                self.loading_window.destroy()
                self.loading_window = None
            self.root.deiconify()

        cancel_button = ctk.CTkButton(
            self.loading_window,
            text="Hủy",
            font=("Arial", 18, "bold"),
            width=150,
            height=50,
            corner_radius=25,
            fg_color="transparent",
            border_color="gray50",
            border_width=2,
            text_color="gray50",
            command=cancel_recognition
        )
        cancel_button.place(relx=0.5, rely=0.9, anchor="center")

        # Bind phím Escape để hủy
        self.loading_window.bind("<Escape>", lambda e: cancel_recognition())

    
    def show_login_screen(self):
        """
        Hiển thị màn hình đăng nhập cho khách hàng với các tùy chọn:
        1. Nhận diện khuôn mặt.
        2. Đăng nhập bằng SĐT và mật khẩu.
        3. Chức năng quên mật khẩu.
        """
        self.root.withdraw()
        login_window = tk.Toplevel(self.root)
        login_window.title("Đăng nhập")
        screen_width = login_window.winfo_screenwidth()
        screen_height = login_window.winfo_screenheight()
        login_window.geometry(f"{screen_width}x{screen_height}+0+0")
        login_window.lift()
        login_window.focus_force()
        try:
            login_window.attributes('-type', 'dock')
        except tk.TclError:
            pass # Bỏ qua lỗi nếu không hỗ trợ
        login_window.configure(bg="lightgray")

        # Frame chính ở giữa màn hình
        content_frame = ctk.CTkFrame(login_window, width=800, height=700, corner_radius=15, fg_color="white", border_width=2, border_color="#014b91")
        content_frame.place(relx=0.5, rely=0.35, anchor="center")
        content_frame.pack_propagate(False)  # Giữ nguyên kích thước của frame

        def handle_login():
            """
            SỬA ĐỔI: Chỉ đăng nhập bằng DB cục bộ.
            """
            self._hide_keyboard()
            phone = phone_entry.get().strip()
            password = password_entry.get().strip()
            if not phone or not password:
                message_label.configure(text="Vui lòng nhập đầy đủ thông tin.", text_color="red")
                return
            
            login_button.configure(state="disabled", text="Đang xử lý...")
            login_window.update()
            
            user_data = db_manager.login_customer(phone, password)
            
            if user_data:
                # Đăng nhập local thành công
                print("LOGIN: Đăng nhập thành công từ CSDL local.")
                login_successful(user_data)
                def verify_with_server_task():
                    print(f"VERIFY: Đối chiếu thông tin user {user_data['name']} với server...")
                    # Cần một endpoint mới trên server: GET /api/user/<user_id>
                    # Giả sử api_manager có hàm get_customer_by_id
                    server_data = self.api_manager.get_customer_by_id(user_data['code'])
                    
                    if server_data is None:
                        # KỊCH BẢN BỊ XÓA TRÊN SERVER
                        print(f"VERIFY-WARN: User {user_data['code']} tồn tại ở local nhưng không có trên server!")
                        # Quyết định xử lý:
                        # Tùy chọn 1 (An toàn): Đánh dấu user này cần đồng bộ lại.
                        db_manager.mark_customer_as_unsynced(user_data['code'])
                        # Tùy chọn 2 (Mạnh tay): Xóa user ở local.
                        # db_manager.delete_customer(user_data['code'])
                    else:
                        # Dữ liệu khớp, có thể cập nhật lại điểm từ server nếu muốn.
                        print("VERIFY: Thông tin user trên server khớp với local.")
                        db_manager.add_or_update_customer_from_server(server_data)

                threading.Thread(target=verify_with_server_task, daemon=True).start()
                return
            
            # 2. Nếu local thất bại, thử đăng nhập qua API (chỉ khi có mạng)
            print("LOGIN: Đăng nhập local thất bại, thử đăng nhập qua API server...")
            server_user_data = self.api_manager.login_customer(phone, password)
            if server_user_data:
                print("LOGIN: Đăng nhập server thành công. Đang lưu/cập nhật dữ liệu về local...")
                # 3. Server thành công -> Lưu dữ liệu về local để lần sau đăng nhập offline được
                # Cần thêm một hàm `add_or_update_customer_from_server` trong db_manager
                db_manager.add_or_update_customer_from_server(server_user_data)
                
                # Dữ liệu từ server có thể khác, chuẩn hóa lại cho logic client
                client_user_data = {
                    "code": server_user_data.get('user_id'),
                    "name": server_user_data.get('full_name'),
                    "phone": server_user_data.get('phone_number'),
                    "points": server_user_data.get('points')
                }
                login_successful(client_user_data)
            else:
                # Cả local và server đều thất bại
                print("LOGIN: Đăng nhập thất bại trên cả local và server.")
                message_label.configure(text="Sai SĐT hoặc mật khẩu. Vui lòng thử lại.", text_color="red")
                login_button.configure(state="normal", text="Đăng Nhập")

        def login_successful(customer_data):
            """Hàm helper để xử lý logic khi đăng nhập thành công."""
            message_label.configure(text=f"Đăng nhập thành công! Chào {customer_data['name']}.", text_color="green")
            self.customer_info = customer_data
            self.customer_name = customer_data['name']
            self.logic.set_customer(customer_data)
            self.update_welcome_message()
            self._update_auth_frame_visibility()
            login_window.after(1500, lambda: [login_window.destroy(), self.root.deiconify()])

        def handle_face_login():
            """Hàm giữ chỗ cho chức năng đăng nhập bằng khuôn mặt."""
            self._hide_keyboard()
            # Sử dụng giao diện loading để nhận diện khuôn mặt
            def on_recognition_finished(user_code):
                # Đóng màn hình loading
                if self.loading_window and self.loading_window.winfo_exists():
                    self.loading_window.destroy()
                if user_code:
                    # Đăng nhập thành công
                    customer_data = db_manager.get_customer_by_code(user_code)
                    if customer_data:
                        message_label.configure(text=f"Đăng nhập thành công! Chào {customer_data['name']}", text_color="green")
                        self.customer_name = customer_data['name']
                        self.logic.set_customer(customer_data)
                        self.update_welcome_message()
                        self._update_auth_frame_visibility()
                        login_window.after(1500, lambda: [login_window.destroy(), self.root.deiconify()])
                        return
                    else:
                        message_label.configure(text="Không tìm thấy thông tin khách hàng.", text_color="red")
                # Nhận diện thất bại hoặc không tìm thấy
                message_label.configure(text="Nhận diện khuôn mặt thất bại. Vui lòng thử lại.", text_color="red")
                login_window.deiconify()
                phone_entry.focus_set()
                self._handle_focus_in(None)
            # Gọi màn hình loading và truyền callback
            self.show_loading_screen()
            # Gán lại callback cho nhận diện
            self.recognition_handler.completion_callback = on_recognition_finished


        def handle_forgot_password():
            self._hide_keyboard()
            dialog = ctk.CTkInputDialog(text="Nhập số điện thoại đã đăng ký để lấy lại mật khẩu:", title="Quên Mật Khẩu")
            phone_number = dialog.get_input()

            if phone_number:
                phone_number = phone_number.strip()
                try:
                    client = get_google_sheets_client()
                    # Bạn cần tạo hàm này trong file backend
                    customer = find_customer_by_phone(client, phone_number)
                    if customer:
                        # LƯU Ý: Đây là cách làm KHÔNG an toàn, chỉ cho mục đích demo.
                        # Trong thực tế, bạn nên gửi SMS hoặc email.
                        password = customer.get('password', 'Không tìm thấy')
                        tkinter.messagebox.showinfo("Thông tin mật khẩu", f"Mật khẩu của bạn là: {password}\n\nVui lòng đăng nhập lại.")
                    else:
                        tkinter.messagebox.showerror("Không tìm thấy", "Số điện thoại này chưa được đăng ký trong hệ thống.")
                except Exception as e:
                    tkinter.messagebox.showerror("Lỗi", f"Đã có lỗi xảy ra: {e}")


        def cancel_login():
            self._hide_keyboard()
            login_window.destroy()
            self.root.deiconify()

        login_window.protocol("WM_DELETE_WINDOW", cancel_login)

        # --- BỐ CỤC GIAO DIỆN ---

        ctk.CTkLabel(content_frame, text="Đăng Nhập", font=("Arial", 32, "bold"), text_color="#014b91").pack(pady=(40, 20))

        # Nút đăng nhập bằng khuôn mặt
        face_id_button = ctk.CTkButton(content_frame, text="Đăng nhập bằng khuôn mặt", font=("Arial", 18), height=50, command=handle_face_login, fg_color="#027cf0", hover_color="#4a4a4a")
        face_id_button.pack(pady=10, padx=40, fill="x")

        # Dải phân cách
        ctk.CTkLabel(content_frame, text="— hoặc —", font=("Arial", 16), text_color="gray").pack(pady=15)

        # Khung nhập liệu SĐT và mật khẩu
        form_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        form_frame.pack(pady=10, padx=40, fill="x")

        phone_entry = ctk.CTkEntry(form_frame, placeholder_text="Số điện thoại", font=("Arial", 16), height=48, corner_radius=10)
        phone_entry.pack(fill="x", pady=(0, 15))

        password_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        password_frame.pack(fill="x") # Đặt Frame này vào form chính

        # 2. Đặt ô nhập mật khẩu vào BÊN TRONG password_frame
        password_entry = ctk.CTkEntry(password_frame, 
                                  placeholder_text="Mật khẩu", 
                                  font=("Arial", 16), 
                                  height=48, 
                                  fg_color="white", 
                                  text_color="black", 
                                  show="*", 
                                  corner_radius=10)
        password_entry.pack(side="left", fill="x", expand=True) # Dùng pack() để nó lấp đầy frame

        # 3. Hàm xử lý logic Hiện/Ẩn
        def toggle_password_visibility():
            if password_entry.cget("show") == "*":
                password_entry.configure(show="")
                show_hide_button.configure(text="Ẩn")
            else:
                password_entry.configure(show="*")
                show_hide_button.configure(text="Hiện")

        # 4. Tạo nút Hiện/Ẩn và đặt nó vào BÊN TRONG password_frame
        show_hide_button = ctk.CTkButton(password_frame, 
                         text="Hiện", 
                         font=("Arial", 14),
                         width=40,
                         height=30,
                         fg_color="transparent",
                         text_color="#014b91",
                         hover=False,
                         command=toggle_password_visibility)
    
        # 5. Dùng .place() để đặt nút đè lên trên ô Entry, trong cùng một Frame
        show_hide_button.place(relx=1.0, rely=0.5, x=-10, anchor="e")
    
        # Gắn sự kiện cho nút Hiện/Ẩn để nó không kích hoạt ẩn bàn phím
        show_hide_button.bind("<Button-1>", lambda e: None) 
    
        # Binding phím Enter để đăng nhập
        phone_entry.bind("<Return>", lambda event: password_entry.focus())
        password_entry.bind("<Return>", lambda event: handle_login())

        # Nút "Quên mật khẩu?"
        forgot_password_button = ctk.CTkButton(content_frame, text="Quên mật khẩu?", font=("Arial", 14), text_color="#014b91", fg_color="transparent", hover=False, command=handle_forgot_password)
        forgot_password_button.pack(anchor="e", padx=40, pady=(5, 20))

        # Nút Đăng nhập chính
        login_button = ctk.CTkButton(content_frame, text="Đăng Nhập", font=("Arial", 18, "bold"), height=50, fg_color="#014b91", command=handle_login)
        login_button.pack(pady=10, padx=40, fill="x")

        # Nút Hủy
        cancel_button = ctk.CTkButton(content_frame, text="Hủy", font=("Arial", 18, "bold"), height=50, fg_color="transparent", border_width=2, border_color="#014b91", text_color="#014b91", command=cancel_login)
        cancel_button.pack(pady=(5, 30), padx=40, fill="x")

        # Label hiển thị thông báo (lỗi hoặc thành công)
        message_label = ctk.CTkLabel(content_frame, text="", font=("Arial", 14), text_color="red")
        message_label.pack(pady=(0, 10), padx=40, fill="x")

        input_widgets = [phone_entry, password_entry]
        background_widgets = [
            login_window, content_frame, form_frame, 
            face_id_button, forgot_password_button, 
            login_button, cancel_button, message_label
        ]
        # Thêm các Label vào danh sách nền
        for child in content_frame.winfo_children() + form_frame.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                background_widgets.append(child)

        # 1. Gắn sự kiện FocusIn cho các ô nhập liệu
        for widget in input_widgets:
            widget.bind("<FocusIn>", self._handle_focus_in)
    
        # 2. Gắn sự kiện nhấn Enter
        phone_entry.bind("<Return>", lambda e: password_entry.focus_set())
        password_entry.bind("<Return>", lambda e: handle_login()) # Enter ở ô cuối sẽ đăng nhập

        # 3. Gắn sự kiện click cho các widget NỀN
        for widget in background_widgets:
            widget.bind("<Button-1>", self._handle_background_click)
        
    def _setup_main_ui_elements(self):
        # Lấy kích thước màn hình để tính toán layout
        self.root.geometry("1920x1080+0+0")
        self.root.overrideredirect(True)
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        control_width = 600
        product_padx = 20
        product_pady = 20
        img_size = (150, 200)
        font_sizes = {"title": 35, "number": 14, "name": 14, "price": 14}
        grid_padx, grid_pady = 10, 25
        cart_min_height = 200

        # Frame chính cho sản phẩm (bên trái)
        self.product_display_frame = tk.Frame(self.root, bg="white")
        self.product_display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=product_padx, pady=product_pady)

        # Thêm label chào mừng khách hàng
        self.welcome_label = tk.Label(
            self.product_display_frame, 
            textvariable=self.welcome_message_var, 
            font=("Arial", 24, "bold"), 
            bg="white", 
            fg="#014b91"
        )
        self.welcome_label.grid(row=0, column=0, columnspan=4, pady=(10, 5), sticky="ew")

        tk.Label(self.product_display_frame, text="Sản phẩm", font=("Arial", font_sizes["title"], "bold"), bg="white").grid(row=1, column=0, columnspan=4, pady=(15, 0))        # Định nghĩa vị trí từng nút theo layout hình vẽ
        # Mỗi tuple: (product_index, row, column, rowspan, columnspan)
        layout = [
            (0, 2, 1, 1, 1),  
            (1, 2, 2, 1, 1),
            (2, 2, 0, 2, 1),
            (3, 3, 1, 1, 1),
            (4, 3, 2, 1, 1),
            (5, 2, 3, 2, 1),
            (6, 4, 0, 1, 1),
            (7, 4, 1, 1, 1),
            (8, 4, 2, 1, 1),
            (9, 4, 3, 1, 1),
        ]

        product_keys = list(PRODUCT_IMAGES_CONFIG.keys())
        total_products = len(product_keys)

        for idx, row, col, rowspan, colspan in layout:
            if idx >= total_products:
                continue
            product_id = product_keys[idx]
            name, img_file, price = PRODUCT_IMAGES_CONFIG[product_id]

            item_frame = tk.Button(
                self.product_display_frame,
                bd=2,
                relief=tk.RAISED,
                bg="lightyellow",
                activebackground="lightyellow",
                cursor="arrow",
                compound=tk.TOP,
                command=lambda prod=(name, price), btn=None: self.on_product_select(prod, btn)
            )
            item_frame.product_data = (name, price)

            img_path = f"{IMAGE_BASE_PATH}{img_file}"
            display_name = name if len(name) <= 12 or screen_width >= 1024 else name[:10] + "..."
            display_text = f"{display_name}\n"
            display_text += f"{price:,}đ"

            try:
                if os.path.exists(img_path):
                    img = Image.open(img_path)
                    img = img.resize(img_size, Image.Resampling.LANCZOS)
                    photo_img = ImageTk.PhotoImage(img)
                    item_frame.config(image=photo_img, text=display_text, font=("Arial", font_sizes["name"]))
                    item_frame.image = photo_img
                else:
                    item_frame.config(text=f"Ảnh lỗi\n{display_text}", font=("Arial", font_sizes["name"]))
            except Exception as e:
                print(f"Lỗi tải ảnh sản phẩm {img_path}: {e}")
                item_frame.config(text=f"Ảnh lỗi\n{display_text}", font=("Arial", font_sizes["name"]))

            item_frame.config(command=lambda prod=(product_id, name, price), btn=item_frame: self.on_product_select(prod, btn))

            item_frame.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, padx=grid_padx, pady=grid_pady, sticky="nsew")
            self.product_display_frame.grid_columnconfigure(col, weight=1)        # Cho phép co giãn các hàng
        for row in range(2, 6):  # 2 đến 5 (tối đa 5 hàng)
            self.product_display_frame.grid_rowconfigure(row, weight=1)

        # Frame cho control panel và giỏ hàng (bên phải) - Fixed width để đảm bảo hiển thị
        self.control_frame = tk.Frame(self.root, bg="lightgray", width=control_width)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=product_pady)
        self.control_frame.pack_propagate(False) # Ngăn frame co lại

        # Responsive font sizes cho control panel (chỉ cho màn hình 1920x1080)
        control_fonts = {
            "status": 16,
            "quantity_title": 18,
            "quantity_btn": 20,
            "action_btn": 16,
            "small_btn": 14,
            "cart_title": 20
        }

        # 1. Tạo một frame chính để chứa các thành phần xác thực
        self.auth_frame = ctk.CTkFrame(self.control_frame, fg_color="lightgray", corner_radius=10)
        #auth_frame.pack(pady=(10, 5), padx=10, fill=tk.X)
    
        # 2. Thêm lời nhắn/hướng dẫn
        auth_label = ctk.CTkLabel(self.auth_frame,
                              text="Trở thành thành viên để nhận nhiều ưu đãi!",
                              font=("Arial", 16, "italic"),
                              text_color="#333333",
                              wraplength=control_width - 50) # Tự động xuống dòng
        auth_label.pack(pady=(15, 10), padx=10)
    
        # 3. Tạo một frame con để chứa 2 nút bấm
        auth_button_frame = ctk.CTkFrame(self.auth_frame, fg_color="transparent")
        auth_button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        auth_button_frame.grid_columnconfigure((0, 1), weight=1) # Chia đều không gian cho 2 nút
    
        # 4. Tạo nút Đăng nhập
        login_btn = ctk.CTkButton(auth_button_frame,
                                text="Đăng Nhập",
                                font=("Arial", 16, "bold"),
                                command=self.show_login_screen, # <-- Sẽ tạo hàm này ở dưới
                                fg_color="#014b91",
                                text_color="white",
                                height=40)
        login_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # 5. Tạo nút Đăng ký
        register_btn = ctk.CTkButton(auth_button_frame,
                                text="Đăng Ký",
                                font=("Arial", 16, "bold"),
                                command=self.show_register_screen,
                                fg_color="transparent",
                                border_color="#014b91",
                                border_width=2,
                                text_color="#014b91",
                                height=40)
        register_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # Status message - Compact
        self.status_frame = tk.Frame(self.control_frame, bg="lightgray")
        self.status_frame.pack(pady=(10,5), fill=tk.X)
        
        status_label = tk.Label(self.status_frame, textvariable=self.status_message_var, 
                               font=("Arial", control_fonts["status"], "bold"), fg="blue", bg="lightgray", 
                               wraplength=control_width-20)
        status_label.pack()

        # Quantity control frame - Compact
        quantity_frame = tk.Frame(self.control_frame, bg="lightgray")
        quantity_frame.pack(pady=8)

        tk.Label(quantity_frame, text="Số lượng:", font=("Arial", control_fonts["quantity_title"], "bold"), bg="lightgray").pack(pady=(0,5))
        
        qty_controls = tk.Frame(quantity_frame, bg="lightgray")
        qty_controls.pack()
        
        btn_size = 2 if screen_width < 1024 else 3
        minus_btn = tk.Button(qty_controls, text="-", font=("Arial", control_fonts["quantity_btn"], "bold"), 
                             width=btn_size, height=1, bg="white", fg="grey", 
                             command=self.decrease_quantity)
        minus_btn.pack(side=tk.LEFT, padx=3)
        
        quantity_display = tk.Label(qty_controls, textvariable=self.quantity_var, 
                                   font=("Arial", control_fonts["quantity_btn"], "bold"), width=4, bg="white", relief=tk.RIDGE, bd=2)
        quantity_display.pack(side=tk.LEFT, padx=3)
        
        plus_btn = tk.Button(qty_controls, text="+", font=("Arial", control_fonts["quantity_btn"], "bold"), 
                            width=btn_size, height=1, bg="white", fg="grey", 
                            command=self.increase_quantity)
        plus_btn.pack(side=tk.LEFT, padx=3)

        # Action buttons frame - Compact
        action_frame = tk.Frame(self.control_frame, bg="lightgray")
        action_frame.pack(pady=8, fill=tk.X)

        btn_height = 2 if screen_width < 1024 else 3
        confirm_btn = tk.Button(action_frame, text="THÊM VÀO GIỎ", 
                               font=("Arial", control_fonts["action_btn"], "bold"), bg="green", fg="white", 
                               height=btn_height, command=self.on_confirm_add)
        confirm_btn.pack(fill=tk.X, pady=2)

        payment_btn = tk.Button(action_frame, text="THANH TOÁN", 
                               font=("Arial", control_fonts["action_btn"], "bold"), bg="red", fg="white", 
                               height=btn_height, command=self.on_ok_handler)
        payment_btn.pack(fill=tk.X, pady=2)

        # Additional control buttons - Compact
        control_buttons_frame = tk.Frame(self.control_frame, bg="lightgray")
        control_buttons_frame.pack(pady=5, fill=tk.X)

        reset_btn = tk.Button(control_buttons_frame, text="RESET", 
                             font=("Arial", control_fonts["small_btn"], "bold"), bg="blue", fg="white", 
                             command=self.on_clear_cart_handler)
        reset_btn.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        exit_btn = tk.Button(control_buttons_frame, text="THOÁT", 
                            font=("Arial", control_fonts["small_btn"], "bold"), bg="black", fg="white", 
                            command=self.on_app_close)
        exit_btn.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # Giỏ hàng - Đảm bảo có đủ không gian
        cart_frame = tk.Frame(self.control_frame, bg="lightgray")
        cart_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        
        tk.Label(cart_frame, text="Giỏ Hàng", font=("Arial", control_fonts["cart_title"], "bold"), bg="lightgray").pack(pady=(0,3))
        
        # Tính toán kích thước giỏ hàng dựa trên màn hình
        cart_text_height = max(6, min(15, int(screen_height / 80)))
        cart_text_width = max(25, int(control_width / 12))
        cart_font_size = max(8, min(12, int(screen_width / 150)))
        
        self.selected_items_display = tk.Text(cart_frame, height=cart_text_height, width=cart_text_width, 
                                            font=("Arial", cart_font_size), wrap=tk.WORD, bd=3, relief=tk.RIDGE)
        self.selected_items_display.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # Đảm bảo giỏ hàng có chiều cao tối thiểu
        cart_frame.configure(height=cart_min_height)
        
        self.update_cart_display_handler() # Hiển thị ban đầu
        self._update_auth_frame_visibility() #Gọi hàm cập nhật giao diện để quyết định ẩn/hiện auth_frame
    def _update_auth_frame_visibility(self):
        """
        Kiểm tra trạng thái đăng nhập và quyết định ẩn hoặc hiện khung xác thực.
        """
        # Giả sử self.logic.get_customer() trả về thông tin khách hàng nếu đã đăng nhập
        # và trả về None nếu chưa đăng nhập.
        customer_info = self.logic.get_customer()

        if customer_info:
             # Nếu ĐÃ có thông tin khách hàng (đã đăng nhập) -> ẨN khung đi
            self.auth_frame.pack_forget()
        else:
            # Nếu CHƯA có thông tin khách hàng -> HIỆN khung lên
            # Chúng ta pack nó vào vị trí đầu tiên, trước cả status_frame
            self.auth_frame.pack(pady=(10, 15), padx=10, fill=tk.X, before=self.status_frame)
    def _on_empty_space_click(self, event):
        """Handle clicks on empty space to deselect products"""
        # Only deselect if we actually clicked on empty space (not on a child widget)
        if event.widget in [self.product_display_frame, self.control_frame]:
            self._deselect_product()

    def on_product_select(self, product, button):
        """Product selection with persistent button pressed state"""
        # Check if clicking the same product - toggle selection
        if self.selected_product == product:
            self._deselect_product()
            return
        
        # Reset previous button state
        if self.selected_button and self.selected_button.winfo_exists():
            try:
                self.selected_button.config(relief=tk.RAISED, bg="lightyellow", activebackground="lightyellow")
            except:
                pass
        
        # Set new button to pressed state
        if button and button.winfo_exists():
            try:
                button.config(relief=tk.SUNKEN, bg="lightgreen", activebackground="lightgreen")
                self.selected_button = button
            except:
                pass
        
        self.selected_product = product
        product_id, name, price = product
        self.status_message_var.set(f"✅ ĐÃ CHỌN: {name} - {price:,}đ")
        
        # Reset quantity to 1 when selecting new product
        self.selected_quantity = 1
        self.quantity_var.set("1")

    def _deselect_product(self):
        """Deselect current product and reset button state"""
        # Reset button state
        if self.selected_button and self.selected_button.winfo_exists():
            try:
                self.selected_button.config(relief=tk.RAISED, bg="lightyellow", activebackground="lightyellow")
            except:
                pass
        
        self.selected_button = None
        self.selected_product = None
        self.selected_quantity = 1
        self.quantity_var.set("1")
        self.status_message_var.set("Chọn sản phẩm để mua hàng")

    def increase_quantity(self):
        if self.selected_quantity < 99:  # Max quantity limit
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
        
        # Add multiple items based on quantity using existing logic methods
        for _ in range(self.selected_quantity):
            # Sử dụng product_id trực tiếp
            self.logic.current_entry_buffer = product_id
            success, message, _ = self.logic.add_item_from_entry()
            if not success:
                self.status_message_var.set(f"Lỗi: {message}")
                self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
                return
        
        self.update_cart_display_handler()
        self.status_message_var.set(f"Đã thêm {self.selected_quantity} {name} vào giỏ hàng!")
        
        # Deselect product after adding to cart (reset button state)
        self._deselect_product()
        
        self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))

    def _cycle_thumb_ads(self):
        ## <<< CẢI TIẾN: Hàm mới chỉ để cycle ảnh thumbnail đã cache
        if not self.ad_thumb_label or not self.cached_thumb_ad_images:
            return

        if self.thumb_imgs_cycle is None:
            self.thumb_imgs_cycle = itertools.cycle(self.cached_thumb_ad_images)
        
        self._update_ad_thumb_display()
    def _update_ad_thumb_display(self):
        if not self.thumb_imgs_cycle or not self.root.winfo_exists() or not self.ad_thumb_label or not self.ad_thumb_label.winfo_exists():
            return
        try:
            img = next(self.thumb_imgs_cycle)
            self.ad_thumb_label.config(image=img)
            self.ad_thumb_label.image = img # Giữ tham chiếu
            self.root.after(4000, self._update_ad_thumb_display)
        except tk.TclError: # Cửa sổ có thể đã bị hủy
            pass

    def update_cart_display_handler(self, temporary_message=None):
        self.selected_items_display.config(state=tk.NORMAL)
        self.selected_items_display.delete(1.0, tk.END)

        if temporary_message:
            self.selected_items_display.insert(tk.END, temporary_message)
            self.selected_items_display.config(state=tk.DISABLED)
            # Lên lịch để xóa thông báo tạm thời và hiển thị lại giỏ hàng
            self.root.after(TEMP_MESSAGE_DURATION, lambda: self.update_cart_display_handler())
            return

        items_from_logic = self.logic.get_selected_items()
        
        if not items_from_logic:
             self.selected_items_display.tag_configure("center", justify='center')
             self.selected_items_display.insert(tk.END, "Chưa có sản phẩm nào\n", "center")
        else:
            product_count = {}
            total_price = 0
            # Phân loại và đếm sản phẩm
            for item_str in items_from_logic:
                found_product = False
                for product_id, (name, _, price) in PRODUCT_IMAGES_CONFIG.items():
                    if product_id == item_str:  # So sánh trực tiếp với product_id
                        if name in product_count:
                            product_count[name]["count"] += 1
                        else:
                            product_count[name] = {"count": 1, "price": price}
                        total_price += price
                        found_product = True
                        break
                if not found_product: # Nên có xử lý cho trường hợp này
                     product_count[f"Mã lỗi {item_str}"] = product_count.get(f"Mã lỗi {item_str}", {"count": 0, "price": 0})
                     product_count[f"Mã lỗi {item_str}"]["count"] +=1
            
            for name, data in product_count.items():
                self.selected_items_display.insert(tk.END, f"{name}: {data['count']} x {data['price']:,}đ\n")
            self.selected_items_display.insert(tk.END, "--------------------\n")
            self.selected_items_display.insert(tk.END, f"Tổng cộng: {total_price:,}đ")

        self.selected_items_display.config(state=tk.DISABLED)

    def on_ok_handler(self):
        if not self.logic.get_selected_items():
            self.status_message_var.set("⚠️ Chưa có sản phẩm nào để thanh toán!")
            self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        self.root.withdraw()
        self._show_confirmation_screen()

    def _show_confirmation_screen(self):
        if self.confirmation_window and self.confirmation_window.winfo_exists():
            self.confirmation_window.focus()
            return

        self.confirmation_window = tk.Toplevel(self.root)
        self.confirmation_window.title("Xác nhận đơn hàng")
        screen_width = self.confirmation_window.winfo_screenwidth()
        screen_height = self.confirmation_window.winfo_screenheight()
        self.confirmation_window.geometry(f"{screen_width}x{screen_height}+0+0")
        self.confirmation_window.lift()
        self.confirmation_window.focus_force()
        try:
            # Dùng 'dock' để có hành vi fullscreen ổn định trên Raspberry Pi
            self.confirmation_window.attributes('-type', 'dock') 
        except tk.TclError: 
            print("Cảnh báo: Không thể đặt thuộc tính '-type'. WM có thể không hỗ trợ.")
        self.confirmation_window.configure(bg="lightgray") # Nền màu xám
        
        # Hàm đóng cửa sổ, giờ đây cũng sẽ gọi hàm ẩn bàn phím chung
        def destroy_confirmation_and_hide_keyboard():
            self._hide_keyboard() # Gọi hàm ẩn chung
            self.confirmation_window.destroy()

        self.confirmation_window.protocol("WM_DELETE_WINDOW", destroy_confirmation_and_hide_keyboard)
        self.confirmation_window.bind("<Escape>", lambda e: destroy_confirmation_and_hide_keyboard())

        content_frame = tk.Frame(self.confirmation_window, width=1500, height=1000, bg="white", relief=tk.RAISED, bd=3)
        content_frame.place(relx=0.5, rely=0.5, anchor="center")
        content_frame.pack_propagate(False)

        items_summary = {}
        total_price = 0
        items_for_api = []
        for item_id in self.logic.get_selected_items():
            name, _, price = PRODUCT_IMAGES_CONFIG.get(item_id, ("Sản phẩm lỗi", "", 0))
            if name in items_summary:
                items_summary[name]["count"] += 1
            else:
                items_summary[name] = {"count": 1, "price": price}
            total_price += price
        for name, data in items_summary.items():
            items_for_api.append({"name": name, "quantity": data["count"], "price": data['price'] * data['count']})

        large_order_discount = 2000 if total_price > 20000 else 0
        customer_points = self.customer_info.get('points', 0) if self.customer_info else 0
        point_conversion_rate = 100

        font_regular = ctk.CTkFont(family="Arial", size=17)
        font_bold = ctk.CTkFont(family="Arial", size=18, weight="bold")
        font_title = ctk.CTkFont(family="Arial", size=38, weight="bold")
        font_total = ctk.CTkFont(family="Arial", size=24, weight="bold")
        font_helper = ctk.CTkFont(family="Arial", size=14, slant="italic")

        combo_frame = ctk.CTkFrame(content_frame, fg_color="#e9e9e9", corner_radius=10) 
        combo_frame.pack(pady=10, padx=25, fill="x", ipady=5)
        ctk.CTkLabel(combo_frame, text="✨ Ưu đãi Combo dành cho bạn ✨", font=font_bold, text_color="#005a9c").pack(pady=(5, 10))
        ctk.CTkLabel(combo_frame, text="Hiện chưa có combo nào cho bạn!", font=font_regular).pack(pady=(0, 10), padx=10)
        points_entry = None

        if customer_points > 0:
            points_input_frame = ctk.CTkFrame(content_frame, fg_color="white")
            points_input_frame.pack(pady=10, padx=25, fill="x")
            
            points_label = ctk.CTkLabel(points_input_frame, text="Dùng điểm thanh toán:", font=font_bold, fg_color="white")
            points_label.pack(side="left", padx=(0, 10))
            
            points_to_use_var = tk.StringVar(value=str(customer_points))
            points_entry = ctk.CTkEntry(points_input_frame, textvariable=points_to_use_var, width=100, font=font_regular, justify='center')
            points_entry.pack(side="left")
            
            points_available_label = ctk.CTkLabel(points_input_frame, text=f"/ {customer_points} điểm khả dụng", font=font_regular, fg_color="white")
            points_available_label.pack(side="left", padx=(5, 0))
            
            points_helper_label = ctk.CTkLabel(points_input_frame, text="", font=font_helper, text_color="#e67e22", fg_color="white")
            default_border_color = points_entry.cget("border_color")
            error_border_color = "#e74c3c"
        
        items_frame = ctk.CTkScrollableFrame(
            content_frame, label_text="Chi tiết đơn hàng", label_font=font_bold, height=250
        )
        items_frame.pack(pady=10, padx=25, fill="x")

        for name, data in items_summary.items():
            item_row = ctk.CTkFrame(items_frame, fg_color="transparent")
            item_row.pack(fill="x", padx=10, pady=4)
            ctk.CTkLabel(item_row, text=f"{data['count']}x {name}", font=font_regular).pack(side="left")
            ctk.CTkLabel(item_row, text=f"{data['count'] * data['price']:,}đ", font=font_regular).pack(side="right")

        summary_frame = ctk.CTkFrame(items_frame, fg_color="transparent")
        summary_frame.pack(fill="x", padx=10, pady=(15, 5))
        input_widgets = []
        if points_entry:
            input_widgets.append(points_entry)

        if input_widgets:
            # Gắn sự kiện FocusIn để HIỆN bàn phím (gọi đúng hàm _handle_focus_in)
            for widget in input_widgets:
                widget.bind("<FocusIn>", self._handle_focus_in) 
                
            # Gắn sự kiện nhấn Enter để ẨN bàn phím
            for widget in input_widgets:
                widget.bind("<Return>", lambda e: self._hide_keyboard())

            # Gắn MỘT sự kiện click toàn cục DUY NHẤT để ẨN bàn phím
            self.confirmation_window.bind_all("<Button-1>", self._handle_background_click)

        def create_summary_line(parent, label_text, is_total=False, is_discount=False):
            line_frame = ctk.CTkFrame(parent, fg_color="transparent")
            text_color = "#2a8a2a" if is_discount else "gray10"
            current_font = font_total if is_total else font_bold
            if is_total: text_color = "#005a9c"
            label = ctk.CTkLabel(line_frame, text=label_text, font=current_font, text_color=text_color)
            label.pack(side="left")
            value_label = ctk.CTkLabel(line_frame, text="", font=current_font, text_color=text_color)
            value_label.pack(side="right")
            return line_frame, value_label

        ctk.CTkFrame(summary_frame, height=2, fg_color="gray80").pack(fill="x", pady=(0, 5))
        sub_total_frame, sub_total_value_label = create_summary_line(summary_frame, "Tổng cộng:")
        high_value_frame, high_value_discount_label = create_summary_line(summary_frame, "Giảm giá đơn hàng lớn:", is_discount=True)
        points_frame_sum, points_discount_label = create_summary_line(summary_frame, "Giảm giá bằng điểm:", is_discount=True)
        final_separator = ctk.CTkFrame(summary_frame, height=3, fg_color="gray50")
        final_total_frame, final_total_label = create_summary_line(summary_frame, "TỔNG THANH TOÁN:", is_total=True)

        sub_total_frame.pack(fill="x", pady=2)
        final_separator.pack(fill="x", pady=5)
        final_total_frame.pack(fill="x", pady=2)

        def update_summary(event=None):
            base_price_before_points = total_price - large_order_discount
            max_discountable_amount = max(0, base_price_before_points - 2000)
            max_points_to_use_for_order = max_discountable_amount // point_conversion_rate
            points_to_display = 0
            show_helper_message = False
            helper_message = ""
            is_valid_input = True
            if customer_points > 0:
                try:
                    user_input_points = int(points_to_use_var.get())
                    points_to_display = user_input_points
                    if user_input_points > customer_points:
                        is_valid_input = False
                        points_to_display = customer_points
                        points_to_use_var.set(str(points_to_display))
                        helper_message = f"Bạn chỉ có {customer_points} điểm."
                        show_helper_message = True
                    elif user_input_points > max_points_to_use_for_order:
                        is_valid_input = False
                        points_to_display = max_points_to_use_for_order
                        points_to_use_var.set(str(points_to_display))
                        helper_message = "Bạn phải thanh toán tối thiểu 2,000đ."
                        show_helper_message = True
                except (ValueError, TypeError):
                    is_valid_input = False
                    points_to_display = 0
                if is_valid_input:
                    points_entry.configure(border_color=default_border_color)
                else:
                    points_entry.configure(border_color=error_border_color)
                if show_helper_message:
                    points_helper_label.configure(text=helper_message)
                    points_helper_label.pack(side="left", padx=(15, 0), pady=(2,0), anchor="w")
                else:
                    points_helper_label.pack_forget()
            points_discount_value = points_to_display * point_conversion_rate
            final_total = total_price - large_order_discount - points_discount_value
            sub_total_value_label.configure(text=f"{total_price:,.0f}đ")
            final_total_label.configure(text=f"{max(0, final_total):,.0f}đ")
            if large_order_discount > 0:
                high_value_discount_label.configure(text=f"-{large_order_discount:,.0f}đ")
                high_value_frame.pack(before=final_separator, fill="x", pady=2)
            else:
                high_value_frame.pack_forget()
            if points_discount_value > 0:
                points_discount_label.configure(text=f"-{points_discount_value:,.0f}đ")
                points_frame_sum.pack(before=final_separator, fill="x", pady=2)
            else:
                points_frame_sum.pack_forget()

        if customer_points > 0:
            points_entry.bind("<KeyRelease>", update_summary)
        update_summary()

        error_label = ctk.CTkLabel(content_frame, text="", font=ctk.CTkFont(size=16), text_color="red")
        error_label.pack(pady=(5,0))

        # 1. Tạo danh sách các widget có thể nhập liệu
        # Trong trường hợp này, chỉ có `points_entry` (nếu nó được tạo)
        input_widgets = []
        if points_entry:
            input_widgets.append(points_entry)

        # 2. Áp dụng logic BIND giống hệt màn hình đăng ký
        if input_widgets:
            # Gắn sự kiện FocusIn cho ô nhập liệu để HIỆN bàn phím
            for widget in input_widgets:
                # Gọi _handle_focus_in để có logic giành lại focus
                widget.bind("<FocusIn>", self._handle_focus_in) 
                
            # Gắn sự kiện nhấn Enter để ẨN bàn phím
            # Vì chỉ có 1 ô, nên Enter sẽ ẩn bàn phím luôn
            for widget in input_widgets:
                widget.bind("<Return>", lambda e: self._hide_keyboard())

            # Gắn MỘT sự kiện click toàn cục DUY NHẤT để ẨN bàn phím
            # Logic này sẽ xử lý tất cả các cú click ra ngoài
            self.confirmation_window.bind_all("<Button-1>", self._handle_background_click)

        def _process_final_payment():
            self._hide_keyboard() # <<< SỬA LỖI: Ẩn bàn phím khi xử lý
            confirm_btn.configure(state="disabled", text="Đang xử lý...")
            back_btn.configure(state="disabled")
            error_label.configure(text="")
            self.confirmation_window.update()
            base_price_before_points = total_price - large_order_discount
            max_discountable_amount = max(0, base_price_before_points - 2000)
            max_points_to_use = max_discountable_amount // point_conversion_rate
            points_to_use_for_payment = 0
            if customer_points > 0:
                try:
                    user_input_points = int(points_to_use_var.get())
                    limited_by_balance = min(user_input_points, customer_points)
                    points_to_use_for_payment = min(limited_by_balance, max_points_to_use)
                    points_to_use_for_payment = max(0, points_to_use_for_payment)
                except (ValueError, TypeError):
                    points_to_use_for_payment = 0
            self.points_used_in_transaction = points_to_use_for_payment
            points_discount = self.points_used_in_transaction * point_conversion_rate
            amount_to_pay = total_price - large_order_discount - points_discount
            amount_to_pay = max(2000, amount_to_pay) if base_price_before_points >= 2000 else base_price_before_points
            try:
                response = requests.post("http://localhost:5000/create-payment-link", json={"name": self.customer_name or "Khách hàng", "amount": amount_to_pay, "items": items_for_api}, timeout=10)
                response.raise_for_status()
                payment_link = response.json().get("checkoutUrl")
                if not payment_link: raise ValueError("Không nhận được link thanh toán.")
                self._open_browser_kiosk_mode(payment_link)
                self.confirmation_window.destroy()
                return
            except requests.exceptions.Timeout:
                error_label.configure(text="⏰ Lỗi: Server không phản hồi. Vui lòng thử lại.")
            except requests.exceptions.RequestException as e:
                error_label.configure(text=f"🔌 Lỗi kết nối hoặc API: {e}")
            except Exception as e:
                error_label.configure(text=f"❌ Lỗi không xác định: {e}")

            confirm_btn.configure(state="normal", text="Xác nhận & Thanh toán")
            back_btn.configure(state="normal")

        btn_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=25, fill="x", padx=25)
        
        # <<< CẢI TIẾN: Hàm riêng để quay lại và ẩn bàn phím >>>
        def back_and_hide_keyboard():
            self._hide_keyboard()
            self.confirmation_window.destroy()
            self.root.deiconify()

        back_btn = ctk.CTkButton(btn_frame, text="Quay Lại", font=ctk.CTkFont(size=20, weight="bold"), height=60, fg_color="#7f8c8d", hover_color="#95a5a6", command=back_and_hide_keyboard)
        back_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        confirm_btn = ctk.CTkButton(btn_frame, text="Xác nhận & Thanh toán", font=ctk.CTkFont(size=20, weight="bold"), height=60, command=_process_final_payment)
        confirm_btn.pack(side="right", expand=True, fill="x", padx=(10, 0))
    
    def on_clear_cart_handler(self):
        """Chỉ xóa các sản phẩm trong giỏ hàng, không reset thông tin khách hàng."""
        if not self.logic.get_selected_items():
            self.status_message_var.set("Giỏ hàng đã trống!")
            self.root.after(TEMP_MESSAGE_DURATION, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
            return
        message, _ = self.logic.reset_all()
        self.update_cart_display_handler()
        self._deselect_product()
        self.status_message_var.set("✅ Giỏ hàng đã được xóa!")
        self.root.after(TEMP_MESSAGE_DURATION, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))

    def on_reset_handler(self):
        message, _ = self.logic.reset_all()
        self.update_cart_display_handler()
        self._deselect_product()
        self.customer_info = None
        self.customer_name = ""
        self.update_welcome_message()
        self.points_used_in_transaction = 0 # <<< SỬA LỖI: Reset lại điểm đã dùng
        self.status_message_var.set("Đã reset! Chọn sản phẩm để mua hàng")
        self.root.after(3000, lambda: self.status_message_var.set("Chọn sản phẩm để mua hàng"))
    def _finalize_and_sync_transaction(self):
        """
        Hàm cốt lõi: Nơi duy nhất xử lý lưu giao dịch, kích hoạt đồng bộ và điều khiển LED.
        <<< ĐÃ SỬA LỖI THỨ TỰ THỰC THI CHO DRIVER LED >>>
        """
        print("UI: Bắt đầu hoàn tất và đồng bộ giao dịch...")
        items_in_cart = self.logic.get_selected_items()
        if not items_in_cart:
            print("UI WARN: Không có sản phẩm để hoàn tất giao dịch.")
            return

        # --- BƯỚC 1: CHUẨN BỊ DỮ LIỆU GỐC ---
        total_amount = self.logic.get_total_price()
        customer_name = self.customer_name or "Khách vãng lai"
        user_id = self.customer_info.get('code') if self.customer_info else None

        # --- BƯỚC 2: TỔNG HỢP DỮ LIỆU SẢN PHẨM ---
        from collections import Counter
        # Biến `product_counts` được định nghĩa ở đây
        product_counts = Counter(items_in_cart)
        
        items_detail_parts = []
        items_sold_list_for_local_db = []
        
        for product_id, quantity in product_counts.items():
            name, _, _ = PRODUCT_IMAGES_CONFIG.get(product_id, ("Sản phẩm lỗi", "", 0))
            items_detail_parts.append(f"{name} x{quantity}")
            items_sold_list_for_local_db.append({"product_name": name, "quantity": quantity})
        
        items_detail_str = ", ".join(items_detail_parts)

        # --- BƯỚC 3: LƯU GIAO DỊCH VÀO DB LOCAL ---
        order_code = db_manager.save_transaction(
            total_amount, customer_name, items_detail_str, items_sold_list_for_local_db
        )

        if not order_code:
            print("UI ERROR: Không thể lưu giao dịch vào DB local.")
            return
            
        print(f"UI: Giao dịch {order_code} đã được lưu vào DB local MỘT LẦN DUY NHẤT.")

        # --- BƯỚC 4: CẬP NHẬT ĐIỂM KHÁCH HÀNG (NẾU CÓ) ---
        if user_id:
            db_manager.update_customer_points(user_id, self.points_used_in_transaction, total_amount)
            print(f"UI: Đã cập nhật điểm cho user {user_id}.")

        # --- BƯỚC 5: ĐỒNG BỘ LÊN SERVER (TRONG LUỒNG NỀN) ---
        def sync_transaction_task():
            # ... (code của luồng này giữ nguyên, không cần thay đổi)
            print(f"SYNC: Bắt đầu đồng bộ đơn hàng {order_code} lên server...")
            final_api_items = [{'product_id': pid, 'quantity': count} for pid, count in product_counts.items()]
            customer_info_for_api = {"user_id": user_id, "name": self.customer_name} if self.customer_info else None
            success = self.api_manager.report_transaction(
                total_amount, final_api_items, customer_info_for_api
            )
            if success:
                print(f"SYNC: Đồng bộ đơn hàng {order_code} lên server THÀNH CÔNG.")
                db_manager.mark_transaction_as_synced(order_code)
            else:
                print(f"SYNC: Đồng bộ đơn hàng {order_code} THẤT BẠI. Sẽ thử lại sau.")
        threading.Thread(target=sync_transaction_task, daemon=True).start()

        # --- BƯỚC 6 (ĐÃ DI CHUYỂN): ĐIỀU KHIỂN DRIVER I2C ĐỂ HIỂN THỊ LED ---
        # Đặt ở cuối hàm để đảm bảo `product_counts` đã tồn tại
        try:
            from core.drivers.PCF8574T import show_payment_leds
            # Tạo lại danh sách product_id lặp lại theo số lượng
            purchased_products_list = []
            for product_id, quantity in product_counts.items():
                purchased_products_list.extend([product_id] * quantity)

            # Gọi hàm điều khiển LED
            show_payment_leds(purchased_products_list)
            print(f"I2C: Đã gửi tín hiệu LED cho các sản phẩm: {purchased_products_list}")
        except Exception as e:
            print(f"I2C ERROR: Không thể gửi tín hiệu cho driver LED: {e}")

    def show_thank_you_screen(self):
        # ... (giữ nguyên code hàm này)
        self._finalize_and_sync_transaction()
        if self.thank_you_window and self.thank_you_window.winfo_exists():
            self.thank_you_window.destroy()
        
        self.root.withdraw() 
        self.thank_you_window = tk.Toplevel(self.root)
        self.thank_you_window.geometry("1920x1080+0+0")
        self.thank_you_window.overrideredirect(True)
        self.thank_you_window.configure(bg="white")
        self.thank_you_window.title("Cảm ơn quý khách")
        
        if self.customer_name:
            thank_you_message = f"Cảm ơn {self.customer_name} đã mua hàng!"
        else:
            thank_you_message = "Cảm ơn quý khách đã mua hàng!"
        
        thank_label = tk.Label(self.thank_you_window, text=thank_you_message, font=("Verdana", 40, "bold"), fg="#FFFFFF", bg="black")
        thank_label.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
        thank_label.lift()
        
        def close_and_reset_after_animation():
            print("UI: Màn hình cảm ơn kết thúc. Bắt đầu reset toàn bộ hệ thống.")
        
            # 1. Phá hủy cửa sổ hiện tại
            if self.thank_you_window and self.thank_you_window.winfo_exists():
                self.thank_you_window.destroy()
            self.thank_you_window = None
        
            # 2. Reset trạng thái logic nghiệp vụ
            self.logic.reset_all() # Reset giỏ hàng
            self.logic.set_customer(None) # Reset khách hàng

            # 3. Reset trạng thái của chính UI
            self.customer_info = None
            self.customer_name = ""
            self.update_welcome_message()
            self._update_auth_frame_visibility()
            self._deselect_product() # Bỏ chọn sản phẩm
            self.update_cart_display_handler() # Cập nhật giỏ hàng rỗng
        
            # 4. Quay về màn hình chào mừng để bắt đầu chu kỳ mới
            self.show_welcome_screen()
        
        self.thank_you_window.attributes('-alpha', 1.0)
        display_duration = 2000
        self.thank_you_window.after(display_duration, close_and_reset_after_animation)
        self.thank_you_window.protocol("WM_DELETE_WINDOW", close_and_reset_after_animation)

    def update_welcome_message(self):
        """Cập nhật lời chào với tên khách hàng"""
        if self.customer_name:
            self.welcome_message_var.set(f"Xin chào {self.customer_name}!")
        else:
            self.welcome_message_var.set("Chào mừng quý khách!")

    
    
    def on_app_close(self, is_welcome_close=False):
        """
        Hàm xử lý đóng ứng dụng một cách an toàn và có trật tự,
        tránh lỗi gọi destroy nhiều lần.
        """
        # 1. BƯỚC BẢO VỆ: Nếu đã trong quá trình đóng, không làm gì thêm.
        if self.is_closing:
            print("UI: Đang trong quá trình đóng, yêu cầu mới bị bỏ qua.")
            return
        
        print("UI: Bắt đầu quy trình đóng ứng dụng an toàn...")
        self.is_closing = True # Đặt cờ ngay lập tức

        # 2. DỌN DẸP TÀI NGUYÊN & CÁC TÁC VỤ NỀU
        # Dọn dẹp các tiến trình và tài nguyên logic trước khi đụng đến giao diện.
        self._cleanup_keyboard()
        self.logic.close_resources()

        # Hủy các lịch trình 'after' đang chờ
        if self.hide_keyboard_timer:
            try:
                # Chỉ hủy nếu root còn tồn tại
                if self.root and self.root.winfo_exists():
                    self.root.after_cancel(self.hide_keyboard_timer)
            except tk.TclError:
                pass # Bỏ qua nếu root đã bị hủy

        # 3. PHÁ HỦY CÁC CỬA SỔ TOPLEVEL (CỬA SỔ CON) TRƯỚC
        # Luôn luôn dọn dẹp các cửa sổ con trước cửa sổ gốc.
        windows_to_close = [
            self.welcome_window, 
            self.thank_you_window, 
            self.confirmation_window
        ]
        for window in windows_to_close:
            try:
                if window and window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass # Bỏ qua nếu nó đã bị hủy cùng lúc

        # 4. XỬ LÝ CỬA SỔ GỐC (ROOT) CUỐI CÙNG
        # Đây là bước duy nhất chúng ta tương tác với self.root để đóng nó.
        try:
            if self.root and self.root.winfo_exists():
                # Dựa vào cờ is_welcome_close để quyết định hành động cuối cùng
                if is_welcome_close:
                    print("UI: Đóng từ màn hình Welcome, thoát hoàn toàn chương trình.")
                    self.root.quit()  # Dừng mainloop
                    # Không cần gọi destroy() vì sys.exit() sẽ kết thúc mọi thứ
                else:
                    print("UI: Đóng từ màn hình chức năng, chỉ hủy cửa sổ gốc.")
                    self.root.destroy() # Hủy cửa sổ nhưng script có thể vẫn chạy
        except tk.TclError:
            print("UI: Lỗi khi xử lý cửa sổ gốc, có thể nó đã bị hủy bởi tiến trình khác.")

        # 5. CÁC HÀNH ĐỘNG CUỐI CÙNG SAU KHI GIAO DIỆN ĐÃ ĐÓNG
        self._show_system_taskbar()

    