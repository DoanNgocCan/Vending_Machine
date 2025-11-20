# SHOPPING_KEYPAD_APP/core/ui/welcome_screen.py
import tkinter as tk
import itertools
try:
    from PIL import Image, ImageTk
    import sys
    import os
except ImportError:
    print("Vui lòng cài đặt thư viện Pillow: pip install Pillow")
    class MockImageTk:
        def PhotoImage(self, img):
            return None
    ImageTk = MockImageTk()

class WelcomeScreen(tk.Toplevel):
    """
    Màn hình quảng cáo và chào mừng.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.overrideredirect(True)
        try:
            self.attributes('-fullscreen', True)
        except tk.TclError:
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            self.geometry(f"{screen_width}x{screen_height}+0+0")
        
        self.configure(bg="white")

        clickable_frame = tk.Frame(self, bg="white")
        clickable_frame.pack(expand=True, fill="both")

        self.ad_label = tk.Label(clickable_frame, bg="white")
        self.ad_label.pack(fill="both", expand=True)

        if not self.controller.cached_ad_images:
            self.ad_label.config(text="Không có ảnh quảng cáo!", font=("Arial", 24))
        else:
            if self.controller.ad_imgs_cycle is None:
                self.controller.ad_imgs_cycle = itertools.cycle(self.controller.cached_ad_images)
            self._update_ad()

        clickable_frame.bind("<Button-1>", self._on_welcome_click)
        self.ad_label.bind("<Button-1>", self._on_welcome_click)
        
        self.protocol("WM_DELETE_WINDOW", lambda: self.controller.on_app_close(is_welcome_close=True))

    def _update_ad(self):
        if not self.winfo_exists():
            return
        try:
            img = next(self.controller.ad_imgs_cycle)
            self.ad_label.config(image=img)
            self.ad_label.image = img
            self.after(4000, self._update_ad)
        except (StopIteration, tk.TclError):
            pass

    def _on_welcome_click(self, event):
        self.controller.show_loading_screen()
        self.destroy()