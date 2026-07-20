# demo-system：约定式部署的示例「被测系统」

一个**多服务**系统（`quote` + `gateway` 两个 nginx 服务），用来端到端验证平台
"一份具体版本的 git 代码 → 拉起到 k8s"这条链路。

## 仓库约定（build.sh + 标准 helm chart）

被测系统 / 评估程序的仓库提供一个单元目录（此示例为仓库根）：`build.sh`（构建镜像）+ `chart/`（标准 helm chart，Chart.yaml 的 name 即 release 名），平台据此拉起：

```yaml
apiVersion: eddplatform/v1
kind: system            # system（被测系统）| eval（评估程序）
build: ./build.sh       # 构建脚本
chart: ./deploy/chart   # helm chart 路径
services: [quote, gateway]
```

## 构建脚本契约（`build.sh`）

平台注入两个环境变量，脚本负责产出镜像：

| 变量 | 含义 |
|---|---|
| `EDD_IMAGE_TAG` | 本次构建的 tag（平台传 commit sha 短码） |
| `EDD_OUT_DIR` | 产物目录：脚本把每个服务的镜像存成 `<svc>.tar`，并写 `images.json`（`{服务: 镜像ref}`） |

平台读 `images.json` → 把 tar 导进集群 → `helm install` 时按 `--set services.<svc>.image=<ref>` 注入。
镜像 ref 用 `edd.local/` 前缀（全限定名 + `imagePullPolicy: Never`，本地不误拉外网）。

## chart（`deploy/chart/`）

`values.services.<name>.image` 是平台注入镜像的挂点；模板对每个服务渲染一个
Deployment + Service，带 readiness 探针。

## 本地跑

见 [`../../deploy/k3s/README.md`](../../deploy/k3s/README.md)：
`python examples/e2e_convention_deploy.py`。
