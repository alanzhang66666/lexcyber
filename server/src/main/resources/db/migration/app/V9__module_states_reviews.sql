CREATE TABLE IF NOT EXISTS app.case_module_states (
  case_id TEXT NOT NULL REFERENCES app.cases(id),
  module TEXT NOT NULL CHECK (module IN ('compliance', 'conviction')),
  schema_version TEXT NOT NULL DEFAULT 'case.module.v1',
  applicability TEXT NOT NULL DEFAULT 'unknown'
    CHECK (applicability IN ('unknown', 'not_applicable', 'limited_context', 'applicable')),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed')),
  version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0),
  content_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  facts_updated_at TIMESTAMPTZ,
  source_version TEXT,
  updated_by UUID REFERENCES app.accounts(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed_at TIMESTAMPTZ,
  PRIMARY KEY (case_id, module)
);

ALTER TABLE app.case_drafts
  ADD COLUMN IF NOT EXISTS template_version TEXT,
  ADD COLUMN IF NOT EXISTS source_version TEXT;

ALTER TABLE app.review_records
  ADD COLUMN IF NOT EXISTS case_id TEXT REFERENCES app.cases(id),
  ADD COLUMN IF NOT EXISTS draft_id TEXT REFERENCES app.case_drafts(id),
  ADD COLUMN IF NOT EXISTS draft_version INTEGER,
  ADD COLUMN IF NOT EXISTS module_state TEXT
    CHECK (module_state IS NULL OR module_state IN ('compliance', 'conviction')),
  ADD COLUMN IF NOT EXISTS module_version INTEGER,
  ADD COLUMN IF NOT EXISTS archive_status TEXT NOT NULL DEFAULT 'open'
    CHECK (archive_status IN ('open', 'archived')),
  ADD COLUMN IF NOT EXISTS return_target TEXT;

ALTER TABLE app.review_records ALTER COLUMN task_id DROP NOT NULL;

ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_task_id_result_version_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_review_records_task_version
  ON app.review_records(task_id, result_version)
  WHERE task_id IS NOT NULL;

ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_target_present;
ALTER TABLE app.review_records ADD CONSTRAINT review_records_target_present
  CHECK (task_id IS NOT NULL OR draft_id IS NOT NULL OR module_state IS NOT NULL);

UPDATE app.review_records r
SET case_id = NULLIF(t.case_id, '')
FROM app.tasks t
WHERE r.task_id = t.id
  AND r.case_id IS NULL
  AND t.case_id IS NOT NULL
  AND t.case_id <> '';

CREATE INDEX IF NOT EXISTS ix_review_records_case ON app.review_records(case_id);
CREATE INDEX IF NOT EXISTS ix_review_records_draft ON app.review_records(draft_id);
CREATE INDEX IF NOT EXISTS ix_review_records_archive ON app.review_records(archive_status);
