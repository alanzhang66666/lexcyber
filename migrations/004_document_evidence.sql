CREATE SCHEMA IF NOT EXISTS documents;
CREATE SCHEMA IF NOT EXISTS evidence;
CREATE SCHEMA IF NOT EXISTS legal_source;

CREATE TABLE IF NOT EXISTS documents.files (
  id UUID PRIMARY KEY,
  case_id UUID,
  filename TEXT NOT NULL,
  content_type TEXT,
  storage_key TEXT,
  sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'uploaded',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents.versions (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents.files(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  storage_key TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents.pages (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents.files(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  text TEXT NOT NULL DEFAULT '',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS documents.fragments (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES documents.files(id) ON DELETE CASCADE,
  page_number INTEGER,
  paragraph INTEGER,
  text TEXT NOT NULL,
  start_offset INTEGER,
  end_offset INTEGER
);

CREATE TABLE IF NOT EXISTS evidence.items (
  id UUID PRIMARY KEY,
  case_id UUID,
  evidence_id TEXT NOT NULL,
  name TEXT NOT NULL,
  sha256 TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS evidence.relations (
  id UUID PRIMARY KEY,
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  relation_type TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS evidence.hashes (
  evidence_pk UUID NOT NULL REFERENCES evidence.items(id) ON DELETE CASCADE,
  sha256 TEXT NOT NULL,
  algorithm TEXT NOT NULL DEFAULT 'sha256',
  PRIMARY KEY (evidence_pk, algorithm)
);

CREATE TABLE IF NOT EXISTS evidence.custody_events (
  id BIGSERIAL PRIMARY KEY,
  evidence_pk UUID NOT NULL REFERENCES evidence.items(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  actor TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS legal_source.sources (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  jurisdiction TEXT,
  source_authority TEXT,
  source_url TEXT
);

CREATE TABLE IF NOT EXISTS legal_source.versions (
  source_id TEXT NOT NULL REFERENCES legal_source.sources(id) ON DELETE CASCADE,
  source_version TEXT NOT NULL,
  effective_from DATE,
  effective_to DATE,
  PRIMARY KEY (source_id, source_version)
);

CREATE TABLE IF NOT EXISTS legal_source.articles (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES legal_source.sources(id) ON DELETE CASCADE,
  article_number TEXT,
  content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legal_source.citations (
  id UUID PRIMARY KEY,
  source_id TEXT,
  article TEXT,
  quote TEXT,
  document_id UUID,
  page INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
