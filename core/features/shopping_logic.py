# SHOPPING_KEYPAD_APP/core/features/shopping_logic.py

from config import PRODUCT_IMAGES_CONFIG

class ShoppingLogic:
    def __init__(self):
        # [QUAN TRỌNG] Chỉ sử dụng duy nhất biến self.cart để chứa hàng
        # Mỗi item là dict: {'id', 'name', 'price', 'quantity', 'total'}
        self.cart = [] 
        
        self.current_entry_buffer = "" 
        self.current_customer = None 
        self.customer_update_callback = None 
        # Biến cờ hỗ trợ logic cũ (nếu cần), nhưng logic chính giờ dựa vào self.cart
        self.is_first_item_after_reset = True 

    def set_customer(self, customer_data):
        """Lưu thông tin khách hàng đang đăng nhập"""
        self.current_customer = customer_data
        if self.customer_update_callback:
            self.customer_update_callback(customer_data)
        
        # Debug log
        name = customer_data.get('name', 'N/A') if customer_data else "Vãng lai"
        print(f"ShoppingLogic: Khách hàng -> {name}")

    def get_customer(self):
        return self.current_customer

    def reset_customer(self):
        self.set_customer(None)

    def customer_update_callback(self, callback):
        self.customer_update_callback = callback

    def add_item_from_entry(self, override_price=None):
        """
        Thêm sản phẩm vào giỏ hàng.
        :param override_price: Giá lấy từ Database (ưu tiên dùng). Nếu None thì dùng giá Config.
        """
        product_id = self.current_entry_buffer
        
        # 1. Kiểm tra ID sản phẩm có trong Config không (để lấy Tên và Ảnh)
        if product_id in PRODUCT_IMAGES_CONFIG:
            # [cite_start]Lấy thông tin từ Config [cite: 58-59]
            # PRODUCT_IMAGES_CONFIG structure: key -> (Name, Image, DefaultPrice)
            product_info = PRODUCT_IMAGES_CONFIG[product_id]
            
            # Xử lý an toàn nếu config có 2 hoặc 3 phần tử
            if len(product_info) == 3:
                name, img_file, default_price = product_info
            else:
                name, img_file = product_info
                default_price = 0

            # [cite_start]2. XÁC ĐỊNH GIÁ BÁN (Ưu tiên giá từ DB truyền vào) [cite: 63-67]
            if override_price is not None:
                final_price = float(override_price)
            else:
                final_price = float(default_price)

            # 3. Thêm vào giỏ hàng (Gộp nếu đã có)
            found = False
            for item in self.cart:
                # So sánh theo ID sản phẩm
                if item['id'] == product_id:
                    item['quantity'] += 1
                    item['price'] = final_price # Cập nhật giá mới nhất (nếu DB đổi)
                    item['total'] = item['quantity'] * final_price
                    found = True
                    break
            
            if not found:
                self.cart.append({
                    'id': product_id,
                    'name': name,
                    'price': final_price,
                    'quantity': 1,
                    'total': final_price
                })
            
            # Reset buffer
            self.current_entry_buffer = ""
            return True, f"Đã thêm {name}", self.cart
        else:
            return False, "Mã sản phẩm không hợp lệ", self.cart

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