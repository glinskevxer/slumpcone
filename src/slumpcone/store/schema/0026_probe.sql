-- Moisture probe calibration checks against oven dried samples.

CREATE TABLE probe_check (
    probe_code      TEXT NOT NULL,
    plant_code      TEXT NOT NULL,
    checked_on      TEXT NOT NULL,
    probe_percent   REAL NOT NULL,
    oven_percent    REAL NOT NULL,
    technician      TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (plant_code, probe_code, checked_on)
);

CREATE INDEX probe_check_by_day ON probe_check (checked_on);
