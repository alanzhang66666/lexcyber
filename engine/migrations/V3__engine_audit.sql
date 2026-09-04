CREATE TABLE IF NOT EXISTS engine.audit_events (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT,
  execution_id UUID,
  agent_name TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
