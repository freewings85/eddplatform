import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { TagNode } from "./types";

export default function Tags({ sysId }: { sysId: string }) {
  const [tags, setTags] = useState<TagNode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    api
      .tags(sysId)
      .then(setTags)
      .catch((e) => setError(String(e)));
  }, [sysId]);

  useEffect(() => {
    setTags(null);
    reload();
  }, [reload]);

  function fail(e: unknown) {
    setError(String(e));
  }

  async function addRoot() {
    const name = prompt("新建根标签，名字（不含 /）：")?.trim();
    if (!name) return;
    await api.createTag(sysId, name, null).catch(fail);
    reload();
  }

  async function addChild(parent: TagNode) {
    const name = prompt(`在「${parent.path}」下新建子标签：`)?.trim();
    if (!name) return;
    await api.createTag(sysId, name, parent.id).catch(fail);
    reload();
  }

  async function rename(node: TagNode) {
    const name = prompt(`重命名「${node.path}」为：`, node.name)?.trim();
    if (!name || name === node.name) return;
    await api.renameTag(sysId, node.id, name).catch(fail);
    reload();
  }

  async function remove(node: TagNode) {
    const kids = (tags ?? []).filter((t) => t.path.startsWith(node.path + "/")).length;
    const extra = kids ? `（含 ${kids} 个子标签，一并删除）` : "";
    if (!confirm(`删除标签「${node.path}」${extra}？\n用例上已用的该标签不会被自动清除。`)) return;
    await api.deleteTag(sysId, node.id).catch(fail);
    reload();
  }

  return (
    <>
      <h2 className="page">标签</h2>
      <p className="sub">分层标签（树）；用例用完整路径引用，如 业务/报价。重命名会联动改写用例上的标签路径</p>
      {error && <p className="err">{error}</p>}

      <div className="toolbar">
        <button className="btn primary" onClick={addRoot}>
          ＋ 新建根标签
        </button>
        <span className="muted count">{tags?.length ?? 0} 个标签</span>
      </div>

      <div className="card">
        {tags && tags.length === 0 && <div className="empty pad">还没有标签，点「新建根标签」开始。</div>}
        {(tags ?? []).map((t) => {
          const depth = t.path.split("/").length - 1;
          return (
            <div key={t.id} className="tag-row" style={{ paddingLeft: 14 + depth * 22 }}>
              <span className="tag-name">
                {depth > 0 && <span className="tag-branch">└ </span>}
                {t.name}
              </span>
              <span className="tag-path mono muted">{t.path}</span>
              <span className="tag-row-actions">
                <button className="btn sm" onClick={() => addChild(t)}>
                  ＋ 子标签
                </button>
                <button className="btn sm" onClick={() => rename(t)}>
                  重命名
                </button>
                <button className="btn sm danger" onClick={() => remove(t)}>
                  删除
                </button>
              </span>
            </div>
          );
        })}
      </div>
    </>
  );
}
