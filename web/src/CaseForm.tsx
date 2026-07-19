import { useState } from "react";
import type { Case, CaseInput } from "./types";

/** 把 JSON 文本域解析成值：空→undefined；能解析成 JSON 就用 JSON；否则当纯字符串。 */
function parseLoose(text: string): unknown {
  const t = text.trim();
  if (!t) return undefined;
  try {
    return JSON.parse(t);
  } catch {
    return text; // 允许纯字符串输入（inputs 支持 dict | str）
  }
}

function toText(v: unknown): string {
  if (v === undefined || v === null) return "";
  if (typeof v === "string") return v;
  return JSON.stringify(v, null, 2);
}

function splitList(text: string): string[] {
  return text
    .split(/[,，\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

type Props = {
  initial?: Case | null; // 有 = 编辑，无 = 新增
  availableEvaluators: string[];
  availableTags: string[]; // 标签树的完整路径
  onCancel: () => void;
  onSubmit: (payload: CaseInput) => Promise<void>;
};

export default function CaseForm({
  initial,
  availableEvaluators,
  availableTags,
  onCancel,
  onSubmit,
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [inputs, setInputs] = useState(toText(initial?.inputs ?? ""));
  const [expected, setExpected] = useState(toText(initial?.expected_output));
  const [tags, setTags] = useState<string[]>(initial?.tags ?? []);
  const [extraTags, setExtraTags] = useState("");
  const [caseVersion, setCaseVersion] = useState(initial?.case_version ?? "v1");
  const [applicable, setApplicable] = useState((initial?.applicable_versions ?? []).join(", "));
  const [evaluators, setEvaluators] = useState<string[]>(initial?.evaluator_names ?? []);
  const [traceRef, setTraceRef] = useState(initial?.trace?.ref ?? "");
  const [traceUrl, setTraceUrl] = useState(initial?.trace?.url ?? "");
  const [traceNote, setTraceNote] = useState(initial?.trace?.note ?? "");
  const [metadata, setMetadata] = useState(toText(initial?.metadata));
  const [author, setAuthor] = useState(initial?.author ?? "");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function toggleEvaluator(n: string) {
    setEvaluators((cur) => (cur.includes(n) ? cur.filter((x) => x !== n) : [...cur, n]));
  }

  function toggleTag(t: string) {
    setTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]));
  }

  // 标签树 ∪ 当前用例已用的标签（保留不在树里的历史标签）
  const knownTags = [...new Set([...availableTags, ...tags])].sort();

  async function submit() {
    setError(null);
    if (!name.trim()) return setError("用例名不能为空");

    // metadata 必须是对象（或空）
    const meta = parseLoose(metadata);
    if (meta !== undefined && (typeof meta !== "object" || Array.isArray(meta))) {
      return setError("metadata 必须是 JSON 对象");
    }

    const payload: CaseInput = {
      name: name.trim(),
      description: description.trim() || null,
      inputs: (parseLoose(inputs) as Case["inputs"]) ?? "",
      expected_output: (parseLoose(expected) as Case["expected_output"]) ?? null,
      tags: [...new Set([...tags, ...splitList(extraTags)])],
      metadata: (meta as Record<string, unknown>) ?? {},
      case_version: caseVersion.trim() || "v1",
      applicable_versions: splitList(applicable),
      evaluator_names: evaluators,
      trace: traceRef.trim()
        ? { ref: traceRef.trim(), url: traceUrl.trim() || null, note: traceNote.trim() || null }
        : null,
      author: author.trim() || null,
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
    <div className="modal-backdrop" onClick={onCancel}>
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
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="新能源车型报价" />
          </label>

          <label className="fld">
            <span>描述</span>
            <input
              value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="这条用例在测什么"
            />
          </label>

          <div className="fld-row">
            <label className="fld">
              <span>inputs（JSON 或文本）</span>
              <textarea value={inputs} onChange={(e) => setInputs(e.target.value)} rows={4}
                placeholder={'{"car": "ev"}'} className="mono" />
            </label>
            <label className="fld">
              <span>expected_output（可空）</span>
              <textarea value={expected} onChange={(e) => setExpected(e.target.value)} rows={4}
                placeholder={'{"premium": 4260}'} className="mono" />
            </label>
          </div>

          <div className="fld">
            <span>标签（分层，来自「标签」管理页）</span>
            <div className="chips">
              {knownTags.length === 0 && (
                <i className="muted">该系统暂无标签，去「标签」页新建，或在下方补充</i>
              )}
              {knownTags.map((t) => (
                <label key={t} className={`chip ${tags.includes(t) ? "on" : ""}`}>
                  <input type="checkbox" checked={tags.includes(t)} onChange={() => toggleTag(t)} />
                  {t}
                </label>
              ))}
            </div>
            <input
              value={extraTags}
              onChange={(e) => setExtraTags(e.target.value)}
              placeholder="补充其它标签（逗号分隔，用完整路径如 业务/报价）"
            />
          </div>

          <label className="fld">
            <span>用例版本</span>
            <input value={caseVersion} onChange={(e) => setCaseVersion(e.target.value)} placeholder="v1" />
          </label>

          <label className="fld">
            <span>适用系统版本（逗号分隔，空 = 全部通用）</span>
            <input value={applicable} onChange={(e) => setApplicable(e.target.value)} placeholder="v1, v2" />
          </label>

          <div className="fld">
            <span>评估器</span>
            <div className="chips">
              {availableEvaluators.length === 0 && <i className="muted">该系统暂无评估器</i>}
              {availableEvaluators.map((n) => (
                <label key={n} className={`chip ${evaluators.includes(n) ? "on" : ""}`}>
                  <input
                    type="checkbox"
                    checked={evaluators.includes(n)}
                    onChange={() => toggleEvaluator(n)}
                  />
                  {n}
                </label>
              ))}
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
                <input value={traceUrl ?? ""} onChange={(e) => setTraceUrl(e.target.value)}
                  placeholder="http://localhost:3100/trace/..." />
              </label>
            </div>
            <label className="fld">
              <span>轨迹问题简述</span>
              <input value={traceNote ?? ""} onChange={(e) => setTraceNote(e.target.value)}
                placeholder="新能源报价算错，quote-engine 少算补贴" />
            </label>
          </fieldset>

          <div className="fld-row">
            <label className="fld">
              <span>metadata（JSON 对象，可空）</span>
              <textarea value={metadata} onChange={(e) => setMetadata(e.target.value)} rows={2}
                className="mono" placeholder={'{"source": "prod"}'} />
            </label>
            <label className="fld">
              <span>负责人</span>
              <input value={author ?? ""} onChange={(e) => setAuthor(e.target.value)} placeholder="张三" />
            </label>
          </div>

          <label className="fld chk">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span>启用</span>
          </label>

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
