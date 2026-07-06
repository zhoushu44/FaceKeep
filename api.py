from functools import lru_cache

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response

from processor import AvatarProcessor

app = FastAPI(title="Avatar Cutout API")


@lru_cache(maxsize=1)
def get_processor() -> AvatarProcessor:
    return AvatarProcessor()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/avatar")
async def create_avatar(file: UploadFile = File(...)) -> Response:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported.")

    image_bytes = await file.read()
    try:
        output = get_processor().process(image_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(content=output, media_type="image/png")
