-- Specimen sets, the cylinders in them and the breaks that came off those.

CREATE TABLE specimen_set (
    set_code        TEXT PRIMARY KEY,
    mix_code        TEXT NOT NULL,
    mix_revision    INTEGER NOT NULL,
    ticket_number   TEXT,
    project         TEXT,
    size            TEXT NOT NULL,
    cure            TEXT NOT NULL,
    purpose         TEXT NOT NULL,
    sampled_at      TEXT NOT NULL,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX specimen_set_by_mix ON specimen_set (mix_code, sampled_at);
CREATE INDEX specimen_set_by_project ON specimen_set (project, sampled_at);

CREATE TABLE specimen (
    code            TEXT PRIMARY KEY,
    set_code        TEXT NOT NULL REFERENCES specimen_set(set_code) ON DELETE CASCADE,
    ticket_number   TEXT NOT NULL,
    cast_at         TEXT NOT NULL,
    size            TEXT NOT NULL,
    cure            TEXT NOT NULL,
    purpose         TEXT NOT NULL,
    age_days        INTEGER NOT NULL,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX specimen_by_set ON specimen (set_code, code);
CREATE INDEX specimen_by_ticket ON specimen (ticket_number);

CREATE TABLE break_result (
    specimen_code   TEXT PRIMARY KEY REFERENCES specimen(code) ON DELETE CASCADE,
    tested_at       TEXT NOT NULL,
    age_days        REAL NOT NULL,
    diameter_one_in REAL NOT NULL,
    diameter_two_in REAL NOT NULL,
    length_in       REAL NOT NULL,
    max_load_lbf    REAL NOT NULL,
    fracture        TEXT NOT NULL,
    tested_by       TEXT,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX break_by_date ON break_result (tested_at);
