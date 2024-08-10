-- Material receipts and the movement ledger behind every silo level.

CREATE TABLE material_receipt (
    reference               TEXT PRIMARY KEY,
    plant_code              TEXT NOT NULL,
    silo_code               TEXT NOT NULL,
    material_code           TEXT NOT NULL,
    received_at             TEXT NOT NULL,
    quantity_lb             REAL NOT NULL,
    supplier                TEXT,
    supplier_ticket         TEXT,
    certificate_reference   TEXT,
    moisture_pct            REAL,
    notes                   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX receipt_by_plant_date ON material_receipt (plant_code, received_at);
CREATE INDEX receipt_by_material ON material_receipt (material_code, received_at);

CREATE TABLE inventory_movement (
    id              INTEGER PRIMARY KEY,
    plant_code      TEXT NOT NULL,
    silo_code       TEXT NOT NULL,
    material_code   TEXT NOT NULL,
    at              TEXT NOT NULL,
    kind            TEXT NOT NULL,
    quantity_lb     REAL NOT NULL,
    reference       TEXT,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX movement_by_silo ON inventory_movement (plant_code, silo_code, at);
CREATE INDEX movement_by_date ON inventory_movement (at, kind);
