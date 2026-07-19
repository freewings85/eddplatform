# 本地 k3s：约定式部署的端到端验证环境

平台的 `start_system` / `start_eval_program` 前置条件把「一份具体版本的 git 代码」
拉起到 k8s。这里给出在一台 Linux（含 WSL2，需 systemd）上跑通真端到端所需的最小栈。

## 安装

```bash
# 1) k3s：单二进制 k8s，自带 containerd（无需 Docker）
curl -sfL https://get.k3s.io | sudo sh -s - --write-kubeconfig-mode 644
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes           # 等到 Ready

# 2) helm
curl -sfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | sudo bash

# 3) buildah（rootless 构建镜像；需要 /etc/subuid /etc/subgid 有当前用户的范围）
sudo apt-get install -y buildah
```

## 跑端到端

```bash
pip install -e '.[dev]'
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
python examples/e2e_convention_deploy.py
```

会用 `examples/demo-system` 造一个真实 git 仓库（v1/v2 两个 commit），平台按
`.eddplatform.yaml` 约定 `clone → build → 导镜像进 containerd → helm 部署` 到一次性
namespace，验证 v1/v2 各自起来、内容正确，再销毁。

## 镜像怎么进集群（可插拔）

本地 e2e 里，构建脚本产出 docker-archive tar，平台用 `sudo k3s ctr -n k8s.io images
import` 把镜像导进集群的 containerd，chart 用 `imagePullPolicy: Never` 直接用本地镜像
（镜像 ref 用 `edd.local/` 假 registry 前缀，全限定名，不会误去外网拉）。

生产环境把这一步换成 **push 到 Harbor**、chart 从 Harbor 拉即可——见
`ConventionDeployer(image_import_cmd=...)`，部署器其余逻辑不变。
