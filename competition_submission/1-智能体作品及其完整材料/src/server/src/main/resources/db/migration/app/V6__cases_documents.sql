CREATE TABLE IF NOT EXISTS app.cases (
  id TEXT PRIMARY KEY,
  owner_account_id UUID NOT NULL REFERENCES app.accounts(id),
  title TEXT NOT NULL,
  jurisdiction TEXT,
  as_of_date DATE,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_cases_owner_created ON app.cases(owner_account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS app.documents (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES app.cases(id),
  filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size BIGINT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('input', 'annotation')),
  storage_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  parse_status TEXT NOT NULL CHECK (parse_status IN (
    'not_started', 'queued', 'running', 'completed', 'waiting_review', 'failed', 'timed_out', 'rejected'
  )),
  parse_task_id UUID REFERENCES app.tasks(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_documents_case_created ON app.documents(case_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_documents_parse_task ON app.documents(parse_task_id);

CREATE TABLE IF NOT EXISTS app.upload_idempotency (
  account_id UUID NOT NULL REFERENCES app.accounts(id),
  case_id TEXT NOT NULL REFERENCES app.cases(id),
  idempotency_key TEXT NOT NULL,
  document_id TEXT REFERENCES app.documents(id),
  request_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, case_id, idempotency_key)
);
