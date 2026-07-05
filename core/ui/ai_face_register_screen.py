# SHOPPING_KEYPAD_APP/core/ui/ai_face_register_screen.py
import tkinter as tk
import customtkinter as ctk
import cv2
import threading
from PIL import Image, ImageTk
import numpy as np
import time
import faiss 
import os 
import queue

class AIFaceRegistrationScreen(tk.Toplevel):
    def __init__(self, parent, controller, local_user_id, name, phone, email, password, original_register_window):
        super().__init__(parent)
        self.controller = controller
        self.controller.start_camera_service()

        self.local_user_id = local_user_id
        self.name = name
        self.phone = phone
        self.email = email
        self.password = password
        self.original_register_window = original_register_window
        
        self.ai_system = self.controller.camera_ai_system
        self.num_images_target = 70
        self._register_capture_running = True # Cờ để hủy

        # --- (Code UI giữ nguyên) ---
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.overrideredirect(True)
        self.configure(bg="white")
        self.lift()
        #self.focus_force()

        self.camera_label = tk.Label(self, bg="white")
        self.camera_label.pack(expand=True, fill="both")

        self.feedback_label = ctk.CTkLabel(
            self, text="Vui lòng nhìn thẳng vào camera", font=("Arial", 30, "bold"),
            text_color="#014b91", fg_color="white"
        )
        self.feedback_label.place(relx=0.5, rely=0.08, anchor="center")
        
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", width=400, height=20, progress_color="#027cf0")
        self.progress_bar.set(0)
        #self.progress_bar.place(relx=0.5, rely=0.15, anchor="center")
        self.current_progress = 0.0
        self.current_border_color = (145, 75, 1)

        self.target_progress = 0.0 # Biến đích để chạy từ từ tới
        self.current_message = ""
        self.current_error = False


        cancel_button = ctk.CTkButton(
            self, text="Hủy", font=("Arial", 18, "bold"),
            width=150, height=50, corner_radius=25,
            fg_color="transparent", border_color="#027cf0", border_width=2,
            text_color="#027cf0", command=self._abort_face_capture
        )
        cancel_button.place(relx=0.5, rely=0.9, anchor="center")

        self.bind("<Escape>", lambda e: self._abort_face_capture())
        
        # === BẮT ĐẦU 2 LUỒNG CHÍNH ===
        # 1. Luồng UI (chỉ để xem)
        self._camera_preview_loop() 
        # 2. Luồng Worker (để xử lý)
        self.registration_thread = threading.Thread(target=self._registration_task, daemon=True)
        self.registration_thread.start()

    def _camera_preview_loop(self):
        is_running = getattr(self, '_recognition_capture_running', getattr(self, '_register_capture_running', False))
            
        if not is_running or not self.winfo_exists():
            return

        # ==========================================
        # 1. LOGIC TĂNG TỪ TỪ TIẾN TRÌNH VÀ SỐ %
        # ==========================================
        target = getattr(self, 'target_progress', 0.0)
        current = getattr(self, 'current_progress', 0.0)
        
        if current < target:
            # Để đăng ký thu 70 ảnh chạy kịp, có thể cần tăng tốc độ lên một xíu
            current += 0.04 
            if current > target:
                current = target
            self.current_progress = current
            self.progress_bar.set(current)
            
        # ==========================================
        # 2. CẬP NHẬT LABEL MƯỢT MÀ THEO %
        # ==========================================
        percent = int(self.current_progress * 100)
        msg = getattr(self, 'current_message', "")
        err = getattr(self, 'current_error', False)
        
        color = "#014b91"
        if err:
            color = "red"
            self.current_border_color = (0, 0, 220)
            display_text = msg
        elif "thành công" in msg.lower():
            color = "#00aa00"
            self.current_border_color = (0, 170, 0)
            display_text = msg
            self.current_progress = 1.0 # Ép đầy thanh
            self.progress_bar.set(1.0)
            percent = 100
        elif "Lỗi" in msg or "Không tìm thấy" in msg:
            color = "#ffaa00"
            self.current_border_color = (0, 140, 255)
            display_text = msg
        else:
            # CHÈN LỜI HƯỚNG DẪN + BỘ ĐẾM % MƯỢT
            if msg == "CAPTURING":
                guidance = self._get_guidance_message(self.current_progress)
                display_text = f"{guidance} ({percent}%)"
                color = "#00aa00"
                self.current_border_color = (0, 170, 0)
            else:
                display_text = f"Đang thu thập dữ liệu... {percent}%"
                self.current_border_color = (240, 124, 2)
                
        self.feedback_label.configure(text=display_text, text_color=color)
        # ==========================================
        # 3. LẤY FRAME VÀ VẼ OVAL CAMERA
        # ==========================================

        frame_bgr = self.ai_system.get_latest_frame_for_display()

        if frame_bgr is not None:
            # Resize chuẩn
            target_w, target_h = 1280, 720
            frame_display = frame_bgr

            # 1. TỌA ĐỘ VÀ KÍCH THƯỚC OVAL KHUÔN MẶT
            center = (target_w // 2, target_h // 2)
            axes = (285, 345)  

            # 2. TẠO MASK OVAL
            mask = np.zeros((target_h, target_w), dtype=np.uint8)
            cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
            masked_frame = cv2.bitwise_and(frame_display, frame_display, mask=mask)

            # 3. TẠO NỀN TRẮNG ĐỤC LỖ OVAL
            bg_color = np.full((target_h, target_w, 3), 255, dtype=np.uint8)
            mask_inv = cv2.bitwise_not(mask)
            bg_cutout = cv2.bitwise_and(bg_color, bg_color, mask=mask_inv)
            final_frame = cv2.add(masked_frame, bg_cutout)

            # 4. VẼ THANH TIẾN TRÌNH BAO QUANH OVAL
            progress = getattr(self, 'current_progress', 0.0)
            active_color = getattr(self, 'current_border_color', (250, 206, 135))
            
            # Vẽ một viền Track (màu xám nhạt) làm nền để thấy rõ hình oval
            track_color = (230, 230, 230) 
            cv2.ellipse(final_frame, center, axes, 0, 0, 360, track_color, 4)

            # Vẽ tiến trình nếu progress > 0
            if progress > 0:
                # Góc quét tối đa mỗi bên là 180 độ
                angle_covered = int(180 * progress)
                
                # Nhánh TRÁI (Bên trái khuôn mặt): 
                # Xuất phát từ 6 giờ (90 độ) chạy thuận chiều kim đồng hồ lên 12 giờ
                cv2.ellipse(final_frame, center, axes, 0, 90, 90 + angle_covered, active_color, 8)
                
                # Nhánh PHẢI (Bên phải khuôn mặt):
                # Xuất phát từ 6 giờ (90 độ) chạy ngược chiều kim đồng hồ lên 12 giờ
                cv2.ellipse(final_frame, center, axes, 0, 90 - angle_covered, 90, active_color, 8)

            # 5. RENDER LÊN GIAO DIỆN TKINTER
            frame_rgb = cv2.cvtColor(final_frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.camera_label.imgtk = imgtk
            self.camera_label.configure(image=imgtk)

        self.after(33, self._camera_preview_loop) # Chạy ở mức ~30fps

    # === CÁC HÀM CẬP NHẬT UI (Callback) ===
    def _schedule_update_progress(self, count, total, message, error=False):
        self.after(0, self._do_update_progress, count, total, message, error)

    def _do_update_progress(self, count, total, message, error=False):
        if not self.winfo_exists(): 
            return
        
        # 1. Lưu CỘT MỐC tiến trình (không cập nhật giao diện trực tiếp)
        if total > 0:
            self.target_progress = count / total
        else:
            self.target_progress = 0
            
        # 2. Lưu trạng thái lời nhắn
        self.current_message = message
        self.current_error = error
    def _get_guidance_message(self, progress_percent):
        """
        Trả về hướng dẫn hành động dựa trên % tiến độ chụp.
        Chiến thuật: 
        0-20%: Nhìn thẳng
        20-40%: Quay nhẹ trái
        40-60%: Quay nhẹ phải
        60-80%: Ngước lên/xuống
        80-100%: Cười tươi
        """
        if progress_percent < 0.2:
            return "Giữ yên, nhìn thẳng vào camera..."
        elif progress_percent < 0.4:
            return "Quay mặt nhẹ sang TRÁI..."
        elif progress_percent < 0.6:
            return "Quay mặt nhẹ sang PHẢI..."
        elif progress_percent < 0.8:
            return "Hơi CÚI xuống hoặc NGƯỚC lên..."
        else:
            return "Tuyệt vời! Hãy cười tươi lên..."

    # === LUỒNG WORKER (XỬ LÝ) ===
    def _registration_task(self):
        """(CHẠY TRÊN LUỒNG NỀN)"""
        reg_data = None # Đổi tên biến success thành reg_data để chứa output dictionary
        try:
            time.sleep(1.0)
            
            # Gọi thẳng hàm register của thư viện AI (sẽ trả về Dict chứa vector và zip)
            reg_data = self.ai_system.register_customer(
                customer_name=str(self.local_user_id), 
                num_frames_to_capture=self.num_images_target, # Đã update param theo luồng mới
                progress_callback=self._schedule_update_progress,
                stop_flag_check=lambda: not self._register_capture_running
            )
            
        except Exception as e:
            print(f"[REGISTER_AI_SCREEN] Lỗi luồng đăng ký: {e}")
            self._schedule_update_progress(0, self.num_images_target, f"Lỗi nghiêm trọng: {e}", error=True)
            reg_data = None
        
        if self._register_capture_running and self.winfo_exists():
            self.after(0, self._on_registration_finished, reg_data)
    def _on_registration_finished(self, reg_data):
        """(CHẠY TRÊN LUỒNG UI)"""
        self.controller.stop_camera_service()
        if not self.winfo_exists(): return

        if reg_data: # Nếu reg_data có dữ liệu (Thành công)
            self.feedback_label.configure(text="Đăng ký khuôn mặt thành công!", text_color="green")
            
            # ======================================================================
            # GỌI HÀM BẤT ĐỒNG BỘ ĐỂ LƯU DATABASE, FAISS VÀ GỬI SERVER (PHẦN 3 & 4)
            # ======================================================================
            self.ai_system.finalize_registration_async(
                user_id=self.local_user_id,
                name=self.name,
                phone=self.phone,
                email=self.email,
                password=self.password,
                points=0,          # Khách mới đăng ký mặc định 0 điểm
                reg_data=reg_data  # Gói dữ liệu chứa Vector và ZIP nén từ RAM
            )
            # ======================================================================

            # Tự động đăng nhập cho khách hàng ở UI
            registration_data = {"code": self.local_user_id, "name": self.name, "phone": self.phone, "points": 0}
            self.controller._on_background_task_complete(
                registration_data=registration_data,
                error_message=None,
                register_window=self.original_register_window
            )
            
            self.after(1500, self.destroy) 
        else:
            # Nếu thất bại (hoặc bị hủy), rollback
            print(f"[REGISTER_AI_SCREEN] Đăng ký AI thất bại. Rollback user {self.local_user_id}...")
            self.controller.db_manager.delete_customer(self.local_user_id)
            self.controller._on_background_task_complete(
                registration_data=None,
                error_message="Không thể tạo dữ liệu khuôn mặt. Vui lòng thử lại.",
                register_window=self.original_register_window
            )
            self.destroy()

    def _abort_face_capture(self):
        """Hủy quy trình chụp và quay lại form đăng ký."""
        self.controller.stop_camera_service()
        print("[REGISTER_AI_SCREEN] Hủy bỏ theo yêu cầu của người dùng.")
        
        # 1. Đặt cờ Hủy để dừng luồng worker và luồng preview
        self._register_capture_running = False 
        
        # 2. Xóa user đã tạo dở (Rollback DB)
        if self.local_user_id:
            print(f"[REGISTER_AI_SCREEN] Rollback user {self.local_user_id}...")
            self.controller.db_manager.delete_customer(self.local_user_id)
            
        # 3. Mở lại cửa sổ đăng ký gốc
        try:
            if self.original_register_window and self.original_register_window.winfo_exists():
                self.original_register_window.deiconify() # Hiện lại
                self.original_register_window.lift() # Đưa lên trên
            else:
                # Fallback: nếu cửa sổ đăng ký bị lỗi, mở màn hình chính
                print("[REGISTER_AI_SCREEN] Không tìm thấy cửa sổ đăng ký gốc, quay về màn hình chính.")
                self.controller.root.deiconify()
        except Exception as e:
            print(f"Lỗi khi mở lại cửa sổ đăng ký: {e}")
            self.controller.root.deiconify() # Fallback
        
        # 4. Phá hủy cửa sổ camera này
        if self.winfo_exists():
            self.destroy()