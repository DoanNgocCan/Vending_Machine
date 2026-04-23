import os
import time
import queue
import threading
import numpy as np
from collections import Counter
import cv2

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
        self.searcher = FastFaceSearch(
            recognizer=self.recognizer,
            model_name=self.MODEL_NAME,
            db_dir=self.DATABASE_DIR,
        )

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
        print("[FR_HANDLER] Yêu cầu tải lại dữ liệu cache nhận diện...")
        self.searcher.reload_index()
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
                    self.cap = cv2.VideoCapture(0)
                    if not self.cap.isOpened():
                        self._camera_running = False
                        continue
                except Exception:
                    self._camera_running = False
                    continue

            if self.cap is not None and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    if self.image_queue.full():
                        try:
                            self.image_queue.get_nowait()
                        except queue.Empty:
                            pass
                    self.latest_frame_for_display = frame
                    self.image_queue.put(frame)
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
    def _is_frame_quality_good(self, frame_bgr):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        focus_val = cv2.Laplacian(gray, cv2.CV_64F).var()
        brightness = gray.mean()
        return (
            focus_val >= BLUR_THRESHOLD
            and BRIGHTNESS_MIN <= brightness <= BRIGHTNESS_MAX
        )

    def _extract_live_embedding(self, frame_bgr, require_quality=False):
        if require_quality and not self._is_frame_quality_good(frame_bgr):
            return None, False

        detected_faces = self.detector.detect(frame_bgr)
        if not detected_faces:
            return None, False

        bbox, keypoints = detected_faces[0]

        is_real, _ = self.liveness.check_liveness(frame_bgr, bbox)
        if not is_real:
            return None, True

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
        results = self.searcher.search(embedding, topk=1)
        if not results:
            return None, 0.0

        best_name, best_score = results[0]
        if best_name != "Unknown" and best_score >= similarity_threshold:
            return best_name, best_score

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
        num_images_to_capture=100,
        progress_callback=None,
        stop_flag_check=None,
    ):
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
            if bgr_frame is None:
                continue

            detected_faces = self.detector.detect(bgr_frame)
            if not detected_faces:
                continue

            bbox, keypoints = detected_faces[0]

            is_real, _ = self.liveness.check_liveness(bgr_frame, bbox)
            if not is_real:
                if progress_callback:
                    progress_callback(
                        len(captured_data_buffer),
                        num_images_to_capture,
                        "⚠️ Vui lòng dùng khuôn mặt thật!",
                        error=True,
                    )
                continue

            aligned_face_bgr = align_face_112(bgr_frame, keypoints)
            if aligned_face_bgr is None:
                continue

            rgb_face_112 = cv2.cvtColor(aligned_face_bgr, cv2.COLOR_BGR2RGB)
            embedding = self.recognizer.get_embedding(rgb_face_112)
            if embedding is None:
                continue

            captured_data_buffer.append(
                {
                    "image": rgb_face_112,
                    "embedding": embedding[0],
                }
            )

            if progress_callback:
                progress_callback(len(captured_data_buffer), num_images_to_capture, "CAPTURING")

        if progress_callback:
            progress_callback(num_images_to_capture, num_images_to_capture, "Đang lưu dữ liệu...")

        person_dir = os.path.join(self.searcher.db_dir, customer_name)
        os.makedirs(person_dir, exist_ok=True)

        all_embeddings = []
        for idx, data in enumerate(captured_data_buffer):
            if stop_flag_check and stop_flag_check():
                return False

            face_img = data["image"]
            emb_vec = data["embedding"]
            all_embeddings.append(emb_vec)

            save_path = os.path.join(person_dir, f"{idx:03d}.jpg")
            cv2.imwrite(save_path, cv2.cvtColor(face_img, cv2.COLOR_RGB2BGR))

        success = False
        if all_embeddings:
            embeddings_np = np.array(all_embeddings).astype(np.float32)
            avg_embedding = np.mean(embeddings_np, axis=0, keepdims=True)
            self.searcher.add_embedding(avg_embedding, customer_name)

            last_img = captured_data_buffer[-1]["image"]
            cv2.imwrite(
                os.path.join(person_dir, "000_avg_ref.jpg"),
                cv2.cvtColor(last_img, cv2.COLOR_RGB2BGR),
            )
            success = True
            self._update_cache_state()
        else:
            if progress_callback:
                progress_callback(0, num_images_to_capture, "Lỗi: Không có dữ liệu AI", error=True)

        self.clear_image_queue()
        return success

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
