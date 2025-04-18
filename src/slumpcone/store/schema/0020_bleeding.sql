-- Bleeding tests, their draws, and column segregation results.

CREATE TABLE bleed_test (
    ticket_number   TEXT NOT NULL,
    tested_on       TEXT NOT NULL,
    technician      TEXT NOT NULL DEFAULT '',
    sample_mass_lb  REAL NOT NULL,
    batch_mass_lb   REAL NOT NULL,
    batch_water_lb  REAL NOT NULL,
    area_in2        REAL NOT NULL,
    PRIMARY KEY (ticket_number, tested_on)
);

CREATE TABLE bleed_reading (
    ticket_number   TEXT NOT NULL,
    tested_on       TEXT NOT NULL,
    elapsed_minutes REAL NOT NULL,
    water_lb        REAL NOT NULL,
    PRIMARY KEY (ticket_number, tested_on, elapsed_minutes),
    FOREIGN KEY (ticket_number, tested_on)
        REFERENCES bleed_test(ticket_number, tested_on) ON DELETE CASCADE
);

CREATE TABLE column_segregation (
    ticket_number   TEXT NOT NULL,
    tested_on       TEXT NOT NULL,
    technician      TEXT NOT NULL DEFAULT '',
    top_coarse_lb   REAL NOT NULL,
    bottom_coarse_lb REAL NOT NULL,
    visual_index    INTEGER,
    PRIMARY KEY (ticket_number, tested_on)
);

CREATE INDEX bleed_by_day ON bleed_test (tested_on);
CREATE INDEX segregation_by_day ON column_segregation (tested_on);
