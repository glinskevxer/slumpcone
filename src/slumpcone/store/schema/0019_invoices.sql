-- Invoices, their lines, the charges on them and the payments against them.

CREATE TABLE invoice (
    number          TEXT PRIMARY KEY,
    account_code    TEXT NOT NULL,
    invoiced_on     TEXT NOT NULL,
    terms_days      INTEGER NOT NULL,
    discount_days   INTEGER NOT NULL DEFAULT 0,
    discount_percent REAL NOT NULL DEFAULT 0,
    tax_percent     REAL NOT NULL DEFAULT 0,
    project         TEXT,
    status          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX invoice_by_account ON invoice (account_code, invoiced_on);
CREATE INDEX invoice_by_status ON invoice (status, invoiced_on);

CREATE TABLE invoice_line (
    invoice_number  TEXT NOT NULL REFERENCES invoice(number) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    ticket_number   TEXT NOT NULL,
    mix_code        TEXT NOT NULL,
    volume_yd3      REAL NOT NULL,
    unit_price      TEXT NOT NULL,
    PRIMARY KEY (invoice_number, position)
);

CREATE INDEX invoice_line_by_ticket ON invoice_line (ticket_number);

CREATE TABLE invoice_charge (
    invoice_number  TEXT NOT NULL REFERENCES invoice(number) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    kind            TEXT NOT NULL,
    quantity        REAL NOT NULL,
    amount          TEXT NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (invoice_number, position)
);

CREATE TABLE invoice_payment (
    invoice_number  TEXT NOT NULL REFERENCES invoice(number) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    received_on     TEXT NOT NULL,
    amount          TEXT NOT NULL,
    reference       TEXT,
    PRIMARY KEY (invoice_number, position)
);
