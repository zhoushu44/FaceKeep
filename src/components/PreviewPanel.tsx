import { Download, FileArchive, Image as ImageIcon } from "lucide-react";
import { apiUrl } from "@/lib/api";
import { formatBytes } from "@/lib/fileUtils";
import { useFileStore } from "@/hooks/useFileStore";

export function PreviewPanel() {
  const queue = useFileStore((state) => state.queue);
  const serverFiles = useFileStore((state) => state.serverFiles);
  const selectedId = useFileStore((state) => state.selectedId);
  const local = queue.find((item) => item.id === selectedId);
  const remote = serverFiles.find((item) => item.id === selectedId) || serverFiles[0];

  const title = local?.relativePath || local?.file.name || remote?.relativePath || remote?.fileName || "等待选择图片";
  const src = local?.cutoutUrl || local?.previewUrl || (remote ? apiUrl(remote.url) : "");
  const size = local ? formatBytes(local.file.size) : remote ? formatBytes(remote.fileSize) : "-";

  return (
    <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5 shadow-2xl shadow-slate-950/30 backdrop-blur">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-white">文件预览</h2>
          <p className="mt-1 max-w-[260px] truncate text-xs text-slate-500">{title}</p>
        </div>
        <ImageIcon className="h-5 w-5 text-cyan-300" />
      </div>

      <div className="mt-5 flex aspect-[4/5] items-center justify-center overflow-hidden rounded-[24px] border border-slate-700 bg-[radial-gradient(circle_at_30%_20%,rgba(57,230,210,.16),transparent_32%),#0f172a]">
        {src ? <img src={src} alt={title} className="h-full w-full object-contain" /> : <div className="text-sm text-slate-500">上传或选择图片后显示预览</div>}
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3 text-xs">
        <div className="info-card">
          <span>文件大小</span>
          <strong>{size}</strong>
        </div>
        <div className="info-card">
          <span>导出格式</span>
          <strong>PNG</strong>
        </div>
        <div className="info-card">
          <span>输出宽度</span>
          <strong>1500 px</strong>
        </div>
        <div className="info-card">
          <span>DPI</span>
          <strong>96</strong>
        </div>
      </div>

      <div className="mt-5 grid gap-3">
        {local?.cutoutUrl ? (
          <a className="download-button" href={local.cutoutUrl} download={`${local.file.name.replace(/\.[^.]+$/, "")}_1500w_96dpi.png`}>
            <Download className="h-4 w-4" /> 下载抠图 PNG
          </a>
        ) : remote ? (
          <a className="download-button" href={apiUrl(remote.pngUrl)}>
            <Download className="h-4 w-4" /> 下载 PNG 1500 像素宽
          </a>
        ) : (
          <button className="download-button opacity-40" disabled>
            <Download className="h-4 w-4" /> 上传完成后可下载
          </button>
        )}
        <a className="secondary-download" href="/api/files.zip">
          <FileArchive className="h-4 w-4" /> 批量打包下载原图
        </a>
      </div>
    </section>
  );
}
