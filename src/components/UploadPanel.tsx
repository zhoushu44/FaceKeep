import { FolderUp, ImagePlus, Images, SlidersHorizontal, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { collectDroppedFiles, createManagedFile, imageOnly } from "@/lib/fileUtils";
import { useFileStore } from "@/hooks/useFileStore";

type Props = {
  onStartUpload: () => void;
};

export function UploadPanel({ onStartUpload }: Props) {
  const addFiles = useFileStore((state) => state.addFiles);
  const queue = useFileStore((state) => state.queue);
  const concurrency = useFileStore((state) => state.concurrency);
  const setConcurrency = useFileStore((state) => state.setConcurrency);
  const singleRef = useRef<HTMLInputElement>(null);
  const multiRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const addSelected = (files: File[]) => {
    const images = imageOnly(files).map(createManagedFile);
    if (images.length) addFiles(images);
  };

  return (
    <section className="rounded-[28px] border border-cyan-300/20 bg-slate-950/70 p-5 shadow-2xl shadow-cyan-950/40 backdrop-blur">
      <div
        className={`relative overflow-hidden rounded-[24px] border border-dashed p-6 transition ${
          dragging ? "border-cyan-300 bg-cyan-300/10" : "border-slate-600 bg-slate-900/80"
        }`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          addSelected(collectDroppedFiles(event.dataTransfer));
        }}
      >
        <div className="absolute -right-12 -top-12 h-40 w-40 rounded-full bg-cyan-400/10 blur-3xl" />
        <UploadCloud className="mb-5 h-12 w-12 text-cyan-300" />
        <h2 className="text-xl font-semibold tracking-tight text-white">上传工作台</h2>
        <p className="mt-2 text-sm leading-6 text-slate-400">拖拽图片到这里，或选择单张、多张、整个文件夹。上传前可预览，上传中显示实时进度。</p>
        <div className="mt-6 grid gap-3">
          <button className="action-button" onClick={() => singleRef.current?.click()}>
            <ImagePlus className="h-4 w-4" /> 单张图片
          </button>
          <button className="action-button" onClick={() => multiRef.current?.click()}>
            <Images className="h-4 w-4" /> 多张批量
          </button>
          <button className="action-button hidden sm:flex" onClick={() => folderRef.current?.click()}>
            <FolderUp className="h-4 w-4" /> 文件夹上传
          </button>
        </div>
        <input ref={singleRef} className="hidden" type="file" accept="image/*" onChange={(event) => addSelected(Array.from(event.target.files || []))} />
        <input ref={multiRef} className="hidden" type="file" accept="image/*" multiple onChange={(event) => addSelected(Array.from(event.target.files || []))} />
        <input ref={folderRef} className="hidden" type="file" accept="image/*" multiple webkitdirectory="" onChange={(event) => addSelected(Array.from(event.target.files || []))} />
      </div>
      <div className="mt-4 rounded-2xl border border-slate-700/70 bg-slate-900/60 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-white">
            <SlidersHorizontal className="h-4 w-4 text-cyan-300" />
            上传并发
          </div>
          <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-2.5 py-1 text-xs font-bold text-cyan-200">{concurrency} 路</span>
        </div>
        <input
          aria-label="上传并发数"
          className="w-full accent-cyan-300"
          type="range"
          min="1"
          max="8"
          value={concurrency}
          onChange={(event) => setConcurrency(Number(event.target.value))}
        />
        <div className="mt-2 flex justify-between text-[11px] text-slate-500">
          <span>稳妥 1</span>
          <span>推荐 2-4</span>
          <span>最高 8</span>
        </div>
      </div>
      <button
        className="mt-4 w-full rounded-2xl bg-cyan-300 px-4 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:-translate-y-0.5 hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={!queue.some((item) => item.status === "ready" || item.status === "error")}
        onClick={onStartUpload}
      >
        开始上传 / 断点续传
      </button>
      <div className="mt-4 rounded-2xl border border-slate-700/70 bg-slate-900/60 p-4 text-xs leading-5 text-slate-400">
        输出标准：JPG，宽度 1500 像素，高度按比例自适应，96 DPI。
      </div>
    </section>
  );
}
