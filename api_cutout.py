"""API 模式抠图处理器"""
import base64
import os
import tempfile
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent


def load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'").strip("`")
        os.environ.setdefault(key, value)


load_env_file()

CUTOUT_MODE = os.getenv("CUTOUT_MODE", "local").strip().lower()
IMAGE_API_KEY = os.getenv("IMAGE_API_KEY", "")
IMAGE_API_BASE_URL = os.getenv("IMAGE_API_BASE_URL", "").rstrip("/")
IMAGE_API_MODEL = os.getenv("IMAGE_API_MODEL", "gpt-image-2")

OUTPUT_WIDTH = int(os.getenv("OUTPUT_WIDTH", "1500"))
OUTPUT_DPI = int(os.getenv("OUTPUT_DPI", "96"))
OUTPUT_PADDING = int(os.getenv("OUTPUT_PADDING", "10"))

PROMPT = (
    "Remove background completely. Keep ONLY the person's head including hair, "
    "face, eyebrows, eyes, nose, mouth, ears. NO neck, NO shoulders, NO body. "
    "Output as transparent background PNG portrait."
)


class APICutoutProcessor:
    """API 模式抠图处理器"""

    def __init__(self) -> None:
        self.api_key = IMAGE_API_KEY
        self.base_url = IMAGE_API_BASE_URL
        self.model = IMAGE_API_MODEL
        self.timeout = 180

    def process(self, image_bytes: bytes) -> bytes:
        img = Image.open(BytesIO(image_bytes)).convert("RGBA")
        temp_png = Path(tempfile.mktemp(suffix=".png", prefix="facekeep_api_"))
        img.save(temp_png, format="PNG")

        try:
            result = self._call_api(temp_png)
            if result is None:
                raise RuntimeError("API call failed")
            return result
        finally:
            temp_png.unlink(missing_ok=True)

    def _call_api(self, image_path: Path) -> bytes | None:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        with image_path.open("rb") as image_file:
            files = {"image": ("image.png", image_file, "image/png")}
            data = {
                "model": self.model,
                "prompt": PROMPT,
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",
            }
            response = requests.post(
                f"{self.base_url}/images/edits",
                headers=headers,
                files=files,
                data=data,
                timeout=self.timeout,
            )

        if not response.ok:
            raise RuntimeError(f"API call failed: HTTP {response.status_code} {response.text[:300]}")

        result = response.json()
        if "data" not in result or not result["data"]:
            raise RuntimeError(f"API call failed: unexpected response {str(result)[:300]}")

        image_data = result["data"][0]
        if "b64_json" in image_data:
            return base64.b64decode(image_data["b64_json"])
        if "url" in image_data:
            resp = requests.get(image_data["url"], timeout=60)
            if resp.ok:
                return resp.content
            raise RuntimeError(f"API image download failed: HTTP {resp.status_code}")
        return None


def get_cutout_processor(mode: str | None = None):
    mode = (mode or CUTOUT_MODE).strip().lower()
    if mode == "api":
        if not IMAGE_API_KEY or not IMAGE_API_BASE_URL:
            raise ValueError("API mode requires IMAGE_API_KEY and IMAGE_API_BASE_URL")
        return APICutoutProcessor()

    from processor import AvatarProcessor
    return AvatarProcessor()


def format_output_png(image_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    width, height = img.size
    padded = Image.new("RGBA", (width + 2 * OUTPUT_PADDING, height + 2 * OUTPUT_PADDING), (0, 0, 0, 0))
    padded.paste(img, (OUTPUT_PADDING, OUTPUT_PADDING))

    target_height = max(1, round(padded.height * OUTPUT_WIDTH / padded.width))
    padded = padded.resize((OUTPUT_WIDTH, target_height), Image.Resampling.LANCZOS)

    output = BytesIO()
    padded.save(output, format="PNG", dpi=(OUTPUT_DPI, OUTPUT_DPI))
    return output.getvalue()


def process_with_padding(image_bytes: bytes, processor=None) -> bytes:
    processor = processor or get_cutout_processor()
    return format_output_png(processor.process(image_bytes))


if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 2:
        print("Usage: python api_cutout.py <image_path>")
        sys.exit(1)

    image_path = Path(sys.argv[1])
    start = time.time()
    result = process_with_padding(image_path.read_bytes())
    output_path = image_path.with_suffix(".cutout.png")
    output_path.write_bytes(result)

    img = Image.open(BytesIO(result))
    print(f"Output: {output_path}")
    print(f"Size: {img.size}")
    print(f"DPI: {img.info.get('dpi')}")
    print(f"Time: {time.time() - start:.2f}s")
