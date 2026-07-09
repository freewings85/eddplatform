"""多轮·前门到前门·token 缓存分账对比：方案A(2.0) vs 方案B(2.3)。

回答"多轮(尤其切业务)时 token 到底花在哪、缓存帮了多少"：每条多轮用例经各自前门
/chat/stream 完整驱动，逐轮攒 usage 再相加，把 input 拆成 **缓存命中 / 非缓存(fresh)**。

    PYTHONPATH=src python examples/chatagent/compare_multiturn.py

口径诚实说明：
- **非缓存(fresh)=input-cache_read** 是全价大头；缓存 token 按各家折扣计（~10-40% input 价），
  故"真实费用"介于 fresh 与 input 之间。
- 2.3 的 usage 是**单 agent 全量**；2.0 的是**collect 叶子、漏 BMA classify/turn_router**
  （每次切业务全新、几乎不命中）→ 2.0 的 token 是**低估**。要精确须 Langfuse 逐 generation。
- 故本表用于看**趋势**（缓存随多轮/切业务的命中走势、fresh 的量级），非最终费用裁决。
"""
import sys
from statistics import mean

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from eddplatform.evals.engine import run  # noqa: E402
from examples.chatagent.evaluators import all_evaluators  # noqa: E402
from examples.chatagent.frontdoor import make_frontdoor_target  # noqa: E402
from examples.chatagent.multiturn_cases import MULTITURN_CASES  # noqa: E402

evs = all_evaluators()


def _avg(res, key):
    vals = [cr.scores.get(key) for cr in res.case_results if key in cr.scores]
    return mean(vals) if vals else 0.0


def run_solution(ns):
    target = make_frontdoor_target(ns, orch="orchestrator", port=7100, turn_timeout=175)
    return run(target, MULTITURN_CASES, evs)


print("跑方案B(2.3) 多轮前门 ...", flush=True)
b = run_solution("edd-2-3")
print("跑方案A(2.0) 多轮前门 ...", flush=True)
a = run_solution("edd-2-0")

# 落盘防丢
import json as _json  # noqa: E402
KEYS = ["维度-时延s", "维度-input_token", "维度-缓存token", "维度-非缓存token",
        "维度-缓存命中率", "维度-成本token"]
_dump = {sol: {"per_case": [{"id": cr.case_id, "scores": cr.scores} for cr in res.case_results],
               "avg": {k: _avg(res, k) for k in KEYS}}
         for sol, res in [("A_2.0", a), ("B_2.3", b)]}
_p = "/tmp/claude-1000/-mnt-e-Documents-github-eddplatform/7cb29248-508b-4d1a-8f80-5a04ed5c6807/scratchpad/compare_mt_result.json"
with open(_p, "w") as _f:
    _json.dump(_dump, _f, ensure_ascii=False, indent=2)
print("[saved]", _p, flush=True)

by_id = {cr.case_id: cr for cr in a.case_results}
print("\n" + "=" * 104)
print("多轮·前门到前门·token 缓存分账   A=2.0(分布式)  B=2.3(单体)   每格 A→B")
print("=" * 104)
hdr = f"{'用例':<22}{'轮':>3}{'时延s':>14}{'input':>16}{'缓存命中':>16}{'非缓存fresh':>18}{'命中率':>14}"
print(hdr)
print("-" * 104)
for cr_b in b.case_results:
    cid = cr_b.case_id
    cr_a = by_id.get(cid)
    n = len(next(c.inputs.get("turns", []) for c in MULTITURN_CASES if c.id == cid))

    def g(cr, k):
        return cr.scores.get(k, 0) if cr else 0
    la, lb = g(cr_a, "维度-时延s"), g(cr_b, "维度-时延s")
    ia, ib = g(cr_a, "维度-input_token"), g(cr_b, "维度-input_token")
    ca, cb = g(cr_a, "维度-缓存token"), g(cr_b, "维度-缓存token")
    fa, fb = g(cr_a, "维度-非缓存token"), g(cr_b, "维度-非缓存token")
    ha, hb = g(cr_a, "维度-缓存命中率"), g(cr_b, "维度-缓存命中率")
    print(f"{cid:<22}{n:>3}{la:>6.1f}→{lb:<6.1f}{ia:>7.0f}→{ib:<7.0f}"
          f"{ca:>7.0f}→{cb:<7.0f}{fa:>8.0f}→{fb:<8.0f}{ha:>6.0%}→{hb:<6.0%}")
print("-" * 104)
print(f"{'均值':<22}{'':>3}{_avg(a,'维度-时延s'):>6.1f}→{_avg(b,'维度-时延s'):<6.1f}"
      f"{_avg(a,'维度-input_token'):>7.0f}→{_avg(b,'维度-input_token'):<7.0f}"
      f"{_avg(a,'维度-缓存token'):>7.0f}→{_avg(b,'维度-缓存token'):<7.0f}"
      f"{_avg(a,'维度-非缓存token'):>8.0f}→{_avg(b,'维度-非缓存token'):<8.0f}"
      f"{_avg(a,'维度-缓存命中率'):>6.0%}→{_avg(b,'维度-缓存命中率'):<6.0%}")
print("-" * 104)
print("注：非缓存(fresh)=全价大头；缓存 token 按折扣计。2.0 token 为低估(漏 BMA)；2.3 为单 agent 全量。")
print("   看趋势：多轮/切业务下缓存命中越高、fresh 越低越省。精确费用须 Langfuse 逐 generation。")
