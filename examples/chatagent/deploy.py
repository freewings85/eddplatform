"""用 EDD 部署一套方案到 k8s（两方案各一个 namespace）。

    PYTHONPATH=src python examples/chatagent/deploy.py [b|b-guide|a|a-guide]

走 EDD：render_manifest → K8sProvider.create。不销毁（留现场）。
"""
import subprocess
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from eddplatform.integrations.k8s import K8sProvider  # noqa: E402
from eddplatform.orchestration.manifest import render_manifest  # noqa: E402
from examples.chatagent import config as C  # noqa: E402

SOL = sys.argv[1] if len(sys.argv) > 1 else "b"
SETS = {
    "b": (C.SOLUTION_B_MODULES, C.SOLUTION_B_BASE, C.VERSION_B),
    "b-guide": (C.SOLUTION_B_GUIDE_MODULES, C.SOLUTION_B_GUIDE_BASE, C.VERSION_B_GUIDE),
    "a": (C.SOLUTION_A_MODULES, C.SOLUTION_A_BASE, C.VERSION_A),
    "a-guide": (C.SOLUTION_A_GUIDE_MODULES, C.SOLUTION_A_GUIDE_BASE, C.VERSION_A_GUIDE),
}
modules, base, version = SETS[SOL]
manifest = render_manifest(modules, version, base)
print(f"[{SOL}] base :", [f"{s['name']}={s['image']}" for s in manifest["base_services"]])
print(f"[{SOL}] apps :", [f"{s['name']}={s['image']}" for s in manifest["services"]])

p = K8sProvider(wait_timeout="180s")
ns = f"edd-{manifest['version'].replace('.', '-')}"
try:
    ns = p.create(manifest)
    print("OK namespace:", ns)
except Exception as e:  # noqa: BLE001
    print("create raised:", repr(e)[:400])
finally:
    print(subprocess.run(["kubectl", "get", "pods", "-n", ns],
                         capture_output=True, text=True).stdout)
