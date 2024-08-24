-- Ingest runs, the content hashes they accepted and the rows they refused.

CREATE TABLE ingest_run (
    id                  INTEGER PRIMARY KEY,
    profile_code        TEXT NOT NULL,
    source_name         TEXT NOT NULL,
    run_at              TEXT NOT NULL,
    accepted_count      INTEGER NOT NULL,
    quarantined_count   INTEGER NOT NULL,
    duplicate_count     INTEGER NOT NULL,
    unmapped_columns    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX ingest_run_by_profile ON ingest_run (profile_code, run_at);

CREATE TABLE ingest_digest (
    digest          TEXT NOT NULL,
    profile_code    TEXT NOT NULL,
    run_id          INTEGER NOT NULL REFERENCES ingest_run(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    PRIMARY KEY (profile_code, digest)
);

CREATE INDEX ingest_digest_by_run ON ingest_digest (run_id);

CREATE TABLE ingest_quarantine (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES ingest_run(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    reasons         TEXT NOT NULL,
    values_json     TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX ingest_quarantine_by_run ON ingest_quarantine (run_id, line_number);
