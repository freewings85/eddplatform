"""FastAPI 应用：EDD 的真实数据接口 —— 读**真实** store（非占位 sample_data），
并能**触发真实评估**（系统自己跑 engine.run 打已部署环境 → 落 RunRecord/Evaluation）。

    uvicorn eddplatform.api.app:app --reload
    → http://127.0.0.1:8000        原型 UI（数据驱动，自动显示 store 里的真实系统）
    → http://127.0.0.1:8000/docs   OpenAPI

真实闭环（不绕过系统）：
    POST /api/systems/{id}/evaluate?version=2.0   → 触发一次真实评估（后台跑，立即回 RUNNING id）
    POST /api/systems/{id}/evaluate?version=2.3
    GET  /api/comparison                          → 两版本已完成评估的老新对比（真实 delta）
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from eddplatform.api.store import STORE
from eddplatform.domain.models import EvalStatus, Requirement
from eddplatform.evals import service
from eddplatform.integrations import jira
from eddplatform.systems import chatagent as chatagent_system

app = FastAPI(
    title="EddPlatform",
    version="0.1.0",
    description="评估驱动研发平台 — 版本化一次性沙箱 + 用例驱动发布评估 + 老新对比（真实数据）。",
)

# 启动即注册真实被评系统（把系统元数据 + 运行绑定装进 store）。占位 demo 数据已清除。
chatagent_system.register(STORE)

PROTOTYPE = Path(__file__).resolve().parents[3] / "prototype" / "index.html"


@app.get("/", include_in_schema=False)
def index():
    if not PROTOTYPE.exists():
        raise HTTPException(404, "prototype/index.html 未找到")
    return FileResponse(PROTOTYPE)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


# --- 系统 / 版本 -----------------------------------------------------------
@app.get("/api/systems")
def list_systems():
    return STORE.systems


@app.get("/api/systems/{system_id}")
def get_system(system_id: str):
    s = STORE.system_by_id(system_id)
    if not s:
        raise HTTPException(404, "system not found")
    return s


@app.get("/api/systems/{system_id}/versions")
def list_versions(system_id: str):
    return STORE.versions_for(system_id)


# --- 用例集 / 评估器 -------------------------------------------------------
@app.get("/api/systems/{system_id}/dataset")
def get_dataset(system_id: str, requirement: str | None = None):
    ds = STORE.dataset_for(system_id)
    if not ds:
        raise HTTPException(404, "dataset not found")
    if requirement:
        cases = [c for c in ds.cases if requirement in c.requirement_ids]
        return ds.model_copy(update={"cases": cases})
    return ds


@app.get("/api/systems/{system_id}/evaluators")
def list_evaluators(system_id: str):
    return STORE.evaluators_for(system_id)


# --- 需求（追溯锚点；详情在 Jira）-----------------------------------------
class RequirementCreate(BaseModel):
    title: str
    description: str | None = None
    external_key: str | None = None
    jira_project: str | None = None


@app.get("/api/systems/{system_id}/requirements")
def list_requirements(system_id: str, key: str | None = None):
    reqs = STORE.requirements_for(system_id)
    if key:
        reqs = [r for r in reqs if r.external_key == key]
    return reqs


@app.get("/api/requirements/{req_id}")
def get_requirement(req_id: str):
    r = STORE.requirement_by_id(req_id)
    if not r:
        raise HTTPException(404, "requirement not found")
    return r


@app.post("/api/systems/{system_id}/requirements")
def create_requirement(system_id: str, body: RequirementCreate):
    key, url = body.external_key, None
    if not key and body.jira_project and jira.available():
        issue = jira.create_issue(body.jira_project, body.title, body.description or "")
        key, url = issue["key"], issue["url"]
    elif key and os.environ.get("JIRA_URL"):
        url = jira.issue_url(key)
    nums = [int(r.id.split("-")[1]) for r in STORE.requirements
            if r.id.startswith("R-") and r.id.split("-")[1].isdigit()]
    req = Requirement(id=f"R-{max(nums) + 1 if nums else 101}", system_id=system_id,
                      title=body.title, description=body.description,
                      external_key=key, external_url=url)
    return STORE.add_requirement(req)


# --- 沙箱 / 环境 -----------------------------------------------------------
@app.get("/api/sandbox-configs")
def list_sandbox_configs():
    return STORE.sandbox_configs


@app.get("/api/environments")
def list_environments():
    return STORE.environments


# --- 运行 / 评估 -----------------------------------------------------------
@app.get("/api/runs")
def list_runs():
    return STORE.runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    r = STORE.run_by_id(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@app.get("/api/evaluations")
def list_evaluations():
    return STORE.evaluations


@app.get("/api/evaluations/{eval_id}")
def get_evaluation(eval_id: str):
    e = STORE.eval_by_id(eval_id)
    if not e:
        raise HTTPException(404, "evaluation not found")
    return e


@app.post("/api/systems/{system_id}/evaluate")
def trigger_evaluation(system_id: str, version: str):
    """触发一次**真实**评估：系统跑 engine.run 打已部署环境 → 落 RunRecord+Evaluation。
    后台执行，立即返回 RUNNING 的 run_id/eval_id，用 GET /api/evaluations/{id} 轮询。"""
    if not STORE.system_by_id(system_id):
        raise HTTPException(404, "system not found")
    if system_id not in STORE.bindings:
        raise HTTPException(400, f"system '{system_id}' 无运行绑定，无法评估")
    if not any(v.label == version for v in STORE.versions_for(system_id)):
        raise HTTPException(404, f"version '{version}' not found")
    run, ev = service.start_evaluation(STORE, system_id, version, background=True)
    return {"run_id": run.id, "eval_id": ev.id, "status": run.status,
            "poll": f"/api/evaluations/{ev.id}"}


# --- 对比 ------------------------------------------------------------------
def _latest_completed(system_id: str, version: str):
    evs = [e for e in STORE.completed_evaluations(system_id) if e.version_label == version]
    return evs[-1] if evs else None


@app.get("/api/comparison")
def get_comparison(baseline: str | None = None, candidate: str | None = None,
                   system: str = "chatagent",
                   baseline_version: str = "2.0", candidate_version: str = "2.3"):
    """两条已完成评估的老新对比。不给 eval id 时，自动取该系统两版本最新完成的评估。"""
    b_eval = STORE.eval_by_id(baseline) if baseline else _latest_completed(system, baseline_version)
    c_eval = STORE.eval_by_id(candidate) if candidate else _latest_completed(system, candidate_version)
    if not b_eval or not c_eval:
        raise HTTPException(404, "两版本都需先各跑完一次评估（POST /api/systems/{id}/evaluate?version=…）")
    cmp = service.comparison_of(STORE, b_eval.id, c_eval.id)
    if not cmp:
        raise HTTPException(409, "评估尚未完成或缺结果")
    return cmp
