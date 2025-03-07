from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from slumpcone.errors import ConflictError, NotFoundError, ValidationError
from slumpcone.store.db import Database
from slumpcone.store.maturity_repo import MaturityRepository
from slumpcone.store.migrations import migrate
from slumpcone.strength.maturity import (
    MaturityCurve,
    MaturityPoint,
    TemperatureReading,
)
from slumpcone.units.quantity import Quantity
from slumpcone.units.temperature import Temperature

FITTED = date(2024, 5, 1)
START = datetime(2024, 6, 12, 8, 0)


@pytest.fixture()
def repo() -> MaturityRepository:
    database = Database.in_memory()
    migrate(database)
    return MaturityRepository(database)


def curve(mix: str = "4000P-57") -> MaturityCurve:
    return MaturityCurve(
        mix,
        (
            MaturityPoint(240.0, Quantity(2200, "psi")),
            MaturityPoint(480.0, Quantity(3300, "psi")),
            MaturityPoint(960.0, Quantity(4300, "psi")),
        ),
    )


def history(hours: int = 48, celsius: float = 20.0) -> list[TemperatureReading]:
    return [
        TemperatureReading(START + timedelta(hours=step), Temperature(celsius, "C"))
        for step in range(0, hours + 1, 12)
    ]


class CaseCurves:
    def test_round_trip(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        loaded = repo.curve("4000p 57", "summer")
        assert loaded.mix_code == "4000P-57"
        assert len(loaded.points) == 3
        assert loaded.span == (240.0, 960.0)

    def test_two_curves_for_one_mixture(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        repo.save_curve(curve(), "winter", FITTED)
        assert repo.curves_for("4000P-57") == ("summer", "winter")

    def test_the_same_name_twice(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        with pytest.raises(ConflictError, match="summer"):
            repo.save_curve(curve(), "summer", FITTED)

    def test_an_unknown_curve(self, repo: MaturityRepository) -> None:
        with pytest.raises(NotFoundError, match="summer"):
            repo.curve("4000P-57", "summer")

    def test_delete_takes_the_points(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        repo.delete_curve("4000P-57", "summer")
        assert repo.curves_for("4000P-57") == ()
        assert repo._db.scalar("SELECT count(*) FROM maturity_point") == 0

    def test_deleting_an_unknown_curve(self, repo: MaturityRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete_curve("4000P-57", "summer")


class CaseReadings:
    def test_one_reading(self, repo: MaturityRepository) -> None:
        repo.record_reading("SN-1", "Bay 4 slab", history()[0])
        assert len(repo.readings("SN-1")) == 1

    def test_the_same_moment_twice(self, repo: MaturityRepository) -> None:
        repo.record_reading("SN-1", "Bay 4 slab", history()[0])
        with pytest.raises(ConflictError, match="SN-1"):
            repo.record_reading("SN-1", "Bay 4 slab", history()[0])

    def test_an_upload_lands_everything_the_first_time(self, repo: MaturityRepository) -> None:
        assert repo.upload("SN-1", "Bay 4 slab", history()) == 5

    def test_a_second_upload_lands_only_the_new_ones(self, repo: MaturityRepository) -> None:
        repo.upload("SN-1", "Bay 4 slab", history(24))
        assert repo.upload("SN-1", "Bay 4 slab", history(48)) == 2

    def test_readings_come_back_oldest_first(self, repo: MaturityRepository) -> None:
        repo.upload("SN-1", "Bay 4 slab", list(reversed(history())))
        moments = [reading.at for reading in repo.readings("SN-1")]
        assert moments == sorted(moments)

    def test_readings_between(self, repo: MaturityRepository) -> None:
        repo.upload("SN-1", "Bay 4 slab", history())
        found = repo.readings_between("SN-1", date(2024, 6, 12), date(2024, 6, 12))
        assert len(found) == 2

    def test_sensors_on_a_placement(self, repo: MaturityRepository) -> None:
        repo.upload("SN-1", "Bay 4 slab", history(12))
        repo.upload("SN-2", "Bay 4 slab", history(12))
        repo.upload("SN-3", "Bay 2 wall", history(12))
        assert repo.sensors("Bay 4 slab") == ("SN-1", "SN-2")

    def test_the_temperature_survives(self, repo: MaturityRepository) -> None:
        repo.upload("SN-1", "Bay 4 slab", history(12, celsius=30.0))
        assert repo.readings("SN-1")[0].temperature.celsius == pytest.approx(30.0)


class CaseEstimate:
    def test_it_reads_a_strength_off_the_curve(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        repo.upload("SN-1", "Bay 4 slab", history(48))
        strength = repo.estimate("4000P-57", "summer", "SN-1")
        assert strength.value > 0.0

    def test_a_warmer_history_reads_stronger(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        repo.upload("SN-1", "Bay 4 slab", history(48, celsius=20.0))
        repo.upload("SN-2", "Bay 4 slab", history(48, celsius=35.0))
        assert repo.estimate("4000P-57", "summer", "SN-2") > repo.estimate(
            "4000P-57", "summer", "SN-1"
        )

    def test_a_sensor_with_one_reading(self, repo: MaturityRepository) -> None:
        repo.save_curve(curve(), "summer", FITTED)
        repo.record_reading("SN-1", "Bay 4 slab", history()[0])
        with pytest.raises(ValidationError, match="fewer than two readings"):
            repo.estimate("4000P-57", "summer", "SN-1")

    def test_an_unknown_curve(self, repo: MaturityRepository) -> None:
        repo.upload("SN-1", "Bay 4 slab", history())
        with pytest.raises(NotFoundError):
            repo.estimate("4000P-57", "summer", "SN-1")
