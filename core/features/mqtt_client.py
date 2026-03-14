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
        """
        Xử lý cập nhật giá/số lượng nhanh (Requirement 2A).

        Payload mẫu:
            {"item_name": "Aquafina", "price": 11000, "quantity": 50}
        hoặc dùng product_id thay cho item_name:
            {"product_id": "Aquafina", "price": 11000, "quantity": 50}
        """
        item_name = payload.get("item_name") or payload.get("product_id")
        price = payload.get("price")
        quantity = payload.get("quantity")

        if not item_name:
            logging.warning("MQTT: Payload product/update thiếu 'item_name' hoặc 'product_id'.")
            return

        # 1. Cập nhật DB cục bộ
        if self._db_manager:
            self._db_manager.update_product_price_quantity(item_name, price, quantity)

        # 2. Cập nhật UI
        if self._product_update_callback:
            # Cập nhật đúng nút sản phẩm mà không vẽ lại toàn bộ lưới
            self._product_update_callback(item_name, price, quantity)
        elif self._ui_refresh_callback:
            # Fallback: vẽ lại toàn bộ lưới nếu không có callback riêng
            self._ui_refresh_callback()

    def _handle_data_changed(self, payload):
        """
        Xử lý tín hiệu có sản phẩm mới / thay đổi dữ liệu lớn (Requirement 2B).

        Payload mẫu:
            {"event": "new_product_added", "product_id": "pepsi-456"}

        Luồng:
            1. Nhận tín hiệu MQTT nhẹ.
            2. Gọi HTTP GET /api/products/{product_id} để lấy đầy đủ thông tin.
            3. Tải ảnh về máy (nếu có image_url).
            4. Lưu vào DB cục bộ.
            5. Làm mới UI.
        """
        product_id = payload.get("product_id")
        if not product_id:
            logging.warning("MQTT: Payload data_changed thiếu 'product_id'.")
            return

        event = payload.get("event", "unknown")
        logging.info(f"MQTT: Nhận tín hiệu '{event}' cho sản phẩm ID='{product_id}'. "
                     f"Đang tải dữ liệu đầy đủ qua HTTP...")

        # Chạy trong thread riêng để không chặn vòng lặp MQTT
        t = threading.Thread(
            target=self._fetch_and_update_product,
            args=(product_id,),
            daemon=True,
        )
        t.start()

    def _fetch_and_update_product(self, product_id):
        """
        Tải dữ liệu đầy đủ của sản phẩm từ server qua HTTP rồi cập nhật DB và UI.
        Chạy trong background thread.
        """
        if not self._api_manager:
            logging.error("MQTT: Chưa cấu hình api_manager, không thể tải dữ liệu sản phẩm.")
            return

        # 1. Lấy thông tin đầy đủ sản phẩm
        product_data = self._api_manager.get_product_by_id(product_id)
        if not product_data:
            logging.error(f"MQTT: Không thể lấy dữ liệu sản phẩm ID={product_id} từ server.")
            return

        # 2. Tải ảnh về máy nếu server cung cấp URL ảnh
        image_url = product_data.get("image_url")
        local_image_path = None
        if image_url:
            item_name = product_data.get("item_name", str(product_id))
            local_image_path = self._api_manager.download_product_image(image_url, item_name)

        # 3. Lưu vào DB cục bộ
        if self._db_manager:
            self._db_manager.upsert_product(product_data, local_image_path)

        # 4. Làm mới giao diện
        if self._ui_refresh_callback:
            self._ui_refresh_callback()

    # ------------------------------------------------------------------
    # Thuộc tính trạng thái
    # ------------------------------------------------------------------

    @property
    def is_connected(self):
        """Trả về True nếu đang kết nối với MQTT broker."""
        return self._connected


# Instance global — import và dùng ở bất kỳ đâu trong ứng dụng
mqtt_manager = MQTTClientManager()
