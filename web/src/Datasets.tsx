import { useCallback, useEffect, useState } from "react";
import { useEscape } from "./useEscape";
import { api } from "./api";
import CaseForm from "./CaseForm";
import type { Case, CaseInput, DatasetInfo, System } from "./types";

/** Case → 表单负载（去掉服务端维护的字段）。 */
function toInput(c: Case): CaseInput {
  const { id, created_at, updated_at, ...rest } = c;
  void id;
  void created_at;
  void updated_at;
  return rest;
}

/** 用例是否匹配某标签 p（分层：命中该标签或其任一子孙）。 */
function matchTag(tags: string[], p: string): boolean {
  return tags.some((t) => t === p || t.startsWith(p + "/"));
}

export default function Datasets({ sysId }: { sysId: string }) {
  const [system, setSystem] = useState<System | null>(null);
  const [libraries, setLibraries] = useState<DatasetInfo[]>([]);
  const [gitBusy, setGitBusy] = useState(false);
  const [dsId, setDsId] = useState<string>("");
  const [cases, setCases] = useState<Case[]>([]);
  const [taxonomy, setTaxonomy] = useState<string[]>([]); // 标签树的完整路径
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Case | null | undefined>(undefined); // undefined=关闭, null=新增
  const [importing, setImporting] = useState(false);
  const [libEditing, setLibEditing] = useState<DatasetInfo | null | undefined>(undefined);
  const [activeTags, setActiveTags] = useState<string[]>([]);

  const reload = useCallback(() => {
    setError(null);
    api.system(sysId).then(setSystem).catch(() => {});
    api.datasets(sysId).then((ls) => {
      setLibraries(ls);
      setDsId((cur) => (ls.some((l) => l.id === cur) ? cur : (ls[0]?.id ?? "")));
    }).catch((e) => setError(String(e)));
    api
      .tags(sysId)
      .then((ts) => setTaxonomy(ts.map((t) => t.path)))
      .catch((e) => setError(String(e)));
  }, [sysId]);

  useEffect(() => {
    setActiveTags([]);
    reload();
  }, [reload]);

  useEffect(() => {
    if (!dsId) return setCases([]);
    api.datasetCases(sysId, dsId).then(setCases).catch((e) => setError(String(e)));
  }, [sysId, dsId, libraries]);

  async function importGit() {
    setError(null);
    setGitBusy(true);
    try {
      const r = await api.importCasesGit(sysId);
      const lines = r.libraries.map((l) => `${l.path}: ${l.count} 条`).join("，");
      alert(`已从 git 导入（commit ${r.commit.slice(0, 8)}）：${lines || "没有发现用例文件夹"}`
        + (r.errors?.length ? `\n警告：${r.errors.join("；")}` : ""));
      reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setGitBusy(false);
    }
  }

  async function exportGit() {
    if (!dsId) return;
    setError(null);
    setGitBusy(true);
    try {
      const r = await api.exportDatasetGit(sysId, dsId);
      alert(r.changed
        ? `已导出到 git（commit ${r.commit.slice(0, 8)}，${r.files} 个用例文件）`
        : "内容与 git 一致，无需导出");
      reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setGitBusy(false);
    }
  }

  async function archiveTrace(c: Case) {
    setError(null);
    try {
      const r = await api.archiveTrace(sysId, dsId, c.id);
      alert(`轨迹已归档：${r.observations} 个 observation（随导出进 git，Langfuse 里删了也不丢）`);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  function downloadTrace(c: Case) {
    if (!c.trace?.data) return;
    const blob = new Blob([JSON.stringify(c.trace.data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trace-${c.trace.ref}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function removeLibrary() {
    const lib = libraries.find((l) => l.id === dsId);
    if (!lib) return;
    if (!confirm(`删除用例库「${lib.name}」及其全部用例？（被任务引用时会被拒绝）`)) return;
    try {
      await api.deleteDataset(sysId, lib.id);
      reload();
    } catch (e) {
      setError(String(e));
    }
  }

  // 过滤标签来源：标签树 ∪ 用例上已用的标签（去重、排序）；分层过滤（且）
  const allTags = [...new Set([...taxonomy, ...cases.flatMap((c) => c.tags)])].sort();
  const visible = activeTags.length
    ? cases.filter((c) => activeTags.every((t) => matchTag(c.tags, t)))
    : cases;

  function toggleTag(t: string) {
    setActiveTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));
  }

  async function saveCase(payload: CaseInput) {
    if (editing) await api.updateCase(sysId, dsId, editing.id, payload);
    else await api.createCase(sysId, dsId, payload);
    setEditing(undefined);
    reload();
  }

  async function removeCase(c: Case) {
    if (!confirm(`删除用例 #${c.id}「${c.name}」？`)) return;
    await api.deleteCase(sysId, dsId, c.id).catch((e) => setError(String(e)));
    reload();
  }

  async function toggleEnabled(c: Case) {
    await api.updateCase(sysId, dsId, c.id, { ...toInput(c), enabled: !c.enabled }).catch((e) =>
      setError(String(e)),
    );
    reload();
  }

  async function exportJson() {
    const data = await api.exportCases(sysId, dsId);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sysId}-${dsId}-cases.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <h2 className="page">用例库</h2>
      <p className="sub">用例有自身版本 + 适用系统版本；一条用例可对应一条线上轨迹（Langfuse）</p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <span className="filter-label">用例库</span>
        <select value={dsId} onChange={(e) => setDsId(e.target.value)}>
          {libraries.length === 0 && <option value="">（暂无用例库）</option>}
          {libraries.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
        <button className="btn" onClick={() => setLibEditing(null)}>＋ 新建用例库</button>
        {dsId && (
          <>
            <button className="btn" onClick={() => setLibEditing(libraries.find((l) => l.id === dsId) ?? null)}>
              编辑库
            </button>
            <button className="btn danger" onClick={removeLibrary}>删除库</button>
            <button className="btn primary" onClick={() => setEditing(null)}>
              ＋ 新增用例
            </button>
            <button className="btn" onClick={() => setImporting(true)}>
              导入
            </button>
            <button className="btn" onClick={() => exportJson().catch((e) => setError(String(e)))}>
              导出
            </button>
          </>
        )}
        <span className="muted count">
          {activeTags.length ? `${visible.length} / ${cases.length}` : cases.length} 条用例
        </span>
      </div>

      {system?.cases_git_url && (
        <p className="note">
          用例仓库：<span className="mono">{system.cases_git_url}</span> @ {system.cases_branch || "main"}
          {" · "}
          <button className="btn sm" onClick={importGit} disabled={gitBusy}>
            {gitBusy ? "处理中…" : "⬇ 从 git 导入（全量）"}
          </button>{" "}
          {dsId && (
            <button className="btn sm" onClick={exportGit} disabled={gitBusy}>
              ⬆ 导出当前库到 git
            </button>
          )}
        </p>
      )}
      {libraries.length === 0 && (
        <p className="note">还没有用例库 — {system?.cases_git_url
          ? "点「从 git 导入」拉取用例仓内容，"
          : ""}或点「新建用例库」手动创建（例如按业务线：guide / searchshops / searchcoupons）。</p>
      )}

      {allTags.length > 0 && (
        <div className="filter-bar">
          <span className="filter-label">标签筛选</span>
          <div className="chips">
            {allTags.map((t) => (
              <button
                key={t}
                className={`chip ${activeTags.includes(t) ? "on" : ""}`}
                onClick={() => toggleTag(t)}
              >
                {t}
              </button>
            ))}
          </div>
          {activeTags.length > 0 && (
            <a className="filter-clear" onClick={() => setActiveTags([])}>
              清除筛选
            </a>
          )}
        </div>
      )}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>用例名</th>
              <th>标签</th>
              <th>用例版本</th>
              <th>适用系统版本</th>
              <th>轨迹</th>
              <th>启用</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((c) => (
              <tr key={c.id} className={c.enabled ? "" : "off"}>
                <td>{c.id}</td>
                <td>
                  <b>{c.name}</b>
                  {c.description && <div className="muted sm">{c.description}</div>}
                </td>
                <td>
                  {c.tags.map((t) => (
                    <span key={t} className="tag">
                      {t}
                    </span>
                  ))}
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
                <td>
                  {c.trace ? (
                    <>
                      <a
                        className="trace-link"
                        href={c.trace.url ?? undefined}
                        target="_blank"
                        rel="noreferrer"
                        title={c.trace.note ?? c.trace.ref}
                      >
                        🔗
                      </a>{" "}
                      {c.trace.data ? (
                        <>
                          <span className="tag v" title={`归档于 ${c.trace.archived_at ?? ""}`}>已归档</span>{" "}
                          <a className="trace-link" onClick={() => downloadTrace(c)}>下载</a>
                        </>
                      ) : (
                        <button className="btn sm" onClick={() => archiveTrace(c)}>归档</button>
                      )}
                    </>
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <label className="switch">
                    <input type="checkbox" checked={c.enabled} onChange={() => toggleEnabled(c)} />
                    <span className="slider" />
                  </label>
                </td>
                <td className="row-actions">
                  <button className="btn sm" onClick={() => setEditing(c)}>
                    编辑
                  </button>
                  <button className="btn sm danger" onClick={() => removeCase(c)}>
                    删除
                  </button>
                </td>
              </tr>
            ))}
            {dsId && cases.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">
                  还没有用例，点「新增用例」或「导入」开始。
                </td>
              </tr>
            )}
            {dsId && cases.length > 0 && visible.length === 0 && (
              <tr>
                <td colSpan={8} className="empty">
                  没有同时含全部所选标签的用例。
                  <a className="filter-clear" onClick={() => setActiveTags([])}>
                    清除筛选
                  </a>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editing !== undefined && (
        <CaseForm
          initial={editing}
          availableTags={taxonomy}
          onCancel={() => setEditing(undefined)}
          onSubmit={saveCase}
        />
      )}

      {libEditing !== undefined && (
        <LibraryForm
          sysId={sysId}
          initial={libEditing}
          onCancel={() => setLibEditing(undefined)}
          onDone={(lib) => {
            setLibEditing(undefined);
            setDsId(lib.id);
            reload();
          }}
        />
      )}

      {importing && (
        <ImportDialog
          sysId={sysId}
          dsId={dsId}
          onClose={() => setImporting(false)}
          onDone={() => {
            setImporting(false);
            reload();
          }}
        />
      )}
    </>
  );
}

function LibraryForm({
  sysId,
  initial,
  onCancel,
  onDone,
}: {
  sysId: string;
  initial: DatasetInfo | null;
  onCancel: () => void;
  onDone: (lib: DatasetInfo) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscape(onCancel);

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("用例库名称不能为空");
    setBusy(true);
    try {
      const payload = { name: name.trim(), description: description.trim() || null };
      const lib = initial
        ? await api.updateDataset(sysId, initial.id, payload)
        : await api.createDataset(sysId, payload);
      onDone(lib);
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
          <b>{initial ? "编辑用例库" : "新建用例库"}</b>
          <a className="modal-x" onClick={onCancel}>✕</a>
        </div>
        <div className="modal-body">
          <label className="fld">
            <span>名称 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="guide 用例库" />
          </label>
          <label className="fld">
            <span>说明</span>
            <textarea rows={2} value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="这批用例覆盖什么场景" />
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

function ImportDialog({
  sysId,
  dsId,
  onClose,
  onDone,
}: {
  sysId: string;
  dsId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"append" | "replace">("append");
  const [format, setFormat] = useState<"json" | "yaml">("json");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscape(onClose);

  async function run() {
    setError(null);
    setBusy(true);
    try {
      if (format === "yaml") {
        const res = await api.importCasesYaml(sysId, dsId, text, mode);
        alert(`导入完成：新增 ${res.added}、更新 ${res.updated}，共 ${res.total} 条`);
        onDone();
        return;
      }
      let cases: Case[];
      try {
        cases = JSON.parse(text);
        if (!Array.isArray(cases)) throw new Error("需要一个用例数组（JSON array）");
      } catch (e) {
        setError("JSON 解析失败：" + String(e));
        return;
      }
      const res = await api.importCases(sysId, dsId, cases, mode);
      alert(`导入完成：新增 ${res.added}、更新 ${res.updated}，共 ${res.total} 条`);
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
          <b>导入用例</b>
          <a className="modal-x" onClick={onClose}>
            ✕
          </a>
        </div>
        <div className="modal-body">
          <div className="fld">
            <span>格式</span>
            <div className="chips">
              <label className={`chip ${format === "json" ? "on" : ""}`}>
                <input type="radio" checked={format === "json"} onChange={() => setFormat("json")} />
                JSON（同「导出」格式）
              </label>
              <label className={`chip ${format === "yaml" ? "on" : ""}`}>
                <input type="radio" checked={format === "yaml"} onChange={() => setFormat("yaml")} />
                评估 YAML（group/role/turns/expect）
              </label>
            </div>
          </div>
          <label className="fld">
            <span>{format === "json" ? "用例 JSON" : "评估用例 YAML"}</span>
            <textarea
              className="mono"
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={format === "json"
                ? '[{"name": "...", "inputs": {...}}]'
                : "group: guide\nrole: guide\ncases:\n  - id: guide_intro\n    turns: [{user: \"介绍一下平台\"}]\n    expect: {judge: {rubric: \"介绍准确\"}}"}
            />
          </label>
          <div className="fld">
            <span>模式</span>
            <div className="chips">
              <label className={`chip ${mode === "append" ? "on" : ""}`}>
                <input
                  type="radio"
                  checked={mode === "append"}
                  onChange={() => setMode("append")}
                />
                append（按 id 合并/更新）
              </label>
              <label className={`chip ${mode === "replace" ? "on" : ""}`}>
                <input
                  type="radio"
                  checked={mode === "replace"}
                  onChange={() => setMode("replace")}
                />
                replace（清空重建）
              </label>
            </div>
          </div>
          {error && <p className="err">{error}</p>}
        </div>
        <div className="modal-foot">
          <button className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button className="btn primary" onClick={run} disabled={busy}>
            {busy ? "导入中…" : "导入"}
          </button>
        </div>
      </div>
    </div>
  );
}
