import os
import subprocess
import platform
import signal

def clean_chromium_session():
    try:
        if platform.system() == "Windows":
            # Windows paths for Chrome/Chromium
            chrome_paths = [
                os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Preferences"),
                os.path.expanduser("~\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Last*"),
                os.path.expanduser("~\\AppData\\Local\\Chromium\\User Data\\Default\\Preferences"),
                os.path.expanduser("~\\AppData\\Local\\Chromium\\User Data\\Default\\Last*")
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    os.remove(path)
        else:
            # Linux paths
            os.system("rm -f ~/.config/chromium/Default/Preferences")
            os.system("rm -f ~/.config/chromium/Default/Last\\ *")
            os.system("rm -f ~/.config/google-chrome/Default/Preferences")
            os.system("rm -f ~/.config/google-chrome/Default/Last\\ *")
        print("Đã xóa session Chrome/Chromium")
    except Exception as e:
        print(f"Lỗi khi xóa session: {e}")

def close_chromium():
    try:
        # Close Chrome/Chromium on Linux
        subprocess.run(["pkill", "-f", "chromium"], check=True)
        print("Đã tắt Chrome/Chromium.")
    except subprocess.CalledProcessError:
        print("Chrome/Chromium không đang chạy hoặc không tắt được.")
    except Exception as e:
        print(f"Lỗi khi đóng trình duyệt: {e}")
def force_kill_system():
    """
    Hàm thoát khẩn cấp (Panic Button).
    Sử dụng khi ứng dụng bị treo, không phản hồi.
    """
    print("!!! HỆ THỐNG ĐANG BỊ ÉP BUỘC DỪNG KHẨN CẤP (FORCE KILL) !!!")
    
    try:
        # 1. Cố gắng tắt các tiến trình con phụ trợ trước
        if platform.system() != "Windows":
            # Tắt bàn phím ảo
            os.system("pkill onboard")
            # Tắt trình duyệt
            os.system("pkill -f chromium")
            os.system("pkill -f chrome")
            # Tắt panel nếu cần
            # os.system("pkill panel") 
            
        # 2. Tự kết liễu tiến trình chính (Python)
        # os.getpid() lấy ID của chương trình hiện tại
        # signal.SIGKILL là lệnh "giết không thương tiếc"
        os.kill(os.getpid(), signal.SIGKILL)
        
    except Exception as e:
        print(f"Lỗi khi force kill: {e}")
        # Nếu vẫn không được, dùng lệnh hệ thống cuối cùng
        os._exit(1)
def close_chrome_Win_Lin():
    """Alias for backward compatibility"""
    close_chromium()