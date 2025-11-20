# --- START OF FILE core/database/local_database_manager.py (Phiên bản Siêu Đơn Giản) ---

import sqlite3
import uuid
from datetime import datetime
import logging
import os
import random
import string
import shutil
import threading 
# <<< SỬA ĐỔI: Không cần import bcrypt nữa >>>
# import bcrypt

DB_PATH = "vending_machine_data.db"

class LocalDatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self._init_db()

    def _get_connection(self):
        con = sqlite3.connect(self.db_path, timeout=10)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                # <<< SỬA ĐỔI: Đổi tên cột password_hash thành password >>>
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customers (
                        user_id TEXT PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        phone_number TEXT UNIQUE NOT NULL,
                        birthday TEXT,
                        password TEXT, -- Lưu mật khẩu dạng text thuần
                        points INTEGER DEFAULT 0,
                        face_encoding BLOB,
                        created_at TEXT,
                        is_synced INTEGER DEFAULT 0
                    )
                """)
                # ... (Các bảng khác không đổi)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS inventory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT UNIQUE,  -- Thêm UNIQUE để tránh trùng tên
                        price REAL DEFAULT 0,
                        units_sold INTEGER DEFAULT 0,
                        units_left INTEGER DEFAULT 0,
                        cost_price REAL DEFAULT 0,
                        reorder_point INTEGER DEFAULT 5,
                        description TEXT
                    )
                """)
                con.commit()
            self.initialize_inventory()
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi khởi tạo database: {e}", exc_info=True)

    def register_customer(self, name, phone, dob, password, face_encoding=None):
        """
        SỬA ĐỔI: Lưu mật khẩu gốc, không mã hóa.
        """
        # Kiểm tra nhanh phone đã tồn tại trước khi tạo user_id (tránh tạo nhiều user_id rác)
        try:
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute("SELECT 1 FROM customers WHERE phone_number = ?", (phone,))
                if cur.fetchone():
                    return {"error": "duplicate_phone"}
        except sqlite3.Error:
            pass  # Nếu lỗi cứ tiếp tục xuống dưới, để insert xử lý
        user_id = f"local_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now().isoformat()
        
        # Câu lệnh SQL đã được cập nhật để dùng cột 'password'
        sql = "INSERT INTO customers (user_id, full_name, phone_number, birthday, password, created_at, face_encoding, is_synced) VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
        try:
            with self._get_connection() as con:
                # Truyền mật khẩu gốc (password) trực tiếp vào câu lệnh
                con.execute(sql, (user_id, name, phone, dob, password, created_at, face_encoding))
                con.commit()
            logging.info(f"Đã đăng ký (không mã hóa) thành công cho: {name}")
            return {"code": user_id, "name": name, "phone": phone, "points": 0}
        except sqlite3.IntegrityError:
            return {"error": "duplicate_phone"}
        except sqlite3.Error as e:
            logging.error(f"Lỗi DB khi đăng ký khách hàng: {e}")
            return {"error": "db_error"}
    def sync_customer_to_server(self, name, phone, dob, password, user_id):
        """
        Đồng bộ khách hàng lên server, cập nhật CSDL và các tài nguyên nhận diện khuôn mặt.
        """
        logging.info(f"SYNC: Bắt đầu đồng bộ user '{name}' (local_id={user_id})...")

        # --- PHẦN 1: CHUẨN BỊ VÀ GỌI API (giữ nguyên) ---
        dob_for_api = None
        if dob:
            sep = '/' if '/' in dob else '-'
            try:
                parts = dob.split(sep)
                day, month, year = (parts[0], parts[1], parts[2]) if len(parts[0]) == 2 else (parts[2], parts[1], parts[0])
                dob_for_api = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except Exception:
                dob_for_api = None
                logging.warning(f"SYNC: Không parse được DOB '{dob}', bỏ qua trường birthday.")

        try:
            from core.features.api_manager import api_manager
        except Exception as e:
            logging.error(f"SYNC: Không import được api_manager: {e}")
            return

        server_customer = api_manager.register_customer(name, phone, dob_for_api, password, user_id)
        
        # --- PHẦN 2: XỬ LÝ KẾT QUẢ TỪ SERVER ---
        if not server_customer:
            logging.error(f"SYNC: Đồng bộ user '{name}' thất bại (API trả về None).")
            return

        server_user_id = server_customer.get('code')
        if not server_user_id:
            logging.error(f"SYNC: API không trả về user_id hợp lệ cho user '{name}'.")
            return

        # --- PHẦN 3: CẬP NHẬT CSDL VÀ TÀI NGUYÊN NHẬN DIỆN ---
        logging.info(f"SYNC: Server trả về user_id={server_user_id}. Bắt đầu cập nhật tài nguyên cục bộ...")
        
        try:
            # Bước 3.1: Cập nhật CSDL
            with self._get_connection() as con:
                if server_user_id != user_id:
                    # Server trả về ID mới, cập nhật cả ID và trạng thái synced
                    con.execute("UPDATE customers SET user_id = ?, is_synced = 1 WHERE user_id = ?", (server_user_id, user_id))
                    logging.info(f"SYNC: [DB] Đã đổi user_id {user_id} -> {server_user_id}.")
                else:
                    # Server trả về ID giống hệt, chỉ cập nhật trạng thái synced
                    con.execute("UPDATE customers SET is_synced = 1 WHERE user_id = ?", (user_id,))
                con.commit()

            # Bước 3.2: Nếu ID đã thay đổi, cập nhật tài nguyên nhận diện khuôn mặt
            if server_user_id != user_id:
                base_db_dir = 'core/Camera_AI/database'
                old_user_dir = os.path.join(base_db_dir, str(user_id)) # Thư mục với ID cũ (local_...)
                new_user_dir = os.path.join(base_db_dir, str(server_user_id)) # Thư mục với ID mới (user_...)
                
                # Đổi tên thư mục ảnh
                if os.path.isdir(old_user_dir):
                    logging.info(f"SYNC: [FS] Đang đổi tên thư mục ảnh từ '{user_id}' -> '{server_user_id}'")
                    if os.path.exists(new_user_dir):
                        # Gộp file nếu thư mục mới đã tồn tại
                        for f in os.listdir(old_user_dir):
                            shutil.move(os.path.join(old_user_dir, f), new_user_dir)
                        shutil.rmtree(old_user_dir)
                    else:
                        os.rename(old_user_dir, new_user_dir)
                    logging.info("SYNC: [FS] Đổi tên thư mục ảnh thành công.")

                # Xóa file cache cũ để buộc hệ thống tạo lại với ID đúng
                cache_path = os.path.join(base_db_dir, 'face_cache_edgeface_base.pkl')
                if os.path.exists(cache_path):
                    os.remove(cache_path)
                    logging.warning("SYNC: [CACHE] Đã xóa file face cache cũ. Hệ thống sẽ tự tạo lại khi khởi động.")

            # In thông báo thành công cuối cùng
            print("-" * 60)
            logging.info(f"✅ SYNC SUCCESS: Đồng bộ hoàn tất cho khách hàng '{name}' (SĐT: {phone}).")
            print("-" * 60)

        except Exception as e:
            logging.error(f"SYNC: Lỗi nghiêm trọng khi cập nhật CSDL hoặc tài nguyên: {e}", exc_info=True)

    def login_customer(self, phone, password_input):
        """
        SỬA ĐỔI: So sánh mật khẩu gốc trực tiếp.
        """
        sql = "SELECT * FROM customers WHERE phone_number = ?"
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                cursor.execute(sql, (phone,))
                user_row = cursor.fetchone()

                # Nếu tìm thấy user và mật khẩu nhập vào khớp với mật khẩu trong DB
                if user_row and user_row['password'] == password_input:
                    logging.info(f"Đăng nhập thành công cho SĐT: {phone}")
                    return {
                        "code": user_row['user_id'],
                        "name": user_row['full_name'],
                        "phone": user_row['phone_number'],
                        "points": user_row['points']
                    }
                else:
                    logging.warning(f"Đăng nhập thất bại: Sai SĐT hoặc mật khẩu cho {phone}")
                    return None
        except Exception as e:
            logging.error(f"Lỗi DB khi đăng nhập: {e}", exc_info=True)
            return None
    
    def add_or_update_customer_from_server(self, server_user_data):
        """
        Thêm một khách hàng mới hoặc cập nhật thông tin từ server vào CSDL local.
        Sử dụng INSERT OR REPLACE để xử lý cả hai trường hợp.
        """
        user_id = server_user_data.get('user_id')
        if not user_id:
            return False
            
        sql = """
            INSERT INTO customers (user_id, full_name, phone_number, points, is_synced, password, created_at)
            VALUES (?, ?, ?, ?, 1, 'synced_from_server', ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                phone_number = excluded.phone_number,
                points = excluded.points,
                is_synced = 1;
        """
        try:
            with self._get_connection() as con:
                con.execute(sql, (
                    user_id,
                    server_user_data.get('full_name'),
                    server_user_data.get('phone_number'),
                    server_user_data.get('points', 0),
                    datetime.now().isoformat()
                ))
            logging.info(f"Đã thêm/cập nhật user {user_id} từ server vào CSDL local.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi thêm/cập nhật user từ server: {e}")
            return False    

    # --- Các hàm còn lại không thay đổi ---
    def generate_order_code(self):
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"ORD-{now}-{rand_part}"
    def save_transaction(self, total_amount, customer_name_str, items_detail_str, items_sold_list):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_code = self.generate_order_code()
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                cursor.execute("INSERT INTO transaction_history (timestamp, order_code, total_amount, customer_name, items_detail, is_synced) VALUES (?, ?, ?, ?, ?, 0)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), order_code, total_amount, customer_name_str, items_detail_str))
                for item in items_sold_list:
                    cursor.execute("""
                    UPDATE inventory 
                    SET units_left = units_left - ?, 
                        units_sold = units_sold + ? 
                    WHERE item_name = ?
                """, (item['quantity'], item['quantity'], item['product_name']))
                return order_code
        except sqlite3.Error as e:
            logging.error(f"LỖI LƯU GIAO DỊCH CỤC BỘ: {e}")
            return None 
    def mark_transaction_as_synced(self, order_code):
        """Đánh dấu một giao dịch đã được đồng bộ thành công."""
        try:
            with self._get_connection() as con:
                con.execute("UPDATE transaction_history SET is_synced = 1 WHERE order_code = ?", (order_code,))
            logging.info(f"Đã đánh dấu đồng bộ thành công cho đơn hàng {order_code}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi đánh dấu đồng bộ đơn hàng {order_code}: {e}")
            return False
    def get_unsynced_customers(self):
        """Lấy tất cả khách hàng có is_synced = 0."""
        try:
            with self._get_connection() as con:
                customers = con.execute("SELECT * FROM customers WHERE is_synced = 0").fetchall()
                return customers
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi lấy danh sách khách hàng chưa đồng bộ: {e}")
            return []
    def update_customer_points(self, user_id, points_used, total_amount):
        if not user_id: return False
        points_earned = int(total_amount / 1000)
        try:
            with self._get_connection() as con:
                con.cursor().execute("UPDATE customers SET points = points - ? + ? WHERE user_id = ?", (points_used, points_earned, user_id))
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi cập nhật điểm cho user {user_id}: {e}")
            return False
    def initialize_inventory(self):
        """
        Tự động nạp sản phẩm từ file config.py vào bảng inventory của Database.
        Chỉ nạp nếu sản phẩm chưa tồn tại (dựa trên tên).
        """
        try:
            # Import config ở đây để tránh lỗi vòng lặp (circular import) nếu có
            # Giả sử file config.py nằm cùng cấp hoặc trong PYTHONPATH
            from config import PRODUCT_IMAGES_CONFIG
        except ImportError:
            logging.error("KHÔNG TÌM THẤY FILE CONFIG.PY ĐỂ NẠP SẢN PHẨM!")
            return

        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                added_count = 0
                
                # Duyệt qua từng sản phẩm trong config
                # config format: "key": ("Tên", "ảnh.png", Giá)
                for key, (name, image_file, price) in PRODUCT_IMAGES_CONFIG.items():
                    
                    # Giả lập dữ liệu còn thiếu
                    default_stock = 50       # Mặc định tồn kho 50 cái
                    default_cost = price * 0.7  # Giả định giá vốn bằng 70% giá bán
                    default_reorder = 10     # Mức báo động hết hàng
                    description = f"Mã ảnh: {image_file}" # Lưu tên ảnh vào mô tả để dễ debug

                    # Dùng INSERT OR IGNORE để không bị lỗi nếu tên sản phẩm đã có rồi
                    cursor.execute("""
                        INSERT OR IGNORE INTO inventory 
                        (item_name, price, units_left, units_sold, cost_price, reorder_point, description)
                        VALUES (?, ?, ?, 0, ?, ?, ?)
                    """, (name, price, default_stock, default_cost, default_reorder, description))
                    
                    if cursor.rowcount > 0:
                        added_count += 1

                con.commit()
                if added_count > 0:
                    logging.info(f"Đã khởi tạo thêm {added_count} sản phẩm từ Config vào Database.")
                else:
                    logging.info("Database đã đồng bộ với Config (không có sản phẩm mới).")
                    
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi khởi tạo inventory: {e}")
    def get_customer_by_id(self, user_id):
        if not user_id: return None
        sql = "SELECT * FROM customers WHERE user_id = ?"
        try:
            with self._get_connection() as con:
                user_row = con.cursor().execute(sql, (user_id,)).fetchone()
                if user_row:
                    return {"code": user_row['user_id'], "name": user_row['full_name'], "phone": user_row['phone_number'], "points": user_row['points']}
                return None
        except sqlite3.Error: return None
    def get_most_recent_customer_with_face_encoding(self):
        """
        Lấy thông tin user_id của khách hàng gần nhất có đăng ký khuôn mặt.
        Hàm này dùng để giả lập việc nhận diện thành công người vừa đăng ký.
        """
        sql = "SELECT user_id FROM customers WHERE face_encoding IS NOT NULL ORDER BY created_at DESC LIMIT 1"
        try:
            with self._get_connection() as con:
                user_row = con.cursor().execute(sql).fetchone()
                if user_row:
                    return {"user_id": user_row['user_id']}
                return None
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi lấy khách hàng gần nhất có face_encoding: {e}")
            return None
    def mark_customer_as_unsynced(self, user_id):
        """Đánh dấu một khách hàng cần được đồng bộ lại."""
        try:
            with self._get_connection() as con:
                con.execute("UPDATE customers SET is_synced = 0 WHERE user_id = ?", (user_id,))
            logging.warning(f"Đã đánh dấu user {user_id} cần đồng bộ lại.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi đánh dấu unsynced cho user {user_id}: {e}")
            return False

db_manager = LocalDatabaseManager()

# --- END OF FILE core/database/local_database_manager.py ---