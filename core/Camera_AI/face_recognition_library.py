import os
import cv2
import torch
import faiss
import pickle
import numpy as np
from torchvision import transforms
from PIL import Image
import time
import threading
import queue
from collections import Counter
import mediapipe as mp
from .backbones import get_model

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
MODULE_ROOT = os.path.dirname(os.path.abspath(__file__))

import sys

# Đường dẫn đến thư mục chứa file hiện tại
MODULE_ROOT = os.path.dirname(os.path.abspath(__file__))

# 1. Thêm thư mục 'anti_spoofing' vào sys.path
anti_spoofing_dir = os.path.join(MODULE_ROOT, 'anti_spoofing')
if anti_spoofing_dir not in sys.path:
    sys.path.append(anti_spoofing_dir)

# 2. Import các module cần thiết (Lưu ý: Thêm lớp Detection vào dòng import)
from src.anti_spoof_predict import AntiSpoofPredict, Detection
from src.generate_patches import CropImage
from src.utility import parse_model_name

# =====================================================================
# 3. VÁ LỖI TẢI RETINAFACE (VÔ HIỆU HÓA LỚP DETECTION GỐC)
# Ghi đè hàm __init__ của Detection thành rỗng (lambda self: None).
# Nhờ vậy AntiSpoofPredict sẽ KHÔNG tìm file .prototxt và .caffemodel nữa,
# giúp tiết kiệm được hàng trăm MB RAM và load cực nhanh trên Pi 5!
# =====================================================================
Detection.__init__ = lambda self: None

# ===============
# CÁC CLASS LOGIC 
# ===============

class ModelEmbedding:
    """
    Tải model EdgeFace từ file checkpoint cục bộ và trích xuất đặc trưng.
    """
    def __init__(self, model_name="edgeface_base"):
        print(f"[MODEL] Đang tải model {model_name} từ file cục bộ...")
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # --- TỐI ƯU 4: Sửa đường dẫn ---
        self.checkpoint_path = os.path.join(MODULE_ROOT, 'checkpoints', f'{model_name}.pt')
        
        if not os.path.exists(self.checkpoint_path):
            print(f"Lỗi: Không tìm thấy file checkpoint tại: {self.checkpoint_path}")
            print("Vui lòng tải model vào thư mục 'checkpoints'.")
            raise FileNotFoundError(self.checkpoint_path)
        
        try:
            self.model = get_model(model_name) 
            self.model.load_state_dict(torch.load(self.checkpoint_path, map_location=self.device))
            self.model.to(self.device)
            self.model.eval() 
            print(f"[MODEL] Đã tải model cục bộ lên {self.device} thành công.")
        except Exception as e:
            print(f"Lỗi nghiêm trọng khi tải model: {e}")
            raise

        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ])

    def get_embedding(self, image_np_rgb):
        try:
            input_tensor = self.transform(image_np_rgb).unsqueeze(0).to(self.device)
            with torch.no_grad():
                embedding = self.model(input_tensor).cpu().numpy()
            faiss.normalize_L2(embedding)
            return embedding
        except Exception as e:
            print(f"[MODEL] Lỗi khi trích xuất embedding: {e}")
            return None

class FastFaceSearch:
    """
    Quản lý database FAISS, bao gồm tải, lưu cache, tìm kiếm và thêm.
    """
    def __init__(self, recognizer, model_name='edgeface_base', db_dir='database'):
        print("[FAISS] Khởi tạo hệ thống tìm kiếm...")
        self.recognizer = recognizer
        self.db_dir = db_dir # Đã là đường dẫn tuyệt đối từ MODULE_ROOT
        
        # --- TỐI ƯU 4: Sửa đường dẫn ---
        self.cache_file = os.path.join(self.db_dir, f"{model_name}_cache.pkl")

        self.embeddings = []
        self.labels = []
        self.name_map = {}
        self.index = None
        self.faiss_id_to_name = {}
        self.embedding_size = 512

        self._build_index()

    def _build_index(self):
        if os.path.exists(self.cache_file):
            print(f"[FAISS] Đang tải cache từ {self.cache_file}")
            try:
                with open(self.cache_file, 'rb') as f:
                    cache = pickle.load(f)
                    self.embeddings = cache['embeddings']
                    self.labels = cache['labels']
                    self.name_map = cache['name_map']
            except Exception as e:
                print(f"[FAISS] Lỗi tải cache, sẽ xây dựng lại: {e}")
                self._build_from_database()
        else:
            print("[FAISS] Không tìm thấy cache, đang xây dựng từ database...")
            self._build_from_database()

        # Đảm bảo self.embeddings là float32 ngay cả khi rỗng
        if not isinstance(self.embeddings, np.ndarray) or self.embeddings.size == 0:
            print("[FAISS] Database rỗng hoặc bị lỗi. Khởi tạo index rỗng.")
            self.embeddings = np.empty((0, self.embedding_size), dtype=np.float32)
            self.labels = np.empty((0,), dtype=np.int32)
            self.name_map = {}
        
        self.embeddings = self.embeddings.astype(np.float32)
        dim = self.embedding_size
        self.index = faiss.IndexFlatIP(dim) 
        
        if self.embeddings.shape[0] > 0:
            self.index.add(self.embeddings)
            for i in range(len(self.embeddings)):
                label_idx = int(self.labels[i])
                self.faiss_id_to_name[i] = self.name_map.get(label_idx, "Unknown_Label")
        
        print(f"[FAISS] Index đã sẵn sàng, đang theo dõi {self.index.ntotal} vector.")

    def _build_from_database(self):
        person_idx = 0
        self.embeddings = []
        self.labels = []
        self.name_map = {}

        if not os.path.isdir(self.db_dir):
            print(f"[FAISS] Thư mục database '{self.db_dir}' không tồn tại. Tạo mới.")
            os.makedirs(self.db_dir, exist_ok=True)
            return

        for person_name in os.listdir(self.db_dir):
            person_path = os.path.join(self.db_dir, person_name)
            if not os.path.isdir(person_path):
                continue
            
            print(f"[FAISS] Đang quét ảnh cho: {person_name}")
            self.name_map[person_idx] = person_name
            
            # --- TỐI ƯU 3: LOGIC VECTOR TRUNG BÌNH ---
            person_embeddings = []
            for file in os.listdir(person_path):
                if not (file.endswith('.jpg') or file.endswith('.png')):
                    continue
                
                img_path = os.path.join(person_path, file)
                img = cv2.imread(img_path)
                if img is None: continue
                
                img_resized = cv2.resize(img, (112, 112))
                img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
                
                emb = self.recognizer.get_embedding(img_rgb)
                if emb is not None:
                    person_embeddings.append(emb[0])
            
            # Tính trung bình và chỉ thêm 1 vector cho người này
            if person_embeddings:
                person_embeddings_np = np.array(person_embeddings).astype(np.float32)
                avg_embedding = np.mean(person_embeddings_np, axis=0, keepdims=False)
                faiss.normalize_L2(avg_embedding.reshape(1, -1)) # Chuẩn hóa
                
                self.embeddings.append(avg_embedding)
                self.labels.append(person_idx)
                print(f"[FAISS] Đã tạo 1 vector trung bình cho {person_name} từ {len(person_embeddings)} ảnh.")
            # --- HẾT TỐI ƯU 3 ---
                
            person_idx += 1

        if self.embeddings:
            self.embeddings = np.array(self.embeddings).astype(np.float32)
            self.labels = np.array(self.labels)
            self._save_cache()
        else:
            print("[FAISS] Không tìm thấy ảnh nào trong database.")


    def _save_cache(self):
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump({
                    'embeddings': self.embeddings,
                    'labels': self.labels,
                    'name_map': self.name_map
                }, f)
            print(f"[FAISS] Đã lưu cache vào {self.cache_file}")
        except Exception as e:
            print(f"[FAISS] Lỗi khi lưu cache: {e}")

    def search(self, query_emb, topk=1):
        if self.index.ntotal == 0: return []
        try:
            D, I = self.index.search(query_emb, topk) 
            results = []
            for idx, score in zip(I[0], D[0]):
                if idx == -1: continue 
                name = self.faiss_id_to_name.get(idx, "Unknown")
                results.append((name, float(score)))
            return results
        except Exception as e:
            print(f"[FAISS] Lỗi khi tìm kiếm: {e}")
            return []

    def add_embedding(self, new_embs, person_name):
        # new_embs bây giờ được kỳ vọng là (1, 512) hoặc (N, 512)
        if new_embs.ndim == 1:
            new_embs = np.expand_dims(new_embs, axis=0)
        
        new_embs = new_embs.astype(np.float32)
        
        if person_name in self.name_map.values():
            new_label = [k for k, v in self.name_map.items() if v == person_name][0]
            print(f"[FAISS] {person_name} đã tồn tại, dùng lại label {new_label}.")
            # TÙY CHỌN: Có thể cập nhật vector trung bình cũ, nhưng giờ ta chỉ thêm mới
        else:
            new_label = len(self.name_map)
            self.name_map[new_label] = person_name
            print(f"[FAISS] Tạo label mới {new_label} cho {person_name}.")

        start_id = self.index.ntotal
        self.index.add(new_embs)
        
        # Thêm vào cache
        self.embeddings = np.vstack([self.embeddings, new_embs])
        new_labels_arr = np.array([new_label] * len(new_embs))
        self.labels = np.hstack([self.labels, new_labels_arr])

        for i in range(len(new_embs)):
            self.faiss_id_to_name[start_id + i] = person_name

        print(f"[FAISS] Đã thêm {len(new_embs)} vector trung bình cho {person_name}.")
        self._save_cache()


class MediaPipeFaceDetector:
    """
    Sử dụng MediaPipe để phát hiện khuôn mặt VÀ 6 điểm mốc chính.
    """
    def __init__(self):
        print("[DETECT] Đang tải model MediaPipe Face Detection...")
        self.detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.7)
        print("[DETECT] Tải model MediaPipe thành công.")

    def detect(self, frame_bgr):
        """
        Phát hiện khuôn mặt.
        Trả về: Danh sách các tuple (bbox, keypoints)
        - bbox: (x1, y1, x2, y2)
        - keypoints: Dictionary chứa 6 điểm mốc (ví dụ: 'left_eye', 'right_eye', ...)
        """
        try:
            h, w, _ = frame_bgr.shape
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self.detector.process(rgb)
            
            detected_faces = []
            
            if results.detections:
                for det in results.detections:
                    # 1. Lấy Bounding Box
                    bbox_data = det.location_data.relative_bounding_box
                    x1 = int(bbox_data.xmin * w)
                    y1 = int(bbox_data.ymin * h)
                    x2 = x1 + int(bbox_data.width * w)
                    y2 = y1 + int(bbox_data.height * h)
                    
                    bbox = (max(0, x1), max(0, y1), min(w, x2), min(h, y2))
                    
                    # 2. Lấy 6 Điểm Mốc (Keypoints)
                    keypoints = {}
                    kp_names = [
                        'right_eye', 'left_eye', 'nose_tip', 
                        'mouth_center', 'right_ear_tragion', 'left_ear_tragion'
                    ]
                    
                    for i, kp in enumerate(det.location_data.relative_keypoints):
                        kp_name = kp_names[i]
                        kp_x = int(kp.x * w)
                        kp_y = int(kp.y * h)
                        keypoints[kp_name] = (kp_x, kp_y)
                        
                    detected_faces.append((bbox, keypoints))
                    
            return detected_faces
            
        except Exception as e:
            print(f"[DETECT] Lỗi MediaPipe: {e}")
            return []

class LivenessDetector:
    def __init__(self, model_dir="anti_spoofing/resources/anti_spoof_models", device_id=0):
        print("[LIVENESS] Đang tải mô hình chống giả mạo...")
        self.model_dir = os.path.join(MODULE_ROOT, model_dir)
        self.model_test = AntiSpoofPredict(device_id) # Sẽ tự động dùng CPU trên Pi
        self.image_cropper = CropImage()
        self.models = [m for m in os.listdir(self.model_dir) if "MiniFASNet" in m]
        print(f"[LIVENESS] Đã tải {len(self.models)} model chống giả mạo.")

    def check_liveness(self, frame_bgr, bbox):
        """
        bbox từ MediaPipe là (x1, y1, x2, y2).
        Hàm này yêu cầu [x, y, w, h] và cần padding một chút vì MediaPipe box quá chật.
        """
        h_img, w_img, _ = frame_bgr.shape
        x1, y1, x2, y2 = bbox
        
        # Mở rộng bbox của MediaPipe (khoảng 15-20%) để giống với RetinaFace
        w_box = x2 - x1
        h_box = y2 - y1
        x1 = max(0, x1 - int(w_box * 0.1))
        y1 = max(0, y1 - int(h_box * 0.15))
        x2 = min(w_img, x2 + int(w_box * 0.1))
        y2 = min(h_img, y2 + int(h_box * 0.1))
        
        # Chuyển sang định dạng [x, y, w, h]
        fas_bbox = [x1, y1, x2 - x1, y2 - y1]
        
        prediction = np.zeros((1, 3))
        for model_name in self.models:
            h_input, w_input, model_type, scale = parse_model_name(model_name)
            param = {
                "org_img": frame_bgr,
                "bbox": fas_bbox,
                "scale": scale,
                "out_w": w_input,
                "out_h": h_input,
                "crop": True,
            }
            if scale is None:
                param["crop"] = False
            
            img = self.image_cropper.crop(**param)
            prediction += self.model_test.predict(img, os.path.join(self.model_dir, model_name))
            
        prediction = prediction / len(self.models)
        label = np.argmax(prediction)
        score = prediction[0][label]
        
        # Label 1 là Mặt Thật, 0 và 2 là Mặt Giả
        is_real = (label == 1) 
        return is_real, score

# =========================================================================
# CLASS THƯ VIỆN CHÍNH
# =========================================================================

class FaceRecognitionSystemWebcam:
    # --- CẤU HÌNH ---
    
    # Chỉ định tên model
    MODEL_NAME = "edgeface_base"
    # Chỉ định thư mục database (sẽ được join với MODULE_ROOT)
    DATABASE_DIR_NAME = os.path.join(MODULE_ROOT, 'database')
    
    # Chỉ giữ frame mới nhất để giảm độ trễ
    IMAGE_QUEUE_SIZE = 1 
    
    def __init__(self):
        print("--- Đang khởi tạo Hệ thống Nhận diện Khuôn mặt (Webcam) ---")
        
        self.latest_frame_for_display = None

        # Tạo đường dẫn tuyệt đối cho thư mục database
        self.DATABASE_BACKUP_DIR = os.path.join(MODULE_ROOT, self.DATABASE_DIR_NAME)
        os.makedirs(self.DATABASE_BACKUP_DIR, exist_ok=True) # Đảm bảo thư mục tồn tại

        self.detector = MediaPipeFaceDetector()
        self.liveness = LivenessDetector()  
        self.recognizer = ModelEmbedding(self.MODEL_NAME)
        self.searcher = FastFaceSearch(self.recognizer, self.MODEL_NAME, self.DATABASE_BACKUP_DIR)
        
        self.image_queue = queue.Queue(maxsize=self.IMAGE_QUEUE_SIZE)
        
        self._camera_running = False 
        self.cap = None
        self.webcam_thread = threading.Thread(target=self._webcam_reader_thread, daemon=True)
        self.webcam_thread.start()
        
        print(f"--- Hệ thống đã sẵn sàng (Queue size: {self.IMAGE_QUEUE_SIZE}) ---")

    def _webcam_reader_thread(self):
        while True:
            # Nếu có lệnh tắt -> Giải phóng camera để tắt đèn LED
            if not self._camera_running:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                    self.clear_image_queue()
                time.sleep(0.2) # Ngủ để tiết kiệm CPU
                continue

            # Nếu có lệnh bật mà chưa mở camera -> Mở camera
            if self._camera_running and self.cap is None:
                try:
                    self.cap = cv2.VideoCapture(0)
                    if not self.cap.isOpened():
                        self._camera_running = False
                        continue
                except:
                    self._camera_running = False
                    continue

            # Đọc ảnh như bình thường
            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    if self.image_queue.full():
                        try: self.image_queue.get_nowait()
                        except queue.Empty: pass
                    self.latest_frame_for_display = frame
                    self.image_queue.put(frame)
                time.sleep(0.01)
    def get_latest_frame_for_display(self):
        return self.latest_frame_for_display
    # Thêm vào trong class FaceRecognitionSystemWebcam
    def start_capture(self):
        if not self._camera_running:
            self._camera_running = True

    def stop_capture(self):
        if self._camera_running:
            self._camera_running = False    
    def clear_image_queue(self):
        while not self.image_queue.empty():
            try: self.image_queue.get_nowait()
            except queue.Empty: break
        print("[QUEUE] Bộ đệm ảnh đã được dọn dẹp.")

    def _get_image_from_camera(self, timeout=3.0):
        if not self._camera_running:
            self.start_capture()
            time.sleep(1.0) # Chờ warm-up
        try:
            # Lấy frame mới nhất từ queue
            return self.image_queue.get(timeout=timeout)
        except queue.Empty:
            print(f"[CAMERA] Lỗi: Không nhận được ảnh từ webcam trong {timeout} giây.")
            return None

    def _find_and_prep_face(self, bgr_frame):
        """
        Tìm, căn chỉnh (xoay) và chuẩn bị khuôn mặt.
        """
    
        # 1. Dùng detector mới, trả về cả bbox và keypoints
        detected_faces = self.detector.detect(bgr_frame) 
    
        if not detected_faces:
            return None, None # Không tìm thấy mặt

        # Lấy khuôn mặt đầu tiên (hoặc lớn nhất)
        bbox, keypoints = detected_faces[0]
    
        # 2. Gọi hàm alignment mới (Dùng cv2.warpAffine)
        aligned_face_bgr = align_face_112(bgr_frame, keypoints)
    
        if aligned_face_bgr is None:
            return None, None
        
        # 3. Chuyển sang RGB để chuẩn bị cho model EdgeFace
        aligned_face_rgb = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
    
        return aligned_face_rgb, bbox

    # =========================================================================
    # CHỨC NĂNG 1: ĐĂNG KÝ KHÁCH HÀNG
    # =========================================================================
    def register_customer(self, customer_name, num_images_to_capture=100, progress_callback=None, stop_flag_check=None):
        if not customer_name or not customer_name.strip():
            print("[REGISTER] Lỗi: Tên khách hàng không hợp lệ.")
            return False
        
        customer_name = customer_name.strip()
        print(f"--- BẮT ĐẦU ĐĂNG KÝ (REAL-TIME AI) CHO '{customer_name}' ---")
        
        captured_data_buffer = [] 
        if progress_callback:
            progress_callback(0, num_images_to_capture, "Chuẩn bị...")

        while len(captured_data_buffer) < num_images_to_capture:
            if stop_flag_check and stop_flag_check():
                self.clear_image_queue()
                return False

            bgr_frame = self._get_image_from_camera(timeout=1.0)
            if bgr_frame is None: continue

            # 1. FACE DETECTION
            detected_faces = self.detector.detect(bgr_frame)
            if not detected_faces: continue
            
            bbox, keypoints = detected_faces[0]

            # 2. ANTI-SPOOFING (BẮT BUỘC KHÔNG CHO ĐĂNG KÝ BẰNG ẢNH GIẢ)
            is_real, _ = self.liveness.check_liveness(bgr_frame, bbox)
            if not is_real:
                if progress_callback:
                    progress_callback(len(captured_data_buffer), num_images_to_capture, "⚠️ Vui lòng dùng khuôn mặt thật!", error=True)
                continue

            # 3. ALIGNMENT
            aligned_face_bgr = align_face_112(bgr_frame, keypoints)
            if aligned_face_bgr is not None:
                rgb_face_112 = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
                
                # 4. EMBEDDING
                embedding = self.recognizer.get_embedding(rgb_face_112)
                
                if embedding is not None:
                    captured_data_buffer.append({
                        "image": rgb_face_112,
                        "embedding": embedding[0]
                    })
                    
                    count = len(captured_data_buffer)
                    if progress_callback:
                        progress_callback(count, num_images_to_capture, "CAPTURING")

        print(f"[REGISTER] Đã thu thập đủ {len(captured_data_buffer)} ảnh và vector. Đang lưu đĩa...")

        # --- (Phần lưu đĩa và lưu FAISS phía sau giữ nguyên như cũ) ---
        if progress_callback:
            progress_callback(num_images_to_capture, num_images_to_capture, "Đang lưu dữ liệu...")

        person_dir = os.path.join(self.searcher.db_dir, customer_name)
        os.makedirs(person_dir, exist_ok=True)

        all_embeddings = []
        for idx, data in enumerate(captured_data_buffer):
            if stop_flag_check and stop_flag_check(): return False
            face_img = data["image"]
            emb_vec = data["embedding"]
            all_embeddings.append(emb_vec)
            
            save_path = os.path.join(person_dir, f"{idx:03d}.jpg")
            cv2.imwrite(save_path, cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR))
        
        success = False
        if all_embeddings:
            embeddings_np = np.array(all_embeddings).astype(np.float32)
            avg_embedding = np.mean(embeddings_np, axis=0, keepdims=True)
            faiss.normalize_L2(avg_embedding)
            
            self.searcher.add_embedding(avg_embedding, customer_name)
            last_img = captured_data_buffer[-1]["image"]
            cv2.imwrite(os.path.join(person_dir, "000_avg_ref.jpg"), cv2.cvtColor(last_img, cv2.COLOR_RGB2BGR))
            success = True
        else:
             if progress_callback:
                progress_callback(0, num_images_to_capture, "Lỗi: Không có dữ liệu AI", error=True)

        self.clear_image_queue()
        return success

    # =========================================================================
    # CHỨC NĂNG 2: ĐĂNG NHẬP / NHẬN DIỆN KHÁCH HÀNG
    # =========================================================================
    def login_customer(self, num_images_to_capture=10, similarity_threshold=0.4, progress_callback=None, stop_flag_check=None): # <-- THÊM STOP_FLAG_CHECK
        
        if self.searcher.index.ntotal == 0:
            print("[LOGIN] Cảnh báo: Database rỗng. Không thể nhận diện.")
            if progress_callback:
                progress_callback(0, num_images_to_capture, "Database rỗng", error=True)
            return "Unknown"
        
        print("--- BẮT ĐẦU QUÁ TRÌNH NHẬN DIỆN ---")
        if progress_callback:
            progress_callback(0, num_images_to_capture, "Bắt đầu nhận diện...")
        
        votes = []
        liveness_failures = 0 # Đếm số lần phát hiện mặt giả
        
        for i in range(num_images_to_capture):
            if stop_flag_check and stop_flag_check():
                print("[LOGIN] Người dùng hủy bỏ.")
                self.clear_image_queue()
                return "Unknown" # Trả về "Unknown" nếu bị hủy
                
            msg = f"Đang lấy ảnh {i + 1}/{num_images_to_capture}..."
            print(f"[LOGIN] {msg}")
            if progress_callback:
                progress_callback(i, num_images_to_capture, msg)

            bgr_frame = self._get_image_from_camera()
            if bgr_frame is None: continue

            # -------------------------------------------------------------
            # BƯỚC 1: FACE DETECTION
            # -------------------------------------------------------------
            detected_faces = self.detector.detect(bgr_frame)
            if not detected_faces:
                continue # Không thấy mặt thì lấy frame tiếp theo
                
            bbox, keypoints = detected_faces[0]

            # -------------------------------------------------------------
            # BƯỚC 2: ANTI-SPOOFING (LIVENESS CHECK)
            # Chỉ kiểm tra khung viền khuôn mặt (Crop) từ ảnh gốc
            # -------------------------------------------------------------
            is_real, liveness_score = self.liveness.check_liveness(bgr_frame, bbox)
            
            if not is_real:
                print(f"[LOGIN] Phát hiện MẶT GIẢ (Spoofing) - Score: {liveness_score:.4f}")
                liveness_failures += 1
                if progress_callback:
                    progress_callback(i, num_images_to_capture, "CẢNH BÁO: Cố gắng giả mạo!")
                continue # BỎ QUA NGAY FRAME NÀY, không thực hiện AI nhận diện tốn CPU

            # -------------------------------------------------------------
            # BƯỚC 3 & 4: ALIGNMENT VÀ RECOGNITION (TRÍCH XUẤT ĐẶC TRƯNG)
            # Chỉ chạy khi chắc chắn đây là MẶT THẬT
            # -------------------------------------------------------------
            aligned_face_bgr = align_face_112(bgr_frame, keypoints)
            
            if aligned_face_bgr is not None:
                rgb_face_112 = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
                embedding = self.recognizer.get_embedding(rgb_face_112)
                
                # -------------------------------------------------------------
                # BƯỚC 5: SO SÁNH EMBEDDED VECTOR (FAISS)
                # -------------------------------------------------------------
                if embedding is not None:
                    results = self.searcher.search(embedding, topk=1)
                    
                    if results:
                        best_name, best_score = results[0]
                        print(f"  -> {best_name} (Score: {best_score:.4f})")
                        if best_score > similarity_threshold:
                            votes.append(best_name)
                        else:
                            votes.append("Unknown")
            
            time.sleep(0.05)
        
        if progress_callback:
            progress_callback(num_images_to_capture, num_images_to_capture, "Đang xử lý kết quả...")

        # -------------------------------------------------------------
        # ĐÁNH GIÁ KẾT QUẢ TỔNG THỂ
        # -------------------------------------------------------------
        # 1. Nếu số lượng ảnh cố tình giả mạo vượt quá 40% số lần quét -> Báo động
        if liveness_failures > (num_images_to_capture * 0.4):
            print(f"[LOGIN] TỪ CHỐI ĐĂNG NHẬP: Phát hiện tấn công giả mạo {liveness_failures}/{num_images_to_capture} frames.")
            self.clear_image_queue()
            return "Spoofing_Detected"

        # 2. Xử lý logic bầu chọn (Voting) cho mặt thật
        result = "Unknown"
        if votes:
            most_common_vote = Counter(votes).most_common(1)[0]
            name = most_common_vote[0]
            count = most_common_vote[1]
            
            # Tính % so với số votes mặt thật hợp lệ, thay vì tổng frame
            if name != "Unknown" and count > (len(votes) // 4):
                result = name
        
        print(f"[LOGIN] Kết quả cuối cùng: {result}")
        self.clear_image_queue()
        return result
    
    # --- Hàm helper để gọi từ bên ngoài ---
    
    def find_and_prep_face(self, bgr_frame):
        # Wrapper cho hàm private
        return self._find_and_prep_face(bgr_frame)

def align_face_112(frame_bgr, keypoints):
    """
    Căn chỉnh (xoay + co giãn) khuôn mặt về 112x112
    dựa trên 3 điểm mốc: 2 mắt và chóp mũi.
    """
    try:
        # Lấy 3 điểm mốc từ khuôn mặt phát hiện được
        src_pts = np.float32([
            keypoints['right_eye'], 
            keypoints['left_eye'], 
            keypoints['nose_tip']
        ])

        # Định nghĩa 3 điểm mốc "chuẩn" (đích) trên ảnh 112x112
        # Các giá trị này được chọn để căn mắt và mũi vào vị trí hợp lý
        dst_pts = np.float32([
            [38.2946, 51.6963],  # Vị trí mắt phải chuẩn
            [73.5318, 51.5014],  # Vị trí mắt trái chuẩn
            [56.0252, 71.7366]   # Vị trí chóp mũi chuẩn
        ])
        
        # 1. Tính toán ma trận biến đổi (xoay, co giãn, dịch chuyển)
        # Chỉ dùng 3 điểm nên 'fullAffine' = False
        M = cv2.getAffineTransform(src_pts, dst_pts)
        
        # 2. Áp dụng phép biến đổi lên ảnh gốc
        # Kích thước ảnh đầu ra là (width, height) = (112, 112)
        aligned_face = cv2.warpAffine(
            frame_bgr, 
            M, 
            (112, 112), 
            borderMode=cv2.BORDER_CONSTANT, 
            borderValue=(0, 0, 0)
        )
        
        return aligned_face

    except Exception as e:
        print(f"[ALIGN] Lỗi khi căn chỉnh: {e}")
        return None


# =========================================================================
# VÍ DỤ SỬ DỤNG THƯ VIỆN
# =========================================================================
if __name__ == "__main__":
    # 1. Đảm bảo bạn có file `backbones.py` trong cùng thư mục.
    # 2. Đảm bảo bạn có thư mục `checkpoints/`
    #    chứa file model (ví dụ: `edgeface_xs_gamma_06.pt`).
    # 3. Đảm bảo bạn có thư mục `database/`
    
    face_system = None
    try:
        face_system = FaceRecognitionSystemWebcam()
        
        while True:
            print("\n" + "="*40)
            print("CHỌN CHỨC NĂNG (WEBCAM - TỐI ƯU):")
            print("1. Đăng ký khách hàng mới")
            print("2. Đăng nhập (Nhận diện khách hàng)")
            print("q. Thoát")
            choice = input("Lựa chọn của bạn: ").strip()
            print("="*40)
            
            if choice == '1':
                customer_name = input("Nhập tên khách hàng để đăng ký: ").strip()
                if customer_name:
                    success = face_system.register_customer(customer_name, num_images_to_capture=30)
                    if success: print(f"\n[MAIN] Đăng ký cho '{customer_name}' thành công!")
                    else: print(f"\n[MAIN] Đăng ký cho '{customer_name}' thất bại.")
                else: print("[MAIN] Tên không hợp lệ.")
            
            elif choice == '2':
                print("Vui lòng nhìn vào camera để đăng nhập...")
                identified_customer = face_system.login_customer(num_images_to_capture=10, similarity_threshold=0.4) 
                print(f"\n[MAIN] Xin chào, {identified_customer}!")
            
            elif choice.lower() == 'q':
                print("Thoát chương trình.")
                os._exit(0) # Thoát cứng để dừng cả luồng daemon
            
            else:
                print("Lựa chọn không hợp lệ, vui lòng thử lại.")
                
    except Exception as e:
        print(f"[MAIN] Gặp lỗi nghiêm trọng: {e}")
    finally:
        if face_system:
            # Code này có thể không chạy do os._exit(0)
            # nhưng nếu thoát bằng Ctrl+C thì nó hữu ích
            print("Dọn dẹp tài nguyên...")
            # (Trong ứng dụng thực tế, bạn cần một cách thoát mềm hơn)
            pass