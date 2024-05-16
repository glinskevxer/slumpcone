-- Fresh property tests taken at the point of discharge.

CREATE TABLE fresh_test (
    id                      INTEGER PRIMARY KEY,
    ticket_number           TEXT NOT NULL,
    kind                    TEXT NOT NULL,
    taken_at                TEXT NOT NULL,
    slump_in                REAL,
    air_pct                 REAL,
    temperature_f           REAL,
    unit_weight_lb_ft3      REAL,
    discharged_before_yd3   REAL,
    technician              TEXT,
    is_retest               INTEGER NOT NULL DEFAULT 0,
    notes                   TEXT NOT NULL DEFAULT '',
    UNIQUE (ticket_number, kind, taken_at, is_retest)
);

CREATE INDEX fresh_test_by_ticket ON fresh_test (ticket_number, taken_at);
CREATE INDEX fresh_test_by_date ON fresh_test (taken_at, kind);
