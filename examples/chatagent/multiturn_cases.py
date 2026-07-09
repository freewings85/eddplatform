"""多轮会话测试集——重点覆盖"切换业务"（一会儿查活动、一会儿查商家）。

目的：看多轮下的真实 token 账，尤其 **缓存命中 vs 非缓存**。单轮口径会高估 2.3
（每轮都吞 ~13k 常驻工具本体）；多轮里那 13k 前缀恒定 → 命中缓存，非缓存(fresh)
才是全价大头。切业务尤其关键：2.3 单 agent 前缀业务无关、切换不失效；2.0 每次切
业务要重跑 BMA classify + 换 turn_router + 换 collect agent。

用例的 expected_output 走轻断言（切业务不追求逐槽命中，主看 token 维度 + 文案不越权）。
两套(2.0/2.3)输入相同、经各自前门驱动，故通用。
"""

from eddplatform.domain.models import Case

_DENY_OP = ["我来帮你预约", "已帮你预约", "正在为你预约", "我来帮你领取", "已帮你领取"]

# 每条用例都挂 token 分账 + 时延维度；文案不越权用 deny。
_DIMS = ["维度-时延s", "维度-input_token", "维度-缓存token", "维度-非缓存token",
         "维度-缓存命中率", "维度-成本token"]

MULTITURN_CASES = [
    # ── 切业务：短（1 次切换）──
    Case(id="mt_switch_short", name="切业务·短：介绍→商家→活动",
         inputs={"turns": [
             {"user": "你好，你们这平台能帮我做啥"},
             {"user": "附近有没有能洗车的店"},
             {"user": "那附近有什么优惠活动吗"},
         ]},
         expected_output={"deny_phrases": _DENY_OP},
         evaluator_names=["文案-禁用话术"] + _DIMS),

    # ── 切业务：乒乓（商家↔活动 来回切）──
    Case(id="mt_switch_pingpong", name="切业务·乒乓：商家→活动→商家→活动",
         inputs={"turns": [
             {"user": "附近有没有洗车的店"},
             {"user": "那有什么洗车的优惠活动吗"},
             {"user": "还是先看看洗车的店吧"},
             {"user": "再看看附近有什么优惠活动"},
         ]},
         expected_output={"deny_phrases": _DENY_OP},
         evaluator_names=["文案-禁用话术"] + _DIMS),

    # ── 切业务：长（多次来回 + 收尾追问）──
    Case(id="mt_switch_long", name="切业务·长：介绍→商家→活动→商家→活动→商家",
         inputs={"turns": [
             {"user": "你是谁，能帮我干嘛"},
             {"user": "附近有没有洗车的店"},
             {"user": "那附近有什么优惠活动吗"},
             {"user": "还是看看洗车的店吧"},
             {"user": "再看看附近有什么优惠活动"},
             {"user": "那还有别的洗车店吗"},
         ]},
         expected_output={"deny_phrases": _DENY_OP},
         evaluator_names=["文案-禁用话术"] + _DIMS),

    # ── 同业务多轮（真实 refine，来自 chatagent3 evals 蓝本）──
    Case(id="mt_within_shops_refine", name="同业务·商家 refine：找店→更近的→第二家营业时间",
         inputs={"turns": [
             {"user": "找几家能做小保养的店"},
             {"user": "有更近一点的吗"},
             {"user": "第二家几点营业，帮我查一下"},
         ]},
         expected_output={"deny_phrases": _DENY_OP,
                          "judge": {"rubric": "多轮应基于已展示的搜索结果回答或引导用户看详情卡片，"
                                    "不应声称代预约；引用商户名要完整不截断。"}},
         evaluator_names=["文案-禁用话术", "文案-LLM裁判"] + _DIMS),

    Case(id="mt_within_coupons_refine", name="同业务·活动 refine：找活动→便宜的→第一个怎么用",
         inputs={"turns": [
             {"user": "附近有什么优惠活动，随便看看"},
             {"user": "有没有便宜点的"},
             {"user": "第一个活动怎么用"},
         ]},
         expected_output={"deny_phrases": _DENY_OP,
                          "judge": {"rubric": "应基于已展示活动回答，如何使用应引导用户自行在卡片/详情页领取，"
                                    "明确不代领操作，语气自然。"}},
         evaluator_names=["文案-禁用话术", "文案-LLM裁判"] + _DIMS),
]
