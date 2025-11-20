# SHOPPING_KEYPAD_APP/core/ui/confirmation_screen.py

import tkinter as tk
import customtkinter as ctk
import requests
import json

class ConfirmationScreen(tk.Toplevel):
    """
    Màn hình xác nhận đơn hàng, nhập điểm và thanh toán.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Tắt taskbar để full màn hình kiosk
        controller._hide_system_taskbar()
        
        self.title("Xác nhận đơn hàng")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.geometry(f"{screen_width}x{screen_height}+0+0")
        
        # Đảm bảo cửa sổ luôn ở trên cùng
        self.lift()
        self.focus_force()
        
        try:
            self.attributes('-type', 'dock') 
        except tk.TclError: 
            pass # Bỏ qua nếu hệ điều hành không hỗ trợ
            
        self.configure(bg="lightgray")
        
        # Xử lý sự kiện đóng cửa sổ
        self.protocol("WM_DELETE_WINDOW", self._back_and_hide_keyboard)
        self.bind("<Escape>", lambda e: self._back_and_hide_keyboard())

        # --- Giao diện chính ---
        content_frame = tk.Frame(self, width=1500, height=1000, bg="white", relief=tk.RAISED, bd=3)
        content_frame.place(relx=0.5, rely=0.5, anchor="center")
        content_frame.pack_propagate(False)

        # --- Xử lý dữ liệu giỏ hàng ---
        items_summary = {}
        self.total_price = 0
        self.items_for_api = [] # Danh sách chuẩn bị cho API

        # Gom nhóm sản phẩm (Group by ID)
        for item_id in self.controller.logic.get_selected_items():
            name, _, price = self.controller.PRODUCT_IMAGES_CONFIG.get(item_id, ("Sản phẩm lỗi", "", 0))
            if name in items_summary:
                items_summary[name]["count"] += 1
            else:
                items_summary[name] = {"count": 1, "price": price}
            self.total_price += price

        # Tạo danh sách item cho API (Sửa lỗi logic giá)
        for name, data in items_summary.items():
            # FIX: Ép kiểu int cho quantity và price (đơn giá)
            qty = int(data["count"])
            unit_price = int(data['price'])
            
            self.items_for_api.append({
                "name": name, 
                "quantity": qty, 
                "price": unit_price
            })

        # Cấu hình giảm giá
        self.large_order_discount = 2000 if self.total_price > 20000 else 0
        self.customer_points = self.controller.customer_info.get('points', 0) if self.controller.customer_info else 0
        self.point_conversion_rate = 100
        
        # --- Fonts ---
        font_regular = ctk.CTkFont(family="Arial", size=17)
        font_bold = ctk.CTkFont(family="Arial", size=18, weight="bold")
        font_title = ctk.CTkFont(family="Arial", size=38, weight="bold")
        font_total = ctk.CTkFont(family="Arial", size=24, weight="bold")
        font_helper = ctk.CTkFont(family="Arial", size=14, slant="italic")
        
        # Tiêu đề
        ctk.CTkLabel(content_frame, text="Xác nhận Đơn hàng", font=font_title, text_color="#014b91").pack(pady=(40, 20))

        # --- Khu vực nhập điểm ---
        self.points_entry = None
        self.points_to_use_var = tk.StringVar(value=str(self.customer_points)) # Mặc định hiển thị max điểm
        self.points_helper_label = None
        self.default_border_color = None

        if self.customer_points > 0:
            points_input_frame = ctk.CTkFrame(content_frame, fg_color="white")
            points_input_frame.pack(pady=10, padx=25, fill="x")
            
            ctk.CTkLabel(points_input_frame, text="Dùng điểm thanh toán:", font=font_bold, fg_color="white").pack(side="left", padx=(0, 10))
            
            self.points_entry = ctk.CTkEntry(points_input_frame, textvariable=self.points_to_use_var, width=100, font=font_regular, justify='center')
            self.points_entry.pack(side="left")
            self.default_border_color = self.points_entry.cget("border_color")
            
            ctk.CTkLabel(points_input_frame, text=f"/ {self.customer_points} điểm khả dụng", font=font_regular, fg_color="white").pack(side="left", padx=(5, 0))
            
            self.points_helper_label = ctk.CTkLabel(points_input_frame, text="", font=font_helper, text_color="#e67e22", fg_color="white")
            self.points_entry.bind("<KeyRelease>", self._update_summary)

        # --- Danh sách sản phẩm (UI) ---
        items_frame = ctk.CTkScrollableFrame(content_frame, label_text="Chi tiết đơn hàng", label_font=font_bold, height=250)
        items_frame.pack(pady=10, padx=25, fill="x")

        for name, data in items_summary.items():
            item_row = ctk.CTkFrame(items_frame, fg_color="transparent")
            item_row.pack(fill="x", padx=10, pady=4)
            
            total_line_price = data['count'] * data['price']
            ctk.CTkLabel(item_row, text=f"{data['count']}x {name}", font=font_regular).pack(side="left")
            ctk.CTkLabel(item_row, text=f"{total_line_price:,}đ", font=font_regular).pack(side="right")

        # --- Tổng kết tiền ---
        summary_frame = ctk.CTkFrame(items_frame, fg_color="transparent")
        summary_frame.pack(fill="x", padx=10, pady=(15, 5))

        ctk.CTkFrame(summary_frame, height=2, fg_color="gray80").pack(fill="x", pady=(0, 5))
        self.sub_total_frame, self.sub_total_value_label = self._create_summary_line(summary_frame, "Tổng cộng:", font=font_bold)
        self.high_value_frame, self.high_value_discount_label = self._create_summary_line(summary_frame, "Giảm giá đơn hàng lớn:", font=font_bold, is_discount=True)
        self.points_frame_sum, self.points_discount_label = self._create_summary_line(summary_frame, "Giảm giá bằng điểm:", font=font_bold, is_discount=True)
        self.final_separator = ctk.CTkFrame(summary_frame, height=3, fg_color="gray50")
        self.final_total_frame, self.final_total_label = self._create_summary_line(summary_frame, "TỔNG THANH TOÁN:", font=font_total, is_total=True)

        self.sub_total_frame.pack(fill="x", pady=2)
        self.final_separator.pack(fill="x", pady=5)
        self.final_total_frame.pack(fill="x", pady=2)

        # Label báo lỗi
        self.error_label = ctk.CTkLabel(content_frame, text="", font=ctk.CTkFont(size=16), text_color="red")
        self.error_label.pack(pady=(5,0))

        # --- Nút điều khiển ---
        btn_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        btn_frame.pack(side="bottom", pady=25, fill="x", padx=25)
        
        self.back_btn = ctk.CTkButton(btn_frame, text="Quay Lại", font=ctk.CTkFont(size=20, weight="bold"), height=60, fg_color="#7f8c8d", hover_color="#95a5a6", command=self._back_and_hide_keyboard)
        self.back_btn.pack(side="left", expand=True, fill="x", padx=(0, 10))
        
        self.confirm_btn = ctk.CTkButton(btn_frame, text="Xác nhận & Thanh toán", font=ctk.CTkFont(size=20, weight="bold"), height=60, command=self._process_final_payment)
        self.confirm_btn.pack(side="right", expand=True, fill="x", padx=(10, 0))

        # Xử lý bàn phím ảo
        input_widgets = []
        if self.points_entry:
            input_widgets.append(self.points_entry)

        if input_widgets:
            for widget in input_widgets:
                widget.bind("<FocusIn>", self.controller._handle_focus_in) 
                widget.bind("<Return>", lambda e: self.controller._hide_keyboard())
        
        self.bind_all("<Button-1>", self._handle_background_click_local)
        
        # Cập nhật UI lần đầu
        self._update_summary()

    def _handle_background_click_local(self, event):
        if event.widget != self.points_entry:
            self.controller._handle_background_click(event)

    def _create_summary_line(self, parent, label_text, font, is_total=False, is_discount=False):
        line_frame = ctk.CTkFrame(parent, fg_color="transparent")
        text_color = "#2a8a2a" if is_discount else "gray10"
        if is_total: text_color = "#005a9c"
        
        label = ctk.CTkLabel(line_frame, text=label_text, font=font, text_color=text_color)
        label.pack(side="left")
        
        value_label = ctk.CTkLabel(line_frame, text="", font=font, text_color=text_color)
        value_label.pack(side="right")
        
        return line_frame, value_label

    def _update_summary(self, event=None):
        base_price_before_points = self.total_price - self.large_order_discount
        
        # Logic: Tối thiểu phải trả 2000đ (quy định của nhiều cổng thanh toán)
        # Số tiền tối đa có thể giảm bằng điểm
        max_discountable_amount = max(0, base_price_before_points - 2000)
        max_points_to_use_for_order = max_discountable_amount // self.point_conversion_rate
        
        points_to_display = 0
        show_helper_message = False
        helper_message = ""
        is_valid_input = True
        
        if self.customer_points > 0 and self.points_entry:
            try:
                val = self.points_to_use_var.get()
                if not val: val = "0"
                user_input_points = int(val)
                points_to_display = user_input_points
                
                if user_input_points > self.customer_points:
                    is_valid_input = False
                    points_to_display = self.customer_points
                    # Không set lại var ngay để người dùng sửa, chỉ tính toán theo max
                    helper_message = f"Bạn chỉ có {self.customer_points} điểm."
                    show_helper_message = True
                elif user_input_points > max_points_to_use_for_order:
                    # Cho phép nhập, nhưng sẽ cảnh báo lúc thanh toán hoặc tự sửa
                    # Ở đây để trải nghiệm tốt, ta chỉ cảnh báo
                    helper_message = "Thanh toán tối thiểu 2,000đ."
                    show_helper_message = True
            except (ValueError, TypeError):
                is_valid_input = False
                points_to_display = 0
            
            if is_valid_input:
                self.points_entry.configure(border_color=self.default_border_color)
            else:
                self.points_entry.configure(border_color="#e74c3c")
            
            if show_helper_message and self.points_helper_label:
                self.points_helper_label.configure(text=helper_message)
                self.points_helper_label.pack(side="left", padx=(15, 0), pady=(2,0), anchor="w")
            elif self.points_helper_label:
                self.points_helper_label.pack_forget()

        points_discount_value = points_to_display * self.point_conversion_rate
        # Đảm bảo không âm
        final_total = max(0, self.total_price - self.large_order_discount - points_discount_value)
        
        self.sub_total_value_label.configure(text=f"{self.total_price:,.0f}đ")
        self.final_total_label.configure(text=f"{final_total:,.0f}đ")
        
        if self.large_order_discount > 0:
            self.high_value_discount_label.configure(text=f"-{self.large_order_discount:,.0f}đ")
            self.high_value_frame.pack(before=self.final_separator, fill="x", pady=2)
        else:
            self.high_value_frame.pack_forget()
            
        if points_discount_value > 0:
            self.points_discount_label.configure(text=f"-{points_discount_value:,.0f}đ")
            self.points_frame_sum.pack(before=self.final_separator, fill="x", pady=2)
        else:
            self.points_frame_sum.pack_forget()

    def _process_final_payment(self):
        self.controller._hide_keyboard()
        self.confirm_btn.configure(state="disabled", text="Đang xử lý...")
        self.back_btn.configure(state="disabled")
        self.error_label.configure(text="")
        self.update()

        # --- 1. Tính toán số tiền cuối cùng (Logic backend) ---
        base_price_before_points = self.total_price - self.large_order_discount
        
        # Ràng buộc tối thiểu 2000đ
        max_discountable_amount = max(0, base_price_before_points - 2000)
        max_points_to_use = max_discountable_amount // self.point_conversion_rate
        
        points_to_use_for_payment = 0
        
        if self.customer_points > 0 and self.points_entry:
            try:
                user_input_points = int(self.points_to_use_var.get())
                # Lấy min của (nhập vào, số dư, số tối đa được dùng)
                points_to_use_for_payment = min(user_input_points, self.customer_points, max_points_to_use)
                points_to_use_for_payment = max(0, points_to_use_for_payment)
            except (ValueError, TypeError):
                points_to_use_for_payment = 0
        
        # Lưu vào controller để trừ điểm sau khi thành công
        self.controller.points_used_in_transaction = points_to_use_for_payment
        
        points_discount = points_to_use_for_payment * self.point_conversion_rate
        amount_to_pay_float = self.total_price - self.large_order_discount - points_discount
        
        # Đảm bảo tối thiểu 2000đ nếu tổng ban đầu >= 2000
        if base_price_before_points >= 2000:
            amount_to_pay_float = max(2000, amount_to_pay_float)
        else:
            # Trường hợp hiếm sản phẩm < 2000đ
            amount_to_pay_float = base_price_before_points

        # FIX: Ép kiểu int (quan trọng cho PayOS)
        final_amount = int(amount_to_pay_float)

        # --- 2. Chuẩn bị Payload gửi API ---
        # FIX: PayOS yêu cầu tổng items == amount.
        # Nếu có giảm giá, danh sách item chi tiết sẽ có tổng > final_amount -> Gây lỗi.
        # Giải pháp: Nếu có giảm giá, gửi 1 item đại diện.
        
        items_total_raw = sum(item['price'] * item['quantity'] for item in self.items_for_api)
        
        api_items_payload = []
        if items_total_raw == final_amount:
            # Giá khớp nhau (không giảm giá), gửi chi tiết
            api_items_payload = self.items_for_api
        else:
            # Có lệch giá (do giảm giá/điểm), gửi item gộp
            print(f"UI: Phát hiện lệch giá (Gốc: {items_total_raw}, Trả: {final_amount}). Dùng item gộp.")
            customer_name_display = self.controller.customer_name or "Khách"
            api_items_payload = [{
                "name": f"Thanh toán đơn hàng ({customer_name_display})",
                "quantity": 1,
                "price": final_amount
            }]

        payload = {
            "name": self.controller.customer_name or "Khách hàng",
            "amount": final_amount,
            "items": api_items_payload
        }
        
        print(f"UI: Đang gửi request thanh toán: {json.dumps(payload, ensure_ascii=False)}")

        # --- 3. Gọi API ---
        try:
            response = requests.post(
                "http://localhost:5000/create-payment-link", 
                json=payload, 
                timeout=10
            )
            
            # Xử lý phản hồi
            try:
                resp_json = response.json()
            except Exception:
                # Nếu server trả về HTML lỗi (500) thì json() sẽ fail
                resp_json = {}
                
            if response.status_code != 200:
                # Lấy thông báo lỗi từ server nếu có
                msg = resp_json.get("error") or resp_json.get("message") or f"Mã lỗi {response.status_code}"
                raise ValueError(f"Server từ chối: {msg}")

            payment_link = resp_json.get("checkoutUrl")
            if not payment_link: 
                raise ValueError("Server không trả về link thanh toán.")
            
            # Thành công
            self.controller._open_browser_kiosk_mode(payment_link)
            self.destroy() 
            return
            
        except requests.exceptions.Timeout:
            self.error_label.configure(text="⏰ Hết thời gian chờ server.")
        except requests.exceptions.ConnectionError:
            self.error_label.configure(text="🔌 Không thể kết nối tới Backend (Port 5000).")
        except Exception as e:
            print(f"UI Error Details: {e}")
            self.error_label.configure(text=f"❌ Lỗi: {str(e)}")

        # Nếu thất bại, mở lại nút
        self.confirm_btn.configure(state="normal", text="Xác nhận & Thanh toán")
        self.back_btn.configure(state="normal")

    def _back_and_hide_keyboard(self):
        self.controller._hide_keyboard()
        self.controller.root.deiconify()
        self.destroy()