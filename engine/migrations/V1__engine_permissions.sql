CREATE SCHEMA IF NOT EXISTS engine;

-- The runtime account may only access its own schema. Provisioning is intentionally
-- explicit in Compose/operations; Python never creates tables at startup.
CREATE TABLE IF NOT EXISTS engine.schema_version_guard (
  id BOOLEAN PRIMARY KEY DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
