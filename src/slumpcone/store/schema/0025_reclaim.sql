-- Wash water tanks and the loads that came back.

CREATE TABLE wash_tank (
    tank                TEXT NOT NULL,
    plant_code          TEXT NOT NULL,
    measured_on         TEXT NOT NULL,
    specific_gravity    REAL NOT NULL,
    volume              REAL NOT NULL,
    volume_unit         TEXT NOT NULL,
    notes               TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (plant_code, tank, measured_on)
);

CREATE TABLE returned_concrete (
    ticket_number       TEXT PRIMARY KEY,
    mix_code            TEXT NOT NULL,
    returned_on         TEXT NOT NULL,
    volume              REAL NOT NULL,
    volume_unit         TEXT NOT NULL,
    age_minutes         REAL NOT NULL,
    disposed_of         TEXT,
    used_in             TEXT
);

CREATE INDEX wash_tank_by_day ON wash_tank (measured_on);
CREATE INDEX returned_by_day ON returned_concrete (returned_on);
