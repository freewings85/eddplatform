"""被评系统的入口抽象（Target）——把系统当黑盒，与它用什么框架无关。

- ``CallableTarget``  进程内可调用（测试 / 同语言集成）
- ``HttpTarget``      HTTP 入口（沙箱里拉起的整系统；pydantic-ai / LangGraph / 任意服务通用）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class CallableTarget:
    fn: Callable[[Any], Any]

    def __call__(self, inputs: Any) -> Any:
        return self.fn(inputs)


@dataclass
class HttpTarget:
    """POST 用例输入到系统入口，取回输出。系统是什么框架写的无所谓。

    ``stream=True`` 时用流式请求，掐**首字节时间**作为 TTFT 兜底，记在 ``last_meta``。
    首选 TTFT 来源仍是被评系统 emit ``completion_start_time`` 到 trace（见 spec）；
    此路径用于被评系统未 emit 时。
    """

    url: str
    method: str = "POST"
    timeout: float = 30.0
    input_key: str | None = None      # None: 整个 inputs 作 body；否则包成 {input_key: inputs}
    stream: bool = False
    last_meta: dict = field(default_factory=dict)   # 每次调用后：{ttft_s?} 等信号

    def __call__(self, inputs: Any) -> Any:
        import httpx

        payload = inputs if self.input_key is None else {self.input_key: inputs}
        if not self.stream:
            self.last_meta = {}
            resp = httpx.request(self.method, self.url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            return resp.json() if "application/json" in ctype else resp.text

        t0 = time.perf_counter()
        ttft: float | None = None
        chunks: list[bytes] = []
        with httpx.stream(self.method, self.url, json=payload, timeout=self.timeout) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_bytes():
                if chunk and ttft is None:
                    ttft = time.perf_counter() - t0
                chunks.append(chunk)
        self.last_meta = {"ttft_s": ttft}
        text = b"".join(chunks).decode("utf-8", "replace")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text
