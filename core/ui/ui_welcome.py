# SHOPPING_KEYPAD_APP/core/ui/ui_welcome.py
import tkinter as tk
import itertools
from core.features.background_sync import sync_manager
try:
    from PIL import Image, ImageTk
    import sys
    import os
except ImportError:
    class MockImageTk:
        def PhotoImage(self, img): return None
    ImageTk = MockImageTk()

class WelcomeScreen(tk.Toplevel):
    """
    Màn hình quảng cáo và chào mừng.
    Có cơ chế 'Warm-up' để đảm bảo nhận cảm ứng chính xác trên Raspberry Pi.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        print("WELCOME: Kích hoạt đồng bộ dữ liệu (Giá/Tồn kho) từ Server...")
        sync_manager.sync_now()
        self.controller.stop_camera_service()

        # Cấu hình cửa sổ
        try:
            self.attributes('-fullscreen', True)
            self.attributes('-topmost', True) # Luôn nằm trên cùng
        except tk.TclError:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            self.geometry(f"{screen_width}x{screen_height}+0+0")
        
        self.configure(bg="white")
        
        # Frame chính
        self.main_frame = tk.Frame(self, bg="white")
        self.main_frame.pack(expand=True, fill="both")

        self.ad_label = tk.Label(self.main_frame, bg="white")
        self.ad_label.pack(fill="both", expand=True)

        # --- TRẠNG THÁI KHỞI ĐỘNG (WARM-UP) ---
        # Lúc mới hiện lên, CHƯA cho phép click ngay để tránh lọt sự kiện
        self.can_interact = False
        
        # Hiển thị ảnh đầu tiên hoặc thông báo
        if not self.controller.cached_ad_images:
            self.ad_label.config(text="Đang khởi tạo hệ thống...", font=("Arial", 30))
        else:
            # Nếu có ảnh, hiển thị ảnh đầu tiên
            if self.controller.ad_imgs_cycle is None:
                self.controller.ad_imgs_cycle = itertools.cycle(self.controller.cached_ad_images)
            self._update_ad()

        # --- QUY TRÌNH KÍCH HOẠT AN TOÀN ---
        # 1. Ngay lập tức ép focus lần 1
        self.lift()
        self.focus_force()
        
        # 2. Sau 500ms: Ép focus lần 2 (để chắc chắn Window Manager đã nhận diện)
        self.after(500, self._force_focus_retry)

        # 3. Sau 2 giây: Mới CHÍNH THỨC nhận cảm ứng (Safe Zone)
        # Thời gian này đủ để ngón tay người dùng rời khỏi màn hình từ thao tác trước
        # và đủ để OS cấp quyền điều khiển hoàn toàn.
        self.after(1000, self._enable_interaction)

        self.protocol("WM_DELETE_WINDOW", lambda: self.controller.on_app_close(is_welcome_close=True))

    def _force_focus_retry(self):
        """Cố gắng lấy quyền điều khiển một lần nữa"""
        if self.winfo_exists():
            self.lift()
            self.focus_force()
            # print("UI-WELCOME: Re-forcing focus...")

    def _enable_interaction(self):
        """Kích hoạt khả năng cảm ứng"""
        if not self.winfo_exists(): return
        
        self.can_interact = True
        
        # Bind sự kiện Click cho TOÀN BỘ các thành phần
        self.bind("<Button-1>", self._on_welcome_click)
        self.main_frame.bind("<Button-1>", self._on_welcome_click)
        self.ad_label.bind("<Button-1>", self._on_welcome_click)
        
        # Nếu không có ảnh quảng cáo, đổi text mời gọi
        if not self.controller.cached_ad_images:
            self.ad_label.config(text="CHẠM ĐỂ BẮT ĐẦU MUA HÀNG")
            
        print("UI-WELCOME: Đã sẵn sàng nhận cảm ứng (Interaction Enabled).")

    def _update_ad(self):
        if not self.winfo_exists(): return
        try:
            img = next(self.controller.ad_imgs_cycle)
            self.ad_label.config(image=img)
            self.ad_label.image = img
            # Chạy slide ảnh mỗi 4 giây
            self.after(4000, self._update_ad)
        except (StopIteration, tk.TclError):
            pass

    def _on_welcome_click(self, event):
        """Xử lý sự kiện chạm màn hình"""
        if not self.winfo_exists(): return
        
        # Nếu chưa hết thời gian chờ (warm-up), bỏ qua cú click
        if not self.can_interact:
            print("UI-WELCOME: Click bị từ chối do đang khởi tạo (Warm-up phase).")
            return

        # Ngắt sự kiện để tránh click đúp
        try:
            self.unbind("<Button-1>")
            self.main_frame.unbind("<Button-1>")
            self.ad_label.unbind("<Button-1>")
        except Exception: pass

        print("UI: Màn hình Welcome đã được chạm! Chuyển cảnh...")
        self.controller.show_loading_screen()
        self.destroy()