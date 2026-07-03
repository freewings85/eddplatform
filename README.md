# EddPlatform

**Evaluation-Driven Development platform for agent systems** — versioned, ephemeral whole-system sandboxes + use-case-driven release evaluation & standardized old-vs-new comparison.

> 评估驱动研发平台（EDD）：按版本拉起**一次性的整系统沙箱**，用同一批用例端到端跑分，产出**老版本 vs 新版本的标准化对比**来把关发布——不凭感觉。

品类定位：**AgentOps ∩ 一次性环境(EaaS) ∩ 评估门禁(eval gate)**。Agent 框架锁定 **pydantic-ai**，评估执行用 **Pydantic Evals**。

---

## 它解决什么

一个系统由多个服务（模块）组成。要升级其中几个模块时，需要客观回答"新版本比老版本好还是坏、在哪些用例上退化"。EddPlatform：

1. 按 **系统版本**（各模块钉住镜像 tag 的组合，如 v1=原 5 服务、v2=2 新 + 3 旧）拉起**隔离的一次性沙箱**；
2. 用**同一批用例**端到端跑，采集**日志 + 全链路轨迹**；
3. 用**同一套评估器**（code + LLM-judge）打分；
4. 产出 **v1 vs v2 的标准化对比**（改善 / 回归 / 持平，只统计两版本都适用的用例）；
5. 跑完**自动销毁**环境。

## 复用优秀开源，二次开发要薄

平台自身不造轮子，是一层薄壳 + 编排，长在这些成熟开源之上：

| 能力 | 复用的开源 | EddPlatform 只做 |
|---|---|---|
| 一次性多服务环境 | **Garden**（+ vCluster / Okteto） | 触发 / 编排 |
| 编排控制器 | **Temporal** | 写流水线 workflow（薄） |
| 黑盒隔离 | k8s namespace+NetworkPolicy → **vCluster** → **Kata/gVisor** | 传参数 |
| 版本 / 镜像仓库 | **Harbor** | 拉 tag、渲染 manifest |
| 统一门户 | **Backstage** | 自定义 Scaffolder action（薄） |
| trace + 评估 + 对比 | **OpenTelemetry → Langfuse** + **Pydantic Evals** | 埋点 + 数据集/评估器配置（薄） |

详见 [`docs/`](docs/)。

## 对象模型

```
System ─< Module(含 Git: 地址/分支/镜像)
       ─< SystemVersion(钉住各模块 tag 的快照, v1/v2)
SandboxConfig ── Environment(某版本的一次性实例, 可配置可选择)
Dataset ─< Case(有自身版本 + 适用系统版本) ── EvaluatorDef
RunRecord   一次执行: 日志/轨迹; 可"单独运行"(自测不评分) 或由评估产生
Evaluation  = 系统版本 × 用例集 × 环境 → 必带一条 RunRecord → EvalResult
Comparison  = 两个 EvalResult 的对比(只统计两版本都适用的用例)
```

见 [`src/eddplatform/domain/models.py`](src/eddplatform/domain/models.py)。

## 目录

```
prototype/            高保真可点击原型（当前 UI，浏览器直接打开）
docs/                 设计与调研文档（架构 / 选型 / 原型设计 / SOP）
src/eddplatform/
  domain/models.py    领域模型（对象模型的代码化）
  api/app.py          FastAPI：把原型当 UI 端起来 + 领域数据接口
  api/sample_data.py  示例数据（保险报价系统 v1/v2）
  evals/runner.py     EvaluatorDef → Pydantic Evals 执行的集成点
tests/
```

## 快速开始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'        # 核心 + 测试
# 可选：pip install -e '.[evals,integrations]'   # pydantic-evals / langfuse / temporal

uvicorn eddplatform.api.app:app --reload   # 打开 http://127.0.0.1:8000 看原型
pytest                                       # 跑测试
```

> 原型也可脱离后端，直接双击 `prototype/index.html` 打开。

## 路线（MVP → 完整）

- [x] 领域模型 + 原型 + API 骨架
- [ ] Harbor 拉 tag → 渲染「系统版本」manifest
- [ ] Garden 在 k8s 拉起 v1/v2 一次性环境 + OTel 埋点
- [ ] Pydantic Evals 跑用例 → Langfuse dataset run
- [ ] Temporal 编排「建 env → 跑 → 评 → 对比 → 销」
- [ ] Backstage 门户 / SSO 单入口

## 状态

内部项目，早期脚手架。私有仓库。
