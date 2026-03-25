# -*- coding: utf-8 -*-
# File: core/features/mqtt_client.py
"""
Module quản lý kết nối MQTT cho máy bán hàng tự động.

Chức năng:
- Kết nối tới MQTT broker khi khởi động.
- Đăng ký (subscribe) 2 topic:
    * vending_machine/product/update   → Cập nhật giá/số lượng nhanh (hot update)
    * vending_machine/product/data_changed → Báo hiệu sản phẩm mới/thay đổi lớn → tải qua HTTP
- Xử lý tin nhắn nhận được và cập nhật DB cục bộ + giao diện.
- Graceful fallback nếu MQTT broker không khả dụng.
"""

import json
import logging
import threading

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logging.warning("MQTT: Thư viện paho-mqtt chưa được cài đặt. Chức năng MQTT bị tắt.")

from config import (
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_TOPIC_PRODUCT_UPDATE,
    MQTT_TOPIC_DATA_CHANGED,
)


class MQTTClientManager:
    """
    Quản lý kết nối MQTT và xử lý tin nhắn cho máy bán hàng.

    Sử dụng:
        mqtt_manager = MQTTClientManager()
        mqtt_manager.setup(db_manager, api_manager,
                           ui_refresh_callback=...,
                           product_update_callback=...)
        mqtt_manager.connect()
    """

    def __init__(self):
        self._client = None
        self._connected = False
        self._db_manager = None
        self._api_manager = None
        # Callback được gọi để làm mới toàn bộ lưới sản phẩm trên UI
        self._ui_refresh_callback = None
        # Callback được gọi với (item_name, price, quantity) khi nhận hot update
        self._product_update_callback = None

    def setup(self, db_manager, api_manager,
              ui_refresh_callback=None,
              product_update_callback=None):
        """
        Cấu hình các dependency cần thiết.

        Args:
            db_manager: Instance LocalDatabaseManager (db_manager global).
            api_manager: Instance VendingAPIManager để gọi API server.
            ui_refresh_callback: Hàm không tham số, gọi khi cần vẽ lại toàn bộ UI.
            product_update_callback: Hàm (item_name, price, quantity) để cập nhật
                                     một sản phẩm cụ thể trên UI mà không vẽ lại tất cả.
        """
        self._db_manager = db_manager
        self._api_manager = api_manager
        self._ui_refresh_callback = ui_refresh_callback
        self._product_update_callback = product_update_callback

    def connect(self, broker=None, port=None):
        """
        Kết nối tới MQTT broker.

        Returns:
            True nếu kết nối thành công, False nếu thất bại hoặc MQTT không khả dụng.
        """
        if not MQTT_AVAILABLE:
            logging.warning("MQTT: paho-mqtt không khả dụng, bỏ qua kết nối.")
            return False

        broker = broker or MQTT_BROKER_HOST
        port = port or MQTT_BROKER_PORT

        try:
            try:
                self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            except AttributeError:
                # paho-mqtt < 2.0 không có CallbackAPIVersion
                self._client = mqtt.Client()
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            self._client.connect(broker, port, keepalive=60)
            self._client.loop_start()
            logging.info(f"MQTT: Đang kết nối tới broker {broker}:{port}...")
            return True
        except Exception as e:
            logging.warning(
                f"MQTT: Không thể kết nối tới broker {broker}:{port}: {e}. "
                f"Hệ thống sẽ dùng HTTP polling thay thế."
            )
            return False

    def disconnect(self):
        """Ngắt kết nối khỏi MQTT broker một cách an toàn."""
        if self._client:
            try:
                self._client.loop_stop()
                self._client.disconnect()
                logging.info("MQTT: Đã ngắt kết nối broker.")
            except Exception as e:
                logging.error(f"MQTT: Lỗi khi ngắt kết nối: {e}")

    # ------------------------------------------------------------------
    # Callbacks nội bộ của paho-mqtt
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            logging.info("MQTT: Kết nối broker thành công!")
            # Đăng ký các topic ngay sau khi kết nối thành công
            print("✅ [MQTT] Kết nối tới Broker THÀNH CÔNG và bắt đầu lắng nghe!")
            client.subscribe(MQTT_TOPIC_PRODUCT_UPDATE)
            client.subscribe(MQTT_TOPIC_DATA_CHANGED)
            logging.info(
                f"MQTT: Đã đăng ký topic: "
                f"'{MQTT_TOPIC_PRODUCT_UPDATE}', '{MQTT_TOPIC_DATA_CHANGED}'"
            )
        else:
            logging.error(f"MQTT: Kết nối thất bại, mã lỗi: {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            logging.warning(
                f"MQTT: Mất kết nối không mong muốn (rc={rc}). "
                f"paho-mqtt sẽ tự thử kết nối lại."
            )

    def _on_message(self, client, userdata, msg):
        """Điểm vào xử lý tất cả tin nhắn MQTT nhận được."""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode("utf-8"))
            logging.info(f"MQTT: Nhận tin nhắn từ topic '{topic}': {payload}")
            print(f"\n[🚀 MQTT XÁC NHẬN] Nhận lệnh từ Server qua kênh '{topic}'")
            print(f"   => Dữ liệu: {payload}\n")

            if topic == MQTT_TOPIC_PRODUCT_UPDATE:
                self._handle_product_update(payload)
            elif topic == MQTT_TOPIC_DATA_CHANGED:
                self._handle_data_changed(payload)
        except json.JSONDecodeError as e:
            logging.error(f"MQTT: Lỗi giải mã JSON: {e} | raw={msg.payload}")
        except Exception as e:
            logging.error(f"MQTT: Lỗi xử lý tin nhắn: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Xử lý từng loại tin nhắn
    # ------------------------------------------------------------------

    def _handle_product_update(self, payload):
        """Xử lý HOT UPDATE: Giá / Tồn kho / Tên sản phẩm"""
        old_name = payload.get("old_name")
        new_name = payload.get("new_name")
        price = payload.get("price")
        units_left = payload.get("units_left")

        if not old_name or not new_name:
            logging.warning("MQTT: Payload thiếu old_name hoặc new_name.")
            return

        # 1. Cập nhật DB cục bộ
        if self._db_manager:
            self._db_manager.hot_update_product(old_name, new_name, price, units_left)

        # 2. Cập nhật UI (gọi hot_update_ui truyền 4 tham số)
        if self._product_update_callback:
            self._product_update_callback(old_name, new_name, price, units_left)

    def _handle_data_changed(self, payload):
        """Xử lý khi Server Tạo mới / Xóa sản phẩm / Đổi ảnh"""
        event = payload.get("event", "unknown")
        logging.info(f"MQTT: Nhận tín hiệu '{event}'. Đang HTTP Sync toàn bộ dữ liệu...")

        # Không gọi API lẻ nữa, gọi luôn HTTP Sync tổng (vì ảnh hưởng giao diện 10 ô)
        def pull_all_from_server():
            if self._db_manager:
                self._db_manager.sync_products_from_server()
                if self._ui_refresh_callback:
                    self._ui_refresh_callback()

        t = threading.Thread(target=pull_all_from_server, daemon=True)
        t.start()


    # ------------------------------------------------------------------
    # Thuộc tính trạng thái
    # ------------------------------------------------------------------

    @property
    def is_connected(self):
        """Trả về True nếu đang kết nối với MQTT broker."""
        return self._connected


# Instance global — import và dùng ở bất kỳ đâu trong ứng dụng
mqtt_manager = MQTTClientManager()
