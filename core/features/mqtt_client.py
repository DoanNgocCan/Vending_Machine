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
import ssl  
import base64
import os
import pickle
import numpy as np

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    logging.warning("MQTT: Thư viện paho-mqtt chưa được cài đặt. Chức năng MQTT bị tắt.")

from config import (
    DEVICE_ID,
    MQTT_BROKER_HOST,
    MQTT_BROKER_PORT,
    MQTT_TOPIC_PRODUCT_UPDATE,
    MQTT_TOPIC_DATA_CHANGED,
    MQTT_TOPIC_FACE_SYNC,
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
        self._sync_timer = None
        self._face_sync_timer = None
        self._face_handler = None

    def setup(self, db_manager, api_manager,
              ui_refresh_callback=None,
              product_update_callback=None,
              face_handler=None):
        """
        Cấu hình các dependency cần thiết.

        Args:
            db_manager: Instance LocalDatabaseManager (db_manager global).
            api_manager: Instance VendingAPIManager để gọi API server.
            ui_refresh_callback: Hàm không tham số, gọi khi cần vẽ lại toàn bộ UI.
            product_update_callback: Hàm (item_name, price, quantity) để cập nhật
                                     một sản phẩm cụ thể trên UI mà không vẽ lại tất cả.
            face_handler: Hàm để xử lý dữ liệu khuôn mặt nhận được.
        """
        self._db_manager = db_manager
        self._api_manager = api_manager
        self._ui_refresh_callback = ui_refresh_callback
        self._product_update_callback = product_update_callback
        self._face_handler = face_handler

    def connect(self, broker=None, port=None):
        """
        Kết nối tới MQTT broker qua WebSockets (Cloudflare Tunnel).
        """
        if not MQTT_AVAILABLE:
            logging.warning("MQTT: paho-mqtt không khả dụng, bỏ qua kết nối.")
            return False

        # Ưu tiên giá trị truyền vào hàm, nếu không có thì dùng từ config/.env
        broker = broker or MQTT_BROKER_HOST
        port = port or MQTT_BROKER_PORT

        try:
            # 1. THÊM tham số transport="websockets"
            try:
                self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, transport="websockets")
            except AttributeError:
                # paho-mqtt < 2.0 không có CallbackAPIVersion
                self._client = mqtt.Client(transport="websockets")
            
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            # 2. Cấu hình WebSocket path (để khớp với root path của Cloudflare Tunnel)
            self._client.ws_set_options(path="/")

            # 3. Kích hoạt SSL/TLS (Bắt buộc để đi qua WSS của Cloudflare)
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

            # Khởi tạo kết nối
            self._client.connect(broker, port, keepalive=60)
            self._client.loop_start()
            logging.info(f"MQTT: Đang kết nối tới WSS broker {broker}:{port}...")
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
            print("[MQTT] Kết nối tới Broker THÀNH CÔNG và bắt đầu lắng nghe!")
            client.subscribe(MQTT_TOPIC_PRODUCT_UPDATE)
            client.subscribe(MQTT_TOPIC_DATA_CHANGED)
            client.subscribe(MQTT_TOPIC_FACE_SYNC)
            logging.info(
                f"MQTT: Đã đăng ký topic: "
                f"'{MQTT_TOPIC_PRODUCT_UPDATE}', '{MQTT_TOPIC_DATA_CHANGED}', '{MQTT_TOPIC_FACE_SYNC}'"
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
            print(f"\n[MQTT XÁC NHẬN] Nhận lệnh từ Server qua kênh '{topic}'")
            print(f"   => Dữ liệu: {payload}")

            if topic == MQTT_TOPIC_PRODUCT_UPDATE:
                self._handle_product_update(payload)
            elif topic == MQTT_TOPIC_DATA_CHANGED:
                self._handle_data_changed(payload)
            elif topic == MQTT_TOPIC_FACE_SYNC:
                self._handle_face_sync(payload)

        except json.JSONDecodeError as e:
            logging.error(f"MQTT: Lỗi giải mã JSON: {e} | raw={msg.payload}")
        except Exception as e:
            logging.error(f"MQTT: Lỗi xử lý tin nhắn: {e}")

    # ------------------------------------------------------------------
    # Xử lý từng loại tin nhắn
    # ------------------------------------------------------------------

    def _handle_product_update(self, payload):
        """Xử lý HOT UPDATE: Giá / Tồn kho / Tên sản phẩm"""
        target_device = payload.get("device_id")

        # 🛑 CHỐT CHẶN: Nếu Server có chỉ định máy nhận, mà không phải máy này -> BỎ QUA
        if target_device and target_device != DEVICE_ID:
            logging.info(f"MQTT: Bỏ qua bản tin vì dành cho máy khác ({target_device})")
            return
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
        
        # 1. FIX LỖI LÂY LAN: Kiểm tra xem lệnh này dành cho máy nào
        target_device = payload.get("device_id")
        
        # Nếu server có chỉ định thiết bị, mà không phải máy này -> BỎ QUA
        if target_device and target_device != DEVICE_ID:
            logging.info(f"MQTT: Bỏ qua data_changed vì dành cho máy khác ({target_device})")
            return

        event = payload.get("event", "unknown")
        logging.info(f"MQTT: Nhận tín hiệu '{event}'. Đang chuẩn bị HTTP Sync toàn bộ dữ liệu...")

        # 2. FIX LỖI NHÁY UI: Xóa bỏ luồng cũ nếu có luồng mới tới liên tục
        if self._sync_timer is not None:
            self._sync_timer.cancel()

        def pull_all_from_server():
            if self._db_manager:
                self._db_manager.sync_products_from_server()
                
                # Gọi refresh UI
                if self._ui_refresh_callback:
                    self._ui_refresh_callback()

        # Đặt đồng hồ đếm ngược 2.0 giây. 
        # Nếu trong 2 giây này có tin nhắn MQTT khác tới, đồng hồ trên sẽ bị hủy và đặt lại.
        # Đảm bảo UI chỉ bị load ĐÚNG 1 LẦN sau khi các gói tin đã đến hết.
        self._sync_timer = threading.Timer(2.0, pull_all_from_server)
        self._sync_timer.start()

    def _handle_face_sync(self, payload):
        """Xử lý tín hiệu 'Chuông báo' có khuôn mặt mới từ MQTT"""
        logging.info("[MQTT] Nhận tín hiệu có khách hàng đăng ký mới! Chuẩn bị Delta Sync HTTP...")
        
        # Hủy luồng cũ nếu có tín hiệu mới tới liên tục
        if self._face_sync_timer is not None:
            self._face_sync_timer.cancel()
            
        def pull_faces():
            if self._db_manager:
                self._db_manager.pull_faces_from_server(self._face_handler)
            else:
                logging.warning("MQTT: Không có db_manager để xử lý Pull HTTP.")
                
        # Gom cụm trong 2 giây. Nếu có 10 lệnh ping trong 2s, cũng chỉ gọi API 1 lần
        self._face_sync_timer = threading.Timer(2.0, pull_faces)
        self._face_sync_timer.start()

    # ------------------------------------------------------------------
    # Thuộc tính trạng thái
    # ------------------------------------------------------------------

    @property
    def is_connected(self):
        """Trả về True nếu đang kết nối với MQTT broker."""
        return self._connected


# Instance global — import và dùng ở bất kỳ đâu trong ứng dụng
mqtt_manager = MQTTClientManager()
