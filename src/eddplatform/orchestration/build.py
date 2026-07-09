"""EDD 构建步骤：按 SystemVersion 钉住的分支把 Module build 成镜像并导入 k3d 集群。

真实多进程系统的每个进程来自某个 git 项目的某个分支(+启动配置)。本模块负责：
用 ``git worktree`` 在临时目录把该分支 checkout 出来(**不动主工作树、也不与已 checkout
的分支冲突** —— 用 --detach 落在该 commit)，``docker build`` 出镜像，再 ``k3d image
import`` 塞进集群 containerd(配合 Deployment 的 imagePullPolicy=IfNotPresent，跑时不拉网)。

镜像命名 ``edd/<system_id>-<module>:<tag>``；tag 用钉住的分支名(非法字符替换)。
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Callable

from eddplatform.domain.models import Module


def image_ref(system_id: str, module_name: str, tag: str) -> str:
    """稳定的本地镜像名。tag 里的 ``/`` 等替成 ``-``（docker tag 不允许 ``/`` 在 tag 段）。"""
    safe = tag.replace("/", "-").replace(":", "-")
    return f"edd/{system_id}-{module_name}:{safe}"


def _run(cmd: list[str], log: Callable[[str], None], **kw):
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def build_module_image(
    module: Module,
    *,
    ref: str,
    system_id: str,
    cluster: str = "edd",
    import_to_cluster: bool = True,
    from_working_tree: bool = False,
    log: Callable[[str], None] | None = None,
) -> str:
    """把 ``module`` 在 ``ref``(分支/commit) 上 build 成镜像并(可选)导入集群，返回镜像名。

    - ``module.git_url``：本地仓库路径。
    - ``module.dockerfile`` / ``module.context``：相对仓库根。
    - 若 ``module.image`` 已给(预构建镜像)，直接返回它，不 build。
    - ``from_working_tree``：直接从**工作树** build（含生成的/被 .gitignore 的运行期必需文件，
      如 chatagent2 的 ``allprojects.md``），而非干净 git worktree checkout。需保证工作树已
      在目标 ``ref`` 上（会校验并在不符时告警）。
    """
    _log = log or (lambda _m: None)
    if module.image:
        return module.image
    img = image_ref(system_id, module.name, ref)
    repo = module.git_url

    if from_working_tree:
        cur = subprocess.run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        if cur != ref:
            _log(f"⚠ 工作树在 '{cur}' 而非 '{ref}'——from_working_tree 用的是工作树当前内容")
        dockerfile = os.path.join(repo, module.dockerfile.lstrip("./"))
        context = os.path.join(repo, module.context.lstrip("./") or ".")
        _run(["docker", "build", "-f", dockerfile, "-t", img, context], _log)
        if import_to_cluster:
            _run(["k3d", "image", "import", img, "-c", cluster], _log)
        _log(f"built {img} (from working tree)")
        return img

    worktree = tempfile.mkdtemp(prefix=f"edd-build-{module.name}-")
    try:
        # --detach：落在 ref 指向的 commit，即使该分支已在主仓 checkout 也不冲突
        _run(["git", "-C", repo, "worktree", "add", "--detach", worktree, ref], _log)
        dockerfile = os.path.join(worktree, module.dockerfile.lstrip("./"))
        context = os.path.join(worktree, module.context.lstrip("./") or ".")
        _run(["docker", "build", "-f", dockerfile, "-t", img, context], _log)
        if import_to_cluster:
            _run(["k3d", "image", "import", img, "-c", cluster], _log)
        _log(f"built {img}")
        return img
    finally:
        subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", worktree],
                       capture_output=True, text=True)
