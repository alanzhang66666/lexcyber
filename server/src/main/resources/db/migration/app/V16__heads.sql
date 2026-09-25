-- V16 — ModuleHead / DraftHead（v1.3 §4.6.7-4.6.8、INV-MODULE-001/002、ADR-0004）
-- Head 只存指针与 stale 状态，不存正文。sentencing 首次成为模块。
-- 旧可变列（case_module_states.content_json/status/version、case_drafts.body/version）删除。

CREATE TABLE app.module_head (
    case_id              uuid NOT NULL REFERENCES app.cases(id),
    module               varchar(32) NOT NULL,
    artifact_stream_id   uuid NOT NULL REFERENCES app.artifact_stream(artifact_stream_id),
    confirmed_version_id uuid NULL,
    stale                boolean NOT NULL DEFAULT true,
    stale_reason         varchar(64) NULL,
    updated_at           timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (case_id, module),
    CONSTRAINT uq_module_head_stream UNIQUE (artifact_stream_id),
    CONSTRAINT ck_module_head_module CHECK (
        module IN ('compliance','conviction','sentencing')
    ),
    CONSTRAINT ck_module_head_stale_reason CHECK (
        stale_reason IS NULL OR stale_reason IN (
            'facts_changed','dependency_changed','newer_version_published',
            'rule_invalidated','legal_source_invalidated'
        )
    ),
    CONSTRAINT ck_module_head_stale_consistency CHECK (
        stale = true OR stale_reason IS NULL
    ),
    -- ADR-0004：confirmed_version_id 存在且 stale=true 时必须给出原因；
    -- 「从未确认」表达为 confirmed_version_id IS NULL
    CONSTRAINT ck_module_head_never_confirmed CHECK (
        confirmed_version_id IS NULL OR NOT stale OR stale_reason IS NOT NULL
    ),
    CONSTRAINT fk_module_head_stream_same_case
        FOREIGN KEY (artifact_stream_id, case_id)
        REFERENCES app.artifact_stream(artifact_stream_id, case_id),
    CONSTRAINT fk_module_head_confirmed_same_stream
        FOREIGN KEY (artifact_stream_id, confirmed_version_id)
        REFERENCES app.artifact_version(artifact_stream_id, artifact_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE TABLE app.draft_head (
    draft_id            uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES app.cases(id),
    artifact_stream_id  uuid NOT NULL UNIQUE REFERENCES app.artifact_stream(artifact_stream_id),
    approved_version_id uuid NULL,
    stale               boolean NOT NULL DEFAULT true,
    stale_reason        varchar(64) NULL,
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT fk_draft_head_draft FOREIGN KEY (draft_id) REFERENCES app.case_drafts(id),
    CONSTRAINT ck_draft_head_stale_reason CHECK (
        stale_reason IS NULL OR stale_reason IN (
            'dependency_changed','newer_version_published','template_invalidated',
            'facts_changed','module_changed'
        )
    ),
    CONSTRAINT ck_draft_head_stale_consistency CHECK (
        stale = true OR stale_reason IS NULL
    ),
    CONSTRAINT ck_draft_head_never_approved CHECK (
        approved_version_id IS NULL OR NOT stale OR stale_reason IS NOT NULL
    ),
    CONSTRAINT fk_draft_head_stream_same_case
        FOREIGN KEY (artifact_stream_id, case_id)
        REFERENCES app.artifact_stream(artifact_stream_id, case_id),
    CONSTRAINT fk_draft_head_approved_same_stream
        FOREIGN KEY (artifact_stream_id, approved_version_id)
        REFERENCES app.artifact_version(artifact_stream_id, artifact_version_id)
        DEFERRABLE INITIALLY IMMEDIATE
);

CREATE INDEX ix_module_head_case_stale ON app.module_head(case_id, stale);
CREATE INDEX ix_draft_head_case_stale ON app.draft_head(case_id, stale);

-- ---------------------------------------------------------------------------
-- 回填 module_head：status='confirmed' → confirmed_version_id = V15 迁出的 version
-- ---------------------------------------------------------------------------

INSERT INTO app.module_head(case_id, module, artifact_stream_id, confirmed_version_id,
                            stale, stale_reason, updated_at)
SELECT s.case_id, ms.module, s.artifact_stream_id,
       CASE WHEN ms.status = 'confirmed' THEN m.artifact_version_id END,
       CASE WHEN ms.status = 'confirmed' THEN false ELSE true END,
       NULL,
       ms.updated_at
FROM app.case_module_states ms
JOIN app.artifact_stream s
  ON s.case_id = ms.case_id AND s.kind = ms.module AND s.scope_key = 'module:' || ms.module
JOIN app.artifact_backfill_map m
  ON m.source_kind = 'module' AND m.case_id = ms.case_id AND m.module = ms.module;

-- ---------------------------------------------------------------------------
-- 回填 draft_head：approved_version_id 从既有 review 推导一次
-- （INV-DRAFT-HEAD-001：这是最后一次允许推导；此后只能由批准流程推进）
-- ---------------------------------------------------------------------------

INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id, approved_version_id,
                           stale, stale_reason, updated_at)
SELECT d.id, d.case_id, s.artifact_stream_id,
       CASE WHEN EXISTS (
                SELECT 1 FROM app.review_records r
                WHERE r.draft_id = d.id AND r.status = 'approved')
            THEN m.artifact_version_id END,
       CASE WHEN EXISTS (
                SELECT 1 FROM app.review_records r
                WHERE r.draft_id = d.id AND r.status = 'approved')
            THEN false ELSE true END,
       NULL,
       d.updated_at
FROM app.case_drafts d
JOIN app.artifact_stream s
  ON s.case_id = d.case_id AND s.kind = 'draft' AND s.scope_key = 'draft:' || d.id::text
JOIN app.artifact_backfill_map m
  ON m.source_kind = 'draft' AND m.draft_id = d.id;

-- ---------------------------------------------------------------------------
-- 收敛旧表：正文/版本/状态语义全部由 artifact + head 接管
-- ---------------------------------------------------------------------------

ALTER TABLE app.case_module_states DROP COLUMN content_json;
ALTER TABLE app.case_module_states DROP COLUMN status;
ALTER TABLE app.case_module_states DROP COLUMN version;
ALTER TABLE app.case_module_states DROP COLUMN schema_version;
ALTER TABLE app.case_module_states DROP COLUMN facts_updated_at;
ALTER TABLE app.case_module_states DROP COLUMN confirmed_at;
-- 保留 applicability / source_version / updated_by / updated_at 作为展示元数据

ALTER TABLE app.case_drafts DROP COLUMN body;
ALTER TABLE app.case_drafts DROP COLUMN version;
-- 保留 id / case_id / draft_type / template_version / source_version / updated_by / updated_at 作为描述符

ALTER TABLE app.case_facts DROP COLUMN items_json;
ALTER TABLE app.case_facts DROP COLUMN status;
ALTER TABLE app.case_facts DROP COLUMN schema_version;
ALTER TABLE app.case_facts DROP COLUMN confirmed_at;
-- case_facts 仅剩 case_id + updated_at，已无独立语义，直接删除
DROP TABLE app.case_facts;

COMMENT ON TABLE app.case_module_states IS
    'DEPRECATED — 仅余展示元数据；权威指针在 app.module_head，正文在 app.artifact_version。';
COMMENT ON TABLE app.case_drafts IS
    '文书描述符（draft_type/updated_by）；正文在 artifact_version，批准指针在 draft_head。';
