# SHOPPING_KEYPAD_APP/config.py

# Cấu hình giao diện (một số có thể không dùng bởi advanced_ui_manager)
import os


WINDOW_TITLE = "Máy bán hàng tự động" # Tiêu đề chung
WINDOW_GEOMETRY = "1920x1080" # Kích thước mặc định, có thể bị override

# Thời gian hiển thị thông báo tạm thời (ms)
TEMP_MESSAGE_DURATION = 2500 # Tăng một chút cho dễ đọc

# Đường dẫn đến thư mục hình ảnh (quan trọng nếu file UI không nằm cùng cấp)
# Nếu main.py chạy từ SHOPPING_KEYPAD_APP, và images là thư mục con:
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_BASE_PATH = os.path.join(_BASE_DIR, "images") + os.sep

# Dữ liệu sản phẩm và quảng cáo (có thể chuyển từ UI vào đây để dễ quản lý)
AD_IMAGES_CONFIG = ["1.png", "2.png", "3.png", "4.png", "5.png", "6.png"]
PRODUCT_IMAGES_CONFIG = {
    "water": ("Aquafina", "water.png", 2000),
    "pepsi": ("Pepsi", "pepsi.png", 2400),
    "sting": ("Sting", "sting.png", 2100),
    "milo": ("Milo Lon", "milo.png", 2300),
    "snackTC": ("Snack Tôm Cay", "snack1.png", 2000),
    "snackTBN": ("Snack Tảo Biển Non", "snack2.png", 2000),
    "snackH": ("Snack Hành", "snack3.png", 2600),
    "snackBN": ("Snack Bắp Ngọt", "snack4.png", 2200),
    "cookie": ("Bánh Quy", "cookie.png", 2800),
    "candy": ("Kẹo Dẻo", "candy.png", 2500)
}

# --- Cấu hình MQTT ---
# Có thể ghi đè bằng biến môi trường MQTT_BROKER_HOST và MQTT_BROKER_PORT
MQTT_BROKER_HOST = "mqtt.lavaa.qzz.io"
MQTT_BROKER_PORT = 443  # Bắt buộc là 443 khi qua Cloudflare Tunnel, không dùng port mặc định 1883 được
'''MQTT_BROKER_HOST = "192.168.1.133"   #os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", "1883"))'''

# Topic MQTT cho cập nhật giá/số lượng nhanh (hot update)
MQTT_TOPIC_PRODUCT_UPDATE = "vending_machine/product/update"

# Topic MQTT báo hiệu có dữ liệu lớn cần tải qua HTTP (sản phẩm mới, ảnh...)
MQTT_TOPIC_DATA_CHANGED = "vending_machine/product/data_changed"
