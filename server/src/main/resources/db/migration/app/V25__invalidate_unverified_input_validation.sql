-- v2 artifacts must retain the engine's proof that every input actually read
-- was verified.  Invalidate effective heads that point at missing or malformed
-- proofs, including registered descendants.  Immutable history is preserved.
WITH RECURSIVE invalid(artifact_version_id) AS (
    SELECT v.artifact_version_id
    FROM app.artifact_version v
    WHERE v.schema_version IN ('case.compliance.v2', 'case.conviction.v2', 'sentencing.v2', 'draft.v2')
      AND (
          jsonb_typeof(v.payload -> 'input_validation') IS DISTINCT FROM 'object'
          OR (v.payload -> 'input_validation' ->> 'schema_version') IS DISTINCT FROM 'case.input-validation.v1'
          OR (v.payload -> 'input_validation' ->> 'status') IS DISTINCT FROM 'verified'
          OR jsonb_typeof(v.payload -> 'input_validation' -> 'checks') IS DISTINCT FROM 'array'
          OR jsonb_typeof(v.payload -> 'input_validation' -> 'blockers') IS DISTINCT FROM 'array'
          OR jsonb_array_length(
                 CASE WHEN jsonb_typeof(v.payload -> 'input_validation' -> 'blockers') = 'array'
                      THEN v.payload -> 'input_validation' -> 'blockers'
                      ELSE '[]'::jsonb END) <> 0
          OR EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                  CASE WHEN jsonb_typeof(v.payload -> 'input_validation' -> 'checks') = 'array'
                       THEN v.payload -> 'input_validation' -> 'checks'
                       ELSE '[]'::jsonb END) check_item
              WHERE jsonb_typeof(check_item) IS DISTINCT FROM 'object'
                 OR check_item ->> 'status' IS DISTINCT FROM 'verified'
          )
      )
    UNION
    SELECT d.artifact_version_id
    FROM app.artifact_artifact_dependency d
    JOIN invalid i ON i.artifact_version_id = d.depends_on_artifact_version_id
)
UPDATE app.module_head h
SET stale = true, stale_reason = 'dependency_changed', updated_at = now()
WHERE h.confirmed_version_id IN (SELECT artifact_version_id FROM invalid)
  AND NOT h.stale;

WITH RECURSIVE invalid(artifact_version_id) AS (
    SELECT v.artifact_version_id
    FROM app.artifact_version v
    WHERE v.schema_version IN ('case.compliance.v2', 'case.conviction.v2', 'sentencing.v2', 'draft.v2')
      AND (
          jsonb_typeof(v.payload -> 'input_validation') IS DISTINCT FROM 'object'
          OR (v.payload -> 'input_validation' ->> 'schema_version') IS DISTINCT FROM 'case.input-validation.v1'
          OR (v.payload -> 'input_validation' ->> 'status') IS DISTINCT FROM 'verified'
          OR jsonb_typeof(v.payload -> 'input_validation' -> 'checks') IS DISTINCT FROM 'array'
          OR jsonb_typeof(v.payload -> 'input_validation' -> 'blockers') IS DISTINCT FROM 'array'
          OR jsonb_array_length(
                 CASE WHEN jsonb_typeof(v.payload -> 'input_validation' -> 'blockers') = 'array'
                      THEN v.payload -> 'input_validation' -> 'blockers'
                      ELSE '[]'::jsonb END) <> 0
          OR EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                  CASE WHEN jsonb_typeof(v.payload -> 'input_validation' -> 'checks') = 'array'
                       THEN v.payload -> 'input_validation' -> 'checks'
                       ELSE '[]'::jsonb END) check_item
              WHERE jsonb_typeof(check_item) IS DISTINCT FROM 'object'
                 OR check_item ->> 'status' IS DISTINCT FROM 'verified'
          )
      )
    UNION
    SELECT d.artifact_version_id
    FROM app.artifact_artifact_dependency d
    JOIN invalid i ON i.artifact_version_id = d.depends_on_artifact_version_id
)
UPDATE app.draft_head h
SET stale = true, stale_reason = 'dependency_changed', updated_at = now()
WHERE h.approved_version_id IN (SELECT artifact_version_id FROM invalid)
  AND NOT h.stale;
