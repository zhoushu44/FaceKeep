export type UploadStatus = "ready" | "uploading" | "done" | "cutting" | "cutout" | "error";

export type ManagedFile = {
  id: string;
  file: File;
  previewUrl: string;
  relativePath?: string;
  fingerprint: string;
  progress: number;
  status: UploadStatus;
  serverId?: string;
  cutoutUrl?: string;
  taskId?: string;
  error?: string;
};

export type ServerFile = {
  id: string;
  fileName: string;
  fileSize: number;
  fileType: string;
  relativePath?: string;
  url: string;
  pngUrl: string;
  createdAt: string;
};

export type UserAccount = {
  id: string;
  username: string;
  name: string;
  apiKey: string;
  credits: number;
  createdAt: string;
  updatedAt: string;
};

export type CreditRecord = {
  id: string;
  userId: string;
  amount: number;
  balance: number;
  reason: string;
  taskId?: string;
  createdAt: string;
};
