-- Customer accounts and what each one was quoted for a mixture.

CREATE TABLE account (
    code                TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    status              TEXT NOT NULL,
    terms_days          INTEGER NOT NULL,
    discount_days       INTEGER NOT NULL DEFAULT 0,
    discount_percent    REAL NOT NULL DEFAULT 0,
    credit_currency     TEXT,
    credit_limit        TEXT,
    contact             TEXT,
    phone               TEXT,
    notes               TEXT NOT NULL DEFAULT ''
);

CREATE TABLE account_quote (
    account_code    TEXT NOT NULL REFERENCES account(code) ON DELETE CASCADE,
    mix_code        TEXT NOT NULL,
    currency        TEXT NOT NULL,
    amount          TEXT NOT NULL,
    effective_from  TEXT,
    effective_to    TEXT,
    PRIMARY KEY (account_code, mix_code, effective_from)
);

CREATE INDEX quote_by_mix ON account_quote (mix_code, account_code);
