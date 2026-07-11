import { ArrowLeft, Clipboard, KeyRound, LogOut, RefreshCw, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { USER_SESSION_KEY, fetchMe, fetchMyCreditRecords } from "@/lib/api";
import type { CreditRecord, UserAccount } from "@/types";

export default function UserCenter() {
  const navigate = useNavigate();
  const [user, setUser] = useState<UserAccount>();
  const [records, setRecords] = useState<CreditRecord[]>([]);
  const [message, setMessage] = useState("");

  const apiKey = localStorage.getItem(USER_SESSION_KEY) || "";

  const reload = async () => {
    if (!apiKey) {
      navigate("/login");
      return;
    }
    const [nextUser, nextRecords] = await Promise.all([fetchMe(apiKey), fetchMyCreditRecords(apiKey)]);
    setUser(nextUser);
    setRecords(nextRecords);
  };

  useEffect(() => {
    reload().catch(() => {
      localStorage.removeItem(USER_SESSION_KEY);
      navigate("/login");
    });
  }, []);

  const copyKey = async () => {
    if (!user) return;
    await navigator.clipboard.writeText(user.apiKey);
    setMessage("API Key 已复制");
  };

  const logout = () => {
    localStorage.removeItem(USER_SESSION_KEY);
    navigate("/login");
  };

  return (
    <main className="min-h-screen bg-[#08111f] px-4 py-6 text-slate-100 lg:px-8">
      <div className="mx-auto max-w-[1100px]">
        <header className="mb-6 flex flex-col gap-4 rounded-[28px] border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20 backdrop-blur md:flex-row md:items-center md:justify-between">
          <div>
            <Link className="mb-3 inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-white" to="/">
              <ArrowLeft className="h-4 w-4" /> 返回文件管理
            </Link>
            <h1 className="text-3xl font-black text-white">用户中心</h1>
            <p className="mt-2 text-sm text-slate-400">查看你的积分余额、API Key 和积分消费记录。</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button className="secondary-download" onClick={() => reload()}><RefreshCw className="h-4 w-4" /> 刷新</button>
            <button className="secondary-download" onClick={logout}><LogOut className="h-4 w-4" /> 退出</button>
          </div>
        </header>

        {message && <div className="mb-5 rounded-2xl border border-cyan-300/30 bg-cyan-300/10 px-4 py-3 text-sm text-cyan-100">{message}</div>}

        {user && (
          <div className="grid gap-5 lg:grid-cols-[360px_minmax(0,1fr)]">
            <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5">
              <div className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-300/10 text-cyan-200"><UserRound /></div>
                  <div className="min-w-0">
                    <div className="truncate text-2xl font-black text-white">{user.name}</div>
                    <div className="truncate text-sm text-cyan-200">@{user.username}</div>
                  </div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-3">
                <div className="rounded-2xl border border-amber-300/30 bg-amber-300/10 p-4"><div className="text-xs text-amber-100">当前余额</div><div className="mt-2 text-2xl font-black text-amber-200">{user.credits}</div></div>
                <div className="rounded-2xl border border-emerald-300/30 bg-emerald-300/10 p-4"><div className="text-xs text-emerald-100">累计增加</div><div className="mt-2 text-2xl font-black text-emerald-200">{records.reduce((sum, record) => sum + Math.max(0, record.amount), 0)}</div></div>
                <div className="rounded-2xl border border-rose-300/30 bg-rose-300/10 p-4"><div className="text-xs text-rose-100">累计消费</div><div className="mt-2 text-2xl font-black text-rose-200">{records.reduce((sum, record) => sum + Math.max(0, -record.amount), 0)}</div></div>
              </div>

              <div className="mt-4 rounded-2xl border border-slate-700 bg-slate-900/70 p-4">
                <div className="mb-2 flex items-center gap-2 text-sm text-slate-300"><KeyRound className="h-4 w-4 text-cyan-300" /> API Key</div>
                <div className="rounded-xl bg-slate-950/70 p-3 text-xs text-slate-300 break-all">{user.apiKey}</div>
                <button className="secondary-download mt-3 w-full justify-center" onClick={copyKey}><Clipboard className="h-4 w-4" /> 复制 Key</button>
              </div>
            </section>

            <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5">
              <h2 className="mb-4 text-lg font-bold text-white">积分记录</h2>
              <div className="max-h-[620px] space-y-2 overflow-y-auto pr-1">
                {records.map((record) => (
                  <div key={record.id} className="rounded-xl border border-slate-700 bg-slate-900/60 p-3 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className={record.amount >= 0 ? "font-bold text-emerald-300" : "font-bold text-rose-300"}>{record.amount >= 0 ? "+" : ""}{record.amount}</span>
                      <span className="text-slate-400">余额 {record.balance}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{record.reason}{record.taskId ? ` · ${record.taskId}` : ""}</div>
                    <div className="mt-1 text-xs text-slate-600">{record.createdAt}</div>
                  </div>
                ))}
                {!records.length && <div className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6 text-center text-sm text-slate-500">暂无积分记录</div>}
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  );
}
