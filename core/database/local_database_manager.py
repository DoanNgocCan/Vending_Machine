# --- START OF FILE core/database/local_database_manager.py 

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
import time
import ast
from core.features.api_manager import DEVICE_ID, API_HEADERS, SERVER_URL
from werkzeug.security import generate_password_hash, check_password_hash

# 1. Lấy đường dẫn thư mục hiện tại (thư mục 'database')
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Lùi lại 2 cấp (database -> core -> thư mục gốc) để tới vị trí của main.py
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

# 3. Trỏ đích danh tới file database ở thư mục gốc
DB_PATH = os.path.join(ROOT_DIR, "vending_machine_data.db")

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
                        email TEXT UNIQUE,     -- Thêm email, xóa birthday
                        password TEXT,
                        points INTEGER DEFAULT 0,
                        face_encoding BLOB,
                        created_at TEXT,
                        is_synced INTEGER DEFAULT 0
                    )
                """)

                # Bảng inventory local - Khóa chính là slot_number
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS inventory (
                        slot_number INTEGER PRIMARY KEY,
                        item_name TEXT,  -- CHÚ Ý: Đã xóa chữ UNIQUE ở đây
                        price INTEGER DEFAULT 0,
                        units_sold INTEGER DEFAULT 0,
                        units_left INTEGER DEFAULT 0,
                        cost_price INTEGER DEFAULT 0,
                        reorder_point INTEGER DEFAULT 5,
                        description TEXT,
                        image_path TEXT,
                        server_product_id TEXT,
                        updated_at TEXT
                    )
                """)

                # Migration: thêm cột mới cho DB cũ chưa có các cột này
                for col_def in [
                    ("image_path", "TEXT"),
                    ("server_product_id", "TEXT"),
                    ("updated_at", "TEXT"),
                ]:
                    try:
                        cursor.execute(f"ALTER TABLE inventory ADD COLUMN {col_def[0]} {col_def[1]}")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e).lower():
                            raise
                
                # Bảng transaction_history
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS transaction_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT,
                        order_code TEXT UNIQUE,
                        total_amount INTEGER,
                        customer_name TEXT,
                        items_detail TEXT,
                        is_synced INTEGER DEFAULT 0
                    )
                """)
                con.commit()
            logging.info("DB Local khởi tạo thành công.")

        except sqlite3.Error as e:
            logging.error(f"Lỗi khi khởi tạo database: {e}", exc_info=True)

    def delete_customer(self, user_id):
        try:
            with self._get_connection() as con:
                con.execute("DELETE FROM customers WHERE user_id = ?", (user_id,))
                con.commit()
            logging.info(f"ROLLBACK: Đã xóa user {user_id} khỏi DB local.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi xóa user {user_id}: {e}")
            return False
        
    def register_customer(self, name, phone, email, password, face_encoding=None): # Đổi dob -> email
        try:
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute("SELECT 1 FROM customers WHERE phone_number = ? OR email = ?", (phone, email))
                if cur.fetchone():
                    return {"error": "duplicate_phone_or_email"}
        except sqlite3.Error:
            pass 
        user_id = f"local_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now().isoformat()
        hashed_password = generate_password_hash(password)
        
        # Đổi birthday -> email
        sql = "INSERT INTO customers (user_id, full_name, phone_number, email, password, created_at, face_encoding, is_synced) VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
        try:
            with self._get_connection() as con:
                # Lưu biến password trực tiếp
                con.execute(sql, (user_id, name, phone, email, password, created_at, face_encoding))
                con.commit()
            logging.info(f"Đã đăng ký thành công cho: {name}")
            return {"code": user_id, "name": name, "phone": phone, "email": email, "points": 0}
        except Exception as e:
            logging.error(f"Lỗi DB khi đăng ký khách hàng: {e}")
            return {"error": "db_error"}

    def sync_customer_to_server(self, name, phone, email, password, user_id): # Đổi dob -> email
        logging.info(f"SYNC: Bắt đầu đồng bộ user '{name}' (local_id={user_id})...")

        try:
            from core.features.api_manager import api_manager
        except Exception as e:
            logging.error(f"SYNC: Không import được api_manager: {e}")
            return

        # Gọi API đăng ký (truyền password 2 lần do server đòi confirm_password)
        server_customer = api_manager.register_customer(name, phone, email, password, password, user_id)
        
        if not server_customer:
            logging.error(f"SYNC: Đồng bộ user '{name}' thất bại.")
            return

        server_user_id = server_customer.get('code')
        if not server_user_id:
            return

        logging.info(f"SYNC: Server trả về user_id={server_user_id}. Cập nhật local...")
        
        try:
            with self._get_connection() as con:
                if server_user_id != user_id:
                    con.execute("UPDATE customers SET user_id = ?, is_synced = 1 WHERE user_id = ?", (server_user_id, user_id))
                    logging.info(f"SYNC: [DB] Đã đổi user_id {user_id} -> {server_user_id}.")
                else:
                    con.execute("UPDATE customers SET is_synced = 1 WHERE user_id = ?", (user_id,))
                con.commit()

            if server_user_id != user_id:
                base_db_dir = 'core/Camera_AI/database'
                old_user_dir = os.path.join(base_db_dir, str(user_id))
                new_user_dir = os.path.join(base_db_dir, str(server_user_id))
                
                if os.path.isdir(old_user_dir):
                    if os.path.exists(new_user_dir):
                        for f in os.listdir(old_user_dir):
                            shutil.move(os.path.join(old_user_dir, f), new_user_dir)
                        shutil.rmtree(old_user_dir)
                    else:
                        os.rename(old_user_dir, new_user_dir)

                cache_path = os.path.join(base_db_dir, 'face_cache_edgeface_base.pkl')
                if os.path.exists(cache_path):
                    os.remove(cache_path)

            print("-" * 60)
            logging.info(f"✅ SYNC SUCCESS: Đồng bộ hoàn tất cho khách hàng '{name}'.")
            print("-" * 60)

        except Exception as e:
            logging.error(f"SYNC: Lỗi cập nhật CSDL: {e}", exc_info=True)

    def get_inventory_map(self):
        stock_map = {}
        try:
            with self._get_connection() as con:
                rows = con.execute(
                    "SELECT slot_number, item_name, units_left, price, image_path, server_product_id FROM inventory"
                ).fetchall()
                for r in rows:
                    stock_map[r['slot_number']] = {
                        'item_name': r['item_name'],
                        'qty': r['units_left'],
                        'price': r['price'],
                        'image_path': r['image_path'],
                        'server_product_id': r['server_product_id'],
                    }
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi lấy map tồn kho: {e}")
        return stock_map

    def update_product_price_quantity(self, item_name, price=None, quantity=None):
        """
        Cập nhật giá và/hoặc số lượng của một sản phẩm theo item_name.
        Dùng khi nhận được MQTT hot update từ server.
        """
        if price is None and quantity is None:
            return False
        try:
            from datetime import datetime as _dt
            now = _dt.now().isoformat()
            with self._get_connection() as con:
                if price is not None and quantity is not None:
                    con.execute(
                        "UPDATE inventory SET price = ?, units_left = ?, updated_at = ? WHERE item_name = ?",
                        (price, quantity, now, item_name)
                    )
                elif price is not None:
                    con.execute(
                        "UPDATE inventory SET price = ?, updated_at = ? WHERE item_name = ?",
                        (price, now, item_name)
                    )
                else:
                    con.execute(
                        "UPDATE inventory SET units_left = ?, updated_at = ? WHERE item_name = ?",
                        (quantity, now, item_name)
                    )
                con.commit()
            logging.info(f"DB: Đã cập nhật sản phẩm '{item_name}': giá={price}, số lượng={quantity}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"DB: Lỗi cập nhật sản phẩm '{item_name}': {e}")
            return False

    def upsert_product(self, product_data, local_image_path=None):
        if not product_data or not product_data.get('item_name'):
            return False
        try:
            from datetime import datetime as _dt
            now = _dt.now().isoformat()
            item_name = product_data['item_name']
            price = product_data.get('price', 0)
            units_left = product_data.get('units_left', product_data.get('quantity', 0))
            cost_price = product_data.get('cost_price', 0)
            description = product_data.get('description', '')
            server_product_id = str(product_data.get('id', ''))
            image_path = local_image_path or product_data.get('image_path', '')

            with self._get_connection() as con:
                # Chỉ UPDATE giá và số lượng, không chèn mới nếu chưa có ô
                con.execute("""
                    UPDATE inventory SET
                        price = ?,
                        cost_price = ?,
                        units_left = ?,
                        description = ?,
                        image_path = COALESCE(?, image_path),
                        server_product_id = ?,
                        updated_at = ?
                    WHERE item_name = ?
                """, (price, cost_price, units_left, description, image_path, server_product_id, now, item_name))
                con.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"DB: Lỗi upsert sản phẩm '{product_data.get('item_name')}': {e}")
            return False

    def sync_all_users_from_server(self):
        """
        MỚI: Khi khởi động, KÉO dữ liệu khách hàng TỪ Server VỀ.
        Server là nguồn chân lý → Client cập nhật local cho khớp.
        """
        logging.info("STARTUP SYNC: Kéo dữ liệu khách hàng từ Server về...")
        
        try:
            s = requests.Session()
            s.trust_env = False
            response = s.get(f"{SERVER_URL}/api/users?limit=10000", 
                            headers=API_HEADERS, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                server_users = data.get('users', [])
                
                with self._get_connection() as con:
                    count = 0
                    for user in server_users:
                        con.execute("""
                            INSERT INTO customers (user_id, full_name, phone_number, email, points, password, is_synced)
                            VALUES (?, ?, ?, ?, ?, ?, 1)
                            ON CONFLICT(user_id) DO UPDATE SET
                                full_name = excluded.full_name,
                                phone_number = excluded.phone_number,
                                email = excluded.email,
                                points = excluded.points,
                                password = excluded.password, -- Lưu thẳng mật khẩu text từ server
                                is_synced = 1
                        """, (
                            user['user_id'],
                            user.get('full_name', ''),
                            user.get('phone_number', ''),
                            user.get('email', ''),
                            user.get('points', 0),
                            user.get('password', '') # Server trả về gì lưu nấy
                        ))
                        count += 1
                    con.commit()
                logging.info(f"✅ Đã đồng bộ {count} khách hàng từ Server.")
        except Exception as e:
            logging.error(f"Lỗi sync users from server: {e}")

    def sync_products_from_server(self):
        get_url = f"{SERVER_URL}/api/products"
        logging.info(f"🔄 Đang đồng bộ kho từ Server cho máy: {DEVICE_ID}...")

        try:
            from core.features.api_manager import api_manager
            s = requests.Session()
            s.trust_env = False
            headers = API_HEADERS.copy()
            if 'X-Device-ID' not in headers:
                headers['X-Device-ID'] = DEVICE_ID

            response = s.get(get_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    server_products = data.get('products', [])
                    
                    # --- BƯỚC 1: XỬ LÝ MẠNG VÀ TẢI ẢNH (Tuyệt đối không mở DB lúc này) ---
                    processed_products = []
                    server_slots = []
                    
                    for p in server_products:
                        slot_number = p.get('slot_number')
                        if not slot_number: continue 
                            
                        server_slots.append(slot_number)
                        item_name = p['item_name']
                        
                        try:
                            server_qty = int(p.get('units_left', 0))
                        except (ValueError, TypeError):
                            server_qty = 0

                        raw_image_url = p.get('image_url') or p.get('image_path')
                        local_image_path = None
                        if raw_image_url:
                            full_url = f"{SERVER_URL}{raw_image_url}" if raw_image_url.startswith('/') else raw_image_url
                            downloaded_path = api_manager.download_product_image(full_url, item_name)
                            if downloaded_path:
                                local_image_path = downloaded_path

                        processed_products.append({
                            'slot': slot_number,
                            'name': item_name,
                            'price': p.get('price', 0),
                            'cost': p.get('cost_price', 0),
                            'qty': server_qty,
                            'desc': p.get('description', ''),
                            'img': local_image_path,
                            'sid': str(p.get('id', ''))
                        })

                    # --- BƯỚC 2: MỞ DATABASE VÀ CẬP NHẬT CỰC NHANH (Chống Lock DB) ---
                    with self._get_connection() as con:
                        cursor = con.cursor()
                        count = 0
                        
                        for p in processed_products:
                            cursor.execute("""
                                INSERT INTO inventory (slot_number, item_name, price, cost_price, units_left, description, image_path, server_product_id, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(slot_number) DO UPDATE SET
                                    item_name = excluded.item_name,
                                    price = excluded.price,
                                    cost_price = excluded.cost_price,
                                    units_left = excluded.units_left,
                                    description = excluded.description,
                                    image_path = COALESCE(excluded.image_path, inventory.image_path),
                                    server_product_id = excluded.server_product_id,
                                    updated_at = excluded.updated_at
                            """, (
                                p['slot'], p['name'], p['price'], p['cost'], 
                                p['qty'], p['desc'], p['img'],
                                p['sid'], datetime.now().isoformat()
                            ))
                            count += 1
                        
                        # Xóa các ô trống không có trên server
                        if server_slots:
                            placeholders = ','.join(['?'] * len(server_slots))
                            delete_query = f"DELETE FROM inventory WHERE slot_number NOT IN ({placeholders})"
                            cursor.execute(delete_query, server_slots)
                        else:
                            cursor.execute("DELETE FROM inventory")
                            
                        con.commit()
                        logging.info(f"✅ Đã cập nhật {count} ô chứa hàng từ Server.")
                        return True
        except Exception as e:
            logging.error(f"❌ Lỗi sync_products_from_server: {e}")
            return False    
    def login_customer(self, login_id, password_input):
        sql = "SELECT * FROM customers WHERE phone_number = ? OR email = ?"
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                cursor.execute(sql, (login_id, login_id))
                user_row = cursor.fetchone()

                # THAY ĐỔI: So sánh trực tiếp text thuần
                if user_row and user_row['password'] == str(password_input):
                    logging.info(f"Đăng nhập thành công cho: {login_id}")
                    return {
                        "code": user_row['user_id'],
                        "name": user_row['full_name'],
                        "phone": user_row['phone_number'],
                        "email": user_row['email'],
                        "points": user_row['points']
                    }
                else:
                    logging.warning(f"Đăng nhập thất bại cho: {login_id}")
                    return None
        except Exception as e:
            logging.error(f"Lỗi DB khi đăng nhập: {e}")
            return None
    
    def update_customer_points_exact(self, user_id, new_points):
        """Hàm này dùng để đồng bộ điểm chuẩn từ Server về (Ghi đè)"""
        try:
            with self._get_connection() as con:
                con.execute("UPDATE customers SET points = ?, is_synced = 1 WHERE user_id = ?", (new_points, user_id))
                con.commit()
            logging.info(f"SYNC POINT: Đã cập nhật user {user_id} thành {new_points} điểm.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi update point user {user_id}: {e}")
            return False
        
    def get_unsynced_transactions(self):
        """Lấy danh sách đơn chưa đồng bộ. Nếu đơn lỗi, đánh dấu bỏ qua để không kẹt hệ thống."""
        try:
            with self._get_connection() as con:
                rows = con.execute("SELECT * FROM transaction_history WHERE is_synced = 0").fetchall()
                transactions = []
                
                # Danh sách các đơn lỗi cần đánh dấu bỏ qua ngay lập tức
                bad_orders = []

                for row in rows:
                    t = dict(row)
                    raw_data = t['items_detail']

                    # 1. Cố gắng đọc dữ liệu
                    try:
                        import json
                        # Ưu tiên JSON chuẩn
                        t['items'] = json.loads(raw_data)
                    except:
                        try:
                            # Dự phòng: Python string (cho các đơn cũ)
                            import ast
                            t['items'] = ast.literal_eval(raw_data)
                        except Exception as e:
                            # ==> ĐÂY LÀ CHỖ XỬ LÝ ĐƠN 38HA CỦA BẠN <==
                            print(f"\n[!!!] DATA CORRUPTED: Đơn {t['order_code']} chứa dữ liệu hỏng: {raw_data}")
                            print(f"[!!!] Bỏ qua đơn này để hệ thống tiếp tục chạy.\n")
                            
                            # Thêm vào danh sách đen để đánh dấu sync=1 (Skip)
                            bad_orders.append(t['order_code'])
                            continue 

                    # 2. Kiểm tra nếu list rỗng (sau khi parse thành công nhưng không có item)
                    if not t['items']:
                        bad_orders.append(t['order_code'])
                        continue

                    transactions.append(t)
                
                # Xử lý dứt điểm các đơn hỏng (đánh dấu là đã xử lý để không lặp lại)
                if bad_orders:
                    for code in bad_orders:
                        self.mark_transaction_as_synced(code) # Coi như đã sync (thực tế là skip)

                return transactions

        except sqlite3.Error as e:
            logging.error(f"Lỗi khi lấy unsynced transactions: {e}")
            return []
        
    def add_or_update_customer_from_server(self, server_user_data):
        user_id = server_user_data.get('user_id')
        if not user_id:
            return False
            
        sql = """
            INSERT INTO customers (user_id, full_name, phone_number, email, points, is_synced, password, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name = excluded.full_name,
                phone_number = excluded.phone_number,
                email = excluded.email,
                points = excluded.points,
                password = excluded.password,
                is_synced = 1;
        """
        try:
            with self._get_connection() as con:
                con.execute(sql, (
                    user_id,
                    server_user_data.get('full_name'),
                    server_user_data.get('phone_number'),
                    server_user_data.get('email'), 
                    server_user_data.get('points', 0),
                    server_user_data.get('password', ''), # Lấy mật khẩu do API trả về
                    datetime.now().isoformat()
                ))
            logging.info(f"Đã thêm/cập nhật user {user_id} từ server vào CSDL local.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi thêm/cập nhật user từ server: {e}")
            return False

    def generate_order_code(self):
        now = datetime.now().strftime("%Y%m%d%H%M%S")
        rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"ORD-{now}-{rand_part}"
    def get_user_current_points(self, user_id):
        """Lấy số điểm hiện tại đang lưu ở Local của user"""
        try:
            with self._get_connection() as con:
                row = con.execute("SELECT points FROM customers WHERE user_id = ?", (user_id,)).fetchone()
                return row['points'] if row else 0
        except Exception:
            return 0

    def save_transaction(self, total_amount, user_id, items_detail_str, items_sold_list):
        """
        Lưu đơn hàng vào DB Local.
        QUAN TRỌNG: Tham số thứ 2 (user_id) phải là MÃ KHÁCH HÀNG (ví dụ: local_xxx), không phải Tên.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        order_code = self.generate_order_code()
        
        # 1. Tự động chuyển danh sách sản phẩm thành JSON chuẩn (Tránh lỗi invalid syntax)
        import json
        try:
            safe_items_json = json.dumps(items_sold_list, ensure_ascii=False)
        except:
            safe_items_json = "[]"

        # 2. Xử lý logic mã khách hàng
        # Nếu user_id bị None hoặc rỗng thì lưu là "Guest"
        final_customer_id = user_id if user_id else "Guest"

        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                
                # [QUAN TRỌNG] Lưu final_customer_id vào cột customer_name
                cursor.execute("""
                    INSERT INTO transaction_history 
                    (timestamp, order_code, total_amount, customer_name, items_detail, is_synced) 
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (timestamp, order_code, total_amount, final_customer_id, safe_items_json))
                
                # 3. Trừ kho Local (Giữ nguyên logic cũ)
                for item in items_sold_list:
                    p_name = item.get('product_name') or item.get('item_name')
                    if p_name:
                        cursor.execute("""
                            UPDATE inventory 
                            SET units_left = units_left - ?, 
                                units_sold = units_sold + ? 
                            WHERE item_name = ?
                        """, (item['quantity'], item['quantity'], p_name))
                
                con.commit()
                logging.info(f"Đã lưu đơn hàng {order_code} cho khách: {final_customer_id}")
                return order_code
        except sqlite3.Error as e:
            logging.error(f"LỖI LƯU GIAO DỊCH LOCAL: {e}")
            return None
        
    def mark_transaction_as_synced(self, order_code):
        try:
            with self._get_connection() as con:
                con.execute("UPDATE transaction_history SET is_synced = 1 WHERE order_code = ?", (order_code,))
            logging.info(f"Đã đánh dấu đồng bộ thành công cho đơn hàng {order_code}.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi đánh dấu đồng bộ đơn hàng {order_code}: {e}")
            return False

    def get_unsynced_customers(self):
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
                con.cursor().execute("UPDATE customers SET points = points - ? + ?, is_synced = 0 WHERE user_id = ?", (points_used, points_earned, user_id))
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi cập nhật điểm cho user {user_id}: {e}")
            return False

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
    
    def hot_update_product(self, old_name, new_name, price, quantity):
        """Cập nhật chớp nhoáng Tên, Giá, Tồn kho không cần HTTP"""
        try:
            from datetime import datetime as _dt
            now = _dt.now().isoformat()
            with self._get_connection() as con:
                con.execute("""
                    UPDATE inventory 
                    SET item_name = ?, price = ?, units_left = ?, updated_at = ?
                    WHERE item_name = ?
                """, (new_name, price, quantity, now, old_name))
                con.commit()
            logging.info(f"HOT UPDATE: Đã đổi '{old_name}' -> '{new_name}', giá: {price}, tồn: {quantity}")
            return True
        except Exception as e:
            logging.error(f"Lỗi hot update sản phẩm: {e}")
            return False

    def get_most_recent_customer_with_face_encoding(self):
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
        try:
            with self._get_connection() as con:
                con.execute("UPDATE customers SET is_synced = 0 WHERE user_id = ?", (user_id,))
            logging.warning(f"Đã đánh dấu user {user_id} cần đồng bộ lại.")
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi đánh dấu unsynced cho user {user_id}: {e}")
            return False

db_manager = LocalDatabaseManager()