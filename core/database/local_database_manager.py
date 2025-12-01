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
import requests
from core.features.api_manager import DEVICE_ID, API_HEADERS, SERVER_URL

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
                
                # Bảng customers
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS customers (
                        user_id TEXT PRIMARY KEY,
                        full_name TEXT NOT NULL,
                        phone_number TEXT UNIQUE NOT NULL,
                        birthday TEXT,
                        password TEXT,
                        points INTEGER DEFAULT 0,
                        face_encoding BLOB,
                        created_at TEXT,
                        is_synced INTEGER DEFAULT 0
                    )
                """)

                # Bảng inventory local
                # [SỬA ĐỔI] Đã bỏ cột slot_number để khớp với Server
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS inventory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT UNIQUE,
                        price REAL DEFAULT 0,
                        units_sold INTEGER DEFAULT 0,
                        units_left INTEGER DEFAULT 0, -- Tồn kho thực tế tại máy này
                        cost_price REAL DEFAULT 0,
                        reorder_point INTEGER DEFAULT 5,
                        description TEXT
                    )
                """)
                
                # Bảng transaction_history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transaction_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        order_code TEXT UNIQUE,
                        total_amount REAL,
                        customer_name TEXT,
                        items_detail TEXT,
                        is_synced INTEGER DEFAULT 0
                    )
                """)
                con.commit()
            logging.info("DB Local khởi tạo thành công.")
            
            # 1. Nạp dữ liệu local từ Config (Dự phòng)
            self.initialize_inventory()
            
            # 2. LUỒNG 1: Đẩy Config lên Server (Kèm số lượng để Server init kho cho máy này)
            t1 = threading.Thread(target=self.push_config_to_server, daemon=True)
            t1.start()
            
            # 3. LUỒNG 2: Kéo giá/tồn kho từ Server về (Để cập nhật nếu Server có thay đổi)
            t2 = threading.Thread(target=self.sync_products_from_server, daemon=True)
            t2.start()
            
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi khởi tạo database: {e}", exc_info=True)

    def delete_customer(self, user_id):
        """Xóa khách hàng khỏi DB local (Dùng khi hủy đăng ký giữa chừng)."""
        try:
            with self._get_connection() as con:
                con.execute("DELETE FROM customers WHERE user_id = ?", (user_id,))
                con.commit()
            logging.info(f"ROLLBACK: Đã xóa user {user_id} khỏi DB local do người dùng hủy.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi xóa user {user_id}: {e}")
            return False
        
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

    # Thêm hàm này vào trong class LocalDatabaseManager (cùng cấp với các hàm khác)
    def push_config_to_server(self):
        """
        Đẩy cấu hình và tồn kho hiện tại lên Server.
        QUAN TRỌNG: Để server khởi tạo dòng trong 'device_inventory'.
        """
        try:
            # Lấy tồn kho thực tế từ DB Local thay vì fix cứng 50
            current_stock = {}
            with self._get_connection() as con:
                rows = con.execute("SELECT item_name, units_left, price FROM inventory").fetchall()
                for r in rows:
                    current_stock[r['item_name']] = {'qty': r['units_left'], 'price': r['price']}

            from config import PRODUCT_IMAGES_CONFIG
            
            sync_url = f"{SERVER_URL}/api/products/batch_sync"
            product_list = []
            
            for key, val in PRODUCT_IMAGES_CONFIG.items():
                name = val[0]
                # Nếu trong DB local có thì lấy số lượng thực, không thì mặc định 50
                qty = current_stock.get(name, {}).get('qty', 50)
                price = current_stock.get(name, {}).get('price', val[2])

                product_list.append({
                    "name": name,
                    "image": val[1],
                    "price": price,
                    "quantity": qty, # Gửi số lượng thực tế lên
                    "device_id": DEVICE_ID 
                })
            
            logging.info(f"📤 Đang đẩy cấu hình kho ({len(product_list)} món) lên Server cho {DEVICE_ID}...")
            
            response = requests.post(sync_url, json={"products": product_list}, headers=API_HEADERS, timeout=10)
            
            if response.status_code == 200:
                logging.info(f"✅ Đã đồng bộ kho thiết bị lên Server.")
            else:
                logging.warning(f"⚠️ Server trả về lỗi khi sync config: {response.text}")
                
        except Exception as e:
            logging.error(f"❌ Lỗi push_config_to_server: {e}")
    # Thêm hàm này vào trong class LocalDatabaseManager
    def sync_products_from_server(self):
        """
        Kéo dữ liệu từ Server về.
        Server sẽ trả về tồn kho (units_left) CỦA RIÊNG MÁY NÀY.
        """
        get_url = f"{SERVER_URL}/api/products"
        logging.info(f"🔄 Đang đồng bộ kho từ Server cho máy: {DEVICE_ID}...")

        try:
            response = requests.get(get_url, headers=API_HEADERS, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    server_products = data.get('products', [])
                    
                    with self._get_connection() as con:
                        cursor = con.cursor()
                        count = 0
                        
                        for p in server_products:
                            # Cập nhật Local DB theo Server
                            # Server trả về units_left là tồn kho của máy này -> Cập nhật luôn
                            cursor.execute("""
                                INSERT INTO inventory (item_name, price, cost_price, units_left, description)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(item_name) DO UPDATE SET
                                    price = excluded.price,
                                    cost_price = excluded.cost_price,
                                    units_left = excluded.units_left, -- Đồng bộ tồn kho từ Server về Local
                                    description = excluded.description
                            """, (
                                p['item_name'], 
                                p['price'], 
                                p.get('cost_price', 0), 
                                p.get('units_left', 0), 
                                p.get('description', '')
                            ))
                            count += 1
                        con.commit()
                        logging.info(f"✅ Đã đồng bộ {count} sản phẩm và tồn kho từ Server.")
                        return True
            else:
                logging.error(f"❌ Lỗi kết nối Server: {response.status_code}")

        except Exception as e:
            logging.error(f"❌ Lỗi sync_products_from_server: {e}")
            return False
        
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
        """
        Lưu giao dịch và trừ kho Local ngay lập tức (Offline logic).
        Sau đó api_manager sẽ gửi giao dịch này lên Server để trừ kho trên Server.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_code = self.generate_order_code()
        
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                
                # 1. Lưu lịch sử
                cursor.execute("""
                    INSERT INTO transaction_history 
                    (timestamp, order_code, total_amount, customer_name, items_detail, is_synced) 
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (timestamp, order_code, total_amount, customer_name_str, items_detail_str))
                
                # 2. Trừ kho Local
                for item in items_sold_list:
                    # item format: {'product_name': 'Coca', 'quantity': 1}
                    cursor.execute("""
                        UPDATE inventory 
                        SET units_left = units_left - ?, 
                            units_sold = units_sold + ? 
                        WHERE item_name = ?
                    """, (item['quantity'], item['quantity'], item['product_name']))
                
                con.commit()
                return order_code
        except sqlite3.Error as e:
            logging.error(f"LỖI LƯU GIAO DỊCH LOCAL: {e}")
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
        """Nạp dữ liệu ban đầu từ Config nếu DB trống."""
        try:
            from config import PRODUCT_IMAGES_CONFIG
        except ImportError:
            return

        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                count = 0
                for key, (name, image_file, default_price) in PRODUCT_IMAGES_CONFIG.items():
                    # Mặc định tạo 50 món cho mỗi loại lúc khởi tạo lần đầu
                    cursor.execute("""
                        INSERT OR IGNORE INTO inventory 
                        (item_name, price, units_left, units_sold, cost_price, reorder_point, description)
                        VALUES (?, ?, 50, 0, 0, 5, ?)
                    """, (name, default_price, f"Image: {image_file}"))
                    
                    if cursor.rowcount > 0:
                        count += 1
                con.commit()
                if count > 0:
                    logging.info(f"Initialized local inventory with {count} items.")
        except sqlite3.Error as e:
            logging.error(f"Lỗi initialize_inventory: {e}")

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