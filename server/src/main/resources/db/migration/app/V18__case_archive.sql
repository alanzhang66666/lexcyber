-- V18 — CaseArchive / CaseArchiveItem（v1.3 §4.6.11）+ 同案归档版本计数器（ADR-0006）
-- insert-only；不使用 ON DELETE CASCADE。

ALTER TABLE app.cases ADD COLUMN next_archive_version integer NOT NULL DEFAULT 1
    CHECK (next_archive_version > 0);

CREATE TABLE app.case_archive (
    archive_id       uuid PRIMARY KEY,
    case_id          uuid NOT NULL REFERENCES app.cases(id),
    archive_version  integer NOT NULL CHECK (archive_version > 0),
    archive_profile  varchar(128) NOT NULL,
    facts_version_id uuid NOT NULL REFERENCES app.facts_version(facts_version_id),
    manifest_hash    text NOT NULL,
    created_by       uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT uq_case_archive_version UNIQUE (case_id, archive_version),
    CONSTRAINT uq_case_archive_manifest UNIQUE (case_id, manifest_hash),
    CONSTRAINT fk_case_archive_facts_same_case
        FOREIGN KEY (case_id, facts_version_id)
        REFERENCES app.facts_version(case_id, facts_version_id)
);

CREATE TABLE app.case_archive_item (
    archive_id          uuid NOT NULL REFERENCES app.case_archive(archive_id),
    artifact_version_id uuid NOT NULL REFERENCES app.artifact_version(artifact_version_id),
    role                varchar(32) NOT NULL,
    PRIMARY KEY (archive_id, artifact_version_id, role),
    CONSTRAINT ck_archive_item_role CHECK (
        role IN ('parse','compliance','conviction','sentencing','draft','supporting')
    )
);

CREATE INDEX ix_archive_case_created ON app.case_archive(case_id, archive_version DESC);
CREATE INDEX ix_archive_item_version ON app.case_archive_item(artifact_version_id);
