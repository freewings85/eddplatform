"""Temporal 编排：EDD 启动一个 task = 把参数传给 Temporal，拉起 workflow 来跑。

- ``workflows.RunTaskWorkflow``：按序执行 task 的前置条件（启动系统 / 启动评估程序 /
  自定义脚本），再让评估程序观测系统，产出运行记录。
- ``activities``：把真正干活的部分（约定式部署、跑脚本、评估观测）包成 Temporal 活动。
- ``worker`` / ``client``：worker 托管 workflow+活动；client 是 EDD 侧提交入口。

需要 ``pip install -e '.[temporal]'`` 和一个 Temporal server（本地 ``temporal server start-dev``）。
"""

from eddplatform.runtime.temporal.shared import (
    TASK_QUEUE,
    OutcomeOut,
    PreconditionSpec,
    RunTaskInput,
    RunTaskOutput,
    to_spec,
)

__all__ = [
    "TASK_QUEUE",
    "PreconditionSpec",
    "RunTaskInput",
    "RunTaskOutput",
    "OutcomeOut",
    "to_spec",
]
