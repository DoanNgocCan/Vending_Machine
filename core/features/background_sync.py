import threading
import logging
import requests
import json
import socket
from ..database.local_database_manager import db_manager
from core.features.api_manager import SERVER_URL, DEVICE_ID, API_HEADERS

class BackgroundSyncManager:
    def __init__(self):
        # Biến cờ để kiểm tra xem có đang đồng bộ hay không
        self._is_syncing = False

    def trigger_sync(self):
        """
        Hàm này được gọi từ UI (Main Thread).
        Chỉ kích hoạt nếu không có tiến trình nào đang chạy.
        """
        if self._is_syncing:
            print("BACKGROUND_SYNC: Tiến trình đồng bộ trước chưa xong, bỏ qua yêu cầu mới.")
            return

        # Tạo luồng daemon để chạy đồng bộ 1 lần
        t = threading.Thread(target=self.sync_now, daemon=True)
        t.start()

    def _check_internet(self, host="8.8.8.8", port=53, timeout=3):
        """
        Kiểm tra nhanh kết nối internet bằng cách ping Google DNS.
        """
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except socket.error:
            return False

    def sync_now(self):
        self._is_syncing = True
        
        if not self._check_internet():
            print("BACKGROUND_SYNC: [CẢNH BÁO] Không có kết nối Internet. Hủy đồng bộ.")
            self._is_syncing = False
            return

        print("BACKGROUND_SYNC: Mạng OK. Bắt đầu chu kỳ đồng bộ...")

        try:
            # --- GIAI ĐOẠN 1: Đẩy dữ liệu Local -> Server (PUSH FIRST) ---
            try:
                self._sync_unsynced_transactions()
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi khi đồng bộ giao dịch: {e}")

            try:
                self._sync_unsynced_customers()
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi khi đồng bộ khách hàng: {e}")

            # --- GIAI ĐOẠN 2: Kéo dữ liệu Server -> Client (PULL LATER) ---
            try:
                print("BACKGROUND_SYNC: Đang kéo dữ liệu sản phẩm từ Server...")
                if db_manager.sync_products_from_server():
                    print("BACKGROUND_SYNC: Cập nhật sản phẩm thành công.")
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi khi cập nhật sản phẩm: {e}")
            
            print("BACKGROUND_SYNC: Kết thúc chu kỳ đồng bộ.")

            try:
                db_manager.sync_all_users_from_server()
            except Exception as e:
                print(f"SYNC: Lỗi cập nhật khách hàng: {e}")
        except Exception as e:
            logging.error(f"BACKGROUND_SYNC: Lỗi nghiêm trọng: {e}", exc_info=True)
        
        finally:
            self._is_syncing = False

    def _sync_unsynced_customers(self):
        # Lấy danh sách cần sync
        customers = db_manager.get_unsynced_customers()
        if not customers:
            return

        print(f"BACKGROUND_SYNC: Tìm thấy {len(customers)} khách hàng cần đồng bộ...")
        for customer in customers:
            try:
                # Gọi hàm sync từng người
                db_manager.sync_customer_to_server(
                    name=customer['full_name'],
                    phone=customer['phone_number'],
                    dob=customer['birthday'],
                    password=customer['password'],
                    user_id=customer['user_id']
                )
            except requests.exceptions.RequestException as re:
                print(f"BACKGROUND_SYNC: Lỗi mạng khi sync user {customer['user_id']}: {re}")
                break 
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi dữ liệu user {customer['user_id']}: {e}")

    # --- TRONG FILE: core/features/background_sync.py ---

    def _sync_unsynced_transactions(self):
        transactions = db_manager.get_unsynced_transactions()
        if not transactions:
            return

        print(f"BACKGROUND_SYNC: Tìm thấy {len(transactions)} đơn hàng offline cần đẩy lên...")
        
        url = f"{SERVER_URL}/api/transactions/record"

        for trans in transactions:
            try:
                clean_items = []
                
                # Check list rỗng
                if not trans['items']:
                    db_manager.mark_transaction_as_synced(trans['order_code'])
                    continue

                for item in trans['items']:
                    p_name = item.get('item_name') or item.get('product_name') or item.get('name')
                    if not p_name: p_name = "UNKNOWN_ITEM"

                    clean_items.append({
                        "item_name": p_name,       
                        "quantity": item.get('quantity', 1),
                        "price": item.get('price', 0)
                    })

                # Xác định khách hàng
                user_id = trans.get('customer_name')
                real_user_id = None
                if user_id and user_id != "Guest":
                    real_user_id = user_id

                # ✅ Payload: CHỈ gửi thông tin giao dịch, KHÔNG gửi điểm
                payload = {
                    "total_amount": trans['total_amount'],
                    "items": clean_items,
                    "device_id": DEVICE_ID,
                    "customer_info": {
                        "user_id": real_user_id,
                    } 
                }
                
                # Gửi request
                json_payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                headers = API_HEADERS.copy()
                headers['Content-Type'] = 'application/json; charset=utf-8'

                response = requests.post(url, data=json_payload, headers=headers, timeout=10)
                
                if response.status_code == 200 or response.status_code == 201:
                    resp_data = response.json()
                    db_manager.mark_transaction_as_synced(trans['order_code'])
                    
                    # ✅ Cập nhật điểm từ Server về Local (Server là nguồn chân lý)
                    if real_user_id and resp_data.get('new_points') is not None:
                        db_manager.update_customer_points_exact(
                            real_user_id, 
                            resp_data['new_points']
                        )
                        print(f"BACKGROUND_SYNC: Đã đồng bộ đơn {trans['order_code']}. "
                              f"Điểm mới từ Server: {resp_data['new_points']}")
                    else:
                        print(f"BACKGROUND_SYNC: Đã đồng bộ đơn {trans['order_code']}.")
                else:
                    print(f"ERROR SERVER: {response.text}")

            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi sync đơn {trans['order_code']}: {e}")

    # Giữ lại để tương thích code cũ nếu có chỗ nào gọi
    def start(self): pass
    def stop(self): pass

# Tạo instance global
sync_manager = BackgroundSyncManager()