"""用 EDD 把方案B(2.3) 的 guide 子集部署到 k8s 一个 namespace，并报告 pod 状态。

    PYTHONPATH=src python examples/chatagent/deploy_guide.py

全程走 EDD：render_manifest(声明式配置) → K8sProvider.create(建 ns+部署+等就绪)。
不销毁(留现场排查)。
"""
import subprocess
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from eddplatform.integrations.k8s import K8sProvider  # noqa: E402
from eddplatform.orchestration.manifest import render_manifest  # noqa: E402
from examples.chatagent.config import (  # noqa: E402
    SOLUTION_B_GUIDE_BASE,
    SOLUTION_B_GUIDE_MODULES,
    VERSION_B_GUIDE,
)

manifest = render_manifest(SOLUTION_B_GUIDE_MODULES, VERSION_B_GUIDE, SOLUTION_B_GUIDE_BASE)
print("base :", [f"{s['name']}={s['image']}" for s in manifest["base_services"]])
print("apps :", [f"{s['name']}={s['image']}" for s in manifest["services"]])

p = K8sProvider(wait_timeout="150s")
ns = f"edd-{manifest['version']}"
try:
    ns = p.create(manifest)
    print("OK namespace:", ns)
except Exception as e:  # noqa: BLE001
    print("create raised:", repr(e)[:400])
finally:
    print(subprocess.run(["kubectl", "get", "pods,svc", "-n", ns],
                         capture_output=True, text=True).stdout)
