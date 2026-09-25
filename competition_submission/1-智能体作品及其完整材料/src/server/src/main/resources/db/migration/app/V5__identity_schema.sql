CREATE TABLE IF NOT EXISTS app.accounts (
  id UUID PRIMARY KEY,
  username TEXT NOT NULL,
  username_normalized TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.auth_sessions (
  id UUID PRIMARY KEY,
  account_id UUID NOT NULL REFERENCES app.accounts(id),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_account ON app.auth_sessions(account_id);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires ON app.auth_sessions(expires_at);
