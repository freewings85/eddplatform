# EDD 接入规范示例（完整仓库骨架）

这个压缩包是一个**接入 EDD 的项目仓库骨架**：把 `eval/` 和 `build/` 两个目录
拷进你的仓库，替换成你的内容即可。详细约定见平台仓库
`docs/EDD接入约定_被评系统与评估程序.md`。

```
你的项目仓库/
├── eval/                         ← 评估代码：纯 pydantic-evals
│   ├── quiz/cases.py             ←   业务子目录示例（Dataset/Case/task/evaluators）
│   ├── worker.py                 ←   Temporal 入口：import 各业务 cases + serve() 一行
│   └── edd_bridge.py             ←   原样复制，不要改（平台↔pydantic-evals 桥）
└── build/                        ← 部署物
    ├── system/                   ←   被评系统单元：build.sh + 标准 helm chart
    └── eval/                     ←   评估程序单元：build.sh + Dockerfile + chart
```

## 三步接入

1. **写评估代码（只需要会 pydantic-evals）**：在 `eval/<业务>/cases.py` 里按
   官方用法定义 `Dataset(name=…, cases=[Case(name=…, …)], evaluators=[…])` 和
   task 函数（驱动被评系统，HTTP 调它在集群内的服务名）。`eval/worker.py` 里
   `serve("你的workflow名", [(dataset, task)])`。**不需要懂 Temporal**——
   桥自动完成契约与四态映射（断言全过=passed / 有不过=failed / task 里
   `raise Skip("原因")`=skipped / 异常或名字对不上=error）。

2. **改 build/**：
   - `build/system/`：build.sh 构建你的服务镜像（吃 `EDD_IMAGE_TAG`/`EDD_OUT_DIR`，
     产出 docker-archive tar + `images.json`）；chart 是 100% 标准 helm chart，
     `Chart.yaml` 的 name = release 名，`values.yaml` 的 `services.<服务名>.image`
     是平台的镜像挂点（服务名 = 集群内 DNS 名）。
   - `build/eval/`：同样约定，Dockerfile COPY 仓库根的 `eval/`。

3. **平台登记**：系统程序（目录 `build/system`）、评估程序（目录 `build/eval`）、
   用例库配 workflow 名（= serve 的名字）、用例 name 与 Case.name 一一对应。

## 部署配置（.env.eval 动态注入）

环境相关配置（LLM 地址/密钥等）**不进镜像、不写死在 chart**：在平台注册项/任务里
填「部署配置」（KEY=VALUE 每行），部署时平台经 helm values 注入：

- `.Values.eddEnv` = 原文 → chart 渲染成 ConfigMap 挂载 `/app/.env.eval`，
  容器 `ACTIVE=eval` 启动读它（配置文件模式）；
- `.Values.eddEnvVars` = 解析后的字典 → envFrom 直接进环境变量（环境变量模式）。

两个挂点的模板在本骨架的 chart 里都有，按你应用的配置方式取用。
