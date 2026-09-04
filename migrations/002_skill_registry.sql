CREATE SCHEMA IF NOT EXISTS skill;

CREATE TABLE IF NOT EXISTS skill.definitions (
  skill_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS skill.versions (
  skill_id TEXT NOT NULL REFERENCES skill.definitions(skill_id) ON DELETE CASCADE,
  version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  risk_level TEXT NOT NULL,
  kind TEXT NOT NULL,
  handler TEXT NOT NULL,
  manifest JSONB NOT NULL,
  input_schema JSONB NOT NULL,
  output_schema JSONB NOT NULL,
  permissions JSONB NOT NULL DEFAULT '[]'::jsonb,
  timeout_seconds INTEGER NOT NULL DEFAULT 30,
  activated_at TIMESTAMPTZ,
  deprecated_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (skill_id, version)
);

CREATE TABLE IF NOT EXISTS skill.permissions (
  skill_id TEXT NOT NULL,
  version TEXT NOT NULL,
  permission TEXT NOT NULL,
  PRIMARY KEY (skill_id, version, permission)
);

CREATE TABLE IF NOT EXISTS skill.executions (
  execution_id UUID PRIMARY KEY,
  request_id TEXT,
  case_id TEXT,
  skill_id TEXT NOT NULL,
  skill_version TEXT NOT NULL,
  actor TEXT,
  input_hash TEXT,
  output_hash TEXT,
  permission_result TEXT,
  source_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL,
  error_code TEXT,
  error TEXT,
  model_usage JSONB,
  human_approval BOOLEAN NOT NULL DEFAULT FALSE,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  duration_ms INTEGER,
  output JSONB,
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS skill.execution_events (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES skill.executions(execution_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
