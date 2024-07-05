-- Trucks, deliveries and the water that went in at the job.

CREATE TABLE truck (
    code                    TEXT PRIMARY KEY,
    drum_volume_yd3         REAL NOT NULL,
    fleet                   TEXT,
    last_uniformity_test    TEXT,
    uniformity_test_days    INTEGER NOT NULL,
    notes                   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE delivery (
    ticket_number           TEXT PRIMARY KEY,
    truck_code              TEXT NOT NULL,
    batched_at              TEXT NOT NULL,
    left_plant_at           TEXT,
    arrived_at              TEXT,
    discharge_started_at    TEXT,
    discharge_finished_at   TEXT,
    revolutions_on_arrival  INTEGER,
    revolutions_at_discharge INTEGER,
    returned_yd3            REAL,
    notes                   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX delivery_by_truck ON delivery (truck_code, batched_at);
CREATE INDEX delivery_by_date ON delivery (batched_at);

CREATE TABLE water_addition (
    ticket_number       TEXT NOT NULL REFERENCES delivery(ticket_number) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    added_at            TEXT NOT NULL,
    amount_gal          REAL NOT NULL,
    requested_by        TEXT NOT NULL,
    revolutions_after   INTEGER NOT NULL,
    discharged_before_yd3 REAL,
    PRIMARY KEY (ticket_number, position)
);
