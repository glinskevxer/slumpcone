-- Materials the plant can batch, and the certificates covering them.

CREATE TABLE material (
    code                    TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    material_class          TEXT NOT NULL,
    supplier                TEXT,
    source                  TEXT,
    specific_gravity        REAL,
    absorption_percent      REAL,
    fineness_modulus        REAL,
    nominal_max_size_mm     REAL,
    dry_rodded_lb_per_ft3   REAL,
    cement_type             TEXT,
    scm_kind                TEXT,
    admixture_type          TEXT,
    solids_percent          REAL,
    water_source            TEXT,
    notes                   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX material_by_class ON material (material_class, code);

CREATE TABLE material_certificate (
    id              INTEGER PRIMARY KEY,
    material_code   TEXT NOT NULL REFERENCES material(code) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    reference       TEXT NOT NULL,
    issued          TEXT NOT NULL,
    expires         TEXT NOT NULL,
    issuer          TEXT,
    lot             TEXT,
    UNIQUE (material_code, reference)
);

CREATE INDEX certificate_by_material ON material_certificate (material_code, kind, expires);
