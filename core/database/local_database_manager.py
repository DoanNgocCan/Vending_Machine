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
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS inventory (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT UNIQUE,
                        price REAL DEFAULT 0,
                        units_sold INTEGER DEFAULT 0,
                        units_left INTEGER DEFAULT 0,
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
            
            # 2. LUỒNG 1: Đẩy Config lên Server
            t1 = threading.Thread(target=self.push_config_to_server, daemon=True)
            t1.start()

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
        
    def register_customer(self, name, phone, dob, password, face_encoding=None):
        try:
            with self._get_connection() as con:
                cur = con.cursor()
                cur.execute("SELECT 1 FROM customers WHERE phone_number = ?", (phone,))
                if cur.fetchone():
                    return {"error": "duplicate_phone"}
        except sqlite3.Error:
            pass 
        user_id = f"local_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now().isoformat()
        
        sql = "INSERT INTO customers (user_id, full_name, phone_number, birthday, password, created_at, face_encoding, is_synced) VALUES (?, ?, ?, ?, ?, ?, ?, 0)"
        try:
            with self._get_connection() as con:
                con.execute(sql, (user_id, name, phone, dob, password, created_at, face_encoding))
                con.commit()
            logging.info(f"Đã đăng ký thành công cho: {name}")
            return {"code": user_id, "name": name, "phone": phone, "points": 0}
        except sqlite3.IntegrityError:
            return {"error": "duplicate_phone"}
        except sqlite3.Error as e:
            logging.error(f"Lỗi DB khi đăng ký khách hàng: {e}")
            return {"error": "db_error"}

    def sync_customer_to_server(self, name, phone, dob, password, user_id):
        logging.info(f"SYNC: Bắt đầu đồng bộ user '{name}' (local_id={user_id})...")
        dob_for_api = None
        if dob:
            sep = '/' if '/' in dob else '-'
            try:
                parts = dob.split(sep)
                day, month, year = (parts[0], parts[1], parts[2]) if len(parts[0]) == 2 else (parts[2], parts[1], parts[0])
                dob_for_api = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            except Exception:
                dob_for_api = None

        try:
            from core.features.api_manager import api_manager
        except Exception as e:
            logging.error(f"SYNC: Không import được api_manager: {e}")
            return

        server_customer = api_manager.register_customer(name, phone, dob_for_api, password, user_id)
        
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
                rows = con.execute("SELECT item_name, units_left, price FROM inventory").fetchall()
                for r in rows:
                    stock_map[r['item_name']] = {
                        'qty': r['units_left'],
                        'price': r['price']
                    }
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi lấy map tồn kho: {e}")
        return stock_map

    def push_config_to_server(self):
        return

    def sync_products_from_server(self):
        """
        [FIX] Sử dụng requests.Session() để tắt trust_env
        """
        get_url = f"{SERVER_URL}/api/products"
        logging.info(f"🔄 Đang đồng bộ kho từ Server cho máy: {DEVICE_ID}...")

        try:
            # --- [SỬA LỖI TẠI ĐÂY] ---
            s = requests.Session()
            s.trust_env = False
            
            response = s.get(get_url, headers=API_HEADERS, timeout=10)
            # -------------------------
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    server_products = data.get('products', [])
                    
                    with self._get_connection() as con:
                        cursor = con.cursor()
                        count = 0
                        
                        for p in server_products:
                            server_qty = p.get('units_left')
                            if server_qty is None:
                                server_qty = p.get('quantity', 0)
                            cursor.execute("""
                                INSERT INTO inventory (item_name, price, cost_price, units_left, description)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(item_name) DO UPDATE SET
                                    price = excluded.price,
                                    cost_price = excluded.cost_price,
                                    units_left = excluded.units_left,
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
        sql = "SELECT * FROM customers WHERE phone_number = ?"
        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                cursor.execute(sql, (phone,))
                user_row = cursor.fetchone()

                if user_row and user_row['password'] == password_input:
                    logging.info(f"Đăng nhập thành công cho SĐT: {phone}")
                    return {
                        "code": user_row['user_id'],
                        "name": user_row['full_name'],
                        "phone": user_row['phone_number'],
                        "points": user_row['points']
                    }
                else:
                    return None
        except Exception as e:
            logging.error(f"Lỗi DB khi đăng nhập: {e}", exc_info=True)
            return None
    
    def add_or_update_customer_from_server(self, server_user_data):
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
                
                cursor.execute("""
                    INSERT INTO transaction_history 
                    (timestamp, order_code, total_amount, customer_name, items_detail, is_synced) 
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (timestamp, order_code, total_amount, customer_name_str, items_detail_str))
                
                for item in items_sold_list:
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
                con.cursor().execute("UPDATE customers SET points = points - ? + ? WHERE user_id = ?", (points_used, points_earned, user_id))
            return True
        except sqlite3.Error as e:
            logging.error(f"Lỗi khi cập nhật điểm cho user {user_id}: {e}")
            return False
    
    def initialize_inventory(self):
        try:
            from config import PRODUCT_IMAGES_CONFIG
        except ImportError:
            return

        try:
            with self._get_connection() as con:
                cursor = con.cursor()
                count = 0
                for key, (name, image_file, default_price) in PRODUCT_IMAGES_CONFIG.items():
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