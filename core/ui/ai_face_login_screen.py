# SHOPPING_KEYPAD_APP/core/ui/ai_face_login_screen.py
import tkinter as tk
import customtkinter as ctk
import cv2
import threading
from PIL import Image, ImageTk
import numpy as np
import time
from collections import Counter
import queue

class AIFaceLoginScreen(tk.Toplevel):
    """
    Màn hình đăng nhập (ĐÃ TỐI ƯU)
    Sử dụng trực tiếp logic 2 luồng của thư viện AI.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.ai_system = self.controller.camera_ai_system
        
        # 1. KIỂM TRA DATABASE RỖNG (giữ nguyên)
        if self.ai_system.searcher.index.ntotal == 0:
            print("[LOGIN_AI_SCREEN] Database rỗng, bỏ qua nhận diện.")
            self.after(0, self._skip_and_close)
            return 
        self.controller.start_camera_service()
        self.num_images_target = 10 
        self._recognition_capture_running = True # Cờ để hủy

        # --- (Code UI giữ nguyên) ---
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.overrideredirect(True)
        self.configure(bg="white")
        self.lift()
        #self.focus_force()

        self.camera_label = tk.Label(self, bg="white")
        self.camera_label.pack(expand=True, fill="both")

        self.feedback_label = ctk.CTkLabel(
            self, text="Nhìn thẳng vào camera để nhận diện",
            font=("Arial", 30, "bold"), text_color="#014b91", fg_color="white"
        )
        self.feedback_label.place(relx=0.5, rely=0.08, anchor="center")
        
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", width=400, height=20, progress_color="#027cf0")
        self.progress_bar.set(0)
        #self.progress_bar.place(relx=0.5, rely=0.15, anchor="center")
        self.current_progress = 0.0
        self.current_border_color = (240, 124, 2)

        self.target_progress = 0.0 # Biến đích để chạy từ từ tới
        self.current_message = ""
        self.current_error = False

        cancel_button = ctk.CTkButton(
            self, text="Hủy", font=("Arial", 18, "bold"),
            width=150, height=50, corner_radius=25,
            fg_color="transparent", border_color="#027cf0", border_width=2,
            text_color="#027cf0", command=self._cancel_recognition
        )
        cancel_button.place(relx=0.5, rely=0.9, anchor="center")

        self.bind("<Escape>", lambda e: self._cancel_recognition())
        
        # === BẮT ĐẦU 2 LUỒNG CHÍNH ===
        # 1. Luồng UI (chỉ để xem)
        self._camera_preview_loop() 
        # 2. Luồng Worker (để xử lý)
        self.recognition_thread = threading.Thread(target=self._recognition_task, daemon=True)
        self.recognition_thread.start()

    def _skip_and_close(self):
        if self.winfo_exists():
            self.controller._on_recognition_finished(None)
            self.destroy() 

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
            # Tốc độ tăng: 0.015 (1.5%) mỗi khung hình. 
            # Bạn có thể tăng giảm số này để % chạy nhanh hay chậm hơn
            current += 0.015 
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
            self.current_progress = 1.0 # Ép đầy thanh tiến trình 100%
            self.progress_bar.set(1.0)
            percent = 100
        elif "Lỗi" in msg or "Không tìm thấy" in msg:
            color = "#ffaa00"
            self.current_border_color = (0, 140, 255)
            display_text = msg
        else:
            # RENDER CHỮ CHẠY %
            display_text = f"Đang nhận diện khuôn mặt... {percent}%"
            if msg == "CAPTURING":
                color = "#00aa00"
                self.current_border_color = (0, 170, 0)
            else:
                self.current_border_color = (240, 124, 2)
                
        self.feedback_label.configure(text=display_text, text_color=color)

        # ==========================================
        # 3. LẤY FRAME VÀ VẼ OVAL CAMERA
        # ==========================================
        frame_bgr = self.ai_system.get_latest_frame_for_display()

        if frame_bgr is not None:
            # Resize chuẩn
            target_w, target_h = 960, 720
            frame_display = cv2.resize(frame_bgr, (target_w, target_h))

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
    # (Được gọi bởi luồng worker)
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
    # === LUỒNG WORKER (XỬ LÝ) ===
    def _recognition_task(self):
        """(CHẠY TRÊN LUỒNG NỀN)"""
        final_result_id = "Unknown"
        try:
            # Chờ 1s cho UI khởi động
            time.sleep(1.0) 
            
            # === LOGIC CỐT LÕI ===
            # Gọi thẳng hàm login của thư viện.
            # Hàm này sẽ tự chạy vòng lặp (vừa chụp vừa xử lý)
            # và gọi lại _schedule_update_progress cho chúng ta.
            final_result_id = self.ai_system.login_customer(
                num_images_to_capture=self.num_images_target,
                similarity_threshold=0.4,
                progress_callback=self._schedule_update_progress,
                stop_flag_check=lambda: not self._recognition_capture_running
            )
            # === KẾT THÚC ===

        except Exception as e:
            print(f"[LOGIN_AI_SCREEN] Lỗi luồng nhận diện: {e}")
            self._schedule_update_progress(0, self.num_images_target, f"Lỗi: {e}", error=True)
            final_result_id = "Unknown"
        
        # Chỉ gọi kết quả nếu người dùng không nhấn Hủy
        if self._recognition_capture_running and self.winfo_exists():
            self.after(0, self._handle_recognition_result, final_result_id)

    def _handle_recognition_result(self, final_result_id):
        if self.winfo_exists():
            self.controller._on_recognition_finished(final_result_id)
            self.controller.stop_camera_service()
            self.destroy()

    def _cancel_recognition(self):
        # Đặt cờ Hủy
        self._recognition_capture_running = False 
        
        # Hủy ngay lập tức (không cần chờ luồng kia)
        if self.winfo_exists():
            self.controller._on_recognition_finished(None)
            self.controller.stop_camera_service()
            self.destroy()