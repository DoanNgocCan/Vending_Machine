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
    def __init__(self, parent, controller, local_user_id, name, phone, dob, password, original_register_window):
        super().__init__(parent)
        self.controller = controller
        
        self.local_user_id = local_user_id
        self.name = name
        self.phone = phone
        self.dob = dob
        self.password = password
        self.original_register_window = original_register_window
        
        self.ai_system = self.controller.camera_ai_system
        self.num_images_target = 200 
        self._register_capture_running = True # Cờ để hủy

        # --- (Code UI giữ nguyên) ---
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.overrideredirect(True)
        self.configure(bg="white")
        self.lift()
        self.focus_force()

        self.camera_label = tk.Label(self, bg="white")
        self.camera_label.pack(expand=True, fill="both")

        self.feedback_label = ctk.CTkLabel(
            self, text="Vui lòng nhìn thẳng vào camera", font=("Arial", 30, "bold"),
            text_color="#014b91", fg_color="white"
        )
        self.feedback_label.place(relx=0.5, rely=0.08, anchor="center")
        
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", width=400, height=20, progress_color="#027cf0")
        self.progress_bar.set(0)
        self.progress_bar.place(relx=0.5, rely=0.15, anchor="center")

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
        """Vòng lặp này CHỈ hiển thị camera, không tính toán."""
        if not self._register_capture_running or not self.winfo_exists():
            return
        frame_bgr = self.ai_system.get_latest_frame_for_display()
        if frame_bgr is not None:
            frame_display = cv2.resize(frame_bgr, (640, 480))
            frame_rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.camera_label.imgtk = imgtk
            self.camera_label.configure(image=imgtk)
        self.after(33, self._camera_preview_loop)

    # === CÁC HÀM CẬP NHẬT UI (Callback) ===
    def _schedule_update_progress(self, count, total, message, error=False):
        self.after(0, self._do_update_progress, count, total, message, error)

    def _do_update_progress(self, count, total, message, error=False):
        if not self.winfo_exists(): 
            return
        
        # Tính phần trăm
        if total > 0:
            progress_value = count / total
        else:
            progress_value = 0
            
        self.progress_bar.set(progress_value)
        
        display_text = message
        color = "#014b91"

        if error:
            color = "red"
        # Nếu library gửi tín hiệu đang chụp (CAPTURING), UI sẽ tự quyết định câu nhắc
        elif message == "CAPTURING":
            display_text = self._get_guidance_message(progress_value)
            color = "#007acc" # Màu xanh dương đậm hơn chút cho hướng dẫn
        elif "Lỗi" in message or "Không tìm thấy" in message:
            color = "#ffaa00" # Màu cam cảnh báo

        self.feedback_label.configure(text=display_text, text_color=color)

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
        success = False
        try:
            time.sleep(1.0)
            
            # === LOGIC CỐT LÕI ===
            # Gọi thẳng hàm register của thư viện
            success = self.ai_system.register_customer(
                customer_name=str(self.local_user_id), # Dùng ID làm tên
                num_images_to_capture=self.num_images_target,
                progress_callback=self._schedule_update_progress,
                stop_flag_check=lambda: not self._register_capture_running
            )
            # === KẾT THÚC ===
            
        except Exception as e:
            print(f"[REGISTER_AI_SCREEN] Lỗi luồng đăng ký: {e}")
            self._schedule_update_progress(0, self.num_images_target, f"Lỗi nghiêm trọng: {e}", error=True)
            success = False
        
        if self._register_capture_running and self.winfo_exists():
            self.after(0, self._on_registration_finished, success)

    def _on_registration_finished(self, success):
        """(CHẠY TRÊN LUỒNG UI)"""
        if not self.winfo_exists(): return

        if success:
            self.feedback_label.configure(text="Đăng ký khuôn mặt thành công!", text_color="green")
            registration_data = self.controller.db_manager.get_customer_by_id(self.local_user_id)
            self.controller._on_background_task_complete(
                registration_data=registration_data,
                error_message=None,
                register_window=self.original_register_window
            )
            threading.Thread(
                target=self.controller._background_registration_and_embedding,
                args=(self.name, self.phone, self.dob, self.password, self.original_register_window, self.local_user_id),
                daemon=True
            ).start()
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