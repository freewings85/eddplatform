# EDD 单元规范示例（edd_helm 文件夹）

这个文件夹就是一个**可部署单元**的完整示例。把它拷进你的仓库（目录名随意，
推荐 `edd_helm/`，多单元时如 `edd/mainagent/`、`edd/eval/`），按你的系统改内容，
然后在 EDD 平台登记「系统程序 / 评估程序」时把**单元目录**填成这个文件夹的路径。

## 文件夹里必须有什么

```
edd_helm/
├── .eddplatform.yaml    ← 单元声明（EDD 读它找到下面两样）
├── build.sh             ← 构建脚本：把服务构建成镜像
└── chart/               ← helm chart：怎么部署到 k8s
    ├── Chart.yaml
    ├── values.yaml
    └── templates/…
```

## .eddplatform.yaml 字段

```yaml
apiVersion: eddplatform/v1
name: mainagent       # 部署名（helm release 名）：小写字母/数字/中划线，单元间互不相同
kind: system          # system=被评系统 | eval=评估程序
build: ./build.sh     # 构建脚本（相对本文件夹）
chart: ./chart        # helm chart 目录（相对本文件夹）
services: [demo]      # 本单元包含的服务名列表
```

**name 就是 helm release 名**：EDD 把本单元部署进一次性 namespace 时执行
`helm upgrade --install <name> ./chart`，chart 里的 k8s 资源以它为前缀，
运行记录的版本标签也按它记（`{mainagent: commit, sessionstore: commit}`）。
按你的进程名填即可：mainagent 单元就填 `mainagent`，sessionstore 就填
`sessionstore`；同一个任务里拉起的多个单元 name 不能重复。

## build.sh 契约

EDD 会注入两个环境变量后执行它：

- `EDD_IMAGE_TAG`：本次构建的镜像 tag（EDD 传 git commit 短 sha）
- `EDD_OUT_DIR`：产物目录。脚本必须：
  1. 每个服务的镜像存成 docker-archive tar 放进去（如 `demo.tar`）；
  2. 写一个 `images.json`：`{"服务名": "镜像ref"}`。

镜像 ref 建议用 `edd.local/` 前缀 + chart 里 `imagePullPolicy: Never`——EDD 负责把
tar 导入集群，不走外网。

## chart 契约

EDD 部署时执行 `helm upgrade --install <release名> ./chart -n <一次性namespace>`，
并对每个服务注入 `--set services.<服务名>.image=<镜像ref>`。所以 values.yaml 里
必须有 `services.<服务名>.image` 这个挂点（见本示例）。

**release 名 = 上面 .eddplatform.yaml 里的 `name`**（helm 层的部署实例标识，
用于卸载与版本标签）。

## 服务间调用（重要）

k8s 集群内服务互相调用用 **Service 的 DNS 名**，不是 IP。本规范约定：
**Service 资源名 = services 里声明的服务名**（见 chart 示例，资源名就是裸服务名）。
于是同一次任务拉起的所有单元都在同一个一次性 namespace 里，互相调用直接写：

```
http://<服务名>:<端口>        # 例：http://mainagent:8100、http://sessionstore:8300
```

和 docker-compose 里的服务名一个体验；评估程序（eval 单元）也部署在同一
namespace，同样用服务名访问被评系统。

**因此服务名必须在本任务的所有单元之间全局唯一**（mainagent 单元的服务叫
mainagent，sessionstore 单元的叫 sessionstore……）；EDD 部署时会检查撞名并报错。
应用配置里的对端地址（如 mainagent 调 sessionstore）直接写服务名即可，
不要写 IP 或环境相关域名。

## 评估程序单元（kind: eval）的额外要求

被拉起后必须作为 Temporal worker 运行：认领 task queue = 平台登记的 `code`，
注册同名 workflow（入参 RunCaseInput → 出参 CaseResultOut），判定失败抛
`temporalio.exceptions.ApplicationError`。完整契约见平台仓库
`docs/EDD接入约定_被评系统与评估程序.md`。

## 自检

平台「新建评估任务 → 部署设置 → 校验」会在你选定的 仓库@commit 里检查：
约定文件存在、kind/build/chart 字段齐全、构建脚本存在、chart/Chart.yaml 存在。
