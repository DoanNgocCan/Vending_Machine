import os
import cv2
import torch
import faiss
import pickle
import numpy as np
import mediapipe as mp
from torchvision import transforms

from .backbones import get_model

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
MODULE_ROOT = os.path.dirname(os.path.abspath(__file__))

from core.Camera_AI.anti_spoofing.src.anti_spoof_predict import AntiSpoofPredict, Detection
from core.Camera_AI.anti_spoofing.src.generate_patches import CropImage
from core.Camera_AI.anti_spoofing.src.utility import parse_model_name

# Vô hiệu hóa Detection gốc để AntiSpoofPredict không cố tải RetinaFace.
Detection.__init__ = lambda self: None


class ModelEmbedding:
    """
    Tải model EdgeFace từ file checkpoint cục bộ và trích xuất đặc trưng.
    """

    def __init__(self, model_name="edgeface_base"):
        print(f"[MODEL] Đang tải model {model_name} từ file cục bộ...")

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.checkpoint_path = os.path.join(MODULE_ROOT, "checkpoints", f"{model_name}.pt")

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

        self.transform = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
            ]
        )

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

    def __init__(self, recognizer, model_name="edgeface_base", db_dir="database"):
        print("[FAISS] Khởi tạo hệ thống tìm kiếm...")
        self.recognizer = recognizer
        self.db_dir = db_dir
        self.cache_file = os.path.join(self.db_dir, f"face_cache_{model_name}.pkl")
        self.legacy_cache_file = os.path.join(self.db_dir, f"{model_name}_cache.pkl")

        self.embeddings = []
        self.labels = []
        self.name_map = {}
        self.index = None
        self.faiss_id_to_name = {}
        self.embedding_size = 512

        self._build_index()

    def _resolve_cache_file(self):
        if os.path.exists(self.cache_file):
            return self.cache_file
        if os.path.exists(self.legacy_cache_file):
            return self.legacy_cache_file
        return None

    def reload_index(self):
        self._build_index()

    def _build_index(self):
        self.embeddings = []
        self.labels = []
        self.name_map = {}
        self.faiss_id_to_name = {}

        cache_path = self._resolve_cache_file()
        if cache_path:
            print(f"[FAISS] Đang tải cache từ {cache_path}")
            try:
                with open(cache_path, "rb") as f:
                    cache = pickle.load(f)
                    self.embeddings = cache.get("embeddings", [])
                    self.labels = cache.get("labels", [])
                    self.name_map = cache.get("name_map", {})
            except Exception as e:
                print(f"[FAISS] Lỗi tải cache, sẽ xây dựng lại: {e}")
                self._build_from_database()
        else:
            print("[FAISS] Không tìm thấy cache, đang xây dựng từ database...")
            self._build_from_database()

        if not isinstance(self.embeddings, np.ndarray) or self.embeddings.size == 0:
            print("[FAISS] Database rỗng hoặc bị lỗi. Khởi tạo index rỗng.")
            self.embeddings = np.empty((0, self.embedding_size), dtype=np.float32)
            self.labels = np.empty((0,), dtype=np.int32)
            self.name_map = {}
        else:
            self.embeddings = np.asarray(self.embeddings, dtype=np.float32)
            if self.embeddings.ndim == 1:
                self.embeddings = self.embeddings.reshape(1, -1)
            self.embedding_size = int(self.embeddings.shape[1])
            faiss.normalize_L2(self.embeddings)

            labels_arr = np.asarray(self.labels).reshape(-1) if self.labels is not None else np.array([], dtype=np.int32)
            if labels_arr.size < len(self.embeddings):
                pad = np.zeros((len(self.embeddings) - labels_arr.size,), dtype=np.int32)
                labels_arr = np.hstack([labels_arr.astype(np.int32, copy=False), pad])
            elif labels_arr.size > len(self.embeddings):
                labels_arr = labels_arr[:len(self.embeddings)]
            self.labels = labels_arr.astype(np.int32, copy=False)

        self.index = faiss.IndexFlatIP(self.embedding_size)

        if self.embeddings.shape[0] > 0:
            self.index.add(self.embeddings)
            for i in range(len(self.embeddings)):
                label_idx = int(self.labels[i]) if len(self.labels) > i else 0
                self.faiss_id_to_name[i] = self.name_map.get(label_idx, "Unknown")

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

        for person_name in sorted(os.listdir(self.db_dir)):
            person_path = os.path.join(self.db_dir, person_name)
            if not os.path.isdir(person_path):
                continue

            print(f"[FAISS] Đang quét ảnh cho: {person_name}")
            self.name_map[person_idx] = person_name

            person_embeddings = []
            for file_name in os.listdir(person_path):
                if not (file_name.endswith(".jpg") or file_name.endswith(".png")):
                    continue

                img_path = os.path.join(person_path, file_name)
                img = cv2.imread(img_path)
                if img is None:
                    continue

                img_resized = cv2.resize(img, (112, 112))
                img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)

                emb = self.recognizer.get_embedding(img_rgb)
                if emb is not None:
                    person_embeddings.append(emb[0])

            if person_embeddings:
                person_embeddings_np = np.array(person_embeddings).astype(np.float32)
                avg_embedding = np.mean(person_embeddings_np, axis=0, keepdims=False)
                faiss.normalize_L2(avg_embedding.reshape(1, -1))

                self.embeddings.append(avg_embedding)
                self.labels.append(person_idx)
                print(f"[FAISS] Đã tạo 1 vector trung bình cho {person_name} từ {len(person_embeddings)} ảnh.")

            person_idx += 1

        if self.embeddings:
            self.embeddings = np.array(self.embeddings).astype(np.float32)
            self.labels = np.array(self.labels, dtype=np.int32)
            self._save_cache()
        else:
            print("[FAISS] Không tìm thấy ảnh nào trong database.")

    def _save_cache(self):
        try:
            os.makedirs(self.db_dir, exist_ok=True)
            with open(self.cache_file, "wb") as f:
                pickle.dump(
                    {
                        "embeddings": self.embeddings,
                        "labels": self.labels,
                        "name_map": self.name_map,
                    },
                    f,
                )
            print(f"[FAISS] Đã lưu cache vào {self.cache_file}")
        except Exception as e:
            print(f"[FAISS] Lỗi khi lưu cache: {e}")

    def search(self, query_emb, topk=1):
        if self.index is None or self.index.ntotal == 0:
            return []
        try:
            query = np.asarray(query_emb, dtype=np.float32)
            if query.ndim == 1:
                query = np.expand_dims(query, axis=0)
            faiss.normalize_L2(query)

            D, I = self.index.search(query, int(max(1, topk)))
            results = []
            for idx, score in zip(I[0], D[0]):
                if idx == -1:
                    continue
                name = self.faiss_id_to_name.get(int(idx), "Unknown")
                results.append((name, float(score)))
            return results
        except Exception as e:
            print(f"[FAISS] Lỗi khi tìm kiếm: {e}")
            return []

    def add_embedding(self, new_embs, person_name):
        vectors = np.asarray(new_embs, dtype=np.float32)
        if vectors.ndim == 1:
            vectors = np.expand_dims(vectors, axis=0)

        if vectors.size == 0:
            return

        if self.index is None:
            self.index = faiss.IndexFlatIP(self.embedding_size)

        if vectors.shape[1] != self.embedding_size:
            if self.index is not None and self.index.ntotal == 0:
                self.embedding_size = int(vectors.shape[1])
                self.index = faiss.IndexFlatIP(self.embedding_size)
                self.embeddings = np.empty((0, self.embedding_size), dtype=np.float32)
                self.labels = np.empty((0,), dtype=np.int32)
            else:
                print("[FAISS] Lỗi: kích thước embedding không khớp index hiện tại.")
                return

        faiss.normalize_L2(vectors)

        if person_name in self.name_map.values():
            new_label = [k for k, v in self.name_map.items() if v == person_name][0]
            print(f"[FAISS] {person_name} đã tồn tại, dùng lại label {new_label}.")
        else:
            new_label = len(self.name_map)
            self.name_map[new_label] = person_name
            print(f"[FAISS] Tạo label mới {new_label} cho {person_name}.")

        start_id = self.index.ntotal
        self.index.add(vectors)

        if not isinstance(self.embeddings, np.ndarray) or self.embeddings.size == 0:
            self.embeddings = np.empty((0, self.embedding_size), dtype=np.float32)
        if not isinstance(self.labels, np.ndarray) or self.labels.size == 0:
            self.labels = np.empty((0,), dtype=np.int32)

        self.embeddings = np.vstack([self.embeddings, vectors])
        new_labels_arr = np.array([new_label] * len(vectors), dtype=np.int32)
        self.labels = np.hstack([self.labels, new_labels_arr])

        for i in range(len(vectors)):
            self.faiss_id_to_name[start_id + i] = person_name

        print(f"[FAISS] Đã thêm {len(vectors)} vector trung bình cho {person_name}.")
        self._save_cache()


class MediaPipeFaceDetector:
    """
    Sử dụng MediaPipe để phát hiện khuôn mặt và 6 điểm mốc chính.
    """

    def __init__(self):
        print("[DETECT] Đang tải model MediaPipe Face Detection...")
        self.detector = mp.solutions.face_detection.FaceDetection(
            model_selection=0, min_detection_confidence=0.7
        )
        print("[DETECT] Tải model MediaPipe thành công.")

    def detect(self, frame_bgr):
        try:
            h, w, _ = frame_bgr.shape
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self.detector.process(rgb)

            detected_faces = []

            if results.detections:
                for det in results.detections:
                    bbox_data = det.location_data.relative_bounding_box
                    x1 = int(bbox_data.xmin * w)
                    y1 = int(bbox_data.ymin * h)
                    x2 = x1 + int(bbox_data.width * w)
                    y2 = y1 + int(bbox_data.height * h)

                    bbox = (max(0, x1), max(0, y1), min(w, x2), min(h, y2))

                    keypoints = {}
                    kp_names = [
                        "right_eye",
                        "left_eye",
                        "nose_tip",
                        "mouth_center",
                        "right_ear_tragion",
                        "left_ear_tragion",
                    ]

                    for i, kp in enumerate(det.location_data.relative_keypoints):
                        keypoints[kp_names[i]] = (int(kp.x * w), int(kp.y * h))

                    detected_faces.append((bbox, keypoints))

            return detected_faces

        except Exception as e:
            print(f"[DETECT] Lỗi MediaPipe: {e}")
            return []


class LivenessDetector:
    def __init__(self, model_dir="anti_spoofing/resources/anti_spoof_models", device_id=0):
        print("[LIVENESS] Đang tải mô hình chống giả mạo...")
        self.model_dir = os.path.join(MODULE_ROOT, model_dir)
        self.model_test = AntiSpoofPredict(device_id)
        self.image_cropper = CropImage()
        self.models = [m for m in os.listdir(self.model_dir) if "MiniFASNet" in m]
        print(f"[LIVENESS] Đã tải {len(self.models)} model chống giả mạo.")

    def check_liveness(self, frame_bgr, bbox):
        h_img, w_img, _ = frame_bgr.shape
        x1, y1, x2, y2 = bbox

        w_box = x2 - x1
        h_box = y2 - y1
        x1 = max(0, x1 - int(w_box * 0.1))
        y1 = max(0, y1 - int(h_box * 0.15))
        x2 = min(w_img, x2 + int(w_box * 0.1))
        y2 = min(h_img, y2 + int(h_box * 0.1))

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

        is_real = label == 1
        return is_real, score


def align_face_112(frame_bgr, keypoints):
    """
    Căn chỉnh (xoay + co giãn) khuôn mặt về 112x112
    dựa trên 3 điểm mốc: 2 mắt và chóp mũi.
    """

    try:
        src_pts = np.array(
            [
                keypoints["right_eye"],
                keypoints["left_eye"],
                keypoints["nose_tip"],
            ],
            dtype=np.float32,
        )

        dst_pts = np.array(
            [
                [38.2946, 51.6963],
                [73.5318, 51.5014],
                [56.0252, 71.7366],
            ],
            dtype=np.float32,
        )

        matrix = cv2.getAffineTransform(src_pts, dst_pts)
        aligned_face = cv2.warpAffine(
            frame_bgr,
            matrix,
            (112, 112),
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

        return aligned_face

    except Exception as e:
        print(f"[ALIGN] Lỗi khi căn chỉnh: {e}")
        return None
