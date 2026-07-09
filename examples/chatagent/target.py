"""EDD target：把一条用例(多轮)打进部署在 k8s 里的 chatagent 入口(/chat/run)，
聚合最终回复 + 工具调用轨迹 + token 用量 + 端到端时延，交给评估器。

访问方式：``kubectl exec`` 进入入口进程 pod 用 curl 打 localhost:<port>/chat/run
（无状态、无需管理 port-forward 生命周期）。请求体 JSON 走 stdin，避免 shell 引号问题。

返回 dict（即评估上下文的 output）::

    {"output": <最终回复文本>,
     "tool_calls": [{"tool_name": str, "args": dict}, ...],   # 跨全部轮次、args 已解析
     "usage": {"input_tokens","output_tokens","total_tokens", ...},
     "latency_s": float}
"""

from __future__ import annotations

import itertools
import json
import subprocess
import time
from typing import Any, Callable

_SESSION = itertools.count(1)


def _post_chat_run(namespace: str, entry: str, port: int, body: dict, timeout: int = 120) -> dict:
    proc = subprocess.run(
        ["kubectl", "exec", "-i", "-n", namespace, f"deploy/{entry}", "--",
         "curl", "-s", "-m", "100", "-X", "POST", f"localhost:{port}/chat/run",
         "-H", "Content-Type: application/json", "-d", "@-"],
        input=json.dumps(body), text=True, capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"/chat/run exec 失败: {proc.stderr[:300]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"/chat/run 返回非 JSON: {proc.stdout[:300]}") from e


def make_chatagent_target(
    namespace: str, entry: str = "mainagent", port: int = 8100, user_id: str = "edd",
    agent_type: str | None = None,
) -> Callable[[Any], dict]:
    """构造打某个 namespace 里 chatagent 入口的 target。

    ``agent_type``：2.0(chatagent2) 需按场景指定跑哪个 agent；2.3(单 hlsc_agent) 留 None。
    """

    def target(inputs: Any) -> dict:
        turns = inputs.get("turns") or [{"user": inputs.get("message", "")}]
        session_id = f"edd-{next(_SESSION)}-{int(time.time())}"
        tool_calls: list[dict] = []
        usage: dict = {}
        output = ""
        detail = None
        t0 = time.perf_counter()
        for turn in turns:
            body = {"session_id": session_id, "user_id": user_id, "message": turn["user"]}
            if agent_type:
                body["agent_type"] = agent_type
            resp = _post_chat_run(namespace, entry, port, body)
            if "output" not in resp:                       # 错误响应如 {"detail": "..."}
                detail = resp.get("detail") or str(resp)[:200]
                continue
            output = resp.get("output") or output
            for msg in resp.get("new_messages") or []:
                for tc in msg.get("tool_calls") or []:
                    args = tc.get("args")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"_raw": args}
                    tool_calls.append({"tool_name": tc.get("tool_name"), "args": args or {}})
            usage = resp.get("usage") or usage
        return {"output": output, "tool_calls": tool_calls, "usage": usage,
                "latency_s": time.perf_counter() - t0, "error": detail}

    return target
