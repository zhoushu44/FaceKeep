import { ArrowLeft, LogIn } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ADMIN_SESSION_KEY, USER_SESSION_KEY, adminLogin } from "@/lib/api";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    setMessage("");
    try {
      const token = await adminLogin(username, password);
      localStorage.removeItem(USER_SESSION_KEY);
      localStorage.setItem(ADMIN_SESSION_KEY, token);
      navigate("/admin");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#08111f] px-4 py-8 text-slate-100">
      <section className="w-full max-w-md rounded-[30px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/30 backdrop-blur">
        <Link className="mb-6 inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-white" to="/"><ArrowLeft className="h-4 w-4" /> 返回首页</Link>
        <h1 className="text-3xl font-black text-white">管理员登录</h1>
        <p className="mt-2 text-sm text-slate-400">管理凭据与普通用户账号独立。</p>
        {message && <div className="mt-5 rounded-2xl border border-rose-300/30 bg-rose-300/10 px-4 py-3 text-sm text-rose-100">{message}</div>}
        <div className="mt-6">
          <label className="admin-label">管理员用户名</label>
          <input className="admin-input" value={username} onChange={(event) => setUsername(event.target.value)} />
          <label className="admin-label">管理员密码</label>
          <input className="admin-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={(event) => event.key === "Enter" && submit()} />
          <button className="download-button mt-5 w-full justify-center" disabled={loading || !username || !password} onClick={submit}><LogIn className="h-4 w-4" /> {loading ? "登录中" : "登录"}</button>
        </div>
      </section>
    </main>
  );
}
