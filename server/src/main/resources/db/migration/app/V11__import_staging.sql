CREATE UNIQUE INDEX ux_cases_owner_id
  ON app.cases(owner_account_id, id);
CREATE UNIQUE INDEX ux_documents_case_id
  ON app.documents(case_id, id);

CREATE TABLE app.import_batches (
  id UUID PRIMARY KEY,
  owner_account_id UUID NOT NULL REFERENCES app.accounts(id),
  schema_version TEXT,
  package_id TEXT,
  producer_id TEXT,
  dataset_id TEXT,
  revision TEXT,
  package_digest TEXT CHECK (package_digest IS NULL OR package_digest ~ '^[0-9a-f]{64}$'),
  original_filename TEXT NOT NULL,
  content_type TEXT NOT NULL,
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  raw_sha256 TEXT NOT NULL CHECK (raw_sha256 ~ '^[0-9a-f]{64}$'),
  storage_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'uploading' CHECK (status IN (
    'uploading', 'uploaded', 'validating', 'validation_failed', 'diff_ready', 'review_required',
    'approved', 'applying', 'partially_completed', 'completed', 'failed'
  )),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata_json) = 'object'),
  error_json JSONB CHECK (error_json IS NULL OR jsonb_typeof(error_json) = 'object'),
  approved_by UUID REFERENCES app.accounts(id),
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  lease_expires_at TIMESTAMPTZ,
  lease_token UUID,
  CHECK ((approved_by IS NULL) = (approved_at IS NULL)),
  CHECK ((status IN ('uploading', 'uploaded', 'validating', 'review_required', 'approved', 'applying')) = (completed_at IS NULL)),
  CHECK (status <> 'applying' OR lease_expires_at IS NOT NULL),
  CHECK ((status = 'applying') = (lease_token IS NOT NULL)),
  UNIQUE (owner_account_id, id)
);

CREATE UNIQUE INDEX ux_import_batches_release
  ON app.import_batches(owner_account_id, producer_id, package_id, revision)
  WHERE producer_id IS NOT NULL AND package_id IS NOT NULL AND revision IS NOT NULL;
CREATE INDEX ix_import_batches_owner_created
  ON app.import_batches(owner_account_id, created_at DESC);
CREATE INDEX ix_import_batches_owner_status
  ON app.import_batches(owner_account_id, status, updated_at DESC);

CREATE TABLE app.import_items (
  id UUID PRIMARY KEY,
  owner_account_id UUID NOT NULL REFERENCES app.accounts(id),
  batch_id UUID NOT NULL,
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  item_id TEXT NOT NULL CHECK (btrim(item_id) <> ''),
  external_case_id TEXT NOT NULL CHECK (btrim(external_case_id) <> ''),
  payload_path TEXT NOT NULL CHECK (btrim(payload_path) <> ''),
  payload_sha256 TEXT NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending', 'validating', 'invalid', 'diff_ready', 'review_required',
    'approved', 'applying', 'applied', 'no_op', 'conflict', 'failed'
  )),
  case_id TEXT,
  diff_json JSONB CHECK (diff_json IS NULL OR jsonb_typeof(diff_json) = 'object'),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata_json) = 'object'),
  error_json JSONB CHECK (error_json IS NULL OR jsonb_typeof(error_json) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  UNIQUE (batch_id, ordinal),
  UNIQUE (batch_id, item_id),
  UNIQUE (batch_id, external_case_id),
  UNIQUE (batch_id, id),
  FOREIGN KEY (owner_account_id, batch_id) REFERENCES app.import_batches(owner_account_id, id),
  FOREIGN KEY (owner_account_id, case_id) REFERENCES app.cases(owner_account_id, id),
  CHECK (status <> 'applied' OR case_id IS NOT NULL)
);
CREATE INDEX ix_import_items_batch_status
  ON app.import_items(batch_id, status, ordinal);
CREATE INDEX ix_import_items_case
  ON app.import_items(case_id) WHERE case_id IS NOT NULL;

CREATE TABLE app.import_steps (
  id UUID PRIMARY KEY,
  batch_id UUID NOT NULL REFERENCES app.import_batches(id),
  item_id UUID,
  step_key TEXT NOT NULL CHECK (btrim(step_key) <> ''),
  ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
  attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending', 'running', 'completed', 'failed', 'skipped'
  )),
  input_json JSONB CHECK (input_json IS NULL OR jsonb_typeof(input_json) = 'object'),
  output_json JSONB CHECK (output_json IS NULL OR jsonb_typeof(output_json) = 'object'),
  error_json JSONB CHECK (error_json IS NULL OR jsonb_typeof(error_json) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  lease_expires_at TIMESTAMPTZ,
  lease_token UUID,
  FOREIGN KEY (batch_id, item_id) REFERENCES app.import_items(batch_id, id),
  CHECK (finished_at IS NULL OR started_at IS NOT NULL),
  CHECK (status <> 'running' OR lease_expires_at IS NOT NULL),
  CHECK ((status = 'running') = (lease_token IS NOT NULL))
);
CREATE UNIQUE INDEX ux_import_steps_batch_step
  ON app.import_steps(batch_id, step_key) WHERE item_id IS NULL;
CREATE UNIQUE INDEX ux_import_steps_item_step
  ON app.import_steps(item_id, step_key) WHERE item_id IS NOT NULL;
CREATE INDEX ix_import_steps_recoverable
  ON app.import_steps(status, updated_at) WHERE status IN ('pending', 'running');

CREATE TABLE app.external_resource_map (
  id UUID PRIMARY KEY,
  owner_account_id UUID NOT NULL REFERENCES app.accounts(id),
  batch_id UUID NOT NULL,
  item_id UUID NOT NULL,
  producer_id TEXT NOT NULL CHECK (btrim(producer_id) <> ''),
  dataset_id TEXT NOT NULL CHECK (btrim(dataset_id) <> ''),
  external_resource_type TEXT NOT NULL CHECK (btrim(external_resource_type) <> ''),
  external_resource_id TEXT NOT NULL CHECK (btrim(external_resource_id) <> ''),
  internal_resource_type TEXT NOT NULL CHECK (btrim(internal_resource_type) <> ''),
  internal_resource_id TEXT NOT NULL CHECK (btrim(internal_resource_id) <> ''),
  case_id TEXT NOT NULL,
  document_id TEXT,
  first_revision TEXT NOT NULL CHECK (btrim(first_revision) <> ''),
  last_revision TEXT NOT NULL CHECK (btrim(last_revision) <> ''),
  source_sha256 TEXT CHECK (source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'),
  source_version TEXT,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata_json) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (owner_account_id, batch_id) REFERENCES app.import_batches(owner_account_id, id),
  FOREIGN KEY (batch_id, item_id) REFERENCES app.import_items(batch_id, id),
  FOREIGN KEY (owner_account_id, case_id) REFERENCES app.cases(owner_account_id, id),
  FOREIGN KEY (case_id, document_id) REFERENCES app.documents(case_id, id),
  UNIQUE (owner_account_id, producer_id, dataset_id, external_resource_type, external_resource_id),
  CHECK (internal_resource_type <> 'case' OR internal_resource_id = case_id),
  CHECK (internal_resource_type <> 'document' OR (document_id IS NOT NULL AND internal_resource_id = document_id))
);
CREATE INDEX ix_external_resource_map_case
  ON app.external_resource_map(case_id, internal_resource_type);
CREATE INDEX ix_external_resource_map_internal
  ON app.external_resource_map(owner_account_id, internal_resource_type, internal_resource_id);
CREATE INDEX ix_external_resource_map_document
  ON app.external_resource_map(document_id) WHERE document_id IS NOT NULL;
