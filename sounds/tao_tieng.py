from gtts import gTTS
import os

def phat_loa(text):
    print(f"Đang xử lý: {text}")
    
    # 1. Chuyển văn bản sang file âm thanh (tiếng Việt)
    tts = gTTS(text=text, lang='vi')
    filename = "amthanh1.mp3"
    tts.save(filename)
    
    # 2. Phát file ra loa Bluetooth
    # mpg321 là trình phát nhạc nhẹ, nó sẽ tự tìm thiết bị audio mặc định (là loa bluetooth đã kết nối)
    os.system(f"mpg321 {filename}")

# Test thử
phat_loa("Thanh toán thành công. Cảm ơn quý khách đã mua hàng.")