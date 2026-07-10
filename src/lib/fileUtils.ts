import type { ManagedFile } from "@/types";

export const CHUNK_SIZE = 1024 * 512;

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function imageOnly(files: File[]): File[] {
  return files.filter((file) => file.type.startsWith("image/"));
}

export function getRelativePath(file: File): string | undefined {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || undefined;
}

export function createFingerprint(file: File): string {
  const relative = getRelativePath(file) || file.name;
  return `${relative}-${file.size}-${file.lastModified}`;
}

export function createManagedFile(file: File): ManagedFile {
  return {
    id: crypto.randomUUID(),
    file,
    previewUrl: URL.createObjectURL(file),
    relativePath: getRelativePath(file),
    fingerprint: createFingerprint(file),
    progress: 0,
    status: "ready",
  };
}

export function collectDroppedFiles(dataTransfer: DataTransfer): File[] {
  return Array.from(dataTransfer.files);
}
