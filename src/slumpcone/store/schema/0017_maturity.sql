-- Strength maturity relationships and the temperature logs they are read against.

CREATE TABLE maturity_curve (
    mix_code    TEXT NOT NULL,
    name        TEXT NOT NULL,
    fitted_on   TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (mix_code, name)
);

CREATE TABLE maturity_point (
    mix_code        TEXT NOT NULL,
    name            TEXT NOT NULL,
    maturity        REAL NOT NULL,
    strength_psi    REAL NOT NULL,
    PRIMARY KEY (mix_code, name, maturity),
    FOREIGN KEY (mix_code, name) REFERENCES maturity_curve(mix_code, name) ON DELETE CASCADE
);

CREATE TABLE temperature_log (
    id              INTEGER PRIMARY KEY,
    sensor          TEXT NOT NULL,
    placement       TEXT NOT NULL,
    at              TEXT NOT NULL,
    temperature_f   REAL NOT NULL,
    UNIQUE (sensor, at)
);

CREATE INDEX log_by_placement ON temperature_log (placement, at);
