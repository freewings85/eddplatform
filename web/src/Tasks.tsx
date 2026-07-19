import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type {
  Dataset,
  EvalProgram,
  Precondition,
  PreconditionKind,
  SystemVersion,
  Task,
  TaskInput,
} from "./types";

const KIND_LABEL: Record<PreconditionKind, string> = {
  start_system: "启动系统",
  start_eval_program: "启动评估程序",
  custom_script: "自定义脚本",
};

/** 前置条件行的可编辑形态（提交时映射成 Precondition）。 */
type Row = {
  kind: PreconditionKind;
  versionLabel?: string; // start_system：选中的系统版本
  programId?: string; // start_eval_program：选中的评估程序
  version?: string; // start_eval_program：选中的评估程序版本
  name?: string; // custom_script
  script?: string; // custom_script
};

export default function Tasks({ sysId }: { sysId: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.tasks(sysId).then(setTasks).catch((e) => setError(String(e)));
  }, [sysId]);
  useEffect(reload, [reload]);

  return (
    <>
      <h2 className="page">评估任务</h2>
      <p className="sub">
        评估任务 = <b>评估数据集</b> + <b>有序前置条件</b>（启动系统 / 启动评估程序 / 自定义脚本）。
        运行一次 = 一条运行记录（experiment）；版本在此选定。
      </p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setCreating(true)}>
          ＋ 新建评估任务
        </button>
        <span className="muted count">{tasks.length} 个任务</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>任务名</th>
              <th>数据集</th>
              <th>前置条件</th>
              <th>评估目标</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td className="mono">{t.id}</td>
                <td>
                  <b>{t.name}</b>
                </td>
                <td>{t.dataset_name ?? "—"}</td>
                <td>
                  {t.preconditions.map((p, i) => (
                    <span key={i} className="tag">
                      {i + 1}. {KIND_LABEL[p.kind]}
                      {p.ref ? ` · ${p.ref}` : ""}
                    </span>
                  ))}
                </td>
                <td className="mono">{t.eval_target ?? "—"}</td>
              </tr>
            ))}
            {tasks.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  还没有评估任务，点「新建评估任务」开始。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {creating && (
        <TaskForm
          sysId={sysId}
          onCancel={() => setCreating(false)}
          onDone={() => {
            setCreating(false);
            reload();
          }}
        />
      )}
    </>
  );
}

function TaskForm({
  sysId,
  onCancel,
  onDone,
}: {
  sysId: string;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState("");
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [versions, setVersions] = useState<SystemVersion[]>([]);
  const [programs, setPrograms] = useState<EvalProgram[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [evalTarget, setEvalTarget] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.dataset(sysId).then(setDataset).catch(() => {});
    api.versions(sysId).then(setVersions).catch(() => {});
    api.evalPrograms(sysId).then(setPrograms).catch(() => {});
  }, [sysId]);

  function addRow(kind: PreconditionKind) {
    const seed: Row =
      kind === "start_system"
        ? { kind, versionLabel: versions[0]?.label }
        : kind === "start_eval_program"
          ? { kind, programId: programs[0]?.id, version: programs[0]?.versions[0] }
          : { kind, name: "seed", script: "" };
    setRows((r) => [...r, seed]);
  }

  function patch(i: number, p: Partial<Row>) {
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...p } : row)));
  }
  function move(i: number, d: number) {
    setRows((r) => {
      const next = [...r];
      const j = i + d;
      if (j < 0 || j >= next.length) return r;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }
  function remove(i: number) {
    setRows((r) => r.filter((_, idx) => idx !== i));
  }

  function toPrecondition(row: Row): Precondition {
    if (row.kind === "start_system") {
      return { kind: row.kind, name: `启动系统 ${row.versionLabel ?? ""}`, ref: row.versionLabel };
    }
    if (row.kind === "start_eval_program") {
      const prog = programs.find((p) => p.id === row.programId);
      return {
        kind: row.kind,
        name: `启动评估程序 ${prog?.name ?? ""}@${row.version ?? ""}`,
        git_url: prog?.git_url,
        ref: row.version,
      };
    }
    return { kind: row.kind, name: row.name || "自定义脚本", script: row.script };
  }

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("任务名不能为空");
    if (rows.length === 0) return setError("至少添加一条前置条件");
    const payload: TaskInput = {
      name: name.trim(),
      system_id: sysId,
      dataset_name: dataset?.name ?? null,
      preconditions: rows.map(toPrecondition),
      eval_target: evalTarget.trim() || null,
    };
    setBusy(true);
    try {
      await api.createTask(sysId, payload);
      onDone();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>新建评估任务</b>
          <a className="modal-x" onClick={onCancel}>
            ✕
          </a>
        </div>

        <div className="modal-body">
          <label className="fld">
            <span>任务名 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="保险报价重构·v1 vs v2" />
          </label>

          <div className="fld-row">
            <label className="fld">
              <span>评估数据集（用例集）</span>
              <input value={dataset?.name ?? "…"} readOnly className="mono" />
            </label>
            <label className="fld">
              <span>评估观测目标（被测服务）</span>
              <input value={evalTarget} onChange={(e) => setEvalTarget(e.target.value)}
                placeholder="quote" />
            </label>
          </div>

          <div className="fld">
            <span>前置条件（按顺序执行；启动前把系统 / 评估程序拉起）</span>
            <div className="pc-add">
              <button className="btn sm" onClick={() => addRow("start_system")}>＋ 启动系统</button>
              <button className="btn sm" onClick={() => addRow("start_eval_program")}>＋ 启动评估程序</button>
              <button className="btn sm" onClick={() => addRow("custom_script")}>＋ 自定义脚本</button>
            </div>

            {rows.length === 0 && <i className="muted">还没有前置条件，用上面的按钮添加。</i>}
            {rows.map((row, i) => (
              <div key={i} className="pc-row">
                <div className="pc-head">
                  <span className="pc-idx">{i + 1}</span>
                  <span className={`pill ${row.kind === "custom_script" ? "neutral" : "new"}`}>
                    {KIND_LABEL[row.kind]}
                  </span>
                  <span className="pc-ctl">
                    <button className="btn sm" onClick={() => move(i, -1)} disabled={i === 0}>↑</button>
                    <button className="btn sm" onClick={() => move(i, 1)} disabled={i === rows.length - 1}>↓</button>
                    <button className="btn sm danger" onClick={() => remove(i)}>删除</button>
                  </span>
                </div>

                {row.kind === "start_system" && (
                  <label className="fld">
                    <span>选择系统版本（被测系统代码）</span>
                    <select value={row.versionLabel ?? ""} onChange={(e) => patch(i, { versionLabel: e.target.value })}>
                      {versions.length === 0 && <option value="">（无系统版本）</option>}
                      {versions.map((v) => (
                        <option key={v.id} value={v.label}>{v.label} · {v.status}</option>
                      ))}
                    </select>
                  </label>
                )}

                {row.kind === "start_eval_program" && (
                  <div className="fld-row">
                    <label className="fld">
                      <span>选择评估程序（评估代码）</span>
                      <select value={row.programId ?? ""} onChange={(e) => {
                        const prog = programs.find((p) => p.id === e.target.value);
                        patch(i, { programId: e.target.value, version: prog?.versions[0] });
                      }}>
                        {programs.length === 0 && <option value="">（无评估程序）</option>}
                        {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    </label>
                    <label className="fld">
                      <span>版本</span>
                      <select value={row.version ?? ""} onChange={(e) => patch(i, { version: e.target.value })}>
                        {(programs.find((p) => p.id === row.programId)?.versions ?? []).map((v) => (
                          <option key={v} value={v}>{v}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                )}

                {row.kind === "custom_script" && (
                  <>
                    <label className="fld">
                      <span>名称</span>
                      <input value={row.name ?? ""} onChange={(e) => patch(i, { name: e.target.value })}
                        placeholder="seed 数据 / 迁移" />
                    </label>
                    <label className="fld">
                      <span>脚本</span>
                      <textarea className="mono" rows={3} value={row.script ?? ""}
                        onChange={(e) => patch(i, { script: e.target.value })}
                        placeholder='kubectl -n "$EDD_NAMESPACE" create configmap seed --from-literal=ok=1' />
                    </label>
                  </>
                )}
              </div>
            ))}
          </div>

          {error && <p className="err">{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={busy}>取消</button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? "创建中…" : "创建任务"}
          </button>
        </div>
      </div>
    </div>
  );
}
