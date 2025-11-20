import tkinter as tk
import customtkinter as ctk
from tkinter import PhotoImage
from PIL import Image, ImageTk
import os

# --- BẮT ĐẦU SỬA LỖI IMPORT ---
import sys
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..') 
sys.path.append(project_root)
# --- KẾT THÚC SỬA LỖI IMPORT ---

from config import IMAGE_BASE_PATH, PRODUCT_IMAGES_CONFIG

class MainView:
    """
    Lớp này chịu trách nhiệm xây dựng toàn bộ giao diện chính (sản phẩm, giỏ hàng)
    vào 'root' window được cung cấp.
    """
    def __init__(self, root, controller):
        self.root = root
        self.controller = controller

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

        self.product_display_frame = tk.Frame(self.root, bg="white")
        self.product_display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=product_padx, pady=product_pady)

        self.welcome_label = tk.Label(
            self.product_display_frame, 
            textvariable=controller.welcome_message_var, 
            font=("Arial", 24, "bold"), 
            bg="white", 
            fg="#014b91"
        )
        self.welcome_label.grid(row=0, column=0, columnspan=4, pady=(10, 5), sticky="ew")

        tk.Label(self.product_display_frame, text="Sản phẩm", font=("Arial", font_sizes["title"], "bold"), bg="white").grid(row=1, column=0, columnspan=4, pady=(15, 0))
        
        layout = [
            (0, 2, 1, 1, 1), (1, 2, 2, 1, 1), (2, 2, 0, 2, 1), (3, 3, 1, 1, 1),
            (4, 3, 2, 1, 1), (5, 2, 3, 2, 1), (6, 4, 0, 1, 1), (7, 4, 1, 1, 1),
            (8, 4, 2, 1, 1), (9, 4, 3, 1, 1),
        ]
        product_keys = list(PRODUCT_IMAGES_CONFIG.keys())
        total_products = len(product_keys)

        for idx, row, col, rowspan, colspan in layout:
            if idx >= total_products: continue
            product_id = product_keys[idx]
            name, img_file, price = PRODUCT_IMAGES_CONFIG[product_id]

            item_frame = tk.Button(
                self.product_display_frame, bd=2, relief=tk.RAISED, bg="lightyellow",
                activebackground="lightyellow", cursor="arrow", compound=tk.TOP,
            )
            
            img_path = os.path.join(project_root, IMAGE_BASE_PATH, img_file)
            
            display_name = name if len(name) <= 12 or screen_width >= 1024 else name[:10] + "..."
            display_text = f"{display_name}\n{price:,}đ"

            try:
                photo_img = controller.cached_product_images.get(product_id)
                if photo_img:
                    item_frame.config(image=photo_img, text=display_text, font=("Arial", font_sizes["name"]))
                    item_frame.image = photo_img
                else:
                    img = Image.open(img_path)
                    img = img.resize(img_size, Image.Resampling.LANCZOS)
                    photo_img = ImageTk.PhotoImage(img)
                    item_frame.config(image=photo_img, text=display_text, font=("Arial", font_sizes["name"]))
                    item_frame.image = photo_img
            except Exception as e:
                print(f"Lỗi tải ảnh sản phẩm {img_path}: {e}")
                item_frame.config(text=f"Ảnh lỗi\n{display_text}", font=("Arial", font_sizes["name"]))

            item_frame.config(command=lambda prod=(product_id, name, price), btn=item_frame: controller.on_product_select(prod, btn))
            
            item_frame.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, padx=grid_padx, pady=grid_pady, sticky="nsew")
            self.product_display_frame.grid_columnconfigure(col, weight=1)
        
        for row in range(2, 6):
            self.product_display_frame.grid_rowconfigure(row, weight=1)

        self.control_frame = tk.Frame(self.root, bg="lightgray", width=control_width)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=product_pady)
        self.control_frame.pack_propagate(False)

        control_fonts = {
            "status": 16, "quantity_title": 18, "quantity_btn": 20,
            "action_btn": 16, "small_btn": 14, "cart_title": 20
        }

        # === LƯU THAM CHIẾU WIDGET VÀO 'self' ĐỂ CONTROLLER TRUY CẬP ===
        self.auth_frame = ctk.CTkFrame(self.control_frame, fg_color="lightgray", corner_radius=10)
        
        auth_label = ctk.CTkLabel(self.auth_frame, text="Trở thành thành viên để nhận nhiều ưu đãi!",
                                  font=("Arial", 16, "italic"), text_color="#333333",
                                  wraplength=control_width - 50)
        auth_label.pack(pady=(15, 10), padx=10)
        
        auth_button_frame = ctk.CTkFrame(self.auth_frame, fg_color="transparent")
        auth_button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        auth_button_frame.grid_columnconfigure((0, 1), weight=1)
        
        login_btn = ctk.CTkButton(auth_button_frame, text="Đăng Nhập", font=("Arial", 16, "bold"),
                                  command=controller.show_login_screen, 
                                  fg_color="#014b91", text_color="white", height=40)
        login_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        register_btn = ctk.CTkButton(auth_button_frame, text="Đăng Ký", font=("Arial", 16, "bold"),
                                     command=controller.show_register_screen,
                                     fg_color="transparent", border_color="#014b91",
                                     border_width=2, text_color="#014b91", height=40)
        register_btn.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # === LƯU THAM CHIẾU WIDGET VÀO 'self' ĐỂ CONTROLLER TRUY CẬP ===
        self.status_frame = tk.Frame(self.control_frame, bg="lightgray")
        self.status_frame.pack(pady=(10,5), fill=tk.X)
        status_label = tk.Label(self.status_frame, textvariable=controller.status_message_var,
                               font=("Arial", control_fonts["status"], "bold"), fg="blue", bg="lightgray", 
                               wraplength=control_width-20)
        status_label.pack()

        quantity_frame = tk.Frame(self.control_frame, bg="lightgray")
        quantity_frame.pack(pady=8)
        tk.Label(quantity_frame, text="Số lượng:", font=("Arial", control_fonts["quantity_title"], "bold"), bg="lightgray").pack(pady=(0,5))
        qty_controls = tk.Frame(quantity_frame, bg="lightgray")
        qty_controls.pack()
        
        minus_btn = tk.Button(qty_controls, text="-", font=("Arial", control_fonts["quantity_btn"], "bold"), 
                             width=3, height=1, bg="white", fg="grey", 
                             command=controller.decrease_quantity)
        minus_btn.pack(side=tk.LEFT, padx=3)
        
        quantity_display = tk.Label(qty_controls, textvariable=controller.quantity_var,
                                   font=("Arial", control_fonts["quantity_btn"], "bold"), width=4, bg="white", relief=tk.RIDGE, bd=2)
        quantity_display.pack(side=tk.LEFT, padx=3)
        
        plus_btn = tk.Button(qty_controls, text="+", font=("Arial", control_fonts["quantity_btn"], "bold"), 
                            width=3, height=1, bg="white", fg="grey", 
                            command=controller.increase_quantity)
        plus_btn.pack(side=tk.LEFT, padx=3)

        action_frame = tk.Frame(self.control_frame, bg="lightgray")
        action_frame.pack(pady=8, fill=tk.X)
        confirm_btn = tk.Button(action_frame, text="THÊM VÀO GIỎ", font=("Arial", control_fonts["action_btn"], "bold"), 
                               bg="green", fg="white", height=3, 
                               command=controller.on_confirm_add)
        confirm_btn.pack(fill=tk.X, pady=2)
        payment_btn = tk.Button(action_frame, text="THANH TOÁN", font=("Arial", control_fonts["action_btn"], "bold"), 
                               bg="red", fg="white", height=3, 
                               command=controller.on_ok_handler)
        payment_btn.pack(fill=tk.X, pady=2)

        control_buttons_frame = tk.Frame(self.control_frame, bg="lightgray")
        control_buttons_frame.pack(pady=5, fill=tk.X)
        reset_btn = tk.Button(control_buttons_frame, text="RESET", font=("Arial", control_fonts["small_btn"], "bold"), 
                             bg="blue", fg="white", 
                             command=controller.on_clear_cart_handler)
        reset_btn.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        exit_btn = tk.Button(control_buttons_frame, text="THOÁT", font=("Arial", control_fonts["small_btn"], "bold"), 
                            bg="black", fg="white", 
                            command=controller.on_app_close)
        exit_btn.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        cart_frame = tk.Frame(self.control_frame, bg="lightgray")
        cart_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        tk.Label(cart_frame, text="Giỏ Hàng", font=("Arial", control_fonts["cart_title"], "bold"), bg="lightgray").pack(pady=(0,3))
        
        cart_text_height = max(6, min(15, int(screen_height / 80)))
        cart_text_width = max(25, int(control_width / 12))
        cart_font_size = max(8, min(12, int(screen_width / 150)))
        
        # === LƯU THAM CHIẾU WIDGET VÀO 'self' ĐỂ CONTROLLER TRUY CẬP ===
        self.selected_items_display = tk.Text(cart_frame, height=cart_text_height, width=cart_text_width, 
                                            font=("Arial", cart_font_size), wrap=tk.WORD, bd=3, relief=tk.RIDGE)
        self.selected_items_display.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        cart_frame.configure(height=cart_min_height)
        
        # Yêu cầu controller cập nhật giỏ hàng (hiện là rỗng)
        controller.update_cart_display_handler()