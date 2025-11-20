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
            
        self.num_images_target = 10 
        self._recognition_capture_running = True # Cờ để hủy

        # --- (Code UI giữ nguyên) ---
        self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        self.overrideredirect(True)
        self.configure(bg="white")
        self.lift()
        self.focus_force()

        self.camera_label = tk.Label(self, bg="white")
        self.camera_label.pack(expand=True, fill="both")

        self.feedback_label = ctk.CTkLabel(
            self, text="Nhìn thẳng vào camera để nhận diện",
            font=("Arial", 30, "bold"), text_color="#014b91", fg_color="white"
        )
        self.feedback_label.place(relx=0.5, rely=0.08, anchor="center")
        
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal", width=400, height=20, progress_color="#027cf0")
        self.progress_bar.set(0)
        self.progress_bar.place(relx=0.5, rely=0.15, anchor="center")

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
        """Vòng lặp này CHỈ hiển thị camera, không tính toán."""
        if not self._recognition_capture_running or not self.winfo_exists():
            return

        # Lấy ảnh mới nhất (do luồng ngầm của thư viện cung cấp)
        frame_bgr = self.ai_system.get_latest_frame_for_display()

        if frame_bgr is not None:
            frame_display = cv2.resize(frame_bgr, (640, 480))
            frame_rgb = cv2.cvtColor(frame_display, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.camera_label.imgtk = imgtk
            self.camera_label.configure(image=imgtk)

        self.after(33, self._camera_preview_loop) # ~30fps

    # === CÁC HÀM CẬP NHẬT UI (Callback) ===
    # (Được gọi bởi luồng worker)
    def _schedule_update_progress(self, count, total, message, error=False):
        self.after(0, self._do_update_progress, count, total, message, error)
    
    def _do_update_progress(self, count, total, message, error=False):
        if not self.winfo_exists(): 
            return
        
        progress_value = count / total
        self.progress_bar.set(progress_value)
        
        color = "#014b91"
        if error:
            color = "red"
        elif "Lỗi" in message or "Không tìm thấy" in message:
            color = "yellow"
            
        self.feedback_label.configure(text=message, text_color=color)

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
            self.destroy()

    def _cancel_recognition(self):
        # Đặt cờ Hủy
        self._recognition_capture_running = False 
        
        # Hủy ngay lập tức (không cần chờ luồng kia)
        if self.winfo_exists():
            self.controller._on_recognition_finished(None)
            self.destroy()