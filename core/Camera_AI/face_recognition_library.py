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
    Quản lý FAISS thuần In-Memory. 
    Không ghi file, mapping ID số nguyên trực tiếp với rowid của SQLite.
    """

    def __init__(self, recognizer, model_name="edgeface_base"):
        print("[FAISS] Khởi tạo hệ thống tìm kiếm In-Memory (RAM)...")
        self.recognizer = recognizer
        self.embedding_size = 512
        
        # BƯỚC 1 BOOT UP: Khởi tạo IndexIDMap rỗng trên RAM
        self.index = faiss.IndexIDMap(faiss.IndexFlatIP(self.embedding_size))

    def load_from_db(self, vectors, rowids):
        """Nạp hàng loạt dữ liệu từ SQLite lên RAM lúc khởi động"""
        if not vectors:
            print("[FAISS] Database rỗng, chưa có vector nào được nạp.")
            return
            
        vec_np = np.array(vectors).astype(np.float32)
        id_np = np.array(rowids).astype(np.int64) # FAISS ID bắt buộc là int64
        
        if vec_np.ndim == 1:
            vec_np = vec_np.reshape(1, -1)
            
        faiss.normalize_L2(vec_np)
        self.index.add_with_ids(vec_np, id_np)
        print(f"[FAISS] Đã nạp thành công {self.index.ntotal} vector vào RAM.")

    def search(self, query_emb, topk=1):
        """Tìm kiếm trả về thẳng rowid"""
        if self.index is None or self.index.ntotal == 0:
            return []
            
        query = np.asarray(query_emb, dtype=np.float32)
        if query.ndim == 1:
            query = np.expand_dims(query, axis=0)
        faiss.normalize_L2(query)

        # BƯỚC 2 LOGIN: Yêu cầu FAISS search
        D, I = self.index.search(query, int(max(1, topk)))
        results = []
        for idx, score in zip(I[0], D[0]):
            if idx != -1:  # -1 nghĩa là không tìm thấy
                results.append((int(idx), float(score))) # Trả về (rowid, score)
        return results

    def add_embedding(self, vector, rowid):
        """Bắn vector mới trực tiếp lên RAM (Register)"""
        vec_np = np.asarray(vector, dtype=np.float32)
        if vec_np.ndim == 1:
            vec_np = np.expand_dims(vec_np, axis=0)
            
        faiss.normalize_L2(vec_np)
        id_np = np.array([rowid], dtype=np.int64)
        
        # BƯỚC 4 REGISTER: Map vector và rowid vào FAISS
        self.index.add_with_ids(vec_np, id_np)
        print(f"[FAISS] Đã cập nhật vector cho rowid={rowid} lên RAM tức thì.")


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
