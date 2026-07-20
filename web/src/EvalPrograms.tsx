import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { EvalProgram } from "./types";

export default function EvalPrograms({ sysId }: { sysId: string }) {
  const [programs, setPrograms] = useState<EvalProgram[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<EvalProgram | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.evalPrograms(sysId).then(setPrograms).catch((e) => setError(String(e)));
  }, [sysId]);
  useEffect(reload, [reload]);

  async function remove(p: EvalProgram) {
    if (!confirm(`删除评估程序「${p.name}」？`)) return;
    try {
      await api.deleteEvalProgram(sysId, p.id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <>
      <h2 className="page">评估程序（评估代码）</h2>
      <p className="sub">
        独立于系统代码的<b>另一套 git 代码库</b>：实现评估逻辑，作为 Temporal worker 被拉起。
        <b>code</b> = 它认领的 RunCase workflow 名与 task queue——平台按 code 逐用例分派。
      </p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setCreating(true)}>
          ＋ 新建评估程序
        </button>
        <span className="muted count">{programs?.length ?? 0} 个</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>评估程序</th>
              <th>Git 仓库</th>
              <th>ref</th>
              <th>code（workflow 名/队列）</th>
              <th>负责人</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(programs ?? []).map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b> <span className="mono muted">{p.id}</span></td>
                <td className="mono">{p.git_url}</td>
                <td><span className="tag">{p.ref}</span></td>
                <td className="mono">{p.code}</td>
                <td>{p.owner ?? "—"}</td>
                <td>
                  <button className="btn sm" onClick={() => setEditing(p)}>编辑</button>{" "}
                  <button className="btn sm danger" onClick={() => remove(p)}>删除</button>
                </td>
              </tr>
            ))}
            {programs && programs.length === 0 && (
              <tr>
                <td colSpan={6} className="empty">
                  暂无评估程序 — 点击「新建评估程序」登记评估代码仓（git 仓库 + code）。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <ProgramForm
          sysId={sysId}
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

function ProgramForm({
  sysId,
  initial,
  onCancel,
  onDone,
}: {
  sysId: string;
  initial: EvalProgram | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [gitUrl, setGitUrl] = useState(initial?.git_url ?? "");
  const [ref, setRef] = useState(initial?.ref ?? "main");
  const [code, setCode] = useState(initial?.code ?? "");
  const [owner, setOwner] = useState(initial?.owner ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("名称不能为空");
    if (!gitUrl.trim()) return setError("Git 仓库不能为空");
    if (!code.trim()) return setError("code 不能为空（RunCase workflow 名/队列）");
    const payload = {
      name: name.trim(),
      git_url: gitUrl.trim(),
      ref: ref.trim() || "main",
      code: code.trim(),
      owner: owner.trim() || null,
    };
    setBusy(true);
    try {
      if (initial) await api.updateEvalProgram(sysId, initial.id, payload);
      else await api.createEvalProgram(sysId, payload);
      onDone();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>{initial ? "编辑评估程序" : "新建评估程序"}</b>
          <a className="modal-x" onClick={onCancel}>✕</a>
        </div>
        <div className="modal-body">
          <label className="fld">
            <span>名称 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="chatagent 评估" />
          </label>
          <label className="fld">
            <span>Git 仓库 *</span>
            <input value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} className="mono"
              placeholder="/mnt/e/Documents/github/chatagent-eval 或 ssh://git@…" />
          </label>
          <div className="fld-row">
            <label className="fld">
              <span>ref（分支/tag/sha）</span>
              <input value={ref} onChange={(e) => setRef(e.target.value)} className="mono"
                placeholder="main" />
            </label>
            <label className="fld">
              <span>code *（workflow 名/队列）</span>
              <input value={code} onChange={(e) => setCode(e.target.value)} className="mono"
                placeholder="chatagent-eval" />
            </label>
          </div>
          <label className="fld">
            <span>负责人</span>
            <input value={owner ?? ""} onChange={(e) => setOwner(e.target.value)} placeholder="leo" />
          </label>
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
