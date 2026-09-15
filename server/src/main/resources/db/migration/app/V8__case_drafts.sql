CREATE TABLE IF NOT EXISTS app.case_drafts (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES app.cases(id),
  draft_type TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  version INTEGER NOT NULL DEFAULT 1,
  updated_by UUID NOT NULL REFERENCES app.accounts(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT case_drafts_version_positive CHECK (version >= 1)
);
CREATE INDEX IF NOT EXISTS ix_case_drafts_case_updated ON app.case_drafts(case_id, updated_at DESC);
