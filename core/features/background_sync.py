# --- FILE: core/features/background_sync.py ---

import threading
import logging
import requests # Cần import requests để bắt lỗi mạng
import socket
from ..database.local_database_manager import db_manager

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
        Cách này nhanh hơn dùng requests và ít tốn tài nguyên hơn.
        """
        try:
            socket.setdefaulttimeout(timeout)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
            return True
        except socket.error:
            return False

    def sync_now(self):
        """
        Thực hiện logic đồng bộ (Chạy trong luồng phụ).
        Có xử lý try/except để không làm crash ứng dụng khi mất mạng.
        """
        self._is_syncing = True
        
        # 1. Kiểm tra mạng trước khi làm gì cả
        if not self._check_internet():
            print("BACKGROUND_SYNC: [CẢNH BÁO] Không có kết nối Internet. Hủy đồng bộ.")
            self._is_syncing = False
            return

        print("BACKGROUND_SYNC: Mạng OK. Bắt đầu chu kỳ đồng bộ...")

        try:
            # --- GIAI ĐOẠN 1: Gửi dữ liệu khách hàng (Client -> Server) ---
            # Dùng try/except riêng lẻ để lỗi phần này không chặn phần kia
            try:
                self._sync_unsynced_customers()
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi khi đồng bộ khách hàng: {e}")

            # --- GIAI ĐOẠN 2: Cập nhật Sản phẩm & Giá (Server -> Client) ---
            # Đây là phần quan trọng nhất để cập nhật giá
            try:
                print("BACKGROUND_SYNC: Đang kéo dữ liệu sản phẩm từ Server...")
                db_manager.sync_products_from_server()
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi khi cập nhật sản phẩm: {e}")
            
            # --- GIAI ĐOẠN 3: Đồng bộ giao dịch (nếu cần) ---
            try:
                self._sync_unsynced_transactions()
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi khi đồng bộ giao dịch: {e}")

            print("BACKGROUND_SYNC: Kết thúc chu kỳ đồng bộ.")

        except Exception as e:
            # Bắt lỗi không xác định khác
            logging.error(f"BACKGROUND_SYNC: Lỗi nghiêm trọng không xác định: {e}", exc_info=True)
        
        finally:
            # Luôn luôn reset cờ để lần sau có thể chạy tiếp
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
                # Nếu lỗi mạng thì dừng vòng lặp ngay, không cố sync người sau làm gì
                break 
            except Exception as e:
                print(f"BACKGROUND_SYNC: Lỗi dữ liệu user {customer['user_id']}: {e}")

    def _sync_unsynced_transactions(self):
        pass

    # Giữ lại để tương thích code cũ
    def start(self): pass
    def stop(self): pass

sync_manager = BackgroundSyncManager()