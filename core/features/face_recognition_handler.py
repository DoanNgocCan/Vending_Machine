import os
import time
import queue
import threading
import numpy as np
from collections import Counter
import cv2
import io          
import zipfile
import pickle

from core.Camera_AI.face_recognition_library import (
    ModelEmbedding,
    MediaPipeFaceDetector,
    LivenessDetector,
    FastFaceSearch,
    align_face_112,
)

RECOGNITION_TIME_LIMIT = 5.0
MAX_EMBS = 100
SIM_THRESHOLD = 0.6
BLUR_THRESHOLD = 20.0
BRIGHTNESS_MIN = 15
BRIGHTNESS_MAX = 240


class FaceRecognitionHandler:
    """
    Service controller duy nhất cho nghiệp vụ nhận diện.
    Điều phối camera + pipeline nghiệp vụ, và tái sử dụng FastFaceSearch từ library.
    """

    MODEL_NAME = "edgeface_base"
    DATABASE_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "Camera_AI", "database")
    )
    IMAGE_QUEUE_SIZE = 1

    def __init__(self):
        print("FaceRecognitionHandler khởi tạo (service controller).")

        self.latest_frame_for_display = None
        self._camera_running = False
        self.cap = None

        self._time_limit = RECOGNITION_TIME_LIMIT
        self._full_time = True

        os.makedirs(self.DATABASE_DIR, exist_ok=True)

        self.detector = MediaPipeFaceDetector()
        self.liveness = LivenessDetector()
        self.recognizer = ModelEmbedding(self.MODEL_NAME)
        
        # Khởi tạo FAISS thuần RAM
        self.searcher = FastFaceSearch(
            recognizer=self.recognizer,
            model_name=self.MODEL_NAME
        )
        
        # Bơm dữ liệu từ DB lên FAISS lúc Boot Up
        self.reload_cache()

        self.image_queue = queue.Queue(maxsize=self.IMAGE_QUEUE_SIZE)
        self.webcam_thread = threading.Thread(target=self._webcam_reader_thread, daemon=True)
        self.webcam_thread.start()

        self._update_cache_state()
        ntotal = self.searcher.index.ntotal if self.searcher.index is not None else 0
        print(f"[FR_HANDLER] Sẵn sàng, index có {ntotal} vector.")

    def _update_cache_state(self):
        self._cache_loaded = bool(
            self.searcher
            and self.searcher.index is not None
            and self.searcher.index.ntotal > 0
        )

    def reload_cache(self):
        """Luồng Boot Up: SQLite -> RAM"""
        print("[FR_HANDLER] Kích hoạt luồng nạp dữ liệu từ Thẻ SD lên RAM...")
        from core.database.local_database_manager import db_manager
        
        records = db_manager.get_all_face_vectors()
        vectors = []
        rowids = []
        
        for r in records:
            try:
                # Bước 3 BOOT UP: Chuyển BLOB -> Numpy Array
                vec = pickle.loads(r['face_vector'])
                vectors.append(vec)
                rowids.append(r['rowid'])
            except Exception as e:
                print(f"[FR_HANDLER] Lỗi parse vector của rowid {r['rowid']}: {e}")
                
        # Reset FAISS và nạp lại
        self.searcher.index.reset()
        if vectors:
            self.searcher.load_from_db(vectors, rowids)
            
        self._update_cache_state()

    # -----------------------------------------------------------------
    # CAMERA SERVICE
    # -----------------------------------------------------------------
    def _webcam_reader_thread(self):
        while True:
            if not self._camera_running:
                if self.cap is not None:
                    self.cap.release()
                    self.cap = None
                    self.clear_image_queue()
                time.sleep(0.2)
                continue

            if self.cap is None:
                try:
                    # Khởi tạo camera với backend V4L2 tối ưu cho Linux
                    self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

                    # 1. Ép camera xuất luồng KHÔNG NÉN YUYV (YUY2) để đạt chất lượng ảnh cao nhất
                    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('Y', 'U', 'Y', 'V'))

                    # 2. Yêu cầu phần cứng trả về kích thước HD (1280x720)
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

                    # 3. Kiểm tra lại cấu hình thực tế từ driver phần cứng
                    w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                    h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                    print(f"[FR_HANDLER] Độ phân giải phần cứng Webcam đang chạy: {int(w)}x{int(h)}")

                    # 4. Kiểm tra xem hệ thống nhận diện đúng định dạng chưa
                    fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
                    codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
                    print(f"[FR_HANDLER] Định dạng ảnh hiện tại: {codec}") 

                    if not self.cap.isOpened():
                        self._camera_running = False
                        continue
                except Exception:
                    self._camera_running = False
                    continue

            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    # 1. DÀNH CHO UI: Không cần resize, giữ nguyên 1280x720
                    self.latest_frame_for_display = frame 

                    # 2. DÀNH CHO AI: Ép nhỏ lại 640x480 để giảm tải cpu
                    frame_ai = cv2.resize(frame, (640, 480))
                    
                    if self.image_queue.full():
                        try:
                            self.image_queue.get_nowait()
                        except queue.Empty:
                            pass
                    # AI chỉ nhận mảng nhỏ
                    self.image_queue.put(frame_ai) 
                time.sleep(0.01)

    def get_latest_frame_for_display(self):
        return self.latest_frame_for_display

    def start_capture(self):
        if not self._camera_running:
            self._camera_running = True

    def stop_capture(self):
        if self._camera_running:
            self._camera_running = False

    def clear_image_queue(self):
        while not self.image_queue.empty():
            try:
                self.image_queue.get_nowait()
            except queue.Empty:
                break

    def _get_image_from_camera(self, timeout=3.0):
        if not self._camera_running:
            self.start_capture()
            time.sleep(1.0)
        try:
            return self.image_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    # -----------------------------------------------------------------
    # PIPELINE HELPERS
    # -----------------------------------------------------------------
    def _check_face_quality(self, frame_bgr, bbox):
        """
        Cắt riêng vùng khuôn mặt để kiểm tra độ mờ và độ sáng.
        Giảm 80-90% khối lượng tính toán so với làm trên toàn bộ khung hình.
        """
        h_img, w_img = frame_bgr.shape[:2]
        x1, y1, x2, y2 = bbox
        
        # Đảm bảo tọa độ cắt không bị âm hoặc vượt lố ra ngoài ảnh
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img, x2), min(h_img, y2)

        face_crop = frame_bgr[y1:y2, x1:x2]
        
        # Tránh lỗi chia cho 0 nếu mảng rỗng (cắt lỗi do sát viền)
        if face_crop.size == 0:
            return False, 0.0

        # Chuyển xám và đo chất lượng CHỈ trên vùng mặt đã cắt
        gray_face = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        focus_val = cv2.Laplacian(gray_face, cv2.CV_64F).var()
        brightness = gray_face.mean()

        is_good = (
            focus_val >= BLUR_THRESHOLD
            and BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX
        )
        
        return is_good, focus_val

    def _extract_live_embedding(self, frame_bgr, require_quality=False):
        # 1. TÌM KHUÔN MẶT TRƯỚC (MediaPipe cực nhanh, nên ưu tiên chạy đầu)
        detected_faces = self.detector.detect(frame_bgr)
        if not detected_faces:
            return None, False

        bbox, keypoints = detected_faces[0]

        # 2. KIỂM TRA CHẤT LƯỢNG SAU KHI CÓ BBOX
        if require_quality:
            is_good, _ = self._check_face_quality(frame_bgr, bbox)
            if not is_good:
                return None, False  # Bỏ qua nếu mặt bị mờ/tối

        # 3. KIỂM TRA GIẢ MẠO (LIVENESS)
        is_real, _ = self.liveness.check_liveness(frame_bgr, bbox)
        if not is_real:
            return None, True

        # 4. ALIGN VÀ TRÍCH XUẤT ĐẶC TRƯNG
        aligned_face_bgr = align_face_112(frame_bgr, keypoints)
        if aligned_face_bgr is None:
            return None, False

        rgb_face_112 = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
        embedding = self.recognizer.get_embedding(rgb_face_112)

        if not isinstance(embedding, np.ndarray) or embedding.size == 0:
            return None, False

        emb_vec = embedding[0] if embedding.ndim == 2 else embedding
        return emb_vec.astype(np.float32), False

    def _match_embedding(self, embedding, similarity_threshold):
        # Bước 2 LOGIN: Yêu cầu FAISS search
        results = self.searcher.search(embedding, topk=1)
        if not results:
            return None, 0.0

        best_rowid, best_score = results[0]
        
        # Bước 3 LOGIN: Kiểm tra Threshold
        if best_score >= similarity_threshold:
            # Bước 4 LOGIN: Gõ cửa SQLite lấy thông tin
            from core.database.local_database_manager import db_manager
            customer = db_manager.get_customer_by_rowid(best_rowid)
            if customer:
                # Trả về user_id (mã khách hàng) để UI xử lý tiếp
                return customer['user_id'], best_score
                
        return None, best_score

    # -----------------------------------------------------------------
    # BACKGROUND RECOGNITION
    # -----------------------------------------------------------------
    def start_recognition(self, completion_callback, time_limit=5.0, full_time=True):
        self._time_limit = max(0.5, float(time_limit))
        self._full_time = bool(full_time)
        print(
            f"HANDLER: Bắt đầu nhận diện nền (time_limit={self._time_limit}s, full_time={self._full_time})..."
        )
        t = threading.Thread(target=self._run_in_thread, args=(completion_callback,), daemon=True)
        t.start()

    def _run_in_thread(self, callback):
        user_id = self._perform_background_recognition()
        self._dispatch_callback(callback, user_id)

    def _dispatch_callback(self, callback, user_id):
        """
        Tkinter không thread-safe: nếu callback là method của UI,
        ưu tiên đưa callback về main thread bằng .after(0, ...).
        """
        owner = getattr(callback, "__self__", None)

        # Callback là method của widget Tk/Toplevel
        if owner is not None and hasattr(owner, "after"):
            try:
                owner.after(0, lambda uid=user_id: callback(uid))
                return
            except Exception:
                pass

        # Callback là method của controller có self.root là Tk
        root = getattr(owner, "root", None)
        if root is not None and hasattr(root, "after"):
            try:
                root.after(0, lambda uid=user_id: callback(uid))
                return
            except Exception:
                pass

        try:
            callback(user_id)
        except Exception as e:
            print(f"[FR] Lỗi callback: {e}")

    def _perform_background_recognition(self):
        self._update_cache_state()
        if not self._cache_loaded:
            print("[FR] Cache chưa sẵn sàng. Bỏ qua nhận diện nền.")
            return None

        try:
            self.start_capture()
            start = time.time()
            collected_embs = []
            target_end = start + self._time_limit

            while time.time() < target_end:
                frame = self._get_image_from_camera(timeout=0.5)
                if frame is None:
                    continue

                emb, _ = self._extract_live_embedding(frame, require_quality=True)
                if emb is None:
                    continue

                collected_embs.append(emb)
                if len(collected_embs) >= MAX_EMBS and not self._full_time:
                    break

            if not collected_embs:
                print("[FR] Không thu được embedding nào hợp lệ.")
                return None

            name_counter = Counter()
            for emb in collected_embs:
                name, score = self._match_embedding(emb, SIM_THRESHOLD)
                if name is not None:
                    name_counter[name] += 1
                else:
                    _ = score

            if not name_counter:
                print("[FR] Không có khuôn mặt nào khớp với ngưỡng cho phép.")
                return None

            most_common_name, count = name_counter.most_common(1)[0]
            print(
                f"[FR] KQ search: name={most_common_name} xuất hiện {count} lần trong {len(collected_embs)} lần nhận diện."
            )
            return most_common_name

        except Exception as e:
            print(f"[FR] Lỗi trong quá trình nhận diện: {e}")
            return None

    # -----------------------------------------------------------------
    # PUBLIC API CHO UI
    # -----------------------------------------------------------------
    def _find_and_prep_face(self, bgr_frame):
        detected_faces = self.detector.detect(bgr_frame)
        if not detected_faces:
            return None, None

        bbox, keypoints = detected_faces[0]
        aligned_face_bgr = align_face_112(bgr_frame, keypoints)
        if aligned_face_bgr is None:
            return None, None

        aligned_face_rgb = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
        return aligned_face_rgb, bbox

    def find_and_prep_face(self, bgr_frame):
        return self._find_and_prep_face(bgr_frame)

    def register_customer(
        self,
        customer_name,
        num_frames_to_capture=100, # Chụp 100 frame
        keep_best=50,              # Lọc lấy 50 frame tốt nhất
        progress_callback=None,
        stop_flag_check=None,
    ):
        """
        Luồng Đăng ký Mới (In-memory AI):
        Thu thập ảnh -> Lọc chất lượng/Anti-spoof -> Chạy Embedding -> Tính Average -> Nén ZIP RAM.
        Trả về Dictionary để Controller (UI) quyết định bước tiếp theo.
        """
        if not customer_name or not customer_name.strip():
            print("[REGISTER] Lỗi: Tên khách hàng không hợp lệ.")
            return None

        customer_name = customer_name.strip()
        print(f"--- BẮT ĐẦU ĐĂNG KÝ (IN-MEMORY AI) CHO '{customer_name}' ---")

        captured_data_buffer = []
        
        if progress_callback:
            progress_callback(0, num_frames_to_capture, "Đang khởi động Camera...")

        while len(captured_data_buffer) < num_frames_to_capture:
            if stop_flag_check and stop_flag_check():
                self.clear_image_queue()
                return None

            bgr_frame = self._get_image_from_camera(timeout=1.0)
            if bgr_frame is None:
                continue

            # Detect Face
            detected_faces = self.detector.detect(bgr_frame)
            if not detected_faces:
                continue

            bbox, keypoints = detected_faces[0]

            # 1. Kiểm tra Liveness (Anti-spoofing) và lấy Confidence Score
            is_real, liveness_score = self.liveness.check_liveness(bgr_frame, bbox)
            if not is_real:
                if progress_callback:
                    progress_callback(
                        len(captured_data_buffer),
                        num_frames_to_capture,
                        "⚠️ Phát hiện giả mạo! Dùng khuôn mặt thật.",
                        error=True,
                    )
                continue

            # 2. Kiểm tra độ sắc nét (Focus/Blur) CHỈ TRÊN MẶT
            is_good, focus_score = self._check_face_quality(bgr_frame, bbox)
            if focus_score < BLUR_THRESHOLD:
                continue # Bỏ qua ảnh mờ

            # 3. Align ảnh về 112x112
            aligned_face_bgr = align_face_112(bgr_frame, keypoints)
            if aligned_face_bgr is None:
                continue

            # 4. Trích xuất Vector
            rgb_face_112 = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
            embedding = self.recognizer.get_embedding(rgb_face_112)
            if embedding is None:
                continue
                
            # Ép kiểu vector về dạng 1D flat array (512-dim)
            emb_vec = embedding[0] if embedding.ndim == 2 else embedding

            # Tính điểm chất lượng tổng hợp (trọng số liveness 70%, focus 30%)
            # Coi điểm focus 500 là mốc trần tối đa để tính tỷ lệ phần trăm
            total_quality = (liveness_score * 0.7) + (min(focus_score, 500) / 500.0) * 0.3

            captured_data_buffer.append({
                "image": rgb_face_112,
                "embedding": emb_vec,
                "quality": total_quality
            })

            if progress_callback:
                progress_callback(len(captured_data_buffer), num_frames_to_capture, "Đang thu thập dữ liệu sinh trắc...")

        if not captured_data_buffer:
            if progress_callback:
                progress_callback(0, num_frames_to_capture, "Lỗi: Không thu được khuôn mặt hợp lệ", error=True)
            self.clear_image_queue()
            return None

        if progress_callback:
            progress_callback(num_frames_to_capture, num_frames_to_capture, "Đang nén và tối ưu hóa dữ liệu...")

        # --- BƯỚC LỌC VÀ ĐÓNG GÓI ---
        # Sắp xếp buffer theo điểm chất lượng từ cao xuống thấp và cắt lấy top 50
        captured_data_buffer.sort(key=lambda x: x['quality'], reverse=True)
        best_frames = captured_data_buffer[:keep_best]

        best_images = [data['image'] for data in best_frames]
        best_embeddings = [data['embedding'] for data in best_frames]
        avg_quality_score = sum(data['quality'] for data in best_frames) / len(best_frames)

        # Xử lý tính toán In-Memory
        avg_vector = self.compute_average_embedding(best_embeddings)
        zip_bytes = self.compress_images_to_zip_bytes(best_images)
        
        # Gán vector vào FAISS Local ngay lập tức để người dùng có thể mua hàng ngay (Phần 3)
        try:
            self._update_cache_state()
            print(f"[REGISTER] Đã trích xuất xong vector. Chuẩn bị lưu Database cho '{customer_name}'.")
        except Exception as e:
            print(f"[REGISTER] Cảnh báo lỗi ghi FAISS Local: {e}")

        self.clear_image_queue()
        print(f"[REGISTER] Hoàn thành luồng In-memory. Trả về vector và file ZIP (Dung lượng: {len(zip_bytes)/1024:.1f} KB)")

        # Trả về Dict cấu trúc chuẩn cho UI/Controller
        return {
            "face_vector": avg_vector,
            "images_zip_bytes": zip_bytes,
            "quality_score": avg_quality_score,
            "num_frames": len(best_frames)
        }

    def login_customer(
        self,
        num_images_to_capture=10,
        similarity_threshold=0.4,
        progress_callback=None,
        stop_flag_check=None,
    ):
        self._update_cache_state()
        if not self._cache_loaded:
            print("[LOGIN] Cảnh báo: Database rỗng. Không thể nhận diện.")
            if progress_callback:
                progress_callback(0, num_images_to_capture, "Database rỗng", error=True)
            return "Unknown"

        print("--- BẮT ĐẦU QUÁ TRÌNH NHẬN DIỆN ---")
        if progress_callback:
            progress_callback(0, num_images_to_capture, "Bắt đầu nhận diện...")

        votes = []
        liveness_failures = 0

        for i in range(num_images_to_capture):
            if stop_flag_check and stop_flag_check():
                print("[LOGIN] Người dùng hủy bỏ.")
                self.clear_image_queue()
                return "Unknown"

            msg = f"Đang lấy ảnh {i + 1}/{num_images_to_capture}..."
            if progress_callback:
                progress_callback(i, num_images_to_capture, msg)

            bgr_frame = self._get_image_from_camera(timeout=1.5)
            if bgr_frame is None:
                continue

            embedding, spoofed = self._extract_live_embedding(bgr_frame, require_quality=False)
            if spoofed:
                liveness_failures += 1
                if progress_callback:
                    progress_callback(i, num_images_to_capture, "CẢNH BÁO: Cố gắng giả mạo!")
                continue

            if embedding is None:
                continue

            best_name, best_score = self._match_embedding(embedding, similarity_threshold)
            if best_name is not None:
                print(f"  -> {best_name} (Score: {best_score:.4f})")
                votes.append(best_name)
            else:
                votes.append("Unknown")

            time.sleep(0.05)

        if progress_callback:
            progress_callback(num_images_to_capture, num_images_to_capture, "Đang xử lý kết quả...")
        
        if liveness_failures > (num_images_to_capture * 0.4):
            print(
                f"[LOGIN] TỪ CHỐI ĐĂNG NHẬP: Phát hiện tấn công giả mạo {liveness_failures}/{num_images_to_capture} frames."
            )
            self.clear_image_queue()
            return "Spoofing_Detected"

        result = "Unknown"
        if votes:
            name, count = Counter(votes).most_common(1)[0]
            if name != "Unknown" and count > (len(votes) // 4):
                result = name

        print(f"[LOGIN] Kết quả cuối cùng: {result}")
        self.clear_image_queue()
        return result

    def compress_images_to_zip_bytes(self, image_list):
        """
        Nén danh sách ảnh (RGB numpy array) thành file ZIP dạng bytes (In-memory).
        Dùng chuẩn JPEG 90% để tối ưu dung lượng (khoảng 100-150KB cho 50 ảnh).
        """
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            for idx, img in enumerate(image_list):
                bgr_img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                success, buffer = cv2.imencode(".jpg", bgr_img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                if success:
                    zip_file.writestr(f"face_{idx:03d}.jpg", buffer.tobytes())
        return zip_buffer.getvalue()

    def compute_average_embedding(self, face_vectors):
        """
        Tính vector trung bình từ danh sách các vectors.
        Đã bao gồm chuẩn hóa (Normalization) để tăng độ chính xác khi đối chiếu FAISS.
        """
        if not face_vectors:
            return None
        embeddings_np = np.array(face_vectors).astype(np.float32)
        avg_embedding = np.mean(embeddings_np, axis=0)
        
        # Chuẩn hóa (L2 Normalize)
        norm = np.linalg.norm(avg_embedding)
        if norm > 0:
            avg_embedding = avg_embedding / norm
            
        return avg_embedding
    
    def finalize_registration_async(self, user_id, name, phone, email, password, points, reg_data):
        """
        Xử lý lưu trữ thông tin đăng ký (gồm mật khẩu và điểm) cục bộ, nạp vector vào FAISS 
        và đẩy dữ liệu toàn vẹn lên Server qua một luồng chạy ngầm (Async Thread).
        """
        from core.database.local_database_manager import db_manager
        from core.features.api_manager import api_manager
        
        face_vector = reg_data['face_vector']
        images_zip_bytes = reg_data['images_zip_bytes']
        vector_blob = pickle.dumps(face_vector)
        
        # BƯỚC 1: Ghi nhận thông tin tài khoản trọn vẹn vào CSDL Local trước (is_synced = 0)
        db_manager.save_customer_with_face_data(
            user_id=user_id,
            name=name,
            phone=phone,
            email=email,
            password=password,
            points=points,
            face_vector=vector_blob,
            images_zip=None 
        )
        print(f"[LOCAL DB] Đã lưu dữ liệu định danh cho '{name}' (Thẻ SD).")

        #BƯỚC 2 REGISTER: Móc rowid và đẩy lên FAISS
        rowid = db_manager.get_rowid_by_user_id(user_id)
        if rowid:
            try:
                self.searcher.add_embedding(face_vector, rowid)
                self._update_cache_state()
            except Exception as e:
                print(f"[FAISS LOCAL] Lỗi nạp nhanh vector: {e}")

        # BƯỚC 3: Triển khai tác vụ mạng bất đồng bộ đẩy dữ liệu đầy đủ lên Server
        def background_upload_task():
            print(f"[ASYNC] Tiến hành tải gói thông tin trọn vẹn của '{name}' lên Server...")
            success, error_msg = api_manager.upload_customer_face_data(
                user_id, name, phone, email, password, points, face_vector, images_zip_bytes
            )
            
            if success:
                # Trường hợp 1: Đồng bộ thành công trực tiếp lên Server
                db_manager.update_sync_status(user_id, is_synced=1)
                print(f"[ASYNC] Đã đồng bộ tài khoản {user_id} lên Server. Thẻ SD an toàn.")
            else:
                # Trường hợp 2: Lỗi mạng/Mất kết nối -> Kích hoạt cơ chế lưu ảnh Fallback Offline
                print(f"[ASYNC] Không thể kết nối tới Server. Đang lưu ảnh nén ZIP vào SQLite làm dữ liệu dự phòng...")
                db_manager.save_customer_with_face_data(
                    user_id=user_id,
                    name=name,
                    phone=phone,
                    email=email,
                    password=password,
                    points=points,
                    face_vector=vector_blob,
                    images_zip=images_zip_bytes
                )
                print(f"[FALLBACK] Đã sao lưu dữ liệu hình ảnh offline thành công cho khách {user_id}.")

        # Kích hoạt Thread chạy độc lập để tránh làm đóng băng giao diện chính
        threading.Thread(target=background_upload_task, daemon=True).start()