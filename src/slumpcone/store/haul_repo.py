"""Haul profiles, and fitting one to what the trucks actually did.

A dispatcher's first cycle time for a new job is a guess off a map. After a
week of tickets it does not have to be, because every delivery record already
carries the four moments the cycle is made of. This repository holds the profile
per job and can fit one from the deliveries on file.

The fit uses the median rather than the mean. One truck that sat two hours at a
job because the pump broke will drag a mean far enough to be useless, and that
kind of afternoon is not rare. The median throws it away without anybody having
to decide which records to exclude, which is a decision that never gets made
honestly.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import date, timedelta

from slumpcone.delivery.record import Delivery
from slumpcone.dispatch.schedule import CycleTime, ScheduleError
from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.store.db import Database
from slumpcone.store.guards import require_one
from slumpcone.store.rows import day, whole

# Below this many deliveries a fit says less than the dispatcher's own guess.
MINIMUM_SAMPLE = 3


class HaulRepository:
    """Haul profiles, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(
        self,
        project_code: str,
        cycle: CycleTime,
        *,
        measured_on: date | None = None,
        from_deliveries: int = 0,
        notes: str = "",
    ) -> CycleTime:
        """File a profile for one job, replacing any earlier one."""
        key = normalize_code(project_code, field="project_code")
        self._db.execute(
            "INSERT INTO haul_profile (project_code, loading_minutes, "
            "haul_out_minutes, on_site_minutes, haul_back_minutes, wash_minutes, "
            "measured_on, from_deliveries, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(project_code) DO UPDATE SET "
            "loading_minutes = excluded.loading_minutes, "
            "haul_out_minutes = excluded.haul_out_minutes, "
            "on_site_minutes = excluded.on_site_minutes, "
            "haul_back_minutes = excluded.haul_back_minutes, "
            "wash_minutes = excluded.wash_minutes, "
            "measured_on = excluded.measured_on, "
            "from_deliveries = excluded.from_deliveries, notes = excluded.notes",
            (
                key,
                cycle.loading.total_seconds() / 60,
                cycle.haul_out.total_seconds() / 60,
                cycle.on_site.total_seconds() / 60,
                cycle.haul_back.total_seconds() / 60,
                cycle.wash.total_seconds() / 60,
                None if measured_on is None else measured_on.isoformat(),
                from_deliveries,
                notes,
            ),
        )
        return cycle

    def get(self, project_code: str) -> CycleTime:
        """The profile on file for one job."""
        key = normalize_code(project_code, field="project_code")
        row = require_one(
            self._db,
            "SELECT * FROM haul_profile WHERE project_code = ?",
            (key,),
            "haul profile",
            key,
        )
        return CycleTime(
            timedelta(minutes=float(row["loading_minutes"])),
            timedelta(minutes=float(row["haul_out_minutes"])),
            timedelta(minutes=float(row["on_site_minutes"])),
            timedelta(minutes=float(row["haul_back_minutes"])),
            timedelta(minutes=float(row["wash_minutes"])),
        )

    def get_or(self, project_code: str, fallback: CycleTime) -> CycleTime:
        """The profile on file, or the caller's own guess."""
        try:
            return self.get(project_code)
        except NotFoundError:
            return fallback

    def provenance(self, project_code: str) -> tuple[date | None, int, str]:
        """When a profile was measured, off how many deliveries, and any note."""
        key = normalize_code(project_code, field="project_code")
        row = require_one(
            self._db,
            "SELECT measured_on, from_deliveries, notes FROM haul_profile "
            "WHERE project_code = ?",
            (key,),
            "haul profile",
            key,
        )
        return (day(row["measured_on"]), whole(row["from_deliveries"]) or 0, str(row["notes"]))

    def projects(self) -> tuple[str, ...]:
        """Every job with a profile, sorted."""
        rows = self._db.query("SELECT project_code FROM haul_profile ORDER BY project_code")
        return tuple(str(row["project_code"]) for row in rows)

    def forget(self, project_code: str) -> None:
        """Drop a profile."""
        key = normalize_code(project_code, field="project_code")
        cursor = self._db.execute("DELETE FROM haul_profile WHERE project_code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("haul profile", key)

    def fit(
        self,
        project_code: str,
        deliveries: Sequence[Delivery],
        *,
        loading: timedelta = timedelta(minutes=10),
        wash: timedelta = timedelta(minutes=5),
        haul_back: timedelta | None = None,
        measured_on: date | None = None,
    ) -> CycleTime:
        """Fit a profile from what the trucks actually did, and file it.

        A delivery record carries the run out and the time on site. It does not
        carry the run home, because nothing on the truck marks the moment it
        gets back, and it does not carry loading or washing either. So the run
        home is taken as equal to the run out unless the caller knows better,
        and the other two stay the caller's own figures. Every one of those is a
        stated assumption rather than a measurement, which is why they are
        arguments.
        """
        out: list[float] = []
        site: list[float] = []
        for record in deliveries:
            if record.left_plant_at and record.arrived_at:
                out.append((record.arrived_at - record.left_plant_at).total_seconds() / 60)
            if record.discharge_started_at and record.discharge_finished_at:
                site.append(
                    (record.discharge_finished_at - record.discharge_started_at).total_seconds()
                    / 60
                )
        if len(out) < MINIMUM_SAMPLE or len(site) < MINIMUM_SAMPLE:
            raise ScheduleError(
                "HAUL_FIT_TOO_THIN",
                f"a fit wants {MINIMUM_SAMPLE} complete records per leg, found "
                f"{len(out)} out and {len(site)} on site",
            )
        run_out = timedelta(minutes=statistics.median(out))
        cycle = CycleTime(
            loading,
            run_out,
            timedelta(minutes=statistics.median(site)),
            run_out if haul_back is None else haul_back,
            wash,
        )
        self.save(
            project_code,
            cycle,
            measured_on=measured_on,
            from_deliveries=len(deliveries),
            notes="fitted from delivery records",
        )
        return cycle
