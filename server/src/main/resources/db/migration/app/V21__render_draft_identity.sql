-- Rendered drafts have a stable UUID descriptor; manual /v1 drafts remain independent.
ALTER TABLE app.case_drafts ADD COLUMN render_doc_type text;
CREATE UNIQUE INDEX uq_render_draft_case_type
    ON app.case_drafts(case_id, render_doc_type) WHERE render_doc_type IS NOT NULL;

-- Preserve old stream IDs and all immutable versions while repairing the missing heads.
DO $$
DECLARE
    stream_row record;
    descriptor_id uuid;
BEGIN
    FOR stream_row IN
        SELECT s.artifact_stream_id, s.case_id, substring(s.scope_key from 7) AS doc_type,
               c.owner_account_id
        FROM app.artifact_stream s JOIN app.cases c ON c.id = s.case_id
        WHERE s.kind = 'draft' AND s.scope_key LIKE 'draft:%'
          AND NOT EXISTS (SELECT 1 FROM app.draft_head h
                          WHERE h.artifact_stream_id = s.artifact_stream_id)
          AND substring(s.scope_key from 7) !~*
              '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    LOOP
        descriptor_id := gen_random_uuid();
        INSERT INTO app.case_drafts(id, case_id, draft_type, render_doc_type, updated_by)
        VALUES (descriptor_id, stream_row.case_id, stream_row.doc_type,
                stream_row.doc_type, stream_row.owner_account_id);
        UPDATE app.artifact_stream SET scope_key = 'draft:' || descriptor_id::text
        WHERE artifact_stream_id = stream_row.artifact_stream_id;
        INSERT INTO app.draft_head(draft_id, case_id, artifact_stream_id)
        VALUES (descriptor_id, stream_row.case_id, stream_row.artifact_stream_id);
        -- Old render jobs did not freeze input version IDs. Regeneration is required;
        -- retain their versions/history, but do not approve an unverifiable dependency snapshot.
        UPDATE app.review_records SET status = 'superseded', decided_at = now()
        WHERE status = 'pending' AND artifact_version_id IN (
            SELECT artifact_version_id FROM app.artifact_version
            WHERE artifact_stream_id = stream_row.artifact_stream_id);
    END LOOP;
END $$;
