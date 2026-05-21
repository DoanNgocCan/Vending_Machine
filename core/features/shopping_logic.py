# SHOPPING_KEYPAD_APP/core/features/shopping_logic.py

class ShoppingLogic:
    def __init__(self):
        # [QUAN TRỌNG] Chỉ sử dụng duy nhất biến self.cart để chứa hàng
        # Mỗi item là dict: {'id', 'name', 'price', 'quantity', 'total'}
        self.cart = [] 
        
        self.current_entry_buffer = "" 
        self.current_customer = None 
        self._customer_update_callback = None 
        # Biến cờ hỗ trợ logic cũ (nếu cần), nhưng logic chính giờ dựa vào self.cart
        self.is_first_item_after_reset = True 

    def set_customer(self, customer_data):
        """Lưu thông tin khách hàng đang đăng nhập"""
        self.current_customer = customer_data
        if self._customer_update_callback:
            self._customer_update_callback(customer_data)
        
        # Debug log
        name = customer_data.get('name', 'N/A') if customer_data else "Vãng lai"
        print(f"ShoppingLogic: Khách hàng -> {name}")

    def get_customer(self):
        return self.current_customer

    def reset_customer(self):
        self.set_customer(None)

    def customer_update_callback(self, callback):
        self._customer_update_callback = callback

    def calculate_total(self):
        """Tính tổng tiền dựa trên self.cart"""
        return sum(item['total'] for item in self.cart)
    
    # Alias cho calculate_total để tương thích code cũ nếu có
    def get_total_price(self):
        return self.calculate_total()

    def get_cart_items(self):
        """Trả về danh sách giỏ hàng"""
        return self.cart
        
    # [QUAN TRỌNG] Hàm này để tương thích với UI Controller cũ đang gọi
    def get_selected_items(self):
        return self.cart

    def clear_cart(self):
        """Xóa giỏ hàng"""
        self.cart = [] # Reset về list rỗng
        self.current_entry_buffer = ""
        return "Giỏ hàng đã được xóa.", []
    
    # Hỗ trợ logic reset cũ
    def reset_all(self):
        self.clear_cart()
        self.reset_customer()
        return "Đã reset.", []

    def start_new_session(self):
        """Bắt đầu phiên mới"""
        self.clear_cart()
        self.reset_customer()
        
    def close_resources(self):
        pass
    
    # Các hàm hỗ trợ nhập liệu keypad (nếu dùng)
    def process_number_input(self, char):
        self.current_entry_buffer += str(char)
        return self.current_entry_buffer
    
    def clear_current_entry(self):
        self.current_entry_buffer = ""

    def auto_login_after_register(self, user_id, name, phone):
        """
        Được gọi ngay sau khi đăng ký thành công ở màn UI.
        Tự động thiết lập phiên mua sắm cho khách hàng mới để họ mua hàng được ngay.
        """
        customer_data = {
            'code': user_id,     # Mã UID của hệ thống
            'name': name,        
            'phone': phone,
            'points': 0          # Khách mới đăng ký chưa có điểm
        }
        self.set_customer(customer_data)
        return True