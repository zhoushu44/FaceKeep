import { ArrowLeft, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ADMIN_SESSION_KEY, fetchImageApiSettings, saveImageApiSettings, verifyAdminSession } from "@/lib/api";

export default function AdminImageApiSettings() {
  const navigate = useNavigate();
  const [endpointUrl, setEndpointUrl] = useState("");
  const [initialEndpointUrl, setInitialEndpointUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [hasApiKey, setHasApiKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const reload = useCallback(async () => {
    const settings = await fetchImageApiSettings();
    setEndpointUrl(settings.endpointUrl);
    setInitialEndpointUrl(settings.endpointUrl);
    setHasApiKey(settings.hasApiKey);
    setApiKey("");
  }, []);

  useEffect(() => {
    void verifyAdminSession().then(reload).catch(() => {
      localStorage.removeItem(ADMIN_SESSION_KEY);
      navigate("/admin/login");
    });
  }, [navigate, reload]);

  const validate = (): string | undefined => {
    try {
      const url = new URL(endpointUrl.trim());
      if (!/^https?:$/.test(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash) return "请输入不含认证信息、查询参数或片段的 HTTP/HTTPS 端点 URL";
    } catch {
      return "请输入有效的 HTTP/HTTPS 端点 URL";
    }
    if (apiKey && (apiKey.length < 16 || apiKey.length > 512 || /\s/.test(apiKey))) return "API Key 必须为 16-512 个字符且不得包含空白";
    if (!apiKey && !hasApiKey) return "请填写 API Key";
    return undefined;
  };

  const save = async () => {
    const error = validate();
    if (error) { setMessage(error); return; }
    if (!window.confirm("确认保存图像 API 设置吗？")) return;
    setBusy(true);
    setMessage("");
    try {
      const settings = await saveImageApiSettings({ endpointUrl: endpointUrl.trim(), apiKey });
      setEndpointUrl(settings.endpointUrl);
      setInitialEndpointUrl(settings.endpointUrl);
      setHasApiKey(settings.hasApiKey);
      setApiKey("");
      setMessage("图像 API 设置已保存");
    } catch (saveError) {
      setMessage(saveError instanceof Error ? saveError.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const cancel = () => {
    if ((endpointUrl !== initialEndpointUrl || apiKey) && !window.confirm("尚未保存的修改将丢失，确认返回吗？")) return;
    navigate("/admin");
  };

  return <main className="min-h-screen bg-[#08111f] px-4 py-6 text-slate-100 lg:px-8"><div className="mx-auto max-w-3xl">
    <header className="mb-6 rounded-[28px] border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20 backdrop-blur"><Link className="mb-3 inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-white" to="/admin"><ArrowLeft className="h-4 w-4" /> 返回管理页面</Link><h1 className="text-3xl font-black text-white">图像 API 设置</h1><p className="mt-2 text-sm text-slate-400">配置用于图像编辑接口的服务端地址与 API Key。密钥仅保存在服务器，不会再次显示。</p></header>
    {message && <div className="mb-5 rounded-2xl border border-cyan-300/30 bg-cyan-300/10 px-4 py-3 text-sm text-cyan-100">{message}</div>}
    <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5"><label className="admin-label">Endpoint URL<input disabled={busy} className="admin-input" type="url" value={endpointUrl} placeholder="https://api.example.com/v1" onChange={(event) => setEndpointUrl(event.target.value)} /></label><p className="mt-1 text-xs text-slate-500">仅支持 HTTP/HTTPS；可填写路径，末尾斜杠会自动移除。</p><label className="admin-label">API Key<input disabled={busy} className="admin-input" type="password" value={apiKey} placeholder={hasApiKey ? "已保存，留空不修改" : "至少 16 个字符"} autoComplete="new-password" onChange={(event) => setApiKey(event.target.value)} /></label><p className="mt-1 text-xs text-slate-500">长度 16-512 个字符，且不得包含空白或控制字符。</p><div className="mt-6 flex justify-end gap-3"><button className="secondary-download" disabled={busy} onClick={cancel}>取消</button><button className="download-button" disabled={busy} onClick={() => void save()}><Save className="h-4 w-4" /> {busy ? "保存中..." : "保存设置"}</button></div></section>
  </div></main>;
}
