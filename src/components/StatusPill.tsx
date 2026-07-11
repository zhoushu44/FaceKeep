import { CheckCircle2, Clock3, FileWarning, Loader2 } from "lucide-react";
import type { UploadStatus } from "@/types";

const styles: Record<UploadStatus, string> = {
  ready: "border-slate-600/60 bg-slate-800/70 text-slate-200",
  uploading: "border-cyan-400/60 bg-cyan-400/10 text-cyan-200",
  done: "border-emerald-400/60 bg-emerald-400/10 text-emerald-200",
  cutting: "border-amber-400/60 bg-amber-400/10 text-amber-200",
  cutout: "border-violet-400/60 bg-violet-400/10 text-violet-200",
  error: "border-rose-400/60 bg-rose-400/10 text-rose-200",
};

const labels: Record<UploadStatus, string> = {
  ready: "待上传",
  uploading: "上传中",
  done: "已上传",
  cutting: "抠图中",
  cutout: "抠图完成",
  error: "失败",
};

export function StatusPill({ status }: { status: UploadStatus }) {
  const Icon = status === "ready" ? Clock3 : status === "uploading" || status === "cutting" ? Loader2 : status === "done" || status === "cutout" ? CheckCircle2 : FileWarning;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-1 text-xs ${styles[status]}`}>
      <Icon className={`h-3.5 w-3.5 ${status === "uploading" || status === "cutting" ? "animate-spin" : ""}`} />
      {labels[status]}
    </span>
  );
}
