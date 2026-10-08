-- Registry writer barrier and durable dependency invalidation events.
CREATE TABLE engine.registry_invalidation_event (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dependencies jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    acknowledged_at timestamptz
);

CREATE OR REPLACE FUNCTION engine.registry_barrier_stmt() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(5495895966559126866);
    RETURN NULL;
END $$;

-- Identity is read from owner rows, never reconstructed by splitting '@'.
CREATE FUNCTION engine.registry_source_dependencies(source_uuid uuid, version text) RETURNS jsonb
LANGUAGE sql STABLE AS $$
    SELECT jsonb_build_array(jsonb_build_object(
               'kind','legal_source','key',source_uuid::text,'version',version))
           || COALESCE(jsonb_agg(jsonb_build_object(
               'kind','rule','key',r.rule_id,'version',r.rule_version)), '[]'::jsonb)
    FROM engine.rule_package r
    WHERE EXISTS (SELECT 1 FROM jsonb_array_elements_text(r.source_ids) ref
                  WHERE lower(ref) = lower(source_uuid::text))
$$;

CREATE OR REPLACE FUNCTION engine.registry_record_invalidation() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    payload jsonb := '[]'::jsonb;
    source_row record;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD IS NOT DISTINCT FROM NEW THEN RETURN NULL; END IF;
    END IF;
    -- Separate branches before accessing table-specific record fields.
    IF TG_TABLE_NAME = 'rule_package' THEN
        IF OLD.legal_review_status = 'approved' THEN
            payload := jsonb_build_array(jsonb_build_object(
                'kind','rule','key',OLD.rule_id,'version',OLD.rule_version));
        END IF;
    ELSIF TG_TABLE_NAME = 'template_package' THEN
        IF OLD.legal_review_status = 'approved' THEN
            payload := jsonb_build_array(jsonb_build_object(
                'kind','template','key',OLD.template_id,'version',OLD.template_version));
        END IF;
    ELSIF TG_TABLE_NAME = 'legal_source' THEN
        IF OLD.verification_level = 'signed_off' THEN
            payload := engine.registry_source_dependencies(OLD.source_id, OLD.source_version);
        END IF;
    ELSIF TG_TABLE_NAME = 'signoff_record' THEN
        IF OLD.decision <> 'approved' THEN RETURN NULL; END IF;
        IF OLD.subject_kind = 'legal_source' THEN
            FOR source_row IN
                SELECT s.source_id, s.source_version FROM engine.legal_source s
                WHERE s.source_key || '@' || s.source_version = OLD.subject_key
                  AND NOT EXISTS (SELECT 1 FROM engine.effective_legal_source e
                                  WHERE e.source_id = s.source_id)
            LOOP
                payload := payload || engine.registry_source_dependencies(
                    source_row.source_id, source_row.source_version);
            END LOOP;
        ELSIF OLD.subject_kind = 'rule' THEN
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                       'kind','rule','key',r.rule_id,'version',r.rule_version)), '[]'::jsonb)
              INTO payload FROM engine.rule_package r
             WHERE r.rule_id || '@' || r.rule_version = OLD.subject_key
               AND NOT EXISTS (SELECT 1 FROM engine.effective_rule_package e
                               WHERE e.rule_package_id = r.rule_package_id);
        ELSIF OLD.subject_kind = 'template' THEN
            SELECT COALESCE(jsonb_agg(jsonb_build_object(
                       'kind','template','key',t.template_id,'version',t.template_version)), '[]'::jsonb)
              INTO payload FROM engine.template_package t
             WHERE t.template_id || '@' || t.template_version = OLD.subject_key
               AND NOT EXISTS (SELECT 1 FROM engine.effective_template_package e
                               WHERE e.template_id = t.template_id AND e.template_version = t.template_version);
        END IF;
    END IF;
    IF jsonb_array_length(payload) > 0 THEN
        INSERT INTO engine.registry_invalidation_event(dependencies) VALUES (payload);
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER trg_registry_barrier_rule BEFORE UPDATE OR DELETE ON engine.rule_package
FOR EACH STATEMENT EXECUTE FUNCTION engine.registry_barrier_stmt();
CREATE TRIGGER trg_registry_barrier_template BEFORE UPDATE OR DELETE ON engine.template_package
FOR EACH STATEMENT EXECUTE FUNCTION engine.registry_barrier_stmt();
CREATE TRIGGER trg_registry_barrier_source BEFORE UPDATE OR DELETE ON engine.legal_source
FOR EACH STATEMENT EXECUTE FUNCTION engine.registry_barrier_stmt();
CREATE TRIGGER trg_registry_barrier_signoff BEFORE INSERT OR UPDATE OR DELETE ON engine.signoff_record
FOR EACH STATEMENT EXECUTE FUNCTION engine.registry_barrier_stmt();
CREATE TRIGGER trg_registry_event_rule AFTER UPDATE OR DELETE ON engine.rule_package
FOR EACH ROW EXECUTE FUNCTION engine.registry_record_invalidation();
CREATE TRIGGER trg_registry_event_template AFTER UPDATE OR DELETE ON engine.template_package
FOR EACH ROW EXECUTE FUNCTION engine.registry_record_invalidation();
CREATE TRIGGER trg_registry_event_source AFTER UPDATE OR DELETE ON engine.legal_source
FOR EACH ROW EXECUTE FUNCTION engine.registry_record_invalidation();
CREATE TRIGGER trg_registry_event_signoff AFTER UPDATE OR DELETE ON engine.signoff_record
FOR EACH ROW EXECUTE FUNCTION engine.registry_record_invalidation();

CREATE OR REPLACE FUNCTION engine.guard_reviewed_source_v8() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND OLD.verification_level IN ('signed_off','disputed','unsupported') THEN
        RAISE EXCEPTION 'reviewed legal source cannot be deleted';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.verification_level IN ('signed_off','disputed','unsupported') THEN
        IF (to_jsonb(OLD) - ARRAY['verification_level','updated_at']) IS DISTINCT FROM (to_jsonb(NEW) - ARRAY['verification_level','updated_at'])
           OR NEW.verification_level NOT IN ('signed_off','disputed','unsupported') THEN
            RAISE EXCEPTION 'reviewed legal source content is immutable; create a new version';
        END IF;
        IF NEW.verification_level IS DISTINCT FROM OLD.verification_level
           AND current_setting('engine.signoff_authorized', true) IS DISTINCT FROM 'on' THEN
            RAISE EXCEPTION 'legal source review transition requires signoff path';
        END IF;
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER trg_reviewed_source_guard_v8 BEFORE UPDATE OR DELETE ON engine.legal_source
FOR EACH ROW EXECUTE FUNCTION engine.guard_reviewed_source_v8();

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lex_engine') THEN
        GRANT SELECT, INSERT, UPDATE ON engine.registry_invalidation_event TO lex_engine;
    END IF;
END $$;
