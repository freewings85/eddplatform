#!/usr/bin/env bash
# 评估程序仓库的约定构建脚本（与被测系统同契约）。
set -euo pipefail
: "${EDD_IMAGE_TAG:?EDD_IMAGE_TAG 未设置}"
: "${EDD_OUT_DIR:?EDD_OUT_DIR 未设置}"
cd "$(dirname "$0")"

SERVICES=(judge)
for svc in "${SERVICES[@]}"; do
  img="edd.local/eval-${svc}:${EDD_IMAGE_TAG}"
  echo ">> building ${img}"
  buildah bud -t "${img}" "services/${svc}"
  buildah push "${img}" "docker-archive:${EDD_OUT_DIR}/${svc}.tar:${img}"
done

python3 - "$EDD_OUT_DIR" "$EDD_IMAGE_TAG" "${SERVICES[@]}" <<'PY'
import json, sys
out, tag, svcs = sys.argv[1], sys.argv[2], sys.argv[3:]
images = {s: f"edd.local/eval-{s}:{tag}" for s in svcs}
with open(f"{out}/images.json", "w") as f:
    json.dump(images, f, indent=2)
print("wrote images.json:", images)
PY
