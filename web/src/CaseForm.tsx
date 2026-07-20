import { useState } from "react";
import { api } from "./api";
import { useEscape } from "./useEscape";
import type { Case, CaseInput } from "./types";

type Props = {
  sysId: string;
  dsId: string;
  initial?: Case | null; // 有 = 编辑，无 = 新增
  availableTags: string[]; // 标签树的完整路径（父在子前）
  onCancel: () => void;
  onSubmit: (payload: CaseInput) => Promise<void>;
};

export default function CaseForm({
  sysId,
  dsId,
  initial,
  availableTags,
  onCancel,
  onSubmit,
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [tags, setTags] = useState<string[]>(initial?.tags ?? []);
  const [tagOpen, setTagOpen] = useState(false);
  const [traceRef, setTraceRef] = useState(initial?.trace?.ref ?? "");
  const [traceUrl, setTraceUrl] = useState(initial?.trace?.url ?? "");
  const [traceNote, setTraceNote] = useState(initial?.trace?.note ?? "");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEscape(onCancel);

  function toggleTag(t: string) {
    setTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));
  }

  // 标签树 ∪ 当前用例已用的标签（保留不在树里的历史标签），父在子前
  const knownTags = [...new Set([...availableTags, ...tags])].sort();

  async function restoreToLangfuse() {
    if (!initial) return;
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const r = await api.restoreTrace(sysId, dsId, initial.id);
      setTraceUrl(r.url);   // 导入成功 → URL 同步回链接框
      setNotice(`已导入 Langfuse（${r.events} 个事件），URL 已回填——记得点「保存」`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("用例名不能为空");

    const payload: CaseInput = {
      name: name.trim(),
      description: description.trim() || null,
      // 表单不编辑的字段原样保留（YAML 导入/轨迹导入填充的内容不被清掉）
      inputs: initial?.inputs ?? "",
      expected_output: initial?.expected_output ?? null,
      metadata: initial?.metadata ?? {},
      applicable_versions: initial?.applicable_versions ?? [],
      author: initial?.author ?? null,
      tags,
      case_version: initial?.case_version ?? "v1",
      trace: traceRef.trim()
        ? { ref: traceRef.trim(), url: traceUrl.trim() || null, note: traceNote.trim() || null }
        : null,
      enabled,
    };

    setBusy(true);
    try {
      await onSubmit(payload);
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
          <b>{initial ? `编辑用例 #${initial.id}` : "新增用例"}</b>
          <a className="modal-x" onClick={onCancel}>
            ✕
          </a>
        </div>

        <div className="modal-body">
          <label className="fld">
            <span>用例名 *</span>
            <input value={name} onChange={(e) => setName(e.target.value)}
              placeholder="guide 场景 · 平台介绍" />
          </label>

          <label className="fld">
            <span>描述</span>
            <textarea
              rows={4}
              value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="这条用例在测什么、判定关注点是什么"
            />
          </label>

          <div className="fld">
            <span>标签（标签树多选；树在「标签」页维护）</span>
            <div className="tagselect">
              <div className="tagselect-box" onClick={() => setTagOpen((o) => !o)}>
                {tags.length === 0 && <span className="muted">点击选择标签…</span>}
                {tags.map((t) => (
                  <span key={t} className="tag">
                    {t}
                    <a
                      className="tag-x"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleTag(t);
                      }}
                    >
                      ×
                    </a>
                  </span>
                ))}
                <span className="tagselect-caret">{tagOpen ? "▴" : "▾"}</span>
              </div>
              {tagOpen && (
                <div className="tagselect-panel">
                  {knownTags.length === 0 && (
                    <i className="muted" style={{ padding: 8, display: "block" }}>
                      该系统暂无标签 — 去「标签」页新建标签树。
                    </i>
                  )}
                  {knownTags.map((t) => {
                    const depth = t.split("/").length - 1;
                    const leaf = t.split("/").pop();
                    return (
                      <label
                        key={t}
                        className={`tagselect-item ${tags.includes(t) ? "on" : ""}`}
                        style={{ paddingLeft: 10 + depth * 18 }}
                      >
                        <input
                          type="checkbox"
                          checked={tags.includes(t)}
                          onChange={() => toggleTag(t)}
                        />
                        {leaf}
                        {depth > 0 && <span className="muted sm"> {t}</span>}
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          <fieldset className="fld trace-box">
            <legend>对应轨迹（Langfuse，可空）</legend>
            <div className="fld-row">
              <label className="fld">
                <span>trace id</span>
                <input value={traceRef} onChange={(e) => setTraceRef(e.target.value)} placeholder="trace-abc123" />
              </label>
              <label className="fld">
                <span>链接 URL</span>
                <div className="inline-btn">
                  <input value={traceUrl ?? ""} onChange={(e) => setTraceUrl(e.target.value)}
                    placeholder="http://localhost:3100/trace/..." />
                  <button className="btn sm" disabled={!traceUrl?.trim()}
                    onClick={() => window.open(traceUrl!, "_blank")}>打开</button>
                </div>
              </label>
            </div>
            <label className="fld">
              <span>轨迹问题简述</span>
              <input value={traceNote ?? ""} onChange={(e) => setTraceNote(e.target.value)}
                placeholder="该轨迹暴露了什么问题" />
            </label>
            {initial?.trace?.data && (
              <div className="pc-add">
                <button className="btn sm" onClick={restoreToLangfuse} disabled={busy}>
                  ↥ 导入 Langfuse（把归档轨迹恢复回去）
                </button>
                <span className="muted count">
                  已归档 {initial.trace.archived_at ? `于 ${initial.trace.archived_at.slice(0, 19)}` : ""}
                </span>
              </div>
            )}
          </fieldset>

          <label className="fld chk">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span>启用</span>
          </label>

          {notice && <p className="note">{notice}</p>}
          {error && <p className="err">{error}</p>}
        </div>

        <div className="modal-foot">
          <button className="btn" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
