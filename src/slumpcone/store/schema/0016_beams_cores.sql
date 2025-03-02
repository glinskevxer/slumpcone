-- Flexural beams and the cores taken when a strength test comes out low.

CREATE TABLE flexural_break (
    specimen_code           TEXT PRIMARY KEY,
    set_code                TEXT NOT NULL,
    mix_code                TEXT NOT NULL,
    tested_at               TEXT NOT NULL,
    age_days                REAL NOT NULL,
    span_in                 REAL NOT NULL,
    width_in                REAL NOT NULL,
    depth_in                REAL NOT NULL,
    max_load_lbf            REAL NOT NULL,
    fracture_from_support_in REAL NOT NULL,
    notes                   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX beam_by_set ON flexural_break (set_code, specimen_code);
CREATE INDEX beam_by_mix ON flexural_break (mix_code, tested_at);

CREATE TABLE concrete_core (
    code                TEXT PRIMARY KEY,
    location            TEXT NOT NULL,
    specified_psi       REAL NOT NULL,
    taken_at            TEXT NOT NULL,
    diameter_in         REAL NOT NULL,
    length_in           REAL NOT NULL,
    max_load_lbf        REAL NOT NULL,
    condition           TEXT NOT NULL,
    has_reinforcement   INTEGER NOT NULL DEFAULT 0,
    notes               TEXT NOT NULL DEFAULT ''
);

CREATE INDEX core_by_location ON concrete_core (location, taken_at);
