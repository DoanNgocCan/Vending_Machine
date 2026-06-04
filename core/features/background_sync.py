import threading
import logging
import requests
import json
import socket
import time
import pickle   # Để đọc vector dạng binary
import numpy as np

from core.database.local_database_manager import db_manager
from core.features.api_manager import SERVER_URL, DEVICE_ID, API_HEADERS, api_manager

class BackgroundSyncManager:
    def __init__(self):
        # Biến cờ để kiểm tra xem có đang đồng bộ hay không
        self._is_syncing = False
        self._stop_event = threading.Event() # Dùng để dừng luồng chạy ngầm khi tắt app

    def start_auto_sync(self, interval_minutes=3):
        """
        Khởi động luồng chạy ngầm định kỳ (Background Worker).
        Mặc định 3 phút chạy 1 lần.
        """
        def periodic_sync():
            while not self._stop_event.is_set():
                self.trigger_sync()
                # Sleep chia nhỏ để có thể dừng app ngay lập tức thay vì bị block nguyên khoảng thời gian dài
                for _ in range(interval_minutes * 60):
                    if self._stop_event.is_set():
                        break
                    time.sleep(1)

        t = threading.Thread(target=periodic_sync, daemon=True)
        t.start()
        logging.info(f"BACKGROUND_SYNC: Đã khởi động Auto Sync Worker (Chu kỳ: {interval_minutes} phút).")

    def trigger_sync(self):
        """
        Hàm này được gọi từ UI hoặc Timer.
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

    def _sync_offline_customers(self):
        """
        Quét CSDL tìm kiếm các tài khoản khách hàng đăng ký offline trong lúc rớt mạng, 
        trích xuất đầy đủ mật khẩu, điểm số, vector, ảnh ZIP để thử đồng bộ lại với Server.
        """
        unsynced_customers = db_manager.get_unsynced_customers()
        if not unsynced_customers:
            return 

        print(f"BACKGROUND_SYNC: Phát hiện {len(unsynced_customers)} tài khoản chưa đồng bộ mặt và thông tin mật khẩu.")

        for row in unsynced_customers:
            try:
                # Ép kiểu sqlite3.Row sang dict để sử dụng được hàm .get() một cách an toàn
                customer = dict(row)
                
                user_id = customer['user_id']
                name = customer['full_name']
                phone = customer['phone_number']
                email = customer.get('email', '')
                password = customer.get('password', '')
                points = customer.get('points', 0)
                
                face_vector_blob = customer['face_vector']
                images_zip_bytes = customer.get('offline_images_zip')

                if not images_zip_bytes or not face_vector_blob:
                    continue  

                try:
                    # Logic giải mã nhị phân chuẩn xác của bạn
                    face_vector = pickle.loads(face_vector_blob)
                except Exception as e:
                    logging.error(f"BACKGROUND_SYNC: Không thể giải mã mảng numpy vector cho {user_id}: {e}")
                    continue

                print(f"  -> Đang gửi bù: ID={user_id}, Tên={name}, Mật khẩu=[Đã mã hóa], Điểm={points}...")

                # Đẩy lên Server đầy đủ tham số mật khẩu và điểm số
                success, error_msg = api_manager.upload_customer_face_data(
                    user_id=user_id,
                    name=name,
                    phone=phone,
                    email=email,
                    password=password,
                    points=points,
                    face_vector=face_vector,
                    images_zip_bytes=images_zip_bytes
                )

                if success:
                    db_manager.update_sync_status(user_id, is_synced=1)
                    db_manager.clear_offline_images_zip(user_id) # Giải phóng dung lượng BLOB ảnh khỏi DB local
                    print(f"Đồng bộ ngầm thành công cho khách hàng {user_id}. Đã dọn dẹp bộ nhớ đệm hình ảnh.")
                else:
                    print(f"Đồng bộ ngầm thất bại cho khách {user_id} ({error_msg}). Sẽ thử lại ở chu kỳ kế tiếp.")

            except Exception as e:
                # Lấy user_id an toàn trong khối except
                failed_id = row['user_id'] if 'user_id' in row.keys() else 'Unknown'
                logging.error(f"BACKGROUND_SYNC: Lỗi nghiêm trọng xảy ra trong vòng lặp đồng bộ khách {failed_id}: {e}")

    def sync_now(self):
        self._is_syncing = True
        
        try:
            if not self._check_internet():
                print("BACKGROUND_SYNC: [CẢNH BÁO] Không có kết nối Internet. Hủy đồng bộ.")
                return

            # ==========================================
            # 1. ĐỒNG BỘ KHUÔN MẶT OFFLINE TRƯỚC
            # ==========================================
            self._sync_offline_customers()
            
            # ==========================================
            # 2. ĐỒNG BỘ ĐƠN HÀNG (LOGIC CŨ CỦA BẠN)
            # ==========================================
            unsynced_transactions = db_manager.get_unsynced_transactions()
            if unsynced_transactions:
                url = f"{SERVER_URL}/api/transactions/sync"
                for trans in unsynced_transactions:
                    try:
                        # Extract thông tin... (Logic giữ nguyên bản cũ của bạn)
                        real_user_id = trans['customer_name']
                        if real_user_id == "Guest" or real_user_id is None:
                            real_user_id = None
                            
                        # (Đoạn này là phần code cũ của bạn, tôi rút gọn lại trong demo, bạn giữ nguyên code parse JSON cũ ở đây)
                        payload = {
                            "order_code": trans['order_code'],
                            "timestamp": trans['timestamp'],
                            "total_amount": trans['total_amount'],
                            "customer_id": real_user_id,
                            "items": trans['items'],
                            "device_id": DEVICE_ID
                        }
                        json_payload = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                        headers = API_HEADERS.copy()
                        headers['Content-Type'] = 'application/json; charset=utf-8'

                        response = requests.post(url, data=json_payload, headers=headers, timeout=10)
                        
                        if response.status_code in (200, 201):
                            resp_data = response.json()
                            db_manager.mark_transaction_as_synced(trans['order_code'])
                            
                            # Cập nhật điểm
                            if real_user_id and resp_data.get('new_points') is not None:
                                db_manager.update_customer_points_exact(real_user_id, resp_data['new_points'])
                                print(f"BACKGROUND_SYNC: Đã đồng bộ đơn {trans['order_code']}. Điểm mới: {resp_data['new_points']}")
                            else:
                                print(f"BACKGROUND_SYNC: Đã đồng bộ đơn {trans['order_code']}.")
                        else:
                            print(f"ERROR SERVER: {response.text}")
                    except Exception as e:
                        print(f"BACKGROUND_SYNC: Lỗi sync đơn {trans['order_code']}: {e}")

        except Exception as e:
            logging.error(f"BACKGROUND_SYNC: Lỗi tổng: {e}")
        finally:
            # Luôn luôn giải phóng cờ này dù có lỗi xảy ra hay không
            self._is_syncing = False

    # Hàm dọn dẹp để tắt ứng dụng an toàn
    def stop(self):
        self._stop_event.set()
        print("BACKGROUND_SYNC: Đã nhận lệnh dừng Auto Worker.")

# Tạo instance global
sync_manager = BackgroundSyncManager()