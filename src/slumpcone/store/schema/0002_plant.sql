-- Plants, the scales that weigh on them and the vessels that feed them.

CREATE TABLE plant (
    code                    TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    unit_system             TEXT NOT NULL,
    mixing_method           TEXT NOT NULL,
    water_source            TEXT NOT NULL,
    max_load_yd3            REAL,
    certification_expires   TEXT,
    location                TEXT,
    notes                   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE plant_scale (
    plant_code          TEXT NOT NULL REFERENCES plant(code) ON DELETE CASCADE,
    code                TEXT NOT NULL,
    name                TEXT NOT NULL,
    capacity_lb         REAL NOT NULL,
    graduation_lb       REAL NOT NULL,
    weighs              TEXT NOT NULL,
    last_calibrated     TEXT NOT NULL,
    calibration_days    INTEGER NOT NULL,
    PRIMARY KEY (plant_code, code)
);

CREATE TABLE plant_silo (
    plant_code      TEXT NOT NULL REFERENCES plant(code) ON DELETE CASCADE,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    material_code   TEXT NOT NULL,
    capacity_lb     REAL NOT NULL,
    level_lb        REAL NOT NULL,
    low_level_lb    REAL,
    PRIMARY KEY (plant_code, code)
);

CREATE INDEX silo_by_material ON plant_silo (material_code, plant_code);
