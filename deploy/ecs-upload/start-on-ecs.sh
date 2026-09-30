#!/usr/bin/env bash
# 在 /opt/lexcyber 执行：load 镜像 → 起栈 → 注入代码 → 灌三案。
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env.v03 ]]; then
  echo "missing .env.v03" >&2
  exit 1
fi

read_env_value() {
  local key="$1"
  awk -F= -v wanted="$key" '$1 == wanted { sub(/^[^=]*=/, ""); print; exit }' .env.v03
}

for key in POSTGRES_PASSWORD APP_DB_PASSWORD ENGINE_DB_PASSWORD ENGINE_SERVICE_TOKEN MINIO_ROOT_PASSWORD; do
  value="$(read_env_value "$key")"
  case "$value" in
    ""|change-me*|dev-*change-me*)
      echo "$key must be a generated secret in .env.v03" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f demo-account.env ]]; then
  echo "missing demo-account.env" >&2
  exit 1
fi
if [[ ! -f lexcyber-demo-images.tar ]]; then
  echo "missing lexcyber-demo-images.tar" >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source demo-account.env
set +a
: "${LEXCYBER_USERNAME:?}"
: "${LEXCYBER_PASSWORD:?}"

echo "==> docker load"
docker load -i lexcyber-demo-images.tar

echo "==> compose up"
docker compose --env-file .env.v03 -f docker-compose.yml -f deploy/docker-compose.demo-cloud.yml up -d

echo "==> wait /healthz"
ok=0
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:18080/healthz >/dev/null; then
    ok=1
    break
  fi
  sleep 2
done
if [[ "$ok" != 1 ]]; then
  echo "healthz not ready" >&2
  docker compose --env-file .env.v03 -f docker-compose.yml -f deploy/docker-compose.demo-cloud.yml ps
  exit 1
fi

echo "==> inject engine/web"
bash deploy/fix_engine_runtime.sh
bash deploy/fix_web_runtime.sh

echo "==> stage materials"
python3 deploy/stage_materials.py --src 法学材料 --out .tmp-legal-docs

echo "==> import three cases (inside engine)"
docker exec lexcyber-v03-engine-1 mkdir -p /app/scripts /tmp/legal-docs
docker cp scripts/import_three_case_demo.py lexcyber-v03-engine-1:/app/scripts/import_three_case_demo.py
docker cp contracts lexcyber-v03-engine-1:/app/contracts
docker cp demo_cases lexcyber-v03-engine-1:/app/demo_cases
docker cp engine lexcyber-v03-engine-1:/app/engine
docker cp .tmp-legal-docs/. lexcyber-v03-engine-1:/tmp/legal-docs/
docker exec \
  -e PYTHONPATH=/app \
  -e LEXCYBER_BASE_URL=http://java:8080 \
  -e LEXCYBER_USERNAME \
  -e LEXCYBER_PASSWORD \
  lexcyber-v03-engine-1 \
  python /app/scripts/import_three_case_demo.py --docs-dir /tmp/legal-docs --register-account

echo "==> restore demo state"
LEXCYBER_BASE_URL=http://127.0.0.1:18080 \
  python3 deploy/demo_restore.py --docs-dir .tmp-legal-docs

echo "ready: http://<ECS_IP>:18080  user=${LEXCYBER_USERNAME}"
