CREATE SCHEMA IF NOT EXISTS review;

CREATE TABLE IF NOT EXISTS review.requests (
  id UUID PRIMARY KEY,
  case_id TEXT,
  task_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  risk_level TEXT,
  reason TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS review.decisions (
  id UUID PRIMARY KEY,
  review_id UUID NOT NULL REFERENCES review.requests(id) ON DELETE CASCADE,
  decision TEXT NOT NULL,
  actor TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS review.comments (
  id UUID PRIMARY KEY,
  review_id UUID NOT NULL REFERENCES review.requests(id) ON DELETE CASCADE,
  actor TEXT,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
