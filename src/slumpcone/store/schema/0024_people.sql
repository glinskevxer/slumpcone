-- Technicians and the certifications they hold.

CREATE TABLE technician (
    code        TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    employer    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE certification (
    number          TEXT PRIMARY KEY,
    technician_code TEXT NOT NULL REFERENCES technician(code) ON DELETE CASCADE,
    grade           TEXT NOT NULL,
    issued_on       TEXT NOT NULL,
    expires_on      TEXT NOT NULL
);

CREATE INDEX certification_by_technician ON certification (technician_code, expires_on);
CREATE INDEX certification_by_expiry ON certification (expires_on);
