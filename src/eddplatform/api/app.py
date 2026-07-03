"""FastAPI 应用：把原型当作当前 UI 端起来 + 暴露领域数据接口（读，占位）。

    uvicorn eddplatform.api.app:app --reload
    → http://127.0.0.1:8000        原型
    → http://127.0.0.1:8000/docs   OpenAPI
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from eddplatform.api import sample_data as sd

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
def get_dataset(system_id: str):
    if sd.DATASET.system_id != system_id:
        raise HTTPException(404, "dataset not found")
    return sd.DATASET


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
