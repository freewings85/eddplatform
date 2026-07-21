import { useCallback, useEffect, useRef, useState } from "react";
import { useEscape } from "./useEscape";
import { api } from "./api";
import type {
  Case,
  DatasetInfo,
  EvalProgram,
  Precondition,
  PreconditionKind,
  SystemProgram,
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
  programId?: string; // 下拉选中的 系统程序/评估程序 注册项
  branch?: string; // 固化的分支
  commit?: string; // 固化的 commit（部署用它）
  branchesHint?: string; // 输入 commit 反查到的分支列表（展示）
  path?: string; // 规范文件夹路径（默认取注册项的目录，可改，随任务固化）
  validationMsg?: string; // 规范校验结果（展示）
  validationOk?: boolean;
  name?: string; // 内部标签（真正的 helm release 名来自单元 chart/Chart.yaml 的 name）
  script?: string; // 旧任务里的自定义脚本（仅保留展示）
  env?: string; // 部署配置（.env.eval 内容；默认取注册项的 env，可改，随任务固化）
};

export default function Tasks({ sysId }: { sysId: string }) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [sysPrograms, setSysPrograms] = useState<SystemProgram[]>([]);
  const [evalPrograms, setEvalPrograms] = useState<EvalProgram[]>([]);
  const [libs, setLibs] = useState<DatasetInfo[]>([]);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<"updated" | "created">("updated");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const reload = useCallback(() => {
    api.tasks(sysId).then(setTasks).catch((e) => setError(String(e)));
    api.systemPrograms(sysId).then(setSysPrograms).catch(() => {});
    api.evalPrograms(sysId).then(setEvalPrograms).catch(() => {});
    api.datasets(sysId).then(setLibs).catch(() => {});
  }, [sysId]);
  useEffect(reload, [reload]);

  // 过滤（任务名/id/前置条件程序名/用例库名 包含匹配）+ 按时间排序 + 分页
  const q = filter.trim().toLowerCase();
  const visibleTasks = tasks.filter((t) => {
    if (!q) return true;
    const lib = libs.find((l) => l.id === t.dataset_id)?.name ?? "";
    const hay = [t.id, t.name, lib, ...t.preconditions.map((p) => p.name ?? "")]
      .join(" ").toLowerCase();
    return hay.includes(q);
  }).sort((a, b) => {
    const key = sortKey === "updated" ? "updated_at" : "created_at";
    return (b[key] ?? "").localeCompare(a[key] ?? "");
  });
  const taskPages = Math.max(1, Math.ceil(visibleTasks.length / pageSize));
  const pageSafe = Math.min(page, taskPages);
  const pageTasks = visibleTasks.slice((pageSafe - 1) * pageSize, pageSafe * pageSize);

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
        评估任务 = <b>启动系统</b> + <b>启动评估程序</b>（下拉选已登记的程序，固化 分支+commit）
        + <b>用例清单</b>。点「执行」= 平台经 Temporal 拉起环境并逐用例分派评估。
      </p>
      {error && <p className="err">{error}</p>}
      {notice && <p className="note">{notice}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setCreating(true)}>
          ＋ 新建评估任务
        </button>
        <input value={filter} style={{ width: 260 }}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
          placeholder="过滤（任务名 / id / 程序名 / 用例库）" />
        <select value={sortKey} onChange={(e) => setSortKey(e.target.value as "updated" | "created")}>
          <option value="updated">按更新时间 ↓</option>
          <option value="created">按创建时间 ↓</option>
        </select>
        <span className="muted count">{visibleTasks.length} / {tasks.length} 个任务</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>任务名</th>
              <th>前置条件（分支@commit）</th>
              <th>评估 workflow</th>
              <th>用例</th>
              <th>创建 / 更新</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pageTasks.map((t) => (
              <tr key={t.id}>
                <td className="mono">{t.id}</td>
                <td>
                  <b>{t.name}</b>
                  {t.destroy_after && <div><span className="tag only">运行后销毁资源</span></div>}
                </td>
                <td>
                  {t.preconditions.map((p, i) => (
                    <span key={i} className="tag">
                      {i + 1}. {p.name || KIND_LABEL[p.kind]}
                      {p.branch ? ` · ${p.branch}` : ""}
                      {p.commit ? `@${p.commit.slice(0, 8)}` : ""}
                    </span>
                  ))}
                </td>
                <td className="mono">
                  {libs.find((l) => l.id === t.dataset_id)?.workflow ?? "—"}
                </td>
                <td>
                  {t.dataset_id
                    ? `${libs.find((l) => l.id === t.dataset_id)?.name ?? t.dataset_id} · ${
                        t.case_ids == null ? "全部" : `勾选 ${t.case_ids.length} 条`}`
                    : "—"}
                </td>
                <td className="muted sm">
                  {t.created_at ? new Date(t.created_at).toLocaleString() : "—"}
                  <div>{t.updated_at ? new Date(t.updated_at).toLocaleString() : "—"}</div>
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
                <td colSpan={7} className="empty">
                  还没有评估任务，点「新建评估任务」开始。
                </td>
              </tr>
            )}
            {tasks.length > 0 && visibleTasks.length === 0 && (
              <tr><td colSpan={7} className="empty">没有匹配过滤条件的任务。</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="pc-add" style={{ marginTop: 6 }}>
        <label className="muted count" style={{ display: "flex", alignItems: "center", gap: 4 }}>
          每页
          <select value={pageSize}
            onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
            {[10, 20, 50].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          条
        </label>
        <button className="btn sm" disabled={pageSafe <= 1} onClick={() => setPage(pageSafe - 1)}>◀ 上一页</button>
        <span className="muted count">第 {pageSafe} / {taskPages} 页</span>
        <button className="btn sm" disabled={pageSafe >= taskPages} onClick={() => setPage(pageSafe + 1)}>下一页 ▶</button>
      </div>

      {(creating || editing) && (
        <TaskForm
          sysId={sysId}
          sysPrograms={sysPrograms}
          evalPrograms={evalPrograms}
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
    programId: p.program_id ?? undefined,
    branch: p.branch ?? undefined,
    commit: p.commit ?? undefined,
    path: p.path ?? undefined,
    name: p.name ?? undefined,
    script: p.script ?? undefined,
    env: p.env ?? undefined,
  }));
}

function TaskForm({
  sysId,
  sysPrograms,
  evalPrograms,
  initial,
  onCancel,
  onDone,
}: {
  sysId: string;
  sysPrograms: SystemProgram[];
  evalPrograms: EvalProgram[];
  initial: Task | null;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [destroyAfter, setDestroyAfter] = useState(initial?.destroy_after ?? false);
  const [rows, setRows] = useState<Row[]>(
    initial
      ? toRows(initial)
      : [
          { kind: "start_system", programId: sysPrograms[0]?.id, name: "system" },
          { kind: "start_eval_program", programId: evalPrograms[0]?.id },
        ],
  );
  const [libraries, setLibraries] = useState<DatasetInfo[]>([]);
  const [datasetId, setDatasetId] = useState<string>(initial?.dataset_id ?? "");
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set(initial?.case_ids ?? []));
  // 旧任务的 case_ids=null 曾表示「全部用例」——编辑时展开成全选，保存后固化为明确清单
  const legacyAll = useRef(initial != null && initial.case_ids == null);
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(8);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<1 | 2>(1);
  useEscape(onCancel);

  useEffect(() => {
    api.datasets(sysId).then((ls) => {
      setLibraries(ls);
      if (!initial) setDatasetId((cur) => cur || (ls[0]?.id ?? ""));
    }).catch(() => {});
    // eslint-disable-next-line
  }, [sysId]);

  useEffect(() => {
    setFilter("");
    setPage(1);
    if (!datasetId) return setCases([]);
    api.datasetCases(sysId, datasetId).then((cs) => {
      setCases(cs);
      if (legacyAll.current) {           // 旧「全部用例」任务：首次加载展开成全选
        legacyAll.current = false;
        setSelected(new Set(cs.map((c) => c.id)));
      }
    }).catch(() => setCases([]));
  }, [sysId, datasetId]);

  // 过滤（id/名称/标签 包含匹配）+ 分页
  const filtered = cases.filter((c) => {
    const q = filter.trim().toLowerCase();
    if (!q) return true;
    return c.name.toLowerCase().includes(q)
      || (c.description ?? "").toLowerCase().includes(q)
      || c.tags.some((t) => t.toLowerCase().includes(q));
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageSafe = Math.min(page, pageCount);
  const pageCases = filtered.slice((pageSafe - 1) * pageSize, pageSafe * pageSize);

  // 注册表是异步加载的：到位后给行和任务级评估程序补默认值
  useEffect(() => {
    setRows((rs) => rs.map((r) => {
      if (r.kind === "start_system" && !r.programId && sysPrograms.length)
        return { ...r, programId: sysPrograms[0].id, path: r.path ?? sysPrograms[0].path };
      if (r.kind === "start_eval_program" && !r.programId && evalPrograms.length)
        return { ...r, programId: evalPrograms[0].id, path: r.path ?? evalPrograms[0].path };
      return r;
    }));
    // eslint-disable-next-line
  }, [sysPrograms, evalPrograms]);

  /** 行对应的注册项（系统程序 或 评估程序）。 */
  function regOf(row: Row): { git_url: string; path: string; label: string;
                              env?: string | null } | null {
    if (row.kind === "start_system") {
      const p = sysPrograms.find((x) => x.id === row.programId);
      return p ? { git_url: p.git_url, path: p.path, label: p.name, env: p.env } : null;
    }
    if (row.kind === "start_eval_program") {
      const p = evalPrograms.find((x) => x.id === row.programId);
      return p ? { git_url: p.git_url, path: p.path, label: p.name, env: p.env } : null;
    }
    return null;
  }

  function addRow(kind: PreconditionKind) {
    const seed: Row =
      kind === "start_system"
        ? { kind, programId: sysPrograms[0]?.id }
        : { kind, programId: evalPrograms[0]?.id };
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

  async function fetchLatestCommit(i: number) {
    const row = rows[i];
    const reg = regOf(row);
    setError(null);
    if (!reg) return setError("先选择程序");
    if (!row.branch?.trim()) return setError("先填分支名，再点「获取最新 commit」");
    try {
      const r = await api.resolveBranch(reg.git_url, row.branch.trim());
      patch(i, { commit: r.commit, branchesHint: undefined });
    } catch (e) {
      setError(String(e));
    }
  }

  async function verifyCommit(i: number) {
    const row = rows[i];
    const reg = regOf(row);
    setError(null);
    if (!reg) return setError("先选择程序");
    if (!row.commit?.trim()) return setError("先填 commit id，再点「校验」");
    try {
      const r = await api.resolveCommit(reg.git_url, row.commit.trim());
      patch(i, {
        commit: r.commit,
        branch: r.branches[0] ?? row.branch,
        branchesHint: r.branches.join(", "),
      });
    } catch (e) {
      setError(String(e));
    }
  }

  async function validateUnit(i: number) {
    const row = rows[i];
    const reg = regOf(row);
    setError(null);
    if (!reg) return setError("先选择程序");
    const ref = row.commit?.trim() || row.branch?.trim();
    if (!ref) return setError("先固化 分支/commit，再校验规范文件夹");
    try {
      const r = await api.validateUnit(reg.git_url, ref, row.path?.trim() || ".");
      patch(i, {
        validationOk: r.ok,
        validationMsg: r.ok
          ? `✓ 规范校验通过：release 名=${r.name} · 服务=[${r.services.join(", ")}]`
          : `✗ ${r.errors.join("；")}`,
      });
    } catch (e) {
      patch(i, { validationOk: false, validationMsg: String(e) });
    }
  }

  function toggleCase(id: string) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toPrecondition(row: Row): Precondition {
    const reg = regOf(row);
    if (row.kind === "custom_script")
      return { kind: row.kind, name: row.name || "自定义脚本", script: row.script };
    // name 只是内部回退标签；真正的 helm release 名来自单元 chart/Chart.yaml 的 name
    const fallback = row.kind === "start_system" ? "system" : "eval";
    const env = row.env ?? reg?.env ?? "";
    return {
      kind: row.kind,
      name: (row.name ?? "").trim() || fallback,
      program_id: row.programId ?? null,
      git_url: reg?.git_url ?? null,
      path: row.path?.trim() || reg?.path || ".",
      branch: row.branch?.trim() || null,
      commit: row.commit?.trim() || null,
      env: env.trim() ? env : null,
    };
  }

  function step1Error(): string | null {
    if (!name.trim()) return "任务名不能为空";
    if (rows.length === 0) return "至少保留一条前置条件";
    for (const row of rows) {
      if (row.kind === "custom_script") continue;
      if (!row.programId || !regOf(row))
        return `「${KIND_LABEL[row.kind]}」需要先在对应页面登记程序，再下拉选择`;
      if (!row.branch?.trim() || !row.commit?.trim())
        return `「${KIND_LABEL[row.kind]} · ${regOf(row)?.label}」需要固化 分支+commit：`
          + "填分支点「获取最新 commit」，或填 commit 点「校验」";
    }
    return null;
  }

  function goNext() {
    setError(null);
    const err = step1Error();
    if (err) return setError(err);
    setStep(2);
  }

  async function submit() {
    setError(null);
    const err = step1Error();
    if (err) {
      setStep(1);
      return setError(err);
    }
    if (datasetId && selected.size === 0)
      return setError("至少勾选一条用例（可用「全选」）");
    const payload: TaskInput = {
      name: name.trim(),
      system_id: sysId,
      preconditions: rows.map(toPrecondition),
      dataset_id: datasetId || null,
      case_ids: [...selected],
      destroy_after: destroyAfter,
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
    <div className="modal-backdrop">
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>
            {initial ? "编辑评估任务" : "新建评估任务"}
            <span className="muted"> · 步骤 {step}/2 · {step === 1 ? "基本信息与前置条件" : "用例清单"}</span>
          </b>
          <a className="modal-x" onClick={onCancel}>
            ✕
          </a>
        </div>

        <div className="modal-body">
          {step === 1 && (<>
          <label className="fld">
            <span>任务名 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="chatagent 2.3-eval guide 冒烟" />
          </label>

          <label className="fld chk">
            <input type="checkbox" checked={destroyAfter}
              onChange={(e) => setDestroyAfter(e.target.checked)} />
            <span>运行结束后销毁本次创建的 k8s 资源（整个一次性 namespace：pod/service/configmap）；
              不勾 = 保留现场供排查，需手动清理</span>
          </label>

          <div className="fld">
            <span>前置条件（按顺序执行；默认 = 启动系统 → 启动评估程序）</span>
            <div className="pc-add">
              <button className="btn sm" onClick={() => addRow("start_system")}>＋ 启动系统</button>
              <button className="btn sm" onClick={() => addRow("start_eval_program")}>＋ 启动评估程序</button>
            </div>

            {rows.length === 0 && <i className="muted">还没有前置条件，用上面的按钮添加。</i>}
            {rows.map((row, i) => {
              const reg = regOf(row);
              const programs: { id: string; name: string }[] =
                row.kind === "start_system" ? sysPrograms : evalPrograms;
              return (
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

                  {row.kind !== "custom_script" && (
                    <>
                      {/* 区块 1：git 相关 —— 下拉选注册项 + 固化 分支/commit */}
                      <div className="pc-block">
                        <div className="pc-block-title">Git 设置</div>
                        <div className="fld-row">
                          <label className="fld">
                            <span>{row.kind === "start_system" ? "系统程序" : "评估程序"} *</span>
                            <select value={row.programId ?? ""}
                              onChange={(e) => patch(i, { programId: e.target.value,
                                branch: undefined, commit: undefined, branchesHint: undefined })}>
                              {programs.length === 0 && (
                                <option value="">
                                  {row.kind === "start_system"
                                    ? "（无系统程序，先去「系统程序」页登记）"
                                    : "（无评估程序，先去「评估程序」页登记）"}
                                </option>
                              )}
                              {programs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                            </select>
                          </label>
                          <label className="fld">
                            <span>Git 仓库（来自登记项）</span>
                            <input className="mono" readOnly
                              value={reg ? `${reg.git_url}${reg.path && reg.path !== "." ? `  ·  ${reg.path}` : ""}` : ""} />
                          </label>
                        </div>
                        <div className="fld-row">
                          <label className="fld">
                            <span>分支</span>
                            <div className="inline-btn">
                              <input className="mono" value={row.branch ?? ""}
                                onChange={(e) => patch(i, { branch: e.target.value, commit: undefined })}
                                placeholder="2.3-eval" />
                              <button className="btn sm" onClick={() => fetchLatestCommit(i)}>
                                获取最新 commit
                              </button>
                            </div>
                          </label>
                          <label className="fld">
                            <span>commit id（固化；部署用它）</span>
                            <div className="inline-btn">
                              <input className="mono" value={row.commit ?? ""}
                                onChange={(e) => patch(i, { commit: e.target.value, branchesHint: undefined })}
                                placeholder="点左侧按钮获取，或直接输入后校验" />
                              <button className="btn sm" onClick={() => verifyCommit(i)}>校验</button>
                            </div>
                          </label>
                        </div>
                        {row.branchesHint && (
                          <p className="hint">该 commit 属于分支：{row.branchesHint}</p>
                        )}
                      </div>

                      {/* 区块 2：部署设置 —— 规范文件夹路径 + 校验 + 下载示例 */}
                      <div className="pc-block">
                        <div className="pc-block-title">
                          部署设置
                          <a className="btn sm" style={{ marginLeft: 8 }}
                            href="/api/edd-unit-template" download>
                            ⬇ 下载规范示例（edd_helm 文件夹）
                          </a>
                        </div>
                        <label className="fld">
                          <span>规范文件夹路径（仓库内含 build.sh + chart/ 的目录）</span>
                          <div className="inline-btn">
                            <input className="mono" value={row.path ?? reg?.path ?? "."}
                              onChange={(e) => patch(i, { path: e.target.value,
                                validationMsg: undefined, validationOk: undefined })}
                              placeholder="edd_helm（默认 . = 仓库根）" />
                            <button className="btn sm" onClick={() => validateUnit(i)}>校验规范</button>
                          </div>
                        </label>
                        {row.validationMsg && (
                          <p className={row.validationOk ? "note" : "err"}
                            style={{ margin: 0 }}>{row.validationMsg}</p>
                        )}
                      </div>

                      {/* 区块 3：部署配置 —— 动态生成 .env.eval 注入 chart */}
                      <div className="pc-block">
                        <div className="pc-block-title">部署配置（.env.eval，随任务固化）</div>
                        <label className="fld">
                          <span>KEY=VALUE 每行；部署时以 eddEnv/eddEnvVars 传入 chart（挂载文件或 envFrom）</span>
                          <textarea className="mono" rows={3}
                            value={row.env ?? reg?.env ?? ""}
                            onChange={(e) => patch(i, { env: e.target.value })}
                            placeholder={"LITELLM_BASE_URL=https://…\nLITELLM_KEY=sk-…"} />
                        </label>
                      </div>
                    </>
                  )}

                  {row.kind === "custom_script" && (
                    <label className="fld">
                      <span>脚本（旧任务保留字段）</span>
                      <textarea className="mono" rows={3} value={row.script ?? ""}
                        onChange={(e) => patch(i, { script: e.target.value })} />
                    </label>
                  )}
                </div>
              );
            })}
          </div>

          </>)}

          {step === 2 && (
          <div className="fld">
            <div className="fld-row">
              <label className="fld">
                <span>用例库 *</span>
                <select value={datasetId} onChange={(e) => {
                  setDatasetId(e.target.value);
                  setSelected(new Set());
                }}>
                  <option value="">（不跑用例，只拉环境）</option>
                  {libraries.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
              </label>
              {datasetId && (
                <label className="fld">
                  <span>过滤（按 id / 名称 / 标签）</span>
                  <input value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1); }}
                    placeholder="输入关键字过滤用例" />
                </label>
              )}
            </div>
            {libraries.length === 0 && (
              <i className="muted">还没有用例库 — 先去「用例库」页新建并导入用例。</i>
            )}

            {datasetId && (<>
            <div className="pc-add">
              <button className="btn sm"
                onClick={() => setSelected(new Set(filtered.map((c) => c.id)))}>
                全选{filter.trim() ? "（过滤结果）" : ""}
              </button>
              <button className="btn sm" onClick={() => setSelected(new Set())}>清空</button>
              <span className="muted count">
                已选 {selected.size} / {cases.length}
                {filter.trim() ? ` · 过滤后 ${filtered.length} 条` : ""}
              </span>
            </div>
            <div className="case-picklist">
              {pageCases.map((c) => (
                <label key={c.id} className={`case-pick ${selected.has(c.id) ? "on" : ""}`}>
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggleCase(c.id)}
                  />
                  <span className="mono">{c.name}</span>
                  {c.description && <span className="muted sm">{c.description}</span>}
                  {c.tags.map((t) => <span key={t} className="tag">{t}</span>)}
                  {!c.enabled && <span className="tag">已禁用</span>}
                </label>
              ))}
              {filtered.length === 0 && (
                <i className="muted" style={{ padding: 10, display: "block" }}>
                  {cases.length === 0 ? "该用例库是空的 — 去「用例库」页导入。" : "没有匹配过滤条件的用例。"}
                </i>
              )}
            </div>
            <div className="pc-add" style={{ marginTop: 6 }}>
              <label className="muted count" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                每页
                <select value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
                  {[8, 20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                条
              </label>
              <button className="btn sm" disabled={pageSafe <= 1}
                onClick={() => setPage(pageSafe - 1)}>◀ 上一页</button>
              <span className="muted count">第 {pageSafe} / {pageCount} 页</span>
              <button className="btn sm" disabled={pageSafe >= pageCount}
                onClick={() => setPage(pageSafe + 1)}>下一页 ▶</button>
            </div>
            </>)}
          </div>
          )}

          {error && <p className="err">{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={busy}>取消</button>
          {step === 2 && (
            <button className="btn" onClick={() => { setError(null); setStep(1); }} disabled={busy}>
              上一步
            </button>
          )}
          {step === 1 ? (
            <button className="btn primary" onClick={goNext}>下一步</button>
          ) : (
            <button className="btn primary" onClick={submit} disabled={busy}>
              {busy ? "保存中…" : initial ? "保存修改" : "创建任务"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
