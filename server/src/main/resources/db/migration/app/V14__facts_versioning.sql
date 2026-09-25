-- V14 — 可编辑实体表 + FactsVersion/FactsHead（v1.3 §4.6.2-4.6.3、INV-FACTS-001..005）
--
-- 实体表承载“当前编辑态”；facts_version 承载不可变快照。
-- facts_version_item 是快照成员索引（entity_id + 内容哈希），供依赖追踪使用。
-- 金额 kind 封闭 6 类（ADR-0003）；facts 版本号由 facts_head.next_version 在锁内分配
-- （与 artifact_stream.next_version / cases.next_archive_version 同构，见 ADR-0006）。

-- ---------------------------------------------------------------------------
-- 1. 案件级可编辑实体
-- ---------------------------------------------------------------------------

CREATE TABLE app.case_actor (
    actor_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    external_id         text,                    -- 数据集稳定 id；手工新增可为空
    actor_type          varchar(32),             -- natural_person | unit | organization
    name                text,
    role                text,
    attributes          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attributes) = 'object'),
    verification_status varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_actor_external UNIQUE (case_id, external_id)
);
CREATE INDEX ix_case_actor_case ON app.case_actor(case_id);

CREATE TABLE app.case_event (
    event_id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    external_id         text,
    event_date          date,
    stage               varchar(64),
    description         text,
    actor_id            uuid NULL REFERENCES app.case_actor(actor_id),
    attributes          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attributes) = 'object'),
    verification_status varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_event_external UNIQUE (case_id, external_id)
);
CREATE INDEX ix_case_event_case ON app.case_event(case_id);

CREATE TABLE app.case_evidence (
    evidence_id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    external_id         text,
    evidence_type       varchar(64),
    label               text,
    document_id         uuid NULL REFERENCES app.documents(id),
    locator             jsonb CHECK (locator IS NULL OR jsonb_typeof(locator) = 'object'),
    attributes          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attributes) = 'object'),
    verification_status varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_evidence_external UNIQUE (case_id, external_id)
);
CREATE INDEX ix_case_evidence_case ON app.case_evidence(case_id);

CREATE TABLE app.case_amount (
    amount_id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    external_id         text,
    kind                varchar(64) NOT NULL,
    label               text,
    value               numeric(20, 4),
    currency            varchar(8) NOT NULL DEFAULT 'CNY',
    component_of        uuid NULL REFERENCES app.case_amount(amount_id),
    evidence_ids        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence_ids) = 'array'),
    verification_status varchar(64),
    attributes          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attributes) = 'object'),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_amount_external UNIQUE (case_id, external_id),
    CONSTRAINT ck_case_amount_kind CHECK (kind IN (
        'payment_settlement_amount', 'illegal_gain', 'crime_amount',
        'business_revenue', 'recovery', 'fine'
    )),
    CONSTRAINT ck_case_amount_no_self_component CHECK (component_of IS NULL OR component_of <> amount_id)
);
CREATE INDEX ix_case_amount_case ON app.case_amount(case_id);

CREATE TABLE app.case_jurisdiction_connection (
    connection_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    external_id         text,
    connection_type     varchar(64),             -- conduct_place | result_place | nationality | ...
    value               text,
    evidence_ids        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence_ids) = 'array'),
    verification_status varchar(64),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_jurisdiction_external UNIQUE (case_id, external_id)
);
CREATE INDEX ix_case_jurisdiction_case ON app.case_jurisdiction_connection(case_id);

-- fact 编辑态：对应现 case_facts.items_json 中的条目
CREATE TABLE app.case_fact (
    fact_id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    external_id         text,
    fact_key            text NOT NULL,
    fact_value          text NOT NULL,
    stage               varchar(64),
    actor_id            uuid NULL REFERENCES app.case_actor(actor_id),
    locator             text,
    source_document_id  uuid NULL REFERENCES app.documents(id),
    evidence_ids        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence_ids) = 'array'),
    verification_status varchar(64),
    source_version      varchar(128),
    attributes          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(attributes) = 'object'),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_case_fact_external UNIQUE (case_id, external_id)
);
CREATE INDEX ix_case_fact_case ON app.case_fact(case_id);

-- ---------------------------------------------------------------------------
-- 2. FactsVersion / FactsVersionItem / FactsHead（v1.3 §4.6.2-4.6.3）
--    不存 status 列（ADR-0002）；版本分配计数器放在 facts_head（锁内推进）。
-- ---------------------------------------------------------------------------

CREATE TABLE app.facts_version (
    facts_version_id uuid PRIMARY KEY,
    case_id          uuid NOT NULL REFERENCES app.cases(id),
    version          integer NOT NULL CHECK (version > 0),
    content_hash     text NOT NULL,
    payload          jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    created_by       uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    confirmed_by     uuid NULL,
    confirmed_at     timestamptz NULL,

    CONSTRAINT uq_facts_version_case_version
        UNIQUE (case_id, version),
    CONSTRAINT uq_facts_version_case_id
        UNIQUE (case_id, facts_version_id),
    CONSTRAINT ck_facts_version_confirmation_pair
        CHECK ((confirmed_by IS NULL) = (confirmed_at IS NULL))
);

CREATE TABLE app.facts_version_item (
    facts_version_id       uuid NOT NULL REFERENCES app.facts_version(facts_version_id),
    entity_kind            varchar(32) NOT NULL,
    entity_id              uuid NOT NULL,
    entity_version_or_hash text NOT NULL,
    PRIMARY KEY (facts_version_id, entity_kind, entity_id),
    CONSTRAINT ck_facts_item_kind CHECK (
        entity_kind IN ('fact','amount','actor','event','evidence','jurisdiction_connection')
    )
);

CREATE TABLE app.facts_head (
    case_id                    uuid PRIMARY KEY REFERENCES app.cases(id),
    confirmed_facts_version_id uuid NULL,
    next_version               integer NOT NULL DEFAULT 1 CHECK (next_version > 0),
    updated_at                 timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_facts_head_same_case
        FOREIGN KEY (case_id, confirmed_facts_version_id)
        REFERENCES app.facts_version(case_id, facts_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX ix_facts_version_case ON app.facts_version(case_id, version DESC);
CREATE INDEX ix_facts_version_item_entity ON app.facts_version_item(entity_kind, entity_id);

-- ---------------------------------------------------------------------------
-- 3. 回填：现有 case_facts 行 → facts_version v1 + facts_head
--    items_json 中的条目同时落成 case_fact 编辑实体（entity_version_or_hash = 条目内容哈希）。
-- ---------------------------------------------------------------------------

-- 每案预置 head 行（确认/分配版本号的行锁锚点；confirmed=NULL 表示无已确认版本）
INSERT INTO app.facts_head(case_id)
SELECT id FROM app.cases
ON CONFLICT (case_id) DO NOTHING;

DO $$
DECLARE
    r  record;
    it record;
    v_version_id uuid;
    v_fact_id    uuid;
    v_doc        uuid;
BEGIN
    FOR r IN SELECT cf.case_id, cf.items_json, cf.status, cf.updated_at, cf.confirmed_at
             FROM app.case_facts cf
    LOOP
        v_version_id := gen_random_uuid();
        INSERT INTO app.facts_version(
            facts_version_id, case_id, version, content_hash, payload, created_by, created_at,
            confirmed_by, confirmed_at)
        SELECT v_version_id, r.case_id, 1,
               encode(digest(COALESCE(r.items_json::text, '[]'), 'sha256'), 'hex'),
               jsonb_build_object('items', COALESCE(r.items_json, '[]'::jsonb)),
               c.owner_account_id, r.updated_at,
               CASE WHEN r.status = 'confirmed' THEN c.owner_account_id END,
               r.confirmed_at
        FROM app.cases c WHERE c.id = r.case_id;

        FOR it IN SELECT item FROM jsonb_array_elements(COALESCE(r.items_json, '[]'::jsonb)) item
        LOOP
            v_fact_id := gen_random_uuid();
            -- sourceDocumentId：先按旧 id 查 legacy_id_map；已是 uuid 形态则直接强转
            v_doc := NULL;
            IF it.item ->> 'sourceDocumentId' IS NOT NULL THEN
                SELECT lm.uuid_id INTO v_doc
                FROM app.legacy_id_map lm
                WHERE lm.entity_kind = 'document'
                  AND lm.legacy_id = it.item ->> 'sourceDocumentId';
                IF v_doc IS NULL
                   AND it.item ->> 'sourceDocumentId' ~*
                       '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
                    v_doc := (it.item ->> 'sourceDocumentId')::uuid;
                END IF;
            END IF;

            INSERT INTO app.case_fact(
                fact_id, case_id, external_id, fact_key, fact_value, locator,
                source_document_id, verification_status, source_version)
            VALUES (
                v_fact_id, r.case_id, it.item ->> 'id', it.item ->> 'key',
                COALESCE(it.item ->> 'value', ''), it.item ->> 'locator', v_doc,
                it.item ->> 'verificationStatus', it.item ->> 'sourceVersion');

            INSERT INTO app.facts_version_item(
                facts_version_id, entity_kind, entity_id, entity_version_or_hash)
            VALUES (
                v_version_id, 'fact', v_fact_id,
                encode(digest(it.item::text, 'sha256'), 'hex'));
        END LOOP;

        UPDATE app.facts_head
        SET confirmed_facts_version_id = CASE WHEN r.status = 'confirmed' THEN v_version_id END,
            next_version = 2,
            updated_at = r.updated_at
        WHERE case_id = r.case_id;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4. metadata_json.relations → 实体表（仅迁移已存在的子数组；字段名按现实现）
-- ---------------------------------------------------------------------------

-- actors: relations.actors[] → case_actor
INSERT INTO app.case_actor(case_id, external_id, actor_type, name, role, attributes)
SELECT c.id, a ->> 'id', a ->> 'type', a ->> 'name', a ->> 'role', a - 'id' - 'type' - 'name' - 'role'
FROM app.cases c
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(c.metadata_json -> 'relations' -> 'actors', '[]'::jsonb)) a
WHERE jsonb_typeof(c.metadata_json -> 'relations' -> 'actors') = 'array'
  AND jsonb_typeof(a) = 'object'
ON CONFLICT (case_id, external_id) DO NOTHING;

-- events: relations.events[] → case_event（字段为 eventId/documentId/locator，见 CaseService.associateDocumentToEvent）
INSERT INTO app.case_event(case_id, external_id, event_date, stage, description, attributes)
SELECT c.id, e ->> 'eventId',
       CASE WHEN e ->> 'date' ~ '^\d{4}-\d{2}-\d{2}$' THEN (e ->> 'date')::date END,
       e ->> 'stage', e ->> 'description', e
FROM app.cases c
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(c.metadata_json -> 'relations' -> 'events', '[]'::jsonb)) e
WHERE jsonb_typeof(c.metadata_json -> 'relations' -> 'events') = 'array'
  AND jsonb_typeof(e) = 'object'
  AND e ->> 'eventId' IS NOT NULL
ON CONFLICT (case_id, external_id) DO NOTHING;

-- evidence: relations.evidence[] → case_evidence
INSERT INTO app.case_evidence(case_id, external_id, evidence_type, label, document_id, locator, attributes)
SELECT c.id, ev ->> 'id', ev ->> 'type', ev ->> 'label',
       lm.uuid_id, ev -> 'locator', ev - 'id' - 'type' - 'label' - 'documentId' - 'locator'
FROM app.cases c
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(c.metadata_json -> 'relations' -> 'evidence', '[]'::jsonb)) ev
LEFT JOIN app.legacy_id_map lm
       ON lm.entity_kind = 'document' AND lm.legacy_id = ev ->> 'documentId'
WHERE jsonb_typeof(c.metadata_json -> 'relations' -> 'evidence') = 'array'
  AND jsonb_typeof(ev) = 'object'
ON CONFLICT (case_id, external_id) DO NOTHING;

-- amounts: relations.amounts[] → case_amount（kind 不在封闭集内的值归入 attributes 保留）
INSERT INTO app.case_amount(case_id, external_id, kind, label, value, currency,
                            evidence_ids, verification_status, attributes)
SELECT c.id, a ->> 'id',
       CASE WHEN a ->> 'kind' IN ('payment_settlement_amount','illegal_gain','crime_amount',
                                  'business_revenue','recovery','fine')
            THEN a ->> 'kind' ELSE 'crime_amount' END,
       a ->> 'label',
       CASE WHEN a ->> 'value' ~ '^-?\d+(\.\d+)?$' THEN (a ->> 'value')::numeric END,
       COALESCE(a ->> 'currency', 'CNY'),
       COALESCE(a -> 'evidence_ids', a -> 'evidenceIds', '[]'::jsonb),
       -- ADR-0003：kind 不可归类的存量数据标 conflicted（路由到缺失事项），不得静默映射
       CASE WHEN a ->> 'kind' IN ('payment_settlement_amount','illegal_gain','crime_amount',
                                  'business_revenue','recovery','fine')
            THEN a ->> 'verification_status'
            ELSE 'conflicted' END,
       CASE WHEN a ->> 'kind' IN ('payment_settlement_amount','illegal_gain','crime_amount',
                                  'business_revenue','recovery','fine')
            THEN '{}'::jsonb
            ELSE jsonb_build_object('original_kind', a ->> 'kind') END
FROM app.cases c
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(c.metadata_json -> 'relations' -> 'amounts', '[]'::jsonb)) a
WHERE jsonb_typeof(c.metadata_json -> 'relations' -> 'amounts') = 'array'
  AND jsonb_typeof(a) = 'object'
ON CONFLICT (case_id, external_id) DO NOTHING;

-- jurisdiction connections: relations.jurisdictionConnections[] / jurisdiction_connections[]
INSERT INTO app.case_jurisdiction_connection(case_id, external_id, connection_type, value,
                                             evidence_ids, verification_status)
SELECT c.id, j ->> 'id', COALESCE(j ->> 'type', j ->> 'connectionType'),
       COALESCE(j ->> 'value', j ->> 'label'),
       COALESCE(j -> 'evidence_ids', j -> 'evidenceIds', '[]'::jsonb),
       COALESCE(j ->> 'verification_status', j ->> 'verificationStatus')
FROM app.cases c
CROSS JOIN LATERAL jsonb_array_elements(
    COALESCE(c.metadata_json -> 'relations' -> 'jurisdictionConnections',
             c.metadata_json -> 'relations' -> 'jurisdiction_connections', '[]'::jsonb)) j
WHERE jsonb_typeof(j) = 'object'
ON CONFLICT (case_id, external_id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- 4b. 实体成员回登记：步骤 4 抽出的实体补进对应案件 v1 快照的成员索引
-- ---------------------------------------------------------------------------

INSERT INTO app.facts_version_item(facts_version_id, entity_kind, entity_id, entity_version_or_hash)
SELECT fv.facts_version_id, e.entity_kind, e.entity_id, e.content_hash
FROM app.facts_version fv
JOIN LATERAL (
    SELECT 'actor'::varchar AS entity_kind, actor_id AS entity_id,
           encode(digest(COALESCE(external_id,'') || '|' || COALESCE(name,''), 'sha256'), 'hex') AS content_hash
    FROM app.case_actor a WHERE a.case_id = fv.case_id
    UNION ALL
    SELECT 'event', event_id,
           encode(digest(COALESCE(external_id,'') || '|' || COALESCE(description,''), 'sha256'), 'hex')
    FROM app.case_event ev WHERE ev.case_id = fv.case_id
    UNION ALL
    SELECT 'evidence', evidence_id,
           encode(digest(COALESCE(external_id,'') || '|' || COALESCE(label,''), 'sha256'), 'hex')
    FROM app.case_evidence e2 WHERE e2.case_id = fv.case_id
    UNION ALL
    SELECT 'amount', amount_id,
           encode(digest(kind || '|' || COALESCE(value::text,''), 'sha256'), 'hex')
    FROM app.case_amount am WHERE am.case_id = fv.case_id
    UNION ALL
    SELECT 'jurisdiction_connection', connection_id,
           encode(digest(COALESCE(connection_type,'') || '|' || COALESCE(value,''), 'sha256'), 'hex')
    FROM app.case_jurisdiction_connection jc WHERE jc.case_id = fv.case_id
) e ON true
WHERE fv.version = 1
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- 5. 旧表退役：case_facts 语义由 facts_version/facts_head + case_fact 接管。
--    /v1 的 FactService 适配层不再读该表；表保留至阶段 3 清理，避免本迁移过度耦合。
-- ---------------------------------------------------------------------------
COMMENT ON TABLE app.case_facts IS
    'DEPRECATED by V14 — 事实基线由 facts_head/facts_version 承载；编辑态在 case_fact。待 V15+ 清理。';
