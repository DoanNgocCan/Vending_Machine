# SHOPPING_KEYPAD_APP/core/ui/thank_you_screen.py
import tkinter as tk

class ThankYouScreen(tk.Toplevel):
    """
    Màn hình cảm ơn.
    Kích hoạt việc hoàn tất giao dịch và tự động reset hệ thống sau 2 giây.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # QUAN TRỌNG: Gọi hàm hoàn tất giao dịch của controller NGAY LẬP TỨC
        self.controller._finalize_and_sync_transaction()
        
        self.geometry("1920x1080+0+0")
        self.overrideredirect(True)
        self.configure(bg="white")
        
        if self.controller.customer_name:
            thank_you_message = f"Cảm ơn {self.controller.customer_name} đã mua hàng!"
        else:
            thank_you_message = "Cảm ơn quý khách đã mua hàng!"
        
        thank_label = tk.Label(self, text=thank_you_message, font=("Verdana", 40, "bold"), fg="#FFFFFF", bg="black")
        thank_label.place(relx=0.5, rely=0.4, anchor=tk.CENTER)
        thank_label.lift()
        
        self.attributes('-alpha', 1.0)
        display_duration = 2000
        
        self.after(display_duration, self._close_and_reset)
        self.protocol("WM_DELETE_WINDOW", self._close_and_reset)

    def _close_and_reset(self):
        """
        Hàm này gọi các hàm reset trên controller và yêu cầu hiển thị
        lại màn hình chào mừng, sau đó tự hủy.
        """
        print("UI: Màn hình cảm ơn kết thúc. Bắt đầu reset toàn bộ hệ thống.")
    
        # 1. Reset trạng thái logic nghiệp vụ
        self.controller.logic.reset_all() 
        self.controller.logic.set_customer(None) 

        # 2. Reset trạng thái của chính UI
        self.controller.customer_info = None
        self.controller.customer_name = ""
        self.controller.update_welcome_message()
        self.controller._update_auth_frame_visibility()
        self.controller._deselect_product()
        self.controller.update_cart_display_handler()
    
        # 3. Yêu cầu controller quay về màn hình chào mừng
        self.controller.show_welcome_screen()
        
        # 4. Tự hủy
        if self.winfo_exists():
            self.destroy()  