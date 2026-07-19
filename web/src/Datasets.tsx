import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import CaseForm from "./CaseForm";
import type { Case, CaseInput, Dataset } from "./types";

/** Case → 表单负载（去掉服务端维护的字段）。 */
function toInput(c: Case): CaseInput {
  const { id, created_at, updated_at, ...rest } = c;
  void id;
  void created_at;
  void updated_at;
  return rest;
}

export default function Datasets({ sysId }: { sysId: string }) {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Case | null | undefined>(undefined); // undefined=关闭, null=新增
  const [importing, setImporting] = useState(false);

  const reload = useCallback(() => {
    setError(null);
    api
      .dataset(sysId)
      .then(setDataset)
      .catch((e) => setError(String(e)));
  }, [sysId]);

  useEffect(() => {
    setDataset(null);
    reload();
  }, [reload]);

  const cases = dataset?.cases ?? [];
  const evaluators = dataset?.evaluator_names ?? [];

  async function saveCase(payload: CaseInput) {
    if (editing) await api.updateCase(sysId, editing.id, payload);
    else await api.createCase(sysId, payload);
    setEditing(undefined);
    reload();
  }

  async function removeCase(c: Case) {
    if (!confirm(`删除用例 #${c.id}「${c.name}」？`)) return;
    await api.deleteCase(sysId, c.id).catch((e) => setError(String(e)));
    reload();
  }

  async function toggleEnabled(c: Case) {
    await api.updateCase(sysId, c.id, { ...toInput(c), enabled: !c.enabled }).catch((e) =>
      setError(String(e)),
    );
    reload();
  }

  async function exportJson() {
    const data = await api.exportCases(sysId);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sysId}-cases.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <h2 className="page">用例库</h2>
      <p className="sub">用例有自身版本 + 适用系统版本；一条用例可对应一条线上轨迹（Langfuse）</p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={() => setEditing(null)}>
          ＋ 新增用例
        </button>
        <button className="btn" onClick={() => setImporting(true)}>
          导入
        </button>
        <button className="btn" onClick={() => exportJson().catch((e) => setError(String(e)))}>
          导出
        </button>
        <span className="muted count">{cases.length} 条用例</span>
      </div>

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>用例名</th>
              <th>标签</th>
              <th>用例版本</th>
              <th>适用系统版本</th>
              <th>评估器</th>
              <th>轨迹</th>
              <th>启用</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
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
                <td className="mono sm">{c.evaluator_names.join(" · ") || "—"}</td>
                <td>
                  {c.trace ? (
                    <a
                      className="trace-link"
                      href={c.trace.url ?? undefined}
                      target="_blank"
                      rel="noreferrer"
                      title={c.trace.note ?? c.trace.ref}
                    >
                      🔗 轨迹
                    </a>
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
            {cases.length === 0 && dataset && (
              <tr>
                <td colSpan={9} className="empty">
                  还没有用例，点「新增用例」或「导入」开始。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editing !== undefined && (
        <CaseForm
          initial={editing}
          availableEvaluators={evaluators}
          onCancel={() => setEditing(undefined)}
          onSubmit={saveCase}
        />
      )}

      {importing && (
        <ImportDialog
          sysId={sysId}
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

function ImportDialog({
  sysId,
  onClose,
  onDone,
}: {
  sysId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"append" | "replace">("append");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setError(null);
    let cases: Case[];
    try {
      cases = JSON.parse(text);
      if (!Array.isArray(cases)) throw new Error("需要一个用例数组（JSON array）");
    } catch (e) {
      return setError("JSON 解析失败：" + String(e));
    }
    setBusy(true);
    try {
      const res = await api.importCases(sysId, cases, mode);
      alert(`导入完成：新增 ${res.added}、更新 ${res.updated}，共 ${res.total} 条`);
      onDone();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>导入用例</b>
          <a className="modal-x" onClick={onClose}>
            ✕
          </a>
        </div>
        <div className="modal-body">
          <p className="hint">粘贴一个用例数组（JSON），格式同「导出」。</p>
          <label className="fld">
            <span>用例 JSON</span>
            <textarea
              className="mono"
              rows={10}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder='[{"name": "...", "inputs": {...}}]'
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
