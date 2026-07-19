"""FastAPI 应用：把原型当作当前 UI 端起来 + 暴露领域数据接口（读，占位）。

    uvicorn eddplatform.api.app:app --reload
    → http://127.0.0.1:8000        原型
    → http://127.0.0.1:8000/docs   OpenAPI
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from eddplatform.api import sample_data as sd
from eddplatform.domain.models import Case, Dataset, TagNode
from eddplatform.store import CaseStore, TagStore

app = FastAPI(
    title="EddPlatform",
    version="0.0.1",
    description="评估驱动研发平台 — 版本化一次性沙箱 + 用例驱动发布评估 + 老新对比。",
)

# 仓库根：src/eddplatform/api/app.py -> parents[3]
PROTOTYPE = Path(__file__).resolve().parents[3] / "prototype" / "index.html"

# 用例 + 标签持久化（sqlite）。首次用示例数据播种，保证 UI 不空。
store = CaseStore()
store.seed_if_empty(sd.DATASET.system_id, sd.DATASET.cases)
tag_store = TagStore()
tag_store.seed_if_empty(sd.DATASET.system_id, sd.SEED_TAGS)


def _dataset_meta(system_id: str) -> tuple[str, list[str]]:
    """dataset 级元信息（静态）：name 与可用评估器；cases 由 store 提供。"""
    if sd.DATASET.system_id == system_id:
        return sd.DATASET.name, sd.DATASET.evaluator_names
    system = sd.system_by_id(system_id)
    return (system.name if system else system_id), []


class ImportRequest(BaseModel):
    cases: list[Case]
    mode: str = "append"                  # append(按 id upsert) / replace(清空重建)


class TagCreate(BaseModel):
    name: str
    parent_id: str | None = None


class TagRename(BaseModel):
    name: str


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


# --- 用例集（dataset 元信息静态 + cases 落 sqlite）------------------------
@app.get("/api/systems/{system_id}/dataset")
def get_dataset(system_id: str) -> Dataset:
    name, evaluator_names = _dataset_meta(system_id)
    return Dataset(
        name=name,
        system_id=system_id,
        evaluator_names=evaluator_names,
        cases=store.list_cases(system_id),
    )


# --- 用例管理（CRUD + 导入导出）-------------------------------------------
@app.post("/api/systems/{system_id}/cases", status_code=201)
def create_case(system_id: str, case: Case) -> Case:
    try:
        return store.add_case(system_id, case)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/cases/{case_id}")
def update_case(system_id: str, case_id: str, case: Case) -> Case:
    try:
        return store.update_case(system_id, case_id, case)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.delete("/api/systems/{system_id}/cases/{case_id}", status_code=204)
def delete_case(system_id: str, case_id: str) -> None:
    try:
        store.delete_case(system_id, case_id)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.get("/api/systems/{system_id}/cases/export")
def export_cases(system_id: str) -> list[Case]:
    return store.export_cases(system_id)


@app.post("/api/systems/{system_id}/cases/import")
def import_cases(system_id: str, body: ImportRequest):
    try:
        res = store.import_cases(system_id, body.cases, mode=body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"added": res.added, "updated": res.updated, "total": res.total}


# --- 标签管理（分层）------------------------------------------------------
@app.get("/api/systems/{system_id}/tags")
def list_tags(system_id: str) -> list[TagNode]:
    return tag_store.list_tags(system_id)


@app.post("/api/systems/{system_id}/tags", status_code=201)
def create_tag(system_id: str, body: TagCreate) -> TagNode:
    try:
        return tag_store.add_tag(system_id, body.name, body.parent_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/tags/{tag_id}")
def rename_tag(system_id: str, tag_id: str, body: TagRename) -> TagNode:
    try:
        node, old_path, new_path = tag_store.rename_tag(system_id, tag_id, body.name)
    except KeyError:
        raise HTTPException(404, "tag not found")
    except ValueError as e:
        raise HTTPException(409, str(e))
    store.rewrite_tag_prefix(system_id, old_path, new_path)  # 同步 case 上的标签路径
    return node


@app.delete("/api/systems/{system_id}/tags/{tag_id}", status_code=204)
def delete_tag(system_id: str, tag_id: str) -> None:
    try:
        tag_store.delete_tag(system_id, tag_id)
    except KeyError:
        raise HTTPException(404, "tag not found")


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
