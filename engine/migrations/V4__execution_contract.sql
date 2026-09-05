ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS request_id UUID;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS result_id UUID;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS result_version INTEGER;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS result_type TEXT;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS content_json TEXT;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS content_hash TEXT;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS retryable BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS enqueued_at TIMESTAMPTZ;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS enqueue_claim_until TIMESTAMPTZ;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS enqueue_last_error TEXT;

ALTER TABLE engine.audit_events ADD COLUMN IF NOT EXISTS task_id UUID;
