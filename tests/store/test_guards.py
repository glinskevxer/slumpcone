from __future__ import annotations

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.register import Register
from slumpcone.store.db import Database
from slumpcone.store.guards import exists, refuse_existing, require_one


@pytest.fixture()
def database() -> Database:
    return Register.in_memory().database


def a_plant(database: Database) -> None:
    database.execute(
        "INSERT INTO plant (code, name, unit_system, mixing_method, water_source) "
        "VALUES (?, ?, ?, ?, ?)",
        ("PL-1", "Ashfield", "customary", "central", "municipal"),
    )


class CaseRequireOne:
    def test_it_hands_back_the_row(self, database: Database) -> None:
        a_plant(database)
        row = require_one(
            database, "SELECT * FROM plant WHERE code = ?", ("PL-1",), "plant", "PL-1"
        )
        assert row["name"] == "Ashfield"

    def test_nothing_there_is_a_not_found(self, database: Database) -> None:
        with pytest.raises(NotFoundError) as caught:
            require_one(
                database, "SELECT * FROM plant WHERE code = ?", ("PL-9",), "plant", "PL-9"
            )
        assert caught.value.kind == "plant"
        assert caught.value.identity == "PL-9"

    def test_the_error_names_what_was_asked_for_not_what_was_queried(
        self, database: Database
    ) -> None:
        # A join can read three tables and still owe the caller one name.
        with pytest.raises(NotFoundError) as caught:
            require_one(
                database,
                "SELECT * FROM plant JOIN plant_scale "
                "ON plant_scale.plant_code = plant.code WHERE plant.code = ?",
                ("PL-9",),
                "scale",
                "PL-9 SC-1",
            )
        assert caught.value.kind == "scale"

    def test_the_first_row_wins(self, database: Database) -> None:
        a_plant(database)
        database.execute(
            "INSERT INTO plant (code, name, unit_system, mixing_method, water_source) "
            "VALUES (?, ?, ?, ?, ?)",
            ("PL-2", "Rothwell", "customary", "central", "municipal"),
        )
        row = require_one(database, "SELECT * FROM plant ORDER BY code", (), "plant", "any")
        assert row["code"] == "PL-1"

    def test_it_takes_no_parameters(self, database: Database) -> None:
        a_plant(database)
        assert require_one(database, "SELECT 1 AS one", (), "thing", "x")["one"] == 1


class CaseRefuseExisting:
    def test_nothing_there_is_quiet(self, database: Database) -> None:
        refuse_existing(
            database, "SELECT 1 FROM plant WHERE code = ?", ("PL-9",), "plant", "PL-9"
        )

    def test_something_there_is_a_conflict(self, database: Database) -> None:
        a_plant(database)
        with pytest.raises(ConflictError) as caught:
            refuse_existing(
                database, "SELECT 1 FROM plant WHERE code = ?", ("PL-1",), "plant", "PL-1"
            )
        assert caught.value.kind == "plant"
        assert caught.value.identity == "PL-1"

    def test_a_row_of_falsy_columns_still_counts_as_there(self, database: Database) -> None:
        # This is the drift the helper exists to stop. A probe written as
        # `if db.query_one(...)` reads a row of zeroes as nothing at all.
        with pytest.raises(ConflictError):
            refuse_existing(database, "SELECT 0 AS zero", (), "thing", "x")

    def test_the_message_reads(self, database: Database) -> None:
        a_plant(database)
        with pytest.raises(ConflictError) as caught:
            refuse_existing(
                database, "SELECT 1 FROM plant WHERE code = ?", ("PL-1",), "plant", "PL-1"
            )
        assert "already on file" in str(caught.value)


class CaseExists:
    def test_nothing_there(self, database: Database) -> None:
        assert not exists(database, "SELECT 1 FROM plant WHERE code = ?", ("PL-9",))

    def test_something_there(self, database: Database) -> None:
        a_plant(database)
        assert exists(database, "SELECT 1 FROM plant WHERE code = ?", ("PL-1",))

    def test_a_falsy_row_is_still_there(self, database: Database) -> None:
        assert exists(database, "SELECT 0 AS zero")

    def test_it_defaults_to_no_parameters(self, database: Database) -> None:
        assert not exists(database, "SELECT 1 FROM plant")


def test_every_repository_reads_through_the_helpers() -> None:
    """No repository should be hand rolling the guard any more."""
    import pathlib

    store = pathlib.Path(__file__).resolve().parents[2] / "src" / "slumpcone" / "store"
    offenders = []
    for path in sorted(store.glob("*.py")):
        text = path.read_text()
        if "if row is None:\n            raise NotFoundError(" in text:
            offenders.append(path.name)
    assert offenders == []
