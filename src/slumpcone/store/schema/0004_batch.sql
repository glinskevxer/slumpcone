-- Delivery tickets, the weights that were recorded and the doses dispensed.

CREATE TABLE batch_ticket (
    number              TEXT PRIMARY KEY,
    plant_code          TEXT NOT NULL,
    mix_code            TEXT NOT NULL,
    mix_revision        INTEGER NOT NULL,
    batched_at          TEXT NOT NULL,
    volume_yd3          REAL NOT NULL,
    truck_code          TEXT,
    purchaser           TEXT,
    project             TEXT,
    cumulative_yd3      REAL,
    revolution_counter  INTEGER,
    water_held_back_lb  REAL,
    notes               TEXT NOT NULL DEFAULT ''
);

CREATE INDEX ticket_by_plant_date ON batch_ticket (plant_code, batched_at);
CREATE INDEX ticket_by_mix ON batch_ticket (mix_code, mix_revision, batched_at);
CREATE INDEX ticket_by_project ON batch_ticket (project, batched_at);

CREATE TABLE batch_ticket_line (
    ticket_number   TEXT NOT NULL REFERENCES batch_ticket(number) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    material_code   TEXT NOT NULL,
    material_class  TEXT NOT NULL,
    required_lb     REAL NOT NULL,
    actual_lb       REAL NOT NULL,
    allowance_lb    REAL NOT NULL,
    PRIMARY KEY (ticket_number, position)
);

CREATE TABLE batch_ticket_admixture (
    ticket_number   TEXT NOT NULL REFERENCES batch_ticket(number) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    material_code   TEXT NOT NULL,
    called_floz     REAL NOT NULL,
    dispensed_floz  REAL NOT NULL,
    PRIMARY KEY (ticket_number, position)
);
