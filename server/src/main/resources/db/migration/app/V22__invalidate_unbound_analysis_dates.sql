-- Old v2 outputs did not bind the rule-selection date. Preserve immutable
-- history and approval pointers, but require regeneration before effective use.
UPDATE app.module_head h SET stale = true, stale_reason = 'analysis_date_unbound', updated_at = now()
FROM app.artifact_version v, app.cases c
WHERE h.confirmed_version_id = v.artifact_version_id AND h.case_id = c.id
  AND v.schema_version IN ('case.compliance.v2', 'case.conviction.v2', 'sentencing.v2')
  AND (c.as_of_date IS NULL OR v.dependency_snapshot ->> 'as_of_date'
       IS DISTINCT FROM to_char(c.as_of_date, 'YYYY-MM-DD'));

UPDATE app.draft_head h SET stale = true, stale_reason = 'analysis_date_unbound', updated_at = now()
FROM app.artifact_version v, app.cases c
WHERE h.approved_version_id = v.artifact_version_id AND h.case_id = c.id
  AND v.schema_version = 'draft.v2'
  AND (c.as_of_date IS NULL OR v.dependency_snapshot ->> 'as_of_date'
       IS DISTINCT FROM to_char(c.as_of_date, 'YYYY-MM-DD'));
