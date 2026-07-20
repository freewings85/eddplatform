#!/usr/bin/env bash
# EDD 约定构建脚本：把本单元的服务构建成镜像 → docker-archive tar + images.json。
# EDD 注入：EDD_IMAGE_TAG（镜像 tag）、EDD_OUT_DIR（产物目录）。
set -euo pipefail
: "${EDD_IMAGE_TAG:?EDD_IMAGE_TAG 未设置}"
: "${EDD_OUT_DIR:?EDD_OUT_DIR 未设置}"
cd "$(dirname "$0")"

SERVICES=(demo)
for svc in "${SERVICES[@]}"; do
  img="edd.local/${svc}:${EDD_IMAGE_TAG}"
  echo ">> building ${img}"
  # 按你的实际情况构建：Dockerfile 路径、构建工具（buildah/docker）自行替换
  buildah bud -t "${img}" "../../services/${svc}"
  buildah push "${img}" "docker-archive:${EDD_OUT_DIR}/${svc}.tar:${img}"
done

python3 - "$EDD_OUT_DIR" "$EDD_IMAGE_TAG" "${SERVICES[@]}" <<'PY'
import json, sys
out, tag, svcs = sys.argv[1], sys.argv[2], sys.argv[3:]
images = {s: f"edd.local/{s}:{tag}" for s in svcs}
with open(f"{out}/images.json", "w") as f:
    json.dump(images, f, indent=2)
print("wrote images.json:", images)
PY
