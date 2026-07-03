"""被评系统的入口抽象（Target）——把系统当黑盒，与它用什么框架无关。

- ``CallableTarget``  进程内可调用（测试 / 同语言集成）
- ``HttpTarget``      HTTP 入口（沙箱里拉起的整系统；pydantic-ai / LangGraph / 任意服务通用）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class CallableTarget:
    fn: Callable[[Any], Any]

    def __call__(self, inputs: Any) -> Any:
        return self.fn(inputs)


@dataclass
class HttpTarget:
    """POST 用例输入到系统入口，取回输出。系统是什么框架写的无所谓。"""

    url: str
    method: str = "POST"
    timeout: float = 30.0
    input_key: str | None = None      # None: 整个 inputs 作 body；否则包成 {input_key: inputs}

    def __call__(self, inputs: Any) -> Any:
        import httpx

        payload = inputs if self.input_key is None else {self.input_key: inputs}
        resp = httpx.request(self.method, self.url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        return resp.json() if "application/json" in ctype else resp.text
