-- Durable event receipt for the Engine registry invalidation stream.
-- Payload is intentionally absent: the event itself is authoritative only
-- while the application transaction applies the normalized dependency set.
CREATE TABLE app.registry_invalidation_applied (
    event_id uuid PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

-- Transaction start time can precede a queued registry withdrawal. New
-- artifacts must use insertion time so delayed events cannot invalidate
-- fresh results created after the exact immutable dependency is restored.
ALTER TABLE app.artifact_version ALTER COLUMN created_at SET DEFAULT clock_timestamp();
