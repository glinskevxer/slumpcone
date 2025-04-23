-- Emission factors and the benchmark tables footprints are judged against.

CREATE TABLE emission_factor (
    material_code   TEXT PRIMARY KEY,
    material_class  TEXT NOT NULL,
    kg_co2e_per_kg  REAL NOT NULL,
    stage           TEXT NOT NULL,
    provenance      TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT '',
    published_on    TEXT
);

CREATE TABLE admixture_density (
    material_code   TEXT PRIMARY KEY,
    value           REAL NOT NULL,
    mass_unit       TEXT NOT NULL,
    volume_unit     TEXT NOT NULL
);

CREATE TABLE benchmark_table (
    name        TEXT PRIMARY KEY,
    published   TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE benchmark_class (
    table_name      TEXT NOT NULL,
    floor_psi       REAL NOT NULL,
    limit_kg_per_m3 REAL NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (table_name, floor_psi),
    FOREIGN KEY (table_name) REFERENCES benchmark_table(name) ON DELETE CASCADE
);

CREATE INDEX factor_by_class ON emission_factor (material_class);
