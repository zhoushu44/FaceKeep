from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models"


@dataclass(frozen=True)
class ModelConfig:
    repo_id: str
    filename: str
    local_path: Path


RETINAFACE_MODEL = ModelConfig(
    repo_id="public-data/insightface-retinaface",
    filename="retinaface_resnet50.onnx",
    local_path=MODELS_DIR / "retinaface_resnet50.onnx",
)

RMBG_MODEL = ModelConfig(
    repo_id="briaai/RMBG-2.0",
    filename="model.onnx",
    local_path=MODELS_DIR / "rmbg_2_0.onnx",
)

INPUT_SIZE = 1024
OUTPUT_SIZE = 512
