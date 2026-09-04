#!/bin/sh
set -eu

if [ -z "${APP_DB_PASSWORD:-}" ] || [ -z "${ENGINE_DB_PASSWORD:-}" ]; then
  echo "APP_DB_PASSWORD and ENGINE_DB_PASSWORD must be provided" >&2
  exit 1
fi

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$APP_DB_PASSWORD" \
  --set=engine_password="$ENGINE_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE lex_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lex_app') \gexec
SELECT format('CREATE ROLE lex_engine LOGIN PASSWORD %L', :'engine_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lex_engine') \gexec
GRANT CONNECT ON DATABASE lexcyber TO lex_app, lex_engine;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION lex_app;
CREATE SCHEMA IF NOT EXISTS engine AUTHORIZATION lex_engine;
GRANT USAGE ON SCHEMA app TO lex_app;
GRANT USAGE ON SCHEMA engine TO lex_engine;
SQL
