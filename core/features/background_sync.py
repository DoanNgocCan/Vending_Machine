# --- START OF FILE core/features/background_sync.py ---

import threading
import time
import logging
from ..database.local_database_manager import db_manager

SYNC_INTERVAL = 300  # 300 giây = 5 phút

class BackgroundSyncManager:
    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_periodic_sync, daemon=True)
        self.is_running = False

    def start(self):
        if not self.is_running:
            print("BACKGROUND_SYNC: Starting background sync manager...")
            self.is_running = True
            self._thread.start()

    def stop(self):
        if self.is_running:
            print("BACKGROUND_SYNC: Stopping background sync manager...")
            self._stop_event.set()
            try:
                self._thread.join(timeout=5)
            except Exception:
                pass
            self.is_running = False
            print("BACKGROUND_SYNC: Stopped.")

    def sync_now(self):
        """
        Thực hiện một lượt đồng bộ ngay lập tức.
        Hàm này có thể được gọi từ bất kỳ đâu, ví dụ như khi khởi động.
        """
        print("BACKGROUND_SYNC: Bắt đầu một lượt đồng bộ ngay lập tức (sync_now)...")
        try:
            # 1. Đồng bộ khách hàng
            self._sync_unsynced_customers()
            
            # 2. Đồng bộ giao dịch
            self._sync_unsynced_transactions()

            print("BACKGROUND_SYNC: Hoàn tất lượt đồng bộ ngay lập tức.")
        except Exception as e:
            logging.error(f"BACKGROUND_SYNC: Lỗi trong quá trình sync_now: {e}", exc_info=True)

    def _run_periodic_sync(self):
        """Hàm này chạy trong luồng nền để đồng bộ định kỳ."""
        print(f"BACKGROUND_SYNC: Luồng đồng bộ định kỳ đã bắt đầu, sẽ chạy mỗi {SYNC_INTERVAL} giây.")
        while not self._stop_event.is_set():
            # Gọi hàm đồng bộ chung
            self.sync_now()
            
            # Chờ cho đến chu kỳ tiếp theo
            print(f"BACKGROUND_SYNC: Chờ {SYNC_INTERVAL} giây cho chu kỳ tiếp theo.")
            self._stop_event.wait(SYNC_INTERVAL)

    def _sync_unsynced_customers(self):
        customers = db_manager.get_unsynced_customers()
        if not customers:
            print("BACKGROUND_SYNC: Không có khách hàng nào cần đồng bộ.")
            return

        print(f"BACKGROUND_SYNC: Tìm thấy {len(customers)} khách hàng cần đồng bộ.")
        for customer in customers:
            print(f"BACKGROUND_SYNC: Đang đồng bộ khách hàng: {customer['full_name']} (ID local: {customer['user_id']})")
            db_manager.sync_customer_to_server(
                name=customer['full_name'],
                phone=customer['phone_number'],
                dob=customer['birthday'],
                password=customer['password'],
                user_id=customer['user_id']
            )
            # Không cần sleep ở đây vì sync_now chỉ chạy một lần khi gọi
            # Hoặc khi chạy định kỳ, khoảng nghỉ 5 phút đã đủ lớn

    def _sync_unsynced_transactions(self):
        # (Chưa triển khai)
        pass

# Tạo một instance toàn cục
sync_manager = BackgroundSyncManager()