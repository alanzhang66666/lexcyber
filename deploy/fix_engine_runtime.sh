#!/usr/bin/env bash
# 把仓库当前 engine/ 代码与 demo_cases 数据注入运行中容器的 site-packages。
# 为什么需要：engine/worker 以 `dramatiq engine.run_api_v03` / `uvicorn engine.run_api_v03`
# 启动时从 site-packages 解析 engine 包；旧镜像里的 site-packages 代码可能落后于仓库
#（例如缺 reviewed_disposition replay 分支），且 pip 安装不带 demo_cases 数据目录。
# 用法：栈起来之后、跑 demo_restore 之前执行一次：
#   bash deploy/fix_engine_runtime.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Git Bash 会把容器内 /usr/... 路径误转成本地 Windows 路径，关掉转换
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

SITE=/usr/local/lib/python3.12/site-packages
# dramatiq/uvicorn 从 site-packages 还是 /app 解析 engine 取决于启动上下文，
# 两处都打，保证无论哪条路径生效都是新代码且有 demo_cases
for c in lexcyber-v03-engine-1 lexcyber-v03-engine-worker-1; do
  docker cp engine/. "$c:$SITE/engine/"
  docker cp engine/. "$c:/app/engine/"
  docker cp demo_cases "$c:$SITE/"
  docker cp demo_cases "$c:/app/"
done
docker restart lexcyber-v03-engine-1 lexcyber-v03-engine-worker-1

# 验证：两处都应有 replay 分支与演示数据
docker exec lexcyber-v03-engine-worker-1 \
  grep -c reviewed_disposition "$SITE/engine/adapters/sentencing.py"
docker exec lexcyber-v03-engine-worker-1 \
  grep -c reviewed_disposition /app/engine/adapters/sentencing.py
docker exec lexcyber-v03-engine-worker-1 \
  ls "$SITE/demo_cases/three_case_demo/index.json" /app/demo_cases/three_case_demo/index.json
echo "engine runtime patched"
