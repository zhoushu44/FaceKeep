from functools import lru_cache
from io import BytesIO
from pathlib import Path
import copy
import hashlib
import hmac
import json
import logging
import stat
import os
import re
import secrets
import shutil
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, StrictInt
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
ADMIN_TOKENS: dict[str, dict] = {}
ADMIN_BOOTSTRAP_LOCK = threading.Lock()
STORAGE_DIR = BASE_DIR / "uploads"
CHUNKS_DIR = STORAGE_DIR / "chunks"
FILES_DIR = STORAGE_DIR / "files"
TASKS_DIR = STORAGE_DIR / "tasks"
BACKUPS_DIR = STORAGE_DIR / "backups"
META_FILE = STORAGE_DIR / "metadata.json"
BACKUP_LOCK = threading.RLock()
SCHEDULE_STOP = threading.Event()
SCHEDULE_THREAD: threading.Thread | None = None
LAST_SCHEDULED_MINUTE: str | None = None
TASK_DISPATCH_STOP = threading.Event()
TASK_DISPATCH_CONDITION = threading.Condition(BACKUP_LOCK)
TASK_DISPATCH_THREAD: threading.Thread | None = None
ACTIVE_TASK_IDS: set[str] = set()
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


class BootstrapRegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    confirmPassword: str


class AdjustCreditsRequest(BaseModel):
    amount: int
    reason: str = "manual_adjustment"


class SetCreditsRequest(BaseModel):
    credits: int
    reason: str = "set_credits"


class BackupConfigRequest(BaseModel):
    endpoint: str = ""
    region: str = ""
    bucket: str = ""
    keyPrefix: str = ""
    accessKeyId: str = ""
    secretAccessKey: str = ""
    forcePathStyle: bool = False
    scheduleEnabled: bool = False
    cronExpression: str = "0 2 * * *"
    retentionDays: int = 14
    maxBackups: int = 10


class RestoreBackupRequest(BaseModel):
    confirm: bool = False


class ImageApiSettingsRequest(BaseModel):
    endpointUrl: str
    apiKey: str
    maxTaskWorkers: StrictInt


@lru_cache(maxsize=1)
def get_processor():
    return get_cutout_processor()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def backup_defaults() -> dict:
    return {"endpoint": "", "region": "", "bucket": "", "keyPrefix": "", "accessKeyId": "", "secretAccessKey": "", "forcePathStyle": False, "scheduleEnabled": False, "cronExpression": "0 2 * * *", "retentionDays": 14, "maxBackups": 10}


def image_api_settings_defaults() -> dict:
    return {"endpointUrl": "", "apiKey": "", "maxTaskWorkers": 10, "updatedAt": None}


def environment_image_api_settings() -> dict:
    return {
        "endpointUrl": os.getenv("IMAGE_API_BASE_URL", "").strip().rstrip("/"),
        "apiKey": os.getenv("IMAGE_API_KEY", "").strip(),
    }


def current_max_task_workers(settings: dict | None) -> int:
    try:
        value = int((settings or {}).get("maxTaskWorkers", 10))
    except (TypeError, ValueError):
        return 10
    return value if 1 <= value <= 32 else 10


def public_image_api_settings(settings: dict) -> dict:
    return {
        "endpointUrl": settings.get("endpointUrl", ""),
        "hasApiKey": bool(settings.get("apiKey", "")),
        "maxTaskWorkers": current_max_task_workers(settings),
    }


def validate_image_api_settings(payload: ImageApiSettingsRequest, previous: dict) -> dict:
    endpoint_url = payload.endpointUrl.strip()
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=400, detail="图像 API 端点必须是无认证信息、查询参数或片段的 HTTP/HTTPS URL")
    normalized_endpoint = parsed._replace(params="", query="", fragment="").geturl().rstrip("/")
    api_key = payload.apiKey.strip()
    if not api_key:
        api_key = previous.get("apiKey", "")
    if not api_key or len(api_key) < 16 or len(api_key) > 512 or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in api_key):
        raise HTTPException(status_code=400, detail="图像 API Key 必须为 16-512 个字符且不得包含空白或控制字符")
    if isinstance(payload.maxTaskWorkers, bool) or not 1 <= payload.maxTaskWorkers <= 32:
        raise HTTPException(status_code=400, detail="全局任务并发必须为 1-32 的整数")
    return {"endpointUrl": normalized_endpoint, "apiKey": api_key, "maxTaskWorkers": payload.maxTaskWorkers, "updatedAt": utc_now()}


def ensure_storage() -> None:
    ensure_storage_dirs_only()
    if not META_FILE.exists():
        save_meta({"sessions": {}, "files": [], "tasks": {}, "users": {}, "admins": {}, "creditRecords": [], "backupConfig": backup_defaults(), "imageApiSettings": image_api_settings_defaults(), "backups": []})


def load_meta() -> dict:
    ensure_storage_dirs_only()
    if not META_FILE.exists():
        return {"sessions": {}, "files": [], "tasks": {}, "users": {}, "admins": {}, "creditRecords": [], "backupConfig": backup_defaults(), "imageApiSettings": image_api_settings_defaults(), "backups": []}
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    meta.setdefault("sessions", {})
    meta.setdefault("files", [])
    meta.setdefault("tasks", {})
    meta.setdefault("users", {})
    meta.setdefault("admins", {})
    meta.setdefault("creditRecords", [])
    config = meta.setdefault("backupConfig", backup_defaults())
    for key, value in backup_defaults().items():
        config.setdefault(key, value)
    image_api_settings = meta.setdefault("imageApiSettings", image_api_settings_defaults())
    for key, value in image_api_settings_defaults().items():
        image_api_settings.setdefault(key, value)
    meta.setdefault("backups", [])
    return meta


def save_meta(meta: dict) -> None:
    with BACKUP_LOCK:
        ensure_storage_dirs_only()
        temp_file = META_FILE.with_suffix(".json.tmp")
        temp_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(META_FILE)


def ensure_storage_dirs_only() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    FILES_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


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


def hash_admin_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt_bytes = bytes.fromhex(salt) if salt else secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes, 310_000)
    return salt_bytes.hex(), digest.hex()


def verify_admin_password(password: str, admin: dict) -> bool:
    salt = admin.get("passwordSalt")
    expected = admin.get("passwordHash")
    if not salt or not expected:
        return False
    _, digest = hash_admin_password(password, salt)
    return hmac.compare_digest(digest, expected)


def has_configured_admin() -> bool:
    return bool(ADMIN_USERNAME and ADMIN_PASSWORD)


def has_any_admin(meta: dict | None = None) -> bool:
    return has_configured_admin() or bool((meta or load_meta()).get("admins", {}))


def validate_bootstrap_registration(payload: BootstrapRegisterRequest) -> tuple[str, str, str]:
    username = payload.username.strip()
    email = payload.email.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="管理员账户名不能为空")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,31}", username):
        raise HTTPException(status_code=400, detail="管理员账户名应为 3-32 位字母、数字、点、下划线或连字符")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="请输入有效的邮箱地址")
    password = payload.password
    if len(password) < 8 or not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password) or not re.search(r"\d", password) or not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="密码至少 8 位，且须包含大写字母、小写字母、数字和特殊字符")
    if password != payload.confirmPassword:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    return username, email, password


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


def require_admin(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Administrator authentication required")
    token = authorization.removeprefix("Bearer ").strip()
    session = ADMIN_TOKENS.get(token)
    if not token or not session:
        raise HTTPException(status_code=401, detail="Invalid administrator token")
    return session


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
    with BACKUP_LOCK:
        meta = load_meta()
        task = meta.get("tasks", {}).get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task


def require_task_owner(task_id: str, api_key: str | None) -> tuple[dict, dict]:
    user = find_user_by_key(api_key)
    with BACKUP_LOCK:
        meta = load_meta()
        task = meta.get("tasks", {}).get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.get("userId") != user.get("id"):
            raise HTTPException(status_code=403, detail="Task access denied")
        return task, meta


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
    try:
        with BACKUP_LOCK:
            task = load_meta().get("tasks", {}).get(task_id)
            if not task or task.get("status") != "processing":
                return
            source_path = Path(task["sourcePath"])
        output_path = TASKS_DIR / f"{task_id}_1500w_96dpi.png"
        width, height = save_png_from_path(source_path, output_path, cutout=True)
        with BACKUP_LOCK:
            meta = load_meta()
            task = meta.get("tasks", {}).get(task_id)
            if task:
                task.update({"status": "completed", "progress": 100, "outputPath": str(output_path), "outputWidth": width, "outputHeight": height, "imageUrl": f"/api/tasks/{task_id}/image", "updatedAt": utc_now()})
                save_meta(meta)
    except Exception as exc:
        with BACKUP_LOCK:
            meta = load_meta()
            task = meta.get("tasks", {}).get(task_id)
            if task:
                task.update({"status": "failed", "progress": 100, "error": str(exc), "updatedAt": utc_now()})
                refund_failed_task(meta, task)
                save_meta(meta)
    finally:
        with TASK_DISPATCH_CONDITION:
            ACTIVE_TASK_IDS.discard(task_id)
            TASK_DISPATCH_CONDITION.notify_all()


def queued_position(task: dict, tasks: dict[str, dict]) -> int | None:
    if task.get("status") != "queued":
        return None
    created_at = task.get("createdAt", "")
    task_id = task.get("taskId", "")
    return sum(1 for other in tasks.values() if other.get("status") == "queued" and (other.get("createdAt", ""), other.get("taskId", "")) < (created_at, task_id))


def public_task(task: dict, tasks: dict[str, dict] | None = None) -> dict:
    return {
        "taskId": task["taskId"],
        "status": task["status"],
        "progress": task.get("progress", 0),
        "queuePosition": queued_position(task, tasks or {}),
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


def configured_max_task_workers() -> int:
    try:
        return current_max_task_workers(load_meta().get("imageApiSettings"))
    except Exception:
        return 10


def select_dispatchable_tasks(tasks: dict[str, dict], active_ids: set[str]) -> list[dict]:
    available_slots = max(configured_max_task_workers() - len(active_ids), 0)
    queued = sorted(
        (task for task in tasks.values() if task.get("status") == "queued" and task.get("taskId") not in active_ids),
        key=lambda task: (task.get("createdAt", ""), task.get("taskId", "")),
    )
    return queued[:available_slots]


def dispatch_tasks() -> None:
    while not TASK_DISPATCH_STOP.is_set():
        workers: list[threading.Thread] = []
        with TASK_DISPATCH_CONDITION:
            meta = load_meta()
            tasks = meta.get("tasks", {})
            for task in select_dispatchable_tasks(tasks, ACTIVE_TASK_IDS):
                task["status"] = "processing"
                task["progress"] = 30
                task["updatedAt"] = utc_now()
                ACTIVE_TASK_IDS.add(task["taskId"])
                workers.append(threading.Thread(target=run_image_task, args=(task["taskId"],), daemon=True))
            if workers:
                save_meta(meta)
            else:
                TASK_DISPATCH_CONDITION.wait(timeout=1)
        for worker in workers:
            worker.start()


def restore_task_queue() -> None:
    with TASK_DISPATCH_CONDITION:
        meta = load_meta()
        changed = False
        for task in meta.get("tasks", {}).values():
            if task.get("status") == "processing":
                task.update({"status": "queued", "progress": 0, "updatedAt": utc_now()})
                changed = True
        ACTIVE_TASK_IDS.clear()
        if changed:
            save_meta(meta)
        TASK_DISPATCH_CONDITION.notify_all()


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


@app.get("/api/admin/bootstrap/status")
def admin_bootstrap_status() -> dict:
    return {"registrationAllowed": not has_any_admin()}


@app.post("/api/admin/bootstrap/register")
def admin_bootstrap_register(payload: BootstrapRegisterRequest) -> dict:
    username, email, password = validate_bootstrap_registration(payload)
    with ADMIN_BOOTSTRAP_LOCK:
        meta = load_meta()
        if has_any_admin(meta):
            raise HTTPException(status_code=403, detail="初始管理员已创建，不能注册")
        now = utc_now()
        salt, password_hash = hash_admin_password(password)
        admin = {
            "id": uuid.uuid4().hex,
            "username": username,
            "email": email,
            "passwordSalt": salt,
            "passwordHash": password_hash,
            "role": "super_admin",
            "permissions": ["*"],
            "createdAt": now,
            "updatedAt": now,
            "initialConfiguration": {"source": "bootstrap", "registrationVersion": 1},
        }
        meta.setdefault("admins", {})[admin["id"]] = admin
        save_meta(meta)
    token = secrets.token_urlsafe(48)
    ADMIN_TOKENS[token] = {"id": admin["id"], "username": admin["username"], "role": admin["role"], "permissions": admin["permissions"]}
    return {"token": token}


@app.post("/api/admin/login")
def admin_login(payload: LoginRequest) -> dict:
    username = payload.username.strip()
    session: dict | None = None
    if has_configured_admin() and hmac.compare_digest(username, ADMIN_USERNAME) and hmac.compare_digest(payload.password, ADMIN_PASSWORD):
        session = {"id": "environment", "username": ADMIN_USERNAME, "role": "super_admin", "permissions": ["*"]}
    else:
        meta = load_meta()
        admin = next((item for item in meta.get("admins", {}).values() if item.get("username") == username), None)
        if admin and verify_admin_password(payload.password, admin):
            session = {"id": admin["id"], "username": admin["username"], "role": admin.get("role", "super_admin"), "permissions": admin.get("permissions", ["*"])}
    if not session:
        raise HTTPException(status_code=401, detail="Invalid administrator credentials")
    token = secrets.token_urlsafe(48)
    ADMIN_TOKENS[token] = session
    return {"token": token}


@app.get("/api/admin/session")
def admin_session(authorization: str | None = Header(default=None)) -> dict:
    session = require_admin(authorization)
    return {"authenticated": True, "admin": session}


@app.post("/api/admin/logout")
def admin_logout(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    token = authorization.removeprefix("Bearer ").strip()
    ADMIN_TOKENS.pop(token, None)
    return {"ok": True}


@app.get("/api/admin/image-api-settings")
def get_image_api_settings(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    settings = load_meta()["imageApiSettings"]
    effective_settings = settings if settings.get("endpointUrl") and settings.get("apiKey") else {**environment_image_api_settings(), "maxTaskWorkers": current_max_task_workers(settings)}
    return {"settings": public_image_api_settings(effective_settings)}


@app.put("/api/admin/image-api-settings")
def save_image_api_settings(payload: ImageApiSettingsRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    with BACKUP_LOCK:
        meta = load_meta()
        previous = meta["imageApiSettings"]
        if not previous.get("apiKey"):
            previous = {**environment_image_api_settings(), **{key: value for key, value in previous.items() if value}}
        settings = validate_image_api_settings(payload, previous)
        meta["imageApiSettings"] = settings
        save_meta(meta)
    get_processor.cache_clear()
    with TASK_DISPATCH_CONDITION:
        TASK_DISPATCH_CONDITION.notify_all()
    return {"settings": public_image_api_settings(settings)}


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

    task = {"taskId": task_id, "userId": user["id"], "status": "queued", "progress": 0, "fileName": filename, "fileType": file.content_type, "headCount": 1, "creditCost": 1, "sourcePath": str(source_path), "createdAt": utc_now(), "updatedAt": utc_now()}
    with TASK_DISPATCH_CONDITION:
        meta = load_meta()
        meta.setdefault("tasks", {})[task_id] = task
        user = deduct_credit_for_task(meta, user["id"], task_id)
        save_meta(meta)
        TASK_DISPATCH_CONDITION.notify_all()
        response = public_task(task, meta["tasks"])
    response.update({"statusUrl": f"/api/tasks/{task_id}", "imageUrl": f"/api/tasks/{task_id}/image", "credits": user["credits"]})
    return response


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> dict:
    task, meta = require_task_owner(task_id, x_api_key)
    return public_task(task, meta["tasks"])


@app.get("/api/tasks/{task_id}/image")
def get_task_image(task_id: str, x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> FileResponse:
    task, _ = require_task_owner(task_id, x_api_key)
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


def public_backup_config(config: dict) -> dict:
    return {key: value for key, value in config.items() if key != "secretAccessKey"} | {"hasSecretAccessKey": bool(config.get("secretAccessKey"))}


def public_backup_record(record: dict) -> dict:
    allowed = ("id", "status", "fileName", "size", "createdAt", "expiresAt", "trigger", "storage", "warning", "cleanupWarning")
    public = {key: record[key] for key in allowed if key in record}
    public["restoreAvailable"] = bool(record.get("localPath") and Path(record["localPath"]).is_file())
    return public


def has_s3_config(config: dict) -> bool:
    return all(str(config.get(key, "")).strip() for key in ("endpoint", "region", "bucket", "accessKeyId", "secretAccessKey"))


def s3_location(config: dict, key: str) -> dict:
    fields = ("endpoint", "region", "bucket", "keyPrefix", "accessKeyId", "forcePathStyle")
    return {field: config.get(field, "") for field in fields} | {"key": key}


def record_s3_location(record: dict, current_config: dict) -> dict | None:
    location = record.get("s3Location")
    if not location and record.get("s3Key"):
        location = s3_location(current_config, record["s3Key"])
    if not location or not location.get("key"):
        return None
    connected = dict(location)
    connected["secretAccessKey"] = current_config.get("secretAccessKey", "")
    return connected if has_s3_config(connected) else None


def validate_cron(expression: str) -> list[str]:
    ranges = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
    parts = expression.split()
    if len(parts) != 5:
        raise HTTPException(status_code=400, detail="Cron 表达式必须为 5 段")
    for field, (minimum, maximum) in zip(parts, ranges):
        for item in field.split(","):
            step = item[2:] if item.startswith("*/") else None
            if item == "*":
                continue
            if step is not None and step.isdigit() and 0 < int(step) <= maximum:
                continue
            if item.isdigit() and minimum <= int(item) <= maximum:
                continue
            raise HTTPException(status_code=400, detail="Cron 字段超出范围或格式不支持")
    return parts


def s3_client(config: dict):
    import boto3
    return boto3.client("s3", endpoint_url=config["endpoint"], region_name=config["region"], aws_access_key_id=config["accessKeyId"], aws_secret_access_key=config["secretAccessKey"], config=__import__("botocore.config", fromlist=["Config"]).Config(s3={"addressing_style": "path" if config.get("forcePathStyle") else "auto"}))


def backup_expiry(config: dict) -> str | None:
    days = int(config.get("retentionDays", 0))
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat() if days else None


def delete_record_storage(record: dict, current_config: dict) -> bool:
    local_path = Path(record.get("localPath", ""))
    if local_path.is_relative_to(BACKUPS_DIR):
        local_path.unlink(missing_ok=True)
    has_remote = bool(record.get("s3Location") or record.get("s3Key"))
    location = record_s3_location(record, current_config)
    if has_remote and not location:
        record["cleanupWarning"] = "缺少对应 S3 凭据或配置，将保留记录以便重试"
        return False
    if not location:
        return True
    try:
        s3_client(location).delete_object(Bucket=location["bucket"], Key=location["key"])
        return True
    except Exception:
        record["cleanupWarning"] = "远端对象删除失败，将保留记录以便重试"
        return False


def cleanup_backups(meta: dict) -> None:
    now = datetime.now(timezone.utc)
    records = meta.get("backups", [])
    maximum = int(meta["backupConfig"].get("maxBackups", 0))
    retained: list[dict] = []
    candidates: list[dict] = []
    for record in records:
        expiry = record.get("expiresAt")
        if expiry and datetime.fromisoformat(expiry) <= now:
            candidates.append(record)
        else:
            retained.append(record)
    if maximum and len(retained) > maximum:
        candidates.extend(retained[maximum:])
        retained = retained[:maximum]
    for record in candidates:
        if not delete_record_storage(record, meta["backupConfig"]):
            retained.append(record)
    meta["backups"] = retained


def sanitized_backup_metadata(meta: dict) -> bytes:
    backup_meta = copy.deepcopy(meta)
    backup_meta.get("backupConfig", {}).pop("secretAccessKey", None)
    backup_meta.get("imageApiSettings", {}).pop("apiKey", None)
    return json.dumps(backup_meta, ensure_ascii=False, indent=2).encode("utf-8")


def create_backup(trigger: str = "manual") -> dict:
    with BACKUP_LOCK:
        ensure_storage()
        meta = load_meta()
        config = meta["backupConfig"]
        backup_id = uuid.uuid4().hex
        filename = f"facekeep-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{backup_id[:8]}.zip"
        local_path = BACKUPS_DIR / filename
        record = {"id": backup_id, "status": "failed", "fileName": filename, "size": 0, "createdAt": utc_now(), "expiresAt": backup_expiry(config), "trigger": trigger, "storage": "local", "localPath": str(local_path)}
        try:
            with zipfile.ZipFile(local_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("uploads/metadata.json", sanitized_backup_metadata(meta))
                for source in (FILES_DIR, TASKS_DIR):
                    for path in source.rglob("*"):
                        if path.is_file():
                            archive.write(path, path.relative_to(BASE_DIR).as_posix())
            record["size"] = local_path.stat().st_size
            if has_s3_config(config):
                key = f"{config.get('keyPrefix', '').strip('/')}/{filename}".strip("/")
                try:
                    s3_client(config).upload_file(str(local_path), config["bucket"], key)
                    record.update({"storage": "s3", "s3Key": key, "s3Location": s3_location(config, key)})
                except Exception:
                    record["warning"] = "S3 上传失败，已保留本地备份"
            record["status"] = "completed"
        except Exception:
            local_path.unlink(missing_ok=True)
            record["error"] = "备份创建失败"
        meta["backups"].insert(0, record)
        cleanup_backups(meta)
        save_meta(meta)
        return record


def cron_field_matches(field: str, value: int) -> bool:
    for item in field.split(","):
        if item == "*" or (item.startswith("*/") and item[2:].isdigit() and int(item[2:]) > 0 and value % int(item[2:]) == 0) or (item.isdigit() and value == int(item)):
            return True
    return False


def schedule_tick() -> None:
    global LAST_SCHEDULED_MINUTE
    with BACKUP_LOCK:
        meta = load_meta()
        config = meta["backupConfig"]
        if not config.get("scheduleEnabled"):
            return
        parts = validate_cron(config.get("cronExpression", ""))
        now = datetime.now(timezone.utc)
        minute_key = now.strftime("%Y%m%d%H%M")
        values = (now.minute, now.hour, now.day, now.month, (now.weekday() + 1) % 7)
        if LAST_SCHEDULED_MINUTE != minute_key and all(cron_field_matches(field, value) for field, value in zip(parts, values)):
            LAST_SCHEDULED_MINUTE = minute_key
            threading.Thread(target=create_backup, args=("scheduled",), daemon=True).start()


def schedule_loop() -> None:
    while not SCHEDULE_STOP.wait(60):
        try:
            schedule_tick()
        except Exception:
            logging.exception("备份定时任务执行失败")


@app.on_event("startup")
def start_backup_scheduler() -> None:
    global SCHEDULE_THREAD, TASK_DISPATCH_THREAD
    ensure_storage()
    restore_task_queue()
    TASK_DISPATCH_STOP.clear()
    if not TASK_DISPATCH_THREAD or not TASK_DISPATCH_THREAD.is_alive():
        TASK_DISPATCH_THREAD = threading.Thread(target=dispatch_tasks, daemon=True)
        TASK_DISPATCH_THREAD.start()
    try:
        schedule_tick()
    except Exception:
        logging.exception("备份定时任务初始化失败")
    if not SCHEDULE_THREAD or not SCHEDULE_THREAD.is_alive():
        SCHEDULE_THREAD = threading.Thread(target=schedule_loop, daemon=True)
        SCHEDULE_THREAD.start()


@app.on_event("shutdown")
def stop_task_dispatcher() -> None:
    TASK_DISPATCH_STOP.set()
    with TASK_DISPATCH_CONDITION:
        TASK_DISPATCH_CONDITION.notify_all()
    if TASK_DISPATCH_THREAD and TASK_DISPATCH_THREAD.is_alive():
        TASK_DISPATCH_THREAD.join(timeout=5)


@app.get("/api/admin/backups/config")
def get_backup_config(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    return {"config": public_backup_config(load_meta()["backupConfig"])}


@app.put("/api/admin/backups/config")
def save_backup_config(payload: BackupConfigRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    if payload.retentionDays < 0 or payload.maxBackups < 0:
        raise HTTPException(status_code=400, detail="过期天数和最大保留数量必须为非负整数")
    validate_cron(payload.cronExpression)
    with BACKUP_LOCK:
        meta = load_meta()
        previous = meta["backupConfig"]
        config = payload.model_dump()
        if not config["secretAccessKey"]:
            config["secretAccessKey"] = previous.get("secretAccessKey", "")
        if payload.scheduleEnabled and not has_s3_config(config):
            raise HTTPException(status_code=400, detail="启用定时备份需要完整 S3 配置")
        meta["backupConfig"] = config
        cleanup_backups(meta)
        save_meta(meta)
    return {"config": public_backup_config(config)}


@app.post("/api/admin/backups/test-connection")
def test_backup_connection(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    with BACKUP_LOCK:
        config = load_meta()["backupConfig"]
    if not has_s3_config(config):
        raise HTTPException(status_code=400, detail="请先填写完整的 S3 配置")
    try:
        s3_client(config).head_bucket(Bucket=config["bucket"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"S3 连接失败：{exc}") from exc
    return {"ok": True, "message": "S3 连接成功"}


@app.get("/api/admin/backups")
def list_backups(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    with BACKUP_LOCK:
        meta = load_meta()
        cleanup_backups(meta)
        save_meta(meta)
        return {"backups": [public_backup_record(record) for record in meta["backups"]]}


@app.post("/api/admin/backups")
def create_manual_backup(authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    record = create_backup("manual")
    if record["status"] != "completed":
        raise HTTPException(status_code=500, detail="备份创建失败")
    return {"backup": public_backup_record(record)}


def get_backup_record(backup_id: str) -> tuple[dict, dict]:
    meta = load_meta()
    record = next((item for item in meta["backups"] if item["id"] == backup_id), None)
    if not record:
        raise HTTPException(status_code=404, detail="备份记录不存在")
    return meta, record


@app.get("/api/admin/backups/{backup_id}/download")
def download_backup(backup_id: str, authorization: str | None = Header(default=None)):
    require_admin(authorization)
    meta, record = get_backup_record(backup_id)
    path = Path(record.get("localPath", ""))
    if path.exists():
        return FileResponse(path, media_type="application/zip", filename=record["fileName"])
    location = record_s3_location(record, meta["backupConfig"])
    if location:
        try:
            body = s3_client(location).get_object(Bucket=location["bucket"], Key=location["key"])["Body"]
            return StreamingResponse(body.iter_chunks(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{record["fileName"]}"'})
        except Exception:
            raise HTTPException(status_code=404, detail="无法读取远端备份")
    raise HTTPException(status_code=404, detail="备份文件不可用")


def validate_restore_archive(archive: zipfile.ZipFile) -> dict:
    infos = archive.infolist()
    if not infos or len(infos) > 5000:
        raise HTTPException(status_code=400, detail="备份条目数量不合法")
    total_size = 0
    names: set[str] = set()
    for info in infos:
        name = info.filename
        mode = info.external_attr >> 16
        valid = name == "uploads/metadata.json" or name.startswith("uploads/files/") or name.startswith("uploads/tasks/")
        unsafe_path = not name or "\\" in name or name.startswith("/") or ".." in Path(name).parts
        non_regular = stat.S_IFMT(mode) not in (0, stat.S_IFREG)
        compressed_ratio = info.file_size / max(info.compress_size, 1)
        if name in names or info.is_dir() or stat.S_ISLNK(mode) or non_regular or not valid or unsafe_path or info.file_size > 512 * 1024 * 1024 or compressed_ratio > 100:
            raise HTTPException(status_code=400, detail="备份包含不安全或不支持的文件")
        names.add(name)
        total_size += info.file_size
        if total_size > 2 * 1024 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="备份解压后过大")
    if "uploads/metadata.json" not in names:
        raise HTTPException(status_code=400, detail="备份元数据无效")
    try:
        metadata = json.loads(archive.read("uploads/metadata.json"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="备份元数据无效") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="备份元数据无效")
    return metadata


@app.post("/api/admin/backups/{backup_id}/restore")
def restore_backup(backup_id: str, payload: RestoreBackupRequest, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="恢复操作必须确认")
    with BACKUP_LOCK:
        _, record = get_backup_record(backup_id)
        path = Path(record.get("localPath", ""))
        if not path.is_file() or not path.is_relative_to(BACKUPS_DIR):
            raise HTTPException(status_code=400, detail="仅支持恢复本地可用备份")
        staging = STORAGE_DIR / f".restore-{uuid.uuid4().hex}"
        rollback = STORAGE_DIR / f".restore-rollback-{uuid.uuid4().hex}"
        try:
            with zipfile.ZipFile(path) as archive:
                restored = validate_restore_archive(archive)
                for info in archive.infolist():
                    target = staging / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, target.open("xb") as destination:
                        shutil.copyfileobj(source, destination)
            staged_uploads = staging / "uploads"
            current_meta = load_meta()
            restored["backupConfig"] = current_meta["backupConfig"]
            restored["backups"] = current_meta["backups"]
            restored["imageApiSettings"] = current_meta["imageApiSettings"]
            rollback.mkdir()
            for source in (FILES_DIR, TASKS_DIR, META_FILE):
                if source.exists():
                    shutil.move(str(source), str(rollback / source.name))
            try:
                for name in ("files", "tasks"):
                    staged = staged_uploads / name
                    destination = STORAGE_DIR / name
                    if staged.exists():
                        shutil.move(str(staged), str(destination))
                    else:
                        destination.mkdir()
                save_meta(restored)
            except Exception:
                shutil.rmtree(FILES_DIR, ignore_errors=True)
                shutil.rmtree(TASKS_DIR, ignore_errors=True)
                META_FILE.unlink(missing_ok=True)
                for name in ("files", "tasks", "metadata.json"):
                    source = rollback / name
                    if source.exists():
                        shutil.move(str(source), str(STORAGE_DIR / name))
                raise
        except HTTPException:
            raise
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
            raise HTTPException(status_code=400, detail="备份文件无效或恢复失败")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(rollback, ignore_errors=True)
    return {"ok": True, "message": "备份恢复成功"}


@app.delete("/api/admin/backups/{backup_id}")
def delete_backup(backup_id: str, authorization: str | None = Header(default=None)) -> dict:
    require_admin(authorization)
    with BACKUP_LOCK:
        meta, record = get_backup_record(backup_id)
        deleted = delete_record_storage(record, meta["backupConfig"])
        if deleted:
            meta["backups"] = [item for item in meta["backups"] if item["id"] != backup_id]
        save_meta(meta)
    return {"ok": deleted, "warning": record.get("cleanupWarning")}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=7333)
