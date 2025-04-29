-- Haul profiles: how long a round trip to one job actually takes.

CREATE TABLE haul_profile (
    project_code        TEXT PRIMARY KEY,
    loading_minutes     REAL NOT NULL,
    haul_out_minutes    REAL NOT NULL,
    on_site_minutes     REAL NOT NULL,
    haul_back_minutes   REAL NOT NULL,
    wash_minutes        REAL NOT NULL,
    measured_on         TEXT,
    from_deliveries     INTEGER NOT NULL DEFAULT 0,
    notes               TEXT NOT NULL DEFAULT ''
);
