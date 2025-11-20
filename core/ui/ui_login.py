# SHOPPING_KEYPAD_APP/core/ui/login_screen.py
import tkinter as tk
import customtkinter as ctk
import threading
from tkinter import messagebox

class LoginScreen(tk.Toplevel):
    """
    Màn hình đăng nhập bằng SĐT/Mật khẩu hoặc Khuôn mặt.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        controller._hide_system_taskbar()
        self.title("Đăng nhập")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")
        self.lift()
        self.focus_force()
        try:
            self.attributes('-type', 'dock')
        except tk.TclError:
            pass
        self.configure(bg="lightgray")
        
        self.protocol("WM_DELETE_WINDOW", self._cancel_login)

        content_frame = ctk.CTkFrame(self, width=800, height=700, corner_radius=15, fg_color="white", border_width=2, border_color="#014b91")
        content_frame.place(relx=0.5, rely=0.35, anchor="center")
        content_frame.pack_propagate(False)

        ctk.CTkLabel(content_frame, text="Đăng Nhập", font=("Arial", 32, "bold"), text_color="#014b91").pack(pady=(40, 20))

        face_id_button = ctk.CTkButton(content_frame, text="Đăng nhập bằng khuôn mặt", font=("Arial", 18), height=50, command=self._handle_face_login, fg_color="#027cf0", hover_color="#4a4a4a")
        face_id_button.pack(pady=10, padx=40, fill="x")

        ctk.CTkLabel(content_frame, text="— hoặc —", font=("Arial", 16), text_color="gray").pack(pady=15)

        form_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        form_frame.pack(pady=10, padx=40, fill="x")

        self.phone_entry = ctk.CTkEntry(form_frame, placeholder_text="Số điện thoại", font=("Arial", 16), height=48, corner_radius=10)
        self.phone_entry.pack(fill="x", pady=(0, 15))

        password_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        password_frame.pack(fill="x") 

        self.password_entry = ctk.CTkEntry(password_frame, placeholder_text="Mật khẩu", font=("Arial", 16), height=48, fg_color="white", text_color="black", show="*", corner_radius=10)
        self.password_entry.pack(side="left", fill="x", expand=True)

        self.show_hide_button = ctk.CTkButton(password_frame, text="Hiện", font=("Arial", 14), width=40, height=30, fg_color="transparent", text_color="#014b91", hover=False, command=self._toggle_password_visibility)
        self.show_hide_button.place(relx=1.0, rely=0.5, x=-10, anchor="e")
        self.show_hide_button.bind("<Button-1>", lambda e: None) 

        forgot_password_button = ctk.CTkButton(content_frame, text="Quên mật khẩu?", font=("Arial", 14), text_color="#014b91", fg_color="transparent", hover=False, command=self._handle_forgot_password)
        forgot_password_button.pack(anchor="e", padx=40, pady=(5, 20))

        self.login_button = ctk.CTkButton(content_frame, text="Đăng Nhập", font=("Arial", 18, "bold"), height=50, fg_color="#014b91", command=self._handle_login)
        self.login_button.pack(pady=10, padx=40, fill="x")

        cancel_button = ctk.CTkButton(content_frame, text="Hủy", font=("Arial", 18, "bold"), height=50, fg_color="transparent", border_width=2, border_color="#014b91", text_color="#014b91", command=self._cancel_login)
        cancel_button.pack(pady=(5, 30), padx=40, fill="x")

        self.message_label = ctk.CTkLabel(content_frame, text="", font=("Arial", 14), text_color="red")
        self.message_label.pack(pady=(0, 10), padx=40, fill="x")

        input_widgets = [self.phone_entry, self.password_entry]
        background_widgets = [self, content_frame, form_frame, face_id_button, forgot_password_button, self.login_button, cancel_button, self.message_label]
        for child in content_frame.winfo_children() + form_frame.winfo_children():
            if isinstance(child, ctk.CTkLabel):
                background_widgets.append(child)

        for widget in input_widgets:
            widget.bind("<FocusIn>", self.controller._handle_focus_in)
    
        self.phone_entry.bind("<Return>", lambda e: self.password_entry.focus_set())
        self.password_entry.bind("<Return>", lambda e: self._handle_login())

        for widget in background_widgets:
            widget.bind("<Button-1>", self.controller._handle_background_click)
        
    def _toggle_password_visibility(self):
        if self.password_entry.cget("show") == "*":
            self.password_entry.configure(show="")
            self.show_hide_button.configure(text="Ẩn")
        else:
            self.password_entry.configure(show="*")
            self.show_hide_button.configure(text="Hiện")

    def _handle_login(self):
        self.controller._hide_keyboard()
        phone = self.phone_entry.get().strip()
        password = self.password_entry.get().strip()
        if not phone or not password:
            self.message_label.configure(text="Vui lòng nhập đầy đủ thông tin.", text_color="red")
            return
        
        self.login_button.configure(state="disabled", text="Đang xử lý...")
        self.update()
        
        user_data = self.controller.db_manager.login_customer(phone, password)
        
        if user_data:
            print("LOGIN: Đăng nhập thành công từ CSDL local.")
            self._login_successful_callback(user_data)
            threading.Thread(target=self._verify_with_server_task, args=(user_data,), daemon=True).start()
            return
        
        print("LOGIN: Đăng nhập local thất bại, thử đăng nhập qua API server...")
        server_user_data = self.controller.api_manager.login_customer(phone, password)
        
        if server_user_data:
            print("LOGIN: Đăng nhập server thành công. Đang lưu/cập nhật dữ liệu về local...")
            self.controller.db_manager.add_or_update_customer_from_server(server_user_data)
            client_user_data = {
                "code": server_user_data.get('user_id'),
                "name": server_user_data.get('full_name'),
                "phone": server_user_data.get('phone_number'),
                "points": server_user_data.get('points')
            }
            self._login_successful_callback(client_user_data)
        else:
            print("LOGIN: Đăng nhập thất bại trên cả local và server.")
            self.message_label.configure(text="Sai SĐT hoặc mật khẩu. Vui lòng thử lại.", text_color="red")
            self.login_button.configure(state="normal", text="Đăng Nhập")

    def _verify_with_server_task(self, user_data):
        """(CHẠY TRÊN LUỒNG NỀN)"""
        print(f"VERIFY: Đối chiếu thông tin user {user_data['name']} với server...")
        server_data = self.controller.api_manager.get_customer_by_id(user_data['code'])
        if server_data is None:
            print(f"VERIFY-WARN: User {user_data['code']} tồn tại ở local nhưng không có trên server!")
            self.controller.db_manager.mark_customer_as_unsynced(user_data['code'])
        else:
            print("VERIFY: Thông tin user trên server khớp với local.")
            self.controller.db_manager.add_or_update_customer_from_server(server_data)

    def _login_successful_callback(self, customer_data):
        """Gọi lại controller để xử lý logic đăng nhập thành công"""
        self.message_label.configure(text=f"Đăng nhập thành công! Chào {customer_data['name']}.", text_color="green")
        self.controller.handle_login_success(customer_data)
        self.after(1500, self.destroy)

    def _handle_face_login(self):
        """Yêu cầu controller hiển thị màn hình loading để nhận diện."""
        self.controller._hide_keyboard()
        self.withdraw()
        self.controller.show_loading_screen()
        self.destroy()

    def _handle_forgot_password(self):
        self.controller._hide_keyboard()
        dialog = ctk.CTkInputDialog(text="Nhập số điện thoại đã đăng ký:", title="Quên Mật Khẩu")
        phone_number = dialog.get_input()
        if phone_number:
            messagebox.showinfo("Demo", f"Chức năng quên mật khẩu cho SĐT: {phone_number} (chưa được triển khai)")

    def _cancel_login(self):
        self.controller._hide_keyboard()
        self.controller.root.deiconify() 
        self.destroy()