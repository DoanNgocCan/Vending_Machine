# --- START OF FILE core/features/api_manager.py (Đã cập nhật) ---
import requests
import logging 
from datetime import datetime

# Đảm bảo IP và Port là chính xác
SERVER_URL = "https://rpi.vietseedscampaign.com"  # Dùng IP của server nếu chạy trên máy khác
API_HEADERS = {
    'Content-Type': 'application/json',
    'X-Device-ID': 'VENDING_001' # Thêm header này nếu server yêu cầu
}

class VendingAPIManager:
    def get_all_products(self):
        endpoint = f"{SERVER_URL}/api/products"
        try:
            response = requests.get(endpoint, headers=API_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                logging.info(f"API: Lấy thành công {len(data['products'])} sản phẩm.")
                return {p['product_id']: p for p in data['products']}
            return None
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi lấy sản phẩm: {e}")
            return None

    def get_customer_by_id(self, user_id):
        endpoint = f"{SERVER_URL}/api/user/{user_id}"
        try:
            response = requests.get(endpoint, headers=API_HEADERS, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get('user')
            # Trả về None nếu user không tồn tại (404) hoặc có lỗi
            return None
        except requests.RequestException:
            return None
        
    def register_customer(self, full_name, phone_number, birthday, password, user_id):
        endpoint = f"{SERVER_URL}/api/user/register"
        payload = {
            "full_name": full_name,
            "phone_number": phone_number,
            "birthday": birthday,
            "password": password,
            "user_id": user_id
        }
        try:
            response = requests.post(endpoint, json=payload, headers=API_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                return {"code": data['user_id'], "name": full_name, "phone": phone_number, "points": 0}
            logging.error(f"API: Đăng ký thất bại. Server: {data.get('message')}")
            return None
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi đăng ký: {e}")
            return None
    def login_customer(self, phone_number, password):
        """
        Gửi yêu cầu đăng nhập đến server.
        API: POST /api/user/login
        """
        endpoint = f"{SERVER_URL}/api/user/login"
        payload = {"phone_number": phone_number, "password": password}
        try:
            response = requests.post(endpoint, json=payload, headers=API_HEADERS, timeout=15)
            # API trả về 200 OK nếu thành công, 401 Unauthorized nếu thất bại
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    logging.info(f"API: Đăng nhập thành công cho SĐT {phone_number}")
                    return data.get('user')  # Trả về object user chứa user_id, full_name, points
            
            # Các trường hợp khác (status code khác 200 hoặc success=false) đều là thất bại
            logging.warning(f"API: Đăng nhập thất bại. Status: {response.status_code}, Body: {response.text}")
            return None
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi đăng nhập: {e}")
            return None

    def report_transaction(self, total_amount, items_list, customer_info=None):
        endpoint = f"{SERVER_URL}/api/transactions/record"
        payload = {
            "total_amount": total_amount,
            "customer_info": customer_info,
            "items": items_list
        }
        try:
            response = requests.post(endpoint, json=payload, headers=API_HEADERS, timeout=20)
            response.raise_for_status()
            data = response.json()
            return data.get("success", False)
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi đồng bộ giao dịch: {e}")
            return False

api_manager = VendingAPIManager()
# --- END OF FILE core/features/api_manager.py ---