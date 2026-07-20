"""约定式部署器：一份具体版本的 git 代码 → 跑起来（helm 部署到一次性 namespace）。

流程（``start_system`` / ``start_eval_program`` 前置条件的执行）::

    clone+checkout(ref) → 读单元(build.sh + chart/) → 跑 build 脚本(产镜像 tar+images.json)
    → 把镜像送进集群(image sink) → helm upgrade --install 到 namespace(--wait)

产出 ``DeployResult``，带**结构化的 {服务: 镜像ref}**——版本可感知，供运行记录打标签、
做老新对比、复现。镜像"送进集群"这一步是**可插拔**的：本地 e2e 用 `k3s ctr import`，
生产换成 push 到 Harbor 即可，部署器其余不变。
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from eddplatform.runtime.convention import BUILD_SCRIPT, CHART_DIR, read_unit

# 默认「镜像送进集群」的命令前缀（本地 k3s：导进 containerd 的 k8s.io 命名空间）。
DEFAULT_IMAGE_IMPORT: list[str] = ["sudo", "k3s", "ctr", "-n", "k8s.io", "images", "import"]
DEFAULT_KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"


@dataclass
class DeployResult:
    release: str
    namespace: str
    ref: str                           # 解析出的 git commit sha
    image_tag: str                     # 构建用的 tag（短 sha）
    images: dict[str, str]             # 服务 -> 镜像 ref（结构化，版本可感知）
    pods: list[str] = field(default_factory=list)


class ConventionDeployer:
    def __init__(
        self,
        *,
        kubeconfig: str | None = None,
        image_import_cmd: Sequence[str] | None = None,
        helm_bin: str = "helm",
        kubectl_bin: str = "kubectl",
        git_bin: str = "git",
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.kubeconfig = kubeconfig or os.environ.get("KUBECONFIG", DEFAULT_KUBECONFIG)
        self.image_import_cmd = list(image_import_cmd or DEFAULT_IMAGE_IMPORT)
        self.helm_bin = helm_bin
        self.kubectl_bin = kubectl_bin
        self.git_bin = git_bin
        self._log = log or (lambda m: print(m))

    # --- 对外 ------------------------------------------------------------
    def deploy(
        self,
        *,
        git_url: str,
        ref: str,
        release: str,
        namespace: str,
        path: str = ".",
        timeout: str = "120s",
    ) -> DeployResult:
        with tempfile.TemporaryDirectory(prefix="edd-deploy-") as tmp:
            repo = Path(tmp) / "repo"
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()

            self._log(f"[1/5] clone {git_url} @ {ref} (单元目录: {path})")
            sha = self._checkout(git_url, ref, repo)
            image_tag = sha[:12]

            unit = repo / path
            spec = read_unit(repo, path)
            # release 名 = chart/Chart.yaml 的 name（helm 原生语义，配置跟代码走）
            release = spec.name
            self._log(f"[2/5] 单元: name={spec.name} services={spec.services} → release={release}")

            self._log(f"[3/5] 跑构建脚本 {BUILD_SCRIPT} (EDD_IMAGE_TAG={image_tag})")
            self._run_build(unit, BUILD_SCRIPT, image_tag, out_dir)
            images = json.loads((out_dir / "images.json").read_text())

            self._log(f"[4/5] 送镜像进集群: {list(images.values())}")
            for tar in sorted(out_dir.glob("*.tar")):
                self._run([*self.image_import_cmd, str(tar)])

            self._log(f"[5/5] helm 部署 {release} -> ns/{namespace}")
            self._helm_install(unit / CHART_DIR, release, namespace, images, timeout)

            pods = self._pods(namespace)
            self._log(f"✓ 部署完成，{len(pods)} 个 pod: {', '.join(pods)}")
            return DeployResult(
                release=release, namespace=namespace, ref=sha,
                image_tag=image_tag, images=images, pods=pods,
            )

    def uninstall(self, *, release: str, namespace: str) -> None:
        """卸一个 helm release（不删 namespace，供同 ns 多 release 场景）。"""
        self._run(
            [self.helm_bin, "uninstall", release, "-n", namespace], check=False, env=self._kube_env()
        )

    def delete_namespace(self, namespace: str) -> None:
        self._run(
            [self.kubectl_bin, "delete", "ns", namespace, "--wait=false"],
            check=False, env=self._kube_env(),
        )

    def destroy(self, *, release: str, namespace: str) -> None:
        self.uninstall(release=release, namespace=namespace)
        self.delete_namespace(namespace)
        self._log(f"✓ 已销毁 {release} / ns {namespace}")

    # --- 内部 ------------------------------------------------------------
    def _checkout(self, git_url: str, ref: str, repo: Path) -> str:
        self._run([self.git_bin, "clone", "--quiet", git_url, str(repo)])
        self._run([self.git_bin, "-C", str(repo), "checkout", "--quiet", ref])
        return self._run([self.git_bin, "-C", str(repo), "rev-parse", "HEAD"]).strip()

    def _run_build(self, unit: Path, build: str, image_tag: str, out_dir: Path) -> None:
        script = (unit / build).resolve()
        if not script.exists():
            raise FileNotFoundError(f"构建脚本不存在: {script}")
        env = {**os.environ, "EDD_IMAGE_TAG": image_tag, "EDD_OUT_DIR": str(out_dir)}
        self._run(["bash", str(script)], cwd=unit, env=env)
        if not (out_dir / "images.json").exists():
            raise RuntimeError("构建脚本没有产出 images.json（约定：写到 $EDD_OUT_DIR/images.json）")

    def _helm_install(
        self, chart: Path, release: str, namespace: str, images: dict[str, str], timeout: str
    ) -> None:
        cmd = [
            self.helm_bin, "upgrade", "--install", release, str(chart),
            "-n", namespace, "--create-namespace", "--wait", "--timeout", timeout,
        ]
        for svc, image in images.items():
            cmd += ["--set", f"services.{svc}.image={image}"]
        self._run(cmd, env=self._kube_env())

    def _pods(self, namespace: str) -> list[str]:
        out = self._run(
            [self.kubectl_bin, "-n", namespace, "get", "pods",
             "-o", "jsonpath={range .items[*]}{.metadata.name}{\" \"}{.status.phase}{\"\\n\"}{end}"],
            env=self._kube_env(),
        )
        return [line.strip() for line in out.splitlines() if line.strip()]

    def _kube_env(self) -> dict[str, str]:
        return {**os.environ, "KUBECONFIG": self.kubeconfig}

    def _run(
        self, cmd: Sequence[str], *, cwd: Path | None = None,
        env: dict | None = None, check: bool = True,
    ) -> str:
        proc = subprocess.run(
            list(cmd), cwd=cwd, env=env, check=False,
            capture_output=True, text=True,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"命令失败({proc.returncode}): {' '.join(cmd)}\n"
                f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
            )
        return proc.stdout
