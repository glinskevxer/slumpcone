-- Jobs, the classes of concrete they specify and the mixtures submitted to them.

CREATE TABLE project (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    owner           TEXT,
    specifier       TEXT,
    unit_system     TEXT NOT NULL,
    started_on      TEXT,
    finished_on     TEXT,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE project_class (
    project_code            TEXT NOT NULL REFERENCES project(code) ON DELETE CASCADE,
    code                    TEXT NOT NULL,
    specified_strength_psi  REAL NOT NULL,
    test_age_days           INTEGER NOT NULL,
    exposure                TEXT NOT NULL,
    slump_target_in         REAL,
    slump_minus_in          REAL,
    slump_plus_in           REAL,
    air_target_pct          REAL,
    air_minus_pct           REAL,
    air_plus_pct            REAL,
    max_water_cementitious  REAL,
    min_cementitious_lb     REAL,
    nominal_max_size_mm     REAL,
    description             TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (project_code, code)
);

CREATE TABLE submittal (
    reference               TEXT PRIMARY KEY,
    project_code            TEXT NOT NULL,
    class_code              TEXT NOT NULL,
    mix_code                TEXT NOT NULL,
    mix_revision            INTEGER NOT NULL,
    submitted_on            TEXT NOT NULL,
    basis                   TEXT NOT NULL,
    status                  TEXT NOT NULL,
    required_average_psi    REAL,
    decided_on              TEXT,
    expires_on              TEXT,
    reviewer                TEXT,
    comments                TEXT NOT NULL DEFAULT ''
);

CREATE INDEX submittal_by_project ON submittal (project_code, class_code, status);
CREATE INDEX submittal_by_mix ON submittal (mix_code, mix_revision);
