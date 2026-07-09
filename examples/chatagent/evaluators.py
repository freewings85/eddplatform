"""chatagent 三场景评估器（EDD Evaluator，移植 chatagent3 runner 的判定语义）。

读评估上下文：``ctx.output`` = target 返回的 {output, tool_calls, usage, latency_s}；
``ctx.expected_output`` = 用例的断言规格 {tools, no_tools, criteria_subset, deny_phrases, judge}。

- 轨迹-工具序列   期望工具名按**子序列**出现在实际调用序列里
- 轨迹-禁用工具   这些工具一次都不能出现
- 轨迹-参数子集   该工具**最后一次**调用参数须**深子集**匹配期望（槽位抽取正确）
- 文案-禁用话术   最终回复禁止出现的短语
- 文案-LLM裁判    真 LLM 按 rubric 评文案质量（DashScope，温度 0）

另含维度评估器：成本(token)、时延——从 usage / duration 读，产 SCORE。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from eddplatform.domain.models import OutputType
from eddplatform.evals.engine import EvalContext, Outcome

LLM_KEY = os.environ.get("LITELLM_KEY_LLM_FLASH", "sk-8cf834ae11f94a9d91f7a98960e116cb")
LLM_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = os.environ.get("EDD_JUDGE_MODEL", "deepseek-v4-flash")


# ── 取值 / 匹配工具（与 runner.py 同语义）─────────────────────────────────────
def _tool_calls(ctx: EvalContext) -> list[dict]:
    return (ctx.output or {}).get("tool_calls", []) if isinstance(ctx.output, dict) else []


def _tool_names(ctx: EvalContext) -> list[str]:
    return [tc.get("tool_name") for tc in _tool_calls(ctx)]


def _output_text(ctx: EvalContext) -> str:
    return (ctx.output or {}).get("output", "") if isinstance(ctx.output, dict) else ""


def _is_subsequence(expected, actual) -> bool:
    it = iter(actual)
    return all(name in it for name in expected)


def _deep_subset(expected, actual) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and _deep_subset(v, actual[k]) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and all(
            any(_deep_subset(i, c) for c in actual) for i in expected)
    if isinstance(expected, str) and isinstance(actual, str):
        return expected in actual
    return expected == actual


def _last_args(ctx: EvalContext, tool: str) -> dict | None:
    for tc in reversed(_tool_calls(ctx)):
        if tc.get("tool_name") == tool:
            return tc.get("args") or {}
    return None


def _ok(name, passed, reason=""):
    return Outcome(name=name, output_type=OutputType.ASSERTION, value=passed,
                   passed=passed, reason=reason)


# ── 客观断言评估器 ───────────────────────────────────────────────────────────
@dataclass
class ToolSequence:
    name: str = "轨迹-工具序列"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        exp = (ctx.expected_output or {}).get("tools")
        if not exp:
            return _ok(self.name, True, "无 tools 断言")
        names = _tool_names(ctx)
        ok = _is_subsequence(exp, names)
        return _ok(self.name, ok, f"期望子序列 {exp}；实际 {names}")


@dataclass
class NoTools:
    name: str = "轨迹-禁用工具"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        exp = (ctx.expected_output or {}).get("no_tools")
        if not exp:
            return _ok(self.name, True, "无 no_tools 断言")
        names = _tool_names(ctx)
        hit = [t for t in exp if t in names]
        return _ok(self.name, not hit, f"不应出现 {exp}；命中 {hit}（实际 {names}）")


@dataclass
class CriteriaSubset:
    name: str = "轨迹-参数子集"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        crit = (ctx.expected_output or {}).get("criteria_subset")
        if not crit:
            return _ok(self.name, True, "无 criteria_subset 断言")
        specs = crit if isinstance(crit, list) else [crit]
        for spec in specs:
            tool = spec["tool"]
            expected_args = spec.get("args", {})
            actual = _last_args(ctx, tool)
            if actual is None:
                return _ok(self.name, False, f"工具 {tool} 未被调用")
            if not _deep_subset(expected_args, actual):
                return _ok(self.name, False,
                           f"{tool} 参数 {actual} 不满足期望子集 {expected_args}")
        return _ok(self.name, True, "参数子集全部满足")


@dataclass
class DenyPhrases:
    name: str = "文案-禁用话术"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        exp = (ctx.expected_output or {}).get("deny_phrases")
        if not exp:
            return _ok(self.name, True, "无 deny_phrases 断言")
        text = _output_text(ctx)
        hit = [p for p in exp if p in text]
        return _ok(self.name, not hit, f"禁止出现 {exp}；命中 {hit}")


@dataclass
class LLMJudge:
    """真 LLM 裁判：按 rubric 评最终回复文案质量。DashScope OpenAI 兼容，温度 0。"""

    name: str = "文案-LLM裁判"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        judge = (ctx.expected_output or {}).get("judge")
        if not judge:
            return _ok(self.name, True, "无 judge 断言")
        rubric = judge.get("rubric", "")
        text = _output_text(ctx)
        try:
            passed, reason = _run_judge(rubric, text)
        except Exception as e:  # noqa: BLE001 —— judge 基础设施故障不硬判负，记原因
            return Outcome(self.name, OutputType.LABEL, "judge_error", True, str(e)[:200])
        return _ok(self.name, passed, reason)


_JUDGE_SYS = ("你是评测裁判：给定评分标准(rubric)和 AI 客服的最终回复，判断回复是否满足该标准。"
              "只依据 rubric 与回复本身判断，不过度苛求措辞，语义满足即可判通过。"
              '只输出 JSON：{"passed": true/false, "reason": "一句话理由"}。')


def _run_judge(rubric: str, output_text: str) -> tuple[bool, str]:
    import httpx

    prompt = f"rubric：{rubric}\n\nAI 客服最终回复：\n{output_text}"
    resp = httpx.post(
        f"{LLM_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {LLM_KEY}"},
        json={"model": LLM_MODEL, "temperature": 0,
              "messages": [{"role": "system", "content": _JUDGE_SYS},
                           {"role": "user", "content": prompt}]},
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(content)
    return bool(data.get("passed")), str(data.get("reason", ""))[:200]


# ── 维度评估器（成本 / 时延，产 SCORE）───────────────────────────────────────
@dataclass
class CostTokens:
    name: str = "维度-成本token"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        usage = (ctx.output or {}).get("usage", {}) if isinstance(ctx.output, dict) else {}
        total = float(usage.get("total_tokens", 0))
        return Outcome(self.name, OutputType.SCORE, total, True,
                       f"total={total} (cache_read={usage.get('cache_read_tokens', 0)})")


@dataclass
class LatencyS:
    name: str = "维度-时延s"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        lat = float((ctx.output or {}).get("latency_s", ctx.duration_s)) \
            if isinstance(ctx.output, dict) else ctx.duration_s
        return Outcome(self.name, OutputType.SCORE, lat, True, f"{lat:.2f}s")


# ── token 分账（把 input 拆成 缓存命中 / 非缓存 —— 多轮成本的真相在这里）──────────
def _usage(ctx: EvalContext) -> dict:
    return (ctx.output or {}).get("usage", {}) if isinstance(ctx.output, dict) else {}


@dataclass
class InputTokens:
    """输入 token 总量（含被缓存命中的部分）。"""
    name: str = "维度-input_token"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        v = float(_usage(ctx).get("input_tokens", 0))
        return Outcome(self.name, OutputType.SCORE, v, True, f"input={v:.0f}")


@dataclass
class CacheReadTokens:
    """命中缓存的输入 token（按各家折扣计费，非全价）。"""
    name: str = "维度-缓存token"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        v = float(_usage(ctx).get("cache_read_tokens", 0))
        return Outcome(self.name, OutputType.SCORE, v, True, f"cache_read={v:.0f}")


@dataclass
class FreshTokens:
    """非缓存(fresh)输入 token = input - cache_read（按全价计费，多轮真实成本的大头）。"""
    name: str = "维度-非缓存token"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        u = _usage(ctx)
        v = float(u.get("input_tokens", 0)) - float(u.get("cache_read_tokens", 0))
        return Outcome(self.name, OutputType.SCORE, v, True, f"fresh={v:.0f}")


@dataclass
class CacheHitRate:
    """缓存命中率 = cache_read / input（0-1）。多轮/切业务时越高越省。"""
    name: str = "维度-缓存命中率"

    def evaluate(self, ctx: EvalContext) -> Outcome:
        u = _usage(ctx)
        inp = float(u.get("input_tokens", 0))
        rate = (float(u.get("cache_read_tokens", 0)) / inp) if inp else 0.0
        return Outcome(self.name, OutputType.SCORE, rate, True, f"{rate:.0%}")


def all_evaluators() -> dict:
    evs = [ToolSequence(), NoTools(), CriteriaSubset(), DenyPhrases(), LLMJudge(),
           CostTokens(), LatencyS(),
           InputTokens(), CacheReadTokens(), FreshTokens(), CacheHitRate()]
    return {e.name: e for e in evs}
