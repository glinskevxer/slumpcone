-- Material prices, with the window each one is in force over.

CREATE TABLE material_price (
    id              INTEGER PRIMARY KEY,
    material_code   TEXT NOT NULL,
    currency        TEXT NOT NULL,
    amount          TEXT NOT NULL,
    per_value       REAL NOT NULL,
    per_unit        TEXT NOT NULL,
    effective_from  TEXT,
    effective_to    TEXT,
    UNIQUE (material_code, currency, effective_from)
);

CREATE INDEX price_by_material ON material_price (material_code, effective_from);
