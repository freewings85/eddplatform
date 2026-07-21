import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { CaseRunResult, RunDetail, RunLogLine, RunRecord } from "./types";

function StatusPill({ status }: { status: string }) {
  const kind = status === "succeeded" || status === "passed" ? "ok"
    : status === "running" ? "run"
    : status === "skipped" ? "neutral" : "down";
  return <span className={`pill ${kind}`}>{status}</span>;
}

function CaseStats({ stats }: { stats?: Record<string, number> }) {
  if (!stats || Object.keys(stats).length === 0) return <span className="muted">—</span>;
  const parts: string[] = [];
  if (stats.passed) parts.push(`✓${stats.passed}`);
  if (stats.failed) parts.push(`✗${stats.failed}`);
  if (stats.error) parts.push(`!${stats.error}`);
  if (stats.skipped) parts.push(`→${stats.skipped}`);
  return <span className="mono" title="✓通过 ✗未通过 !评估错误 →不适用">{parts.join(" ")}</span>;
}

export default function Runs({ sysId }: { sysId: string }) {
  const [runs, setRuns] = useState<RunRecord[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const reload = useCallback(() => {
    api.runs(sysId).then(setRuns).catch((e) => setError(String(e)));
  }, [sysId]);
  useEffect(reload, [reload]);

  // 有 running 的 run 时每 5s 轮询刷新
  useEffect(() => {
    if (!runs?.some((r) => r.status === "running")) return;
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
  }, [runs, reload]);

  useEffect(() => {
    if (!openId) return setDetail(null);
    api.run(openId).then(setDetail).catch((e) => setError(String(e)));
  }, [openId, runs]);

  // 过滤（运行 id/任务名/状态/namespace 包含匹配）+ 按创建时间排序 + 分页
  const q = filter.trim().toLowerCase();
  const visible = (runs ?? []).filter((r) => {
    if (!q) return true;
    return [r.id, r.task_name, r.task_id, r.status, r.namespace]
      .join(" ").toLowerCase().includes(q);
  }).sort((a, b) => {
    const cmp = (a.created_at ?? "").localeCompare(b.created_at ?? "");
    return sortAsc ? cmp : -cmp;
  });
  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
  const pageSafe = Math.min(page, pageCount);
  const pageRuns = visible.slice((pageSafe - 1) * pageSize, pageSafe * pageSize);

  return (
    <>
      <h2 className="page">运行记录</h2>
      <p className="sub">一次运行 = 一次 task 执行（experiment）：前置条件拉起环境 → 逐用例评估</p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <input value={filter} style={{ width: 300 }}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
          placeholder="过滤（运行 id / 任务名 / 状态 / namespace）" />
        <select value={sortAsc ? "asc" : "desc"} onChange={(e) => setSortAsc(e.target.value === "asc")}>
          <option value="desc">按创建时间 ↓</option>
          <option value="asc">按创建时间 ↑</option>
        </select>
        <span className="muted count">{visible.length} / {(runs ?? []).length} 条</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>运行</th>
              <th>任务</th>
              <th>状态</th>
              <th>用例结果</th>
              <th>版本标签</th>
              <th>k8s namespace</th>
              <th>创建时间</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {pageRuns.map((r) => (
              <tr key={r.id}>
                <td className="mono">{r.id}</td>
                <td><b>{r.task_name || r.task_id}</b></td>
                <td><StatusPill status={r.status} /></td>
                <td><CaseStats stats={r.case_stats} /></td>
                <td className="mono">
                  {Object.entries(r.versions).map(([k, v]) => `${k}@${v.slice(0, 8)}`).join(" ") || "—"}
                </td>
                <td className="mono sm">{r.namespace || "—"}</td>
                <td className="muted">{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
                <td>
                  <button className="btn sm" onClick={() => setOpenId(openId === r.id ? null : r.id)}>
                    {openId === r.id ? "收起" : "详情"}
                  </button>
                </td>
              </tr>
            ))}
            {runs && runs.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">
                  暂无运行记录 — 在「评估任务」页对任务点「执行」。
                </td>
              </tr>
            )}
            {runs && runs.length > 0 && visible.length === 0 && (
              <tr><td colSpan={8} className="empty">没有匹配过滤条件的运行。</td></tr>
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
        <span className="muted count">第 {pageSafe} / {pageCount} 页</span>
        <button className="btn sm" disabled={pageSafe >= pageCount} onClick={() => setPage(pageSafe + 1)}>下一页 ▶</button>
      </div>

      {detail && <RunDetailView detail={detail} />}
    </>
  );
}

function lineKind(line: string): string {
  if (line.startsWith("$ ")) return "cmd";
  if (line.startsWith("✓") || line.startsWith("=== RUN") && line.includes("succeeded")) return "ok";
  if (line.startsWith("✗") || line.startsWith("!") || line.includes("失败")) return "bad";
  return "";
}

function ConsoleOutput({ runId, running }: { runId: string; running: boolean }) {
  const [lines, setLines] = useState<RunLogLine[]>([]);
  const lastId = useRef(0);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    lastId.current = 0;
    setLines([]);
    let stop = false;
    const pull = () =>
      api.runLogs(runId, lastId.current).then((p) => {
        if (stop || p.lines.length === 0) return;
        lastId.current = p.last_id;
        setLines((prev) => [...prev, ...p.lines]);
      }).catch(() => { /* 日志拉取失败不打扰主界面 */ });
    pull();
    if (!running) return () => { stop = true; };
    const t = setInterval(pull, 2000);
    return () => { stop = true; clearInterval(t); };
  }, [runId, running]);

  // 新行到达时贴底滚动（像 Jenkins 控制台）
  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines]);

  return (
    <>
      <div className="section-title">控制台输出</div>
      <div className="console" ref={boxRef}>
        {lines.map((l) => (
          <div key={l.id} className={`console-line ${lineKind(l.line)}`}>
            <span className="console-ts">{new Date(l.ts).toLocaleTimeString("zh-CN", { hour12: false })}</span>
            <span>{l.line || " "}</span>
          </div>
        ))}
        {lines.length === 0 && (
          <div className="console-empty">
            {running ? "等待执行日志…" : "（该运行没有控制台日志——可能是本功能上线前的历史运行）"}
          </div>
        )}
      </div>
    </>
  );
}

function RunDetailView({ detail }: { detail: RunDetail }) {
  return (
    <>
      <div className="section-title">
        运行 {detail.id} · namespace <span className="mono">{detail.namespace || "—"}</span>
        {detail.workflow_id && <> · workflow <span className="mono">{detail.workflow_id}</span></>}
      </div>
      {detail.detail && <p className="err">{detail.detail}</p>}

      <ConsoleOutput runId={detail.id} running={detail.status === "running"} />

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>前置条件</th>
              <th>名称</th>
              <th>状态</th>
              <th>ref</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            {detail.outcomes.map((o, i) => (
              <tr key={i}>
                <td>{o.kind}</td>
                <td>{o.name}</td>
                <td><StatusPill status={o.status === "ok" ? "succeeded" : "failed"} /></td>
                <td className="mono">{o.ref ? o.ref.slice(0, 12) : "—"}</td>
                <td className="muted">{o.detail || "—"}</td>
              </tr>
            ))}
            {detail.outcomes.length === 0 && (
              <tr><td colSpan={5} className="empty">（无前置条件结果）</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="section-title">逐用例结果（{detail.case_results.length}）</div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>用例</th>
              <th>状态</th>
              <th>分数</th>
              <th>指标</th>
              <th>轨迹</th>
              <th>详情</th>
            </tr>
          </thead>
          <tbody>
            {detail.case_results.map((c: CaseRunResult) => (
              <tr key={c.case_id}>
                <td className="mono">{c.case_id}</td>
                <td><StatusPill status={c.status} /></td>
                <td className="mono">
                  {Object.entries(c.scores).map(([k, v]) => `${k}=${v}`).join(" ") || "—"}
                </td>
                <td className="mono">
                  {Object.entries(c.metrics).map(([k, v]) => `${k}=${v}`).join(" ") || "—"}
                </td>
                <td>
                  {c.trace_url ? (
                    <a href={c.trace_url} target="_blank" rel="noreferrer">Langfuse ↗</a>
                  ) : "—"}
                </td>
                <td className="muted">{c.detail || "—"}</td>
              </tr>
            ))}
            {detail.case_results.length === 0 && (
              <tr>
                <td colSpan={7} className="empty">
                  {detail.status === "running" ? "评估进行中…" : "该运行没有逐用例结果（任务未挂评估程序，或环境未就绪）。"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}
