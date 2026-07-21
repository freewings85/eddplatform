import { useCallback, useEffect, useState } from "react";
import { useEscape } from "./useEscape";
import { api } from "./api";
import type { InfraProgram } from "./types";

export default function InfraPrograms({ sysId }: { sysId: string }) {
  const [programs, setPrograms] = useState<InfraProgram[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<InfraProgram | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.infraPrograms(sysId).then(setPrograms).catch((e) => setError(String(e)));
  }, [sysId]);
  useEffect(reload, [reload]);

  async function remove(p: InfraProgram) {
    if (!confirm(`删除基础组件库「${p.name}」？`)) return;
    try {
      await api.deleteInfraProgram(sysId, p.id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <>
      <h2 className="page">基础组件（独立部署的 kafka / postgres / temporal…）</h2>
      <p className="sub">
        登记基础组件库：一个<b>独立 git 仓库 + 目录</b>，目录下每个子文件夹 = 一个
        可独立部署进运行 namespace 的组件（<b>纯 chart 单元</b>：只有 chart/，无
        build.sh，平台跳过构建直接 helm 部署）。建任务时在「基础组件」区块从这里
        选库、扫描、勾选组件——多任务并发需要隔离共享组件时用。
      </p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setCreating(true)}>
          ＋ 新建基础组件库
        </button>
        <span className="muted count">{programs?.length ?? 0} 个</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>组件库</th>
              <th>Git 仓库</th>
              <th>组件目录</th>
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
                  暂无基础组件库 — 点击「新建基础组件库」登记（仓库里每个子文件夹一个
                  组件，如 kafka/chart、postgres/chart、temporal/chart）。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {(creating || editing) && (
        <InfraForm
          sysId={sysId}
          initial={editing}
          onCancel={() => { setCreating(false); setEditing(null); }}
          onDone={() => { setCreating(false); setEditing(null); reload(); }}
        />
      )}
    </>
  );
}

function InfraForm({ sysId, initial, onCancel, onDone }: {
  sysId: string;
  initial: InfraProgram | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [gitUrl, setGitUrl] = useState(initial?.git_url ?? "");
  const [path, setPath] = useState(initial?.path ?? ".");
  const [owner, setOwner] = useState(initial?.owner ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscape(onCancel);

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("名称不能为空");
    if (!gitUrl.trim()) return setError("Git 仓库不能为空");
    if (/\s/.test(gitUrl.trim()))
      return setError("Git 地址不能包含空格/制表符——检查是否粘贴了多余内容");
    const payload = {
      name: name.trim(),
      git_url: gitUrl.trim(),
      path: path.trim() || ".",
      owner: owner.trim() || null,
    };
    setBusy(true);
    try {
      if (initial) await api.updateInfraProgram(sysId, initial.id, payload);
      else await api.createInfraProgram(sysId, payload);
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
          <b>{initial ? "编辑基础组件库" : "新建基础组件库"}</b>
          <a className="modal-x" onClick={onCancel}>✕</a>
        </div>
        <div className="modal-body">
          <label className="fld">
            <span>名称 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="通用基础组件" />
          </label>
          <label className="fld">
            <span>Git 仓库 *（独立的组件仓库）</span>
            <input value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} className="mono"
              placeholder="ssh://git@…/edd_infra_components.git" />
          </label>
          <div className="fld-row">
            <label className="fld">
              <span>组件目录（子文件夹=组件，默认 . = 仓库根）</span>
              <input value={path} onChange={(e) => setPath(e.target.value)} className="mono"
                placeholder="." />
            </label>
            <label className="fld">
              <span>负责人</span>
              <input value={owner ?? ""} onChange={(e) => setOwner(e.target.value)} placeholder="leo" />
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
