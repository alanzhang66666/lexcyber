#!/usr/bin/env bash
# 把本仓库构建好的 web/dist 注入运行中的 web 容器。
# 场景：演示栈用已有镜像起服务，前端改完后不重新 docker build（ECS 2G 会 OOM）。
# 用法（先在仓库根目录完成 npm --prefix web run build）：
#   bash deploy/fix_web_runtime.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f web/dist/index.html ]; then
  echo "web/dist/index.html missing; run: npm --prefix web run build" >&2
  exit 1
fi

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

docker cp web/dist/. lexcyber-v03-web-1:/usr/share/nginx/html/
docker exec lexcyber-v03-web-1 nginx -s reload || docker restart lexcyber-v03-web-1
echo "web runtime patched"
