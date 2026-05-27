# SHOPPING_KEYPAD_APP/config.py

# Cấu hình giao diện (một số có thể không dùng bởi advanced_ui_manager)
import os
from dotenv import load_dotenv


_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"))


DEVICE_ID = os.getenv("VENDING_DEVICE_ID", "VENDING_MACHINE_01")
SERVER_URL = os.getenv("VENDING_SERVER_URL", "http://localhost:8000").rstrip("/")

WINDOW_TITLE = "Máy bán hàng tự động" # Tiêu đề chung
WINDOW_GEOMETRY = "1920x1080" # Kích thước mặc định, có thể bị override

# Thời gian hiển thị thông báo tạm thời (ms)
TEMP_MESSAGE_DURATION = 2500 # Tăng một chút cho dễ đọc

# Đường dẫn đến thư mục hình ảnh (quan trọng nếu file UI không nằm cùng cấp)
# Nếu main.py chạy từ SHOPPING_KEYPAD_APP, và images là thư mục con:
IMAGE_BASE_PATH = os.path.join(_BASE_DIR, "images") + os.sep

# Dữ liệu sản phẩm và quảng cáo (có thể chuyển từ UI vào đây để dễ quản lý)
AD_IMAGES_CONFIG = ["1.png", "2.png", "3.png", "4.png", "5.png", "6.png"]

# --- Cấu hình MQTT ---
# Có thể ghi đè bằng biến môi trường MQTT_BROKER_HOST và MQTT_BROKER_PORT
MQTT_BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))

# Topic MQTT cho cập nhật giá/số lượng nhanh (hot update)
MQTT_TOPIC_PRODUCT_UPDATE = os.getenv("MQTT_TOPIC_PRODUCT_UPDATE", "vending_machine/product/update")

# Topic MQTT báo hiệu có dữ liệu lớn cần tải qua HTTP (sản phẩm mới, ảnh...)
MQTT_TOPIC_DATA_CHANGED = os.getenv("MQTT_TOPIC_DATA_CHANGED", "vending_machine/product/data_changed")

MQTT_TOPIC_FACE_SYNC = os.getenv("MQTT_TOPIC_FACE_SYNC", "vending/sync/faces")
