# EddPlatform

**Evaluation-Driven Development platform for agent systems** — versioned, ephemeral whole-system sandboxes + use-case-driven release evaluation & standardized old-vs-new comparison.

> 评估驱动研发平台（EDD）：按版本拉起**一次性的整系统沙箱**，用同一批用例端到端跑分，产出**老版本 vs 新版本的标准化对比**来把关发布——不凭感觉。

品类定位：**AgentOps ∩ 一次性环境(EaaS) ∩ 评估门禁(eval gate)**。

**框架无关**：被评系统当黑盒（从入口拿 `输入→输出` + OTel 轨迹），无论它用 **pydantic-ai、LangGraph** 还是任意 HTTP 服务都能评。

**技术栈**：前端 **React + TypeScript + Vite**（`web/`）；后端 **Python / FastAPI**（`src/`）为主，可含 **Java** 服务——平台语言/框架无关，服务间走 REST/OTel。

---

## 它解决什么

一个系统由多个服务（模块）组成。要升级其中几个模块时，需要客观回答"新版本比老版本好还是坏、在哪些用例上退化"。EddPlatform：

1. 按 **系统版本**（各模块钉住镜像 tag 的组合，如 v1=原 5 服务、v2=2 新 + 3 旧）拉起**隔离的一次性沙箱**；
2. 用**同一批用例**端到端跑，采集**日志 + 全链路轨迹**；
3. 用**同一套评估器**（code + LLM-judge）打分；
4. 产出 **v1 vs v2 的标准化对比**（改善 / 回归 / 持平，只统计两版本都适用的用例）；
5. 跑完**自动销毁**环境。

## 复用优秀开源，二次开发要薄

平台自身**不造轮子**（包括**不自研评估引擎**），是一层薄壳 + 编排，长在成熟开源之上：

| 能力 | 复用的开源 | EddPlatform 只做 |
|---|---|---|
| **评估引擎 + 存储 + 老新对比** | **Langfuse**（框架无关，MIT 开源核心）| 薄 task loop + Target 适配 + 写 score |
| 评估 harness（可选，二选一）| **Promptfoo** / **DeepEval** / pydantic-evals | 走中立适配层接入，分数回灌 Langfuse |
| 一次性多服务环境 | **Garden**（+ vCluster / Okteto）| 触发 / 编排 |
| 编排控制器 | **Temporal** | 写流水线 workflow（薄）|
| 黑盒隔离 | k8s namespace+NetworkPolicy → **vCluster** → **Kata/gVisor** | 传参数 |
| 版本 / 镜像仓库 | **Harbor** | 拉 tag、渲染 manifest |
| 统一门户 | **Backstage** | 自定义 Scaffolder action（薄）|
| 追踪 | **OpenTelemetry** | 埋点 |

> **评估引擎 = Langfuse，不自研。** 仓库里的 `evals/engine.py` 只是**中立适配接口 + 零依赖本地兜底评分器**（离线开发 / CI 冒烟用）；生产走 `evals/adapters/langfuse.py`。中立层让引擎可换（Langfuse / Promptfoo / DeepEval），不锁死。详见 [`docs/`](docs/)。

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
web/                  前端 React + TypeScript + Vite（连 FastAPI /api）
prototype/            高保真可点击原型（设计基准，浏览器直接打开）
docs/                 设计与调研文档（架构 / 选型 / 原型设计 / SOP）
examples/eval_demo.py 离线跑通评估内核（本地兜底，零依赖）
src/eddplatform/
  domain/models.py            领域模型（对象模型的代码化）
  api/app.py                  FastAPI：把原型当 UI 端起来 + 领域数据接口
  api/sample_data.py          示例数据（保险报价系统 v1/v2）
  evals/engine.py             中立评估接口 + 零依赖本地兜底评分器（dev/CI）
  evals/targets.py            被评系统入口抽象（Callable / HTTP 黑盒）
  evals/adapters/langfuse.py  ★ 评估引擎（推荐）：Langfuse
  evals/adapters/pydantic_evals.py  可选后端（仅 pydantic-ai 项目）
tests/
```

## 快速开始

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'                 # 核心 + 测试

python examples/eval_demo.py            # 离线跑通评估内核（无需 Langfuse）
uvicorn eddplatform.api.app:app --reload  # http://127.0.0.1:8000 看原型
pytest

# 评估引擎（推荐）：Langfuse —— 本地自托管一键起（见 deploy/langfuse/）
pip install -e '.[langfuse]'
( cd deploy/langfuse && cp -n .env.example .env && docker compose up -d )   # web: http://localhost:3100
export LANGFUSE_HOST=http://localhost:3100 \
       LANGFUSE_PUBLIC_KEY=pk-lf-eddplatform-local \
       LANGFUSE_SECRET_KEY=sk-lf-eddplatform-local
python examples/langfuse_run.py     # 端到端：sync 用例 → 跑 v1/v2 → 到 Langfuse Compare 看对比
```

前端（React + TypeScript + Vite）：

```bash
cd web && npm install
npm run dev          # http://localhost:5173（/api 自动代理到 :8000 的 FastAPI）
```

> 原型也可脱离后端，直接双击 `prototype/index.html` 打开。

## 路线（MVP → 完整）

- [x] 领域模型 + 原型 + API 骨架
- [x] 框架无关评估接口 + 本地兜底 + 离线 demo
- [ ] **Langfuse 接入**：sync 用例集 → dataset run(v1/v2) → 写 score → Compare 对比
- [ ] Harbor 拉 tag → 渲染「系统版本」manifest
- [ ] Garden 在 k8s 拉起 v1/v2 一次性环境 + OTel 埋点
- [ ] Temporal 编排「建 env → 跑 → 评 → 对比 → 销」
- [ ] Backstage 门户 / SSO 单入口

## 状态

内部项目，早期脚手架。私有仓库。评估引擎复用 Langfuse，不自研。
