import { useCallback, useEffect, useState } from "react";
import { useEscape } from "./useEscape";
import { api } from "./api";
import type { SystemProgram } from "./types";

export default function SystemPrograms({ sysId }: { sysId: string }) {
  const [programs, setPrograms] = useState<SystemProgram[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<SystemProgram | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.systemPrograms(sysId).then(setPrograms).catch((e) => setError(String(e)));
  }, [sysId]);
  useEffect(reload, [reload]);

  async function remove(p: SystemProgram) {
    if (!confirm(`删除系统程序「${p.name}」？`)) return;
    try {
      await api.deleteSystemProgram(sysId, p.id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <>
      <h2 className="page">系统程序（被评系统的 git 单元）</h2>
      <p className="sub">
        登记被评系统的可部署单元：名称 + git 地址（+ 单元目录）。<b>登记一次，
        建评估任务时下拉复用</b>——分支/commit 在任务里选定并固化。一个系统多个进程
        可各登记一条（如 mainagent / sessionstore / toolexecutor）。
      </p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setCreating(true)}>
          ＋ 新建系统程序
        </button>
        <span className="muted count">{programs?.length ?? 0} 个</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>系统程序</th>
              <th>Git 仓库</th>
              <th>单元目录</th>
              <th>负责人</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(programs ?? []).map((p) => (
              <tr key={p.id}>
                <td><b>{p.name}</b></td>
                <td className="mono">{p.git_url}</td>
                <td className="mono">{p.path}</td>
                <td>{p.owner ?? "—"}</td>
                <td>
                  <button className="btn sm" onClick={() => setEditing(p)}>编辑</button>{" "}
                  <button className="btn sm danger" onClick={() => remove(p)}>删除</button>
                </td>
              </tr>
            ))}
            {programs && programs.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  暂无系统程序 — 点击「新建系统程序」登记被评系统的 git 单元
                  （仓库需按 EDD 接入约定提供 build.sh + 标准 helm chart）。
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
  initial: SystemProgram | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [gitUrl, setGitUrl] = useState(initial?.git_url ?? "");
  const [path, setPath] = useState(initial?.path ?? ".");
  const [env, setEnv] = useState(initial?.env ?? "");
  const [owner, setOwner] = useState(initial?.owner ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscape(onCancel);

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("名称不能为空");
    if (!gitUrl.trim()) return setError("Git 仓库不能为空");
    if (/\s/.test(gitUrl.trim()))
      return setError("Git 地址不能包含空格/制表符——检查是否粘贴了列表里的多余内容");
    const payload = {
      name: name.trim(),
      git_url: gitUrl.trim(),
      path: path.trim() || ".",
      env: env.trim() ? env : null,
      owner: owner.trim() || null,
    };
    setBusy(true);
    try {
      if (initial) await api.updateSystemProgram(sysId, initial.id, payload);
      else await api.createSystemProgram(sysId, payload);
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
          <b>{initial ? "编辑系统程序" : "新建系统程序"}</b>
          <a className="modal-x" onClick={onCancel}>✕</a>
        </div>
        <div className="modal-body">
          <label className="fld">
            <span>名称 *（自定义，如 mainagent）</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="mainagent" />
          </label>
          <label className="fld">
            <span>Git 仓库 *</span>
            <input value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} className="mono"
              placeholder="ssh://git@…/chatagent.git 或本地路径" />
          </label>
          <div className="fld-row">
            <label className="fld">
              <span>单元目录（含 build.sh + chart/，默认 . = 根）</span>
              <input value={path} onChange={(e) => setPath(e.target.value)} className="mono"
                placeholder="edd/system" />
            </label>
            <label className="fld">
              <span>负责人</span>
              <input value={owner ?? ""} onChange={(e) => setOwner(e.target.value)} placeholder="leo" />
            </label>
          </div>
          <label className="fld">
            <span>部署配置（.env.eval 内容，KEY=VALUE 每行；建任务时带出可改，部署时注入 chart）</span>
            <textarea className="mono" rows={4} value={env ?? ""}
              onChange={(e) => setEnv(e.target.value)}
              placeholder={"LITELLM_BASE_URL=https://…\nLITELLM_KEY=sk-…"} />
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
