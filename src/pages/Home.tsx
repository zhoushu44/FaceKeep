import { Gauge, HardDrive, ImageUp, ShieldCheck } from "lucide-react";
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { FileQueue } from "@/components/FileQueue";
import { PreviewPanel } from "@/components/PreviewPanel";
import { UploadPanel } from "@/components/UploadPanel";
import { ADMIN_SESSION_KEY, USER_SESSION_KEY, completeUpload, createSession, fetchFiles, fetchImageTask, fetchTaskImage, submitImageTask, uploadChunk } from "@/lib/api";
import { CHUNK_SIZE, formatBytes } from "@/lib/fileUtils";
import { useFileStore } from "@/hooks/useFileStore";

const BROWSER_REQUEST_WORKERS = 2;

export default function Home() {
  const queue = useFileStore((state) => state.queue);
  const serverFiles = useFileStore((state) => state.serverFiles);
  const updateFile = useFileStore((state) => state.updateFile);
  const setServerFiles = useFileStore((state) => state.setServerFiles);
  const addServerFile = useFileStore((state) => state.addServerFile);

  useEffect(() => {
    fetchFiles().then(setServerFiles).catch(() => setServerFiles([]));
  }, [setServerFiles]);

  const uploadOne = async (itemId: string) => {
    const item = useFileStore.getState().queue.find((entry) => entry.id === itemId);
    if (!item) return;
    updateFile(item.id, { status: "uploading", error: undefined });
    try {
      const totalChunks = Math.ceil(item.file.size / CHUNK_SIZE) || 1;
      const session = await createSession({
        fileName: item.file.name,
        fileSize: item.file.size,
        fileType: item.file.type,
        relativePath: item.relativePath,
        fingerprint: item.fingerprint,
        totalChunks,
      });
      const uploaded = new Set(session.uploadedChunks);
      for (let index = 0; index < totalChunks; index += 1) {
        if (!uploaded.has(index)) {
          const start = index * CHUNK_SIZE;
          const chunk = item.file.slice(start, Math.min(start + CHUNK_SIZE, item.file.size));
          await uploadChunk({ uploadId: session.uploadId, chunkIndex: index, fingerprint: item.fingerprint, chunk });
        }
        updateFile(item.id, { progress: Math.round(((index + 1) / totalChunks) * 100) });
      }
      const serverFile = await completeUpload(session.uploadId);
      updateFile(item.id, { status: "done", serverId: serverFile.id, progress: 100 });
      addServerFile(serverFile);
    } catch (error) {
      updateFile(item.id, { status: "error", error: error instanceof Error ? error.message : "上传失败" });
    }
  };

  const runConcurrent = async (ids: string[], worker: (id: string) => Promise<void>) => {
    let cursor = 0;
    const workerCount = Math.min(BROWSER_REQUEST_WORKERS, ids.length);
    const runWorker = async () => {
      while (cursor < ids.length) {
        const id = ids[cursor];
        cursor += 1;
        await worker(id);
      }
    };
    await Promise.all(Array.from({ length: workerCount }, runWorker));
  };

  const startUpload = async () => {
    const targets = useFileStore.getState().queue.filter((item) => item.status === "ready" || item.status === "error");
    await runConcurrent(targets.map((item) => item.id), uploadOne);
  };

  const cutoutOne = async (itemId: string) => {
    const item = useFileStore.getState().queue.find((entry) => entry.id === itemId);
    if (!item) return;
    updateFile(item.id, { status: "cutting", progress: 10, error: undefined });
    try {
      const apiKey = localStorage.getItem(USER_SESSION_KEY);
      if (!apiKey) {
        updateFile(item.id, { status: "error", progress: 0, error: "请先登录用户账号再抠图" });
        return;
      }
      const submitted = await submitImageTask(item.file, apiKey);
      let task = await fetchImageTask(submitted.taskId, apiKey);
      while (task.status === "queued" || task.status === "processing") {
        updateFile(item.id, { progress: task.progress });
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        task = await fetchImageTask(submitted.taskId, apiKey);
      }
      if (task.status === "failed") throw new Error(task.error || "抠图失败，积分已退回");
      const output = await fetchTaskImage(submitted.taskId, apiKey);
      const previousUrl = useFileStore.getState().queue.find((entry) => entry.id === item.id)?.cutoutUrl;
      if (previousUrl?.startsWith("blob:")) URL.revokeObjectURL(previousUrl);
      updateFile(item.id, { status: "cutout", progress: 100, cutoutUrl: URL.createObjectURL(output), taskId: submitted.taskId });
    } catch (error) {
      updateFile(item.id, { status: "error", progress: 0, error: error instanceof Error ? error.message : "抠图失败" });
    }
  };

  const startCutout = async () => {
    const targets = useFileStore.getState().queue.filter((item) => item.status === "done" || (item.status === "error" && item.serverId));
    await runConcurrent(targets.map((item) => item.id), cutoutOne);
  };

  const uploadedSize = serverFiles.reduce((sum, item) => sum + item.fileSize, 0);
  const done = queue.filter((item) => item.status === "cutout").length;
  const cutting = queue.filter((item) => item.status === "cutting").length;
  const cutoutProgress = queue.length ? Math.round(queue.reduce((sum, item) => sum + (item.status === "cutout" ? 100 : item.status === "cutting" ? item.progress : 0), 0) / queue.length) : 0;
  const isAdmin = Boolean(localStorage.getItem(ADMIN_SESSION_KEY));
  const isUser = !isAdmin && Boolean(localStorage.getItem(USER_SESSION_KEY));
  const logout = () => {
    localStorage.removeItem(ADMIN_SESSION_KEY);
    localStorage.removeItem(USER_SESSION_KEY);
    window.location.reload();
  };

  // 首页对所有人可见，未登录时显示入口引导

  return (
    <main className="min-h-screen overflow-hidden bg-[#08111f] text-slate-100">
      <div className="fixed inset-0 -z-10 bg-[radial-gradient(circle_at_15%_10%,rgba(57,230,210,.20),transparent_34%),radial-gradient(circle_at_90%_20%,rgba(246,180,75,.16),transparent_28%),linear-gradient(135deg,#08111f,#0b1020_55%,#111827)]" />
      <div className="mx-auto max-w-[1500px] px-4 py-6 lg:px-8">
        <header className="mb-6 rounded-[32px] border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20 backdrop-blur-xl">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="mb-3 inline-flex rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-xs font-medium text-cyan-200">
                FaceKeep 文件管理中枢
              </div>
              <h1 className="max-w-3xl text-3xl font-black tracking-tight text-white md:text-5xl">上传、预览、续传与 PNG 标准输出，一屏完成。</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-400">支持单张图片、多张批量、文件夹整体上传；断点续传实时进度；导出 PNG 宽 1500 像素，高度自适应，96 DPI。</p>
              <div className="mt-4 flex flex-wrap gap-3">
                <Link className="inline-flex rounded-full border border-white/20 px-4 py-2 text-sm font-bold text-slate-200 transition hover:border-cyan-300/50 hover:text-cyan-100" to="/api-docs">API 文档</Link>
                {!isAdmin && !isUser && <><Link className="inline-flex rounded-full border border-cyan-300/30 bg-cyan-300/10 px-4 py-2 text-sm font-bold text-cyan-100" to="/login">用户登录</Link><Link className="inline-flex rounded-full border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm font-bold text-amber-100" to="/admin/login">管理员登录</Link></>}
                {isUser && <><Link className="inline-flex rounded-full border border-cyan-300/30 bg-cyan-300/10 px-4 py-2 text-sm font-bold text-cyan-100" to="/user">积分中心</Link><button className="inline-flex rounded-full border border-white/20 px-4 py-2 text-sm font-bold" onClick={logout}>退出</button></>}
                {isAdmin && <><Link className="inline-flex rounded-full border border-amber-300/30 bg-amber-300/10 px-4 py-2 text-sm font-bold text-amber-100" to="/admin">管理后台</Link><button className="inline-flex rounded-full border border-white/20 px-4 py-2 text-sm font-bold" onClick={logout}>退出</button></>}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:min-w-[520px]">
              <Metric icon={<ImageUp />} label="总文件" value={String(queue.length + serverFiles.length)} />
              <Metric icon={<Gauge />} label="抠图进度" value={`${cutoutProgress}%${cutting ? ` · ${cutting} 处理中` : ""}`} />
              <Metric icon={<ShieldCheck />} label="抠图完成" value={String(done)} />
              <Metric icon={<HardDrive />} label="存储" value={formatBytes(uploadedSize)} />
            </div>
          </div>
        </header>

        <div className="grid gap-5 xl:grid-cols-[360px_minmax(0,1fr)_380px]">
          <UploadPanel onStartUpload={startUpload} onStartCutout={startCutout} />
          <FileQueue />
          <PreviewPanel />
        </div>
      </div>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/60 p-3">
      <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-300/10 text-cyan-200">{icon}</div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-bold text-white">{value}</div>
    </div>
  );
}
