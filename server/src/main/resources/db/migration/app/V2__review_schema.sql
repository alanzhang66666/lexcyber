CREATE TABLE IF NOT EXISTS app.review_records (
  id UUID PRIMARY KEY,
  task_id UUID NOT NULL REFERENCES app.tasks(id),
  result_version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
  decision TEXT NOT NULL DEFAULT 'none',
  actor TEXT,
  authenticated BOOLEAN NOT NULL DEFAULT FALSE,
  comment TEXT,
  decided_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (task_id, result_version)
);
CREATE TABLE IF NOT EXISTS app.business_audit (
  id BIGSERIAL PRIMARY KEY,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
