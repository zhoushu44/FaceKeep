import { ArrowLeft, Clipboard, Coins, KeyRound, LogOut, Plus, RefreshCw, Save, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ADMIN_SESSION_KEY, adminLogout, adjustCredits, createUser, fetchCreditRecords, fetchUsers, setCredits, updateUser, verifyAdminSession } from "@/lib/api";
import type { CreditRecord, UserAccount } from "@/types";

export default function Admin() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [records, setRecords] = useState<CreditRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [initialCredits, setInitialCredits] = useState(10);
  const [adjustAmount, setAdjustAmount] = useState(1);
  const [setValue, setSetValue] = useState(0);
  const [message, setMessage] = useState("");

  const selected = useMemo(() => users.find((user) => user.id === selectedId), [users, selectedId]);

  const reload = async () => {
    const [nextUsers, nextRecords] = await Promise.all([fetchUsers(), fetchCreditRecords()]);
    setUsers(nextUsers);
    setRecords(nextRecords);
    if (!selectedId && nextUsers[0]) setSelectedId(nextUsers[0].id);
  };

  useEffect(() => {
    verifyAdminSession().then(reload).catch(() => {
      localStorage.removeItem(ADMIN_SESSION_KEY);
      navigate("/admin/login");
    });
  }, []);

  useEffect(() => {
    if (selected) {
      setUsername(selected.username || "");
      setName(selected.name);
      setApiKey(selected.apiKey);
      setSetValue(selected.credits);
    }
  }, [selected]);

  const create = async () => {
    const user = await createUser({ username, name: name || username, password, credits: initialCredits });
    setMessage(`已创建用户：${user.name}，API Key 已自动生成`);
    setUsername("");
    setName("");
    setPassword("");
    setApiKey("");
    setSelectedId(user.id);
    await reload();
  };

  const saveUser = async () => {
    if (!selected) return;
    const user = await updateUser(selected.id, { username, name, apiKey, password: password || undefined });
    setMessage(`已保存：${user.name}`);
    setPassword("");
    await reload();
  };

  const addOrMinus = async (amount: number) => {
    if (!selected) return;
    const user = await adjustCredits(selected.id, amount, amount >= 0 ? "admin_add" : "admin_subtract");
    setMessage(`积分已更新：${user.credits}`);
    await reload();
  };

  const setCredit = async () => {
    if (!selected) return;
    const user = await setCredits(selected.id, setValue, "admin_set");
    setMessage(`积分已设置：${user.credits}`);
    await reload();
  };

  const copyKey = async () => {
    if (!selected) return;
    await navigator.clipboard.writeText(selected.apiKey);
    setMessage("API Key 已复制");
  };

  return (
    <main className="min-h-screen bg-[#08111f] px-4 py-6 text-slate-100 lg:px-8">
      <div className="mx-auto max-w-[1500px]">
        <header className="mb-6 flex flex-col gap-4 rounded-[28px] border border-white/10 bg-white/[0.04] p-5 shadow-2xl shadow-black/20 backdrop-blur lg:flex-row lg:items-center lg:justify-between">
          <div>
            <Link className="mb-3 inline-flex items-center gap-2 text-sm text-cyan-200 hover:text-white" to="/">
              <ArrowLeft className="h-4 w-4" /> 返回文件管理
            </Link>
            <h1 className="text-3xl font-black text-white">用户与积分管理</h1>
            <p className="mt-2 text-sm text-slate-400">创建用户、设置 API Key、增减积分，并查看每次扣费和调整记录。</p>
          </div>
          <div className="flex gap-3">
            <button className="action-button" onClick={() => reload()}><RefreshCw className="h-4 w-4" /> 刷新数据</button>
            <button className="secondary-download" onClick={async () => { await adminLogout(); navigate("/admin/login"); }}><LogOut className="h-4 w-4" /> 退出</button>
          </div>
        </header>

        {message && <div className="mb-5 rounded-2xl border border-cyan-300/30 bg-cyan-300/10 px-4 py-3 text-sm text-cyan-100">{message}</div>}

        <div className="grid gap-5 xl:grid-cols-[380px_minmax(0,1fr)_420px]">
          <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-white"><Plus className="h-5 w-5 text-cyan-300" /> 创建/编辑用户</h2>
            <label className="admin-label">登录用户名</label>
            <input className="admin-input" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="例如：user001" />
            <label className="admin-label">用户姓名/名称</label>
            <input className="admin-input" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：客户 A" />
            <label className="admin-label">登录密码</label>
            <input className="admin-input" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={selected ? "留空表示不修改密码" : "新用户必填"} />
            <label className="admin-label">API Key</label>
            <input className="admin-input" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="新建时自动生成；编辑时可手动重置" />
            <label className="admin-label">新用户初始积分</label>
            <input className="admin-input" type="number" value={initialCredits} onChange={(event) => setInitialCredits(Number(event.target.value))} />
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button className="download-button" onClick={create}><Plus className="h-4 w-4" /> 新建用户</button>
              <button className="secondary-download" disabled={!selected} onClick={saveUser}><Save className="h-4 w-4" /> 保存修改</button>
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-white"><UserRound className="h-5 w-5 text-cyan-300" /> 用户列表</h2>
            <div className="max-h-[620px] space-y-3 overflow-y-auto pr-1">
              {users.map((user) => (
                <button
                  key={user.id}
                  className={`w-full rounded-2xl border p-4 text-left transition ${selectedId === user.id ? "border-cyan-300/70 bg-cyan-300/10" : "border-slate-700 bg-slate-900/70 hover:border-cyan-300/40"}`}
                  onClick={() => setSelectedId(user.id)}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-bold text-white">{user.name}</div>
                      <div className="mt-1 truncate text-xs text-cyan-200">@{user.username || "未设置用户名"}</div>
                      <div className="mt-1 truncate text-xs text-slate-500">{user.apiKey}</div>
                    </div>
                    <div className="rounded-full bg-amber-300/10 px-3 py-1 text-sm font-black text-amber-200">{user.credits} 分</div>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="rounded-[28px] border border-slate-700/70 bg-slate-950/70 p-5">
            <h2 className="mb-4 flex items-center gap-2 text-lg font-bold text-white"><Coins className="h-5 w-5 text-amber-300" /> 积分与 Key</h2>
            {selected ? (
              <>
                <div className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4">
                  <div className="text-sm text-slate-400">当前用户</div>
                  <div className="mt-1 text-2xl font-black text-white">{selected.name}</div>
                  <div className="mt-3 flex items-center gap-2 rounded-xl bg-slate-950/70 p-3 text-xs text-slate-300">
                    <KeyRound className="h-4 w-4 text-cyan-300" />
                    <span className="min-w-0 flex-1 truncate">{selected.apiKey}</span>
                    <button onClick={copyKey}><Clipboard className="h-4 w-4" /></button>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <input className="admin-input !mt-0" type="number" value={adjustAmount} onChange={(event) => setAdjustAmount(Number(event.target.value))} />
                  <button className="download-button" onClick={() => addOrMinus(Math.abs(adjustAmount))}>加积分</button>
                  <button className="secondary-download" onClick={() => addOrMinus(-Math.abs(adjustAmount))}>减积分</button>
                  <div className="rounded-2xl border border-amber-300/30 bg-amber-300/10 px-4 py-3 text-center text-xl font-black text-amber-200">{selected.credits} 分</div>
                </div>

                <div className="mt-4 grid grid-cols-[1fr_auto] gap-3">
                  <input className="admin-input !mt-0" type="number" value={setValue} onChange={(event) => setSetValue(Number(event.target.value))} />
                  <button className="secondary-download px-5" onClick={setCredit}>设为该值</button>
                </div>
              </>
            ) : (
              <div className="text-sm text-slate-500">请选择或创建用户</div>
            )}

            <h3 className="mb-3 mt-6 text-sm font-bold text-slate-300">积分记录</h3>
            <div className="max-h-[280px] space-y-2 overflow-y-auto pr-1">
              {records.filter((record) => !selected || record.userId === selected.id).map((record) => (
                <div key={record.id} className="rounded-xl border border-slate-700 bg-slate-900/60 p-3 text-xs">
                  <div className="flex justify-between gap-3">
                    <span className={record.amount >= 0 ? "text-emerald-300" : "text-rose-300"}>{record.amount >= 0 ? "+" : ""}{record.amount}</span>
                    <span className="text-slate-400">余额 {record.balance}</span>
                  </div>
                  <div className="mt-1 text-slate-500">{record.reason}{record.taskId ? ` · ${record.taskId}` : ""}</div>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
