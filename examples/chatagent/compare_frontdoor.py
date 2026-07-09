"""EDD 老新对比（**前门到前门·完整系统**）：方案A(2.0) vs 方案B(2.3)，三场景。

与 compare.py 的关键区别：两套都经各自**前门 orchestrator :7100 /chat/stream** 驱动
**完整一轮**（2.0: orchestrator→workflows→BMA→chatagent2→toolprovider；2.3:
orchestrator→chatagent3→toolexecutor），而非直接打某个下游进程。这样时延/文案才是
"整套系统"的、可比的。用户口径：要对比完整的系统，而不是某个点。

    PYTHONPATH=src python examples/chatagent/compare_frontdoor.py

可比性说明（诚实标注，不重蹈"不公平对比"覆辙）：
- **时延**：前门到 chat_request_end 的墙钟，完全端到端、公平可比 —— 头号指标。
- **文案质量**：judge/deny 断言对最终回复，架构中立、公平可比。
- **token**：2.3 单 agent 一次 usage 事件即全量；2.0 的 usage 事件只带叶子 agent
  (chatagent2)的用量，**漏掉 BMA classify/turn_router + workflows 小模型**（分处独立
  进程、不往 chat-events 发 usage）。故 2.0 的 token 是**低估**，跨架构 token 对比需
  Langfuse trace 汇总（待办改进），此处仅原样列出并标注。
- **参数抽取**：2.3 前门 SSE 带 search_*(query=...) 完整 args；2.0 前门 search 工具
  调用 args 不落 SSE → 前门侧无法对等抽取（见直接探针 compare.py 的 collect-agent 口径）。
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
from examples.chatagent.evaluators import all_evaluators  # noqa: E402
from examples.chatagent.frontdoor import make_frontdoor_target  # noqa: E402

GROUPS = {"guide": GUIDE_CASES, "searchshops": SEARCHSHOPS_CASES, "searchcoupons": SEARCHCOUPONS_CASES}
DIMS = ["维度-成本token", "维度-时延s"]
NEUTRAL = {"文案-LLM裁判", "文案-禁用话术"}
evs = all_evaluators()


def _avg(res, key):
    vals = [cr.scores.get(key) for cr in res.case_results if key in cr.scores]
    return mean(vals) if vals else 0.0


def _quality(res):
    hits, tot = 0, 0
    for cr in res.case_results:
        neu = {k: v for k, v in cr.assertions.items() if k in NEUTRAL}
        if neu:
            tot += 1
            hits += all(neu.values())
    return (hits / tot) if tot else None


def _failed(res):
    """整体 passed=False 的用例数（含真实 LLM 行为偏差与错误）。"""
    return sum(1 for cr in res.case_results if not cr.passed)


def run_solution(ns):
    """经前门 orchestrator :7100 驱动完整一轮；两套用法一致（2.0 的路由由 BMA 自动完成，
    不需 agent_type）。"""
    out = {}
    target = make_frontdoor_target(ns, orch="orchestrator", port=7100, turn_timeout=175)
    for scen, group in GROUPS.items():
        cases = [c.model_copy(update={"evaluator_names": c.evaluator_names + DIMS}) for c in group]
        out[scen] = run(target, cases, evs)
    return out


print("跑方案B(2.3, edd-2-3) 前门 ...", flush=True)
b = run_solution("edd-2-3")
print("跑方案A(2.0, edd-2-0) 前门 ...", flush=True)
a = run_solution("edd-2-0")


def pct(x):
    return "—" if x is None else f"{x:.0%}"


# 先落盘（防 print 崩溃丢整轮结果）：每方案每场景的 时延/token/质量/失败数 + 逐用例分数。
def _summ(sol):
    return {scen: {"latency_s": _avg(res, "维度-时延s"), "tokens": _avg(res, "维度-成本token"),
                   "quality": _quality(res), "failed": _failed(res), "n": len(res.case_results),
                   "cases": [{"id": cr.case_id, "passed": cr.passed,
                              "scores": cr.scores, "assertions": cr.assertions}
                             for cr in res.case_results]}
            for scen, res in sol.items()}


import json as _json  # noqa: E402
_out = {"A_2.0": _summ(a), "B_2.3": _summ(b)}
with open("/tmp/claude-1000/-mnt-e-Documents-github-eddplatform/7cb29248-508b-4d1a-8f80-5a04ed5c6807/scratchpad/compare_fd_result.json", "w") as _f:
    _json.dump(_out, _f, ensure_ascii=False, indent=2)
print("[saved] compare_fd_result.json", flush=True)

print("\n" + "=" * 96)
print("老新对比·前门到前门·完整系统   A=方案A(2.0/orchestrator→workflows→BMA→chatagent2)")
print("                              B=方案B(2.3/orchestrator→chatagent3→toolexecutor)")
print("=" * 96)
print(f"{'场景':<13}{'时延s A→B':>18}{'token A→B(见注)':>24}{'文案质量 A→B':>18}{'失败 A/B':>12}")
print("-" * 96)
for scen in GROUPS:
    la, lb = _avg(a[scen], "维度-时延s"), _avg(b[scen], "维度-时延s")
    ta, tb = _avg(a[scen], "维度-成本token"), _avg(b[scen], "维度-成本token")
    qa, qb = _quality(a[scen]), _quality(b[scen])
    ea, eb = _failed(a[scen]), _failed(b[scen])
    print(f"{scen:<13}{la:>8.1f} → {lb:<7.1f}{ta:>10.0f} → {tb:<10.0f}"
          f"{pct(qa):>8} → {pct(qb):<8}{ea:>5}/{eb:<5}")
print("-" * 96)
print("注：时延=前门完整一轮墙钟，端到端公平可比；token 2.0 为低估(漏 BMA/workflows 独立进程 LLM)，")
print("   跨架构 token 需 Langfuse trace 汇总；文案质量=judge/deny 断言(架构中立)。")
