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
        
        # Danh sách lưu các nút sản phẩm (để xóa đi vẽ lại khi update)
        self.product_buttons = []
        # Dict tra cứu nút theo item_name cho cập nhật nhanh
        self._product_btn_map = {}

        # [RIGHT] Khởi tạo Frame điều khiển (Giỏ hàng, Nút bấm...)
        self._init_control_panel()

        # --- 3. VẼ LƯỚI SẢN PHẨM LẦN ĐẦU ---
        #self.refresh_product_grid()

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
                  command=self.controller.return_to_welcome).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # --- F. Hiển thị Giỏ hàng ---
        cart_frame = tk.Frame(self.control_frame, bg="lightgray")
        cart_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        tk.Label(cart_frame, text="Giỏ Hàng", font=("Arial", 20, "bold"), bg="lightgray").pack(pady=(0,3))
        
        self.selected_items_display = tk.Text(cart_frame, height=10, width=30, font=("Arial", 23), wrap=tk.WORD, bd=3, relief=tk.RIDGE)
        self.selected_items_display.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        
        # Cập nhật hiển thị giỏ hàng lần đầu (nếu có dữ liệu cũ)
        self.controller.update_cart_display_handler()

    # ------------------------------------------------------------------
    # Lưới sản phẩm
    # ------------------------------------------------------------------
    # Sơ đồ 10 ô trên giao diện (row, col, rowspan, colspan)
    SLOT_LAYOUT = {
        1: (2, 0, 2, 1),  # Ô 1: Trái, To
        2: (2, 1, 1, 1),  # Ô 2: Giữa, Trên
        3: (2, 2, 1, 1),  # Ô 3: Giữa, Trên
        4: (2, 3, 2, 1),  # Ô 4: Phải, To
        5: (3, 1, 1, 1),  # Ô 5: Giữa, Dưới
        6: (3, 2, 1, 1),  # Ô 6: Giữa, Dưới
        7: (4, 0, 1, 1),  # Ô 7: Hàng cuối
        8: (4, 1, 1, 1),  # Ô 8: Hàng cuối
        9: (4, 2, 1, 1),  # Ô 9: Hàng cuối
        10:(4, 3, 1, 1)   # Ô 10: Hàng cuối
    }

    def refresh_product_grid(self):
        print("[UI] Đang làm mới 10 ô sản phẩm...")
        
        # 1. Xóa các nút cũ
        for btn in self.product_buttons:
            btn.destroy()
        self.product_buttons.clear()
        self._product_btn_map.clear()

        # 2. Lấy dữ liệu tồn kho (Key là Slot Number từ 1 đến 10)
        try:
            current_stock = self.controller.get_latest_inventory()
        except AttributeError:
            current_stock = {}

        font_sizes = {"name": 11}
        grid_padx, grid_pady = 10, 25
        img_size = (150, 200)

        # 3. Quét qua đúng 10 ô vật lý
        for slot in range(1, 11):
            row, col, rowspan, colspan = self.SLOT_LAYOUT[slot]
            product_info = current_stock.get(slot)
            
            # Vẽ giao diện cho từng ô
            self._create_slot_button(
                slot, product_info, row, col, rowspan, colspan,
                img_size, font_sizes, grid_padx, grid_pady
            )

        # Cấu hình co giãn lưới
        for i in range(4):
            self.product_display_frame.grid_columnconfigure(i, weight=1)
        for r in range(2, 5):
            self.product_display_frame.grid_rowconfigure(r, weight=1)

    def _create_slot_button(self, slot, product_info, row, col, rowspan, colspan,
                               img_size, font_sizes, grid_padx, grid_pady):
        """Tạo nút hiển thị cho 1 ô (có hoặc không có sản phẩm)."""
        
        # Nếu ô trống (không có sản phẩm)
        if not product_info:
            empty_frame = tk.Button(
                self.product_display_frame, bd=2, relief=tk.FLAT,
                bg="#f0f0f0", state=tk.DISABLED,
                text=f"Ô số {slot}\n[Trống]", font=("Arial", font_sizes["name"]), fg="#aaaaaa"
            )
            empty_frame.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, padx=grid_padx, pady=grid_pady, sticky="nsew")
            self.product_buttons.append(empty_frame)
            return

        # --- NẾU Ô CÓ SẢN PHẨM ---
        item_name = product_info["item_name"]
        img_path = product_info["image_path"]
        current_price = product_info["price"]
        stock_qty = product_info["qty"]
        product_id = slot 

        is_out_of_stock = stock_qty <= 0

        if is_out_of_stock:
            btn_state = tk.DISABLED
            btn_bg = "#e0e0e0"
            text_color = "red"
            status_text = f"{int(current_price):,}đ\n(HẾT)"
        else:
            btn_state = tk.NORMAL
            btn_bg = "lightyellow"
            text_color = "black"
            status_text = f"{int(current_price):,}đ"

        display_text = f"Ô {slot}: {item_name}\n{status_text}"

        item_frame = tk.Button(
            self.product_display_frame, bd=2, relief=tk.RAISED,
            bg=btn_bg, activebackground=btn_bg,
            compound=tk.TOP, state=btn_state,
            disabledforeground=text_color
        )

        # Xử lý hình ảnh (có cache thông minh)
        try:
            photo_img = None
            # Lấy thời gian chỉnh sửa file thực tế trên ổ cứng (để check nếu ảnh bị server ghi đè)
            current_mtime = os.path.getmtime(img_path) if img_path and os.path.exists(img_path) else 0
            
            # Lấy dữ liệu cache hiện tại của ô này
            cached_data = self.controller.cached_product_images.get(product_id)

            # Điều kiện dùng lại ảnh trong RAM:
            # 1. Có cache định dạng dict
            # 2. Đường dẫn ảnh giống hệt nhau (tránh lỗi thay sản phẩm khác vào cùng ô)
            # 3. File trên ổ cứng không bị thay đổi (tránh lỗi đổi ảnh nhưng giữ nguyên tên)
            if (cached_data and isinstance(cached_data, dict) and 
                cached_data.get("path") == img_path and 
                cached_data.get("mtime") == current_mtime):
                photo_img = cached_data.get("image")

            # Nếu cache sai hoặc chưa có -> Tải lại từ ổ cứng
            if not photo_img and img_path and os.path.exists(img_path):
                img = Image.open(img_path).resize(img_size, Image.Resampling.LANCZOS)
                photo_img = ImageTk.PhotoImage(img)
                # Lưu lại cache với cấu trúc mới (dict)
                self.controller.cached_product_images[product_id] = {
                    "path": img_path,
                    "mtime": current_mtime,
                    "image": photo_img
                }

            if photo_img:
                item_frame.config(image=photo_img, text=display_text,
                                  font=("Arial", font_sizes["name"]), fg=text_color, wraplength=140)
                item_frame.image = photo_img
            else:
                item_frame.config(text=f"[No Img]\n{display_text}")

        except Exception as e:
            item_frame.config(text=f"Error\n{display_text}")

        if not is_out_of_stock:
            # Truyền ID giả lập để tương thích với luồng Controller hiện tại
            item_frame.config(
                command=lambda p=(product_id, item_name, current_price), b=item_frame:
                    self.controller.on_product_select(p, b)
            )

        item_frame.grid(
            row=row, column=col, rowspan=rowspan, columnspan=colspan,
            padx=grid_padx, pady=grid_pady, sticky="nsew"
        )

        self.product_buttons.append(item_frame)
        self._product_btn_map[item_name] = item_frame # Vẫn lưu map theo tên để update nhanh khi có giao dịch
    @staticmethod
    def _make_product_id(item_name):
        """Tạo khóa cache cho sản phẩm từ item_name (dùng cho sản phẩm từ server không có trong cấu hình tĩnh)."""
        return "".join(c if c.isalnum() or c in '-_' else '_' for c in item_name).lower()

    def hot_update_ui(self, old_name, new_name, price, quantity):
        """Cập nhật logic giao diện khi có thay đổi từ MQTT"""
        # Nếu có đổi tên, phải đổi khóa (key) trong từ điển lưu trữ nút bấm
        if old_name != new_name and old_name in self._product_btn_map:
            self._product_btn_map[new_name] = self._product_btn_map.pop(old_name)
            
        # Gọi hàm update UI có sẵn (hàm này sẽ tự động đọc lại DB mới nhất)
        self.update_single_product(new_name, price, quantity)
    def update_single_product(self, item_name, price=None, quantity=None):
        """
        Cập nhật hiển thị của MỘT sản phẩm cụ thể mà không vẽ lại toàn bộ lưới.
        Được gọi khi nhận được MQTT hot update (Requirement 2A).
        Args:
            item_name: Tên sản phẩm (khớp với DB).
            price: Giá mới (None = không thay đổi).
            quantity: Số lượng mới (None = không thay đổi).
        """
        btn = self._product_btn_map.get(item_name)
        if btn is None:
            return

        try:
            current_stock = self.controller.get_latest_inventory()
        except AttributeError:
            current_stock = {}

        product_data = {}
        current_slot = "" # Thêm biến hứng slot
        for slot, data in current_stock.items():
            if data.get('item_name') == item_name:
                product_data = data
                current_slot = slot
                break
        db_price = price if price is not None else product_data.get("price", 0)
        stock_qty = quantity if quantity is not None else product_data.get("qty", 0)

        current_price = db_price
        
        is_out_of_stock = stock_qty <= 0
        if is_out_of_stock:
            btn_state = tk.DISABLED
            btn_bg = "#e0e0e0"
            text_color = "red"
            status_text = f"{int(current_price):,}đ\n(HẾT)"
        else:
            btn_state = tk.NORMAL
            btn_bg = "lightyellow"
            text_color = "black"
            status_text = f"{int(current_price):,}đ"

        display_text = f"Ô {current_slot}: {item_name}\n{status_text}"

        # Cập nhật nút
        btn.config(state=btn_state, bg=btn_bg, activebackground=btn_bg,
                   disabledforeground=text_color)
        if btn.cget("image"):
            btn.config(text=display_text, fg=text_color, wraplength=140)
        else:
            btn.config(text=f"[No Img]\n{display_text}")

        # Gán lại command với giá mới
        #static_key = static[0] if static else self._make_product_id(item_name)
        if not is_out_of_stock:
            btn.config(
                command=lambda p=(current_slot, item_name, current_price), b=btn:
                    self.controller.on_product_select(p, b)
            )
        else:
            btn.config(command="")

        print(f"[UI] Đã cập nhật sản phẩm '{item_name}': giá={current_price}, tồn kho={stock_qty}.")