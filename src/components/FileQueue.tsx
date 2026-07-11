import { Download, Trash2 } from "lucide-react";
import { apiUrl, deleteServerFile } from "@/lib/api";
import { formatBytes } from "@/lib/fileUtils";
import { useFileStore } from "@/hooks/useFileStore";
import { StatusPill } from "@/components/StatusPill";

export function FileQueue() {
  const queue = useFileStore((state) => state.queue);
  const serverFiles = useFileStore((state) => state.serverFiles);
  const selectedId = useFileStore((state) => state.selectedId);
  const select = useFileStore((state) => state.select);
  const removeServerFile = useFileStore((state) => state.removeServerFile);

  return (
    <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5 shadow-2xl shadow-slate-950/30 backdrop-blur">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">文件队列</h2>
          <p className="text-xs text-slate-500">本地待上传与服务端文件统一管理</p>
        </div>
        <span className="rounded-full border border-amber-300/30 bg-amber-300/10 px-3 py-1 text-xs text-amber-200">{queue.length + serverFiles.length} 项</span>
      </div>
      <div className="max-h-[620px] space-y-3 overflow-y-auto pr-1">
        {queue.map((item) => (
          <button
            key={item.id}
            onClick={() => select(item.id)}
            className={`w-full rounded-2xl border p-3 text-left transition hover:border-cyan-300/60 ${selectedId === item.id ? "border-cyan-300/70 bg-cyan-300/10" : "border-slate-700 bg-slate-900/70"}`}
          >
            <div className="flex gap-3">
              <div className="flex shrink-0 gap-2">
                <div>
                  <img src={item.previewUrl} alt="原图缩略图" className="h-16 w-16 rounded-xl object-cover" />
                  <div className="mt-1 text-center text-[10px] text-slate-500">原图</div>
                </div>
                {item.cutoutUrl && (
                  <div>
                    <img src={item.cutoutUrl} alt="抠图缩略图" className="h-16 w-16 rounded-xl bg-[linear-gradient(45deg,#1e293b_25%,transparent_25%),linear-gradient(-45deg,#1e293b_25%,transparent_25%),linear-gradient(45deg,transparent_75%,#1e293b_75%),linear-gradient(-45deg,transparent_75%,#1e293b_75%)] bg-[length:12px_12px] object-contain" />
                    <div className="mt-1 text-center text-[10px] text-violet-300">抠图结果</div>
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-medium text-white">{item.relativePath || item.file.name}</div>
                <div className="mt-1 text-xs text-slate-500">{formatBytes(item.file.size)}</div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full rounded-full bg-cyan-300 transition-all" style={{ width: `${item.progress}%` }} />
                </div>
                <div className="mt-1 text-[10px] text-slate-500">{item.status === "cutting" ? `抠图处理中 ${item.progress}%` : item.status === "cutout" ? "抠图完成" : `上传进度 ${item.progress}%`}</div>
              </div>
              <StatusPill status={item.status} />
            </div>
          </button>
        ))}

        {serverFiles.map((item) => (
          <div key={item.id} className="rounded-2xl border border-slate-700 bg-slate-900/70 p-3">
            <button className="w-full text-left" onClick={() => select(item.id)}>
              <div className="truncate text-sm font-medium text-white">{item.relativePath || item.fileName}</div>
              <div className="mt-1 text-xs text-slate-500">{formatBytes(item.fileSize)} · 已上传</div>
            </button>
            <div className="mt-3 flex gap-2">
              <a className="mini-button" href={apiUrl(item.pngUrl)}>PNG 1500w</a>
              <a className="mini-button" href={apiUrl(item.url)}><Download className="h-3.5 w-3.5" /> 原图</a>
              <button
                className="mini-button text-rose-200"
                onClick={async () => {
                  await deleteServerFile(item.id);
                  removeServerFile(item.id);
                }}
              >
                <Trash2 className="h-3.5 w-3.5" /> 删除
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
