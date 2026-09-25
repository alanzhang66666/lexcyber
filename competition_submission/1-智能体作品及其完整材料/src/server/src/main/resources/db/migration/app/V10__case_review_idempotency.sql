CREATE TABLE app.case_create_idempotency (
  account_id UUID NOT NULL REFERENCES app.accounts(id),
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  case_id TEXT REFERENCES app.cases(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, idempotency_key)
);

CREATE TABLE app.review_open_idempotency (
  account_id UUID NOT NULL REFERENCES app.accounts(id),
  case_id TEXT NOT NULL REFERENCES app.cases(id),
  idempotency_key TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  review_id UUID REFERENCES app.review_records(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (account_id, case_id, idempotency_key)
);

CREATE INDEX ix_case_create_idempotency_case
  ON app.case_create_idempotency(case_id);

CREATE INDEX ix_review_open_idempotency_review
  ON app.review_open_idempotency(review_id);
