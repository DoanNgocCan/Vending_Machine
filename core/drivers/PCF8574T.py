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
SLOT_LED_MAPPING: Dict[str, int] = {
    "1":  0b00010001,  # Khoang 1
    "2":  0b00010010,  # Khoang 2
    "3":  0b00010100,  # Khoang 3
    "4":  0b00011000,  # Khoang 4
    "5":  0b10010000,  # Khoang 5
    "6":  0b01010000,  # Khoang 6
    "7":  0b00100001,  # Khoang 7
    "8":  0b00100010,  # Khoang 8
    "9":  0b00100100,  # Khoang 9
    "10": 0b00101000   # Khoang 10
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
    
    def turn_on_product_led(self, slot_id: str) -> bool:
        """
        Turn on LED for a specific product.
        
        Args:
            slot_id (str): Slot ID (from "1" to "10")
            
        Returns:
            bool: True if LED turned on successfully, False otherwise
        """
        if slot_id in SLOT_LED_MAPPING:
            led_byte = SLOT_LED_MAPPING[slot_id]
            success = self.write_to_pcf8574(led_byte)
            if success:
                print(f"PCF8574T: Mở khoang {slot_id} (0b{led_byte:08b})")
            return success
        else:
            print(f"PCF8574T: Không tìm thấy mapping cho khoang {slot_id}")
            return False
    
    def show_payment_success_sequence(self, purchased_slots: List[str]) -> None:
        if not self.is_initialized:
            print("PCF8574T: Chưa khởi tạo, bỏ qua mở khoang hàng")
            return
        
        def led_sequence() -> None:
            try:
                self.turn_off_all_leds()
                time.sleep(0.5)
                
                # Đếm số lượng cần mở cho từng khoang
                slot_count: Dict[str, int] = {}
                for slot in purchased_slots:
                    slot_count[slot] = slot_count.get(slot, 0) + 1
                
                # Mở khoang trực tiếp, không check CONFIG nữa
                for slot_id, quantity in slot_count.items():
                    print(f"PCF8574T: Kích hoạt khoang {slot_id} x{quantity} lần")
                    for _ in range(max(1, quantity)):
                        self.turn_on_product_led(slot_id)
                        time.sleep(LED_BLINK_DELAY)
                        self.turn_off_all_leds()
                        time.sleep(LED_BLINK_DELAY)
                    
                    time.sleep(LED_PAUSE_DELAY)
            except Exception as e:
                print(f"PCF8574T: Lỗi trong chuỗi LED - {e}")
                self.turn_off_all_leds()
                
        threading.Thread(target=led_sequence, daemon=True).start()
    
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
