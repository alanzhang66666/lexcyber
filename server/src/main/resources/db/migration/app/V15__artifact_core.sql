-- V15 — ArtifactStream / ArtifactVersion / 依赖表 / execution_publication（v1.3 §4.6.4-4.6.6、4.6.10）
-- 三套结果存储（result_versions / case_module_states.content_json / case_drafts.body）合并为一套。
-- 回填映射保存在 app.artifact_backfill_map，供 V16（heads）与 V17（review 改绑）使用。

-- ---------------------------------------------------------------------------
-- 1. 核心表（DDL 与 v1.3 §4.6 逐字对齐；execution_id 不设跨 schema FK）
-- ---------------------------------------------------------------------------

CREATE TABLE app.artifact_stream (
    artifact_stream_id uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    kind                varchar(32) NOT NULL,
    scope_key           text NOT NULL,
    latest_version_id   uuid NULL,
    next_version        integer NOT NULL DEFAULT 1 CHECK (next_version > 0),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT ck_artifact_stream_kind CHECK (
        kind IN ('parse','compliance','conviction','sentencing','draft')
    ),
    CONSTRAINT uq_artifact_stream_scope UNIQUE (case_id, kind, scope_key),
    CONSTRAINT uq_artifact_stream_pair UNIQUE (artifact_stream_id, case_id)
);

CREATE TABLE app.artifact_version (
    artifact_version_id uuid PRIMARY KEY,
    artifact_stream_id  uuid NOT NULL REFERENCES app.artifact_stream(artifact_stream_id),
    version             integer NOT NULL CHECK (version > 0),
    schema_version      varchar(128) NOT NULL,
    outcome_status      varchar(32) NOT NULL,
    payload             jsonb NOT NULL,
    blockers            jsonb NOT NULL DEFAULT '[]'::jsonb,
    dependency_snapshot jsonb NOT NULL,
    execution_id        uuid NULL,
    output_hash         text NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_artifact_version_stream_version
        UNIQUE (artifact_stream_id, version),
    CONSTRAINT uq_artifact_version_stream_id
        UNIQUE (artifact_stream_id, artifact_version_id),
    CONSTRAINT ck_artifact_outcome CHECK (
        outcome_status IN ('calculated','blocked','not_applicable')
    ),
    CONSTRAINT ck_artifact_blockers_shape CHECK (
        jsonb_typeof(blockers) = 'array'
    ),
    CONSTRAINT ck_artifact_dependency_shape CHECK (
        jsonb_typeof(dependency_snapshot) = 'object'
    )
);

ALTER TABLE app.artifact_stream
ADD CONSTRAINT fk_artifact_stream_latest_same_stream
FOREIGN KEY (artifact_stream_id, latest_version_id)
REFERENCES app.artifact_version(artifact_stream_id, artifact_version_id)
DEFERRABLE INITIALLY DEFERRED;

-- ADR-0001：execution_publication 为权威绑定；本约束是第二层防线（手工发布 execution_id 为 NULL，不受限）
CREATE UNIQUE INDEX ux_artifact_version_execution
ON app.artifact_version(execution_id)
WHERE execution_id IS NOT NULL;

CREATE TABLE app.artifact_facts_dependency (
    artifact_version_id uuid PRIMARY KEY REFERENCES app.artifact_version(artifact_version_id),
    facts_version_id    uuid NOT NULL REFERENCES app.facts_version(facts_version_id)
);

CREATE TABLE app.artifact_artifact_dependency (
    artifact_version_id            uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    depends_on_artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    PRIMARY KEY (artifact_version_id, depends_on_artifact_version_id),
    CONSTRAINT ck_artifact_no_self_dependency
        CHECK (artifact_version_id <> depends_on_artifact_version_id)
);

CREATE TABLE app.artifact_external_dependency (
    artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    dependency_kind     varchar(32) NOT NULL,
    dependency_key      text NOT NULL,
    dependency_version  text NOT NULL,
    PRIMARY KEY (artifact_version_id, dependency_kind, dependency_key, dependency_version),
    CONSTRAINT ck_external_dependency_kind CHECK (
        dependency_kind IN ('rule','legal_source','template')
    )
);

CREATE TABLE app.execution_publication (
    execution_id        uuid PRIMARY KEY,
    artifact_version_id uuid NOT NULL UNIQUE REFERENCES app.artifact_version(artifact_version_id),
    completion_identity text NOT NULL,
    output_hash         text NOT NULL,
    published_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_artifact_version_stream_created
ON app.artifact_version(artifact_stream_id, created_at DESC);
CREATE INDEX ix_artifact_facts_dependency_facts
ON app.artifact_facts_dependency(facts_version_id, artifact_version_id);
CREATE INDEX ix_artifact_dependency_upstream
ON app.artifact_artifact_dependency(depends_on_artifact_version_id, artifact_version_id);
CREATE INDEX ix_artifact_external_dependency_lookup
ON app.artifact_external_dependency(dependency_kind, dependency_key, dependency_version);
CREATE INDEX ix_artifact_stream_case_kind
ON app.artifact_stream(case_id, kind);

-- ---------------------------------------------------------------------------
-- 2. 回填映射表（V16/V17 使用；非业务表，供迁移期解析旧外键）
-- ---------------------------------------------------------------------------

CREATE TABLE app.artifact_backfill_map (
    artifact_version_id uuid PRIMARY KEY REFERENCES app.artifact_version(artifact_version_id),
    source_kind         varchar(16) NOT NULL CHECK (source_kind IN ('result','module','draft')),
    task_id             uuid,
    result_version      integer,
    case_id             uuid,
    module              varchar(32),
    draft_id            uuid,
    draft_version       integer
);
CREATE INDEX ix_backfill_map_task ON app.artifact_backfill_map(task_id, result_version) WHERE task_id IS NOT NULL;
CREATE INDEX ix_backfill_map_module ON app.artifact_backfill_map(case_id, module) WHERE module IS NOT NULL;
CREATE INDEX ix_backfill_map_draft ON app.artifact_backfill_map(draft_id) WHERE draft_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3. 回填：result_versions → parse stream
--    scope_key = 'document:{document_id}'；stream 按 (document 的 parse_task_id → task → case) 定位。
--    tasks.status failed/timed_out 不产生 version（INV-ARTIFACT-002）。
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    s   record;
    rv  record;
    v_stream uuid;
    v_ver    uuid;
    v_next   int;
BEGIN
    FOR s IN
        SELECT DISTINCT t.case_id AS case_id, d.id AS document_id
        FROM app.result_versions r
        JOIN app.tasks t ON t.id = r.task_id
        JOIN app.documents d ON d.parse_task_id = t.id
        WHERE t.case_id IS NOT NULL
          AND t.status IN ('completed','waiting_review')
    LOOP
        v_stream := gen_random_uuid();
        INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key)
        VALUES (v_stream, s.case_id, 'parse', 'document:' || s.document_id::text);

        v_next := 1;
        FOR rv IN
            SELECT r.result_id, r.task_id, r.version, r.result_type, r.content_json, r.content_hash,
                   r.created_at, r.execution_id, r.source_refs_json
            FROM app.result_versions r
            JOIN app.tasks t ON t.id = r.task_id
            JOIN app.documents d ON d.parse_task_id = t.id
            WHERE d.id = s.document_id AND t.case_id = s.case_id
              AND t.status IN ('completed','waiting_review')
            ORDER BY r.version
        LOOP
            v_ver := gen_random_uuid();
            INSERT INTO app.artifact_version(
                artifact_version_id, artifact_stream_id, version, schema_version,
                outcome_status, payload, blockers, dependency_snapshot,
                execution_id, output_hash, created_at)
            VALUES (
                v_ver, v_stream, v_next, COALESCE(rv.result_type, 'document.parse.v1'),
                'calculated', rv.content_json, '[]'::jsonb,
                jsonb_build_object('source_refs', COALESCE(rv.source_refs_json, '[]'::jsonb)),
                rv.execution_id, rv.content_hash, rv.created_at);
            INSERT INTO app.artifact_backfill_map(artifact_version_id, source_kind, task_id, result_version)
            VALUES (v_ver, 'result', rv.task_id, rv.version);
            v_next := v_next + 1;
        END LOOP;

        UPDATE app.artifact_stream
        SET next_version = v_next,
            latest_version_id = (
                SELECT artifact_version_id FROM app.artifact_version
                WHERE artifact_stream_id = v_stream ORDER BY version DESC LIMIT 1)
        WHERE artifact_stream_id = v_stream;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 4. 回填：module stream = 非 parse 任务的执行结果 + case_module_states.content_json
--    taskType→module 只映射已定义模块；其余带案任务结果写审计不丢（INV-ARTIFACT-002）。
--    同一 (case,module) 只建一条 stream；执行版本与手工版本按时间归并编号。
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    s        record;
    v        record;
    v_stream uuid;
    v_ver    uuid;
    v_next   int;
BEGIN
    FOR s IN
        SELECT DISTINCT x.case_id, x.module
        FROM (
            SELECT t.case_id,
                   CASE t.metadata_json ->> 'taskType'
                       WHEN 'sentencing.calculate' THEN 'sentencing'
                       WHEN 'compliance.analyze'   THEN 'compliance'
                       WHEN 'conviction.analyze'   THEN 'conviction'
                   END AS module
            FROM app.result_versions r
            JOIN app.tasks t ON t.id = r.task_id
            WHERE t.case_id IS NOT NULL
              AND t.status IN ('completed','waiting_review')
              AND NOT EXISTS (SELECT 1 FROM app.documents d WHERE d.parse_task_id = t.id)
            UNION
            SELECT ms.case_id, ms.module FROM app.case_module_states ms
        ) x
        WHERE x.module IS NOT NULL
        ORDER BY x.case_id, x.module
    LOOP
        v_stream := gen_random_uuid();
        INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key)
        VALUES (v_stream, s.case_id, s.module, 'module:' || s.module);

        v_next := 1;
        FOR v IN
            SELECT * FROM (
                SELECT r.result_id, r.task_id, r.version AS result_version,
                       r.result_type, r.content_json, r.content_hash,
                       r.created_at, r.execution_id, r.source_refs_json,
                       'result'::text AS src
                FROM app.result_versions r
                JOIN app.tasks t ON t.id = r.task_id
                WHERE t.case_id = s.case_id
                  AND t.status IN ('completed','waiting_review')
                  AND NOT EXISTS (SELECT 1 FROM app.documents d WHERE d.parse_task_id = t.id)
                  AND CASE t.metadata_json ->> 'taskType'
                        WHEN 'sentencing.calculate' THEN 'sentencing'
                        WHEN 'compliance.analyze'   THEN 'compliance'
                        WHEN 'conviction.analyze'   THEN 'conviction'
                      END = s.module
                UNION ALL
                SELECT NULL::uuid, NULL::uuid, NULL::int,
                       ms.schema_version, ms.content_json,
                       encode(digest(ms.content_json::text, 'sha256'), 'hex'),
                       ms.updated_at, NULL::uuid, NULL::jsonb,
                       'module'::text
                FROM app.case_module_states ms
                WHERE ms.case_id = s.case_id AND ms.module = s.module
            ) allv
            ORDER BY allv.created_at, allv.src
        LOOP
            v_ver := gen_random_uuid();
            INSERT INTO app.artifact_version(
                artifact_version_id, artifact_stream_id, version, schema_version,
                outcome_status, payload, blockers, dependency_snapshot,
                execution_id, output_hash, created_at)
            VALUES (
                v_ver, v_stream, v_next,
                COALESCE(v.result_type, 'case.module.v1'),
                'calculated', v.content_json, '[]'::jsonb,
                jsonb_build_object('source_refs', COALESCE(v.source_refs_json, '[]'::jsonb)),
                v.execution_id, v.content_hash, v.created_at);
            IF v.src = 'result' THEN
                INSERT INTO app.artifact_backfill_map(artifact_version_id, source_kind, task_id, result_version)
                VALUES (v_ver, 'result', v.task_id, v.result_version);
            ELSE
                INSERT INTO app.artifact_backfill_map(artifact_version_id, source_kind, case_id, module)
                VALUES (v_ver, 'module', s.case_id, s.module);
            END IF;
            v_next := v_next + 1;
        END LOOP;

        UPDATE app.artifact_stream
        SET next_version = v_next,
            latest_version_id = (
                SELECT artifact_version_id FROM app.artifact_version
                WHERE artifact_stream_id = v_stream ORDER BY version DESC LIMIT 1)
        WHERE artifact_stream_id = v_stream;
    END LOOP;

    -- 未映射任务类型的执行结果：审计留存，不静默丢弃
    INSERT INTO app.business_audit(actor, action, resource_type, resource_id, payload_json)
    SELECT 'migration-v15', 'result_version_unmapped_tasktype',
           'result_version', r.result_id::text,
           jsonb_build_object('task_id', r.task_id, 'version', r.version,
                              'task_type', t.metadata_json ->> 'taskType',
                              'case_id', t.case_id, 'task_status', t.status)
    FROM app.result_versions r
    JOIN app.tasks t ON t.id = r.task_id
    WHERE NOT EXISTS (SELECT 1 FROM app.documents d WHERE d.parse_task_id = t.id)
      AND (t.case_id IS NULL
           OR t.status NOT IN ('completed','waiting_review')
           OR COALESCE(t.metadata_json ->> 'taskType', '') NOT IN
              ('sentencing.calculate','compliance.analyze','conviction.analyze'));
END $$;

-- ---------------------------------------------------------------------------
-- 5. 回填：case_drafts → draft stream（body 进入 payload；描述列留在 slim 表）
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    d  record;
    v_stream uuid;
    v_ver    uuid;
BEGIN
    FOR d IN SELECT id, case_id, draft_type, body, version, template_version, source_version, updated_at
             FROM app.case_drafts
    LOOP
        v_stream := gen_random_uuid();
        INSERT INTO app.artifact_stream(artifact_stream_id, case_id, kind, scope_key)
        VALUES (v_stream, d.case_id, 'draft', 'draft:' || d.id::text);

        v_ver := gen_random_uuid();
        INSERT INTO app.artifact_version(
            artifact_version_id, artifact_stream_id, version, schema_version,
            outcome_status, payload, blockers, dependency_snapshot,
            execution_id, output_hash, created_at)
        VALUES (
            v_ver, v_stream, 1, 'case.draft.v1',
            'calculated',
            jsonb_build_object('body', d.body, 'draft_type', d.draft_type,
                               'template_version', d.template_version,
                               'source_version', d.source_version),
            '[]'::jsonb, '{}'::jsonb,
            NULL, encode(digest(d.body, 'sha256'), 'hex'), d.updated_at);
        INSERT INTO app.artifact_backfill_map(artifact_version_id, source_kind, case_id, draft_id, draft_version)
        VALUES (v_ver, 'draft', d.case_id, d.id, d.version);

        UPDATE app.artifact_stream
        SET latest_version_id = v_ver, next_version = 2
        WHERE artifact_stream_id = v_stream;
    END LOOP;
END $$;

COMMENT ON TABLE app.result_versions IS
    'DEPRECATED by V15 — 结果由 artifact_version 承载；V17 完成 review 改绑后由后续迁移清理。';
COMMENT ON COLUMN app.case_module_states.content_json IS
    'DEPRECATED by V15 — 模块正文由 artifact_version.payload 承载；表在 V16 收敛为 head。';
COMMENT ON COLUMN app.case_drafts.body IS
    'DEPRECATED by V15 — 文书正文由 artifact_version.payload.body 承载；表在 V16 收敛为描述符。';
