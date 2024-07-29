-- Orders booked against a project class.

CREATE TABLE concrete_order (
    number          TEXT PRIMARY KEY,
    project_code    TEXT NOT NULL,
    class_code      TEXT NOT NULL,
    volume_yd3      REAL NOT NULL,
    placement_date  TEXT NOT NULL,
    mix_code        TEXT,
    start_time      TEXT,
    rate_yd3        REAL,
    placement       TEXT,
    status          TEXT NOT NULL,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX order_by_project ON concrete_order (project_code, placement_date);
CREATE INDEX order_by_date ON concrete_order (placement_date, status);
