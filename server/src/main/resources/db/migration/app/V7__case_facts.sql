CREATE TABLE IF NOT EXISTS app.case_facts (
  case_id TEXT PRIMARY KEY REFERENCES app.cases(id),
  schema_version TEXT NOT NULL DEFAULT 'case.facts.v1',
  status TEXT NOT NULL CHECK (status IN ('draft', 'confirmed')),
  items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed_at TIMESTAMPTZ
);
