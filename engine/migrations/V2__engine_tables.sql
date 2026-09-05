CREATE TABLE IF NOT EXISTS engine.executions (
  execution_id UUID PRIMARY KEY,
  task_id UUID NOT NULL,
  contract_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'waiting_review', 'failed', 'timed_out')),
  current_stage TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  result_json JSONB,
  error_code TEXT,
  error_message TEXT,
  lease_owner TEXT,
  lease_until TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS engine.stage_checkpoints (
  id BIGSERIAL PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES engine.executions(execution_id),
  stage TEXT NOT NULL,
  state_json JSONB NOT NULL,
  sequence_no INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (execution_id, sequence_no)
);
CREATE TABLE IF NOT EXISTS engine.skill_executions (
  execution_id UUID NOT NULL REFERENCES engine.executions(execution_id),
  skill_execution_id UUID NOT NULL,
  skill_id TEXT NOT NULL,
  skill_version TEXT NOT NULL,
  status TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  output_hash TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (execution_id, skill_execution_id)
);
