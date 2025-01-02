-- An append only log of everything that changed the register.

CREATE TABLE audit_event (
    id          INTEGER PRIMARY KEY,
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    subject     TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    digest      TEXT NOT NULL
);

CREATE INDEX audit_by_subject ON audit_event (subject, at);
CREATE INDEX audit_by_actor ON audit_event (actor, at);
CREATE INDEX audit_by_action ON audit_event (action, at);
