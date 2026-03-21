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

# Ánh xạ từ item_name (trong DB) sang thông tin ảnh tĩnh đã cấu hình sẵn.
# Format: { "Aquafina": ("water", "water.png", 2000), ... }
_NAME_TO_STATIC_CONFIG = {}
for _key, (_name, _img, _price) in PRODUCT_IMAGES_CONFIG.items():
    _NAME_TO_STATIC_CONFIG[_name] = (_key, _img, _price)


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
                  command=self.controller.on_app_close).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

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

        font_sizes = {"name": 14}
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

        # Xử lý hình ảnh (có cache)
        try:
            photo_img = self.controller.cached_product_images.get(product_id)
            if not photo_img and img_path and os.path.exists(img_path):
                img = Image.open(img_path).resize(img_size, Image.Resampling.LANCZOS)
                photo_img = ImageTk.PhotoImage(img)
                self.controller.cached_product_images[product_id] = photo_img

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
    '''def refresh_product_grid(self):
        """
        Hàm QUAN TRỌNG: Xóa hết nút cũ và vẽ lại dựa trên DB mới nhất.
        """
        print("[UI] Đang làm mới lưới sản phẩm từ Database Local...")
        
        # 1. Xóa các nút cũ để tránh chồng chéo
        for btn in self.product_buttons:
            btn.destroy()
        self.product_buttons.clear()
        self._product_btn_map.clear()

        # 2. Lấy dữ liệu tồn kho MỚI NHẤT từ Controller -> DB Local
        try:
            current_stock = self.controller.get_latest_inventory()
        except AttributeError:
            print("[UI] Cảnh báo: Controller chưa có hàm get_latest_inventory. Dùng dữ liệu mặc định.")
            current_stock = {}

        # 3. Xây dựng danh sách sản phẩm sẽ hiển thị.
        products_to_show = self._build_product_list(current_stock)

        # =========================================================
        # GIỚI HẠN GIAO DIỆN STRICTLY 10 SẢN PHẨM
        # =========================================================
        if len(products_to_show) > 10:
            # Lấy 9 sản phẩm đầu tiên và lấy sản phẩm cuối cùng (mới nhất từ DB)
            # để ghi đè vào vị trí thứ 10. Các sản phẩm ở giữa bị bỏ qua trên UI.
            products_to_show = products_to_show[:9] + [products_to_show[-1]]
        # =========================================================

        # 4. Nếu không có sản phẩm nào → hiển thị giao diện trống
        if not products_to_show:
            self._show_empty_state()
            return

        # 5. Xác định layout (Lúc này len(products_to_show) chắc chắn <= 10)
        layout = self._get_layout(len(products_to_show))

        font_sizes = {"name": 14}
        grid_padx, grid_pady = 10, 25
        img_size = (150, 200)

        # 6. Vẽ lại từng nút sản phẩm
        for idx, (row, col, rowspan, colspan) in enumerate(layout):
            if idx >= len(products_to_show):
                break

            product_info = products_to_show[idx]
            self._create_product_button(
                product_info, row, col, rowspan, colspan,
                img_size, font_sizes, grid_padx, grid_pady
            )

        # 7. Cấu hình co giãn lưới
        num_cols = max((col + colspan for _, col, _, colspan in layout), default=4)
        for i in range(num_cols):
            self.product_display_frame.grid_columnconfigure(i, weight=1)
        for r in range(2, max((row + rowspan for row, _, rowspan, _ in layout), default=6) + 1):
            self.product_display_frame.grid_rowconfigure(r, weight=1)'''
    @staticmethod
    def _make_product_id(item_name):
        """Tạo khóa cache cho sản phẩm từ item_name (dùng cho sản phẩm từ server không có trong cấu hình tĩnh)."""
        return "".join(c if c.isalnum() or c in '-_' else '_' for c in item_name).lower()

    '''def _build_product_list(self, current_stock):
        """
        Xây dựng danh sách sản phẩm để hiển thị.

        Ưu tiên:
          1. Sản phẩm trong DB (đã đồng bộ từ server).
          2. Sản phẩm trong cấu hình tĩnh PRODUCT_IMAGES_CONFIG chưa xuất hiện trong DB.

        Mỗi phần tử trả về là dict:
            {
                "product_id": str,    # key dùng để cache ảnh
                "item_name": str,     # tên sản phẩm (khớp với DB)
                "image_path": str,    # đường dẫn tuyệt đối đến ảnh (hoặc None)
                "default_price": float,
                "db_price": float,
                "stock_qty": int,
            }
        """
        result = []

        # --- Sản phẩm từ DB (có thể bao gồm cả sản phẩm mới từ server) ---
        for item_name, data in current_stock.items():
            static = _NAME_TO_STATIC_CONFIG.get(item_name)
            if static:
                product_id, img_file, default_price = static
                img_path = os.path.join(project_root, IMAGE_BASE_PATH, img_file)
                if not os.path.exists(img_path):
                    img_path = None
            else:
                # Sản phẩm mới từ server, không có trong cấu hình tĩnh
                product_id = self._make_product_id(item_name)
                img_path = data.get("image_path") or None
                default_price = data.get("price", 0)

            # Ưu tiên đường dẫn ảnh đã tải từ server nếu có
            db_image_path = data.get("image_path")
            if db_image_path and os.path.exists(db_image_path):
                img_path = db_image_path

            result.append({
                "product_id": product_id,
                "item_name": item_name,
                "image_path": img_path,
                "default_price": default_price,
                "db_price": data.get("price", 0),
                "stock_qty": data.get("qty", 0),
            })

        # --- Bổ sung sản phẩm từ cấu hình tĩnh chưa có trong DB ---
        db_names = set(current_stock.keys())
        for product_id, (name, img_file, default_price) in PRODUCT_IMAGES_CONFIG.items():
            if name not in db_names:
                img_path = os.path.join(project_root, IMAGE_BASE_PATH, img_file)
                if not os.path.exists(img_path):
                    img_path = None
                result.append({
                    "product_id": product_id,
                    "item_name": name,
                    "image_path": img_path,
                    "default_price": default_price,
                    "db_price": 0,
                    "stock_qty": 0,
                })

        return result'''

    '''def _get_layout(self, count):
        """
        Trả về danh sách (row, col, rowspan, colspan) cho `count` sản phẩm.
        Dùng layout cố định cho 10 sản phẩm; layout lưới đơn giản cho các trường hợp khác.
        """
        if count == 10:
            # Layout gốc tối ưu cho 10 sản phẩm
            return [
                (2, 1, 1, 1), (2, 2, 1, 1), (2, 0, 2, 1), (3, 1, 1, 1),
                (3, 2, 1, 1), (2, 3, 2, 1), (4, 0, 1, 1), (4, 1, 1, 1),
                (4, 2, 1, 1), (4, 3, 1, 1),
            ]

        # Layout lưới động: 4 cột
        cols = 4
        layout = []
        for i in range(count):
            row = 2 + (i // cols)
            col = i % cols
            layout.append((row, col, 1, 1))
        return layout'''

    '''def _create_product_button(self, product_info, row, col, rowspan, colspan,
                               img_size, font_sizes, grid_padx, grid_pady):
        """Tạo và đặt một nút sản phẩm vào lưới."""
        product_id = product_info["product_id"]
        item_name = product_info["item_name"]
        img_path = product_info["image_path"]
        default_price = product_info["default_price"]
        db_price = product_info["db_price"]
        stock_qty = product_info["stock_qty"]

        current_price = db_price if db_price > 0 else default_price
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

        display_text = f"{item_name}\n{status_text}"

        item_frame = tk.Button(
            self.product_display_frame, bd=2, relief=tk.RAISED,
            bg=btn_bg, activebackground=btn_bg,
            compound=tk.TOP, state=btn_state,
            disabledforeground=text_color
        )

        # Xử lý hình ảnh (có cache để tối ưu hiệu năng)
        try:
            photo_img = self.controller.cached_product_images.get(product_id)
            if not photo_img and img_path and os.path.exists(img_path):
                img = Image.open(img_path).resize(img_size, Image.Resampling.LANCZOS)
                photo_img = ImageTk.PhotoImage(img)
                self.controller.cached_product_images[product_id] = photo_img

            if photo_img:
                item_frame.config(image=photo_img, text=display_text,
                                  font=("Arial", font_sizes["name"]), fg=text_color, wraplength=140)
                item_frame.image = photo_img
            else:
                item_frame.config(text=f"[No Img]\n{display_text}")

        except Exception as e:
            print(f"Lỗi load ảnh {item_name}: {e}")
            item_frame.config(text=f"Error\n{display_text}")

        if not is_out_of_stock:
            item_frame.config(
                command=lambda p=(product_id, item_name, current_price), b=item_frame:
                    self.controller.on_product_select(p, b)
            )

        item_frame.grid(
            row=row, column=col,
            rowspan=rowspan, columnspan=colspan,
            padx=grid_padx, pady=grid_pady, sticky="nsew"
        )

        self.product_buttons.append(item_frame)
        self._product_btn_map[item_name] = item_frame
'''
    '''def _show_empty_state(self):
        """Hiển thị thông báo khi không có sản phẩm nào (server trống)."""
        empty_label = tk.Label(
            self.product_display_frame,
            text="Chưa có sản phẩm nào.\nVui lòng liên hệ quản trị viên.",
            font=("Arial", 24), bg="white", fg="#888888",
            justify=tk.CENTER
        )
        empty_label.grid(row=2, column=0, columnspan=4, pady=80, sticky="nsew")
        self.product_buttons.append(empty_label)'''

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

        # Tra cứu giá mặc định từ cấu hình tĩnh nếu có
        static = _NAME_TO_STATIC_CONFIG.get(item_name)
        default_price = static[2] if static else 0
        current_price = db_price if db_price > 0 else default_price

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