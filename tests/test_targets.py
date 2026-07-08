"""被评系统入口 Target：HTTP 黑盒 + 可选流式测 TTFT（兜底路径）。"""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eddplatform.evals.targets import HttpTarget


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        time.sleep(0.15)                       # 首字节前固定延迟 → TTFT 应 ≥ 0.1s
        body = b'{"premium": 4260}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/quote"
    srv.shutdown()


def test_http_target_blocking_returns_json(server):
    tgt = HttpTarget(url=server)
    assert tgt({"car": "ev"}) == {"premium": 4260}
    assert tgt.last_meta == {}                 # 非流式不记 TTFT


def test_http_target_stream_records_ttft(server):
    tgt = HttpTarget(url=server, stream=True)
    out = tgt({"car": "ev"})
    assert out == {"premium": 4260}            # 流式也能拼回完整 JSON
    assert tgt.last_meta.get("ttft_s") is not None
    assert tgt.last_meta["ttft_s"] >= 0.1      # 服务器首字节前 sleep 0.15s
