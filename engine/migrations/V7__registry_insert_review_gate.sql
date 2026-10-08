-- V7 — registry insert review gate and effective reviewed projections.
-- Existing V6 UPDATE/DELETE guards remain authoritative for rows after insert.

CREATE OR REPLACE FUNCTION engine.guard_rule_package_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.legal_review_status <> 'pending' THEN
        RAISE EXCEPTION 'rule packages must be inserted pending; use signoff() for review';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION engine.guard_template_package_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.legal_review_status <> 'pending' THEN
        RAISE EXCEPTION 'templates must be inserted pending; use signoff() for review';
    END IF;
    RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION engine.guard_legal_source_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.verification_level NOT IN ('pending', 'verified') THEN
        RAISE EXCEPTION 'legal sources must be inserted pending or verified; use signoff() for review';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_rule_package_insert_review_gate
    BEFORE INSERT ON engine.rule_package
    FOR EACH ROW EXECUTE FUNCTION engine.guard_rule_package_insert();
CREATE TRIGGER trg_template_insert_review_gate
    BEFORE INSERT ON engine.template_package
    FOR EACH ROW EXECUTE FUNCTION engine.guard_template_package_insert();
CREATE TRIGGER trg_legal_source_insert_review_gate
    BEFORE INSERT ON engine.legal_source
    FOR EACH ROW EXECUTE FUNCTION engine.guard_legal_source_insert();

-- These projections make the review evidence part of every production read while
-- retaining the append-only base tables and their complete history.
CREATE OR REPLACE VIEW engine.effective_legal_source AS
SELECT source.*
FROM engine.legal_source AS source
WHERE source.verification_level = 'signed_off'
  AND EXISTS (
      SELECT 1
      FROM engine.signoff_record AS signoff
      WHERE signoff.subject_kind = 'legal_source'
        AND signoff.subject_key = source.source_key || '@' || source.source_version
        AND signoff.decision = 'approved'
  );

CREATE OR REPLACE VIEW engine.effective_template_package AS
SELECT template.*
FROM engine.template_package AS template
WHERE template.legal_review_status = 'approved'
  AND EXISTS (
      SELECT 1
      FROM engine.signoff_record AS signoff
      WHERE signoff.subject_kind = 'template'
        AND signoff.subject_key = template.template_id || '@' || template.template_version
        AND signoff.decision = 'approved'
  );

CREATE OR REPLACE VIEW engine.effective_rule_package AS
SELECT rule.*
FROM engine.rule_package AS rule
WHERE rule.legal_review_status = 'approved'
  AND EXISTS (
      SELECT 1
      FROM engine.signoff_record AS signoff
      WHERE signoff.subject_kind = 'rule'
        AND signoff.subject_key = rule.rule_id || '@' || rule.rule_version
        AND signoff.decision = 'approved'
  )
  AND NOT EXISTS (
      SELECT 1
      FROM jsonb_array_elements_text(rule.source_ids) AS referenced(source_id)
      WHERE referenced.source_id !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
         OR NOT EXISTS (
             SELECT 1
             FROM engine.effective_legal_source AS source
             WHERE lower(source.source_id::text) = lower(referenced.source_id)
         )
  );
