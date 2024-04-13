from __future__ import annotations

import pytest

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.materials.kinds import MaterialClass
from slumpcone.mixdesign.design import MixDesign
from slumpcone.mixdesign.proportions import AdmixtureCharge, Charge, Proportions
from slumpcone.percent import Percent
from slumpcone.spec.exposure import ExposureSet
from slumpcone.store.db import Database
from slumpcone.store.migrations import migrate
from slumpcone.store.mixdesign_repo import MixDesignRepository
from slumpcone.tolerance import Band
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


@pytest.fixture()
def repo() -> MixDesignRepository:
    database = Database.in_memory()
    migrate(database)
    return MixDesignRepository(database)


def rate(value: float) -> MassPerVolume:
    return MassPerVolume(value, "lb", "yd3")


def proportions(air: float = 6.0) -> Proportions:
    return Proportions(
        (
            Charge("CEM-I", MaterialClass.CEMENT, rate(470)),
            Charge("SCM-F", MaterialClass.SCM, rate(94)),
            Charge("CA-57", MaterialClass.COARSE_AGGREGATE, rate(1780)),
            Charge("FA-1", MaterialClass.FINE_AGGREGATE, rate(1255)),
            Charge("W-1", MaterialClass.WATER, rate(250)),
        ),
        (AdmixtureCharge("AD-AE", Quantity(1.2, "floz")),),
        Percent(air),
    )


def design(**overrides: object) -> MixDesign:
    fields: dict[str, object] = {
        "code": "4000P-57",
        "name": "Paving mix",
        "proportions": proportions(),
        "specified_strength": Quantity(4500, "psi"),
        "nominal_max_size": Quantity(1.0, "in"),
        "slump_target": Quantity(4.0, "in"),
        "exposure": ExposureSet.parse("F2 S1"),
        "plant_code": "PL-1",
    }
    fields.update(overrides)
    return MixDesign(**fields)  # type: ignore[arg-type]


class CaseRoundTrip:
    def test_everything_comes_back(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        loaded = repo.get("4000P-57", 1)
        assert loaded.code == "4000P-57"
        assert loaded.name == "Paving mix"
        assert loaded.plant_code == "PL-1"
        assert loaded.specified_strength == Quantity(4500, "psi")
        assert loaded.test_age_days == 28
        assert str(loaded.exposure) == "F2 S1 W0 C0"

    def test_the_proportions_come_back_in_order(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        loaded = repo.get("4000P-57", 1)
        codes = [c.material_code for c in loaded.proportions.charges]
        assert codes == ["CEM-I", "SCM-F", "CA-57", "FA-1", "W-1"]
        assert loaded.proportions.cementitious == rate(564)

    def test_the_admixture_dose_comes_back(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        loaded = repo.get("4000P-57", 1)
        assert loaded.proportions.admixtures[0].material_code == "AD-AE"
        assert loaded.proportions.admixtures[0].dose_per_cwt.value == pytest.approx(1.2)

    def test_the_slump_band_survives(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        band = repo.get("4000P-57", 1).slump_tolerance()
        assert band.low == pytest.approx(2.5)
        assert band.high == pytest.approx(5.5)

    def test_a_one_sided_slump_band_survives(self, repo: MixDesignRepository) -> None:
        repo.save(design(slump_band=Band.at_most(5.0)))
        band = repo.get("4000P-57", 1).slump_tolerance()
        assert band.low is None
        assert band.high == pytest.approx(5.0)

    def test_the_air_band_survives(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        band = repo.get("4000P-57", 1).air_tolerance()
        assert band is not None
        assert band.low == pytest.approx(4.5)

    def test_a_design_with_no_air_has_no_band(self, repo: MixDesignRepository) -> None:
        repo.save(design(proportions=proportions(air=0.0)))
        assert repo.get("4000P-57", 1).air_tolerance() is None

    def test_the_nominal_size_survives_the_millimetre_column(
        self, repo: MixDesignRepository
    ) -> None:
        repo.save(design())
        loaded = repo.get("4000P-57", 1)
        assert loaded.nominal_max_size.to("in").value == pytest.approx(1.0)


class CaseRevisions:
    def test_saving_the_same_revision_twice_is_refused(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        with pytest.raises(ConflictError, match="4000P-57 r1"):
            repo.save(design())

    def test_latest_returns_the_highest(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        repo.save(design().revise(proportions(air=5.0)))
        assert repo.latest("4000P-57").revision == 2

    def test_revisions_are_oldest_first(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        repo.save(design().revise(proportions(air=5.0)))
        assert [d.revision for d in repo.revisions("4000P-57")] == [1, 2]

    def test_an_earlier_revision_is_untouched(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        repo.save(design().revise(proportions(air=5.0)))
        assert repo.get("4000P-57", 1).design_air == Percent(6.0)
        assert repo.get("4000P-57", 2).design_air == Percent(5.0)


class CaseLookups:
    def test_get_names_what_is_missing(self, repo: MixDesignRepository) -> None:
        with pytest.raises(NotFoundError, match="4000P-57 r3"):
            repo.get("4000P-57", 3)

    def test_latest_names_what_is_missing(self, repo: MixDesignRepository) -> None:
        with pytest.raises(NotFoundError, match="4000P-57"):
            repo.latest("4000P-57")

    def test_codes_and_latest_all(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        repo.save(design(code="3000W-67", name="Wall mix"))
        assert repo.codes() == ("3000W-67", "4000P-57")
        assert [d.code for d in repo.latest_all()] == ["3000W-67", "4000P-57"]

    def test_for_plant(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        repo.save(design(code="3000W-67", name="Wall mix", plant_code="PL-2"))
        assert [d.code for d in repo.for_plant("pl 1")] == ["4000P-57"]

    def test_delete_takes_the_charges_with_it(self, repo: MixDesignRepository) -> None:
        repo.save(design())
        repo.delete("4000P-57", 1)
        assert repo.codes() == ()
        assert repo._db.scalar("SELECT count(*) FROM mix_design_charge") == 0
        assert repo._db.scalar("SELECT count(*) FROM mix_design_admixture") == 0

    def test_delete_names_what_is_missing(self, repo: MixDesignRepository) -> None:
        with pytest.raises(NotFoundError):
            repo.delete("4000P-57", 1)
