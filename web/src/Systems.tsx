import { useCallback, useEffect, useState } from "react";
import { useEscape } from "./useEscape";
import { api } from "./api";
import type { System } from "./types";

export default function Systems({ onOpen }: { onOpen: (id: string, name: string) => void }) {
  const [systems, setSystems] = useState<System[] | null>(null);
  const [editing, setEditing] = useState<System | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.systems().then(setSystems).catch((e) => setError(String(e)));
  }, []);
  useEffect(reload, [reload]);

  async function remove(s: System) {
    if (!confirm(`删除系统「${s.name}」？（有任务或运行记录时会被拒绝）`)) return;
    try {
      await api.deleteSystem(s.id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <>
      <h2 className="page">系统管理</h2>
      <p className="sub">注册被评系统；进入系统工作台管理它的评估程序、用例与任务</p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setCreating(true)}>
          ＋ 新建系统
        </button>
        <span className="muted count">{systems?.length ?? 0} 套系统</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>系统</th>
              <th>ID</th>
              <th>负责人</th>
              <th>说明</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(systems ?? []).map((s) => (
              <tr key={s.id} className="click" style={{ cursor: "pointer" }}
                title="点击进入系统工作台"
                onClick={() => onOpen(s.id, s.name)}>
                <td><b>{s.name}</b></td>
                <td className="mono">{s.id}</td>
                <td>{s.owner ?? "—"}</td>
                <td className="muted">{s.description ?? "—"}</td>
                <td>
                  {/* 行点击=进入；操作按钮阻止冒泡避免误进 */}
                  <button className="btn sm"
                    onClick={(e) => { e.stopPropagation(); setEditing(s); }}>编辑</button>{" "}
                  <button className="btn sm danger"
                    onClick={(e) => { e.stopPropagation(); remove(s); }}>删除</button>
                </td>
              </tr>
            ))}
            {systems && systems.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  暂无系统 — 点击「新建系统」注册你的第一套被评系统。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <SystemForm
          initial={editing}
          onCancel={() => {
            setCreating(false);
            setEditing(null);
          }}
          onDone={() => {
            setCreating(false);
            setEditing(null);
            reload();
          }}
        />
      )}
    </>
  );
}

function SystemForm({
  initial,
  onCancel,
  onDone,
}: {
  initial: System | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [id, setId] = useState(initial?.id ?? "");
  const [name, setName] = useState(initial?.name ?? "");
  const [owner, setOwner] = useState(initial?.owner ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [casesGitUrl, setCasesGitUrl] = useState(initial?.cases_git_url ?? "");
  const [casesBranch, setCasesBranch] = useState(initial?.cases_branch ?? "main");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscape(onCancel);

  async function submit() {
    setError(null);
    if (!id.trim()) return setError("系统 ID 不能为空（如 chatagent）");
    if (!name.trim()) return setError("名称不能为空");
    if (/\s/.test(casesGitUrl.trim()))
      return setError("用例仓库地址不能包含空格/制表符");
    const payload: System = {
      id: id.trim(),
      name: name.trim(),
      owner: owner.trim() || null,
      description: description.trim() || null,
      cases_git_url: casesGitUrl.trim() || null,
      cases_branch: casesBranch.trim() || "main",
    };
    setBusy(true);
    try {
      if (initial) await api.updateSystem(initial.id, payload);
      else await api.createSystem(payload);
      onDone();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>{initial ? "编辑系统" : "新建系统"}</b>
          <a className="modal-x" onClick={onCancel}>✕</a>
        </div>
        <div className="modal-body">
          <label className="fld">
            <span>系统 ID *</span>
            <input value={id} onChange={(e) => setId(e.target.value)}
              readOnly={!!initial} className="mono" placeholder="chatagent" />
          </label>
          <label className="fld">
            <span>名称 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="chatagent 2.3" />
          </label>
          <label className="fld">
            <span>负责人</span>
            <input value={owner ?? ""} onChange={(e) => setOwner(e.target.value)} placeholder="leo" />
          </label>
          <label className="fld">
            <span>说明</span>
            <textarea rows={3} value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="被评系统的一句话说明" />
          </label>
          <div className="fld-row">
            <label className="fld">
              <span>用例仓库 git 地址（git 管用例版本；一个文件夹=一个用例库）</span>
              <input value={casesGitUrl} onChange={(e) => setCasesGitUrl(e.target.value)}
                className="mono" placeholder="ssh://git@…/chatagent-cases.git 或本地路径" />
            </label>
            <label className="fld">
              <span>用例仓分支</span>
              <input value={casesBranch} onChange={(e) => setCasesBranch(e.target.value)}
                className="mono" placeholder="main" />
            </label>
          </div>
          {error && <p className="err">{error}</p>}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={busy}>取消</button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
