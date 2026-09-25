-- V6 — 法源/规则/模板注册与会签（v1.3 §6.1-6.4、INV-LEGAL-004..007、INV-RULE-001/002、INV-EXPLAIN-003）
-- 规则层是 Engine 内独立子系统，规则版本与代码版本解耦（INV-RULE-001：规则更新不要求发版）。
-- legal_review_status=approved 是参与产出结论的前置（INV-RULE-002），会签结论落 signoff_record。

-- ---------------------------------------------------------------------------
-- 1. 法源（LegalSource）——版本化条目 + 显式新旧链 + 别名
-- ---------------------------------------------------------------------------

CREATE TABLE engine.legal_source (
    source_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_key       text NOT NULL,               -- 稳定键：criminal_law.art287_2 / fashi-2025-13.art6 ...
    title            text NOT NULL,
    document_number  text,                        -- 文号：法释〔2019〕15号 / 主席令第…号
    article          text,                        -- 条款项定位：第二百八十七条之二第一款
    jurisdiction     text NOT NULL DEFAULT 'CN',  -- CN | CN-HK | …（国家/地区级；地方细则用 coverage）
    authority        varchar(32) NOT NULL,        -- constitution|law|judicial_interpretation|department_rule|local_rule|guiding_case|policy
    source_version   text NOT NULL,               -- 版本标识（修订年份/文号/内部版次）
    effective_from   date NOT NULL,
    effective_to     date,                        -- NULL=现行；失效/被替代时填
    repeal_date      date,                        -- 明令废止日（可选，区别于效力区间终点）
    official_url     text,
    excerpt          text,                        -- 关键原文摘录（非全文）
    content_hash     text NOT NULL,               -- canonical 内容 sha256（INV-EXPLAIN 可追溯）
    provenance       text,                        -- 采集来源/录入人/出处说明
    verification_level varchar(32) NOT NULL DEFAULT 'pending',
    coverage         jsonb NOT NULL DEFAULT '{}'::jsonb,  -- INV-LEGAL-007 覆盖边界声明
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_legal_source_key_version UNIQUE (source_key, source_version),
    CONSTRAINT ck_legal_source_authority CHECK (authority IN (
        'constitution','law','judicial_interpretation','department_rule',
        'local_rule','guiding_case','policy')),
    CONSTRAINT ck_legal_source_verification CHECK (verification_level IN (
        'pending','verified','signed_off','disputed','unsupported')),
    CONSTRAINT ck_legal_source_effective CHECK (effective_to IS NULL OR effective_to >= effective_from)
);
CREATE INDEX ix_legal_source_key ON engine.legal_source(source_key);
CREATE INDEX ix_legal_source_effective ON engine.legal_source(effective_from, effective_to);

-- 新旧/替代显式建链（INV-LEGAL-005：是数据不是注释）
CREATE TABLE engine.legal_source_supersession (
    predecessor_id uuid NOT NULL REFERENCES engine.legal_source(source_id),
    successor_id   uuid NOT NULL REFERENCES engine.legal_source(source_id),
    relation_type  varchar(32) NOT NULL DEFAULT 'replaces',
    note           text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (predecessor_id, successor_id),
    CONSTRAINT ck_supersession_no_self CHECK (predecessor_id <> successor_id),
    CONSTRAINT ck_supersession_type CHECK (relation_type IN ('replaces','amends','repeals','partially_replaces'))
);

CREATE TABLE engine.legal_source_alias (
    source_id uuid NOT NULL REFERENCES engine.legal_source(source_id),
    alias     text NOT NULL,                      -- 别名/俗名/缩写（检索第一层召回）
    PRIMARY KEY (source_id, alias)
);
CREATE INDEX ix_legal_source_alias ON engine.legal_source_alias(alias);

-- ---------------------------------------------------------------------------
-- 2. 规则包（RulePackage）——数据驱动，版本冻结，approved 才可产出
-- ---------------------------------------------------------------------------

CREATE TABLE engine.rule_package (
    rule_package_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id          text NOT NULL,               -- 稳定键：conviction.bangxin.objective
    rule_version     text NOT NULL,
    family           varchar(32) NOT NULL,        -- compliance|conviction|distinction|sentencing
    legal_review_status varchar(32) NOT NULL DEFAULT 'pending',
    effective_from   date,
    effective_to     date,
    source_ids       jsonb NOT NULL DEFAULT '[]'::jsonb,   -- → engine.legal_source.source_id 数组
    predicate        jsonb NOT NULL,              -- 结构化条件（由 P6 引擎 DSL 解释）
    outcome          jsonb NOT NULL,              -- finding 模板（element/flag/blocker，非结论）
    required_evidence_kinds jsonb NOT NULL DEFAULT '[]'::jsonb,
    coverage         jsonb NOT NULL DEFAULT '{}'::jsonb,   -- 适用边界（罪名集/地域/时间）
    content_hash     text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_rule_package_version UNIQUE (rule_id, rule_version),
    CONSTRAINT ck_rule_family CHECK (family IN ('compliance','conviction','distinction','sentencing')),
    CONSTRAINT ck_rule_review CHECK (legal_review_status IN ('pending','approved','rejected','superseded')),
    CONSTRAINT ck_rule_source_ids CHECK (jsonb_typeof(source_ids) = 'array')
);
CREATE INDEX ix_rule_package_family ON engine.rule_package(family, legal_review_status);

-- ---------------------------------------------------------------------------
-- 3. 模板包（文书字段字典 + 正文模板；approved 才可用于正式导出）
-- ---------------------------------------------------------------------------

CREATE TABLE engine.template_package (
    template_id      text NOT NULL,               -- prosecution_draft / sentencing_recommendation / ...
    template_version text NOT NULL,
    doc_type         varchar(64) NOT NULL,
    legal_review_status varchar(32) NOT NULL DEFAULT 'pending',
    field_schema     jsonb NOT NULL DEFAULT '{}'::jsonb,  -- 字段字典（占位符 → 来源工件路径）
    body_template    text NOT NULL,
    content_hash     text NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (template_id, template_version),
    CONSTRAINT ck_template_review CHECK (legal_review_status IN ('pending','approved','rejected','superseded'))
);

-- ---------------------------------------------------------------------------
-- 4. 会签记录（subject 指向具体版本；批准性会签是 legal_review_status 的证据）
-- ---------------------------------------------------------------------------

CREATE TABLE engine.signoff_record (
    signoff_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_kind varchar(32) NOT NULL,            -- rule | legal_source | template
    subject_key  text NOT NULL,                   -- rule_id@rule_version | source_key@source_version | template_id@version
    reviewer     text NOT NULL,                   -- 会签人标识（账号/姓名）
    role         varchar(64) NOT NULL,            -- legal_reviewer | domain_owner | engineering
    decision     varchar(16) NOT NULL,            -- approved | rejected
    comment      text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_signoff_subject CHECK (subject_kind IN ('rule','legal_source','template')),
    CONSTRAINT ck_signoff_decision CHECK (decision IN ('approved','rejected'))
);
CREATE INDEX ix_signoff_subject ON engine.signoff_record(subject_kind, subject_key);

-- ---------------------------------------------------------------------------
-- 5. 不可变保护：approved/signed_off 行内容字段冻结；
--    仅允许 legal_review_status/verification_level 单向迁到 superseded（新版本替代）。
--    批准路径在应用层 signoff()：同事务写 signoff_record + 推进状态。
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION engine.guard_rule_package() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.legal_review_status IN ('approved','superseded') THEN
            RAISE EXCEPTION 'approved/superseded rule packages cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.legal_review_status IN ('approved','superseded') THEN
        IF NOT (OLD.legal_review_status = 'approved' AND NEW.legal_review_status = 'superseded'
                AND NEW.rule_id = OLD.rule_id AND NEW.rule_version = OLD.rule_version
                AND NEW.family = OLD.family AND NEW.predicate = OLD.predicate
                AND NEW.outcome = OLD.outcome AND NEW.source_ids = OLD.source_ids
                AND NEW.effective_from IS NOT DISTINCT FROM OLD.effective_from
                AND NEW.effective_to IS NOT DISTINCT FROM OLD.effective_to
                AND NEW.required_evidence_kinds = OLD.required_evidence_kinds
                AND NEW.coverage = OLD.coverage AND NEW.content_hash = OLD.content_hash) THEN
            RAISE EXCEPTION 'approved rule package content is immutable; only supersede transition allowed';
        END IF;
    ELSIF NEW.legal_review_status IN ('approved','rejected') THEN
        -- pending→approved/rejected 都是评审结论，只能走 signoff()（同事务有 signoff_record + GUC）
        IF current_setting('engine.signoff_authorized', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'rule review transitions require signoff path (engine.signoff_authorized)';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION engine.guard_template_package() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.legal_review_status IN ('approved','superseded') THEN
            RAISE EXCEPTION 'approved/superseded templates cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.legal_review_status IN ('approved','superseded') THEN
        IF NOT (OLD.legal_review_status = 'approved' AND NEW.legal_review_status = 'superseded'
                AND NEW.template_id = OLD.template_id AND NEW.template_version = OLD.template_version
                AND NEW.doc_type = OLD.doc_type AND NEW.field_schema = OLD.field_schema
                AND NEW.body_template = OLD.body_template AND NEW.content_hash = OLD.content_hash) THEN
            RAISE EXCEPTION 'approved template content is immutable; only supersede transition allowed';
        END IF;
    ELSIF NEW.legal_review_status IN ('approved','rejected') THEN
        IF current_setting('engine.signoff_authorized', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'template review transitions require signoff path';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION engine.guard_legal_source() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.verification_level IN ('signed_off','disputed') THEN
            RAISE EXCEPTION 'signed_off/disputed legal sources cannot be deleted';
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.verification_level = 'signed_off' THEN
        -- signed_off 内容冻结；只允许 verification_level 迁到 disputed/unsupported（复核降级）
        IF NOT (NEW.verification_level IN ('disputed','unsupported')
                AND NEW.source_key = OLD.source_key AND NEW.source_version = OLD.source_version
                AND NEW.title = OLD.title AND NEW.article IS NOT DISTINCT FROM OLD.article
                AND NEW.document_number IS NOT DISTINCT FROM OLD.document_number
                AND NEW.authority = OLD.authority
                AND NEW.effective_from = OLD.effective_from
                AND NEW.effective_to IS NOT DISTINCT FROM OLD.effective_to
                AND NEW.content_hash = OLD.content_hash) THEN
            RAISE EXCEPTION 'signed_off legal source content is immutable; only downgrade allowed';
        END IF;
        IF current_setting('engine.signoff_authorized', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'legal source downgrade requires signoff path';
        END IF;
    ELSIF NEW.verification_level IN ('signed_off','disputed','unsupported') THEN
        IF current_setting('engine.signoff_authorized', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'legal source review transitions require signoff path';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_rule_package_guard BEFORE UPDATE OR DELETE ON engine.rule_package
    FOR EACH ROW EXECUTE FUNCTION engine.guard_rule_package();
CREATE TRIGGER trg_template_guard BEFORE UPDATE OR DELETE ON engine.template_package
    FOR EACH ROW EXECUTE FUNCTION engine.guard_template_package();
CREATE TRIGGER trg_legal_source_guard BEFORE UPDATE OR DELETE ON engine.legal_source
    FOR EACH ROW EXECUTE FUNCTION engine.guard_legal_source();
