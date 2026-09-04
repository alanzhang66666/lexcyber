CREATE SCHEMA IF NOT EXISTS cases;

CREATE TABLE IF NOT EXISTS cases.matters (
  id UUID PRIMARY KEY,
  title TEXT NOT NULL,
  jurisdiction TEXT,
  as_of_date DATE,
  status TEXT NOT NULL DEFAULT 'open',
  summary TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases.parties (
  id UUID PRIMARY KEY,
  case_id UUID NOT NULL REFERENCES cases.matters(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  name TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases.facts (
  id UUID PRIMARY KEY,
  case_id UUID NOT NULL REFERENCES cases.matters(id) ON DELETE CASCADE,
  fact_type TEXT NOT NULL,
  value TEXT NOT NULL,
  source JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases.timelines (
  id UUID PRIMARY KEY,
  case_id UUID NOT NULL REFERENCES cases.matters(id) ON DELETE CASCADE,
  event_date TEXT,
  description TEXT NOT NULL,
  source JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
