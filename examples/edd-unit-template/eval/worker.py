"""Temporal 入口（与 cases 代码分离——业务子目录里只有纯 pydantic-evals）。

汇总各业务子目录的 (dataset, task)，serve() 一行接入 EDD。
"""
from quiz import cases as quiz

from edd_bridge import serve

if __name__ == "__main__":
    serve("capital-quiz-eval", [           # workflow 名=队列名（平台用例库里配同名）
        (quiz.dataset, quiz.task),
        # (order.dataset, order.task),     # 更多业务子目录在此追加
    ])
