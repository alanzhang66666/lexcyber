CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.tasks (
  id UUID PRIMARY KEY,
  request_id UUID NOT NULL,
  execution_id UUID NOT NULL,
  case_id TEXT,
  query_text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'waiting_review', 'failed', 'timed_out', 'rejected')),
  current_stage TEXT NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_app_tasks_request_id ON app.tasks(request_id);
CREATE INDEX IF NOT EXISTS ix_app_tasks_status_updated ON app.tasks(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS app.task_dispatch_outbox (
  id BIGSERIAL PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES app.tasks(id),
  execution_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  published_at TIMESTAMPTZ,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.result_versions (
  result_id UUID NOT NULL,
  task_id UUID NOT NULL REFERENCES app.tasks(id),
  version INTEGER NOT NULL,
  result_type TEXT NOT NULL,
  content_json JSONB NOT NULL,
  content_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (result_id, version),
  UNIQUE (task_id, version)
);

CREATE TABLE IF NOT EXISTS app.audit_events (
  id BIGSERIAL PRIMARY KEY,
  request_id UUID,
  task_id UUID,
  execution_id UUID,
  event_type TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
