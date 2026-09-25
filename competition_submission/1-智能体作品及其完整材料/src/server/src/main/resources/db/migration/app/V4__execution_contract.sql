ALTER TABLE app.tasks ADD COLUMN IF NOT EXISTS session_id TEXT;
ALTER TABLE app.tasks ADD COLUMN IF NOT EXISTS error_code TEXT;

ALTER TABLE app.task_dispatch_outbox ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE app.task_dispatch_outbox ADD COLUMN IF NOT EXISTS last_error TEXT;
CREATE INDEX IF NOT EXISTS ix_task_dispatch_pending ON app.task_dispatch_outbox(next_attempt_at, id) WHERE published_at IS NULL;

ALTER TABLE app.result_versions ADD COLUMN IF NOT EXISTS execution_id UUID;
ALTER TABLE app.result_versions ADD COLUMN IF NOT EXISTS source_refs_json JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS ix_result_versions_execution ON app.result_versions(execution_id);
