# EDD 单元规范示例（edd_helm 文件夹）

这个文件夹就是一个**可部署单元**的完整示例：**一个标准 helm chart + 一个构建脚本**，
没有任何 EDD 私有格式。把它拷进你的仓库（目录名随意，推荐 `edd_helm/`；一个仓库
多个单元时如 `edd/mainagent/`、`edd/eval/`），改成你的系统，然后在 EDD 平台登记
「系统程序 / 评估程序」时把**单元目录**填成这个文件夹的路径。

## 文件夹结构（就这两样）

```
edd_helm/
├── build.sh             ← 构建脚本：把服务构建成镜像（EDD 唯一的非 helm 约定）
└── chart/               ← 100% 标准 helm chart
    ├── Chart.yaml       ← name = helm release 名（见下）
    ├── values.yaml      ← services.<服务名>.image 挂点（见下）
    └── templates/…
```

## Chart.yaml：`name` 就是部署名（helm release 名）

EDD 部署本单元时执行 `helm upgrade --install <name> ./chart -n <一次性namespace>`。
按你的进程名填：mainagent 单元就填 `mainagent`，sessionstore 就填 `sessionstore`
（小写字母/数字/中划线）。同一个任务里拉起的多个单元 name 不能重复，EDD 会检查。
运行记录的版本标签也按它记（`{mainagent: commit, sessionstore: commit}`）。

## values.yaml：服务声明 + 镜像挂点

```yaml
services:
  demo:            # ← 服务名
    image: ""      # ← EDD 部署时注入 --set services.demo.image=<build 产出的镜像>
    port: 8080
```

**服务名 = k8s Service 资源名 = 集群内 DNS 调用地址**。同一次任务的所有单元都在
同一个一次性 namespace 里，服务之间互相调用直接写：

```
http://<服务名>:<端口>      # 例：http://mainagent:8100、http://sessionstore:8300
```

和 docker-compose 的服务名一个体验；评估程序（eval 单元）也部署在同一 namespace，
同样用服务名访问被评系统。**因此服务名必须在本任务的所有单元之间全局唯一**，
应用配置里的对端地址直接写服务名，不要写 IP 或环境相关域名。

chart 模板资源名请用裸服务名（见本示例 templates/），这样 DNS 名才等于服务名。

## build.sh 契约

EDD 注入两个环境变量后执行它：

- `EDD_IMAGE_TAG`：本次构建的镜像 tag（EDD 传 git commit 短 sha）
- `EDD_OUT_DIR`：产物目录。脚本必须：
  1. 每个服务的镜像存成 docker-archive tar 放进去（如 `demo.tar`）；
  2. 写一个 `images.json`：`{"服务名": "镜像ref"}`（服务名与 values.yaml 一致）。

镜像 ref 建议用 `edd.local/` 前缀 + chart 里 `imagePullPolicy: Never`——EDD 负责把
tar 导入集群，不走外网。

## 评估程序单元的额外要求

被拉起后必须作为 Temporal worker 运行：认领 task queue = 平台登记的 `code`，
注册同名 workflow（入参 RunCaseInput → 出参 CaseResultOut），判定失败抛
`temporalio.exceptions.ApplicationError`。完整契约见平台仓库
`docs/EDD接入约定_被评系统与评估程序.md`。

## 自检

平台「新建评估任务 → 部署设置 → 校验规范」会在你选定的 仓库@commit 里检查：
`build.sh` 存在、`chart/Chart.yaml` 有效（name 合法）、`values.yaml` 有
`services.<服务名>.image` 挂点。
