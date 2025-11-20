from flask import Flask, request, jsonify, render_template
from payos import PayOS, ItemData, PaymentData
import time
import threading
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Cấu hình PayOS

#QR cua LAN
client_id = os.getenv("PAYOS_CLIENT_ID")
api_key = os.getenv("PAYOS_API_KEY")
checksum_key = os.getenv("PAYOS_CHECKSUM_KEY")

payos = PayOS(client_id, api_key, checksum_key)

app = Flask(__name__, static_url_path="", static_folder="public")
YOUR_DOMAIN = "http://localhost:5000"

# Hàng đợi dùng để gửi tín hiệu từ Flask về Tkinter
shared_queue = None

def set_shared_queue(queue_instance):
    global shared_queue
    shared_queue = queue_instance

@app.route("/payment-success/<int:order_code>")
def payment_success(order_code):
    print("Flask: Đã nhận yêu cầu thành công cho order", order_code)
    if shared_queue:
        shared_queue.put("success")
        print("Flask: Đã gửi 'success' vào shared_queue")
    else:
        print("Flask: shared_queue chưa được gán!")
    return "", 204

@app.route("/cancel")
def payment_cancel():
    print("Flask: Khách đã hủy thanh toán.")
    if shared_queue:
        shared_queue.put("cancel")
        print("Flask: Đã gửi 'cancel' vào shared_queue")
    else:
        print("Flask: shared_queue chưa được gán!")
    return "", 204

@app.route("/create-payment-link", methods=["POST"])
def create_payment_link():
    try:
        if not request.is_json:
            return jsonify({"error": "Request must be JSON"}), 400

        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON data"}), 400

        total_amount = int(data.get("amount", 0))
        items_data = data.get("items", [])

        if total_amount <= 0:
            return jsonify({"error": "Invalid amount"}), 400

        for item in items_data:
            if "quantity" not in item or "price" not in item:
                return jsonify({"error": "Each item must have quantity and price"}), 400

        items = [
            ItemData(
                name=item.get("name", "Item"),  # ✅ lấy tên đúng từ client
                quantity=int(item["quantity"]),
                price=int(item["price"])
            ) for item in items_data
        ]

        order_code = int(time.time())

        payment_data = PaymentData(
            orderCode=order_code,
            amount=total_amount,
            description="Thanh toan don hang",
            items=items,
            cancelUrl=YOUR_DOMAIN + "/cancel",
            returnUrl=YOUR_DOMAIN + f"/payment-success/{order_code}",  # route mới
        )

        payment_link_response = payos.createPaymentLink(payment_data)
        return jsonify({"checkoutUrl": payment_link_response.checkoutUrl}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def run_flask_app():
    """Chạy Flask app - tương thích với code cũ"""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

# Cho phép main.py gọi set_shared_queue và run_flask_app
__all__ = ["app", "set_shared_queue", "run_flask_app"]
