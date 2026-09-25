#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"
: "${ENGINE_DB_PASSWORD:?ENGINE_DB_PASSWORD is required}"
: "${ENGINE_SERVICE_TOKEN:?ENGINE_SERVICE_TOKEN is required}"
: "${MODEL_CONFIG_ENCRYPTION_KEY:?MODEL_CONFIG_ENCRYPTION_KEY is required}"

DATA_ROOT="${DATA_ROOT:-/data}"
PGDATA="${DATA_ROOT}/postgres"
REDIS_DATA="${DATA_ROOT}/redis"
OBJECT_ROOT="${OBJECT_STORAGE_ROOT:-${DATA_ROOT}/objects}"

export DATABASE_URL="${DATABASE_URL:-jdbc:postgresql://127.0.0.1:5432/lexcyber}"
export DATABASE_USER="${DATABASE_USER:-lex_app}"
export DATABASE_PASSWORD="${DATABASE_PASSWORD:-${APP_DB_PASSWORD}}"
export ENGINE_BASE_URL="${ENGINE_BASE_URL:-http://127.0.0.1:8100}"
export ENGINE_SERVICE_TOKEN
export SPRING_FLYWAY_ENABLED="false"
export REVIEW_AUTH_MODE="${REVIEW_AUTH_MODE:-trusted-header}"
export STORAGE_PROVIDER="${OBJECT_STORAGE_PROVIDER:-filesystem}"
export STORAGE_ROOT="${OBJECT_STORAGE_ROOT:-${DATA_ROOT}/objects}"

export ENGINE_DATABASE_URL="${ENGINE_DATABASE_URL:-postgresql://lex_engine:${ENGINE_DB_PASSWORD}@127.0.0.1:5432/lexcyber}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export SERVICE_TOKEN="${SERVICE_TOKEN:-${ENGINE_SERVICE_TOKEN}}"
export APP_CALLBACK_BASE_URL="${APP_CALLBACK_BASE_URL:-http://127.0.0.1:8081}"
export WORKFLOW_PROFILE="${WORKFLOW_PROFILE:-competition}"
export OBJECT_STORAGE_PROVIDER="${OBJECT_STORAGE_PROVIDER:-filesystem}"
export OBJECT_STORAGE_ROOT="${OBJECT_STORAGE_ROOT:-${DATA_ROOT}/objects}"
export KNOWLEDGE_ROOT="${KNOWLEDGE_ROOT:-/opt/lexcyber/knowledge}"

mkdir -p "${PGDATA}" "${REDIS_DATA}" "${OBJECT_ROOT}"
chown -R postgres:postgres "${PGDATA}" "${OBJECT_ROOT}"

if [[ ! -s "${PGDATA}/PG_VERSION" ]]; then
  runuser -u postgres -- /usr/lib/postgresql/16/bin/initdb \
    --pgdata="${PGDATA}" \
    --username=postgres \
    --auth-local=trust \
    --auth-host=scram-sha-256 \
    --no-locale \
    --encoding=UTF8
fi

runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl \
  --pgdata="${PGDATA}" \
  --options="-c listen_addresses=127.0.0.1 -p 5432" \
  --wait start

if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='lexcyber'" | grep -q 1; then
  runuser -u postgres -- createdb lexcyber
fi

runuser -u postgres -- psql --dbname=postgres --set=postgres_password="${POSTGRES_PASSWORD}" <<'SQL'
ALTER ROLE postgres PASSWORD :'postgres_password';
SQL

runuser -u postgres -- psql --dbname=lexcyber \
  --set=app_password="${APP_DB_PASSWORD}" \
  --set=engine_password="${ENGINE_DB_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE lex_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lex_app') \gexec
SELECT format('ALTER ROLE lex_app PASSWORD %L', :'app_password') \gexec
SELECT format('CREATE ROLE lex_engine LOGIN PASSWORD %L', :'engine_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lex_engine') \gexec
SELECT format('ALTER ROLE lex_engine PASSWORD %L', :'engine_password') \gexec
GRANT CONNECT, CREATE ON DATABASE lexcyber TO lex_app, lex_engine;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION lex_app;
CREATE SCHEMA IF NOT EXISTS engine AUTHORIZATION lex_engine;
GRANT USAGE, CREATE ON SCHEMA app TO lex_app;
GRANT USAGE, CREATE ON SCHEMA engine TO lex_engine;
SQL

/opt/flyway/flyway migrate \
  -url="jdbc:postgresql://127.0.0.1:5432/lexcyber" \
  -user=lex_app \
  -password="${APP_DB_PASSWORD}" \
  -schemas=app \
  -defaultSchema=app \
  -locations=filesystem:/opt/lexcyber/src/server/src/main/resources/db/migration/app \
  -baselineOnMigrate=true

/opt/flyway/flyway migrate \
  -url="jdbc:postgresql://127.0.0.1:5432/lexcyber" \
  -user=lex_engine \
  -password="${ENGINE_DB_PASSWORD}" \
  -schemas=engine \
  -defaultSchema=engine \
  -locations=filesystem:/opt/lexcyber/src/engine/migrations \
  -baselineOnMigrate=true

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/lexcyber.conf
