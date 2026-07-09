"""chatagent 三场景评估用例集（据 chatagent3 现成 evals/cases/*.yaml 的权威蓝本构造）。

用 EDD 的 Case 表达：``inputs.turns`` 是多轮用户输入，``expected_output`` 是断言规格
（对齐 chatagent3 runner 的语义）：
  tools           期望工具名按子序列出现（轨迹）
  no_tools        这些工具一次都不能出现
  criteria_subset {tool, args} 该工具最后一次调用参数须深子集匹配（槽位抽取正确）
  deny_phrases    最终回复禁止出现的短语（防越权代操作/生硬追问）
  judge           {rubric} 交 LLM 裁判评文案质量

这些断言由 evaluators.py 里的评估器施加：judge/deny_phrases/expect 从被评系统 HTTP 回复
文本读；tools/criteria_subset 从被评系统 emit 到 Langfuse 的 trace 读（黑盒）。

两套方案(2.0/2.3)输入相同、场景语义一致，故用例对两版本通用（applicable_versions 留空）。
"""

from eddplatform.domain.models import Case

# ── guide（纯问答，不进 confirm_business/search_*）────────────────────────────
GUIDE_CASES = [
    Case(id="guide_platform_intro", name="平台介绍→Skill(platform-intro)",
         inputs={"turns": [{"user": "你们这个平台是做什么的，能帮我介绍一下吗"}]},
         expected_output={"tools": ["Skill"],
                          "no_tools": ["confirm_business", "search_shops", "search_coupons"],
                          "criteria_subset": {"tool": "Skill", "args": {"skill": "platform-intro"}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集", "轨迹-禁用工具"]),
    Case(id="guide_saving_methods", name="省钱办法→Skill(saving-methods)",
         inputs={"turns": [{"user": "养车有什么省钱的办法吗，教教我"}]},
         expected_output={"tools": ["Skill"],
                          "no_tools": ["confirm_business", "search_shops", "search_coupons"],
                          "criteria_subset": {"tool": "Skill", "args": {"skill": "saving-methods"}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集", "轨迹-禁用工具"]),
    Case(id="guide_symptom_no_diagnosis", name="方向盘抖-不下诊断",
         inputs={"turns": [{"user": "我的车最近开起来方向盘有点抖，是怎么回事啊"}]},
         expected_output={"no_tools": ["confirm_business", "search_shops", "search_coupons"],
                          "judge": {"rubric": "回复不应给出确定的故障诊断结论（不应断言具体故障原因），"
                                    "应以简短说明加一个问句收束，自然引导用户去查门店或看优惠/活动来进一步检查。"}},
         evaluator_names=["轨迹-禁用工具", "文案-LLM裁判"]),
    Case(id="guide_insurance_not_business", name="车险问题-当知识答",
         inputs={"turns": [{"user": "新手第一年买车险大概要花多少钱，有什么要注意的"}]},
         expected_output={"no_tools": ["confirm_business", "search_shops", "search_coupons"],
                          "judge": {"rubric": "回复应作为知识性解答处理车险相关问题，不应把它当成找门店或"
                                    "找优惠的业务去执行查询，语气自然，不生硬拒绝。"}},
         evaluator_names=["轨迹-禁用工具", "文案-LLM裁判"]),
    Case(id="guide_smalltalk", name="寒暄-不生硬追问业务",
         inputs={"turns": [{"user": "你好呀"}]},
         expected_output={"no_tools": ["confirm_business", "search_shops", "search_coupons"],
                          "judge": {"rubric": "回复应是自然的问候/寒暄式回应，不应生硬地询问用户要办理什么"
                                    "业务或列出业务清单。"}},
         evaluator_names=["轨迹-禁用工具", "文案-LLM裁判"]),
]

# ── searchshops（找门店）─────────────────────────────────────────────────────
SEARCHSHOPS_CASES = [
    Case(id="shop_direct_wash", name="附近洗车店→洗车项目+当前位置",
         inputs={"turns": [{"user": "附近有没有洗车的店"}]},
         expected_output={"tools": ["confirm_business", "resolve_project_terms", "search_shops"],
                          "criteria_subset": {"tool": "search_shops", "args": {"query": {"op": "LEAF", "params": {
                              "use_current_location": True, "resolved_projects": ["洗车美容-洗车"]}}}},
                          "deny_phrases": ["你是想找门店吗", "请确认"]},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集", "文案-禁用话术"]),
    Case(id="shop_type_4s", name="4S店→shop_types",
         inputs={"turns": [{"user": "附近的4S店有哪些"}]},
         expected_output={"tools": ["confirm_business", "search_shops"],
                          "criteria_subset": {"tool": "search_shops", "args": {"query": {"op": "LEAF", "params": {
                              "shop_types": ["4S店"], "use_current_location": True}}}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
    Case(id="shop_nearer_is_order", name="更近一点→orderBy=distance",
         inputs={"turns": [{"user": "找几家能做小保养的店"}, {"user": "有更近一点的吗"}]},
         expected_output={"tools": ["search_shops", "search_shops"],
                          "criteria_subset": {"tool": "search_shops", "args": {"orderBy": "distance"}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
    Case(id="shop_ui_operation_denied", name="帮我预约第一家→拒绝代预约",
         inputs={"turns": [{"user": "帮我找家洗车店"}, {"user": "帮我预约第一家"}]},
         expected_output={"deny_phrases": ["我来帮你预约", "已帮你预约", "正在为你预约"],
                          "judge": {"rubric": "回复应明确表示无法代为预约，并指引用户自行在卡片/详情页操作，语气自然不生硬。"}},
         evaluator_names=["文案-禁用话术", "文案-LLM裁判"]),
    Case(id="shop_generic_nearby", name="修车地方→当前位置",
         inputs={"turns": [{"user": "附近有什么可以修车的地方推荐一下吗"}]},
         expected_output={"tools": ["confirm_business", "search_shops"],
                          "criteria_subset": {"tool": "search_shops", "args": {"query": {"op": "LEAF", "params": {
                              "use_current_location": True}}}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
]

# ── searchcoupons（找优惠）───────────────────────────────────────────────────
SEARCHCOUPONS_CASES = [
    Case(id="coupon_generic_nearby", name="附近优惠→当前位置",
         inputs={"turns": [{"user": "附近有什么优惠活动，随便看看"}]},
         expected_output={"tools": ["confirm_business", "search_coupons"],
                          "criteria_subset": {"tool": "search_coupons", "args": {"query": {"op": "LEAF", "params": {
                              "use_current_location": True}}}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
    Case(id="coupon_asks_price_project_aligned", name="小保养多少钱→asks_price+项目对齐",
         inputs={"turns": [{"user": "做个小保养大概多少钱"}]},
         expected_output={"tools": ["confirm_business", "resolve_project_terms", "search_coupons"],
                          "criteria_subset": {"tool": "search_coupons", "args": {"asks_price": True,
                              "query": {"op": "LEAF", "params": {"resolved_projects": ["保养&维修-小保养"]}}}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
    Case(id="coupon_zero_yuan", name="0元洗车→activity_keywords",
         inputs={"turns": [{"user": "附近有没有0元洗车之类的活动"}]},
         expected_output={"tools": ["confirm_business", "search_coupons"],
                          "criteria_subset": {"tool": "search_coupons", "args": {"query": {"op": "LEAF", "params": {
                              "use_current_location": True, "activity_keywords": ["0元"]}}}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
    Case(id="coupon_brand_and_project_split", name="米其林补胎多少钱→品牌+项目拆分",
         inputs={"turns": [{"user": "我想找米其林轮胎的补胎活动，多少钱"}]},
         expected_output={"tools": ["confirm_business", "resolve_project_terms", "search_coupons"],
                          "criteria_subset": {"tool": "search_coupons", "args": {"asks_price": True,
                              "query": {"op": "LEAF", "params": {"brand_keywords": ["米其林"],
                                        "resolved_projects": ["轮胎&轮毂-补胎"]}}}}},
         evaluator_names=["轨迹-工具序列", "轨迹-参数子集"]),
    Case(id="coupon_ui_operation_denied", name="帮我领了→拒绝代领",
         inputs={"turns": [{"user": "先看看附近有什么优惠活动"}, {"user": "帮我把第一个领了"}]},
         expected_output={"deny_phrases": ["我来帮你领", "已帮你领", "正在为你领取"],
                          "judge": {"rubric": "回复应明确表示无法代为领取优惠券，并指引用户自行在卡片/详情页操作，语气自然不生硬。"}},
         evaluator_names=["文案-禁用话术", "文案-LLM裁判"]),
]

ALL_CASES = GUIDE_CASES + SEARCHSHOPS_CASES + SEARCHCOUPONS_CASES
