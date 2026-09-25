-- V17 — review_records 改绑 artifact_version_id（v1.3 §4.6.9、INV-REVIEW-REF-001）
-- 删除多态目标列（task_id/result_version/draft_id/draft_version/module_state/module_version）
-- 与 archive_status / return_target / authenticated。改绑经由 V15 的 artifact_backfill_map。
-- 无法解析到 artifact_version 的历史行：写入 business_audit 后删除（避免静默丢失）。

ALTER TABLE app.review_records ADD COLUMN artifact_version_id uuid;

-- task 目标 → parse/结果 artifact
UPDATE app.review_records r
SET artifact_version_id = m.artifact_version_id
FROM app.artifact_backfill_map m
WHERE r.artifact_version_id IS NULL
  AND m.source_kind = 'result'
  AND r.task_id IS NOT NULL
  AND m.task_id = r.task_id AND m.result_version = r.result_version;

-- draft 目标 → 该 draft 的当前 version（历史版本号已不可得，按最近版本归并）
UPDATE app.review_records r
SET artifact_version_id = m.artifact_version_id
FROM app.artifact_backfill_map m
WHERE r.artifact_version_id IS NULL
  AND m.source_kind = 'draft'
  AND r.draft_id IS NOT NULL
  AND m.draft_id = r.draft_id;

-- module 目标 → 该 (case,module) 的当前 version
UPDATE app.review_records r
SET artifact_version_id = m.artifact_version_id
FROM app.artifact_backfill_map m
WHERE r.artifact_version_id IS NULL
  AND m.source_kind = 'module'
  AND r.module_state IS NOT NULL
  AND m.case_id = r.case_id AND m.module = r.module_state;

-- 无法改绑的历史行：先留审计再删除
INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
SELECT COALESCE(r.actor, 'migration-v17'), 'review_record_dropped_unbindable',
       'review_record', r.id::text,
       jsonb_build_object('task_id', r.task_id, 'draft_id', r.draft_id,
                          'module_state', r.module_state, 'status', r.status,
                          'reason', 'no artifact_version mapping')
FROM app.review_records r
WHERE r.artifact_version_id IS NULL;

DELETE FROM app.review_records WHERE artifact_version_id IS NULL;

ALTER TABLE app.review_records ALTER COLUMN artifact_version_id SET NOT NULL;
ALTER TABLE app.review_records ADD CONSTRAINT review_records_artifact_fkey
    FOREIGN KEY (artifact_version_id) REFERENCES app.artifact_version(artifact_version_id);

-- 目标模型列名与类型
ALTER TABLE app.review_records RENAME COLUMN id TO review_id;
ALTER TABLE app.review_records ALTER COLUMN decision TYPE varchar(64);
ALTER TABLE app.review_records ALTER COLUMN decision DROP NOT NULL;
ALTER TABLE app.review_records ALTER COLUMN decision DROP DEFAULT;
ALTER TABLE app.review_records ADD COLUMN actor_id uuid;

-- case_id 缺失的行：由已绑定的 artifact 回填（stream 是权威归属）
UPDATE app.review_records r
SET case_id = s.case_id
FROM app.artifact_version v
JOIN app.artifact_stream s ON s.artifact_stream_id = v.artifact_stream_id
WHERE v.artifact_version_id = r.artifact_version_id
  AND r.case_id IS NULL;

-- actor 文本（username）→ accounts.id；解析链：username → artifact 所在案 owner → task 所在案 owner
UPDATE app.review_records r
SET actor_id = COALESCE(
        (SELECT a.id FROM app.accounts a WHERE a.username_normalized = lower(r.actor)),
        (SELECT s2c.owner_account_id
           FROM app.artifact_version v2
           JOIN app.artifact_stream s2 ON s2.artifact_stream_id = v2.artifact_stream_id
           JOIN app.cases s2c ON s2c.id = s2.case_id
          WHERE v2.artifact_version_id = r.artifact_version_id
          LIMIT 1),
        (SELECT c2.owner_account_id FROM app.cases c2 WHERE c2.id = r.case_id))
WHERE r.actor_id IS NULL;

-- actor 被代位解析的行：披露式审计（原 actor 值保留在 payload，不伪造身份）
INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
SELECT 'migration-v17', 'review_actor_substituted', 'review_record', r.review_id::text,
       jsonb_build_object('original_actor', r.actor, 'resolved_actor_id', r.actor_id,
                          'artifact_version_id', r.artifact_version_id,
                          'reason', 'actor not resolvable; attributed to case owner')
FROM app.review_records r
WHERE r.actor_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM app.accounts a
                  WHERE a.id = r.actor_id AND a.username_normalized = lower(r.actor));

-- 仍无法解析的：审计后删除（保有证据，不静默）
INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
SELECT 'migration-v17', 'review_record_dropped_unresolvable_actor', 'review_record', r.review_id::text,
       jsonb_build_object('original_actor', r.actor, 'artifact_version_id', r.artifact_version_id,
                          'case_id', r.case_id, 'status', r.status)
FROM app.review_records r
WHERE r.actor_id IS NULL;
DELETE FROM app.review_records WHERE actor_id IS NULL;
ALTER TABLE app.review_records ALTER COLUMN actor_id SET NOT NULL;
ALTER TABLE app.review_records DROP COLUMN actor;
ALTER TABLE app.review_records DROP COLUMN authenticated;

-- 决策时间一致性：非 pending 必须有 decided_at；pending 必须为 NULL
UPDATE app.review_records SET decided_at = now()
WHERE status <> 'pending' AND decided_at IS NULL;
UPDATE app.review_records SET decided_at = NULL
WHERE status = 'pending' AND decided_at IS NOT NULL;

-- 删除多态目标列与归档标志
ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_target_present;
ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_task_id_fkey;
DROP INDEX IF EXISTS app.ux_review_records_task_version;
DROP INDEX IF EXISTS app.ix_review_records_archive;
ALTER TABLE app.review_records DROP COLUMN task_id;
ALTER TABLE app.review_records DROP COLUMN result_version;
ALTER TABLE app.review_records DROP COLUMN draft_id;
ALTER TABLE app.review_records DROP COLUMN draft_version;
ALTER TABLE app.review_records DROP COLUMN module_state;
ALTER TABLE app.review_records DROP COLUMN module_version;
ALTER TABLE app.review_records DROP COLUMN archive_status;
ALTER TABLE app.review_records DROP COLUMN return_target;
-- case_id 保留为冗余定位列（查询索引常用），但不作为权威绑定
ALTER TABLE app.review_records ALTER COLUMN status TYPE varchar(32);
ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_status_check;

ALTER TABLE app.review_records ADD CONSTRAINT ck_review_status
    CHECK (status IN ('pending','approved','rejected','superseded'));
ALTER TABLE app.review_records ADD CONSTRAINT ck_review_decision_time
    CHECK ((status = 'pending' AND decided_at IS NULL)
        OR (status <> 'pending' AND decided_at IS NOT NULL));

CREATE INDEX ix_review_artifact_status
ON app.review_records(artifact_version_id, status, created_at DESC);
CREATE INDEX ix_review_case ON app.review_records(case_id);
