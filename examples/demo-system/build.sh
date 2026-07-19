#!/usr/bin/env bash
# EddPlatform 约定构建脚本（属于「被测系统」仓库自己）。
# 职责：把本系统的各服务构建成镜像 → 存成 docker-archive tar → 写 images.json。
# 平台注入的环境变量：
#   EDD_IMAGE_TAG  本次构建用的 tag（平台通常传 git commit sha）
#   EDD_OUT_DIR    产物输出目录（平台准备好；脚本把 <svc>.tar 和 images.json 放这里）
# 镜像 ref 用 edd.local/ 这个假 registry 前缀 —— 全限定名，配 imagePullPolicy: Never
# 就不会去外网拉，平台把 tar 导进集群的 containerd 即可。
set -euo pipefail
: "${EDD_IMAGE_TAG:?EDD_IMAGE_TAG 未设置}"
: "${EDD_OUT_DIR:?EDD_OUT_DIR 未设置}"
cd "$(dirname "$0")"

SERVICES=(quote gateway)
for svc in "${SERVICES[@]}"; do
  img="edd.local/demo-${svc}:${EDD_IMAGE_TAG}"
  echo ">> building ${img}"
  buildah bud -t "${img}" "services/${svc}"
  buildah push "${img}" "docker-archive:${EDD_OUT_DIR}/${svc}.tar:${img}"
done

python3 - "$EDD_OUT_DIR" "$EDD_IMAGE_TAG" "${SERVICES[@]}" <<'PY'
import json, sys
out, tag, svcs = sys.argv[1], sys.argv[2], sys.argv[3:]
images = {s: f"edd.local/demo-{s}:{tag}" for s in svcs}
with open(f"{out}/images.json", "w") as f:
    json.dump(images, f, indent=2)
print("wrote images.json:", images)
PY
