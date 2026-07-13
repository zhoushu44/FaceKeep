import { ArrowLeft, Copy, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

const API_BASE = "http://localhost:7333";

function CodeBlock({ children }: { children: string }) {
  const copy = async () => { await navigator.clipboard.writeText(children); };
  return <div className="relative mt-3 overflow-x-auto rounded-2xl border border-slate-700 bg-slate-950 p-4 pr-14 font-mono text-xs leading-6 text-cyan-100"><button className="absolute right-3 top-3 rounded-lg border border-slate-600 p-2 text-slate-300 hover:border-cyan-300 hover:text-cyan-100" onClick={() => void copy()} aria-label="复制接口示例"><Copy className="h-4 w-4" /></button><pre>{children}</pre></div>;
}

export default function ApiDocs() {
  return <main className="min-h-screen bg-[#08111f] px-4 py-6 text-slate-100 lg:px-8"><div className="mx-auto max-w-5xl">
    <header className="mb-6 rounded-[28px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/20 backdrop-blur"><Link className="inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-white" to="/"><ArrowLeft className="h-4 w-4" /> 返回首页</Link><div className="mt-5 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm font-medium text-cyan-200">FaceKeep Public API</p><h1 className="mt-2 text-3xl font-black text-white md:text-4xl">任务 API 文档</h1><p className="mt-3 text-sm leading-6 text-slate-400">通过 API 提交图片抠图任务、查询进度并下载结果。此页面不包含管理员或图像服务密钥。</p></div><a className="inline-flex items-center gap-2 rounded-xl border border-cyan-300/30 bg-cyan-300/10 px-4 py-2 text-sm font-bold text-cyan-100 hover:bg-cyan-300/20" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">FastAPI Swagger <ExternalLink className="h-4 w-4" /></a></div></header>
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]"><div className="space-y-5">
      <Section title="服务地址与鉴权"><p>本地开发服务地址：<code>{API_BASE}</code>。所有任务接口均使用用户 API Key，在请求头中传入 <code>X-API-Key</code>。</p><CodeBlock>{`X-API-Key: fk_your_api_key`}</CodeBlock></Section>
      <Section title="提交任务 · POST /api/tasks/submit"><p>以 <code>multipart/form-data</code> 上传图片，字段名为 <code>file</code>。成功后任务先进入全局队列。</p><CodeBlock>{`curl -X POST "${API_BASE}/api/tasks/submit" \
  -H "X-API-Key: fk_your_api_key" \
  -F "file=@input.jpg"

{
  "taskId": "...",
  "status": "queued",
  "progress": 0,
  "queuePosition": 0,
  "imageUrl": "/api/tasks/.../image"
}`}</CodeBlock></Section>
      <Section title="查询任务 · GET /api/tasks/{taskId}"><p>使用任务 ID 查询 <code>taskId</code>、<code>status</code>、<code>progress</code>、<code>queuePosition</code> 与 <code>imageUrl</code>。请求同样必须带 <code>X-API-Key</code>。</p><CodeBlock>{`curl "${API_BASE}/api/tasks/{taskId}" \
  -H "X-API-Key: fk_your_api_key"`}</CodeBlock></Section>
      <Section title="下载图片 · GET /api/tasks/{taskId}/image"><p>任务完成后下载 PNG 结果；未完成时返回 <code>409</code>。</p><CodeBlock>{`curl "${API_BASE}/api/tasks/{taskId}/image" \
  -H "X-API-Key: fk_your_api_key" \
  --output result.png`}</CodeBlock></Section>
      <Section title="队列与状态语义"><ul className="list-disc space-y-2 pl-5"><li><code>queued</code>：已排队，<code>queuePosition</code> 为此前等待的任务数。</li><li><code>processing</code>：服务器正在处理。</li><li><code>completed</code>：可下载结果图片。</li><li><code>failed</code>：处理失败，查看 <code>error</code>。</li></ul><p className="mt-3">队列并发为服务器全局设置，影响所有用户；管理员可在图像 API 设置中配置最大同时处理数量，并非单个用户的限制。</p></Section>
      <Section title="安全与常见错误"><p>查询和下载仅限任务归属用户：使用其他用户的 API Key 会返回 <code>403</code>。请妥善保管 API Key，勿在浏览器前端、公开仓库或日志中暴露。</p><div className="mt-3 grid gap-2 text-sm text-slate-300"><div><code>400</code> 请求参数或图片无效</div><div><code>401</code> 未提供或 API Key 无效</div><div><code>403</code> 任务不属于当前用户</div><div><code>409</code> 任务尚未完成，不能下载图片</div></div></Section>
    </div><aside className="h-fit rounded-[24px] border border-slate-700/70 bg-slate-950/70 p-5 text-sm text-slate-400"><h2 className="font-bold text-white">快速链接</h2><a className="mt-4 flex items-center gap-2 text-cyan-200 hover:text-white" href={`${API_BASE}/docs`} target="_blank" rel="noreferrer">Swagger /docs <ExternalLink className="h-4 w-4" /></a><Link className="mt-3 block text-cyan-200 hover:text-white" to="/">首页工作台</Link></aside></div>
  </div></main>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="rounded-[24px] border border-slate-700/70 bg-slate-950/70 p-5 text-sm leading-6 text-slate-400"><h2 className="text-xl font-bold text-white">{title}</h2><div className="mt-3">{children}</div></section>;
}
