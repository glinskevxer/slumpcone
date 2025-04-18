-- Mixer uniformity tests, C94 Annex A1, and the two samples each one takes.

CREATE TABLE uniformity_test (
    mixer       TEXT NOT NULL,
    tested_on   TEXT NOT NULL,
    plant_code  TEXT NOT NULL DEFAULT '',
    technician  TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (mixer, tested_on)
);

CREATE TABLE uniformity_sample (
    mixer               TEXT NOT NULL,
    tested_on           TEXT NOT NULL,
    label               TEXT NOT NULL,
    unit_weight_lb_ft3  REAL NOT NULL,
    air_percent         REAL NOT NULL,
    slump_in            REAL NOT NULL,
    coarse_retained_pct REAL NOT NULL,
    coarse_gravity      REAL NOT NULL,
    sample_volume_ft3   REAL NOT NULL,
    coarse_mass_lb      REAL NOT NULL,
    strength_7day_psi   REAL,
    PRIMARY KEY (mixer, tested_on, label),
    FOREIGN KEY (mixer, tested_on)
        REFERENCES uniformity_test(mixer, tested_on) ON DELETE CASCADE
);

CREATE INDEX uniformity_by_day ON uniformity_test (tested_on);
CREATE INDEX uniformity_by_plant ON uniformity_test (plant_code, tested_on);
