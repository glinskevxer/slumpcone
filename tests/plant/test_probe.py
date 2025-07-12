from __future__ import annotations

from datetime import date, timedelta

import pytest

from slumpcone.percent import Percent
from slumpcone.plant.probe import (
    CHECK_VALID_DAYS,
    ProbeCheck,
    ProbeError,
    ProbeHistory,
    ProbeStanding,
    history_for,
    probes_needing_attention,
)

TODAY = date(2024, 6, 12)


def check(
    *,
    probe: float = 4.5,
    oven: float = 4.3,
    days_ago: int = 3,
    code: str = "MP-1",
) -> ProbeCheck:
    return ProbeCheck(
        code,
        TODAY - timedelta(days=days_ago),
        Percent(probe),
        Percent(oven),
        "R. Okafor",
    )


class CaseOneCheck:
    def test_the_offset(self) -> None:
        assert check(probe=4.5, oven=4.3).offset.value == pytest.approx(0.2)

    def test_a_probe_reading_low(self) -> None:
        one = check(probe=4.0, oven=4.3)
        assert one.offset.value == pytest.approx(-0.3)
        assert not one.reads_high

    def test_a_probe_reading_high(self) -> None:
        assert check(probe=4.5, oven=4.3).reads_high

    def test_a_small_offset_is_inside_the_limit(self) -> None:
        assert check(probe=4.5, oven=4.3).is_within_limit

    def test_a_large_offset_is_not(self) -> None:
        assert not check(probe=6.0, oven=4.3).is_within_limit

    def test_exactly_on_the_limit_passes(self) -> None:
        assert check(probe=5.3, oven=4.3).is_within_limit

    def test_the_limit_works_in_both_directions(self) -> None:
        assert not check(probe=3.0, oven=4.3).is_within_limit

    def test_days_since(self) -> None:
        assert check(days_ago=10).days_since(TODAY) == 10

    def test_negative_moisture(self) -> None:
        with pytest.raises(ProbeError) as caught:
            check(probe=-1.0)
        assert caught.value.code == "PROBE_NEGATIVE_MOISTURE"

    def test_a_reading_that_is_not_aggregate_moisture(self) -> None:
        with pytest.raises(ProbeError) as caught:
            check(oven=45.0)
        assert caught.value.code == "PROBE_MOISTURE_OFF_SCALE"

    def test_the_code_is_normalised(self) -> None:
        assert check(code=" mp-1 ").probe_code == "MP-1"

    def test_describe(self) -> None:
        text = check(probe=4.5, oven=4.3).describe()
        assert "0.20 points high" in text
        assert "within limit" in text

    def test_a_failing_check_describes(self) -> None:
        assert "out of limit" in check(probe=6.0, oven=4.3).describe()


class CaseHistory:
    def steady(self) -> ProbeHistory:
        return ProbeHistory(
            "MP-1",
            (
                check(probe=4.5, oven=4.3, days_ago=60),
                check(probe=4.4, oven=4.2, days_ago=30),
                check(probe=4.6, oven=4.35, days_ago=3),
            ),
        )

    def wandering(self) -> ProbeHistory:
        return ProbeHistory(
            "MP-1",
            (
                check(probe=4.35, oven=4.3, days_ago=60),
                check(probe=4.9, oven=4.2, days_ago=30),
                check(probe=4.6, oven=4.35, days_ago=3),
            ),
        )

    def test_the_latest_check(self) -> None:
        latest = self.steady().latest
        assert latest is not None
        assert latest.days_since(TODAY) == 3

    def test_no_checks_at_all(self) -> None:
        empty = ProbeHistory("MP-1", ())
        assert empty.latest is None
        assert empty.mean_offset.value == pytest.approx(0.0)
        assert empty.drift.value == pytest.approx(0.0)

    def test_the_mean_offset(self) -> None:
        assert self.steady().mean_offset.value == pytest.approx(
            (0.2 + 0.2 + 0.25) / 3, rel=1e-6
        )

    def test_a_steady_probe_is_not_drifting(self) -> None:
        assert self.steady().drift.value == pytest.approx(0.05, abs=1e-9)
        assert not self.steady().is_drifting

    def test_a_wandering_probe_is(self) -> None:
        assert self.wandering().drift.value == pytest.approx(0.65, abs=1e-9)
        assert self.wandering().is_drifting

    def test_one_check_cannot_show_drift(self) -> None:
        one = ProbeHistory("MP-1", (check(),))
        assert one.drift.value == pytest.approx(0.0)
        assert not one.is_drifting

    def test_a_history_carrying_somebody_elses_check(self) -> None:
        with pytest.raises(ProbeError) as caught:
            ProbeHistory("MP-1", (check(code="MP-2"),))
        assert caught.value.code == "PROBE_HISTORY_MIXED"

    def test_gathering_one_probes_checks(self) -> None:
        pile = [check(code="MP-1"), check(code="MP-2"), check(code="MP-1", days_ago=9)]
        assert len(history_for("MP-1", pile).checks) == 2

    def test_gathering_for_a_probe_with_nothing(self) -> None:
        assert history_for("MP-9", [check()]).checks == ()

    def test_describe(self) -> None:
        text = self.steady().describe(TODAY)
        assert "3 check(s)" in text
        assert "mean offset +0.22" in text


class CaseStanding:
    def test_a_recently_checked_probe_is_good(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=3),))
        assert history.standing(TODAY) is ProbeStanding.GOOD
        assert history.standing(TODAY).may_batch

    def test_a_probe_near_the_end_of_its_window_is_due(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=27),))
        assert history.standing(TODAY) is ProbeStanding.DUE
        assert not history.standing(TODAY).may_batch

    def test_a_probe_past_its_window_is_overdue(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=45),))
        assert history.standing(TODAY) is ProbeStanding.OVERDUE

    def test_a_probe_never_checked_is_overdue_not_failed(self) -> None:
        assert ProbeHistory("MP-1", ()).standing(TODAY) is ProbeStanding.OVERDUE

    def test_a_probe_that_failed_its_check_is_failed(self) -> None:
        history = ProbeHistory("MP-1", (check(probe=6.0, oven=4.3, days_ago=3),))
        assert history.standing(TODAY) is ProbeStanding.FAILED

    def test_a_failed_check_beats_a_fresh_date(self) -> None:
        history = ProbeHistory("MP-1", (check(probe=6.0, oven=4.3, days_ago=0),))
        assert history.standing(TODAY) is ProbeStanding.FAILED

    def test_the_window_can_be_tightened(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=10),))
        assert history.standing(TODAY, valid_days=7) is ProbeStanding.OVERDUE

    def test_the_default_window(self) -> None:
        assert CHECK_VALID_DAYS == 30

    def test_every_standing_but_good_needs_attention(self) -> None:
        for standing in ProbeStanding:
            assert standing.needs_attention is (standing is not ProbeStanding.GOOD)

    def test_the_standing_reads_as_words(self) -> None:
        assert str(ProbeStanding.OVERDUE) == "overdue, do not batch off it"


class CaseCorrecting:
    def test_a_good_probe_gets_its_offset_taken_off(self) -> None:
        history = ProbeHistory("MP-1", (check(probe=4.5, oven=4.3, days_ago=3),))
        assert history.corrected(Percent(5.0), TODAY).value == pytest.approx(4.8)

    def test_a_probe_reading_low_gets_the_correction_added(self) -> None:
        history = ProbeHistory("MP-1", (check(probe=4.0, oven=4.3, days_ago=3),))
        assert history.corrected(Percent(5.0), TODAY).value == pytest.approx(5.3)

    def test_the_correction_never_goes_below_zero(self) -> None:
        history = ProbeHistory("MP-1", (check(probe=5.0, oven=4.3, days_ago=3),))
        assert history.corrected(Percent(0.2), TODAY).value == pytest.approx(0.0)

    def test_an_overdue_probe_refuses(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=45),))
        with pytest.raises(ProbeError) as caught:
            history.corrected(Percent(5.0), TODAY)
        assert caught.value.code == "PROBE_NOT_IN_STANDING"

    def test_a_probe_that_has_never_been_checked_refuses(self) -> None:
        with pytest.raises(ProbeError):
            ProbeHistory("MP-1", ()).corrected(Percent(5.0), TODAY)

    def test_a_probe_due_for_a_check_refuses_too(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=27),))
        with pytest.raises(ProbeError):
            history.corrected(Percent(5.0), TODAY)

    def test_the_refusal_names_the_standing(self) -> None:
        history = ProbeHistory("MP-1", (check(days_ago=45),))
        with pytest.raises(ProbeError) as caught:
            history.corrected(Percent(5.0), TODAY)
        assert "overdue" in str(caught.value)


class CaseAttention:
    def test_nothing_to_look_at(self) -> None:
        good = ProbeHistory("MP-1", (check(days_ago=3),))
        assert probes_needing_attention([good], TODAY) == ()

    def test_the_worst_comes_first(self) -> None:
        due = ProbeHistory("MP-2", (check(days_ago=27, code="MP-2"),))
        overdue = ProbeHistory("MP-3", (check(days_ago=45, code="MP-3"),))
        failed = ProbeHistory("MP-4", (check(probe=6.0, oven=4.3, days_ago=3, code="MP-4"),))
        found = probes_needing_attention([due, overdue, failed], TODAY)
        assert [one.probe_code for one in found] == ["MP-4", "MP-3", "MP-2"]

    def test_a_good_probe_is_left_out(self) -> None:
        good = ProbeHistory("MP-1", (check(days_ago=3),))
        due = ProbeHistory("MP-2", (check(days_ago=27, code="MP-2"),))
        found = probes_needing_attention([good, due], TODAY)
        assert [one.probe_code for one in found] == ["MP-2"]

    def test_ties_break_on_the_code(self) -> None:
        first = ProbeHistory("MP-9", (check(days_ago=45, code="MP-9"),))
        second = ProbeHistory("MP-2", (check(days_ago=45, code="MP-2"),))
        found = probes_needing_attention([first, second], TODAY)
        assert [one.probe_code for one in found] == ["MP-2", "MP-9"]

    def test_nothing_at_all(self) -> None:
        assert probes_needing_attention([], TODAY) == ()
