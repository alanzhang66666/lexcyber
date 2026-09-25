CREATE TABLE app.model_access_config (
  scope TEXT PRIMARY KEY DEFAULT 'global' CHECK (scope = 'global'),
  provider TEXT NOT NULL CHECK (provider IN ('stub', 'openai')),
  model_name TEXT NOT NULL,
  api_base_url TEXT NOT NULL CHECK (api_base_url ~ '^https?://'),
  api_key_ciphertext BYTEA,
  api_key_nonce BYTEA,
  api_key_fingerprint TEXT,
  timeout_seconds NUMERIC NOT NULL CHECK (timeout_seconds > 0),
  updated_by TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((api_key_ciphertext IS NULL) = (api_key_nonce IS NULL))
);
