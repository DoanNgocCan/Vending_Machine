# SHOPPING_KEYPAD_APP/core/features/shopping_logic.py

class ShoppingLogic:
    def __init__(self):
        self.selected_items = []
        self.is_first_item_after_reset = True
        self.current_entry_buffer = "" # Bộ đệm cho số đang nhập
        self.current_customer = None  # Thêm thuộc tính để lưu thông tin khách hàng
        self.customer_update_callback = None  # Thêm thuộc tính callback
    def reset_customer(self):
        """
        Đặt lại thông tin khách hàng về trạng thái vãng lai (None).
        Hàm này sẽ được gọi khi thanh toán thành công hoặc khi reset giỏ hàng.
        """
        self.set_customer(None)
    def customer_update_callback(self, callback):
        """
        UI đăng ký hàm này để được thông báo khi khách hàng thay đổi.
        Ví dụ: để cập nhật lời chào "Xin chào, [Tên]".
        """
        self.customer_update_callback = callback

    def set_customer(self, customer_data):
        """
        Được gọi từ UI sau khi đăng ký hoặc "nhận diện" thành công.
        :param customer_data: Một dictionary chứa thông tin khách hàng, hoặc None.
        """
        self.current_customer = customer_data
        
        # In ra console để debug
        if customer_data:
            print(f"ShoppingLogic: Khách hàng được đặt thành -> {customer_data.get('name', 'N/A')}")
        else:
            print("ShoppingLogic: Khách hàng được reset về trạng thái vãng lai.")
        
        # Kích hoạt callback để thông báo cho UI về sự thay đổi này
        if self.customer_update_callback:
            self.customer_update_callback(self.current_customer)

    def get_customer(self):
        """
        Lấy thông tin khách hàng hiện tại.
        Hàm này sẽ được payment_handler.py sử dụng để ghi log và cộng điểm.
        """
        return self.current_customer

    
    def process_number_input(self, number_char):
        self.current_entry_buffer += str(number_char)
        return self.current_entry_buffer

    def get_current_entry(self):
        return self.current_entry_buffer

    def clear_last_char_entry(self):
        self.current_entry_buffer = self.current_entry_buffer[:-1]
        return self.current_entry_buffer

    def clear_current_entry(self):
        self.current_entry_buffer = ""

    def add_item_from_entry(self):
        """
        Thêm sản phẩm từ current_entry_buffer vào giỏ hàng.
        Trả về (bool: thành công, str: thông báo/sản phẩm đã thêm, list: giỏ hàng hiện tại)
        """
        item_str = self.current_entry_buffer
        self.clear_current_entry() # Xóa buffer sau khi lấy giá trị

        if not item_str:
            return False, "Vui lòng nhập mã sản phẩm.", self.selected_items

        # Kiểm tra xem item_str có phải là product_id hợp lệ không
        from config import PRODUCT_IMAGES_CONFIG
        if item_str not in PRODUCT_IMAGES_CONFIG:
            return False, f"Mã sản phẩm '{item_str}' không tồn tại.", self.selected_items

        self.selected_items.append(item_str)
        self.is_first_item_after_reset = False
        return True, f"Đã thêm: {item_str}", self.selected_items

    def get_selected_items(self):
        return list(self.selected_items) # Trả về bản sao
    def get_total_price(self):
        """
        Tính và trả về tổng giá tiền của tất cả các sản phẩm trong giỏ hàng.
        """
        from config import PRODUCT_IMAGES_CONFIG
        total_price = 0
        for item_id in self.selected_items:
            # Lấy giá từ config, nếu không tìm thấy sản phẩm thì giá là 0
            # Cấu trúc tuple là (name, image_file, price)
            _, _, price = PRODUCT_IMAGES_CONFIG.get(item_id, (None, None, 0))
            total_price += price
        return total_price

    def process_ok_action(self):
        """
        Xử lý logic khi nhấn nút OK.
        Trả về (str: thông báo cho UI, bool: có nên reset không, list: giỏ hàng)
        """
        item_added_in_ok = False
        message = ""

        if self.is_first_item_after_reset:
            if self.current_entry_buffer: # Nếu có gì đó trong buffer
                success, msg_or_item, _ = self.add_item_from_entry()
                if success:
                    print(f"Sản phẩm đã chọn (qua OK): {msg_or_item.split(': ')[-1]}")
                    message = f"OK: {msg_or_item}"
                    item_added_in_ok = True
                else: # Thêm thất bại (số không hợp lệ)
                    message = f"OK Lỗi: {msg_or_item}"
                    return message, False, self.selected_items # Không reset, chỉ báo lỗi
            else: # Không nhập gì mà nhấn OK lần đầu
                message = "Vui lòng nhập sản phẩm."
                return message, False, self.selected_items # Không reset, chỉ báo lỗi

        # Nếu không phải lần đầu, hoặc lần đầu nhưng đã thêm được sản phẩm
        if not self.is_first_item_after_reset or item_added_in_ok:
            if self.selected_items:
                print("Hoàn tất chọn. Sản phẩm đã chọn: ", self.selected_items)
                message = "OK: Hoàn tất! Sản phẩm: " + ", ".join(self.selected_items)
                return message, True, self.selected_items # Reset sau khi OK thành công
            else:
                # Trường hợp này ít xảy ra nếu is_first_item_after_reset đúng
                message = "Chưa có sản phẩm nào để OK."
                return message, False, self.selected_items # Không reset

        # Mặc định (nếu không rơi vào các trường hợp trên)
        return message, False, self.selected_items

    def reset_all(self):
        """
        Reset giỏ hàng, trạng thái.
        Trả về (str: thông báo, list: giỏ hàng rỗng)
        """
        self.selected_items.clear()
        self.clear_current_entry()
        self.is_first_item_after_reset = True
        # Reset thông tin khách hàng về None (khách vãng lai)
        self.current_customer = None
        return "Đã reset giỏ hàng.", self.selected_items

    def close_resources(self):
        """Được gọi khi ứng dụng đóng."""
        pass
