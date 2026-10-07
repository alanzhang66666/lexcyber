-- Collection replacements before V24 could sever evidence/actor links. Inspect
-- frozen snapshots, never the current working copy, and invalidate only heads
-- consuming those broken snapshots (including registered descendants).
-- Immutable facts/artifacts, approval pointers and archive manifests are kept.
DO $$
DECLARE
    invalid_facts uuid[];
BEGIN
    WITH snapshots AS (
        SELECT facts_version_id, case_id, payload FROM app.facts_version
    ), members AS (
        SELECT s.facts_version_id, s.case_id, section.kind, e.item
        FROM snapshots s
        CROSS JOIN LATERAL (VALUES
            ('fact', s.payload -> 'items'),
            ('amount', s.payload #> '{entities,amounts}'),
            ('jurisdiction', s.payload #> '{entities,jurisdictionConnections}'),
            ('event', s.payload #> '{entities,events}')
        ) AS section(kind, items)
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(section.items) = 'array' THEN section.items ELSE '[]'::jsonb END
        ) AS e(item)
    ), identities AS (
        SELECT s.facts_version_id, s.case_id, section.kind, e.ordinality, e.item,
               lower(e.item ->> 'entityId') AS canonical
        FROM snapshots s
        CROSS JOIN LATERAL (VALUES
            ('evidence', s.payload #> '{entities,evidence}'),
            ('actor', s.payload #> '{entities,actors}')
        ) AS section(kind, items)
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(section.items) = 'array' THEN section.items ELSE '[]'::jsonb END
        ) WITH ORDINALITY AS e(item, ordinality)
    ), aliases AS (
        SELECT i.facts_version_id, i.kind, i.ordinality, i.canonical,
               CASE WHEN a.value ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                    THEN lower(a.value) ELSE a.value END AS alias
        FROM identities i
        CROSS JOIN LATERAL (VALUES
            (btrim(i.item ->> 'entityId')), (btrim(i.item ->> 'id')), (btrim(i.item ->> 'externalId'))
        ) AS a(value)
        WHERE a.value IS NOT NULL AND a.value <> ''
    ), refs AS (
        SELECT m.facts_version_id, 'evidence' AS kind, r.value AS raw,
               r.value #>> '{}' AS value
        FROM members m
        CROSS JOIN LATERAL jsonb_array_elements(
            CASE WHEN jsonb_typeof(m.item -> 'evidenceIds') = 'array'
                 THEN m.item -> 'evidenceIds' ELSE '[]'::jsonb END
        ) AS r(value)
        WHERE m.kind IN ('fact', 'amount', 'jurisdiction')
        UNION ALL
        SELECT m.facts_version_id, 'actor', m.item -> 'actorId', m.item ->> 'actorId'
        FROM members m
        WHERE m.kind IN ('fact', 'event') AND m.item ->> 'actorId' IS NOT NULL
          AND btrim(m.item ->> 'actorId') <> ''
    ), invalid AS (
        SELECT s.facts_version_id FROM snapshots s
        CROSS JOIN LATERAL (VALUES
            (s.payload #> '{entities,evidence}'), (s.payload #> '{entities,actors}')
        ) AS section(items)
        WHERE section.items IS NOT NULL AND section.items <> 'null'::jsonb
          AND jsonb_typeof(section.items) <> 'array'
        UNION
        SELECT facts_version_id FROM identities
        WHERE canonical IS NULL OR canonical !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        UNION
        SELECT i.facts_version_id FROM identities i
        WHERE (i.kind = 'evidence' AND EXISTS (
            SELECT 1 FROM app.case_evidence e WHERE e.evidence_id::text = i.canonical AND e.case_id <> i.case_id
        )) OR (i.kind = 'actor' AND EXISTS (
            SELECT 1 FROM app.case_actor a WHERE a.actor_id::text = i.canonical AND a.case_id <> i.case_id
        ))
        UNION
        SELECT facts_version_id FROM aliases
        GROUP BY facts_version_id, kind, alias HAVING count(DISTINCT ordinality) > 1
        UNION
        SELECT facts_version_id FROM members
        WHERE kind IN ('fact', 'amount', 'jurisdiction') AND item ? 'evidenceIds'
          AND item -> 'evidenceIds' <> 'null'::jsonb
          AND jsonb_typeof(item -> 'evidenceIds') <> 'array'
        UNION
        SELECT r.facts_version_id FROM refs r
        WHERE jsonb_typeof(r.raw) <> 'string' OR btrim(r.value) = '' OR NOT EXISTS (
            SELECT 1 FROM aliases a WHERE a.facts_version_id = r.facts_version_id AND a.kind = r.kind
              AND a.alias = CASE WHEN btrim(r.value) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                                 THEN lower(btrim(r.value)) ELSE btrim(r.value) END
        )
    )
    SELECT array_agg(DISTINCT facts_version_id) INTO invalid_facts FROM invalid;

    IF invalid_facts IS NULL THEN RETURN; END IF;

    WITH RECURSIVE affected(artifact_version_id) AS (
        SELECT artifact_version_id FROM app.artifact_facts_dependency
        WHERE facts_version_id = ANY(invalid_facts)
        UNION
        SELECT d.artifact_version_id FROM app.artifact_artifact_dependency d
        JOIN affected a ON a.artifact_version_id = d.depends_on_artifact_version_id
    )
    UPDATE app.module_head SET stale = true, stale_reason = 'dependency_changed', updated_at = now()
    WHERE confirmed_version_id IN (SELECT artifact_version_id FROM affected) AND NOT stale;

    WITH RECURSIVE affected(artifact_version_id) AS (
        SELECT artifact_version_id FROM app.artifact_facts_dependency
        WHERE facts_version_id = ANY(invalid_facts)
        UNION
        SELECT d.artifact_version_id FROM app.artifact_artifact_dependency d
        JOIN affected a ON a.artifact_version_id = d.depends_on_artifact_version_id
    )
    UPDATE app.draft_head SET stale = true, stale_reason = 'dependency_changed', updated_at = now()
    WHERE approved_version_id IN (SELECT artifact_version_id FROM affected) AND NOT stale;
END $$;
