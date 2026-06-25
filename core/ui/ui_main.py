import tkinter as tk
import customtkinter as ctk
from tkinter import PhotoImage
from PIL import Image, ImageTk
import os
import sys
import requests
import threading
import random
from datetime import datetime
# Import module xử lý lời chào vừa tạo
from core.ui.ui_main_ads import generate_recommendation_messages

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
        product_padx = 25
        product_pady = 25
        
        # [LEFT] Frame chứa danh sách sản phẩm (Dùng CTkFrame để hỗ trợ trong suốt)
        self.product_display_frame = ctk.CTkFrame(self.root, fg_color="white", corner_radius=0)
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
             font=("Arial", control_fonts["status"], "bold"), fg="#014b91", bg="lightgray", 
             wraplength=control_width-20, height=2).pack()

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
        
        ctk.CTkButton(action_frame, text="THÊM VÀO GIỎ 🛒", font=("Arial", 18, "bold"),
              fg_color="#28a745", hover_color="#218838", text_color="white", 
              height=60, corner_radius=10,
              command=self.controller.on_confirm_add).pack(fill=tk.X, pady=5, padx=10)

        ctk.CTkButton(action_frame, text="THANH TOÁN 💳", font=("Arial", 18, "bold"),
                    fg_color="#dc3545", hover_color="#c82333", text_color="white", 
                    height=60, corner_radius=10,
                    command=self.controller.on_ok_handler).pack(fill=tk.X, pady=5, padx=10)
                
        # --- E. Reset & Thoát ---
        control_buttons_frame = tk.Frame(self.control_frame, bg="lightgray")
        control_buttons_frame.pack(pady=5, fill=tk.X)
        
        # Nút RESET đã được bo góc và có hiệu ứng hover
        ctk.CTkButton(control_buttons_frame, text="RESET", font=("Arial", 16, "bold"), 
                      fg_color="#014b91", hover_color="#00346F", text_color="white", 
                      height=50, corner_radius=12,
                      command=self.controller.on_clear_cart_handler).pack(side=tk.LEFT, padx=(10, 5), fill=tk.X, expand=True)
        
        # Nút THOÁT đã được bo góc và có hiệu ứng hover
        ctk.CTkButton(control_buttons_frame, text="THOÁT", font=("Arial", 16, "bold"), 
                      fg_color="#333333", hover_color="#1a1a1a", text_color="white", 
                      height=50, corner_radius=12,
                      command=self.controller.return_to_welcome).pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)

        # --- F. Hiển thị Giỏ hàng ---
        # 1. Khởi tạo khung chứa tổng (Dòng này bị thiếu gây ra lỗi)
        cart_frame = tk.Frame(self.control_frame, bg="lightgray") 
        cart_frame.pack(pady=5, fill=tk.BOTH, expand=True)
        tk.Label(cart_frame, text="Giỏ Hàng", font=("Arial", 20, "bold"), bg="lightgray").pack(pady=(0,3))
        
        # 2. Khung bo góc hiện đại bọc bên ngoài Text
        cart_container = ctk.CTkFrame(cart_frame, corner_radius=10, fg_color="white", border_width=1, border_color="#cccccc")
        cart_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        cart_container.pack_propagate(False)
        
        # 3. Widget Text (Đã bỏ viền, nền trắng cho đồng bộ)
        # 3. Widget Text
        self.selected_items_display = tk.Text(
            cart_container, height=10, width=30, font=("Arial", 23), 
            wrap=tk.WORD, bd=0, relief=tk.FLAT, bg="white", highlightthickness=0,
            takefocus=0)
        self.selected_items_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.selected_items_display.bind("<Button-1>", lambda e: self.controller._hide_keyboard())
        self.selected_items_display.bind("<FocusIn>", lambda e: self.controller._hide_keyboard())
        
        # Cập nhật hiển thị giỏ hàng lần đầu (nếu có dữ liệu cũ)
        self.controller.update_cart_display_handler()

    # ------------------------------------------------------------------
    # Lưới sản phẩm
    # ------------------------------------------------------------------
    # Sơ đồ 10 ô trên giao diện (row, col, rowspan, colspan)
    SLOT_LAYOUT = {
        1: (2, 1, 1, 1),  # Ô 2: Giữa, Trên
        2: (2, 2, 1, 1),  # Ô 3: Giữa, Trên
        3: (2, 0, 2, 1),  # Ô 3: Trái, To
        4: (3, 1, 1, 1),  # Ô 5: Giữa, Dưới
        5: (3, 2, 1, 1),  # Ô 6: Giữa, Dưới
        6: (2, 3, 2, 1),  # Ô 4: Phải, To
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

        font_sizes = {"name": 16}
        grid_padx, grid_pady = 10, 25
        img_size = (150, 200)

        # 3. Quét qua đúng 10 ô vật lý
        for slot in range(1, 11):
            row, col, rowspan, colspan = self.SLOT_LAYOUT[slot]
            product_info = current_stock.get(slot) or current_stock.get(str(slot))
            
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
        
        # --- NẾU Ô TRỐNG ---
        if not product_info:
            empty_frame = ctk.CTkButton(
                self.product_display_frame,
                text=f"Ô số {slot}\n[Trống]",
                font=("Arial", font_sizes["name"]),
                fg_color="#f0f0f0",
                text_color="#aaaaaa",
                state="disabled",
                corner_radius=15,      # Bo góc 15px
                border_width=2,        # Viền mỏng
                border_color="#e0e0e0"
            )
            empty_frame.grid(row=row, column=col, rowspan=rowspan, columnspan=colspan, padx=grid_padx, pady=grid_pady, sticky="nsew")
            self.product_buttons.append(empty_frame)
            return

        # --- NẾU Ô CÓ SẢN PHẨM ---
        item_name = product_info["item_name"]
        img_path = product_info["image_path"]
        current_price = product_info["price"]
        stock_qty = product_info["qty"]
        product_id = str(slot)

        is_out_of_stock = stock_qty <= 0

        # 1. Cấu hình màu sắc
        if is_out_of_stock:
            btn_state = "disabled"
            btn_bg = "#f5f5f5"
            text_color = "#dc3545" # Đỏ
            status_text = f"{int(current_price):,}đ\n(HẾT)"
        else:
            btn_state = "normal"
            btn_bg = "#ffffff"       # Nền trắng sạch sẽ
            text_color = "#333333"   # Chữ xám đậm
            status_text = f"{int(current_price):,}đ"

        display_text = f"Ô {slot}: {item_name}\n{status_text}"

        # 2. XỬ LÝ ẢNH TRƯỚC KHI TẠO NÚT BẤM (RẤT QUAN TRỌNG)
        photo_img = None
        try:
            current_mtime = os.path.getmtime(img_path) if img_path and os.path.exists(img_path) else 0
            cached_data = self.controller.cached_product_images.get(product_id)

            if (cached_data and isinstance(cached_data, dict) and 
                cached_data.get("path") == img_path and 
                cached_data.get("mtime") == current_mtime):
                photo_img = cached_data.get("image")

            if not photo_img and img_path and os.path.exists(img_path):
                img = Image.open(img_path).resize(img_size, Image.Resampling.LANCZOS)
                photo_img = ctk.CTkImage(light_image=img, size=img_size)
                self.controller.cached_product_images[product_id] = {
                    "path": img_path,
                    "mtime": current_mtime,
                    "image": photo_img
                }
        except Exception as e:
            pass # Nếu lỗi tải ảnh, photo_img vẫn là None

        # 3. TẠO NÚT BẤM VÀ TRUYỀN ẢNH VÀO NGAY LÚC KHỞI TẠO
        # Chọn màu viền mặc định: xanh dương giống nút đăng nhập cho sản phẩm có thể chọn, giữ màu xám cho hết hàng
        default_border_color = "#014b91" if not is_out_of_stock else "#cccccc"

        item_frame = ctk.CTkButton(
            self.product_display_frame, 
            text=display_text if photo_img else f"[No Img]\n{display_text}",
            image=photo_img,         # <--- BÍ QUYẾT LÀ Ở ĐÂY: Truyền ảnh vào ngay lập tức
            font=("Arial", font_sizes["name"], "bold"),
            text_color=text_color,
            text_color_disabled=text_color,
            fg_color=btn_bg,
            hover=False,
            state=btn_state,
            compound="top",
            corner_radius=15,
            border_width=3,
            border_color=default_border_color
        )

        if not is_out_of_stock:
            item_frame.configure(
                command=lambda p=(product_id, item_name, current_price), b=item_frame:
                    self.controller.on_product_select(p, b)
            )

        item_frame.grid(
            row=row, column=col, rowspan=rowspan, columnspan=colspan,
            padx=grid_padx, pady=grid_pady, sticky="nsew"
        )
        
        # Cập nhật GUI tức thì để khắc phục lỗi Alpha (trong suốt)
        item_frame.update_idletasks()

        self.product_buttons.append(item_frame)
        self._product_btn_map[item_name] = item_frame
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
        """
        btn = self._product_btn_map.get(item_name)
        if btn is None:
            return

        try:
            current_stock = self.controller.get_latest_inventory()
        except AttributeError:
            current_stock = {}

        product_data = {}
        current_slot = "" 
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
            btn_state = "disabled"
            btn_bg = "#f5f5f5"
            text_color = "#dc3545"
            status_text = f"{int(current_price):,}đ\n(HẾT)"
        else:
            btn_state = "normal"
            btn_bg = "#ffffff"
            text_color = "#333333"
            status_text = f"{int(current_price):,}đ"

        display_text = f"Ô {current_slot}: {item_name}\n{status_text}"

        # Sử dụng .configure() thay cho .config()
        btn.configure(
            state=btn_state, 
            fg_color=btn_bg, 
            text_color_disabled=text_color,
            text_color=text_color,
            text=display_text
        )

        # Kiểm tra ảnh (trong ctk thuộc tính image truy cập bằng cget)
        if not btn.cget("image"):
            btn.configure(text=f"[No Img]\n{display_text}")

        if not is_out_of_stock:
            btn.configure(
                command=lambda p=(str(current_slot), item_name, current_price), b=btn:
                    self.controller.on_product_select(p, b)
            )
        else:
            btn.configure(command=None)
        # THÊM LOGIC CẬP NHẬT GIÁ CHO POPUP ĐỀ XUẤT (NẾU ĐANG MỞ)
        if hasattr(self, 'recommendation_overlay') and self.recommendation_overlay.winfo_exists():
            inventory = self.controller.get_latest_inventory()
            
            # Lấy thông tin sản phẩm đang được popup hiển thị
            rec_product = inventory.get(self.current_recommended_slot) or inventory.get(int(self.current_recommended_slot) if self.current_recommended_slot.isdigit() else self.current_recommended_slot)
            
            # Nếu sản phẩm bị thay đổi MQTT trùng với sản phẩm đang hiện trên Popup
            if rec_product and rec_product.get('item_name') == item_name:
                new_price = price if price is not None else rec_product.get('price', 0)
                
                # Sửa trực tiếp Label giá và tên trên Popup
                if hasattr(self, 'rec_price_label') and self.rec_price_label.winfo_exists():
                    self.rec_price_label.config(text=f"{int(new_price):,} VNĐ")
                if hasattr(self, 'rec_name_label') and self.rec_name_label.winfo_exists():
                    self.rec_name_label.config(text=item_name)
    # ==========================================
    # CÁC HÀM XỬ LÝ POPUP GỢI Ý MUA HÀNG
    # ==========================================
    def check_and_show_recommendation(self, user_id, user_name):
        """Chạy luồng ngầm lấy dữ liệu gợi ý từ server"""
        def fetch_data():
            try:
                url = f"https://vending-machine.lavaa.qzz.io/api/users/{user_id}/recommendation"
                response = requests.get(url, timeout=5)
                
                # Kiểm tra mã trạng thái HTTP trước khi phân tích JSON
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get('status') == 'success':
                            product = data['data']
                            self.root.after(0, lambda: self.show_recommendation_popup(product, user_name))
                        else:
                            print(f"[UI] Không có gợi ý: {data.get('message')}")
                    except ValueError:
                        print("[UI] Cảnh báo: Server không trả về JSON hợp lệ.")
                else:
                    print(f"[UI] Lỗi Server API: Mã {response.status_code}")
                    print(f"[UI] Chi tiết lỗi: {response.text}")
            except Exception as e:
                print(f"[UI] Lỗi kết nối khi tải gợi ý mua hàng: {e}")

        threading.Thread(target=fetch_data, daemon=True).start()

    def show_recommendation_popup(self, product, user_name):
        """Vẽ popup đề xuất với lời chào cá nhân hóa và phân loại sản phẩm thông minh"""
        recommended_name = product['name']
        recommended_price = product['price']
        
        # --- LẤY TEXT ĐÃ ĐƯỢC XỬ LÝ TỪ MODULE BÊN NGOÀI ---
        final_greeting, final_suggest = generate_recommendation_messages(user_name, recommended_name)
        
        # 1. Tìm slot sản phẩm
        try:
            current_stock = self.controller.get_latest_inventory()
        except AttributeError: 
            current_stock = {}

        target_slot = None
        max_stock = 0
        for slot, data in current_stock.items():
            if data.get('item_name') == recommended_name and data.get('qty', 0) > 0:
                target_slot = slot
                max_stock = data.get('qty', 0)
                recommended_price = data.get('price', recommended_price)
                break
        
        if not target_slot: return

        self.current_recommended_slot = str(target_slot)

        # 2. VẼ GIAO DIỆN
        popup_w, popup_h = 800, 600  # Tăng chiều rộng lên 800 (cũ là 680)
        self.recommendation_overlay = ctk.CTkFrame(
            self.root, width=popup_w, height=popup_h,
            fg_color="#014b91", corner_radius=25, border_width=3, border_color="#FFD700"
        )
        self.recommendation_overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.recommendation_overlay.pack_propagate(False)


        tk.Label(self.recommendation_overlay, text=final_greeting, 
                 font=("Arial", 24, "bold"), bg="#014b91", fg="white", 
                 wraplength=popup_w - 60).pack(pady=(30, 5))
        
        tk.Label(self.recommendation_overlay, text=final_suggest, 
                 font=("Arial", 14, "italic"), bg="#014b91", fg="#e0e0e0", 
                 wraplength=popup_w - 60).pack(pady=(0, 15))

        # 3. HIỂN THỊ ẢNH
        product_id = str(target_slot)
        cached_data = self.controller.cached_product_images.get(product_id)
        if cached_data:
            img_label = ctk.CTkLabel(self.recommendation_overlay, text="", image=cached_data["image"], bg_color="transparent")
            img_label.image = cached_data["image"]
            img_label.pack(pady=5)

        # 4. TÊN & GIÁ (Lưu vào thuộc tính self để lát nữa dễ cập nhật)
        self.rec_name_label = tk.Label(self.recommendation_overlay, text=f"{recommended_name}", 
                 font=("Arial", 28, "bold"), bg="#014b91", fg="#FFD700")
        self.rec_name_label.pack()
        
        self.rec_price_label = tk.Label(self.recommendation_overlay, text=f"{int(recommended_price):,} VNĐ", 
                 font=("Arial", 20), bg="#014b91", fg="white")
        self.rec_price_label.pack(pady=(5, 15))

        # 5. SỐ LƯỢNG & NÚT BẤM
        self.popup_qty = tk.IntVar(value=1)
        qty_frame = tk.Frame(self.recommendation_overlay, bg="#014b91")
        qty_frame.pack(pady=5)
        
        tk.Button(qty_frame, text="-", font=("Arial", 18, "bold"), width=3, bg="#e0e0e0",
                  command=lambda: self.popup_qty.set(max(1, self.popup_qty.get() - 1))).pack(side="left", padx=15)
        
        tk.Label(qty_frame, textvariable=self.popup_qty, font=("Arial", 22, "bold"), 
                 width=4, bg="white", relief="sunken").pack(side="left", padx=10)
        
        tk.Button(qty_frame, text="+", font=("Arial", 18, "bold"), width=3, bg="#e0e0e0",
                  command=lambda: self.popup_qty.set(min(max_stock, self.popup_qty.get() + 1))).pack(side="left", padx=15)

        btn_frame = tk.Frame(self.recommendation_overlay, bg="#014b91")
        btn_frame.pack(pady=25)
        
        ctk.CTkButton(btn_frame, text="MUA LUÔN 🛒", font=("Arial", 22, "bold"), fg_color="#4CAF50", 
                      width=280, height=75, corner_radius=20,
                      command=lambda: self.accept_recommendation(target_slot, recommended_name, self.popup_qty.get())).pack(side="left", padx=20)
        
        ctk.CTkButton(btn_frame, text="ĐỂ SAU NHÉ", font=("Arial", 22, "bold"), fg_color="#555555", 
                      width=280, height=75, corner_radius=20,
                      command=self.close_recommendation_popup).pack(side="right", padx=20)
    def close_recommendation_popup(self):
        """Đóng thông báo và cho phép người dùng chọn món bình thường"""
        if hasattr(self, 'recommendation_overlay'):
            self.recommendation_overlay.destroy()

    def accept_recommendation(self, slot, name, qty):
        """Khách bấm CÓ -> Chọn nhanh sản phẩm rồi đi thẳng vào luồng thanh toán."""
        self.close_recommendation_popup()
        
        # LẤY GIÁ MỚI NHẤT TỪ KHO CỤC BỘ (Source of Truth)
        inventory = self.controller.get_latest_inventory()
        # slot có thể là string hoặc int tùy theo cách lưu trong dict
        product_data = inventory.get(slot) or inventory.get(int(slot))
        
        if not product_data:
            print(f"[UI] Lỗi: Không tìm thấy sản phẩm tại ô {slot} để cập nhật giá.")
            return

        latest_price = product_data.get('price', 0)
        latest_name = product_data.get('item_name', name)
        
        # 1. Giả lập chọn sản phẩm với GIÁ ĐÃ CẬP NHẬT
        product_tuple = (str(slot), latest_name, latest_price)
        self.controller.on_product_select(product_tuple, None)
        
        # 2. Đồng bộ số lượng từ Popup
        safe_qty = min(qty, max(1, self.controller.max_available_quantity))
        self.controller.selected_quantity = safe_qty
        self.controller.quantity_var.set(str(safe_qty))
        
        # 3. Kích hoạt cùng luồng với nút THANH TOÁN
        self.controller.on_ok_handler()
        print(f"[UI] MUA LUÔN: đã chọn {safe_qty} {latest_name} và chuyển sang xác nhận thanh toán.")