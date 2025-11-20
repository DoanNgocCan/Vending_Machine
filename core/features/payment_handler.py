# --- START OF FILE core/features/payment_handler.py (ĐÃ ĐƯỢC ĐƠN GIẢN HÓA) ---

import queue
import logging

def check_payment_queue(root, ui, shopping_logic, flask_to_tkinter_queue):
    """
    Chỉ lắng nghe tín hiệu từ web server thanh toán.
    Khi có tín hiệu 'success', gọi hàm show_thank_you_screen() của UI.
    Toàn bộ logic xử lý giao dịch sẽ do UI đảm nhiệm.
    """
    try:
        message = flask_to_tkinter_queue.get_nowait()
        
        # Đóng trình duyệt trong mọi trường hợp (thành công hoặc hủy)
        if message in ["success", "cancel"]:
            from ..utils.system_utils import close_chromium
            close_chromium()

        # Xử lý theo tín hiệu
        if message == "success":
            logging.info("PAYMENT_HANDLER: Nhận được tín hiệu thanh toán THÀNH CÔNG. Chuyển quyền xử lý cho UI...")
            # Kích hoạt màn hình cảm ơn, nơi này sẽ tự xử lý phần còn lại
            ui.show_thank_you_screen() 
            
        elif message == "cancel":
            logging.info("PAYMENT_HANDLER: Nhận được tín hiệu thanh toán BỊ HỦY.")
            # Chỉ cần hiện lại màn hình chính
            if ui.root and ui.root.winfo_exists():
                ui.root.deiconify()

    except queue.Empty:
        pass
    
    # Lên lịch kiểm tra lại sau 1 giây
    root.after(1000, lambda: check_payment_queue(root, ui, shopping_logic, flask_to_tkinter_queue))

# XÓA HOÀN TOÀN hàm background_task_handler khỏi file này.