import { useEffect, useState } from "react";
import { api } from "./api";

export default function Settings() {
  const [host, setHost] = useState("");
  const [pk, setPk] = useState("");
  const [sk, setSk] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.settings().then((s) => {
      setHost(s.langfuse_host ?? "");
      setPk(s.langfuse_public_key ?? "");
      setSk(s.langfuse_secret_key ?? "");
    }).catch((e) => setError(String(e)));
  }, []);

  async function save() {
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      await api.saveSettings({
        langfuse_host: host.trim() || null,
        langfuse_public_key: pk.trim() || null,
        langfuse_secret_key: sk.trim() || null,
      });
      setMsg("已保存");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      await api.saveSettings({
        langfuse_host: host.trim() || null,
        langfuse_public_key: pk.trim() || null,
        langfuse_secret_key: sk.trim() || null,
      });
      const r = await api.testLangfuse();
      setMsg(`连接成功 ✓ 项目：${r.projects.join("、") || "（无）"}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h2 className="page">基础设置</h2>
      <p className="sub">平台级配置：Langfuse 连接（用例轨迹归档、跑分轨迹链接都靠它）</p>
      {error && <p className="err">{error}</p>}
      {msg && <p className="note">{msg}</p>}

      <div className="card" style={{ padding: 16, maxWidth: 640 }}>
        <label className="fld">
          <span>Langfuse Host</span>
          <input className="mono" value={host} onChange={(e) => setHost(e.target.value)}
            placeholder="http://localhost:3100" />
        </label>
        <label className="fld">
          <span>Public Key（Langfuse 项目设置 → API Keys，pk-lf-…；不是网页登录账号）</span>
          <input className="mono" value={pk} onChange={(e) => setPk(e.target.value)}
            placeholder="pk-lf-…" />
        </label>
        <label className="fld">
          <span>Secret Key（sk-lf-…）</span>
          <input className="mono" type="password" value={sk} onChange={(e) => setSk(e.target.value)}
            placeholder="sk-lf-…" />
        </label>
        <div className="pc-add" style={{ marginTop: 10 }}>
          <button className="btn primary" onClick={save} disabled={busy}>保存</button>
          <button className="btn" onClick={test} disabled={busy}>
            {busy ? "处理中…" : "保存并测试连接"}
          </button>
        </div>
      </div>
    </>
  );
}
