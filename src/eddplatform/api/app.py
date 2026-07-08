"""FastAPI 应用：把原型当作当前 UI 端起来 + 暴露领域数据接口（读，占位）。

    uvicorn eddplatform.api.app:app --reload
    → http://127.0.0.1:8000        原型
    → http://127.0.0.1:8000/docs   OpenAPI
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from eddplatform.api import sample_data as sd
from eddplatform.domain.models import Requirement
from eddplatform.integrations import jira

app = FastAPI(
    title="EddPlatform",
    version="0.0.1",
    description="评估驱动研发平台 — 版本化一次性沙箱 + 用例驱动发布评估 + 老新对比。",
)

# 仓库根：src/eddplatform/api/app.py -> parents[3]
PROTOTYPE = Path(__file__).resolve().parents[3] / "prototype" / "index.html"


@app.get("/", include_in_schema=False)
def index():
    if not PROTOTYPE.exists():
        raise HTTPException(404, "prototype/index.html 未找到")
    return FileResponse(PROTOTYPE)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


# --- 系统 / 模块 / 版本 ----------------------------------------------------
@app.get("/api/systems")
def list_systems():
    return sd.SYSTEMS


@app.get("/api/systems/{system_id}")
def get_system(system_id: str):
    system = sd.system_by_id(system_id)
    if not system:
        raise HTTPException(404, "system not found")
    return system


@app.get("/api/systems/{system_id}/versions")
def list_versions(system_id: str):
    return [v for v in sd.VERSIONS if v.system_id == system_id]


# --- 用例 / 评估器 ---------------------------------------------------------
@app.get("/api/systems/{system_id}/dataset")
def get_dataset(system_id: str, requirement: str | None = None):
    if sd.DATASET.system_id != system_id:
        raise HTTPException(404, "dataset not found")
    if requirement:
        cases = [c for c in sd.DATASET.cases if requirement in c.requirement_ids]
        return sd.DATASET.model_copy(update={"cases": cases})
    return sd.DATASET


# --- 需求（追溯锚点；详情在 Jira）-----------------------------------------
class RequirementCreate(BaseModel):
    title: str
    description: str | None = None
    external_key: str | None = None       # 关联已有 Jira 号
    jira_project: str | None = None       # 给了且无 external_key 且 Jira 可用 → 推送建 issue


@app.get("/api/systems/{system_id}/requirements")
def list_requirements(system_id: str, key: str | None = None):
    reqs = [r for r in sd.REQUIREMENTS if r.system_id == system_id]
    if key:
        reqs = [r for r in reqs if r.external_key == key]
    return reqs


@app.get("/api/requirements/{req_id}")
def get_requirement(req_id: str):
    r = next((x for x in sd.REQUIREMENTS if x.id == req_id), None)
    if not r:
        raise HTTPException(404, "requirement not found")
    return r


@app.post("/api/systems/{system_id}/requirements")
def create_requirement(system_id: str, body: RequirementCreate):
    """新建需求：可推送到 Jira 建 issue / 关联已有 key / 暂不关联（离线亦可）。"""
    key, url = body.external_key, None
    if not key and body.jira_project and jira.available():
        issue = jira.create_issue(body.jira_project, body.title, body.description or "")
        key, url = issue["key"], issue["url"]
    elif key and os.environ.get("JIRA_URL"):
        url = jira.issue_url(key)
    nums = [int(r.id.split("-")[1]) for r in sd.REQUIREMENTS
            if r.id.startswith("R-") and r.id.split("-")[1].isdigit()]
    req = Requirement(id=f"R-{max(nums) + 1 if nums else 101}", system_id=system_id,
                      title=body.title, description=body.description,
                      external_key=key, external_url=url)
    sd.REQUIREMENTS.append(req)
    return req


@app.get("/api/systems/{system_id}/evaluators")
def list_evaluators(system_id: str):
    return sd.EVALUATORS


# --- 沙箱 / 环境 -----------------------------------------------------------
@app.get("/api/sandbox-configs")
def list_sandbox_configs():
    return sd.SANDBOX_CONFIGS


@app.get("/api/environments")
def list_environments():
    return sd.ENVIRONMENTS


# --- 运行 / 评估 / 对比 ----------------------------------------------------
@app.get("/api/runs")
def list_runs():
    return sd.RUNS


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = next((r for r in sd.RUNS if r.id == run_id), None)
    if not run:
        raise HTTPException(404, "run not found")
    return run


@app.get("/api/evaluations")
def list_evaluations():
    return sd.EVALUATIONS


@app.get("/api/comparison")
def get_comparison(baseline: str = "E-2000", candidate: str = "E-2001"):
    c = sd.COMPARISON
    if {baseline, candidate} != {c.baseline_eval_id, c.candidate_eval_id}:
        raise HTTPException(404, "comparison not available for these evaluations")
    return c
