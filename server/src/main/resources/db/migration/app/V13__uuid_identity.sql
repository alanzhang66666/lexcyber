-- V13 — 主键迁移到 uuid（ADR 见 docs/architecture-roadmap.md，目标架构 v1.3 §4.6）
--
-- cases / documents / case_drafts 的 TEXT 主键（case-xxx / doc-xxx / draft-xxx）不可
-- 强转 uuid，故为每行分配新 uuid 并在 app.legacy_id_map 保留旧值映射，/v1 入口据此解析。
-- MinIO storage_key 为不透明字符串且已持久化，保持原值，不重写对象。
-- tasks.case_id 原以 '' 表示「无案件」，迁移为 NULL；normalize 触发器随之移除。

-- digest()/gen_random_uuid() 依赖 pgcrypto；显式装到 public（Flyway 迁移期 search_path=app，
-- 不指定 schema 会把函数装进 app schema，业务角色运行时 search_path 找不到）。
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
ALTER EXTENSION pgcrypto SET SCHEMA public;

CREATE TABLE app.legacy_id_map (
  legacy_id   TEXT PRIMARY KEY,
  entity_kind VARCHAR(16) NOT NULL CHECK (entity_kind IN ('case', 'document', 'draft')),
  uuid_id     UUID NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------------
-- 1. 解除对 TEXT id 列的全部依赖（FK / 触发器 / 唯一索引 / 普通索引 / CHECK）
-- ---------------------------------------------------------------------------

ALTER TABLE app.documents DROP CONSTRAINT IF EXISTS documents_case_id_fkey;
ALTER TABLE app.case_facts DROP CONSTRAINT IF EXISTS case_facts_case_id_fkey;
ALTER TABLE app.case_module_states DROP CONSTRAINT IF EXISTS case_module_states_case_id_fkey;
ALTER TABLE app.case_drafts DROP CONSTRAINT IF EXISTS case_drafts_case_id_fkey;
ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_case_id_fkey;
ALTER TABLE app.review_records DROP CONSTRAINT IF EXISTS review_records_draft_id_fkey;
ALTER TABLE app.upload_idempotency DROP CONSTRAINT IF EXISTS upload_idempotency_case_id_fkey;
ALTER TABLE app.upload_idempotency DROP CONSTRAINT IF EXISTS upload_idempotency_document_id_fkey;
ALTER TABLE app.case_create_idempotency DROP CONSTRAINT IF EXISTS case_create_idempotency_case_id_fkey;
ALTER TABLE app.review_open_idempotency DROP CONSTRAINT IF EXISTS review_open_idempotency_case_id_fkey;
ALTER TABLE app.import_items DROP CONSTRAINT IF EXISTS import_items_owner_account_id_case_id_fkey;
ALTER TABLE app.external_resource_map DROP CONSTRAINT IF EXISTS external_resource_map_owner_account_id_case_id_fkey;
ALTER TABLE app.external_resource_map DROP CONSTRAINT IF EXISTS external_resource_map_case_id_document_id_fkey;

DROP TRIGGER IF EXISTS trg_tasks_case_id ON app.tasks;
DROP FUNCTION IF EXISTS app.normalize_case_id;

DROP INDEX IF EXISTS app.ux_cases_owner_id;
DROP INDEX IF EXISTS app.ux_documents_case_id;
DROP INDEX IF EXISTS app.ix_documents_case_created;
DROP INDEX IF EXISTS app.ix_review_records_case;
DROP INDEX IF EXISTS app.ix_review_records_draft;
DROP INDEX IF EXISTS app.ix_import_items_case;
DROP INDEX IF EXISTS app.external_resource_map_case;
DROP INDEX IF EXISTS app.ix_external_resource_map_case;
DROP INDEX IF EXISTS app.ix_external_resource_map_document;
DROP INDEX IF EXISTS app.ix_case_create_idempotency_case;

-- external_resource_map 上把 internal_resource_id(TEXT) 与 case_id/document_id 比较的
-- 自动命名 CHECK 必须先删（类型改变后比较不成立）。
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'app.external_resource_map'::regclass AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%internal_resource_id%'
  LOOP
    EXECUTE format('ALTER TABLE app.external_resource_map DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 2. 三张主表：分配新 uuid、登记 legacy 映射、换主键
-- ---------------------------------------------------------------------------

ALTER TABLE app.cases DROP CONSTRAINT cases_pkey;
ALTER TABLE app.cases RENAME COLUMN id TO legacy_id;
ALTER TABLE app.cases ADD COLUMN id UUID;
UPDATE app.cases SET id = gen_random_uuid();
ALTER TABLE app.cases ALTER COLUMN id SET NOT NULL;
INSERT INTO app.legacy_id_map (legacy_id, entity_kind, uuid_id)
  SELECT legacy_id, 'case', id FROM app.cases;
ALTER TABLE app.cases ADD PRIMARY KEY (id);
ALTER TABLE app.cases DROP COLUMN legacy_id;

ALTER TABLE app.documents DROP CONSTRAINT documents_pkey;
ALTER TABLE app.documents RENAME COLUMN id TO legacy_id;
ALTER TABLE app.documents ADD COLUMN id UUID;
UPDATE app.documents SET id = gen_random_uuid();
ALTER TABLE app.documents ALTER COLUMN id SET NOT NULL;
INSERT INTO app.legacy_id_map (legacy_id, entity_kind, uuid_id)
  SELECT legacy_id, 'document', id FROM app.documents;
ALTER TABLE app.documents ADD PRIMARY KEY (id);
ALTER TABLE app.documents DROP COLUMN legacy_id;

ALTER TABLE app.case_drafts DROP CONSTRAINT case_drafts_pkey;
ALTER TABLE app.case_drafts RENAME COLUMN id TO legacy_id;
ALTER TABLE app.case_drafts ADD COLUMN id UUID;
UPDATE app.case_drafts SET id = gen_random_uuid();
ALTER TABLE app.case_drafts ALTER COLUMN id SET NOT NULL;
INSERT INTO app.legacy_id_map (legacy_id, entity_kind, uuid_id)
  SELECT legacy_id, 'draft', id FROM app.case_drafts;
ALTER TABLE app.case_drafts ADD PRIMARY KEY (id);
ALTER TABLE app.case_drafts DROP COLUMN legacy_id;

-- ---------------------------------------------------------------------------
-- 3. 引用列：TEXT -> uuid（经 legacy_id_map 回填），随后重建 FK / PK / 索引 / CHECK
-- ---------------------------------------------------------------------------

-- documents.case_id
ALTER TABLE app.documents ADD COLUMN case_id_uuid UUID;
UPDATE app.documents d SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = d.case_id;
ALTER TABLE app.documents ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.documents DROP COLUMN case_id;
ALTER TABLE app.documents RENAME COLUMN case_id_uuid TO case_id;

-- case_facts.case_id（PK 成员）
ALTER TABLE app.case_facts DROP CONSTRAINT case_facts_pkey;
ALTER TABLE app.case_facts ADD COLUMN case_id_uuid UUID;
UPDATE app.case_facts f SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = f.case_id;
ALTER TABLE app.case_facts ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.case_facts DROP COLUMN case_id;
ALTER TABLE app.case_facts RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE app.case_facts ADD PRIMARY KEY (case_id);

-- case_module_states.case_id（PK 成员）
ALTER TABLE app.case_module_states DROP CONSTRAINT case_module_states_pkey;
ALTER TABLE app.case_module_states ADD COLUMN case_id_uuid UUID;
UPDATE app.case_module_states s SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = s.case_id;
ALTER TABLE app.case_module_states ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.case_module_states DROP COLUMN case_id;
ALTER TABLE app.case_module_states RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE app.case_module_states ADD PRIMARY KEY (case_id, module);

-- case_drafts.case_id
ALTER TABLE app.case_drafts ADD COLUMN case_id_uuid UUID;
UPDATE app.case_drafts d SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = d.case_id;
ALTER TABLE app.case_drafts ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.case_drafts DROP COLUMN case_id;
ALTER TABLE app.case_drafts RENAME COLUMN case_id_uuid TO case_id;

-- review_records.case_id / draft_id（均可空）
ALTER TABLE app.review_records ADD COLUMN case_id_uuid UUID;
UPDATE app.review_records r SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = r.case_id;
ALTER TABLE app.review_records DROP COLUMN case_id;
ALTER TABLE app.review_records RENAME COLUMN case_id_uuid TO case_id;

ALTER TABLE app.review_records ADD COLUMN draft_id_uuid UUID;
UPDATE app.review_records r SET draft_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'draft' AND m.legacy_id = r.draft_id;
ALTER TABLE app.review_records DROP COLUMN draft_id;
ALTER TABLE app.review_records RENAME COLUMN draft_id_uuid TO draft_id;

-- tasks.case_id：'' 哨兵 -> NULL
ALTER TABLE app.tasks ADD COLUMN case_id_uuid UUID;
UPDATE app.tasks t SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = NULLIF(t.case_id, '');
ALTER TABLE app.tasks DROP COLUMN case_id;
ALTER TABLE app.tasks RENAME COLUMN case_id_uuid TO case_id;

-- upload_idempotency.case_id / document_id
ALTER TABLE app.upload_idempotency DROP CONSTRAINT upload_idempotency_pkey;
ALTER TABLE app.upload_idempotency ADD COLUMN case_id_uuid UUID;
UPDATE app.upload_idempotency u SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = u.case_id;
ALTER TABLE app.upload_idempotency ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.upload_idempotency DROP COLUMN case_id;
ALTER TABLE app.upload_idempotency RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE app.upload_idempotency ADD COLUMN document_id_uuid UUID;
UPDATE app.upload_idempotency u SET document_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'document' AND m.legacy_id = u.document_id;
ALTER TABLE app.upload_idempotency DROP COLUMN document_id;
ALTER TABLE app.upload_idempotency RENAME COLUMN document_id_uuid TO document_id;
ALTER TABLE app.upload_idempotency ADD PRIMARY KEY (account_id, case_id, idempotency_key);

-- case_create_idempotency.case_id
ALTER TABLE app.case_create_idempotency ADD COLUMN case_id_uuid UUID;
UPDATE app.case_create_idempotency e SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = e.case_id;
ALTER TABLE app.case_create_idempotency DROP COLUMN case_id;
ALTER TABLE app.case_create_idempotency RENAME COLUMN case_id_uuid TO case_id;

-- review_open_idempotency.case_id（PK 成员）
ALTER TABLE app.review_open_idempotency DROP CONSTRAINT review_open_idempotency_pkey;
ALTER TABLE app.review_open_idempotency ADD COLUMN case_id_uuid UUID;
UPDATE app.review_open_idempotency e SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = e.case_id;
ALTER TABLE app.review_open_idempotency ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.review_open_idempotency DROP COLUMN case_id;
ALTER TABLE app.review_open_idempotency RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE app.review_open_idempotency ADD PRIMARY KEY (account_id, case_id, idempotency_key);

-- import_items.case_id（可空；applied 行必有值）
ALTER TABLE app.import_items ADD COLUMN case_id_uuid UUID;
UPDATE app.import_items i SET case_id_uuid = m.uuid_id
  FROM app.legacy_id_map m
  WHERE m.entity_kind = 'case' AND m.legacy_id = i.case_id;
ALTER TABLE app.import_items DROP COLUMN case_id;
ALTER TABLE app.import_items RENAME COLUMN case_id_uuid TO case_id;
ALTER TABLE app.import_items ADD CONSTRAINT import_items_applied_case
  CHECK (status <> 'applied' OR case_id IS NOT NULL);

-- external_resource_map.case_id / document_id
ALTER TABLE app.external_resource_map ADD COLUMN case_id_uuid UUID;
UPDATE app.external_resource_map m SET case_id_uuid = lm.uuid_id
  FROM app.legacy_id_map lm
  WHERE lm.entity_kind = 'case' AND lm.legacy_id = m.case_id;
ALTER TABLE app.external_resource_map ALTER COLUMN case_id_uuid SET NOT NULL;
ALTER TABLE app.external_resource_map DROP COLUMN case_id;
ALTER TABLE app.external_resource_map RENAME COLUMN case_id_uuid TO case_id;

ALTER TABLE app.external_resource_map ADD COLUMN document_id_uuid UUID;
UPDATE app.external_resource_map m SET document_id_uuid = lm.uuid_id
  FROM app.legacy_id_map lm
  WHERE lm.entity_kind = 'document' AND lm.legacy_id = m.document_id;
ALTER TABLE app.external_resource_map DROP COLUMN document_id;
ALTER TABLE app.external_resource_map RENAME COLUMN document_id_uuid TO document_id;

-- internal_resource_id 保持 TEXT（多态：case / document / module_state / review 等），
-- 但其值在 type=case|document 时必须等于对应 uuid 的文本形式。
UPDATE app.external_resource_map m SET internal_resource_id = lm.uuid_id::text
  FROM app.legacy_id_map lm
  WHERE (m.internal_resource_type = 'case' AND lm.entity_kind = 'case'
         AND m.internal_resource_id = lm.legacy_id)
     OR (m.internal_resource_type = 'document' AND lm.entity_kind = 'document'
         AND m.internal_resource_id = lm.legacy_id);

ALTER TABLE app.external_resource_map ADD CONSTRAINT external_resource_map_internal_case
  CHECK (internal_resource_type <> 'case' OR internal_resource_id = case_id::text);
ALTER TABLE app.external_resource_map ADD CONSTRAINT external_resource_map_internal_document
  CHECK (internal_resource_type <> 'document'
         OR (document_id IS NOT NULL AND internal_resource_id = document_id::text));

-- cases.metadata_json 内 relations.events[].documentId：改写为新 uuid 文本
UPDATE app.cases c SET metadata_json = jsonb_set(
    c.metadata_json, '{relations,events}', (
      SELECT jsonb_agg(
          CASE WHEN lm.uuid_id IS NULL THEN e
               ELSE jsonb_set(e, '{documentId}', to_jsonb(lm.uuid_id::text))
          END)
      FROM jsonb_array_elements(c.metadata_json -> 'relations' -> 'events') e
      LEFT JOIN app.legacy_id_map lm
        ON lm.entity_kind = 'document' AND lm.legacy_id = e ->> 'documentId'))
WHERE jsonb_typeof(c.metadata_json -> 'relations' -> 'events') = 'array'
  AND c.metadata_json -> 'relations' -> 'events' <> '[]'::jsonb;

-- ---------------------------------------------------------------------------
-- 4. 重建唯一索引、FK、普通索引
-- ---------------------------------------------------------------------------

CREATE UNIQUE INDEX ux_cases_owner_id ON app.cases(owner_account_id, id);
CREATE UNIQUE INDEX ux_documents_case_id ON app.documents(case_id, id);
CREATE INDEX ix_documents_case_created ON app.documents(case_id, created_at DESC);
CREATE INDEX ix_review_records_case ON app.review_records(case_id);
CREATE INDEX ix_review_records_draft ON app.review_records(draft_id);
CREATE INDEX ix_import_items_case ON app.import_items(case_id) WHERE case_id IS NOT NULL;
CREATE INDEX ix_external_resource_map_case ON app.external_resource_map(case_id, internal_resource_type);
CREATE INDEX ix_external_resource_map_document ON app.external_resource_map(document_id) WHERE document_id IS NOT NULL;
CREATE INDEX ix_case_create_idempotency_case ON app.case_create_idempotency(case_id);

-- draft_id 列删除时 review_records_target_present 被连带移除，重建（同 V9 定义）。
ALTER TABLE app.review_records ADD CONSTRAINT review_records_target_present
  CHECK (task_id IS NOT NULL OR draft_id IS NOT NULL OR module_state IS NOT NULL);

ALTER TABLE app.documents ADD CONSTRAINT documents_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.case_facts ADD CONSTRAINT case_facts_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.case_module_states ADD CONSTRAINT case_module_states_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.case_drafts ADD CONSTRAINT case_drafts_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.review_records ADD CONSTRAINT review_records_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.review_records ADD CONSTRAINT review_records_draft_id_fkey
  FOREIGN KEY (draft_id) REFERENCES app.case_drafts(id);
ALTER TABLE app.upload_idempotency ADD CONSTRAINT upload_idempotency_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.upload_idempotency ADD CONSTRAINT upload_idempotency_document_id_fkey
  FOREIGN KEY (document_id) REFERENCES app.documents(id);
ALTER TABLE app.case_create_idempotency ADD CONSTRAINT case_create_idempotency_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.review_open_idempotency ADD CONSTRAINT review_open_idempotency_case_id_fkey
  FOREIGN KEY (case_id) REFERENCES app.cases(id);
ALTER TABLE app.import_items ADD CONSTRAINT import_items_owner_account_id_case_id_fkey
  FOREIGN KEY (owner_account_id, case_id) REFERENCES app.cases(owner_account_id, id);
ALTER TABLE app.external_resource_map ADD CONSTRAINT external_resource_map_owner_account_id_case_id_fkey
  FOREIGN KEY (owner_account_id, case_id) REFERENCES app.cases(owner_account_id, id);
ALTER TABLE app.external_resource_map ADD CONSTRAINT external_resource_map_case_id_document_id_fkey
  FOREIGN KEY (case_id, document_id) REFERENCES app.documents(case_id, id);
