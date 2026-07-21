# EDD 接入约定：被评系统 与 评估程序

> 任何想被 EddPlatform 拉起、评估的项目（被评系统 或 评估程序），都必须满足本约定。
> 核心概念一句话：**能被 EDD 使用的项目，必须提供"helm 包"——一个自带构建脚本与
> helm chart 的可部署单元文件夹。**

## 1. 可部署单元 = 一个文件夹

EDD 定位一个可部署单元用三元组：**git 仓库 + ref（分支或 commit）+ 单元目录**。

- 单元目录默认 `.`（仓库根）；
- **一个仓库可以包含多个单元**。典型场景：chatagent 仓库里既有被评系统本身，又有
  评估程序，各放一个文件夹即可：

```
com.celiang.hlsc.service.ai.chatagent3/   （2.3-eval 分支）
├── services/…                             ← 业务代码本体
├── edd/
│   ├── system/                            ← 单元①：被评系统
│   │   ├── build.sh
│   │   └── chart/                         ← 标准 helm chart
│   └── eval/                              ← 单元②：评估程序
│       ├── build.sh
│       └── chart/
└── …
```

平台侧对应的填法：
- 「启动系统」前置条件：仓库 + 分支/commit + 目录 `edd/system`；
- 「评估程序」注册：同一仓库 + ref + 目录 `edd/eval`（workflow 名见 §4）。

## 2. 单元目录里必须有什么：标准 helm chart + 构建脚本

没有任何 EDD 私有清单文件——单元目录就两样东西：

```
edd_helm/
├── build.sh             ← 构建脚本（EDD 唯一的非 helm 约定；helm 不管构建）
└── chart/               ← 100% 标准 helm chart
    ├── Chart.yaml       ← name = helm release 名（按进程名填：mainagent/sessionstore…）
    ├── values.yaml      ← services.<服务名>.image 挂点
    └── templates/…
```

**release 名 = chart/Chart.yaml 的 `name`**（helm 原生语义）：EDD 执行
`helm upgrade --install <name> <chart>`，运行记录的版本标签按它记 key，
同一任务多个单元的 name 不能重复（EDD 检查）。用户在平台界面不填任何部署名。

**① 构建脚本**（`build.sh`）：职责是把本单元的服务构建成镜像。平台注入两个环境变量：

- `EDD_IMAGE_TAG`：本次构建用的 tag（平台传 git commit 短 sha）；
- `EDD_OUT_DIR`：产物输出目录。脚本必须把每个服务的镜像存成
  `docker-archive` tar 放进去，并写一个 `images.json`（`{"服务名": "镜像ref"}`）。

镜像 ref 建议用 `edd.local/` 假 registry 前缀 + `imagePullPolicy: Never`，
平台负责把 tar 导入集群 containerd，不走外网。

**② helm chart**（`chart/`）：本单元的 k8s 部署描述。平台会以
`--set services.<服务名>.image=<镜像ref>` 注入 build 产出的镜像后
`helm upgrade --install --wait` 到一次性 namespace。values.yaml 里必须有
`services.<服务名>.image` 这个约定挂点——服务名清单也从这里读。

**服务间调用**：Service 资源名 = 服务名（裸名，不加前缀）。同一任务的全部单元
在同一个一次性 namespace 里，互相调用直接 `http://<服务名>:<端口>`（评估程序
访问被评系统同理）。因此**服务名在本任务所有单元之间必须唯一**，EDD 部署时
检查撞名。应用配置对端地址写服务名，不要写 IP。

参考实现：`examples/demo-system/`、`examples/demo-eval/`、可下载的
`edd_helm` 规范示例（平台「部署设置 → 下载规范示例」）。

## 3. 平台怎么执行（你不用做，但要知道）

```
clone 仓库 → checkout ref → 进入单元目录（读 chart/Chart.yaml 拿 release 名）
→ 跑 build.sh（产镜像 tar + images.json）→ 镜像导入集群
→ helm install chart/ 到一次性 namespace（注入镜像）→ 记录解析出的 commit sha
```

版本可感知：无论你填分支还是 commit，运行记录里落的都是解析出的**实际 sha**——
这是老新对比与复现的地基。**配置跟代码走**：build/chart 的写法随版本演进，
EDD 平台侧不保存这些细节，checkout 哪个版本就用哪个版本的约定。

## 4. 评估程序的额外约定（kind: eval）

评估程序被拉起后是一个 **Temporal worker**，必须：

1. 连接平台的 Temporal server，认领的 **task queue 名 = 它注册的 workflow 名**
   ——这个名字写在**评估程序自己的代码/配置里**（平台不登记）；
   平台侧在「用例库」上配置同名 `workflow`，两边即对上；
**推荐路径（零 Temporal 知识）：标准 pydantic-evals + `edd_bridge`。**
开发者只写原生 pydantic-evals（https://ai.pydantic.dev/evals/ ——
`Case`/`Dataset`/`Evaluator`/task 函数，该怎么写怎么写），然后把模板里的
`eval/edd_bridge.py` **原样复制**进评估程序目录，最后一行：

```python
serve("my-eval", [(dataset, task)])   # workflow 名 = 队列名（平台用例库里配同名）
```

桥自动完成：Temporal worker、契约收发、结果映射——assertions 全 True→passed、
有 False→failed（detail=未通过项+原因）、数值评估器输出→scores、
`increment_eval_metric` 的值+task_duration_s→metrics、task 里
`raise Skip("原因")`→skipped、task/评估器异常与 dataset/case 找不到→error。
EDD 用例库按 `Dataset.name` / `Case.name` 与代码一一对应（用例库=纯注册记录，
评估内容只存在于评估代码里）。完整示例见模板 `eval/worker.py`。

**底层契约（不用桥、自己实现 worker 时）**：注册 workflow，签名
`RunCaseInput → CaseResultOut`（见 `src/eddplatform/runtime/temporal/shared.py`）：
   - `RunCaseInput`：`run_id` + `namespace` + **`dataset`（用例集 name）+
     `case`（用例 name）**——参数只有这两个名字；
   - `CaseResultOut`：`case_id`（=用例 name）+ `status`
     （passed/failed/error/skipped）+ `scores`/`metrics` + `detail` + `trace_url`；
   - **失败必须抛 `temporalio.exceptions.ApplicationError`**（普通异常会让
     workflow task 无限重试）；dataset/case 找不到也抛它（平台记 error=映射配错）。

平台执行任务时按**用例库配置的 workflow 名**逐用例
`execute_child_workflow(名=workflow, 队列=workflow)`，评估程序 worker 逐条认领：
按 `(dataset, case)` 在自己代码里查到该 case 的定义 → 驱动被评系统 → 打分 → 返回。

## 5. 接入检查清单

- [ ] 单元目录有 `build.sh` + `chart/`（标准 helm chart）
- [ ] `chart/Chart.yaml` 的 name 合法（= helm release 名，按进程名填）
- [ ] `build.sh` 吃 `EDD_IMAGE_TAG`/`EDD_OUT_DIR`，产出 tar + `images.json`
- [ ] `chart/values.yaml` 有 `services.<服务名>.image` 挂点（服务名=集群 DNS 名）
- [ ] （评估程序）标准 pydantic-evals 写用例与评估器 + 复制 `edd_bridge.py` + `serve("名字", [(dataset, task)])`
- [ ] 在 EDD 界面登记：系统程序/评估程序（名称+仓库+目录）；用例库配置同名 `workflow`
