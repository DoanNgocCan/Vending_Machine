# --- START OF FILE core/features/face_recognition_handler.py (ĐÃ SỬA LỖI & TÁI CẤU TRÚC) ---

import threading
import time
import os
import pickle
import numpy as np
from collections import Counter

try:
    import cv2
except Exception:
    cv2 = None

try:
    import faiss
except Exception:
    faiss = None

try:
    from core.Camera_AI.model import ModelEmbedding, MediaPipeFaceDetector
except Exception:
    ModelEmbedding = None
    MediaPipeFaceDetector = None

# Đường dẫn thống nhất
CACHE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Camera_AI', 'database', 'face_cache_edgeface_base.pkl'))
RECOGNITION_TIME_LIMIT = 5.0
MAX_EMBS = 100
SIM_THRESHOLD = 0.6
BLUR_THRESHOLD = 20.0
BRIGHTNESS_MIN = 15
BRIGHTNESS_MAX = 240
CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720
TARGET_FPS = 30

class FaceRecognitionHandler:
    def __init__(self):
        print("FaceRecognitionHandler khởi tạo (background 5s recognition).")

        self._reset_cache_attributes()
        
        # Tải cache lần đầu tiên
        self._load_cache()

        # Chuẩn bị model + detector
        self._detector = None
        self._embedder = None
        if ModelEmbedding and MediaPipeFaceDetector:
            try:
                self._detector = MediaPipeFaceDetector()
                self._embedder = ModelEmbedding()
            except Exception as e:
                print(f"[FR] Lỗi khởi tạo model/detector: {e}")
        else:
            print("[FR] Cảnh báo: Thiếu ModelEmbedding hoặc MediaPipeFaceDetector.")

    def _reset_cache_attributes(self):
        """Helper để reset tất cả các thuộc tính liên quan đến cache."""
        self._cache_loaded = False
        self._embeddings = None
        self._labels = []
        self._name_map = {}
        self._faiss_index = None
        self._dim = None
        self._faiss_id_to_name = {}

    def reload_cache(self):
        """
        Tải lại dữ liệu cache từ file .pkl.
        Đây là phương thức public được gọi từ bên ngoài.
        """
        print("[FR_HANDLER] Yêu cầu tải lại dữ liệu cache nhận diện...")
        self._load_cache()

    def _load_cache(self):
        """
        Hàm nội bộ để đọc file cache và xây dựng index.
        """
        # Reset trạng thái trước khi tải
        self._reset_cache_attributes()
        
        if not os.path.exists(CACHE_FILE):
            print(f"[FR] Cache không tồn tại: {CACHE_FILE}")
            return
            
        if faiss is None:
            print('[FR] Cảnh báo: Thiếu thư viện FAISS, không thể dựng index nhận diện.')
            return

        try:
            with open(CACHE_FILE, 'rb') as f:
                cache = pickle.load(f)
            
            embs = cache.get('embeddings')
            labels = cache.get('labels')
            name_map = cache.get('name_map') or {}

            if isinstance(embs, list):
                embs = np.array(embs, dtype='float32')

            if not isinstance(embs, np.ndarray) or embs.size == 0:
                print('[FR] Cache embeddings rỗng hoặc không hợp lệ.')
                return

            self._embeddings = embs.astype('float32')
            self._labels = np.array(labels) if labels is not None else np.zeros(len(embs))
            self._name_map = name_map
            self._dim = self._embeddings.shape[1]
            
            # Xây dựng FAISS index
            index = faiss.IndexHNSWFlat(self._dim, 32)
            normalized_embs = self._embeddings.copy() # Tạo bản sao để normalize
            faiss.normalize_L2(normalized_embs)
            index.add(normalized_embs)
            
            # Map faiss internal id -> name theo labels
            for i in range(len(self._embeddings)):
                label = self._labels[i]
                name = self._name_map.get(label, 'Unknown')
                self._faiss_id_to_name[i] = name
            
            self._faiss_index = index
            self._cache_loaded = True
            print(f"[FR] Đã load cache và dựng index thành công: {self._embeddings.shape[0]} embeddings.")
        except Exception as e:
            print(f"[FR] Lỗi nghiêm trọng khi load cache hoặc dựng index: {e}")
            self._reset_cache_attributes() # Reset lại nếu có lỗi

    # --- Các phương thức còn lại (start_recognition, _perform_recognition, ...) giữ nguyên ---
    # Bạn có thể copy-paste chúng vào đây hoặc chỉ thay thế các hàm ở trên.
    # Để chắc chắn, tôi sẽ cung cấp lại toàn bộ phần còn lại.

    def start_recognition(self, completion_callback, time_limit: float = 5.0, full_time: bool = True):
        self._time_limit = max(0.5, float(time_limit))
        self._full_time = bool(full_time)
        print(f"HANDLER: Bắt đầu nhận diện nền (time_limit={self._time_limit}s, full_time={self._full_time})...")
        t = threading.Thread(target=self._run_in_thread, args=(completion_callback,), daemon=True)
        t.start()

    def _run_in_thread(self, callback):
        user_id = self._perform_recognition()
        try:
            callback(user_id)
        except Exception as e:
            print(f"[FR] Lỗi callback: {e}")

    def _perform_recognition(self):
        if not self._cache_loaded or self._faiss_index is None:
            print('[FR] Cache chưa được tải hoặc index FAISS chưa sẵn sàng. Bỏ qua nhận diện.')
            return None
        if cv2 is None or self._detector is None or self._embedder is None:
            print('[FR] Thiếu cv2, detector hoặc embedder. Bỏ qua nhận diện.')
            return None

        cap = None
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print('[FR] Không mở được camera.')
                return None
            print('[FR] Camera background recognition START.')

            start = time.time()
            collected_embs = []
            target_end = start + self._time_limit

            while time.time() < target_end:
                ret, frame = cap.read()
                if not ret: continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                focus_val = cv2.Laplacian(gray, cv2.CV_64F).var()
                brightness = gray.mean()
                if focus_val < BLUR_THRESHOLD or brightness < BRIGHTNESS_MIN or brightness > BRIGHTNESS_MAX:
                    continue

                faces = self._detector.detect(frame)
                if not faces: continue
                
                x1, y1, x2, y2 = faces[0]
                face_img = frame[y1:y2, x1:x2]
                if face_img.size == 0: continue

                if len(collected_embs) >= MAX_EMBS and not self._full_time:
                    break 
                
                if len(collected_embs) < MAX_EMBS:
                    try:
                        emb = self._embedder.get_embedding(face_img)
                        if isinstance(emb, np.ndarray) and emb.size > 0:
                            collected_embs.append(emb[0] if emb.ndim == 2 else emb)
                    except Exception:
                        continue
            
            if not collected_embs:
                print('[FR] Không thu được embedding nào hợp lệ.')
                return None
            
            # Nhận diện dựa trên embedding thu thập được
            name_counter = Counter()
            for emb in collected_embs:
                query = np.array([emb], dtype='float32')
                faiss.normalize_L2(query)
                D, I = self._faiss_index.search(query, 1)
                
                best_idx = I[0][0]
                best_dist = D[0][0]
                cosine_sim = 1 - (best_dist**2 / 2) # Chuyển đổi từ L2 distance sang Cosine Similarity
                
                if cosine_sim >= SIM_THRESHOLD:
                    name = self._faiss_id_to_name.get(best_idx, 'Unknown')
                    if name != 'Unknown':
                        name_counter[name] += 1
            
            if not name_counter:
                print('[FR] Không có khuôn mặt nào khớp với ngưỡng cho phép.')
                return None
            
            most_common_name, count = name_counter.most_common(1)[0]
            print(f"[FR] KQ search: name={most_common_name} xuất hiện {count} lần trong {len(collected_embs)} lần nhận diện.")
            return most_common_name

        except Exception as e:
            print(f"[FR] Lỗi trong quá trình nhận diện: {e}")
            return None
        finally:
            if cap: cap.release()
            print('[FR] Camera background recognition END.')