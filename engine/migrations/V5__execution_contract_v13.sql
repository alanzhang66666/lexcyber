-- v1.3 §4.6.12 / §8.4：Execution 与业务结果分离 + fencing token + outcome envelope。
-- INV-RUNTIME-001：人审决定（waiting_review）与超时（timed_out）不是技术执行态；
-- 超时映射为 failed + 错误码，人审标志改由 output_envelope 携带。

ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS artifact_stream_id UUID;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS input_snapshot_ref TEXT;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS fencing_token BIGINT NOT NULL DEFAULT 0;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS completion_identity TEXT;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS output_hash TEXT;
ALTER TABLE engine.executions ADD COLUMN IF NOT EXISTS output_envelope JSONB;

CREATE SEQUENCE IF NOT EXISTS engine.fencing_token_seq;

-- 存量终态行先归并状态，再回填完成身份，最后收紧 CHECK（顺序不可颠倒）。
UPDATE engine.executions SET status='completed' WHERE status='waiting_review';
UPDATE engine.executions
SET status='failed', error_code=COALESCE(error_code,'ENGINE_TIMEOUT')
WHERE status='timed_out';
UPDATE engine.executions
SET output_hash=COALESCE(output_hash, content_hash),
    completion_identity=COALESCE(completion_identity, 'legacy:'||execution_id::text)
WHERE status='completed';

ALTER TABLE engine.executions DROP CONSTRAINT IF EXISTS executions_status_check;
ALTER TABLE engine.executions ADD CONSTRAINT executions_status_check
  CHECK (status IN ('created','queued','claimed','running','completed','failed'));

ALTER TABLE engine.executions ADD CONSTRAINT ck_execution_completion
  CHECK (status <> 'completed' OR (output_hash IS NOT NULL AND completion_identity IS NOT NULL));
