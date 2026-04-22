# SHOPPING_KEYPAD_APP/core/ui/register_screen.py
import tkinter as tk
import customtkinter as ctk
import re

class RegisterScreen(tk.Toplevel):
    """
    Màn hình đăng ký thông tin người dùng.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.controller.stop_camera_service()
        
        controller._hide_system_taskbar()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")
        self.lift()
        self.focus_force()
        try:
            self.attributes('-type', 'dock')
        except tk.TclError:
            print("Cảnh báo: Không thể đặt thuộc tính '-type'.")
        self.configure(bg="lightgray")
        
        self.protocol("WM_DELETE_WINDOW", self._cancel_and_hide_keyboard)

        # Tăng chiều cao lên 780 để chứa thêm ô Xác nhận mật khẩu
        content_frame = tk.Frame(self, width=800, height=780, bg="white", relief=tk.RAISED, bd=3)
        content_frame.place(relx=0.5, rely=0.4, anchor="center")
        content_frame.pack_propagate(False)

        tk.Label(content_frame, text="Đăng ký khách hàng", font=("Arial", 32, "bold"), bg="white", fg="#014b91").pack(pady=(30, 20))

        form_frame = ctk.CTkFrame(content_frame, fg_color="white", corner_radius=100)
        form_frame.pack(pady=10, padx=60, fill="x", expand=True)

        name_label = ctk.CTkLabel(form_frame, text="Họ và tên", font=("Arial", 16), text_color="black")
        name_label.pack(anchor="w", padx=5)
        self.name_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="Nguyễn Văn A", placeholder_text_color="gray")
        self.name_entry.pack(fill="x", pady=(5, 15))

        phone_label = ctk.CTkLabel(form_frame, text="Số điện thoại", font=("Arial", 16), text_color="black")
        phone_label.pack(anchor="w", padx=5)
        self.phone_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="Nhập SĐT 10 số", placeholder_text_color="gray")
        self.phone_entry.pack(fill="x", pady=(5, 15))

        # Đổi Ngày sinh thành Email
        email_label = ctk.CTkLabel(form_frame, text="Email", font=("Arial", 16), text_color="black")
        email_label.pack(anchor="w", padx=5)
        self.email_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="vidu@gmail.com", placeholder_text_color="gray")
        self.email_entry.pack(fill="x", pady=(5, 15))

        password_label = ctk.CTkLabel(form_frame, text="Mật khẩu", font=("Arial", 16), text_color="black")
        password_label.pack(anchor="w", padx=5)
        password_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        password_frame.pack(fill="x", pady=(5, 15))

        self.password_entry = ctk.CTkEntry(password_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="Mật khẩu (ít nhất 6 ký tự)", placeholder_text_color="gray", show="*")
        self.password_entry.pack(side="left", fill="x", expand=True)
        
        self.show_hide_button = ctk.CTkButton(password_frame, text="Hiện", font=("Arial", 14), width=40, height=30, fg_color="transparent", text_color="#014b91", hover=False, command=self._toggle_password_visibility)
        self.show_hide_button.place(relx=1.0, rely=0.5, x=-10, anchor="e")

        # Thêm ô Xác nhận mật khẩu
        confirm_password_label = ctk.CTkLabel(form_frame, text="Xác nhận mật khẩu", font=("Arial", 16), text_color="black")
        confirm_password_label.pack(anchor="w", padx=5)
        self.confirm_password_entry = ctk.CTkEntry(form_frame, font=("Arial", 18), height=48, corner_radius=15, border_width=2, border_color="#014b91", fg_color="white", text_color="black", placeholder_text="Nhập lại mật khẩu", placeholder_text_color="gray", show="*")
        self.confirm_password_entry.pack(fill="x", pady=(5, 15))

        # Cập nhật danh sách input_widgets
        self.input_widgets = [self.name_entry, self.phone_entry, self.email_entry, self.password_entry, self.confirm_password_entry]
        background_widgets = [self, content_frame, form_frame, name_label, phone_label, email_label, password_label, confirm_password_label]
        
        for widget in self.input_widgets:
            widget.bind("<FocusIn>", self.controller._handle_focus_in)
            widget.bind("<Return>", lambda e, w=widget: self.controller._on_enter_key(w, self.input_widgets))
            
        for widget in background_widgets:
            widget.bind("<Button-1>", self.controller._handle_background_click)

        self.message_var = tk.StringVar(value="")
        message_label = ctk.CTkLabel(content_frame, textvariable=self.message_var, font=("Arial", 16), text_color="red", fg_color="white")
        message_label.pack(pady=(0, 10))

        btn_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=(0, 30), fill="x", padx=60)
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        register_btn = ctk.CTkButton(btn_frame, text="Tiếp tục", font=("Arial", 18, "bold"), fg_color="#014b91", text_color="white", height=50, corner_radius=100, command=self._save_registration)
        register_btn.grid(row=0, column=0, padx=(0,10), sticky="ew")

        cancel_button = ctk.CTkButton(btn_frame, text="Hủy", font=("Arial", 18, "bold"), fg_color="transparent", text_color="#014b91", border_width=2, border_color="#014b91", height=50, corner_radius=100, command=self._cancel_and_hide_keyboard)
        cancel_button.grid(row=0, column=1, padx=(10, 0), sticky="ew")

    def _toggle_password_visibility(self):
        if self.password_entry.cget("show") == "*":
            self.password_entry.configure(show="")
            self.show_hide_button.configure(text="Ẩn")
        else:
            self.password_entry.configure(show="*")
            self.show_hide_button.configure(text="Hiện")

    def _save_registration(self):
        self.focus_set()
        self.controller._hide_keyboard() 
        name = self.name_entry.get().strip()
        phone = self.phone_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.password_entry.get().strip()
        confirm_password = self.confirm_password_entry.get().strip()

        # Kiểm tra nhập đủ
        if not name or not phone or not email or not password or not confirm_password:
            self.message_var.set("Vui lòng nhập đầy đủ thông tin.")
            return
        
        if any(char.isdigit() for char in name):
            self.message_var.set("Tên không hợp lệ.")
            return
            
        if not phone.isdigit() or not (len(phone) == 10):
            self.message_var.set("Số điện thoại phải có 10 chữ số.")
            return
            
        # Kiểm tra định dạng Email
        if not re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email):
            self.message_var.set("Email không đúng định dạng.")
            self.email_entry.focus()
            return

        if len(password) < 6:
            self.message_var.set("Mật khẩu phải có ít nhất 6 ký tự.")
            self.password_entry.focus()
            return
            
        # Kiểm tra khớp mật khẩu
        if password != confirm_password:
            self.message_var.set("Mật khẩu xác nhận không khớp.")
            self.confirm_password_entry.focus()
            return
        
        print("[REGISTER_UI] Dữ liệu hợp lệ. Đang đăng ký vào DB local...")
        
        # Truyền email vào db_manager (đã sửa ở bước trước)
        result = self.controller.db_manager.register_customer(name, phone, email, password, face_encoding=None)
        
        if "error" in result:
            if result["error"] == "duplicate_phone_or_email":
                self.message_var.set("Lỗi: Số điện thoại hoặc Email này đã tồn tại.")
            else:
                self.message_var.set(f"Lỗi CSDL: {result['error']}")
            return

        local_user_id = result['code']
        print(f"[REGISTER_UI] Đăng ký DB local thành công, local_id: {local_user_id}. Chuyển sang chụp ảnh.")

        self.withdraw()
        
        # Cập nhật lời gọi API sang màn hình chụp ảnh, truyền email thay vì dob
        self.controller.show_face_capture_screen(
            local_user_id,
            name,
            phone,
            email,
            password,
            self
        )

    def _cancel_and_hide_keyboard(self):
        self.focus_set()
        self.controller._hide_keyboard()
        self.controller.root.deiconify() 
        self.destroy()