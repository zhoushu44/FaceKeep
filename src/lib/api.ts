import type { BackupConfig, BackupRecord, CreditRecord, ImageApiSettings, ServerFile, UserAccount } from "@/types";

const API_BASE = "";
export const USER_SESSION_KEY = "facekeep_user_api_key";
export const ADMIN_SESSION_KEY = "facekeep_admin_token";

async function adminFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem(ADMIN_SESSION_KEY) || "";
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (response.status === 401) {
    localStorage.removeItem(ADMIN_SESSION_KEY);
    window.location.assign("/admin/login");
  }
  return response;
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const data = await response.json().catch(() => null);
  return new Error(data?.detail || fallback);
}

export async function adminLogin(username: string, password: string): Promise<string> {
  const response = await fetch(`${API_BASE}/api/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw await responseError(response, "管理员用户名或密码错误");
  const data = await response.json();
  return data.token;
}

export async function fetchAdminBootstrapStatus(): Promise<boolean> {
  const response = await fetch(`${API_BASE}/api/admin/bootstrap/status`);
  if (!response.ok) throw await responseError(response, "初始管理员状态加载失败");
  const data = await response.json();
  return data.registrationAllowed === true;
}

export async function registerInitialAdmin(payload: { username: string; email: string; password: string; confirmPassword: string }): Promise<string> {
  const response = await fetch(`${API_BASE}/api/admin/bootstrap/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw await responseError(response, "初始管理员注册失败");
  const data = await response.json();
  return data.token;
}

export async function verifyAdminSession(): Promise<void> {
  const response = await adminFetch("/api/admin/session");
  if (!response.ok) throw new Error("管理员登录状态已失效");
}

export async function adminLogout(): Promise<void> {
  await adminFetch("/api/admin/logout", { method: "POST" });
  localStorage.removeItem(ADMIN_SESSION_KEY);
}

export async function fetchFiles(): Promise<ServerFile[]> {
  const response = await fetch(`${API_BASE}/api/files`);
  if (!response.ok) throw new Error("文件列表加载失败");
  const data = await response.json();
  return data.files;
}

export async function createSession(payload: {
  fileName: string;
  fileSize: number;
  fileType: string;
  relativePath?: string;
  fingerprint: string;
  totalChunks: number;
}): Promise<{ uploadId: string; uploadedChunks: number[] }> {
  const response = await fetch(`${API_BASE}/api/uploads/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("上传会话创建失败");
  return response.json();
}

export async function uploadChunk(payload: {
  uploadId: string;
  chunkIndex: number;
  fingerprint: string;
  chunk: Blob;
}): Promise<{ progress: number }> {
  const form = new FormData();
  form.append("uploadId", payload.uploadId);
  form.append("chunkIndex", String(payload.chunkIndex));
  form.append("fingerprint", payload.fingerprint);
  form.append("chunk", payload.chunk);
  const response = await fetch(`${API_BASE}/api/uploads/chunk`, { method: "POST", body: form });
  if (!response.ok) throw new Error("分片上传失败");
  return response.json();
}

export async function completeUpload(uploadId: string): Promise<ServerFile> {
  const response = await fetch(`${API_BASE}/api/uploads/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uploadId }),
  });
  if (!response.ok) throw new Error("文件合并失败");
  const data = await response.json();
  return data.file;
}

export type ImageTask = {
  taskId: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  queuePosition?: number | null;
  imageUrl?: string;
  error?: string;
};

export async function submitImageTask(file: File, apiKey: string): Promise<ImageTask> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/api/tasks/submit`, {
    method: "POST",
    headers: { "X-API-Key": apiKey },
    body: form,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail || "任务提交失败");
  return data;
}

export async function fetchImageTask(taskId: string, apiKey: string): Promise<ImageTask> {
  const response = await fetch(`${API_BASE}/api/tasks/${taskId}`, { headers: { "X-API-Key": apiKey } });
  if (!response.ok) throw new Error("任务状态获取失败");
  return response.json();
}

export async function fetchTaskImage(taskId: string, apiKey: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}/api/tasks/${taskId}/image`, { headers: { "X-API-Key": apiKey } });
  if (!response.ok) throw new Error("结果图片加载失败");
  return response.blob();
}

export async function deleteServerFile(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/files/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("删除失败");
}

export async function fetchUsers(): Promise<UserAccount[]> {
  const response = await adminFetch("/api/admin/users");
  if (!response.ok) throw new Error("用户列表加载失败");
  const data = await response.json();
  return data.users;
}

export async function createUser(payload: { username: string; name: string; password: string; credits: number }): Promise<UserAccount> {
  const response = await adminFetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("创建用户失败");
  const data = await response.json();
  return data.user;
}

export async function updateUser(id: string, payload: { username?: string; name?: string; apiKey?: string; password?: string }): Promise<UserAccount> {
  const response = await adminFetch(`/api/admin/users/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("更新用户失败");
  const data = await response.json();
  return data.user;
}

export async function adjustCredits(id: string, amount: number, reason: string): Promise<UserAccount> {
  const response = await adminFetch(`/api/admin/users/${id}/credits/adjust`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount, reason }),
  });
  if (!response.ok) throw new Error("调整积分失败");
  const data = await response.json();
  return data.user;
}

export async function setCredits(id: string, credits: number, reason: string): Promise<UserAccount> {
  const response = await adminFetch(`/api/admin/users/${id}/credits/set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ credits, reason }),
  });
  if (!response.ok) throw new Error("设置积分失败");
  const data = await response.json();
  return data.user;
}

export async function fetchCreditRecords(userId?: string): Promise<CreditRecord[]> {
  const query = userId ? `?userId=${encodeURIComponent(userId)}` : "";
  const response = await adminFetch(`/api/admin/credit-records${query}`);
  if (!response.ok) throw new Error("积分记录加载失败");
  const data = await response.json();
  return data.records;
}

export async function fetchImageApiSettings(): Promise<ImageApiSettings> {
  const response = await adminFetch("/api/admin/image-api-settings");
  if (!response.ok) throw await responseError(response, "图像 API 设置加载失败");
  return (await response.json()).settings;
}

export async function saveImageApiSettings(payload: { endpointUrl: string; apiKey: string; maxTaskWorkers: number }): Promise<ImageApiSettings> {
  const response = await adminFetch("/api/admin/image-api-settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  if (!response.ok) throw await responseError(response, "图像 API 设置保存失败");
  return (await response.json()).settings;
}

export async function fetchBackupConfig(): Promise<BackupConfig> {
  const response = await adminFetch("/api/admin/backups/config");
  if (!response.ok) throw await responseError(response, "备份配置加载失败");
  return (await response.json()).config;
}

export async function saveBackupConfig(config: BackupConfig): Promise<BackupConfig> {
  const response = await adminFetch("/api/admin/backups/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
  if (!response.ok) throw await responseError(response, "备份配置保存失败");
  return (await response.json()).config;
}

export async function testBackupConnection(): Promise<string> {
  const response = await adminFetch("/api/admin/backups/test-connection", { method: "POST" });
  if (!response.ok) throw await responseError(response, "S3 连接测试失败");
  return (await response.json()).message;
}

export async function fetchBackups(): Promise<BackupRecord[]> {
  const response = await adminFetch("/api/admin/backups");
  if (!response.ok) throw await responseError(response, "备份记录加载失败");
  return (await response.json()).backups;
}

export async function createBackup(): Promise<BackupRecord> {
  const response = await adminFetch("/api/admin/backups", { method: "POST" });
  if (!response.ok) throw await responseError(response, "备份创建失败");
  return (await response.json()).backup;
}

export async function downloadBackup(id: string): Promise<Blob> {
  const response = await adminFetch(`/api/admin/backups/${id}/download`);
  if (!response.ok) throw await responseError(response, "备份下载失败");
  return response.blob();
}

export async function restoreBackup(id: string): Promise<string> {
  const response = await adminFetch(`/api/admin/backups/${id}/restore`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) });
  if (!response.ok) throw await responseError(response, "备份恢复失败");
  return (await response.json()).message;
}

export async function deleteBackup(id: string): Promise<string | undefined> {
  const response = await adminFetch(`/api/admin/backups/${id}`, { method: "DELETE" });
  if (!response.ok) throw await responseError(response, "备份删除失败");
  return (await response.json()).warning;
}

export async function login(username: string, password: string): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw new Error("用户名或密码错误");
  const data = await response.json();
  return data.user;
}

export async function fetchMe(apiKey: string): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/api/users/me`, { headers: { "X-API-Key": apiKey } });
  if (!response.ok) throw new Error("登录状态已失效");
  const data = await response.json();
  return data.user;
}

export async function fetchMyCreditRecords(apiKey: string): Promise<CreditRecord[]> {
  const response = await fetch(`${API_BASE}/api/users/me/credit-records`, { headers: { "X-API-Key": apiKey } });
  if (!response.ok) throw new Error("积分记录加载失败");
  const data = await response.json();
  return data.records;
}

export function apiUrl(path: string): string {
  return path;
}
