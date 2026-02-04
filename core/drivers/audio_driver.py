import pygame
import os
import time
import threading
from gtts import gTTS

class AudioDriver:
    def __init__(self):
        # 1. Xác định đường dẫn tuyệt đối đến thư mục assets/sounds
        # Đi từ: core/drivers/audio_driver.py -> core/drivers -> core -> ROOT -> assets/sounds
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.join(current_dir, '..', '..') 
        self.sound_dir = os.path.join(project_root,'sounds')
        
        # Tạo thư mục nếu chưa có
        if not os.path.exists(self.sound_dir):
            os.makedirs(self.sound_dir)

        # 2. Định nghĩa đường dẫn file
        self.ding_file = os.path.join(self.sound_dir, "ding.mp3")
        self.static_voice = os.path.join(self.sound_dir, "amthanh1.mp3")
        
        # Khởi tạo mixer ngay lập tức
        try:
            pygame.mixer.pre_init(44100, -16, 2, 2048) # Cấu hình chuẩn cho Pi
            pygame.mixer.init()
        except Exception as e:
            print(f"[AudioDriver] Lỗi init pygame: {e}")

    def play_thank_you_async(self, customer_name=None):
        """Hàm public để UI gọi"""
        thread = threading.Thread(
            target=self._run_audio_sequence,
            args=(customer_name,),
            daemon=True
        )
        thread.start()

    def _run_audio_sequence(self, customer_name):
        try:
            # --- BƯỚC 1: BẮT BUỘC CHẠY DING.MP3 TRƯỚC ---
            if os.path.exists(self.ding_file):
                print(f"[AudioDriver] Đang phát: {self.ding_file}")
                # Load và phát ngay
                if not pygame.mixer.get_init(): pygame.mixer.init()
                pygame.mixer.music.load(self.ding_file)
                pygame.mixer.music.play()
                
                # Vòng lặp chờ: Phải đợi Ding kêu xong mới được đi tiếp
                # Nếu không có vòng lặp này, code chạy tuột xuống dưới và load file nói đè mất tiếng Ding
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            else:
                print(f"[AudioDriver] LỖI: Không tìm thấy file {self.ding_file}")

            # Nghỉ 1 nhịp ngắn giữa tiếng Ding và tiếng Nói (0.3s)
            time.sleep(0.3)

            # --- BƯỚC 2: XỬ LÝ GIỌNG NÓI ---
            final_file_to_play = None
            voice_temp_file = os.path.join(self.sound_dir, "voice_temp.mp3")

            # Logic chọn file
            if not customer_name or customer_name == "Khách vãng lai":
                # A. Khách vãng lai -> Dùng file có sẵn (amthanh1.mp3)
                print("[AudioDriver] -> Chế độ: Khách vãng lai (Dùng file sẵn)")
                if os.path.exists(self.static_voice):
                    final_file_to_play = self.static_voice
                else:
                    print(f"[AudioDriver] LỖI: Không tìm thấy file {self.static_voice}")
            else:
                # B. Khách quen -> Tạo file giọng nói mới
                print(f"[AudioDriver] -> Chế độ: Khách quen ({customer_name})")
                try:
                    short_name = customer_name.split()[-1]
                    text = f"Thanh toán thành công. Cảm ơn quý khách {customer_name} đã mua hàng."
                    
                    tts = gTTS(text=text, lang='vi')
                    tts.save(voice_temp_file)
                    final_file_to_play = voice_temp_file
                except Exception as e:
                    print(f"[AudioDriver] Lỗi tạo TTS: {e}. Quay về dùng file cũ.")
                    final_file_to_play = self.static_voice

            # --- BƯỚC 3: PHÁT GIỌNG NÓI ---
            if final_file_to_play and os.path.exists(final_file_to_play):
                print(f"[AudioDriver] Đang phát giọng nói: {final_file_to_play}")
                pygame.mixer.music.load(final_file_to_play)
                pygame.mixer.music.play()
                
                # Chờ nói xong
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)

                # Xóa file tạm (nếu là file temp)
                if final_file_to_play == voice_temp_file:
                    pygame.mixer.music.unload()
                    try:
                        os.remove(voice_temp_file)
                    except: pass
            
        except Exception as e:
            print(f"[AudioDriver] Lỗi luồng phát: {e}")

    def stop_audio(self):
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()