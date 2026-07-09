"""EDD 部署模型改进（真实 chatagent dogfood 暴露的短板）。

现有 Module 只有 git/branch/image，无法描述"怎么启动一个真实进程"；System 无法声明
它依赖的基础服务（kafka/redis/mysql/postgres…）。本组测试驱动补齐：

- Module 带 command / args / ports / env，且 image 可选（无预构建镜像时从 git+分支 build）
- BaseService 描述一个基础服务
- System.base_services 声明沙箱里要一并拉起的基础服务
- render_manifest 把 module 的启动信息与 base_services 一并渲染
- K8sProvider 的 Deployment 对象带 command/args/多端口/env
"""

from eddplatform.domain.models import (
    BaseService,
    Module,
    RunRecord,
    RunType,
    System,
    SystemVersion,
)
from eddplatform.integrations.k8s import _deployment, _namespace_name
from eddplatform.orchestration.build import image_ref
from eddplatform.orchestration.manifest import render_manifest


def test_build_image_ref_sanitizes_tag():
    assert image_ref("chatagent", "mainagent", "2.3") == "edd/chatagent-mainagent:2.3"
    assert image_ref("chatagent", "orch", "refactor/x") == "edd/chatagent-orch:refactor-x"


def test_run_record_cleanup_after_flag_default_true():
    r = RunRecord(id="R1", type=RunType.EVALUATION, system_id="chatagent",
                  version_label="2.3")
    assert r.cleanup_after is True                         # 默认跑完清理 namespace
    r2 = RunRecord(id="R2", type=RunType.EVALUATION, system_id="chatagent",
                   version_label="2.3", cleanup_after=False)
    assert r2.cleanup_after is False                       # 可选保留现场


def test_module_carries_startup_command_ports_env():
    m = Module(name="mainagent", git_url="g", branch="2.3",
               command=["uv", "run", "python", "server.py"],
               args=["--host", "0.0.0.0"],
               ports=[8100],
               env={"SERVER_PORT": "8100", "LLM_STUB": "0"})
    assert m.command == ["uv", "run", "python", "server.py"]
    assert m.args == ["--host", "0.0.0.0"]
    assert m.ports == [8100]
    assert m.env["LLM_STUB"] == "0"


def test_module_image_optional_build_from_git():
    m = Module(name="mainagent", git_url="g", branch="2.3")
    assert m.image is None                    # 无预构建镜像 → 从 git+分支 build


def test_base_service_model():
    kafka = BaseService(name="kafka", image="apache/kafka:3.9.0", ports=[9092],
                        env={"KAFKA_AUTO_CREATE_TOPICS_ENABLE": "true"})
    assert kafka.name == "kafka"
    assert kafka.ports == [9092]
    assert kafka.env["KAFKA_AUTO_CREATE_TOPICS_ENABLE"] == "true"


def test_base_service_carries_command_args():
    t = BaseService(name="temporal", image="img", ports=[7233],
                    command=["temporal", "server", "start-dev"], args=["--ip", "0.0.0.0"])
    assert t.command == ["temporal", "server", "start-dev"]
    assert t.args == ["--ip", "0.0.0.0"]


def test_render_manifest_base_service_includes_command():
    base = [BaseService(name="temporal", image="img", ports=[7233],
                        command=["temporal", "server", "start-dev"], args=["--ip", "0.0.0.0"])]
    v = SystemVersion(id="b", system_id="chatagent", label="2.3", module_pins={})
    man = render_manifest([], v, base_services=base)
    bs = {s["name"]: s for s in man["base_services"]}
    assert bs["temporal"]["command"] == ["temporal", "server", "start-dev"]
    assert bs["temporal"]["args"] == ["--ip", "0.0.0.0"]


def test_system_carries_base_services():
    s = System(id="chatagent", name="chatagent",
               base_services=[BaseService(name="postgres", image="postgres:16", ports=[5432])])
    assert s.base_services[0].name == "postgres"


def test_render_manifest_includes_startup_and_base_services():
    modules = [Module(name="mainagent", git_url="g", branch="2.3", image="edd/mainagent",
                      command=["uvicorn", "mainagent.main:create_app"],
                      args=["--factory"], ports=[8100], env={"LLM_STUB": "0"})]
    base = [BaseService(name="postgres", image="postgres:16", ports=[5432],
                        env={"POSTGRES_DB": "chatagent3_test"})]
    v = SystemVersion(id="b", system_id="chatagent", label="2.3",
                      module_pins={"mainagent": "2.3"})
    man = render_manifest(modules, v, base_services=base)
    svc = {s["name"]: s for s in man["services"]}
    assert svc["mainagent"]["image"] == "edd/mainagent:2.3"
    assert svc["mainagent"]["command"] == ["uvicorn", "mainagent.main:create_app"]
    assert svc["mainagent"]["args"] == ["--factory"]
    assert svc["mainagent"]["ports"] == [8100]
    assert svc["mainagent"]["env"]["LLM_STUB"] == "0"
    bs = {s["name"]: s for s in man["base_services"]}
    assert bs["postgres"]["image"] == "postgres:16"
    assert bs["postgres"]["ports"] == [5432]
    assert bs["postgres"]["env"]["POSTGRES_DB"] == "chatagent3_test"


def test_render_manifest_none_image_matches_build_ref():
    # 无预构建镜像时，render 出的镜像名必须与 build 步骤产出的一致，否则部署找不到镜像
    modules = [Module(name="mainagent", git_url="g", branch="2.3", ports=[8100])]
    v = SystemVersion(id="b", system_id="chatagent", label="2.3",
                      module_pins={"mainagent": "2.3"})
    man = render_manifest(modules, v)
    svc = {s["name"]: s["image"] for s in man["services"]}
    assert svc["mainagent"] == image_ref("chatagent", "mainagent", "2.3")
    assert svc["mainagent"] == "edd/chatagent-mainagent:2.3"


def test_render_manifest_backward_compatible_single_tag():
    """老口径仍成立：只钉 image:tag、无启动信息。"""
    modules = [Module(name="quote", git_url="g", image="registry/quote")]
    v = SystemVersion(id="v2", system_id="ins", label="v2", module_pins={"quote": "2.2.0"})
    man = render_manifest(modules, v)
    svc = {s["name"]: s["image"] for s in man["services"]}
    assert svc["quote"] == "registry/quote:2.2.0"
    assert man["base_services"] == []


def test_namespace_name_sanitizes_dotted_version():
    # k8s namespace 不能含点；版本号 2.3 要清成 2-3
    assert _namespace_name("edd", "2.3") == "edd-2-3"
    assert _namespace_name("edd", "v1.0-beta") == "edd-v1-0-beta"


def test_k8s_deployment_uses_local_imported_image():
    # k3d image import 把镜像塞进集群 containerd；部署要用本地镜像而非去公网拉
    d = _deployment("s", "edd/s:2.3", ports=[8100])
    c = d["spec"]["template"]["spec"]["containers"][0]
    assert c["imagePullPolicy"] == "IfNotPresent"


def test_k8s_deployment_sets_ndots_1_for_external_dns():
    # 外部域名(如 LLM API)在通配 search 域环境下要靠 ndots:1 才能正确解析
    d = _deployment("s", "img", ports=[80])
    spec = d["spec"]["template"]["spec"]
    assert {"name": "ndots", "value": "1"} in spec["dnsConfig"]["options"]


def test_k8s_deployment_object_has_command_args_ports_env():
    d = _deployment("mainagent", "edd/mainagent:2.3",
                    command=["uvicorn", "mainagent.main:create_app"], args=["--factory"],
                    ports=[8100, 8101], replicas=1, env={"LLM_STUB": "0"})
    c = d["spec"]["template"]["spec"]["containers"][0]
    assert c["command"] == ["uvicorn", "mainagent.main:create_app"]
    assert c["args"] == ["--factory"]
    assert [p["containerPort"] for p in c["ports"]] == [8100, 8101]
    assert {"name": "LLM_STUB", "value": "0"} in c["env"]
