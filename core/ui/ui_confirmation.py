# SHOPPING_KEYPAD_APP/core/ui/confirmation_screen.py

import time
import tkinter as tk
import customtkinter as ctk
import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
PAYMENT_API_URL = os.getenv("PAYMENT_API_URL", "http://localhost:5000/create-payment-link")

class ConfirmationScreen(tk.Toplevel):
    """
    Màn hình xác nhận đơn hàng với giao diện một cột, thanh gạt dùng điểm phong cách Shopee.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.controller.stop_camera_service()
        
        self.title("Xác nhận đơn hàng")
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
        
        # Xử lý sự kiện đóng cửa sổ
        self.protocol("WM_DELETE_WINDOW", self._back_to_main)
        self.bind("<Escape>", lambda e: self._back_to_main())

        # --- Giao diện chính (Container) ---
        content_frame = tk.Frame(self, width=1200, height=1030, bg="white", relief=tk.RAISED, bd=3)
        content_frame.place(relx=0.5, rely=0.5, anchor="center")
        content_frame.pack_propagate(False)

        # --- Xử lý dữ liệu giỏ hàng ---
        cart_items = self.controller.logic.get_selected_items()
        items_summary = {}
        self.total_price = 0
        self.items_for_api = []

        for item in cart_items:
            name = item['name']
            qty = item['quantity']
            price = int(item['price']) 
            total_item_price = int(item['total'])
            self.total_price += total_item_price
            items_summary[name] = {"count": qty, "price": price}
            self.items_for_api.append({"name": name, "quantity": qty, "price": price})

        # Cấu hình giảm giá & điểm
        self.large_order_discount = 2000 if self.total_price > 20000 else 0
        self.customer_points = self.controller.customer_info.get('points', 0) if self.controller.customer_info else 0
        self.point_conversion_rate = 100
        
        # --- Fonts ---
        font_regular = ctk.CTkFont(family="Arial", size=20)
        font_bold = ctk.CTkFont(family="Arial", size=19, weight="bold")
        font_title = ctk.CTkFont(family="Arial", size=42, weight="bold")
        font_total = ctk.CTkFont(family="Arial", size=26, weight="bold")
        font_helper = ctk.CTkFont(family="Arial", size=19, slant="italic")
        
        # 1. Tiêu đề
        ctk.CTkLabel(content_frame, text="Xác nhận Đơn hàng", font=font_title, text_color="#014b91").pack(pady=(15, 15))

        # 2. PHẦN DÙNG ĐIỂM (HIỆN TRÊN CÙNG)
        self.use_points_var = tk.BooleanVar(value=False)
        if self.customer_points > 0:
            base_price = self.total_price - self.large_order_discount
            # Điều kiện: Giảm tối đa 50% và phải còn ít nhất 2000đ cho PayOS
            max_discount_50_pct = base_price * 0.5
            max_discount_payos = max(0, base_price - 2000)
            max_discount_money = min(max_discount_50_pct, max_discount_payos)
            max_points_allowed = int(max_discount_money // self.point_conversion_rate)
            points_to_use = min(self.customer_points, max_points_allowed)

            if points_to_use > 0:
                discount_value = points_to_use * self.point_conversion_rate
                
                point_frame = ctk.CTkFrame(content_frame, fg_color="#f8f9fa", corner_radius=15, border_width=1, border_color="#e0e0e0")
                point_frame.pack(fill="x", padx=60, pady=(5, 5), ipady=12)

                self.points_switch = ctk.CTkSwitch(
                    point_frame,
                    text=f"Sử dụng {points_to_use} điểm để được giảm {discount_value:,.0f}đ (Số dư: {self.customer_points} điểm)",
                    font=font_bold,
                    variable=self.use_points_var,
                    command=self._update_summary,
                    switch_width=60,
                    switch_height=25,
                    progress_color="#014b91" 
                )
                self.points_switch.pack(anchor="center")
                ctk.CTkLabel(point_frame, text="*Áp dụng giảm tối đa 50% giá trị đơn hàng", font=font_helper, text_color="#e62222").pack()

        # 3. CHI TIẾT ĐƠN HÀNG (FULL WIDTH)
        # Chiều cao 480 giúp hiện đủ 10-12 món mà không cần lăn chuột
        items_frame = ctk.CTkScrollableFrame(content_frame, label_text="Chi tiết sản phẩm", label_font=font_bold, height=410)
        items_frame.pack(fill="x", padx=60, pady=10)

        for name, data in items_summary.items():
            item_row = ctk.CTkFrame(items_frame, fg_color="transparent")
            item_row.pack(fill="x", padx=25, pady=6)
            
            total_line_price = data['count'] * data['price']
            ctk.CTkLabel(item_row, text=f"{data['count']}x {name}", font=font_regular).pack(side="left")
            ctk.CTkLabel(item_row, text=f"{total_line_price:,}đ", font=font_bold).pack(side="right")

        # 4. BẢNG TỔNG KẾT (FULL WIDTH)
        summary_frame = ctk.CTkFrame(content_frame, fg_color="#f1f2f6", corner_radius=12)
        summary_frame.pack(fill="x", padx=60, pady=10, ipadx=20, ipady=10)

        self.sub_total_frame, self.sub_total_value_label = self._create_summary_line(summary_frame, "Tổng cộng giá gốc:", font=font_bold)
        self.high_value_frame, self.high_value_discount_label = self._create_summary_line(summary_frame, "Ưu đãi đơn hàng lớn:", font=font_helper, is_discount=True)
        self.points_frame_sum, self.points_discount_label = self._create_summary_line(summary_frame, "Giảm giá tích điểm:", font=font_helper, is_discount=True)
        self.final_separator = ctk.CTkFrame(summary_frame, height=2, fg_color="gray60")
        self.final_total_frame, self.final_total_label = self._create_summary_line(summary_frame, "TỔNG THANH TOÁN:", font=font_total, is_total=True)

        self.sub_total_frame.pack(fill="x", pady=2)
        self.final_separator.pack(fill="x", pady=6)
        self.final_total_frame.pack(fill="x", pady=2)

        # --- HIỂN THỊ ĐIỂM TÍCH LŨY ---
        self.earn_points_label = ctk.CTkLabel(summary_frame, text="", font=ctk.CTkFont(family="Arial", size=18, slant="italic"), text_color="#27ae60") # Màu xanh lá cây bắt mắt
        self.earn_points_label.pack(fill="x", pady=(5, 0))

        # Label báo lỗi
        self.error_label = ctk.CTkLabel(content_frame, text="", font=font_helper, text_color="#e74c3c")
        self.error_label.pack(pady=5)

        # 5. NÚT ĐIỀU KHIỂN
        btn_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=15, fill="x", padx=60)
        
        self.back_btn = ctk.CTkButton(btn_frame, text="Quay Lại", font=ctk.CTkFont(size=22, weight="bold"), height=65, fg_color="#7f8c8d", hover_color="#95a5a6", command=self._back_to_main)
        self.back_btn.pack(side="left", expand=True, fill="x", padx=(0, 15))
        
        self.confirm_btn = ctk.CTkButton(btn_frame, text="Xác nhận & Thanh toán", font=ctk.CTkFont(size=22, weight="bold"), height=65, command=self._process_final_payment)
        self.confirm_btn.pack(side="right", expand=True, fill="x", padx=(15, 0))
        
        self._update_summary()

    def _create_summary_line(self, parent, label_text, font, is_total=False, is_discount=False):
        line_frame = ctk.CTkFrame(parent, fg_color="transparent")
        text_color = "#d35400" if is_discount else "gray10" # Màu cam đậm cho giảm giá
        if is_total: text_color = "#014b91"
        
        label = ctk.CTkLabel(line_frame, text=label_text, font=font, text_color=text_color)
        label.pack(side="left")
        value_label = ctk.CTkLabel(line_frame, text="", font=font, text_color=text_color)
        value_label.pack(side="right")
        return line_frame, value_label

    def _update_summary(self, event=None):
        base_price_before_points = self.total_price - self.large_order_discount
        points_discount_value = 0
        
        if self.use_points_var.get():
            max_discount_50_pct = base_price_before_points * 0.5
            max_discount_payos = max(0, base_price_before_points - 2000)
            max_discount_money = min(max_discount_50_pct, max_discount_payos)

            max_points_allowed = int(max_discount_money // self.point_conversion_rate)
            actual_points_used = min(self.customer_points, max_points_allowed)
            points_discount_value = actual_points_used * self.point_conversion_rate

        final_total = max(0, base_price_before_points - points_discount_value)

        self.sub_total_value_label.configure(text=f"{self.total_price:,.0f}đ")
        self.final_total_label.configure(text=f"{final_total:,.0f}đ")
        
        if self.large_order_discount > 0:
            self.high_value_discount_label.configure(text=f"-{self.large_order_discount:,.0f}đ")
            self.high_value_frame.pack(before=self.final_separator, fill="x", pady=2)
        else:
            self.high_value_frame.pack_forget()
        
        points_earned = int(final_total // 1000) 
        
        # Chỉ hiển thị nếu khách có đăng nhập (tức là customer_info tồn tại)
        if self.controller.customer_info and points_earned > 0:
            self.earn_points_label.configure(text=f"🎁 Bạn sẽ tích lũy thêm {points_earned} điểm từ đơn hàng này!")
        else:
            self.earn_points_label.configure(text="")
            
        self.update_idletasks()

        if points_discount_value > 0:
            self.points_discount_label.configure(text=f"-{points_discount_value:,.0f}đ")
            self.points_frame_sum.pack(before=self.final_separator, fill="x", pady=2)
        else:
            self.points_frame_sum.pack_forget()
        self.update_idletasks()

    def _process_final_payment(self):
        self.confirm_btn.configure(state="disabled", text="Đang khởi tạo...")
        self.back_btn.configure(state="disabled")
        self.error_label.configure(text="")
        self.update()

        base_price_before_points = self.total_price - self.large_order_discount
        points_to_use_for_payment = 0
        
        if self.use_points_var.get():
            max_discount_50_pct = base_price_before_points * 0.5
            max_discount_payos = max(0, base_price_before_points - 2000)
            max_discount_money = min(max_discount_50_pct, max_discount_payos)
            max_points_allowed = int(max_discount_money // self.point_conversion_rate)
            points_to_use_for_payment = min(self.customer_points, max_points_allowed)
        
        self.controller.points_used_in_transaction = points_to_use_for_payment
        points_discount = points_to_use_for_payment * self.point_conversion_rate
        final_amount = int(max(0, base_price_before_points - points_discount))
        
        if base_price_before_points >= 2000:
            final_amount = max(2000, final_amount)

        items_total_raw = sum(item['price'] * item['quantity'] for item in self.items_for_api)
        api_items_payload = []
        if items_total_raw == final_amount:
            api_items_payload = self.items_for_api
        else:
            customer_name_display = self.controller.customer_name or "Khách"
            api_items_payload = [{
                "name": f"Đơn hàng từ {customer_name_display}",
                "quantity": 1,
                "price": final_amount
            }]

        payload = {
            "name": self.controller.customer_name or "Khách hàng",
            "amount": final_amount,
            "items": api_items_payload
        }

        try:
            response = requests.post(PAYMENT_API_URL, json=payload, timeout=10)
            resp_json = response.json() if response.status_code == 200 else {}
                
            if response.status_code != 200:
                msg = resp_json.get("error") or f"Lỗi kết nối ({response.status_code})"
                raise ValueError(msg)

            payment_link = resp_json.get("checkoutUrl")
            if not payment_link: raise ValueError("Không nhận được link thanh toán.")
            
            self.controller._open_browser_kiosk_mode(payment_link)
            time.sleep(2)
            self.destroy() 
            return
            
        except Exception as e:
            self.error_label.configure(text=f"❌ {str(e)}")
            self.confirm_btn.configure(state="normal", text="Xác nhận & Thanh toán")
            self.back_btn.configure(state="normal")

    def _back_to_main(self):
        self.controller.root.deiconify()
        self.destroy()