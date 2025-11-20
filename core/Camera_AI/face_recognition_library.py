# -*- coding: utf-8 -*-
# File: face_recognition_webcam_local.py
#
# PHIÊN BẢN ĐÃ TỐI ƯU:
# 1. Giảm độ trễ (queue.Queue(maxsize=1)).
# 2. Tăng độ chính xác (dùng vector trung bình - centroid - khi đăng ký).
# 3. Đồng bộ logic vector trung bình khi xây dựng lại cache.
# 4. Sửa lỗi đường dẫn (path) bằng os.path.join và MODULE_ROOT.

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
try:
    # --- TỐI ƯU 4 ---
    # Import tương đối, giả định backbones.py nằm cùng thư mục
    from .backbones import get_model
except ImportError:
    print("LỖI: Không thể import 'get_model' từ 'backbones.py'.")
    print("Vui lòng đảm bảo file 'backbones.py' nằm chung thư mục với file này.")
    # Thử import trực tiếp nếu chạy như script
    try:
        from backbones import get_model
    except ImportError:
        print("LỖI: Import trực tiếp 'backbones.py' cũng thất bại.")
        exit()


os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
MODULE_ROOT = os.path.dirname(os.path.abspath(__file__))

# =========================================================================
# CÁC CLASS LOGIC (TỪ APP_FAISS.PY VÀ MODEL.PY)
# =========================================================================

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
# =========================================================================
# CLASS THƯ VIỆN CHÍNH
# =========================================================================

class FaceRecognitionSystemWebcam:
    # --- CẤU HÌNH ---
    
    # --- TỐI ƯU 4: Sửa đường dẫn ---
    # Chỉ định tên model
    MODEL_NAME = "edgeface_base"
    # Chỉ định thư mục database (sẽ được join với MODULE_ROOT)
    DATABASE_DIR_NAME = os.path.join(MODULE_ROOT, 'database')
    
    # --- TỐI ƯU 1: GIẢM ĐỘ TRỄ ---
    # Chỉ giữ frame mới nhất để giảm độ trễ
    IMAGE_QUEUE_SIZE = 1 
    
    def __init__(self):
        print("--- Đang khởi tạo Hệ thống Nhận diện Khuôn mặt (Webcam) ---")
        
        self.latest_frame_for_display = None

        # --- TỐI ƯU 4: Sửa đường dẫn ---
        # Tạo đường dẫn tuyệt đối cho thư mục database
        self.DATABASE_BACKUP_DIR = os.path.join(MODULE_ROOT, self.DATABASE_DIR_NAME)
        os.makedirs(self.DATABASE_BACKUP_DIR, exist_ok=True) # Đảm bảo thư mục tồn tại

        self.detector = MediaPipeFaceDetector()
        self.recognizer = ModelEmbedding(self.MODEL_NAME)
        self.searcher = FastFaceSearch(self.recognizer, self.MODEL_NAME, self.DATABASE_BACKUP_DIR)
        
        self.image_queue = queue.Queue(maxsize=self.IMAGE_QUEUE_SIZE)
        
        self.webcam_thread = threading.Thread(target=self._webcam_reader_thread, daemon=True)
        self.webcam_thread.start()
        
        print(f"--- Hệ thống đã sẵn sàng (Queue size: {self.IMAGE_QUEUE_SIZE}) ---")

    def _webcam_reader_thread(self):
        print("[WEBCAM] Đang mở webcam...")
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[WEBCAM] Lỗi: Không thể mở webcam.")
            return

        while True:
            ret, frame = cap.read()
            if not ret:
                print("[WEBCAM] Lỗi: Không thể đọc frame. Thử lại...")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(0)
                continue

            # --- TỐI ƯU 1: LOGIC "LATEST FRAME" ---
            # Logic này đã đúng: nếu queue đầy (size=1),
            # nó sẽ vứt frame cũ đi để nhét frame mới vào.
            if self.image_queue.full():
                try: self.image_queue.get_nowait()
                except queue.Empty: pass
            
            self.latest_frame_for_display = frame
            self.image_queue.put(frame)
            time.sleep(0.01) # Vẫn giữ sleep nhỏ để tránh lãng phí 100% CPU

        cap.release()
        print("[WEBCAM] Đã đóng webcam.")

    def get_latest_frame_for_display(self):
        return self.latest_frame_for_display
    
    def clear_image_queue(self):
        while not self.image_queue.empty():
            try: self.image_queue.get_nowait()
            except queue.Empty: break
        print("[QUEUE] Bộ đệm ảnh đã được dọn dẹp.")

    def _get_image_from_camera(self, timeout=3.0):
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
    def register_customer(self, customer_name, num_images_to_capture=200, progress_callback=None, stop_flag_check=None):
        """
        Phiên bản Hybrid:
        - Tính toán AI (Embedding) NGAY LẬP TỨC trong vòng lặp chụp.
        - Lưu ảnh vào RAM buffer.
        - Chỉ ghi xuống ổ cứng (I/O) sau khi hoàn tất.
        -> Tận dụng thời gian tính AI làm độ trễ tự nhiên để khách quay đầu.
        """
        if not customer_name or not customer_name.strip():
            print("[REGISTER] Lỗi: Tên khách hàng không hợp lệ.")
            return False
        
        customer_name = customer_name.strip()
        print(f"--- BẮT ĐẦU ĐĂNG KÝ (REAL-TIME AI) CHO '{customer_name}' ---")
        
        # Buffer chứa bộ đôi: (ảnh_đã_crop, vector_đặc_trưng)
        captured_data_buffer = [] 
        
        if progress_callback:
            progress_callback(0, num_images_to_capture, "Chuẩn bị...")

        # --- GIAI ĐOẠN 1: CHỤP & TÍNH TOÁN (Vừa chụp vừa tính) ---
        while len(captured_data_buffer) < num_images_to_capture:
            # 1. Kiểm tra hủy
            if stop_flag_check and stop_flag_check():
                self.clear_image_queue()
                return False

            # 2. Lấy ảnh
            bgr_frame = self._get_image_from_camera(timeout=1.0)
            if bgr_frame is None: continue

            # 3. Detect & Crop (Bước này nhanh)
            rgb_face_112, _ = self.find_and_prep_face(bgr_frame)
            
            if rgb_face_112 is not None:
                # 4. TÍNH AI NGAY LẬP TỨC (Bước này tốn ~100-200ms)
                # Chính bước này tạo ra độ trễ tự nhiên giúp khách kịp quay đầu
                embedding = self.recognizer.get_embedding(rgb_face_112)
                
                if embedding is not None:
                    # Chỉ lưu vào RAM, CHƯA ghi ổ cứng
                    captured_data_buffer.append({
                        "image": rgb_face_112,
                        "embedding": embedding[0]
                    })
                    
                    count = len(captured_data_buffer)
                    
                    # Gửi callback "CAPTURING" để UI hiện hướng dẫn (Quay trái/phải...)
                    if progress_callback:
                        progress_callback(count, num_images_to_capture, "CAPTURING")
                        
                    if count % 10 == 0:
                        print(f"[REGISTER] Đã xử lý: {count}/{num_images_to_capture}")
            
            # Không cần time.sleep() vì hàm get_embedding đã tốn thời gian rồi

        print(f"[REGISTER] Đã thu thập đủ {len(captured_data_buffer)} ảnh và vector. Đang lưu đĩa...")

        # --- GIAI ĐOẠN 2: LƯU TRỮ (Chỉ tốn I/O disk, rất nhanh) ---
        if progress_callback:
            progress_callback(num_images_to_capture, num_images_to_capture, "Đang lưu dữ liệu...")

        person_dir = os.path.join(self.searcher.db_dir, customer_name)
        os.makedirs(person_dir, exist_ok=True)

        all_embeddings = []
        
        # Duyệt qua buffer để lưu ra file
        for idx, data in enumerate(captured_data_buffer):
            if stop_flag_check and stop_flag_check(): return False

            face_img = data["image"]
            emb_vec = data["embedding"]
            
            all_embeddings.append(emb_vec)
            
            # Lưu ảnh JPG (để làm dataset train sau này)
            save_path = os.path.join(person_dir, f"{idx:03d}.jpg")
            # Chuyển RGB -> BGR khi lưu bằng OpenCV
            cv2.imwrite(save_path, cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR))
        
        # --- GIAI ĐOẠN 3: TẠO VECTOR TRUNG BÌNH & KẾT THÚC ---
        success = False
        if all_embeddings:
            embeddings_np = np.array(all_embeddings).astype(np.float32)
            
            # Tính trung bình cộng
            avg_embedding = np.mean(embeddings_np, axis=0, keepdims=True)
            faiss.normalize_L2(avg_embedding)
            
            # Thêm vào database nhận diện
            self.searcher.add_embedding(avg_embedding, customer_name)
            
            # Lưu ảnh đại diện (lấy ảnh cuối)
            last_img = captured_data_buffer[-1]["image"]
            cv2.imwrite(os.path.join(person_dir, "000_avg_ref.jpg"), cv2.cvtColor(last_img, cv2.COLOR_RGB2BGR))
            
            success = True
            print(f"[REGISTER] Hoàn tất đăng ký {customer_name} với {len(all_embeddings)} ảnh.")
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

            rgb_face_112, _ = self.find_and_prep_face(bgr_frame)
            
            if rgb_face_112 is not None:
                embedding = self.recognizer.get_embedding(rgb_face_112)
                
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

        result = "Unknown"
        if votes:
            most_common_vote = Counter(votes).most_common(1)[0]
            name = most_common_vote[0]
            count = most_common_vote[1]
            
            if name != "Unknown" and count > (num_images_to_capture // 4):
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