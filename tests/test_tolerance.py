from __future__ import annotations

import pytest

from slumpcone.errors import ValidationError
from slumpcone.tolerance import Band, Side


class CaseConstruction:
    def test_symmetric(self) -> None:
        band = Band.symmetric(4.0, 1.0)
        assert band.low == pytest.approx(3.0)
        assert band.high == pytest.approx(5.0)

    def test_at_most_has_no_floor(self) -> None:
        band = Band.at_most(5.0)
        assert band.low is None
        assert band.high == pytest.approx(5.0)

    def test_at_least_has_no_ceiling(self) -> None:
        band = Band.at_least(3000.0)
        assert band.low == pytest.approx(3000.0)
        assert band.high is None

    def test_between_targets_the_midpoint(self) -> None:
        band = Band.between(4.5, 7.5)
        assert band.target == pytest.approx(6.0)
        assert band.low == pytest.approx(4.5)
        assert band.high == pytest.approx(7.5)

    def test_between_refuses_an_inverted_range(self) -> None:
        with pytest.raises(ValidationError, match="cannot be below"):
            Band.between(7.5, 4.5)

    def test_a_negative_allowance_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            Band(4.0, -1.0, 1.0)

    def test_a_band_open_on_both_sides_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="not a band"):
            Band(4.0, None, None)

    def test_an_infinite_target_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            Band(float("inf"), 1.0, 1.0)


class CaseSide:
    band = Band(4.0, 1.0, 1.5)

    def test_inside(self) -> None:
        assert self.band.side(4.0) is Side.IN
        assert self.band.side(3.0) is Side.IN
        assert self.band.side(5.5) is Side.IN

    def test_outside(self) -> None:
        assert self.band.side(2.75) is Side.LOW
        assert self.band.side(5.75) is Side.HIGH

    def test_contains_agrees_with_side(self) -> None:
        assert self.band.contains(4.0)
        assert not self.band.contains(2.0)

    def test_the_epsilon_saves_an_edge_computed_from_a_percentage(self) -> None:
        edge = Band.at_most(564.0 * 1.01)
        assert edge.contains(569.6400000000001)

    def test_one_sided_bands(self) -> None:
        assert Band.at_most(5.0).side(-100.0) is Side.IN
        assert Band.at_least(3000.0).side(1e9) is Side.IN

    def test_side_prints_its_own_name(self) -> None:
        assert str(Side.HIGH) == "high"


class CaseDeviation:
    band = Band.symmetric(4.0, 1.0)

    def test_zero_inside(self) -> None:
        assert self.band.deviation(4.5) == pytest.approx(0.0)

    def test_negative_below(self) -> None:
        assert self.band.deviation(2.5) == pytest.approx(-0.5)

    def test_positive_above(self) -> None:
        assert self.band.deviation(6.0) == pytest.approx(1.0)

    def test_one_sided(self) -> None:
        assert Band.at_most(5.0).deviation(-3.0) == pytest.approx(0.0)
        assert Band.at_least(5.0).deviation(9.0) == pytest.approx(0.0)


class CaseReshape:
    def test_clamp(self) -> None:
        band = Band.symmetric(4.0, 1.0)
        assert band.clamp(2.0) == pytest.approx(3.0)
        assert band.clamp(9.0) == pytest.approx(5.0)
        assert band.clamp(4.2) == pytest.approx(4.2)
        assert Band.at_most(5.0).clamp(-9.0) == pytest.approx(-9.0)

    def test_widen(self) -> None:
        band = Band.symmetric(4.0, 1.0).widen(0.5)
        assert band.low == pytest.approx(2.5)
        assert band.high == pytest.approx(5.5)

    def test_widen_leaves_an_open_side_open(self) -> None:
        band = Band.at_most(5.0).widen(1.0)
        assert band.low is None
        assert band.high == pytest.approx(6.0)

    def test_widen_refuses_a_negative(self) -> None:
        with pytest.raises(ValidationError):
            Band.symmetric(4.0, 1.0).widen(-0.1)


class CaseText:
    def test_symmetric(self) -> None:
        assert Band.symmetric(4.0, 1.0).format(1, "in") == "4.0 +/- 1.0 in"

    def test_asymmetric(self) -> None:
        assert Band(4.0, 1.0, 2.0).format(1) == "4.0 +2.0 -1.0"

    def test_one_sided(self) -> None:
        assert Band.at_most(5.0).format(1, "in") == "at most 5.0 in"
        assert Band.at_least(3000.0).format(0, "psi") == "at least 3000 psi"

    def test_default_str(self) -> None:
        assert str(Band.symmetric(4.0, 1.0)) == "4.00 +/- 1.00"
