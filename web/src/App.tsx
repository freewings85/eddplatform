import { useEffect, useState } from "react";
import { api } from "./api";
import type {
  Comparison,
  Dataset,
  EvaluatorDef,
  Evaluation,
  Requirement,
  RequirementRollup,
  RunRecord,
  System,
  SystemVersion,
} from "./types";

/** 极简数据加载 hook。 */
function useData<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    loader()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line
  }, deps);
  return { data, error };
}

type Nav = { view: string; label: string; icon: string };

const GLOBAL_NAV: Nav[] = [
  { view: "overview", label: "全局概览", icon: "📊" },
  { view: "systems", label: "系统管理", icon: "🗂️" },
];

const SYSTEM_NAV: Nav[] = [
  { view: "sys-overview", label: "系统概览", icon: "🏠" },
  { view: "requirements", label: "需求", icon: "📌" },
  { view: "datasets", label: "用例库", icon: "📁" },
  { view: "evaluators", label: "评估器", icon: "⚗️" },
  { view: "runs", label: "运行记录", icon: "🏃" },
  { view: "evaluations", label: "评估", icon: "✅" },
  { view: "comparison", label: "评估对比", icon: "🔀" },
];

function Pill({ kind, children }: { kind?: string; children: React.ReactNode }) {
  return <span className={`pill ${kind ?? "neutral"}`}>{children}</span>;
}

export default function App() {
  const [mode, setMode] = useState<"global" | "system">("global");
  const [view, setView] = useState("overview");
  const [sysId, setSysId] = useState<string | null>(null);
  const [sysName, setSysName] = useState<string>("");

  function openSystem(id: string, name: string) {
    setSysId(id);
    setSysName(name);
    setMode("system");
    setView("sys-overview");
  }
  function backToGlobal() {
    setMode("global");
    setView("systems");
    setSysId(null);
  }

  const nav = mode === "system" ? SYSTEM_NAV : GLOBAL_NAV;

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="logo">E</div>
          <div>
            <b>EddPlatform</b>
            <small>评估驱动研发</small>
          </div>
        </div>
        {mode === "system" && (
          <>
            <a className="backglobal" onClick={backToGlobal}>
              ← 返回全局
            </a>
            <div className="syspick">
              当前系统
              <b>{sysName}</b>
            </div>
          </>
        )}
        <nav className="nav">
          {nav.map((n) => (
            <a
              key={n.view}
              className={view === n.view ? "active" : ""}
              onClick={() => setView(n.view)}
            >
              {n.icon} {n.label}
            </a>
          ))}
        </nav>
        <div className="side-foot">
          底座：Langfuse · Garden · Temporal · Harbor · Backstage
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="crumb">
            {mode === "system" ? (
              <>
                全局 <span>/ {sysName} / {navLabel(nav, view)}</span>
              </>
            ) : (
              navLabel(nav, view)
            )}
          </div>
        </div>
        <div className="content">
          {mode === "global" && view === "overview" && <Overview />}
          {mode === "global" && view === "systems" && (
            <Systems onOpen={openSystem} />
          )}
          {mode === "system" && sysId && view === "sys-overview" && (
            <SysOverview sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "requirements" && (
            <Requirements sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "datasets" && (
            <Datasets sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "evaluators" && (
            <Evaluators sysId={sysId} />
          )}
          {mode === "system" && view === "runs" && <Runs />}
          {mode === "system" && view === "evaluations" && <Evaluations />}
          {mode === "system" && view === "comparison" && <ComparisonView />}
        </div>
      </main>
    </div>
  );
}

function navLabel(nav: Nav[], view: string): string {
  return nav.find((n) => n.view === view)?.label ?? "";
}

function Overview() {
  const { data, error } = useData(api.systems, []);
  return (
    <>
      <h2 className="page">全局概览</h2>
      <p className="sub">跨所有系统的总览 · 选一个系统进入它的工作台</p>
      {error && <p className="err">{error}</p>}
      <div className="stats">
        <Stat k="系统" v={data ? String(data.length) : "…"} />
        <Stat k="进行中评估" v="1" />
        <Stat k="运行中沙箱" v="3" />
        <Stat k="待处理回归" v="5" />
      </div>
    </>
  );
}

function Systems({ onOpen }: { onOpen: (id: string, name: string) => void }) {
  const { data, error } = useData(api.systems, []);
  return (
    <>
      <h2 className="page">系统管理</h2>
      <p className="sub">平台支持多套系统；每套系统管理自己的模块与各模块的 Git</p>
      {error && <p className="err">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>系统</th>
              <th>模块数</th>
              <th>负责人</th>
              <th>生产版本</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((s) => (
              <tr key={s.id} className="click" onClick={() => onOpen(s.id, s.name)}>
                <td>
                  <b>{s.name}</b>
                </td>
                <td>{s.modules.length}</td>
                <td>{s.owner}</td>
                <td>{s.prod_version}</td>
                <td>
                  <button className="btn sm">管理</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SysOverview({ sysId }: { sysId: string }) {
  const sys = useData(() => api.system(sysId), [sysId]);
  const versions = useData(() => api.versions(sysId), [sysId]);
  return (
    <>
      <h2 className="page">{sys.data?.name ?? "系统"}</h2>
      <p className="sub">模块 &amp; Git · 系统版本</p>

      <div className="section-title">模块（{sys.data?.modules.length ?? 0}）</div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>模块</th>
              <th>Git 仓库</th>
              <th>分支</th>
              <th>镜像</th>
              <th>生产 tag</th>
              <th>负责人</th>
            </tr>
          </thead>
          <tbody>
            {(sys.data?.modules ?? []).map((m) => (
              <tr key={m.name}>
                <td>
                  <b>{m.name}</b>
                </td>
                <td className="mono">{m.git_url}</td>
                <td>
                  <span className="tag">{m.branch}</span>
                </td>
                <td className="mono">{m.image}</td>
                <td className="mono">{m.prod_tag}</td>
                <td>{m.owner}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="section-title">系统版本</div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>版本</th>
              <th>模块组合</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {(versions.data ?? []).map((v: SystemVersion) => (
              <tr key={v.id}>
                <td>
                  <b>{v.label}</b>
                </td>
                <td className="muted">
                  {Object.keys(v.module_pins).length} 模块
                  {v.note ? ` · ${v.note}` : ""}
                </td>
                <td>
                  <Pill kind={v.status === "production" ? "ok" : undefined}>
                    {v.status}
                  </Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Datasets({ sysId }: { sysId: string }) {
  const { data, error } = useData<Dataset>(() => api.dataset(sysId), [sysId]);
  return (
    <>
      <h2 className="page">用例库</h2>
      <p className="sub">用例有自身版本 + 适用系统版本（多版本通用 / 某版本专属）</p>
      {error && <p className="err">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>用例名</th>
              <th>需求</th>
              <th>用例版本</th>
              <th>适用系统版本</th>
              <th>评估器</th>
            </tr>
          </thead>
          <tbody>
            {(data?.cases ?? []).map((c) => (
              <tr key={c.id}>
                <td>{c.id}</td>
                <td>{c.name}</td>
                <td>
                  {c.requirement_ids.length === 0 ? (
                    <span className="muted">—</span>
                  ) : (
                    c.requirement_ids.map((r) => (
                      <span key={r} className="tag">
                        {r}
                      </span>
                    ))
                  )}
                </td>
                <td>
                  <span className="tag v">{c.case_version}</span>
                </td>
                <td>
                  {c.applicable_versions.length === 0 ? (
                    <span className="tag">全部版本</span>
                  ) : c.applicable_versions.length === 1 ? (
                    <span className="tag only">仅 {c.applicable_versions[0]} 专属</span>
                  ) : (
                    c.applicable_versions.map((v) => (
                      <span key={v} className="tag">
                        {v}
                      </span>
                    ))
                  )}
                </td>
                <td className="mono">{c.evaluator_names.join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Evaluators({ sysId }: { sysId: string }) {
  const { data } = useData<EvaluatorDef[]>(() => api.evaluators(sysId), [sysId]);
  return (
    <>
      <h2 className="page">评估器</h2>
      <p className="sub">引擎复用 Langfuse（框架无关）；code + LLM-judge</p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>评估器</th>
              <th>定义方式</th>
              <th>读取</th>
              <th>输出</th>
              <th>阈值</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((e) => (
              <tr key={e.name}>
                <td>
                  <b>{e.name}</b>
                </td>
                <td>
                  <Pill kind={e.kind === "llm_judge" ? "new" : undefined}>
                    {e.kind}
                  </Pill>
                </td>
                <td className="mono">{e.input_field}</td>
                <td>{e.output_type}</td>
                <td className="muted">{e.threshold ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Runs() {
  const { data } = useData<RunRecord[]>(api.runs, []);
  return (
    <>
      <h2 className="page">运行记录</h2>
      <p className="sub">一次运行 = 拉起环境 → 跑（日志/轨迹）；可单独运行或由评估产生</p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>运行</th>
              <th>类型</th>
              <th>版本</th>
              <th>状态</th>
              <th>时长</th>
              <th>关联评估</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => (
              <tr key={r.id}>
                <td className="mono">#{r.id}</td>
                <td>
                  <Pill kind={r.type === "evaluation" ? "new" : undefined}>
                    {r.type === "evaluation" ? "评估运行" : "单独运行"}
                  </Pill>
                </td>
                <td>{r.version_label}</td>
                <td>
                  <Pill kind={r.status === "completed" ? "ok" : "run"}>
                    {r.status}
                  </Pill>
                </td>
                <td>{r.duration_s ? `${Math.round(r.duration_s)}s` : "—"}</td>
                <td className="muted">{r.eval_id ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Evaluations() {
  const { data } = useData<Evaluation[]>(api.evaluations, []);
  return (
    <>
      <h2 className="page">评估</h2>
      <p className="sub">评估任务 = 系统版本 × 用例集 × 环境 → 必带运行记录 → 结果</p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>评估任务</th>
              <th>版本</th>
              <th>状态</th>
              <th>结果</th>
              <th>运行</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((e) => (
              <tr key={e.id}>
                <td>
                  <b>{e.name}</b>
                </td>
                <td>{e.version_label}</td>
                <td>
                  <Pill kind={e.status === "completed" ? "ok" : "run"}>
                    {e.status}
                  </Pill>
                </td>
                <td>
                  {e.result ? `通过 ${Math.round(e.result.pass_rate * 100)}%` : "—"}
                </td>
                <td className="mono">{e.run_id ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ComparisonView() {
  const { data } = useData<Comparison>(api.comparison, []);
  return (
    <>
      <h2 className="page">评估对比</h2>
      <p className="sub">对比两个评估结果（只统计两版本都适用的用例）</p>
      {data && (
        <>
          <p className="note">
            适用用例 <b>{data.applicable_cases}</b> · 改善{" "}
            <b className="up">{data.improved}</b> · 回归{" "}
            <b className="down">{data.regressed}</b> · 持平 {data.unchanged}
          </p>
          <div className="card">
            <table>
              <thead>
                <tr>
                  <th>指标</th>
                  <th>基线</th>
                  <th>候选</th>
                  <th>变化</th>
                </tr>
              </thead>
              <tbody>
                {data.metrics.map((m) => {
                  const delta = m.candidate - m.baseline;
                  return (
                    <tr key={m.metric}>
                      <td>{m.metric}</td>
                      <td>{m.baseline}</td>
                      <td>
                        <b>{m.candidate}</b>
                      </td>
                      <td className={delta >= 0 ? "up" : "down"}>
                        {delta >= 0 ? "▲" : "▼"} {delta.toFixed(3)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {data.by_requirement.length > 0 && (
            <>
              <div className="section-title">按需求</div>
              <div className="card">
                <table>
                  <thead>
                    <tr>
                      <th>需求</th>
                      <th>Jira</th>
                      <th>v1 基线</th>
                      <th>v2 候选</th>
                      <th>结论</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_requirement.map((r) => {
                      const v = rollupVerdict(r);
                      return (
                        <tr key={r.requirement_id}>
                          <td>
                            <b>{r.requirement_id}</b> {r.title}
                          </td>
                          <td className="mono">{r.external_key ?? "—"}</td>
                          <td className="muted">
                            {r.baseline_passed}/{r.total_cases}
                          </td>
                          <td>
                            <b>
                              {r.candidate_passed}/{r.total_cases}
                            </b>
                          </td>
                          <td>
                            <Pill kind={v.kind}>{v.text}</Pill>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="hint">
                达标 = 该需求验收用例在候选版本全部通过（用例级结果按 requirement_ids 卷到需求级）。
              </p>
            </>
          )}
          <p className="hint">数据来自 FastAPI /api/comparison（示例）；生产接 Langfuse dataset run 对比。</p>
        </>
      )}
    </>
  );
}

/** 由 rollup 的通过数派生达标结论（API 不序列化 property，前端本地判定）。 */
function rollupVerdict(r: RequirementRollup): { text: string; kind?: string } {
  const bm = r.total_cases > 0 && r.baseline_passed === r.total_cases;
  const cm = r.total_cases > 0 && r.candidate_passed === r.total_cases;
  if (cm && !bm) return { text: "✅ 达标", kind: "ok" };
  if (bm && !cm) return { text: "❌ 回归", kind: "bad" };
  if (bm && cm) return { text: "保持", kind: undefined };
  return { text: "仍未达标", kind: undefined };
}

function Requirements({ sysId }: { sysId: string }) {
  const { data, error } = useData<Requirement[]>(
    () => api.requirements(sysId),
    [sysId],
  );
  const cmp = useData<Comparison>(api.comparison, []);
  const rollupById = new Map(
    (cmp.data?.by_requirement ?? []).map((r) => [r.requirement_id, r]),
  );
  return (
    <>
      <h2 className="page">需求</h2>
      <p className="sub">
        追溯锚点：详情在 Jira（唯一真相源），平台把需求挂到验收用例 &amp; 系统版本，评估对比按需求汇总达标
      </p>
      {error && <p className="err">{error}</p>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>需求</th>
              <th>Jira 号</th>
              <th>候选版本 (v2) 达标</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((r) => {
              const ro = rollupById.get(r.id);
              const v = ro ? rollupVerdict(ro) : null;
              return (
                <tr key={r.id}>
                  <td>
                    <b>{r.id}</b> {r.title}
                  </td>
                  <td className="mono">
                    {r.external_url ? (
                      <a href={r.external_url} target="_blank" rel="noopener">
                        {r.external_key} ↗
                      </a>
                    ) : (
                      r.external_key ?? "—"
                    )}
                  </td>
                  <td>
                    {ro && v ? (
                      <>
                        <Pill kind={v.kind}>{v.text}</Pill>{" "}
                        <span className="muted">
                          ({ro.candidate_passed}/{ro.total_cases})
                        </span>
                      </>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="hint">
        "达标" = 验收用例在候选版本全部通过，由评估对比实时算出，不写回 Jira。Jira 状态与达标正交。
      </p>
    </>
  );
}

function Stat({ k, v }: { k: string; v: string }) {
  return (
    <div className="card stat">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}
