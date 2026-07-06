from huggingface_hub import hf_hub_download

from models import MODELS_DIR, RETINAFACE_MODEL, RMBG_MODEL, ModelConfig


MODELS = (RETINAFACE_MODEL, RMBG_MODEL)


def ensure_model(config: ModelConfig) -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if config.local_path.exists():
        return

    downloaded = hf_hub_download(
        repo_id=config.repo_id,
        filename=config.filename,
        local_dir=MODELS_DIR,
        local_dir_use_symlinks=False,
    )
    source = MODELS_DIR / config.filename
    if source.exists() and source != config.local_path:
        source.replace(config.local_path)
    elif downloaded != str(config.local_path):
        config.local_path.write_bytes(source.read_bytes())


def ensure_models() -> None:
    for config in MODELS:
        ensure_model(config)


if __name__ == "__main__":
    ensure_models()
    print("Models are ready.")
