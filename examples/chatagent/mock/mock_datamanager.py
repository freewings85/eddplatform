"""Mock datamanager backend for L1 e2e (task #70) + projectterm_resolver dev.

工作流 capability (searchshops / searchcoupons) 调外部 datamanager
(`DATAMANAGER_BASE_URL`，默认 `http://127.0.0.1:50400/service_ai_datamanager`)
做"项目 keyword → packageId / 商户 keyword 扩展 / 商户列表 / 优惠列表"。
本地 / CI 没有真 datamanager 时 L1 e2e 全 502 hang，不能验证业务成功路径。

本 mock 用 stdlib http.server 起一个轻量 backend，返回固定形状的 canned
response 让 capability code 跑通：

- POST /service_ai_datamanager/package/searchPackageByKeyword         → 1 个 packageId
- POST /service_ai_datamanager/Activity/searchPackageByKeyword        → 老 L1 形态
    body 含 `keyword` (str) → {result: {exactMatched:[{packageId:100,...}], ragMatched:[]}}
- POST /service_ai_datamanager/Activity/searchPackageByKeywords       → 新批量端点（plural）
    body 含 `keywords` (list) → {result: {<kw>: {exactMatched, fuzzyMatched, ragMatched}}}
    按 fixture 全量叶项目做子串匹配（mock 不复现真 RAG，只为 capability 跑通）
- POST /service_ai_datamanager/Activity/listActivityPackageTreePageByFeign
                                                                      → 226 leaf 全树（fixture）
- POST /service_ai_datamanager/package/listTreePage                   → 空 tree
- POST /service_ai_datamanager/otherlexiconquery/fusionSearch         → 空 matches
- POST /service_ai_datamanager/shop/workflows/complexQuery            → 3 家固定洗车店
- POST /service_ai_datamanager/activity/workflows/combinedQuery       → 2 张固定洗车券

启动：`MOCK_DATAMANAGER_PORT=50401 python scripts/mock_datamanager.py`
配置：dev_all.sh 在 SERVICES 上方 export
  `DATAMANAGER_BASE_URL=http://127.0.0.1:50401/service_ai_datamanager`
让 workflows-worker 调本 mock 而非真 50400。

Why stdlib：避免新依赖；轻 mock 不需要 fastapi/路由表。固定数据，不复
现真 datamanager 业务规则——L1 验证的是 capability + workflow contract，
不是 backend 算法。新的 listActivityPackageTreePageByFeign 复用
`src/mainagent/test/projectterm_resolver/fixtures/sample_tree_response.json`
（真 API 截取的 8 root / 226 leaf 全量样本），module load 时一次性读到 module
global，运行时无 IO。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


_BASE_PREFIX = "/service_ai_datamanager"

# tree fixture：projectterm_resolver acceptance 测试也用同一份文件，
# 避免 mock 跟测试用例 fixture 漂移。
_REPO_ROOT: Path = Path(__file__).resolve().parents[1]
_TREE_FIXTURE_PATH: Path = (
    _REPO_ROOT
    / "src"
    / "mainagent"
    / "test"
    / "projectterm_resolver"
    / "fixtures"
    / "sample_tree_response.json"
)


def _load_tree_fixture() -> dict[str, Any]:
    """module 加载时一次性把 sample_tree_response.json 读进 memory。

    文件不存在时返一份空响应（不让 mock 启动崩，方便老路径继续跑）。
    """
    if not _TREE_FIXTURE_PATH.exists():
        logging.warning("tree fixture 不存在 (%s)，listActivityPackageTreePageByFeign 将返空", _TREE_FIXTURE_PATH)
        return {
            "status": 0,
            "message": "执行成功",
            "result": {
                "pageNum": 1, "pageSize": 1000, "total": 0, "pages": 0, "list": [],
            },
        }
    with _TREE_FIXTURE_PATH.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return data


_TREE_RESPONSE: dict[str, Any] = _load_tree_fixture()


def _flatten_leaves(tree_response: dict[str, Any]) -> list[dict[str, Any]]:
    """递归 walk tree，把所有 last=True 的节点摊平，顺便 derive `path`。

    与 DataManager 修复后的语义对齐：
      - path = 祖先链 packageName 用 '/' 拼接，**不含 leaf 自身**
      - root 自身是 leaf（罕见）→ path = ""

    真 API 的 listActivityPackageTreePageByFeign 不返 `path`，由 mock 手工 derive。
    """
    leaves: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = tree_response.get("result", {}).get("list", []) or []

    def _walk(node: dict[str, Any], ancestor_chain: list[str]) -> None:
        if node.get("last"):
            # path 是祖先链不含自身；root 是 leaf 时 ancestor_chain 空 → path=""。
            path: str = "/".join(ancestor_chain)
            leaves.append({
                "packageId": node.get("packageId"),
                "packageName": node.get("packageName"),
                "last": True,
                "parentId": node.get("parentId"),
                "ancestors": node.get("ancestors", ""),
                "path": path,
            })
        # 递归时 ancestor_chain 加入当前节点（孩子的祖先链含当前节点）。
        next_chain: list[str] = ancestor_chain + [str(node.get("packageName", ""))]
        for child in node.get("children") or []:
            _walk(child, next_chain)

    for root in roots:
        _walk(root, [])
    return leaves


_ALL_LEAVES: list[dict[str, Any]] = _flatten_leaves(_TREE_RESPONSE)


def _all_named_nodes() -> list[dict[str, Any]]:
    """walk tree，收集所有节点（含中间节点），用于 exactMatched 命中。

    DataManager 真 API 的 exactMatched 可能命中非叶节点（例：'洗车' last=False 仍可被命中）。
    每个节点也 derive 出 path = 祖先链不含自身 '/' 拼接。
    """
    nodes: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = _TREE_RESPONSE.get("result", {}).get("list", []) or []

    def _walk(node: dict[str, Any], ancestor_chain: list[str]) -> None:
        path: str = "/".join(ancestor_chain)
        nodes.append({
            "packageId": node.get("packageId"),
            "packageName": node.get("packageName"),
            "last": bool(node.get("last")),
            "parentId": node.get("parentId"),
            "ancestors": node.get("ancestors", ""),
            "path": path,
        })
        next_chain: list[str] = ancestor_chain + [str(node.get("packageName", ""))]
        for child in node.get("children") or []:
            _walk(child, next_chain)

    for root in roots:
        _walk(root, [])
    return nodes


_ALL_NODES: list[dict[str, Any]] = _all_named_nodes()


# ── canned responses ───────────────────────────────────────────────────────


def _ok(result: Any) -> dict[str, Any]:
    return {"status": 0, "result": result}


def _ok_with_message(result: Any) -> dict[str, Any]:
    """跟真 API 一致的形态：含 message 字段（projectterm_resolver 工具校验时会读）。"""
    return {"status": 0, "message": "执行成功", "result": result}


def _shop_card(shop_id: int, name: str, distance: float) -> dict[str, Any]:
    """Mock shop record satisfying searchshops `_extract_backend_items` shape
    (commercials list with dicts) and downstream card formatting."""
    return {
        "id": shop_id,
        "shop_id": shop_id,
        "shopId": shop_id,
        "title": name,
        "shop_name": name,
        "shopName": name,
        "name": name,
        "address": "上海市徐汇区虚构路 1 号",
        "distance": distance,
        "distance_km": distance,
        "latitude": 31.2,
        "longitude": 121.45,
        "rating": 4.7,
        "businessHours": "9:00-21:00",
    }


def _coupon_card(coupon_id: str, title: str, shop_name: str) -> dict[str, Any]:
    """Mock coupon record satisfying searchcoupons backend response shape."""
    return {
        "activity_id": coupon_id,
        "activityId": coupon_id,
        "id": coupon_id,
        "packageName": title,
        "title": title,
        "commercialName": shop_name,
        "shop_name": shop_name,
        "price_label": "9.9 元",
        "price": 9.9,
        "content": title,
        "distance": 1.2,
    }


_SHOPS_FIXTURE: list[dict[str, Any]] = [
    _shop_card(1001, "途虎养车徐汇店", 1.2),
    _shop_card(1002, "天猫养车徐家汇店", 1.8),
    _shop_card(1003, "京东养车徐家汇店", 2.5),
]


_COUPONS_FIXTURE: list[dict[str, Any]] = [
    _coupon_card("c2001", "精致洗车券", "途虎养车徐汇店"),
    _coupon_card("c2002", "标准洗车套餐", "天猫养车徐家汇店"),
]


# DataManager 真实在 alias 表里维护着"口语词 → 真实项目"映射，所以"换机油"
# 可以直接 exact 命中"小保养"，即便字面不像。mock 这里 hardcode 一小撮典型
# 映射，覆盖常见同义场景；alias value 必须是 fixture tree 里**真实存在的 leaf
# packageName**，写错下面 _name_to_node 会查不到导致 hit 丢失。
_ALIAS_MAP: dict[str, list[str]] = {
    "换机油": ["小保养"],
    "换机滤": ["空气滤清器更换"],
    "补胎": ["贴片补胎"],
    "刹车片": ["前刹车片更换", "后刹车片更换"],
    "打蜡": ["漆面打蜡"],
}


# 录制式响应：把真 DataManager 对若干典型 keyword 的实际返回直接抓下来塞表里，
# 优先级高于下面的算法兜底。一旦 keyword 命中本表，直接返录制 (exact / rag) 形态
# 给上层；不命中才走 alias + 双向子串 + 字符集重合的算法路径。
#
# 录制来源（真 DataManager `/Activity/searchPackageByKeywords`）：
# - 换机油   → exact: 小保养 / 4 个油更换类（alias 命中 + 油更换字面）
# - 机油更换 → rag: 4 个油更换类（无 alias，没命中小保养，是真 DM 的边界）
# - 空调清洗 → rag: 空调系统相关 6 项
# - 轮胎检查 → rag: 轮胎相关 4 项
# - 保养     → rag: 保养项目 / 小保养 / 保养&维修 / 大保养 / 空调滤清器更换
#
# similarity 字段尽量沿用真 DM 实际数值，让 LLM 在 mock 下看到的"信号强弱"分布
# 跟生产一致。
_RECORDED_RESPONSES: dict[str, dict[str, list[tuple[str, float | None]]]] = {
    "换机油": {
        "exact": [
            ("小保养", None),
            ("变速箱油更换", None),
            ("分动箱油更换", None),
            ("差速器油更换", None),
            ("转向助力油更换", None),
        ],
        "rag": [],
    },
    "机油更换": {
        "exact": [],
        "rag": [
            ("变速箱油更换", 0.45),
            ("差速器油更换", 0.394),
            ("转向助力油更换", 0.468),
            ("分动箱油更换", 0.462),
        ],
    },
    "空调清洗": {
        "exact": [],
        "rag": [
            ("空调冷凝器清洗", 0.928),
            ("蒸发箱清洗", 0.934),
            ("空调系统", 0.985),
            ("空调管路杀菌/除味", 0.868),
            ("空调系统深度养护", 0.907),
            ("节气门清洗", 0.528),
        ],
    },
    "轮胎检查": {
        "exact": [],
        "rag": [
            ("轮胎", 0.414),
            ("胎压监测匹配及更换", 0.518),
            ("轮胎&轮毂", 0.711),
        ],
    },
    "保养": {
        "exact": [],
        "rag": [
            ("保养项目", 0.67),
            ("小保养", 0.769),
            ("保养&维修", 0.825),
            # 真 DM 还会返"大保养"，但 fixture 没有这个 leaf，跳过
            ("空调滤清器更换", 0.341),
        ],
    },
    # ── 症状词：真 DM 大多返空，subagent 需要拆"部位 / 元件 + 处理"二次搜 ──
    "刹车抖动": {"exact": [], "rag": []},
    "底盘异响": {"exact": [], "rag": []},
    "刹车异响": {"exact": [], "rag": []},
    "雨刮刮不干净": {"exact": [], "rag": []},
    "胎压报警漏气": {"exact": [], "rag": []},
    "启动困难": {"exact": [], "rag": []},
    "空调不制冷": {"exact": [], "rag": []},
    "车身被刮": {"exact": [], "rag": []},
    "发动机故障灯": {"exact": [], "rag": []},
    "异响": {"exact": [], "rag": []},
    "悬挂": {"exact": [], "rag": []},
    "启动": {"exact": [], "rag": []},
    # ── 症状有 alias 直接命中的 ──
    "方向盘跑偏": {"exact": [("四轮定位", None)], "rag": []},
    "电瓶亏电": {"exact": [("搭电", None)], "rag": []},
    # ── 部位 / 元件词：真 DM 走 rag ──
    "底盘": {
        "exact": [],
        "rag": [
            ("后轮毂轴承更换", 0.646),
            ("横拉杆总成更换", 0.684),
            ("减震顶胶轴承更换", 0.539),
            ("前平衡杆支架检修/更换", 0.641),
            ("后平衡杆支架检修/更换", 0.61),
            ("后平衡杆连杆更换", 0.591),
        ],
    },
    "摆臂": {
        "exact": [],
        "rag": [
            ("后摆臂更换", 0.603),
            ("前摆臂更换", 0.611),
            ("前摆臂球头更换", 0.411),
            ("后摆臂球头更换", 0.427),
            ("前摆臂衬套更换", 0.42),
            ("后摆臂衬套更换", 0.422),
        ],
    },
    "减震": {
        "exact": [],
        "rag": [
            ("后减震更换", 0.596),
            ("前减震更换", 0.572),
            ("减震顶胶轴承更换", 0.507),
            ("前减震总成更换", 0.383),
            ("后减震总成更换", 0.413),
        ],
    },
    "刹车片": {
        "exact": [],
        "rag": [
            ("前刹车片更换", 0.879),
            ("后刹车片更换", 0.881),
            ("刹车片更换", 0.879),
            ("刹车片更换（带件）", 0.828),
        ],
    },
    "刹车盘": {
        "exact": [],
        "rag": [
            ("后刹车盘更换", 0.763),
            ("前刹车盘更换", 0.761),
        ],
    },
    "雨刮": {
        "exact": [],
        "rag": [
            ("后雨刮更换", 0.911),
            ("前雨刮更换", 0.874),
            ("雨刮更换", 0.893),
            ("前雨刮更换（带件）", 0.516),
        ],
    },
    "雨刮片": {
        "exact": [],
        "rag": [
            ("后雨刮更换", 0.562),
            ("前雨刮更换", 0.497),
        ],
    },
    "胎压": {
        "exact": [],
        "rag": [("胎压监测匹配及更换", 0.533)],
    },
    "补胎": {"exact": [("补胎", None)], "rag": []},
    "轮胎": {"exact": [("轮胎", None)], "rag": []},
    "四轮定位": {"exact": [("四轮定位", None)], "rag": []},
    "搭电": {"exact": [("搭电", None)], "rag": []},
    "电瓶": {
        "exact": [],
        "rag": [
            ("电瓶更换", 0.49),
            ("上门换电瓶", 0.375),
        ],
    },
    "点火": {
        "exact": [],
        "rag": [("点火线圈更换", 0.363)],
    },
    "空调": {
        "exact": [],
        "rag": [
            ("空调管路杀菌/除味", 0.509),
            ("空调系统深度养护", 0.582),
            ("蒸发箱清洗", 0.329),
        ],
    },
    "故障码": {
        "exact": [],
        "rag": [("电脑故障码检测/清除", 0.594)],
    },
    "电脑检测": {
        "exact": [],
        "rag": [("电脑故障码检测/清除", 0.614)],
    },
    "车身": {
        "exact": [],
        "rag": [
            ("车身装饰贴件", 0.827),
            ("车身颜色改装", 0.509),
            ("车身外观防护件", 0.48),
            ("其他装饰件", 0.396),
            ("外观装饰件", 0.747),
            ("内饰装饰件", 0.369),
        ],
    },
    "划痕": {
        "exact": [],
        "rag": [("划痕处理", 0.512)],
    },
    "喷漆": {
        "exact": [],
        "rag": [("全车喷漆", 0.506)],
    },
}


def _name_to_node() -> dict[str, dict[str, Any]]:
    """按 packageName 索引 _ALL_NODES，alias 命中时用 O(1) 拿 path / id / parent 等。"""
    out: dict[str, dict[str, Any]] = {}
    for node in _ALL_NODES:
        name: str = str(node.get("packageName") or "")
        if name and name not in out:
            out[name] = node
    return out


_NAME_INDEX: dict[str, dict[str, Any]] = _name_to_node()


def _build_node(name: str) -> dict[str, Any] | None:
    """按 packageName 在 _NAME_INDEX 拿真实节点 dict；查不到返 None（跳过）。

    刻意不附 similarity —— LLM 不该按数字排序，靠 path/语义判断；mock 跟生产
    工具下发都保持 wire 干净。
    """
    node = _NAME_INDEX.get(name)
    if node is None:
        return None
    return dict(node)


def _wrap_rag(keyword: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """真 DM rag 形态：[{originalName, candidates: [...]}]；候选空时返空 list。"""
    if not candidates:
        return []
    return [{"originalName": keyword, "candidates": candidates}]


def _match_keyword_against_leaves(keyword: str) -> dict[str, list[dict[str, Any]]]:
    """对单个 keyword 在 fixture 全量节点上做三档匹配。

    优先级：
    1. 录制响应表 `_RECORDED_RESPONSES`：命中即按真 DM 返回原样输出（最准）
    2. 否则走算法兜底：
       - exactMatched: alias 命中 + 双向子串关系
       - fuzzyMatched: 字符集重合度 > 0.7
       - ragMatched: 字符集重合度 > 0.5
    """
    kw: str = (keyword or "").strip()
    if not kw:
        return {"exactMatched": [], "fuzzyMatched": [], "ragMatched": []}

    # ── 1. 录制响应优先 ────────────────────────────────────────
    recorded = _RECORDED_RESPONSES.get(kw)
    if recorded is not None:
        exact: list[dict[str, Any]] = []
        rag_cands: list[dict[str, Any]] = []
        for entry in recorded.get("exact", []):
            name = entry[0] if isinstance(entry, (tuple, list)) else entry
            node = _build_node(name)
            if node is not None:
                exact.append(node)
        for entry in recorded.get("rag", []):
            name = entry[0] if isinstance(entry, (tuple, list)) else entry
            node = _build_node(name)
            if node is not None:
                rag_cands.append(node)
        return {
            "exactMatched": exact,
            "fuzzyMatched": [],
            "ragMatched": _wrap_rag(kw, rag_cands),
        }

    # ── 2. 算法兜底 ───────────────────────────────────────────
    exact = []
    fuzzy: list[dict[str, Any]] = []
    rag_cands = []
    exact_names: set[str] = set()

    # 2.1 alias 表命中 —— 直接进 exact 桶
    for alias_name in _ALIAS_MAP.get(kw, []):
        node = _NAME_INDEX.get(alias_name)
        if node is not None and alias_name not in exact_names:
            exact.append(dict(node))
            exact_names.add(alias_name)

    # 2.2 双向子串命中 —— 也进 exact 桶
    for node in _ALL_NODES:
        name: str = str(node.get("packageName", ""))
        if not name or name in exact_names:
            continue
        if kw in name or name in kw:
            exact.append(dict(node))
            exact_names.add(name)

    # 2.3 fuzzy / rag：字符集重合度
    kw_chars: set[str] = set(kw)
    kw_len: int = len(kw_chars)
    if kw_len == 0:
        return {
            "exactMatched": exact,
            "fuzzyMatched": fuzzy,
            "ragMatched": _wrap_rag(kw, rag_cands),
        }

    for node in _ALL_NODES:
        name = str(node.get("packageName", ""))
        if not name or name in exact_names:
            continue
        overlap: float = len(kw_chars & set(name)) / kw_len
        if overlap > 0.7:
            fuzzy.append(dict(node))
        elif overlap > 0.5:
            rag_cands.append(dict(node))

    return {
        "exactMatched": exact,
        "fuzzyMatched": fuzzy,
        "ragMatched": _wrap_rag(kw, rag_cands),
    }


def _batch_search_keywords(keywords: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """批量版 searchPackageByKeyword 响应 result：{<kw>: {exactMatched, fuzzyMatched, ragMatched}}。"""
    return {kw: _match_keyword_against_leaves(kw) for kw in keywords}


def _route(path: str, body: dict[str, Any]) -> dict[str, Any]:
    """根据 endpoint 返回 canned response。"""
    if not path.startswith(_BASE_PREFIX):
        return {"status": -1, "message": f"unexpected base: {path}"}
    relative = path[len(_BASE_PREFIX):]

    if relative == "/Activity/searchPackageByKeywords":
        # 新批量端点（plural）：keywords 是 list[str]
        # 返 {result: {<kw>: {exactMatched, fuzzyMatched, ragMatched}}}
        keywords_raw: Any = body.get("keywords")
        if not (isinstance(keywords_raw, list) and all(isinstance(k, str) for k in keywords_raw)):
            return {"status": -1, "message": "keywords must be list[str]"}
        return _ok_with_message(_batch_search_keywords(keywords_raw))

    if relative in ("/package/searchPackageByKeyword", "/Activity/searchPackageByKeyword"):
        # 老 L1 路径（singular）：keyword 是 str，返 {result: {exactMatched: [...], ragMatched: []}}
        # capability code 期望 result.exactMatched[].packageId
        return _ok({
            "exactMatched": [{"packageId": 100, "title": "通用项目"}],
            "ragMatched": [],
        })
    if relative == "/Activity/listActivityPackageTreePageByFeign":
        # 新增端点：直接吐 fixture（已是 {status, result: {pageNum, pageSize, total, pages, list}} 形态）
        # 任何 pageNum / pageSize 入参一律忽略（mock 简化，一次给全 226 leaf）。
        return _TREE_RESPONSE
    if relative == "/package/listTreePage":
        # capability 用 result（list）扁平化为 project parent map；空 tree OK
        return _ok([])
    if relative == "/otherlexiconquery/fusionSearch":
        # capability 用 fusion result 扩品牌/商户/类型；空 matches 走 keyword 兜底
        return _ok({"exact_matched": [], "fuzzy_matched": [], "rag_matched": []})
    if relative == "/shop/workflows/complexQuery":
        return _ok({"commercials": _SHOPS_FIXTURE, "total": len(_SHOPS_FIXTURE)})
    if relative == "/activity/workflows/combinedQuery":
        return _ok({"commercialActivities": _COUPONS_FIXTURE, "total": len(_COUPONS_FIXTURE)})

    # 未知 path：返回空成功，不挂 capability（任何 unknown 都按"无结果"算）
    return _ok({})


# ── HTTP server ────────────────────────────────────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logging.info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
            return
        self._respond(404, {"status": -1, "message": f"GET unsupported: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict):
            body = {}
        response = _route(self.path, body)
        self._respond(200, response)

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.getenv("MOCK_DATAMANAGER_PORT", "50401"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [mock-datamanager] %(message)s")
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    logging.info(
        "listening on http://127.0.0.1:%d (base path %s, %d leaf projects loaded)",
        port, _BASE_PREFIX, len(_ALL_LEAVES),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
    sys.exit(0)
