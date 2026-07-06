from io import BytesIO

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
        self.parser = BiSeNet()

    def process(self, image_bytes: bytes) -> bytes:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        cv_image = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)

        class_mask = self.parser.parse(cv_image)
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
