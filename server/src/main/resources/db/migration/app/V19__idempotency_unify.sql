-- V19 — 统一幂等（v1.3 §4.9）
-- 合并 upload_idempotency / case_create_idempotency / review_open_idempotency 三张表。
-- 幂等记录与目标资源创建在同一 app 事务内完成（由服务层保证）。

CREATE TABLE app.idempotency_record (
    principal_id       uuid NOT NULL,
    idempotency_key    varchar(200) NOT NULL,
    request_hash       text NOT NULL,
    resource_type      varchar(64) NOT NULL,
    resource_id        uuid NOT NULL,
    response_status    integer NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (principal_id, idempotency_key)
);
CREATE INDEX ix_idempotency_resource ON app.idempotency_record(resource_type, resource_id);

-- 回填三张旧表。resource_id 必须可解释为目标资源 uuid：
--   upload  → document_id；case_create → case_id；review_open → review_id
INSERT INTO app.idempotency_record(principal_id, idempotency_key, request_hash,
                                   resource_type, resource_id, response_status, created_at)
SELECT account_id, idempotency_key, request_hash, 'document', document_id, 200, created_at
FROM app.upload_idempotency
WHERE document_id IS NOT NULL
ON CONFLICT (principal_id, idempotency_key) DO NOTHING;

INSERT INTO app.idempotency_record(principal_id, idempotency_key, request_hash,
                                   resource_type, resource_id, response_status, created_at)
SELECT account_id, idempotency_key, request_hash, 'case', case_id, 200, created_at
FROM app.case_create_idempotency
WHERE case_id IS NOT NULL
ON CONFLICT (principal_id, idempotency_key) DO NOTHING;

INSERT INTO app.idempotency_record(principal_id, idempotency_key, request_hash,
                                   resource_type, resource_id, response_status, created_at)
SELECT account_id, idempotency_key, request_hash, 'review', review_id, 200, created_at
FROM app.review_open_idempotency
WHERE review_id IS NOT NULL
-- 旧表 PK 为 (account_id, case_id, key) 三段；收敛为两段时可能碰撞 → 保留先到者
ON CONFLICT (principal_id, idempotency_key) DO NOTHING;

DROP TABLE app.upload_idempotency;
DROP TABLE app.case_create_idempotency;
DROP TABLE app.review_open_idempotency;
