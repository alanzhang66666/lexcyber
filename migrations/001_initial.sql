CREATE SCHEMA IF NOT EXISTS workflow;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS agent;

CREATE TABLE IF NOT EXISTS workflow.tasks (
  id UUID PRIMARY KEY,
  request_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  user_query TEXT NOT NULL,
  status TEXT NOT NULL,
  state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_json JSONB,
  error TEXT,
  retry_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workflow.checkpoints (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES workflow.tasks(id) ON DELETE CASCADE,
  node_name TEXT NOT NULL,
  state_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit.events (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL,
  task_id UUID,
  agent_name TEXT NOT NULL,
  model_name TEXT,
  prompt_version TEXT,
  input_hash TEXT,
  tool_calls JSONB NOT NULL DEFAULT '[]'::jsonb,
  model_output JSONB,
  token_usage JSONB,
  latency_ms INTEGER,
  reviewer_result TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent.prompt_versions (
  prompt_id TEXT NOT NULL,
  version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  model_name TEXT,
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (prompt_id, version)
);
