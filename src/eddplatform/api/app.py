"""FastAPI 应用：用例评估管理系统的领域 API（零假数据，全部走 MySQL store）。

    uvicorn eddplatform.api.app:app --reload
    → http://127.0.0.1:8000/docs   OpenAPI（web/ 前端经 vite 代理调 /api）
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from eddplatform.api import case_yaml, git_resolve, run_service
from eddplatform.domain.models import (Case, DatasetInfo, EvalProgram, PreconditionKind,
                                       RunRecord, System, SystemProgram, TagNode, Task)
from eddplatform.store import (CaseStore, DatasetStore, EvalProgramStore, RunStore,
                               SystemProgramStore, SystemStore, TagStore, TaskStore)

app = FastAPI(
    title="EddPlatform",
    version="0.0.1",
    description="评估驱动研发平台 — 版本化一次性沙箱 + 用例驱动发布评估 + 老新对比。",
)

# 仓库根：src/eddplatform/api/app.py -> parents[3]
PROTOTYPE = Path(__file__).resolve().parents[3] / "prototype" / "index.html"

store = CaseStore()
dataset_store = DatasetStore()
tag_store = TagStore()
system_store = SystemStore()
system_program_store = SystemProgramStore()
task_store = TaskStore()
eval_program_store = EvalProgramStore()
run_store = RunStore()


def _require_system(system_id: str) -> None:
    if system_store.get(system_id) is None:
        raise HTTPException(404, "system not found")


class ImportRequest(BaseModel):
    cases: list[Case]
    mode: str = "append"                  # append(按 id upsert) / replace(清空重建)


class YamlImportRequest(BaseModel):
    text: str
    mode: str = "append"


class TagCreate(BaseModel):
    name: str
    parent_id: str | None = None


class TagRename(BaseModel):
    name: str


@app.get("/", include_in_schema=False)
def index():
    if not PROTOTYPE.exists():
        return RedirectResponse("/docs")
    return FileResponse(PROTOTYPE)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


# --- 系统注册 --------------------------------------------------------------
@app.get("/api/systems")
def list_systems() -> list[System]:
    return system_store.list()


@app.get("/api/systems/{system_id}")
def get_system(system_id: str) -> System:
    system = system_store.get(system_id)
    if not system:
        raise HTTPException(404, "system not found")
    return system


@app.post("/api/systems", status_code=201)
def create_system(system: System) -> System:
    try:
        return system_store.create(system)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}")
def update_system(system_id: str, system: System) -> System:
    try:
        return system_store.update(system_id, system)
    except KeyError:
        raise HTTPException(404, "system not found")


@app.delete("/api/systems/{system_id}", status_code=204)
def delete_system(system_id: str) -> None:
    _require_system(system_id)
    if task_store.list(system_id) or run_store.list(system_id):
        raise HTTPException(409, "系统下还有任务或运行记录，先清理")
    try:
        system_store.delete(system_id)
    except KeyError:
        raise HTTPException(404, "system not found")


# --- 系统程序注册（被评系统的可部署 git 单元）------------------------------
@app.get("/api/systems/{system_id}/system-programs")
def list_system_programs(system_id: str) -> list[SystemProgram]:
    _require_system(system_id)
    return system_program_store.list(system_id)


@app.post("/api/systems/{system_id}/system-programs", status_code=201)
def create_system_program(system_id: str, program: SystemProgram) -> SystemProgram:
    _require_system(system_id)
    try:
        return system_program_store.create(system_id, program)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/system-programs/{program_id}")
def update_system_program(system_id: str, program_id: str, program: SystemProgram) -> SystemProgram:
    _require_system(system_id)
    try:
        return system_program_store.update(system_id, program_id, program)
    except KeyError:
        raise HTTPException(404, "system program not found")


@app.delete("/api/systems/{system_id}/system-programs/{program_id}", status_code=204)
def delete_system_program(system_id: str, program_id: str) -> None:
    _require_system(system_id)
    try:
        system_program_store.delete(system_id, program_id)
    except KeyError:
        raise HTTPException(404, "system program not found")


# --- git 解析（建任务时把 分支/commit 固化成双字段）-------------------------
class GitBranchQuery(BaseModel):
    git_url: str
    branch: str


class GitCommitQuery(BaseModel):
    git_url: str
    commit: str


@app.post("/api/git/resolve-branch")
def resolve_branch(body: GitBranchQuery):
    try:
        return git_resolve.resolve_branch(body.git_url, body.branch)
    except git_resolve.GitResolveError as e:
        raise HTTPException(400, str(e))


@app.post("/api/git/resolve-commit")
def resolve_commit(body: GitCommitQuery):
    try:
        return git_resolve.resolve_commit(body.git_url, body.commit)
    except git_resolve.GitResolveError as e:
        raise HTTPException(400, str(e))


class UnitQuery(BaseModel):
    git_url: str
    ref: str                              # commit（或分支）
    path: str = "."


@app.post("/api/git/validate-unit")
def validate_unit(body: UnitQuery):
    """在 仓库@ref 里校验单元文件夹是否满足 EDD 接入规范。"""
    try:
        return git_resolve.validate_unit(body.git_url, body.ref, body.path)
    except git_resolve.GitResolveError as e:
        raise HTTPException(400, str(e))


@app.get("/api/edd-unit-template")
def download_unit_template():
    """下载单元规范示例文件夹（edd_helm/，含 README 说明书）。"""
    import io
    import zipfile

    from fastapi.responses import Response

    root = Path(__file__).resolve().parents[3] / "examples" / "edd-unit-template"
    if not root.exists():
        raise HTTPException(404, "模板目录缺失")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(root.rglob("*")):
            if f.is_file():
                z.write(f, f"edd_helm/{f.relative_to(root)}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="edd_helm.zip"'})


# --- 评估程序注册 ----------------------------------------------------------
@app.get("/api/systems/{system_id}/eval-programs")
def list_eval_programs(system_id: str) -> list[EvalProgram]:
    _require_system(system_id)
    return eval_program_store.list(system_id)


@app.post("/api/systems/{system_id}/eval-programs", status_code=201)
def create_eval_program(system_id: str, program: EvalProgram) -> EvalProgram:
    _require_system(system_id)
    try:
        return eval_program_store.create(system_id, program)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/eval-programs/{program_id}")
def update_eval_program(system_id: str, program_id: str, program: EvalProgram) -> EvalProgram:
    _require_system(system_id)
    try:
        return eval_program_store.update(system_id, program_id, program)
    except KeyError:
        raise HTTPException(404, "eval program not found")


@app.delete("/api/systems/{system_id}/eval-programs/{program_id}", status_code=204)
def delete_eval_program(system_id: str, program_id: str) -> None:
    _require_system(system_id)
    try:
        eval_program_store.delete(system_id, program_id)
    except KeyError:
        raise HTTPException(404, "eval program not found")


# --- 评估任务（task + 前置条件）-------------------------------------------
@app.get("/api/systems/{system_id}/tasks")
def list_tasks(system_id: str) -> list[Task]:
    _require_system(system_id)
    return task_store.list(system_id)


@app.post("/api/systems/{system_id}/tasks", status_code=201)
def create_task(system_id: str, task: Task) -> Task:
    _require_system(system_id)
    try:
        return task_store.create(system_id, task)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/tasks/{task_id}")
def update_task(system_id: str, task_id: str, task: Task) -> Task:
    _require_system(system_id)
    try:
        return task_store.update(system_id, task_id, task)
    except KeyError:
        raise HTTPException(404, "task not found")


@app.delete("/api/systems/{system_id}/tasks/{task_id}", status_code=204)
def delete_task(system_id: str, task_id: str) -> None:
    _require_system(system_id)
    try:
        task_store.delete(system_id, task_id)
    except KeyError:
        raise HTTPException(404, "task not found")


@app.post("/api/systems/{system_id}/tasks/{task_id}/run", status_code=202)
async def run_task_endpoint(system_id: str, task_id: str) -> RunRecord:
    _require_system(system_id)
    task = task_store.get(system_id, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    # 逐用例分派的 code 来自「启动评估程序」前置条件引用的注册项
    eval_program = None
    for pc in task.preconditions:
        if pc.kind == PreconditionKind.START_EVAL_PROGRAM and pc.program_id:
            eval_program = eval_program_store.get(system_id, pc.program_id)
            if eval_program is None:
                raise HTTPException(409, f"评估程序 {pc.program_id} 不存在（已被删除？）")
            break
    all_cases = []
    if task.dataset_id:
        if dataset_store.get(system_id, task.dataset_id) is None:
            raise HTTPException(409, f"用例库 {task.dataset_id} 不存在（已被删除？）")
        all_cases = [c for c in store.list_cases(system_id, task.dataset_id) if c.enabled]
        if task.case_ids is not None:
            picked = set(task.case_ids)
            all_cases = [c for c in all_cases if c.id in picked]
    cases = [run_service.case_to_spec(c) for c in all_cases]
    try:
        return await run_service.start_run(system_id, task, eval_program=eval_program,
                                           cases=cases, run_store=run_store)
    except ConnectionError as e:
        raise HTTPException(503, str(e))


# --- 运行记录 --------------------------------------------------------------
@app.get("/api/runs")
def list_runs(system_id: str | None = None) -> list[RunRecord]:
    return run_store.list(system_id)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = run_store.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {**run.model_dump(),
            "case_results": [c.model_dump() for c in run_store.case_results(run_id)]}


# --- 用例库（一系统多库）与用例 --------------------------------------------
def _require_dataset(system_id: str, dataset_id: str) -> None:
    if dataset_store.get(system_id, dataset_id) is None:
        raise HTTPException(404, "dataset not found")


@app.get("/api/systems/{system_id}/datasets")
def list_datasets(system_id: str) -> list[DatasetInfo]:
    _require_system(system_id)
    return dataset_store.list(system_id)


@app.post("/api/systems/{system_id}/datasets", status_code=201)
def create_dataset(system_id: str, dataset: DatasetInfo) -> DatasetInfo:
    _require_system(system_id)
    try:
        return dataset_store.create(system_id, dataset)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/datasets/{dataset_id}")
def update_dataset(system_id: str, dataset_id: str, dataset: DatasetInfo) -> DatasetInfo:
    _require_system(system_id)
    try:
        return dataset_store.update(system_id, dataset_id, dataset)
    except KeyError:
        raise HTTPException(404, "dataset not found")


@app.delete("/api/systems/{system_id}/datasets/{dataset_id}", status_code=204)
def delete_dataset(system_id: str, dataset_id: str) -> None:
    _require_system(system_id)
    if any(t.dataset_id == dataset_id for t in task_store.list(system_id)):
        raise HTTPException(409, "有评估任务引用该用例库，先修改任务")
    try:
        dataset_store.delete(system_id, dataset_id)
    except KeyError:
        raise HTTPException(404, "dataset not found")
    # 级联删除库内用例
    conn = store.db.connect()
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM cases WHERE system_id=%s AND dataset_id=%s",
                      (system_id, dataset_id))
        conn.commit()
    finally:
        conn.close()


@app.get("/api/systems/{system_id}/datasets/{dataset_id}/cases")
def list_dataset_cases(system_id: str, dataset_id: str) -> list[Case]:
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    return store.list_cases(system_id, dataset_id)


@app.post("/api/systems/{system_id}/datasets/{dataset_id}/cases", status_code=201)
def create_case(system_id: str, dataset_id: str, case: Case) -> Case:
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    try:
        return store.add_case(system_id, dataset_id, case)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/datasets/{dataset_id}/cases/{case_id}")
def update_case(system_id: str, dataset_id: str, case_id: str, case: Case) -> Case:
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    try:
        return store.update_case(system_id, dataset_id, case_id, case)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.delete("/api/systems/{system_id}/datasets/{dataset_id}/cases/{case_id}", status_code=204)
def delete_case(system_id: str, dataset_id: str, case_id: str) -> None:
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    try:
        store.delete_case(system_id, dataset_id, case_id)
    except KeyError:
        raise HTTPException(404, "case not found")


@app.get("/api/systems/{system_id}/datasets/{dataset_id}/cases/export")
def export_cases(system_id: str, dataset_id: str) -> list[Case]:
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    return store.export_cases(system_id, dataset_id)


@app.post("/api/systems/{system_id}/datasets/{dataset_id}/cases/import")
def import_cases(system_id: str, dataset_id: str, body: ImportRequest):
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    try:
        res = store.import_cases(system_id, dataset_id, body.cases, mode=body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"added": res.added, "updated": res.updated, "total": res.total}


@app.post("/api/systems/{system_id}/datasets/{dataset_id}/cases/import-yaml")
def import_cases_yaml(system_id: str, dataset_id: str, body: YamlImportRequest):
    _require_system(system_id)
    _require_dataset(system_id, dataset_id)
    try:
        cases = case_yaml.parse_eval_yaml(body.text)
        res = store.import_cases(system_id, dataset_id, cases, mode=body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"added": res.added, "updated": res.updated, "total": res.total}


# --- 标签管理（分层）------------------------------------------------------
@app.get("/api/systems/{system_id}/tags")
def list_tags(system_id: str) -> list[TagNode]:
    _require_system(system_id)
    return tag_store.list_tags(system_id)


@app.post("/api/systems/{system_id}/tags", status_code=201)
def create_tag(system_id: str, body: TagCreate) -> TagNode:
    _require_system(system_id)
    try:
        return tag_store.add_tag(system_id, body.name, body.parent_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.put("/api/systems/{system_id}/tags/{tag_id}")
def rename_tag(system_id: str, tag_id: str, body: TagRename) -> TagNode:
    _require_system(system_id)
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
    _require_system(system_id)
    try:
        tag_store.delete_tag(system_id, tag_id)
    except KeyError:
        raise HTTPException(404, "tag not found")
