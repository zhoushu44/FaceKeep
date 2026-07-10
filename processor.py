from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

KEEP_FACE_CLASSES = {
    1,  # skin
    2,  # left eyebrow
    3,  # right eyebrow
    4,  # left eye
    5,  # right eye
    6,  # eyeglasses
    7,  # left ear
    8,  # right ear
    10,  # nose
    11,  # mouth
    12,  # upper lip
    13,  # lower lip
    17,  # hair
}


class AvatarProcessor:
    def __init__(self) -> None:
        local_model = Path(__file__).parent / "models" / "parsing_resnet18.onnx"
        if local_model.exists():
            import onnxruntime as ort
            self.session = ort.InferenceSession(str(local_model), providers=["CPUExecutionProvider"])
            self.input_name = self.session.get_inputs()[0].name
            self.input_size = tuple(self.session.get_inputs()[0].shape[2:4][::-1])
            self.input_mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
            self.input_std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        else:
            from uniface.parsing import BiSeNet

            self.parser = BiSeNet()
            self.session = None
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        self.face_detector = cv2.CascadeClassifier(str(cascade_path))

    def process(self, image_bytes: bytes) -> bytes:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        cv_image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        alpha = self.create_multi_avatar_alpha(cv_image)
        result = self.compose_rgba(cv_image, alpha)
        output = BytesIO()
        result.save(output, format="PNG")
        return output.getvalue()

    def create_multi_avatar_alpha(self, cv_image: np.ndarray) -> np.ndarray:
        boxes = self.detect_face_boxes(cv_image)
        if not boxes:
            class_mask = self._parse(cv_image)
            return self.create_alpha(class_mask)

        h, w = cv_image.shape[:2]
        merged = np.zeros((h, w), dtype=np.uint8)
        for x1, y1, x2, y2 in boxes:
            crop = cv_image[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            class_mask = self._parse(crop)
            crop_alpha = self.create_alpha(class_mask)
            merged[y1:y2, x1:x2] = np.maximum(merged[y1:y2, x1:x2], crop_alpha)

        if merged.max() == 0:
            class_mask = self._parse(cv_image)
            return self.create_alpha(class_mask)
        return self.refine_alpha(merged)

    def detect_face_boxes(self, cv_image: np.ndarray) -> list[tuple[int, int, int, int]]:
        h, w = cv_image.shape[:2]
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        faces = self.face_detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28))
        boxes: list[tuple[int, int, int, int]] = []
        for x, y, fw, fh in faces:
            cx = x + fw / 2
            cy = y + fh / 2
            side = max(fw, fh) * 2.45
            x1 = max(0, int(cx - side * 0.5))
            y1 = max(0, int(cy - side * 0.58))
            x2 = min(w, int(cx + side * 0.5))
            y2 = min(h, int(cy + side * 0.62))
            if x2 - x1 >= 24 and y2 - y1 >= 24:
                boxes.append((x1, y1, x2, y2))
        return self.merge_boxes(boxes, w, h)

    def merge_boxes(self, boxes: list[tuple[int, int, int, int]], width: int, height: int) -> list[tuple[int, int, int, int]]:
        merged: list[tuple[int, int, int, int]] = []
        for box in sorted(boxes, key=lambda item: (item[1], item[0])):
            x1, y1, x2, y2 = box
            matched = False
            for index, current in enumerate(merged):
                if self.iou(box, current) > 0.28 or self.intersects(box, current):
                    cx1, cy1, cx2, cy2 = current
                    merged[index] = (max(0, min(x1, cx1)), max(0, min(y1, cy1)), min(width, max(x2, cx2)), min(height, max(y2, cy2)))
                    matched = True
                    break
            if not matched:
                merged.append(box)
        return merged

    def intersects(self, a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0, min(ay2, by2) - max(ay1, by1))
        if inter_w == 0 or inter_h == 0:
            return False
        smaller = min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1))
        return inter_w * inter_h / max(smaller, 1) > 0.22

    def iou(self, a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_w = max(0, min(ax2, bx2) - max(ax1, bx1))
        inter_h = max(0, min(ay2, by2) - max(ay1, by1))
        inter = inter_w * inter_h
        area_a = (ax2 - ax1) * (ay2 - ay1)
        area_b = (bx2 - bx1) * (by2 - by1)
        return inter / max(area_a + area_b - inter, 1)

    def create_alpha(self, class_mask: np.ndarray) -> np.ndarray:
        alpha = np.isin(class_mask, list(KEEP_FACE_CLASSES)).astype(np.uint8) * 255
        return self.refine_alpha(alpha)

    def refine_alpha(self, alpha: np.ndarray) -> np.ndarray:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=2)
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel, iterations=1)
        alpha = cv2.GaussianBlur(alpha, (0, 0), 1.2)
        return alpha

    def compose_rgba(self, cv_image: np.ndarray, alpha: np.ndarray) -> Image.Image:
        rgb = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb).convert("RGBA")
        pil_img.putalpha(Image.fromarray(alpha))
        return pil_img

    def _parse(self, cv_image: np.ndarray) -> np.ndarray:
        h, w = cv_image.shape[:2]
        if self.session is None:
            return self.parser.parse(cv_image)
        resized = cv2.resize(cv_image, self.input_size, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        norm = (rgb.astype(np.float32) / 255.0 - self.input_mean) / self.input_std
        blob = norm.transpose(2, 0, 1)[None, ...]
        outputs = self.session.run(None, {self.input_name: blob})
        parsing = outputs[0].argmax(axis=1)[0]
        return cv2.resize(parsing.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
