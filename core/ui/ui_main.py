import tkinter as tk
import customtkinter as ctk
from tkinter import PhotoImage
from PIL import Image, ImageTk
import os
import sys

# --- CẤU HÌNH ĐƯỜNG DẪN (Để import được config) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(current_dir, '..', '..') 
sys.path.append(project_root)

from config import IMAGE_BASE_PATH, PRODUCT_IMAGES_CONFIG

class MainView:
    """
    Lớp này chịu trách nhiệm xây dựng toàn bộ giao diện chính (sản phẩm, giỏ hàng)
    vào 'root' window được cung cấp.
    """
    def __init__(self, root, controller):
        self.root = root
        self.controller = controller
        
        # --- 1. CẤU HÌNH CỬA SỔ CHÍNH ---
        self.controller.stop_camera_service()
        self.root.geometry("1920x1080+0+0")
        self.root.overrideredirect(True)
        
        # --- 2. LAYOUT CHÍNH (Chia làm 2 phần: Trái & Phải) ---
        product_padx = 20
        product_pady = 20
        
        # [LEFT] Frame chứa danh sách sản phẩm
        self.product_display_frame = tk.Frame(self.root, bg="white")
        self.product_display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=product_padx, pady=product_pady)

        # Tiêu đề & Lời chào
        self.welcome_label = tk.Label(
            self.product_display_frame, 
            textvariable=controller.welcome_message_var, 
            font=("Arial", 24, "bold"), 
            bg="white", 
            fg="#014b91"
        )
        self.welcome_label.grid(row=0, column=0, columnspan=4, pady=(10, 5), sticky="ew")

        # Tiêu đề "Sản phẩm"
        tk.Label(self.product_display_frame, text="Sản phẩm", font=("Arial", 35, "bold"), bg="white").grid(row=1, column=0, columnspan=4, pady=(15, 0))
        
        # Danh sách lưu các nút sản phẩm (để xóa đi vẽ lại khi update giá)
        self.product_buttons = []

        # [RIGHT] Khởi tạo Frame điều khiển (Giỏ hàng, Nút bấm...)
        self._init_control_panel()

        # --- 3. VẼ LƯỚI SẢN PHẨM LẦN ĐẦU ---
        self.refresh_product_grid()

    def _init_control_panel(self):
        """Khởi tạo cột bên phải (Giỏ hàng, Nút bấm, Đăng nhập...)"""
        control_width = 600
        # Cấu hình font chữ
        control_fonts = {
            "status": 20, "quantity_title": 18, "quantity_btn": 20,
            "action_btn": 16, "small_btn": 14, "cart_title": 20
        }
        
        self.control_frame = tk.Frame(self.root, bg="lightgray", width=control_width)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=20)
        self.control_frame.pack_propagate(False) # Giữ kích thước cố định

        # --- A. Khu vực Đăng nhập/Đăng ký ---
        self.auth_frame = ctk.CTkFrame(self.control_frame, fg_color="lightgray", corner_radius=10)
        self.auth_frame.pack(fill=tk.X, pady=(10, 5))
        
        auth_label = ctk.CTkLabel(self.auth_frame, text="Trở thành thành viên để nhận nhiều ưu đãi!",
                                  font=("Arial", 16, "italic"), text_color="#333333", wraplength=control_width - 50)
        auth_label.pack(pady=(15, 10), padx=10)
        
        auth_button_frame = ctk.CTkFrame(self.auth_frame, fg_color="transparent")
        auth_button_frame.pack(fill=tk.X, padx=15, pady=(0, 15))
        auth_button_frame.grid_columnconfigure((0, 1), weight=1)
        
        # Nút Đăng Nhập
        ctk.CTkButton(auth_button_frame, text="Đăng Nhập", font=("Arial", 16, "bold"),
                      command=self.controller.show_login_screen, 
                      fg_color="#014b91", text_color="white", height=40).grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # Nút Đăng Ký
        ctk.CTkButton(auth_button_frame, text="Đăng Ký", font=("Arial", 16, "bold"),
                      command=self.controller.show_register_screen,
                      fg_color="transparent", border_color="#014b91", border_width=2, 
                      text_color="#014b91", height=40).grid(row=0, column=1, padx=(5, 0), sticky="ew")

        # --- B. Trạng thái & Thông báo ---
        self.status_frame = tk.Frame(self.control_frame, bg="lightgray")
        self.status_frame.pack(pady=(10,5), fill=tk.X)
        tk.Label(self.status_frame, textvariable=self.controller.status_message_var,
                 font=("Arial", control_fonts["status"], "bold"), fg="blue", bg="lightgray", 
                 wraplength=control_width-20).pack()

        # --- C. Điều chỉnh số lượng ---
        quantity_frame = tk.Frame(self.control_frame, bg="lightgray")
        quantity_frame.pack(pady=8)
        tk.Label(quantity_frame, text="Số lượng:", font=("Arial", 18, "bold"), bg="lightgray").pack(pady=(0,5))
        
        qty_controls = tk.Frame(quantity_frame, bg="lightgray")
        qty_controls.pack()
        
        tk.Button(qty_controls, text="-", font=("Arial", 20, "bold"), width=3, bg="white", 
                  command=self.controller.decrease_quantity).pack(side=tk.LEFT, padx=3)
        
        tk.Label(qty_controls, textvariable=self.controller.quantity_var, font=("Arial", 20, "bold"), 
                 width=4, bg="white", relief=tk.RIDGE, bd=2).pack(side=tk.LEFT, padx=3)
        
        tk.Button(qty_controls, text="+", font=("Arial", 20, "bold"), width=3, bg="white", 
                  command=self.controller.increase_quantity).pack(side=tk.LEFT, padx=3)

        # --- D. Các nút hành động (Thêm, Thanh toán) ---
        action_frame = tk.Frame(self.control_frame, bg="lightgray")
        action_frame.pack(pady=8, fill=tk.X)
        
        tk.Button(action_frame, text="THÊM VÀO GIỎ", font=("Arial", 16, "bold"), bg="green", fg="white", height=3, 
                  command=self.controller.on_confirm_add).pack(fill=tk.X, pady=2, padx=10)
        
        tk.Button(action_frame, text="THANH TOÁN", font=("Arial", 16, "bold"), bg="red", fg="white", height=3, 
                  command=self.controller.on_ok_handler).pack(fill=tk.X, pady=2, padx=10)
        
        # --- E. Reset & Thoát ---
        control_buttons_frame = tk.Frame(self.control_frame, bg="lightgray")
        control_buttons_frame.pack(pady=5, fill=tk.X)
        
        tk.Button(control_buttons_frame, text="RESET", font=("Arial", 14, "bold"), bg="blue", fg="white", 
                  command=self.controller.on_clear_cart_handler).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        tk.Button(control_buttons_frame, text="THOÁT", font=("Arial", 14, "bold"), bg="black", fg="white", 
                  command=self.controller.on_app_close).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # --- F. Hiển thị Giỏ hàng ---
        cart_frame = tk.Frame(self.control_frame, bg="lightgray")
        cart_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        tk.Label(cart_frame, text="Giỏ Hàng", font=("Arial", 20, "bold"), bg="lightgray").pack(pady=(0,3))
        
        self.selected_items_display = tk.Text(cart_frame, height=10, width=30, font=("Arial", 23), wrap=tk.WORD, bd=3, relief=tk.RIDGE)
        self.selected_items_display.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # Cập nhật hiển thị giỏ hàng lần đầu (nếu có dữ liệu cũ)
        self.controller.update_cart_display_handler()

    def refresh_product_grid(self):
        """
        Hàm QUAN TRỌNG: Xóa hết nút cũ và vẽ lại dựa trên DB mới nhất.
        Được gọi khi MainView khởi tạo hoặc khi Controller yêu cầu update.
        """
        print("[UI] Đang làm mới lưới sản phẩm từ Database Local...")
        
        # 1. Xóa các nút cũ để tránh chồng chéo
        for btn in self.product_buttons:
            btn.destroy()
        self.product_buttons.clear()

        # 2. Lấy dữ liệu tồn kho MỚI NHẤT từ Controller -> DB Local
        try:
            current_stock = self.controller.get_latest_inventory()
        except AttributeError:
            print("[UI] Cảnh báo: Controller chưa có hàm get_latest_inventory. Dùng dữ liệu mặc định.")
            current_stock = {}

        # 3. Cấu hình Layout (Sơ đồ vị trí các nút)
        # Format: (idx, row, col, rowspan, colspan)
        layout = [
            (0, 2, 1, 1, 1), (1, 2, 2, 1, 1), (2, 2, 0, 2, 1), (3, 3, 1, 1, 1),
            (4, 3, 2, 1, 1), (5, 2, 3, 2, 1), (6, 4, 0, 1, 1), (7, 4, 1, 1, 1),
            (8, 4, 2, 1, 1), (9, 4, 3, 1, 1),
        ]
        
        font_sizes = {"name": 14}
        grid_padx, grid_pady = 10, 25
        img_size = (150, 200)
        product_keys = list(PRODUCT_IMAGES_CONFIG.keys())

        # 4. Vẽ lại từng nút sản phẩm
        for idx, row, col, rowspan, colspan in layout:
            if idx >= len(product_keys): continue
            
            product_id = product_keys[idx]
            name, img_file, default_price = PRODUCT_IMAGES_CONFIG[product_id]

            # --- LOGIC GIÁ & TỒN KHO ---
            product_data = current_stock.get(name)
            
            if product_data and isinstance(product_data, dict):
                stock_qty = product_data.get('qty', 0)
                db_price = product_data.get('price', 0)
                # Ưu tiên giá từ DB (đã sync), nếu chưa có thì dùng giá mặc định
                current_price = db_price if db_price > 0 else default_price
            else:
                stock_qty = 0 # Hoặc 100 tùy logic bạn muốn khi chưa sync
                current_price = default_price

            is_out_of_stock = stock_qty <= 0

            # Cấu hình hiển thị (Màu sắc, Trạng thái)
            if is_out_of_stock:
                btn_state = tk.DISABLED
                btn_bg = "#e0e0e0" # Màu xám
                text_color = "red"
                status_text = f"{int(current_price):,}đ\n(HẾT)"
            else:
                btn_state = tk.NORMAL
                btn_bg = "lightyellow"
                text_color = "black"
                status_text = f"{int(current_price):,}đ"

            # Tạo nút
            item_frame = tk.Button(
                self.product_display_frame, bd=2, relief=tk.RAISED,
                bg=btn_bg, activebackground=btn_bg,
                compound=tk.TOP, state=btn_state,
                disabledforeground=text_color
            )
            
            # Xử lý hình ảnh (có cache để tối ưu hiệu năng)
            display_name = name
            display_text = f"{display_name}\n{status_text}"
            
            try:
                # Thử lấy từ cache của controller trước
                photo_img = self.controller.cached_product_images.get(product_id)
                if not photo_img:
                    # Nếu chưa có, load từ file và cache lại
                    img_path = os.path.join(project_root, IMAGE_BASE_PATH, img_file)
                    if os.path.exists(img_path):
                        img = Image.open(img_path).resize(img_size, Image.Resampling.LANCZOS)
                        photo_img = ImageTk.PhotoImage(img)
                        self.controller.cached_product_images[product_id] = photo_img
                    else:
                        photo_img = None
                
                if photo_img:
                    item_frame.config(image=photo_img, text=display_text, font=("Arial", font_sizes["name"]), fg=text_color, wraplength=140)
                    item_frame.image = photo_img # Giữ tham chiếu
                else:
                    item_frame.config(text=f"[No Img]\n{display_text}")

            except Exception as e:
                print(f"Lỗi load ảnh {name}: {e}")
                item_frame.config(text=f"Error\n{display_text}")

            # Gán sự kiện click (chỉ khi còn hàng)
            if not is_out_of_stock:
                # Quan trọng: Truyền current_price mới nhất vào hàm xử lý
                item_frame.config(command=lambda p=(product_id, name, current_price), b=item_frame: self.controller.on_product_select(p, b))
            
            # Đặt nút vào lưới
            item_frame.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, padx=grid_padx, pady=grid_pady, sticky="nsew")
            
            # Lưu vào list để quản lý
            self.product_buttons.append(item_frame)

        # Cấu hình co giãn lưới (để các nút dàn đều đẹp mắt)
        for i in range(4): self.product_display_frame.grid_columnconfigure(i, weight=1)
        for row in range(2, 6): self.product_display_frame.grid_rowconfigure(row, weight=1)