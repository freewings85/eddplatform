"""真实一次性环境 provider：kubectl 把 manifest 部署到独立 namespace → 等就绪 → 销。

实现 orchestration.providers.EnvironmentProvider。对当前 kube context（本地 k3d 集群
或任意真实集群）操作，用纯 kubectl（无需 python k8s 客户端）。每个系统版本一个
namespace（对应"两个 namespace"的设计）；跑完 destroy 删 namespace（ephemeral）。

manifest 结构（来自 orchestration.manifest.render_manifest，可加 port/env/replicas）::

    {"system_id","version","services":[{"name","image","port"?,"env"?,"replicas"?}, ...]}
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass

from eddplatform.domain.models import RunStatus


def _namespace_name(prefix: str, version: str) -> str:
    """把 ``<prefix>-<version>`` 清成合法 k8s namespace(DNS-1123 label)。

    版本号常含点(如 ``2.3``)，而 namespace 名只允许小写字母/数字/``-`` → 点等替成 ``-``。
    """
    safe = re.sub(r"[^a-z0-9-]", "-", f"{prefix}-{version}".lower())
    return safe.strip("-")


def available() -> bool:
    """kubectl 在 PATH 且能连上集群。"""
    if shutil.which("kubectl") is None:
        return False
    r = subprocess.run(["kubectl", "cluster-info"], capture_output=True, text=True)
    return r.returncode == 0


def _kubectl(args: list[str], stdin: str | None = None, check: bool = True):
    return subprocess.run(["kubectl", *args], input=stdin, text=True,
                          capture_output=True, check=check)


def _deployment(name: str, image: str, *, command: list[str] | None = None,
                args: list[str] | None = None, ports: list[int] | None = None,
                replicas: int = 1, env: dict | None = None) -> dict:
    ports = ports or []
    container: dict = {
        "name": name, "image": image,
        "imagePullPolicy": "IfNotPresent",   # 用 k3d image import 的本地镜像，不去公网拉
        "ports": [{"containerPort": p} for p in ports],
        "env": [{"name": k, "value": str(v)} for k, v in (env or {}).items()],
    }
    if command:
        container["command"] = list(command)
    if args:
        container["args"] = list(args)
    return {
        "apiVersion": "apps/v1", "kind": "Deployment",
        "metadata": {"name": name, "labels": {"app": name}},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": {"app": name}},
                "spec": {
                    "containers": [container],
                    # ndots:1 让外部域名(≥1 点，如 dashscope.aliyuncs.com)先按绝对名解析，
                    # 绕开宿主注入的通配 search 域(如 *.51cjml.com)；单标签服务名(kafka 等)
                    # 仍走 search 域在集群内解析。
                    "dnsConfig": {"options": [{"name": "ndots", "value": "1"}]},
                },
            },
        },
    }


def _service(name: str, ports: list[int]) -> dict:
    return {
        "apiVersion": "v1", "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": {"app": name},
                 "ports": [{"name": f"p{p}", "port": p, "targetPort": p} for p in ports]},
    }


@dataclass
class K8sProvider:
    namespace_prefix: str = "edd"
    wait_timeout: str = "120s"
    default_port: int = 80

    def _require(self) -> None:
        if not available():
            raise RuntimeError(
                "K8sProvider 需要 kubectl + 可用 k8s 集群（如本地 k3d）。"
                "离线无集群请用 orchestration.providers.MockProvider。"
            )

    def create(self, manifest: dict, ttl_hours: float = 2.0) -> str:
        self._require()
        ns = _namespace_name(self.namespace_prefix, manifest.get("version", "env"))
        # namespace 用 apply（幂等，重跑不炸）
        _kubectl(["apply", "-f", "-"], stdin=json.dumps(
            {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": ns}}))
        # 基础服务先起(kafka/redis/pg…)，业务进程依赖它们
        base = manifest.get("base_services", [])
        services = manifest.get("services", [])
        for svc in base + services:
            ports = [int(p) for p in svc.get("ports", [])] or [self.default_port]
            dep = _deployment(svc["name"], svc["image"],
                              command=svc.get("command"), args=svc.get("args"),
                              ports=ports, replicas=int(svc.get("replicas", 1)),
                              env=svc.get("env", {}))
            _kubectl(["apply", "-n", ns, "-f", "-"], stdin=json.dumps(dep))
            _kubectl(["apply", "-n", ns, "-f", "-"], stdin=json.dumps(_service(svc["name"], ports)))
        for svc in base + services:
            _kubectl(["rollout", "status", "-n", ns, f"deployment/{svc['name']}",
                      "--timeout", self.wait_timeout])
        return ns

    def status(self, env_id: str) -> RunStatus:
        self._require()
        r = _kubectl(["get", "namespace", env_id], check=False)
        return RunStatus.RUNNING if r.returncode == 0 else RunStatus.DESTROYED

    def destroy(self, env_id: str) -> None:
        self._require()
        _kubectl(["delete", "namespace", env_id, "--wait=false"], check=False)
