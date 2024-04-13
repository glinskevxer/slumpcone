-- Mix designs, one row per revision, with their charges and admixture doses.

CREATE TABLE mix_design (
    code                    TEXT NOT NULL,
    revision                INTEGER NOT NULL,
    name                    TEXT NOT NULL,
    plant_code              TEXT,
    specified_strength_psi  REAL NOT NULL,
    test_age_days           INTEGER NOT NULL,
    nominal_max_size_mm     REAL NOT NULL,
    slump_target_in         REAL NOT NULL,
    slump_band_target_in    REAL,
    slump_minus_in          REAL,
    slump_plus_in           REAL,
    air_target_pct          REAL,
    air_minus_pct           REAL,
    air_plus_pct            REAL,
    design_air_pct          REAL NOT NULL,
    mass_unit               TEXT NOT NULL,
    volume_unit             TEXT NOT NULL,
    exposure                TEXT NOT NULL,
    notes                   TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (code, revision)
);

CREATE TABLE mix_design_charge (
    code            TEXT NOT NULL,
    revision        INTEGER NOT NULL,
    position        INTEGER NOT NULL,
    material_code   TEXT NOT NULL,
    material_class  TEXT NOT NULL,
    content         REAL NOT NULL,
    PRIMARY KEY (code, revision, position),
    FOREIGN KEY (code, revision) REFERENCES mix_design(code, revision) ON DELETE CASCADE
);

CREATE TABLE mix_design_admixture (
    code            TEXT NOT NULL,
    revision        INTEGER NOT NULL,
    position        INTEGER NOT NULL,
    material_code   TEXT NOT NULL,
    dose_floz_cwt   REAL NOT NULL,
    PRIMARY KEY (code, revision, position),
    FOREIGN KEY (code, revision) REFERENCES mix_design(code, revision) ON DELETE CASCADE
);

CREATE INDEX mix_design_by_plant ON mix_design (plant_code, code, revision);
