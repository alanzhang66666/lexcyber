-- Older adapters recorded legal divergence while publishing calculated results.
-- Preserve immutable versions and approval pointers; invalidate effective heads
-- and their explicitly registered artifact descendants before reuse.
WITH RECURSIVE invalid(artifact_version_id) AS (
    SELECT artifact_version_id FROM app.artifact_version
    WHERE schema_version IN ('case.compliance.v2', 'case.conviction.v2', 'sentencing.v2')
      AND COALESCE(payload -> 'divergence', '[]'::jsonb) <> '[]'::jsonb
    UNION
    SELECT d.artifact_version_id
    FROM app.artifact_artifact_dependency d
    JOIN invalid i ON i.artifact_version_id = d.depends_on_artifact_version_id
)
UPDATE app.module_head h
SET stale = true, stale_reason = 'rule_invalidated', updated_at = now()
WHERE h.confirmed_version_id IN (SELECT artifact_version_id FROM invalid);

WITH RECURSIVE invalid(artifact_version_id) AS (
    SELECT artifact_version_id FROM app.artifact_version
    WHERE schema_version IN ('case.compliance.v2', 'case.conviction.v2', 'sentencing.v2')
      AND COALESCE(payload -> 'divergence', '[]'::jsonb) <> '[]'::jsonb
    UNION
    SELECT d.artifact_version_id
    FROM app.artifact_artifact_dependency d
    JOIN invalid i ON i.artifact_version_id = d.depends_on_artifact_version_id
)
UPDATE app.draft_head h
SET stale = true, stale_reason = 'dependency_changed', updated_at = now()
WHERE h.approved_version_id IN (SELECT artifact_version_id FROM invalid);
