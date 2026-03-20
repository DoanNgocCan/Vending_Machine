# --- START OF FILE core/features/api_manager.py (Updated for Multi-Client) ---
import requests
import logging
import os
from datetime import datetime

# --- CẤU HÌNH ---
SERVER_URL = "http://192.168.1.5:5000"  # Thay bằng IP thật nếu server chạy trên máy khác. Giữ nguyên nếu server chạy cùng máy.
# QUAN TRỌNG: Đây là tên định danh của máy này. Mỗi máy phải có ID khác nhau.
DEVICE_ID = "VENDING_MACHINE_01" 

API_HEADERS = {
    'Content-Type': 'application/json',
    'X-Device-ID': DEVICE_ID  # Server sẽ dựa vào đây để biết trừ kho máy nào
}

class VendingAPIManager:
    def get_all_products(self):
        """
        Lấy danh sách sản phẩm và tồn kho dành riêng cho máy này.
        """
        endpoint = f"{SERVER_URL}/api/products"
        try:
            # Header đã có X-Device-ID, Server sẽ trả về đúng tồn kho của máy này
            response = requests.get(endpoint, headers=API_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                logging.info(f"API: Lấy thành công {len(data['products'])} sản phẩm cho thiết bị {DEVICE_ID}.")
                # Trả về dict với key là item_name để dễ truy xuất
                return {p['item_name']: p for p in data['products']}
            return None
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi lấy sản phẩm: {e}")
            return None

    def get_product_by_id(self, product_id):
        """
        Lấy thông tin đầy đủ của một sản phẩm theo ID từ server.
        Dùng khi nhận tín hiệu MQTT data_changed để lấy dữ liệu mới nhất (bao gồm image_url).
        """
        endpoint = f"{SERVER_URL}/api/products/{product_id}"
        try:
            response = requests.get(endpoint, headers=API_HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get("success"):
                logging.info(f"API: Lấy thành công thông tin sản phẩm ID={product_id}.")
                return data.get('product')
            logging.warning(f"API: Server trả về thất bại cho sản phẩm ID={product_id}: {data.get('message')}")
            return None
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi lấy sản phẩm ID={product_id}: {e}")
            return None

    def download_product_image(self, image_url, item_name):
        """
        Tải ảnh sản phẩm từ server về thư mục images/ cục bộ.
        Trả về đường dẫn file cục bộ nếu thành công, None nếu thất bại.
        """
        if not image_url:
            return None

        try:
            from config import IMAGE_BASE_PATH
            images_dir = IMAGE_BASE_PATH.rstrip(os.sep)
            os.makedirs(images_dir, exist_ok=True)

            # Lấy tên file từ URL hoặc dùng item_name làm tên file
            url_filename = image_url.split('/')[-1].split('?')[0]
            if url_filename and '.' in url_filename:
                local_filename = url_filename
            else:
                # Chuẩn hóa tên file từ item_name
                safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in item_name)
                local_filename = f"{safe_name}.png"

            local_path = os.path.join(images_dir, local_filename)

            # Tải ảnh nếu chưa có hoặc để cập nhật
            response = requests.get(image_url, timeout=30, stream=True)
            response.raise_for_status()

            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logging.info(f"API: Đã tải ảnh '{item_name}' về {local_path}.")
            return local_path

        except requests.RequestException as e:
            logging.error(f"API: Lỗi tải ảnh '{item_name}' từ {image_url}: {e}")
            return None
        except OSError as e:
            logging.error(f"API: Lỗi ghi file ảnh '{item_name}': {e}")
            return None

    def get_customer_by_id(self, user_id):
        endpoint = f"{SERVER_URL}/api/user/{user_id}"
        try:
            response = requests.get(endpoint, headers=API_HEADERS, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    return data.get('user')
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
        endpoint = f"{SERVER_URL}/api/user/login"
        payload = {"phone_number": phone_number, "password": password}
        try:
            response = requests.post(endpoint, json=payload, headers=API_HEADERS, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    logging.info(f"API: Đăng nhập thành công cho SĐT {phone_number}")
                    return data.get('user')
            
            logging.warning(f"API: Đăng nhập thất bại. Status: {response.status_code}")
            return None
        except requests.RequestException as e:
            logging.error(f"API: Lỗi mạng khi đăng nhập: {e}")
            return None

    def report_transaction(self, total_amount, items_list, customer_info=None):
        """
        Gửi giao dịch lên server.
        Server sẽ dựa vào X-Device-ID để trừ kho trong bảng device_inventory.
        """
        endpoint = f"{SERVER_URL}/api/transactions/record"
        payload = {
            "total_amount": total_amount,
            "customer_info": customer_info,
            "items": items_list,
            "device_id": DEVICE_ID # Gửi thêm trong body cho chắc chắn
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