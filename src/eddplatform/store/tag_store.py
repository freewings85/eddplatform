"""标签树持久化：每系统一棵标签树，节点存 ``(id, name, parent_id)``（MySQL）。

case 用**完整路径**（``业务/报价``）引用标签；路径由 parent 链计算得到。
重命名会改变子树路径，调用方（API）负责把 case 上的旧路径前缀重写成新路径。
"""

from __future__ import annotations

import threading

from eddplatform.domain.models import TagNode
from eddplatform.store.db import Db


class TagStore:
    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def _connect(self):
        return self.db.connect()

    # --- 读 --------------------------------------------------------------
    def list_tags(self, system_id: str) -> list[TagNode]:
        """返回全部标签节点（含计算好的 path），按 path 排序（父在子前）。"""
        rows = self._rows(system_id)
        by_id = {r["id"]: r for r in rows}
        nodes = [
            TagNode(
                id=r["id"],
                name=r["name"],
                parent_id=r["parent_id"],
                path=self._path_of(r["id"], by_id),
            )
            for r in rows
        ]
        nodes.sort(key=lambda n: n.path)
        return nodes

    def paths(self, system_id: str) -> list[str]:
        return [n.path for n in self.list_tags(system_id)]

    # --- 写 --------------------------------------------------------------
    def add_tag(self, system_id: str, name: str, parent_id: str | None = None) -> TagNode:
        name = self._validate_name(name)
        with self._lock:
            conn = self._connect()
            try:
                by_id = self._by_id(conn, system_id)
                if parent_id is not None and parent_id not in by_id:
                    raise ValueError(f"父标签 {parent_id} 不存在")
                self._reject_dup_sibling(by_id, parent_id, name)
                tag_id = self._next_id(conn, system_id)
                pos = self._next_position(conn, system_id)
                with conn.cursor() as c:
                    c.execute(
                        "INSERT INTO tags(system_id, id, name, parent_id, position) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (system_id, tag_id, name, parent_id, pos),
                    )
                conn.commit()
                by_id[tag_id] = {"id": tag_id, "name": name, "parent_id": parent_id}
                path = self._path_of(tag_id, by_id)
            finally:
                conn.close()
        return TagNode(id=tag_id, name=name, parent_id=parent_id, path=path)

    def rename_tag(self, system_id: str, tag_id: str, new_name: str) -> tuple[TagNode, str, str]:
        """重命名。返回 (节点, 旧路径, 新路径)——调用方据此重写 case 标签前缀。"""
        new_name = self._validate_name(new_name)
        with self._lock:
            conn = self._connect()
            try:
                by_id = self._by_id(conn, system_id)
                if tag_id not in by_id:
                    raise KeyError(tag_id)
                node = by_id[tag_id]
                old_path = self._path_of(tag_id, by_id)
                self._reject_dup_sibling(by_id, node["parent_id"], new_name, exclude=tag_id)
                with conn.cursor() as c:
                    c.execute(
                        "UPDATE tags SET name=%s WHERE system_id=%s AND id=%s",
                        (new_name, system_id, tag_id),
                    )
                conn.commit()
                node["name"] = new_name
                new_path = self._path_of(tag_id, by_id)
            finally:
                conn.close()
        return (
            TagNode(id=tag_id, name=new_name, parent_id=node["parent_id"], path=new_path),
            old_path,
            new_path,
        )

    def delete_tag(self, system_id: str, tag_id: str) -> list[str]:
        """删除节点及其全部子孙（级联）。返回被删的路径列表。"""
        with self._lock:
            conn = self._connect()
            try:
                by_id = self._by_id(conn, system_id)
                if tag_id not in by_id:
                    raise KeyError(tag_id)
                doomed = self._subtree_ids(tag_id, by_id)
                deleted_paths = [self._path_of(i, by_id) for i in doomed]
                with conn.cursor() as c:
                    c.executemany(
                        "DELETE FROM tags WHERE system_id=%s AND id=%s",
                        [(system_id, i) for i in doomed],
                    )
                conn.commit()
            finally:
                conn.close()
        return deleted_paths

    # --- 内部 ------------------------------------------------------------
    def _rows(self, system_id: str) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT id, name, parent_id, position FROM tags WHERE system_id=%s "
                    "ORDER BY position",
                    (system_id,),
                )
                return c.fetchall()
        finally:
            conn.close()

    @staticmethod
    def _by_id(conn, system_id: str) -> dict[str, dict]:
        with conn.cursor() as c:
            c.execute(
                "SELECT id, name, parent_id FROM tags WHERE system_id=%s", (system_id,)
            )
            return {r["id"]: dict(r) for r in c.fetchall()}

    @staticmethod
    def _path_of(tag_id: str, by_id: dict) -> str:
        parts, cur, guard = [], tag_id, 0
        while cur is not None and cur in by_id and guard < 64:
            parts.append(by_id[cur]["name"])
            cur = by_id[cur]["parent_id"]
            guard += 1
        return "/".join(reversed(parts))

    @staticmethod
    def _subtree_ids(root: str, by_id: dict) -> list[str]:
        out, stack = [], [root]
        while stack:
            cur = stack.pop()
            out.append(cur)
            stack.extend(i for i, r in by_id.items() if r["parent_id"] == cur)
        return out

    @staticmethod
    def _validate_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("标签名不能为空")
        if "/" in name:
            raise ValueError('标签名不能包含 "/"')
        return name

    @staticmethod
    def _reject_dup_sibling(by_id: dict, parent_id: str | None, name: str, exclude: str | None = None) -> None:
        for i, r in by_id.items():
            if i != exclude and r["parent_id"] == parent_id and r["name"] == name:
                raise ValueError(f"同级已存在标签「{name}」")

    def _next_id(self, conn, system_id: str) -> str:
        with conn.cursor() as c:
            c.execute("SELECT id FROM tags WHERE system_id=%s", (system_id,))
            rows = c.fetchall()
        nums = [int(r["id"]) for r in rows if str(r["id"]).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    def _next_position(self, conn, system_id: str) -> int:
        with conn.cursor() as c:
            c.execute("SELECT MAX(position) AS m FROM tags WHERE system_id=%s", (system_id,))
            row = c.fetchone()
        return 0 if row["m"] is None else int(row["m"]) + 1
