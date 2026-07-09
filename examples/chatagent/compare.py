"""EDD 老新对比：方案A(2.0) vs 方案B(2.3)，三场景，真实系统+真实 LLM。

    PYTHONPATH=src python examples/chatagent/compare.py

两套方案各自部署在一个 namespace（edd-2-0 / edd-2-3）。对同一批用例：
- 2.3：打 chatagent3 mainagent（单 hlsc_agent，raw message 自路由）。
- 2.0：打 chatagent2 mainagent，按场景传 agent_type 跑对应 agent。

因两架构内部工具不同，**跨架构对比看结果层**：时延、成本(token)、质量(LLM 裁判/禁用话术)。
各自的完整断言通过率(2.3-native 断言对 2.0 不适用)仅作各自参考。
"""
import sys
from statistics import mean

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from eddplatform.evals.engine import run  # noqa: E402
from examples.chatagent.cases import (  # noqa: E402
    GUIDE_CASES,
    SEARCHCOUPONS_CASES,
    SEARCHSHOPS_CASES,
)
from examples.chatagent.config import AGENT_TYPE_2_0  # noqa: E402
from examples.chatagent.evaluators import all_evaluators  # noqa: E402
from examples.chatagent.target import make_chatagent_target  # noqa: E402

GROUPS = {"guide": GUIDE_CASES, "searchshops": SEARCHSHOPS_CASES, "searchcoupons": SEARCHCOUPONS_CASES}
DIMS = ["维度-成本token", "维度-时延s"]
NEUTRAL = {"文案-LLM裁判", "文案-禁用话术"}   # 架构中立的质量断言
evs = all_evaluators()


def _avg(res, key):
    vals = [cr.scores.get(key) for cr in res.case_results if key in cr.scores]
    return mean(vals) if vals else 0.0


def _quality(res):
    """架构中立质量：judge/deny 断言的通过率（只算含这些断言的用例）。"""
    hits, tot = 0, 0
    for cr in res.case_results:
        neu = {k: v for k, v in cr.assertions.items() if k in NEUTRAL}
        if neu:
            tot += 1
            hits += all(neu.values())
    return (hits / tot) if tot else None


def _assertion_pass(res, name):
    """某个断言(如 轨迹-参数子集)的通过率，只算含该断言的用例。两架构都产 search_* 工具
    调用参数，故『参数抽取准确率』跨架构可比。"""
    vals = [cr.assertions[name] for cr in res.case_results if name in cr.assertions]
    return (sum(vals) / len(vals)) if vals else None


def run_solution(ns, entry, agent_type_map):
    out = {}
    for scen, group in GROUPS.items():
        cases = [c.model_copy(update={"evaluator_names": c.evaluator_names + DIMS}) for c in group]
        at = agent_type_map.get(scen) if agent_type_map else None
        target = make_chatagent_target(ns, entry=entry, agent_type=at)
        out[scen] = run(target, cases, evs)
    return out


print("跑方案B(2.3, edd-2-3) ...")
b = run_solution("edd-2-3", "mainagent", None)
print("跑方案A(2.0, edd-2-0) ...")
a = run_solution("edd-2-0", "ca2-mainagent", AGENT_TYPE_2_0)

def pct(x):
    return "—" if x is None else f"{x:.0%}"


print("\n" + "=" * 92)
print("老新对比  A=方案A(2.0/chatagent2 旧)   B=方案B(2.3/chatagent3 新·重构后)")
print("=" * 92)
print(f"{'场景':<13}{'参数抽取 A→B':>18}{'时延s A→B':>16}{'token A→B':>18}{'guide质量 A→B':>18}")
print("-" * 92)
for scen in GROUPS:
    pa, pb = _assertion_pass(a[scen], "轨迹-参数子集"), _assertion_pass(b[scen], "轨迹-参数子集")
    la, lb = _avg(a[scen], "维度-时延s"), _avg(b[scen], "维度-时延s")
    ta, tb = _avg(a[scen], "维度-成本token"), _avg(b[scen], "维度-成本token")
    qa, qb = _quality(a[scen]), _quality(b[scen])
    print(f"{scen:<13}{pct(pa):>7} → {pct(pb):<7}{la:>6.1f} → {lb:<6.1f}"
          f"{ta:>8.0f} → {tb:<8.0f}{pct(qa):>8} → {pct(qb):<8}")
print("-" * 92)
print("说明：参数抽取=search_* 工具参数(resolved_projects/位置/asks_price 等)命中率，跨架构可比；")
print("     2.0 search 打的是 collect agent(产参数不产最终文案)，故 search 的 guide质量列为 —；")
print("     时延/token 为各自入口一次 /chat/run 的实测；越快、越省、抽取/质量越高越好。")
