import type { CreditRecord, ServerFile, UserAccount } from "@/types";

const API_BASE = "";

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

export async function deleteServerFile(id: string): Promise<void> {
  const response = await fetch(`${API_BASE}/api/files/${id}`, { method: "DELETE" });
  if (!response.ok) throw new Error("删除失败");
}

export async function fetchUsers(): Promise<UserAccount[]> {
  const response = await fetch(`${API_BASE}/api/admin/users`);
  if (!response.ok) throw new Error("用户列表加载失败");
  const data = await response.json();
  return data.users;
}

export async function createUser(payload: { username: string; name: string; password: string; credits: number }): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/api/admin/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("创建用户失败");
  const data = await response.json();
  return data.user;
}

export async function updateUser(id: string, payload: { username?: string; name?: string; apiKey?: string; password?: string }): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/api/admin/users/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error("更新用户失败");
  const data = await response.json();
  return data.user;
}

export async function adjustCredits(id: string, amount: number, reason: string): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/api/admin/users/${id}/credits/adjust`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount, reason }),
  });
  if (!response.ok) throw new Error("调整积分失败");
  const data = await response.json();
  return data.user;
}

export async function setCredits(id: string, credits: number, reason: string): Promise<UserAccount> {
  const response = await fetch(`${API_BASE}/api/admin/users/${id}/credits/set`, {
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
  const response = await fetch(`${API_BASE}/api/admin/credit-records${query}`);
  if (!response.ok) throw new Error("积分记录加载失败");
  const data = await response.json();
  return data.records;
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
