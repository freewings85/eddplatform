"""端到端验证：一份具体版本的 git 代码 → 平台按约定拉起到 k8s。

真实链路（需要本机有 k3s + helm + buildah + git，见 deploy/k3s 说明）：
  1. 用 examples/demo-system 造一个**真实 git 仓库**，提交两个版本（v1 / v2）；
  2. 平台 ConventionDeployer 按 .eddplatform.yaml 约定：clone→build→导镜像→helm 部署；
  3. 分别部署 v1、v2 到两个一次性 namespace，验证服务真的起来、且版本各自正确；
  4. 打印结构化 {服务: 镜像ref}（带 commit sha）——证明版本可感知；
  5. 销毁。

    python examples/e2e_convention_deploy.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from eddplatform.runtime import ConventionDeployer

DEMO = Path(__file__).resolve().parent / "demo-system"


def sh(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(tmp: Path) -> tuple[str, dict[str, str]]:
    """把 demo-system 拷成一个真实 git 仓库，提交 v1、v2 两个版本，返回 (repo_url, {ver: sha})。"""
    repo = tmp / "demo-system-src"
    shutil.copytree(DEMO, repo)
    sh("git", "init", "-q", cwd=repo)
    sh("git", "config", "user.email", "e2e@edd.local", cwd=repo)
    sh("git", "config", "user.name", "edd-e2e", cwd=repo)
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "demo-system v1", cwd=repo)
    sha_v1 = sh("git", "rev-parse", "HEAD", cwd=repo)

    # 造第二个版本：把两个服务的页面从 v1 改成 v2
    for svc in ("quote", "gateway"):
        p = repo / "services" / svc / "index.html"
        p.write_text(p.read_text().replace("v1", "v2"))
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-qm", "demo-system v2", cwd=repo)
    sha_v2 = sh("git", "rev-parse", "HEAD", cwd=repo)

    return f"file://{repo}", {"v1": sha_v1, "v2": sha_v2}


def served_text(namespace: str, deploy: str = "quote") -> str:
    return sh("kubectl", "-n", namespace, "exec", f"deploy/{deploy}", "--", "wget", "-qO-", "localhost")


def main() -> int:
    deployer = ConventionDeployer()
    results = {}
    ok = True
    with tempfile.TemporaryDirectory(prefix="edd-e2e-") as tmp:
        repo_url, shas = make_repo(Path(tmp))
        print(f"真实 git 仓库: {repo_url}")
        print(f"版本: v1={shas['v1'][:12]}  v2={shas['v2'][:12]}\n")

        for ver in ("v1", "v2"):
            ns = f"edd-e2e-{ver}"
            print(f"===== 部署 {ver} → ns/{ns} =====")
            try:
                res = deployer.deploy(git_url=repo_url, ref=shas[ver], release="demo", namespace=ns)
                results[ver] = res
                text = served_text(ns)
                print(f"服务返回: {text!r}")
                expect = f"demo-system {ver}"
                all_running = all(p.endswith("Running") for p in res.pods)
                if expect in text and all_running:
                    print(f"✓ {ver} OK：内容含「{expect}」、pod 全部 Running\n")
                else:
                    ok = False
                    print(f"✗ {ver} FAIL：期望含「{expect}」、pods={res.pods}\n")
            except Exception as e:  # noqa: BLE001
                ok = False
                print(f"✗ {ver} 部署异常: {e}\n")

        print("===== 结构化结果（版本可感知）=====")
        for ver, res in results.items():
            print(f"{ver}: ref={res.ref[:12]} images={res.images}")

        print("\n===== 销毁 =====")
        for ver in results:
            deployer.destroy(release="demo", namespace=f"edd-e2e-{ver}")

    print("\n" + ("✅ 端到端通过" if ok else "❌ 端到端失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
