import { useEffect, useState } from "react";
import { api } from "./api";
import Datasets from "./Datasets";
import EvalPrograms from "./EvalPrograms";
import InfraPrograms from "./InfraPrograms";
import Runs from "./Runs";
import SystemPrograms from "./SystemPrograms";
import Settings from "./Settings";
import Systems from "./Systems";
import Tags from "./Tags";
import Tasks from "./Tasks";

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
  { view: "settings", label: "基础设置", icon: "⚙️" },
];

const SYSTEM_NAV: Nav[] = [
  { view: "system-code", label: "系统程序", icon: "🧩" }, // 被评系统的 git 单元注册
  { view: "eval-programs", label: "评估程序", icon: "🧪" }, // 评估代码 git/版本
  { view: "infra-programs", label: "基础组件", icon: "🧱" }, // 独立部署的 kafka/pg/temporal…
  { view: "datasets", label: "用例库", icon: "📁" }, // 评估数据
  { view: "tags", label: "标签", icon: "🏷️" },
  { view: "tasks", label: "评估任务", icon: "🎯" }, // task + 前置条件
  { view: "runs", label: "运行记录", icon: "🏃" }, // experiment = 运行记录
  { view: "comparison", label: "评估对比", icon: "🔀" },
];

export default function App() {
  const [mode, setMode] = useState<"global" | "system">("global");
  const [view, setView] = useState("overview");
  const [sysId, setSysId] = useState<string | null>(null);
  const [sysName, setSysName] = useState<string>("");

  function openSystem(id: string, name: string) {
    setSysId(id);
    setSysName(name);
    setMode("system");
    setView("system-code");
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
          底座：Langfuse · Temporal · k8s（约定式部署）
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
          {mode === "global" && view === "settings" && <Settings />}
          {mode === "system" && sysId && view === "system-code" && (
            <SystemPrograms sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "eval-programs" && (
            <EvalPrograms sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "infra-programs" && (
            <InfraPrograms sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "datasets" && (
            <Datasets sysId={sysId} />
          )}
          {mode === "system" && sysId && view === "tags" && <Tags sysId={sysId} />}
          {mode === "system" && sysId && view === "tasks" && <Tasks sysId={sysId} />}
          {mode === "system" && sysId && view === "runs" && <Runs sysId={sysId} />}
          {mode === "system" && view === "comparison" && <ComparisonPlaceholder />}
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
  const runs = useData(() => api.runs(), []);
  const running = runs.data?.filter((r) => r.status === "running").length ?? 0;
  return (
    <>
      <h2 className="page">全局概览</h2>
      <p className="sub">跨所有系统的总览 · 选一个系统进入它的工作台</p>
      {error && <p className="err">{error}</p>}
      <div className="stats">
        <Stat k="系统" v={data ? String(data.length) : "…"} />
        <Stat k="运行记录" v={runs.data ? String(runs.data.length) : "…"} />
        <Stat k="进行中" v={runs.data ? String(running) : "…"} />
      </div>
      {data && data.length === 0 && (
        <p className="note">平台是空的 — 去「系统管理」注册第一套被评系统。</p>
      )}
    </>
  );
}

function ComparisonPlaceholder() {
  return (
    <>
      <h2 className="page">评估对比</h2>
      <p className="sub">对比两次运行的逐用例结果（改善 / 回归 / 持平）</p>
      <div className="card">
        <p className="empty" style={{ padding: 24 }}>
          对比视图将随逐用例评估数据的积累重建：同一任务用不同 ref 各执行一次，
          即可对齐逐用例分数做老新对比。当前请先在「运行记录」查看单次结果。
        </p>
      </div>
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
