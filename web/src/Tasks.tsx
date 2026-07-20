import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type {
  EvalProgram,
  Precondition,
  PreconditionKind,
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
  name?: string;
  gitUrl?: string; // start_system：被评系统仓库
  ref?: string; // start_system / start_eval_program：git ref
  programId?: string; // start_eval_program：选中的评估程序
  script?: string; // custom_script
};

export default function Tasks({ sysId }: { sysId: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [programs, setPrograms] = useState<EvalProgram[]>([]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(() => {
    api.tasks(sysId).then(setTasks).catch((e) => setError(String(e)));
    api.evalPrograms(sysId).then(setPrograms).catch(() => {});
  }, [sysId]);
  useEffect(reload, [reload]);

  async function run(t: Task) {
    setError(null);
    setNotice(null);
    try {
      const r = await api.runTask(sysId, t.id);
      setNotice(`已提交执行 ${r.id}，去「运行记录」查看进度与结果。`);
    } catch (e) {
      setError(String(e));
    }
  }

  async function remove(t: Task) {
    if (!confirm(`删除任务「${t.name}」？`)) return;
    try {
      await api.deleteTask(sysId, t.id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <>
      <h2 className="page">评估任务</h2>
      <p className="sub">
        评估任务 = <b>有序前置条件</b>（启动系统 / 启动评估程序 / 自定义脚本）+ <b>评估程序</b>。
        点「执行」= 平台经 Temporal 拉起环境并逐用例分派评估，产出一条运行记录。
      </p>
      {error && <p className="err">{error}</p>}
      {notice && <p className="note">{notice}</p>}

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
              <th>前置条件</th>
              <th>评估程序</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td className="mono">{t.id}</td>
                <td>
                  <b>{t.name}</b>
                </td>
                <td>
                  {t.preconditions.map((p, i) => (
                    <span key={i} className="tag">
                      {i + 1}. {KIND_LABEL[p.kind]}
                      {p.ref ? ` · ${p.ref}` : ""}
                    </span>
                  ))}
                </td>
                <td className="mono">
                  {programs.find((p) => p.id === t.eval_program_id)?.code ??
                    (t.eval_program_id || "—")}
                </td>
                <td>
                  <button className="btn sm primary" onClick={() => run(t)}>执行</button>{" "}
                  <button className="btn sm" onClick={() => setEditing(t)}>编辑</button>{" "}
                  <button className="btn sm danger" onClick={() => remove(t)}>删除</button>
                </td>
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

      {(creating || editing) && (
        <TaskForm
          sysId={sysId}
          programs={programs}
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

function toRows(task: Task): Row[] {
  return task.preconditions.map((p) => ({
    kind: p.kind,
    name: p.name ?? undefined,
    gitUrl: p.git_url ?? undefined,
    ref: p.ref ?? undefined,
    script: p.script ?? undefined,
  }));
}

function TaskForm({
  sysId,
  programs,
  initial,
  onCancel,
  onDone,
}: {
  sysId: string;
  programs: EvalProgram[];
  initial: Task | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [rows, setRows] = useState<Row[]>(initial ? toRows(initial) : []);
  const [evalProgramId, setEvalProgramId] = useState<string>(initial?.eval_program_id ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function addRow(kind: PreconditionKind) {
    const prog = programs[0];
    const seed: Row =
      kind === "start_system"
        ? { kind, gitUrl: "", ref: "" }
        : kind === "start_eval_program"
          ? { kind, programId: prog?.id, gitUrl: prog?.git_url, ref: prog?.ref }
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
      return {
        kind: row.kind,
        name: row.name || "system",
        git_url: row.gitUrl?.trim() || null,
        ref: row.ref?.trim() || null,
      };
    }
    if (row.kind === "start_eval_program") {
      const prog = programs.find((p) => p.id === row.programId);
      return {
        kind: row.kind,
        name: row.name || (prog ? `eval-${prog.code}` : "eval"),
        git_url: prog?.git_url ?? row.gitUrl ?? null,
        ref: row.ref?.trim() || prog?.ref || null,
      };
    }
    return { kind: row.kind, name: row.name || "自定义脚本", script: row.script };
  }

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("任务名不能为空");
    if (rows.length === 0) return setError("至少添加一条前置条件");
    for (const row of rows) {
      if (row.kind === "start_system" && (!row.gitUrl?.trim() || !row.ref?.trim()))
        return setError("「启动系统」需要 Git 仓库和 ref");
      if (row.kind === "start_eval_program" && !row.programId)
        return setError("「启动评估程序」需要选择评估程序");
    }
    const payload: TaskInput = {
      name: name.trim(),
      system_id: sysId,
      preconditions: rows.map(toPrecondition),
      eval_program_id: evalProgramId || null,
    };
    setBusy(true);
    try {
      if (initial) await api.updateTask(sysId, initial.id, payload);
      else await api.createTask(sysId, payload);
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
          <b>{initial ? "编辑评估任务" : "新建评估任务"}</b>
          <a className="modal-x" onClick={onCancel}>
            ✕
          </a>
        </div>

        <div className="modal-body">
          <div className="fld-row">
            <label className="fld">
              <span>任务名 *</span>
              <input value={name} onChange={(e) => setName(e.target.value)}
                placeholder="chatagent 2.3-eval guide 冒烟" />
            </label>
            <label className="fld">
              <span>评估程序（逐用例评估；空 = 只拉环境不评估）</span>
              <select value={evalProgramId} onChange={(e) => setEvalProgramId(e.target.value)}>
                <option value="">（不评估）</option>
                {programs.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} · code={p.code}</option>
                ))}
              </select>
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
                  <div className="fld-row">
                    <label className="fld">
                      <span>Git 仓库 *（含 .eddplatform.yaml 部署约定）</span>
                      <input className="mono" value={row.gitUrl ?? ""}
                        onChange={(e) => patch(i, { gitUrl: e.target.value })}
                        placeholder="ssh://git@…/chatagent.git 或本地路径" />
                    </label>
                    <label className="fld">
                      <span>ref *（分支/tag/sha）</span>
                      <input className="mono" value={row.ref ?? ""}
                        onChange={(e) => patch(i, { ref: e.target.value })}
                        placeholder="2.3-eval" />
                    </label>
                  </div>
                )}

                {row.kind === "start_eval_program" && (
                  <div className="fld-row">
                    <label className="fld">
                      <span>选择评估程序（评估代码）</span>
                      <select value={row.programId ?? ""} onChange={(e) => {
                        const prog = programs.find((p) => p.id === e.target.value);
                        patch(i, { programId: e.target.value, gitUrl: prog?.git_url, ref: prog?.ref });
                      }}>
                        {programs.length === 0 && <option value="">（无评估程序，先去登记）</option>}
                        {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      </select>
                    </label>
                    <label className="fld">
                      <span>ref（默认用评估程序登记的 ref）</span>
                      <input className="mono" value={row.ref ?? ""}
                        onChange={(e) => patch(i, { ref: e.target.value })}
                        placeholder="main" />
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
            {busy ? "保存中…" : initial ? "保存修改" : "创建任务"}
          </button>
        </div>
      </div>
    </div>
  );
}
