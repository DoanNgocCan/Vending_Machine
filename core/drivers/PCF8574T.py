"""
PCF8574T Controller Driver

Module điều khiển khoang hàng thông qua chip PCF8574T qua giao tiếp I2C.
Hỗ trợ điều khiển 12 khoang hàng riêng biệt cho việc hiển thị trạng thái sản phẩm.

Author: CDPĐ-UIT Team
Version: 1.0
"""

import smbus2
import time
import threading
from typing import List, Dict, Optional
from config import PRODUCT_IMAGES_CONFIG


# ================================
# CONSTANTS AND CONFIGURATION
# ================================

# I2C Configuration
PCF8574_ADDRESS = 0x20  # Địa chỉ I2C của PCF8574T

# Timing Configuration
STATE_DELAY_TIME = 0.5      # Thời gian mỗi trạng thái (giây)
LED_BLINK_DELAY = 0.1       # Thời gian nhấp nháy LED
LED_PAUSE_DELAY = 0.1       # Thời gian nghỉ giữa các sản phẩm

# LED Control Mapping
# Mapping sản phẩm với byte điều khiển LED (12 LED với mã byte từ phần cứng)
PRODUCT_LED_MAPPING: Dict[str, int] = {
    "water":    0b00010001,  # P1  - Aquafina
    "pepsi":    0b00010010,  # P2  - Pepsi
    "sting":    0b00010100,  # P3  - Sting
    "milo":     0b00011000,  # P4  - Milo Lon
    "snackTC":  0b10010000,  # P5  - Snack Tôm Cay
    "snackTBN": 0b01010000,  # P6  - Snack Tảo Biển Non
    "snackH":   0b00100001,  # P7  - Snack Hành
    "snackBN":  0b00100010,  # P8  - Snack Bắp Ngọt
    "cookie":   0b00100100,  # P9  - Bánh Quy
    "candy":    0b00101000   # P10 - Kẹo Dẻo
}

# LED States
ALL_OFF_STATE = 0b00110000  # Trạng thái OFF cho tất cả LED


# ================================
# MAIN CONTROLLER CLASS
# ================================

class PCF8574Controller:
    """
    Controller class for managing PCF8574T operations via I2C.
    
    This class provides methods to control individual and display
    sequences for product selection and payment confirmation.
    """
    
    def __init__(self, address: int = PCF8574_ADDRESS) -> None:
        """
        Initialize the PCF8574T controller.
        
        Args:
            address (int): I2C address of the PCF8574T chip
        """
        self.address = address
        self.bus: Optional[smbus2.SMBus] = None
        self.is_initialized = False
        
    def initialize(self) -> bool:
        """
        Initialize I2C connection and test the PCF8574T chip.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            self.bus = smbus2.SMBus(1)  # Bus I2C của Raspberry Pi thường là 1
            # Test write để kiểm tra kết nối
            self.write_to_pcf8574(ALL_OFF_STATE)
            self.is_initialized = True
            print("PCF8574T: Khởi tạo thành công")
            return True
        except Exception as e:
            print(f"PCF8574T: Lỗi khởi tạo - {e}")
            self.is_initialized = False
            return False
    
    def write_to_pcf8574(self, data: int) -> bool:
        """
        Write data to the PCF8574T chip.
        
        Args:
            data (int): Byte data to write to the chip
            
        Returns:
            bool: True if write successful, False otherwise
        """
        if not self.is_initialized or not self.bus:
            return False
        try:
            self.bus.write_byte(self.address, data)
            return True
        except Exception as e:
            print(f"PCF8574T: Lỗi ghi dữ liệu - {e}")
            return False
    
    def turn_off_all_leds(self) -> bool:
        """
        Turn off all LEDs.
        
        Returns:
            bool: True if operation successful, False otherwise
        """
        return self.write_to_pcf8574(ALL_OFF_STATE)
    
    def turn_on_product_led(self, product_id: str) -> bool:
        """
        Turn on LED for a specific product.
        
        Args:
            product_id (str): Product ID (from "1" to "12")
            
        Returns:
            bool: True if LED turned on successfully, False otherwise
        """
        if product_id in PRODUCT_LED_MAPPING:
            led_byte = PRODUCT_LED_MAPPING[product_id]
            success = self.write_to_pcf8574(led_byte)
            if success:
                print(f"PCF8574T: Bật LED P{product_id} (0b{led_byte:08b}) cho sản phẩm {product_id}")
            return success
        else:
            print(f"PCF8574T: Không tìm thấy mapping cho sản phẩm {product_id}")
            return False
    
    def show_payment_success_sequence(self, purchased_products: List[str]) -> None:
        """
        Hiển thị chuỗi khoang hàng cho các sản phẩm đã mua.
        
        Args:
            purchased_products (List[str]): Danh sách ID sản phẩm đã mua
        """
        if not self.is_initialized:
            print("PCF8574T: Chưa khởi tạo, bỏ qua mở khoang hàng")
            return
        
        def led_sequence() -> None:
            """Internal function to run in separate thread."""
            try:
                # Tắt tất cả khoang hàng trước
                self.turn_off_all_leds()
                time.sleep(0.01)
                
                # Đếm số lượng từng loại sản phẩm
                product_count: Dict[str, int] = {}
                for product_id in purchased_products:
                    product_count[product_id] = product_count.get(product_id, 0) + 1
                
                print(f"PCF8574T: Hiển thị LED cho {len(product_count)} loại sản phẩm")
                
                # Mở khoang hàng cho từng loại sản phẩm đã mua
                for product_id, quantity in product_count.items():
                    if product_id in PRODUCT_IMAGES_CONFIG:
                        product_name = PRODUCT_IMAGES_CONFIG[product_id][0]
                        print(f"PCF8574T: {product_name} x{quantity} - LED {product_id}")
                        
                        # Mở khoang hàng cho sản phẩm này nhiều lần tương ứng với số lượng
                        for _ in range(max(1, quantity)):
                            self.turn_on_product_led(product_id)
                            time.sleep(LED_BLINK_DELAY)
                            self.turn_off_all_leds()
                            time.sleep(LED_BLINK_DELAY)
                        
                        # Pause giữa các sản phẩm khác nhau
                        time.sleep(LED_PAUSE_DELAY)
                
                print("PCF8574T: Hoàn thành hiển thị LED thanh toán")
                
            except Exception as e:
                print(f"PCF8574T: Lỗi trong chuỗi LED - {e}")
                self.turn_off_all_leds()
        
        # Chạy mở khoang hàng trong thread riêng để không block UI
        led_thread = threading.Thread(target=led_sequence, daemon=True)
        led_thread.start()
    
    def close(self) -> None:
        """
        Đóng kết nối I2C và cleanup resources.
        """
        if self.bus:
            try:
                self.turn_off_all_leds()
                self.bus.close()
                print("PCF8574T: Đã đóng kết nối")
            except Exception as e:
                print(f"PCF8574T: Lỗi khi đóng - {e}")
        self.is_initialized = False


# ================================
# GLOBAL INSTANCE AND UTILITIES
# ================================

# Instance global để sử dụng trong toàn bộ app
pcf8574_controller = PCF8574Controller()


def initialize_led_controller() -> bool:
    """
    Khởi tạo controller - được gọi từ main.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    return pcf8574_controller.initialize()


def show_payment_leds(purchased_products: List[str]) -> None:
    """
    Mở khoang hàng cho thanh toán thành công.
    
    Args:
        purchased_products (List[str]): Danh sách ID sản phẩm đã mua
    """
    pcf8574_controller.show_payment_success_sequence(purchased_products)


def close_led_controller() -> None:
    """
    Đóng controller .
    """
    pcf8574_controller.close()
