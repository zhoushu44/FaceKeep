from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from uniface.parsing import BiSeNet

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
            self.parser = BiSeNet()
            self.session = None

    def process(self, image_bytes: bytes) -> bytes:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        cv_image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

        class_mask = self._parse(cv_image)
        alpha = self.create_alpha(class_mask)
        result = self.compose_rgba(cv_image, alpha)
        output = BytesIO()
        result.save(output, format="PNG")
        return output.getvalue()

    def create_alpha(self, class_mask: np.ndarray) -> np.ndarray:
        alpha = np.isin(class_mask, list(KEEP_FACE_CLASSES)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=1)
        alpha = cv2.GaussianBlur(alpha, (0, 0), 0.8)
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
