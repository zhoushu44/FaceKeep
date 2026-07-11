from functools import lru_cache
from io import BytesIO
from pathlib import Path
import hashlib
import hmac
import json
import os
import secrets
import shutil
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel
from PIL import Image
import cv2

from api_cutout import OUTPUT_DPI, OUTPUT_WIDTH, get_cutout_processor, process_with_padding

app = FastAPI(title="FaceKeep File Manager API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent


def load_env() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_TOKENS: set[str] = set()
STORAGE_DIR = BASE_DIR / "uploads"
CHUNKS_DIR = STORAGE_DIR / "chunks"
FILES_DIR = STORAGE_DIR / "files"
TASKS_DIR = STORAGE_DIR / "tasks"
META_FILE = STORAGE_DIR / "metadata.json"
OUTPUT_FORMAT = "PNG"
PNG_WIDTH = OUTPUT_WIDTH
PNG_DPI = OUTPUT_DPI


class UploadSessionRequest(BaseModel):
    fileName: str
    fileSize: int
    fileType: str = ""
    relativePath: str | None = None
    fingerprint: str
    totalChunks: int


class CompleteUploadRequest(BaseModel):
    uploadId: str


class CreateUserRequest(BaseModel):
    username: str
    name: str
    password: str
    credits: int = 0


class UpdateUserRequest(BaseModel):
    username: str | None = None
    name: str | None = None
    apiKey: str | None = None
    password: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AdjustCreditsRequest(BaseModel):
    amount: int
    reason: str = "manual_adjustment"


class SetCreditsRequest(BaseModel):
    credits: int
    reason: str = "set_credits"


@lru_cache(maxsize=1)
def get_processor():
    return get_cutout_processor()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_storage() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    if not META_FILE.exists():
        save_meta({"sessions": {}, "files": [], "tasks": {}, "users": {}, "creditRecords": []})


def load_meta() -> dict:
    ensure_storage_dirs_only()
    if not META_FILE.exists():
        return {"sessions": {}, "files": [], "tasks": {}, "users": {}, "creditRecords": []}
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    meta.setdefault("sessions", {})
    meta.setdefault("files", [])
    meta.setdefault("tasks", {})
    meta.setdefault("users", {})
    meta.setdefault("creditRecords", [])
    return meta


def save_meta(meta: dict) -> None:
    ensure_storage_dirs_only()
    temp_file = META_FILE.with_suffix(".json.tmp")
    temp_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(META_FILE)


def ensure_storage_dirs_only() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_name(name: str) -> str:
    cleaned = Path(name).name.replace("\x00", "").strip()
    return cleaned or "upload.bin"


def get_uploaded_chunks(upload_id: str) -> list[int]:
    chunk_dir = CHUNKS_DIR / upload_id
    if not chunk_dir.exists():
        return []
    chunks = []
    for path in chunk_dir.glob("*.part"):
        try:
            chunks.append(int(path.stem))
        except ValueError:
            continue
    return sorted(chunks)


def generate_api_key() -> str:
    return f"fk_{uuid.uuid4().hex}{uuid.uuid4().hex[:8]}"


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or uuid.uuid4().hex
    digest = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return salt, digest


def verify_password(password: str, user: dict) -> bool:
    salt = user.get("passwordSalt")
    expected = user.get("passwordHash")
    if not salt or not expected:
        return False
    _, digest = hash_password(password, salt)
    return digest == expected


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user.get("username", ""),
        "name": user["name"],
        "apiKey": user["apiKey"],
        "credits": user.get("credits", 0),
        "createdAt": user.get("createdAt"),
        "updatedAt": user.get("updatedAt"),
    }


def require_admin(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Administrator authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or token not in ADMIN_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid administrator token")
    return token


def find_user_by_key(api_key: str | None) -> dict:
    if not api_key:
        raise HTTPException(status_code=401, detail="API key is required")
    meta = load_meta()
    for user in meta.get("users", {}).values():
        if user.get("apiKey") == api_key:
            return user
    raise HTTPException(status_code=401, detail="Invalid API key")


def add_credit_record(meta: dict, user_id: str, amount: int, balance: int, reason: str, task_id: str | None = None) -> dict:
    record = {
        "id": uuid.uuid4().hex,
        "userId": user_id,
        "amount": amount,
        "balance": balance,
        "reason": reason,
        "taskId": task_id,
        "createdAt": utc_now(),
    }
    meta.setdefault("creditRecords", []).insert(0, record)
    return record


def count_heads(source_path: Path) -> int:
    image = cv2.imread(str(source_path))
    if image is None:
        return 1
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    faces = detector.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(32, 32))
    return max(1, len(faces))


def deduct_credit_for_task(meta: dict, user_id: str, task_id: str) -> dict:
    user = meta.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if int(user.get("credits", 0)) < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    user["credits"] = int(user.get("credits", 0)) - 1
    user["updatedAt"] = utc_now()
    add_credit_record(meta, user_id, -1, user["credits"], "task_image_cost", task_id)
    return user


def refund_failed_task(meta: dict, task: dict) -> None:
    if task.get("creditRefunded"):
        return
    user = meta.get("users", {}).get(task.get("userId"))
    if not user:
        return
    user["credits"] = int(user.get("credits", 0)) + 1
    user["updatedAt"] = utc_now()
    task["creditRefunded"] = True
    add_credit_record(meta, user["id"], 1, user["credits"], "failed_task_refund", task["taskId"])


def find_file(file_id: str) -> dict:
    meta = load_meta()
    for item in meta.get("files", []):
        if item["id"] == file_id:
            return item
    raise HTTPException(status_code=404, detail="File not found")


def find_task(task_id: str) -> dict:
    meta = load_meta()
    task = meta.get("tasks", {}).get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def save_png_from_path(source_path: Path, target_path: Path, cutout: bool = False) -> tuple[int, int]:
    if cutout:
        output = process_with_padding(source_path.read_bytes(), get_processor())
        target_path.write_bytes(output)
        image = Image.open(BytesIO(output))
        return image.size

    image = Image.open(source_path).convert("RGBA")
    width, height = image.size
    target_height = max(1, round(height * PNG_WIDTH / width))
    image = image.resize((PNG_WIDTH, target_height), Image.Resampling.LANCZOS)
    image.save(target_path, format="PNG", dpi=(PNG_DPI, PNG_DPI))
    return PNG_WIDTH, target_height


def run_image_task(task_id: str) -> None:
    meta = load_meta()
    task = meta.get("tasks", {}).get(task_id)
    if not task:
        return
    task["status"] = "processing"
    task["progress"] = 30
    task["updatedAt"] = utc_now()
    save_meta(meta)

    try:
        source_path = Path(task["sourcePath"])
        output_path = TASKS_DIR / f"{task_id}_1500w_96dpi.png"
        width, height = save_png_from_path(source_path, output_path, cutout=True)
        meta = load_meta()
        task = meta["tasks"][task_id]
        task.update(
            {
                "status": "completed",
                "progress": 100,
                "outputPath": str(output_path),
                "outputWidth": width,
                "outputHeight": height,
                "imageUrl": f"/api/tasks/{task_id}/image",
                "updatedAt": utc_now(),
            }
        )
        save_meta(meta)
    except Exception as exc:
        meta = load_meta()
        task = meta.get("tasks", {}).get(task_id)
        if task:
            task.update({"status": "failed", "progress": 100, "error": str(exc), "updatedAt": utc_now()})
            refund_failed_task(meta, task)
            save_meta(meta)


def public_task(task: dict) -> dict:
    return {
        "taskId": task["taskId"],
        "status": task["status"],
        "progress": task.get("progress", 0),
        "fileName": task.get("fileName"),
        "imageUrl": task.get("imageUrl"),
        "outputWidth": task.get("outputWidth"),
        "outputHeight": task.get("outputHeight"),
        "headCount": task.get("headCount", 1),
        "creditCost": task.get("creditCost", 1),
        "dpi": PNG_DPI,
        "format": OUTPUT_FORMAT,
        "error": task.get("error"),
        "createdAt": task.get("createdAt"),
        "updatedAt": task.get("updatedAt"),
    }


def to_public_file(item: dict) -> dict:
    return {
        "id": item["id"],
        "fileName": item["fileName"],
        "fileSize": item["fileSize"],
        "fileType": item.get("fileType", ""),
        "relativePath": item.get("relativePath"),
        "url": f"/api/files/{item['id']}",
        "pngUrl": f"/api/files/{item['id']}/png",
        "createdAt": item["createdAt"],
    }


@app.get("/health")
def health() -> dict[str, str]:
    ensure_storage()
    return {"status": "ok"}


@app.post("/api/admin/login")
def admin_login(payload: LoginRequest) -> dict:
    if not ADMIN_USERNAME or not ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Administrator credentials are not configured")
    if not hmac.compare_digest(payload.username, ADMIN_USERNAME) or not hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid administrator credentials")
    token = secrets.token_urlsafe(48)
    ADMIN_TOKENS.add(token)
    return {"token": token}


@app.get("/api/admin/session")
def admin_session(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    return {"authenticated": True}


@app.post("/api/admin/logout")
def admin_logout(authorization: str | None = Header(default=None)) -> dict:
    token = require_admin(authorization)
    ADMIN_TOKENS.discard(token)
    return {"ok": True}


@app.get("/api/admin/users")
def list_users(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    ensure_storage()
    meta = load_meta()
    return {"users": [public_user(user) for user in meta.get("users", {}).values()]}


@app.post("/api/admin/users")
def create_user(payload: CreateUserRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    ensure_storage()
    meta = load_meta()
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if not payload.password:
        raise HTTPException(status_code=400, detail="Password is required")
    if any(user.get("username") == username for user in meta.get("users", {}).values()):
        raise HTTPException(status_code=400, detail="Username already exists")
    api_key = generate_api_key()
    user_id = uuid.uuid4().hex
    salt, password_hash = hash_password(payload.password)
    user = {
        "id": user_id,
        "username": username,
        "name": payload.name.strip() or username,
        "apiKey": api_key,
        "passwordSalt": salt,
        "passwordHash": password_hash,
        "credits": max(0, int(payload.credits)),
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    meta.setdefault("users", {})[user_id] = user
    if user["credits"]:
        add_credit_record(meta, user_id, user["credits"], user["credits"], "initial_credits")
    save_meta(meta)
    return {"user": public_user(user)}


@app.patch("/api/admin/users/{user_id}")
def update_user(user_id: str, payload: UpdateUserRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    meta = load_meta()
    user = meta.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.username is not None:
        username = payload.username.strip()
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")
        if any(other.get("username") == username and other.get("id") != user_id for other in meta.get("users", {}).values()):
            raise HTTPException(status_code=400, detail="Username already exists")
        user["username"] = username
    if payload.apiKey is not None:
        api_key = payload.apiKey.strip() or generate_api_key()
        if any(other.get("apiKey") == api_key and other.get("id") != user_id for other in meta.get("users", {}).values()):
            raise HTTPException(status_code=400, detail="API key already exists")
        user["apiKey"] = api_key
    if payload.password:
        salt, password_hash = hash_password(payload.password)
        user["passwordSalt"] = salt
        user["passwordHash"] = password_hash
    if payload.name is not None:
        user["name"] = payload.name.strip() or user["name"]
    user["updatedAt"] = utc_now()
    save_meta(meta)
    return {"user": public_user(user)}


@app.post("/api/admin/users/{user_id}/credits/adjust")
def adjust_user_credits(user_id: str, payload: AdjustCreditsRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    meta = load_meta()
    user = meta.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    next_credits = int(user.get("credits", 0)) + int(payload.amount)
    if next_credits < 0:
        raise HTTPException(status_code=400, detail="Credits cannot be negative")
    user["credits"] = next_credits
    user["updatedAt"] = utc_now()
    record = add_credit_record(meta, user_id, int(payload.amount), next_credits, payload.reason)
    save_meta(meta)
    return {"user": public_user(user), "record": record}


@app.post("/api/admin/users/{user_id}/credits/set")
def set_user_credits(user_id: str, payload: SetCreditsRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    meta = load_meta()
    user = meta.get("users", {}).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    current = int(user.get("credits", 0))
    next_credits = max(0, int(payload.credits))
    delta = next_credits - current
    user["credits"] = next_credits
    user["updatedAt"] = utc_now()
    record = add_credit_record(meta, user_id, delta, next_credits, payload.reason)
    save_meta(meta)
    return {"user": public_user(user), "record": record}


@app.get("/api/admin/credit-records")
def list_credit_records(userId: str | None = None, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    meta = load_meta()
    records = meta.get("creditRecords", [])
    if userId:
        records = [record for record in records if record.get("userId") == userId]
    return {"records": records}


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict:
    meta = load_meta()
    username = payload.username.strip()
    user = next((item for item in meta.get("users", {}).values() if item.get("username") == username), None)
    if not user or not verify_password(payload.password, user):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"user": public_user(user)}


@app.get("/api/users/me")
def get_me(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict:
    return {"user": public_user(find_user_by_key(x_api_key))}


@app.get("/api/users/me/credit-records")
def get_my_credit_records(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict:
    user = find_user_by_key(x_api_key)
    meta = load_meta()
    records = [record for record in meta.get("creditRecords", []) if record.get("userId") == user["id"]]
    return {"records": records}


@app.post("/avatar")
async def create_avatar(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> Response:
    """同步抠图接口：必须携带用户 API Key，每张成功扣1积分，失败自动退款。"""
    user = find_user_by_key(x_api_key)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")
    if int(user.get("credits", 0)) < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    meta = load_meta()
    user = meta["users"][user["id"]]
    user["credits"] = int(user.get("credits", 0)) - 1
    user["updatedAt"] = utc_now()
    add_credit_record(meta, user["id"], -1, user["credits"], "avatar_cutout_prep")
    save_meta(meta)

    try:
        image_bytes = await file.read()
        output = process_with_padding(image_bytes, get_processor())
    except Exception as exc:
        meta = load_meta()
        user = meta["users"].get(user["id"])
        if user:
            user["credits"] = int(user.get("credits", 0)) + 1
            user["updatedAt"] = utc_now()
            add_credit_record(meta, user["id"], 1, user["credits"], "avatar_cutout_refund")
            save_meta(meta)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    meta = load_meta()
    user = meta["users"].get(user["id"])
    if user:
        existing = next((r for r in meta.get("creditRecords", []) if r.get("reason") == "avatar_cutout_prep" and r.get("userId") == user["id"] and r.get("amount") == -1), None)
        if existing:
            existing["reason"] = "avatar_cutout_cost"
            save_meta(meta)

    return Response(content=output, media_type="image/png")


@app.post("/api/uploads/session")
def create_upload_session(payload: UploadSessionRequest) -> dict:
    ensure_storage()
    meta = load_meta()
    sessions = meta.setdefault("sessions", {})

    for upload_id, session in sessions.items():
        if session.get("fingerprint") == payload.fingerprint and session.get("status") != "completed" and (CHUNKS_DIR / upload_id).exists():
            session["updatedAt"] = utc_now()
            save_meta(meta)
            return {"uploadId": upload_id, "uploadedChunks": get_uploaded_chunks(upload_id)}

    upload_id = uuid.uuid4().hex
    sessions[upload_id] = {
        "uploadId": upload_id,
        "fingerprint": payload.fingerprint,
        "fileName": sanitize_name(payload.fileName),
        "fileSize": payload.fileSize,
        "fileType": payload.fileType,
        "relativePath": payload.relativePath,
        "totalChunks": payload.totalChunks,
        "status": "uploading",
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    (CHUNKS_DIR / upload_id).mkdir(parents=True, exist_ok=True)
    save_meta(meta)
    return {"uploadId": upload_id, "uploadedChunks": []}


@app.post("/api/uploads/chunk")
async def upload_chunk(
    uploadId: str = Form(...),
    chunkIndex: int = Form(...),
    fingerprint: str = Form(...),
    chunk: UploadFile = File(...),
) -> dict:
    ensure_storage()
    meta = load_meta()
    session = meta.get("sessions", {}).get(uploadId)
    if not session or session.get("fingerprint") != fingerprint:
        raise HTTPException(status_code=404, detail="Upload session not found")

    chunk_dir = CHUNKS_DIR / uploadId
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / f"{chunkIndex}.part"
    with chunk_path.open("wb") as output:
        shutil.copyfileobj(chunk.file, output)

    uploaded = get_uploaded_chunks(uploadId)
    total = max(int(session["totalChunks"]), 1)
    session["updatedAt"] = utc_now()
    save_meta(meta)
    return {
        "uploadId": uploadId,
        "chunkIndex": chunkIndex,
        "completed": len(uploaded) >= total,
        "progress": round(len(uploaded) / total * 100, 2),
    }


@app.post("/api/uploads/complete")
def complete_upload(payload: CompleteUploadRequest) -> dict:
    ensure_storage()
    meta = load_meta()
    session = meta.get("sessions", {}).get(payload.uploadId)
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")

    total = int(session["totalChunks"])
    uploaded = get_uploaded_chunks(payload.uploadId)
    if uploaded != list(range(total)):
        raise HTTPException(status_code=400, detail="Upload chunks are incomplete")

    file_id = uuid.uuid4().hex
    filename = sanitize_name(session["fileName"])
    target = FILES_DIR / f"{file_id}_{filename}"
    with target.open("wb") as output:
        for index in range(total):
            chunk_path = CHUNKS_DIR / payload.uploadId / f"{index}.part"
            with chunk_path.open("rb") as source:
                shutil.copyfileobj(source, output)

    item = {
        "id": file_id,
        "fileName": filename,
        "fileSize": target.stat().st_size,
        "fileType": session.get("fileType", ""),
        "relativePath": session.get("relativePath"),
        "path": str(target),
        "createdAt": utc_now(),
    }
    session["status"] = "completed"
    session["updatedAt"] = utc_now()
    meta.setdefault("files", []).insert(0, item)
    save_meta(meta)
    shutil.rmtree(CHUNKS_DIR / payload.uploadId, ignore_errors=True)
    return {"file": to_public_file(item)}


@app.post("/api/tasks/submit")
async def submit_task(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Form(default=None),
) -> dict:
    ensure_storage()
    user = find_user_by_key(x_api_key or api_key)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are supported")

    task_id = uuid.uuid4().hex
    filename = sanitize_name(file.filename or "image")
    source_path = TASKS_DIR / f"{task_id}_{filename}"
    with source_path.open("wb") as output:
        shutil.copyfileobj(file.file, output)

    head_count = count_heads(source_path)
    task = {
        "taskId": task_id,
        "userId": user["id"],
        "status": "queued",
        "progress": 0,
        "fileName": filename,
        "fileType": file.content_type,
        "headCount": head_count,
        "creditCost": 1,
        "sourcePath": str(source_path),
        "createdAt": utc_now(),
        "updatedAt": utc_now(),
    }
    meta = load_meta()
    meta.setdefault("tasks", {})[task_id] = task
    user = deduct_credit_for_task(meta, user["id"], task_id)
    save_meta(meta)
    background_tasks.add_task(run_image_task, task_id)
    return {
        "taskId": task_id,
        "statusUrl": f"/api/tasks/{task_id}",
        "imageUrl": f"/api/tasks/{task_id}/image",
        "headCount": head_count,
        "creditCost": 1,
        "credits": user["credits"],
    }


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    return public_task(find_task(task_id))


@app.get("/api/tasks/{task_id}/image")
def get_task_image(task_id: str) -> FileResponse:
    task = find_task(task_id)
    if task.get("status") != "completed":
        raise HTTPException(status_code=409, detail="Task is not completed")
    output_path = Path(task.get("outputPath", ""))
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Task image not found")
    stem = Path(task.get("fileName") or "image").stem
    return FileResponse(output_path, filename=f"{stem}_1500w_96dpi.png", media_type="image/png")


@app.get("/api/files")
def list_files() -> dict:
    ensure_storage()
    meta = load_meta()
    files = [to_public_file(item) for item in meta.get("files", []) if Path(item.get("path", "")).exists()]
    return {"files": files}


@app.get("/api/files/{file_id}")
def download_file(file_id: str) -> FileResponse:
    item = find_file(file_id)
    path = Path(item["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=item["fileName"], media_type=item.get("fileType") or "application/octet-stream")


@app.get("/api/files/{file_id}/png")
def download_png(file_id: str) -> StreamingResponse:
    item = find_file(file_id)
    path = Path(item["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        output = BytesIO()
        temp_path = TASKS_DIR / f"{file_id}_preview.png"
        save_png_from_path(path, temp_path)
        output.write(temp_path.read_bytes())
        temp_path.unlink(missing_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="File cannot be converted to PNG") from exc

    output.seek(0)
    stem = Path(item["fileName"]).stem or "image"
    headers = {"Content-Disposition": f'attachment; filename="{stem}_1500w_96dpi.png"'}
    return StreamingResponse(output, media_type="image/png", headers=headers)


@app.get("/api/files.zip")
def download_all_files() -> StreamingResponse:
    ensure_storage()
    meta = load_meta()
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in meta.get("files", []):
            path = Path(item.get("path", ""))
            if path.exists():
                archive.write(path, arcname=item.get("relativePath") or item["fileName"])
    output.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="facekeep-files.zip"'}
    return StreamingResponse(output, media_type="application/zip", headers=headers)


@app.delete("/api/files/{file_id}")
def delete_file(file_id: str) -> dict:
    ensure_storage()
    meta = load_meta()
    remaining = []
    deleted = False
    for item in meta.get("files", []):
        if item["id"] == file_id:
            Path(item.get("path", "")).unlink(missing_ok=True)
            deleted = True
        else:
            remaining.append(item)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    meta["files"] = remaining
    save_meta(meta)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=7333)
