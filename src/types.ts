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

export type BackupConfig = {
  endpoint: string;
  region: string;
  bucket: string;
  keyPrefix: string;
  accessKeyId: string;
  secretAccessKey?: string;
  hasSecretAccessKey?: boolean;
  forcePathStyle: boolean;
  scheduleEnabled: boolean;
  cronExpression: string;
  retentionDays: number;
  maxBackups: number;
};

export type ImageApiSettings = {
  endpointUrl: string;
  hasApiKey: boolean;
  maxTaskWorkers: number;
};

export type BackupRecord = {
  id: string;
  status: "completed" | "failed";
  fileName: string;
  size: number;
  createdAt: string;
  expiresAt?: string;
  trigger: string;
  storage: "local" | "s3";
  warning?: string;
  cleanupWarning?: string;
  restoreAvailable: boolean;
};
