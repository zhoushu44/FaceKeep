import { ArrowLeft, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ADMIN_SESSION_KEY, USER_SESSION_KEY, fetchAdminBootstrapStatus, registerInitialAdmin } from "@/lib/api";

function validate(username: string, email: string, password: string, confirmPassword: string): string {
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$/.test(username.trim())) return "管理员账户名应为 3-32 位字母、数字、点、下划线或连字符";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) return "请输入有效的邮箱地址";
  if (password.length < 8 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/\d/.test(password) || !/[^A-Za-z0-9]/.test(password)) return "密码至少 8 位，且须包含大写字母、小写字母、数字和特殊字符";
  if (password !== confirmPassword) return "两次输入的密码不一致";
  return "";
}

export default function AdminRegister() {
  const navigate = useNavigate();
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchAdminBootstrapStatus().then(setAllowed).catch(() => {
      setAllowed(false);
      setMessage("初始管理员状态加载失败");
    });
  }, []);

  const submit = async () => {
    const validationMessage = validate(username, email, password, confirmPassword);
    if (validationMessage) {
      setMessage(validationMessage);
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const token = await registerInitialAdmin({ username: username.trim(), email: email.trim(), password, confirmPassword });
      localStorage.removeItem(USER_SESSION_KEY);
      localStorage.setItem(ADMIN_SESSION_KEY, token);
      navigate("/admin");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "初始管理员注册失败");
      if (error instanceof Error && error.message === "初始管理员已创建，不能注册") setAllowed(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#08111f] px-4 py-8 text-slate-100">
      <section className="w-full max-w-md rounded-[30px] border border-white/10 bg-white/[0.04] p-6 shadow-2xl shadow-black/30 backdrop-blur">
        <Link className="mb-6 inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-white" to="/admin/login"><ArrowLeft className="h-4 w-4" /> 返回管理员登录</Link>
        <h1 className="text-3xl font-black text-white">初始管理员注册</h1>
        <p className="mt-2 text-sm text-slate-400">仅在系统尚未配置任何管理员时可用。</p>
        {message && <div className="mt-5 rounded-2xl border border-rose-300/30 bg-rose-300/10 px-4 py-3 text-sm text-rose-100">{message}</div>}
        {allowed === false ? <div className="mt-6 rounded-2xl border border-slate-300/20 bg-white/5 px-4 py-3 text-sm text-slate-300">初始管理员已创建，不能注册。</div> : allowed && <div className="mt-6">
          <label className="admin-label">管理员账户名</label>
          <input className="admin-input" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="3-32 位字母、数字或 ._-" />
          <label className="admin-label">邮箱</label>
          <input className="admin-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@example.com" />
          <label className="admin-label">密码</label>
          <input className="admin-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位，含四类字符" />
          <label className="admin-label">确认密码</label>
          <input className="admin-input" type="password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} onKeyDown={(event) => event.key === "Enter" && submit()} />
          <button className="download-button mt-5 w-full justify-center" disabled={loading} onClick={submit}><UserPlus className="h-4 w-4" /> {loading ? "注册中" : "创建初始管理员"}</button>
        </div>}
      </section>
    </main>
  );
}
