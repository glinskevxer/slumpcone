"""Reading and writing projects, their classes and their submittals.

Submittals are keyed on their own reference rather than on the mixture, because
the same mixture is submitted to several jobs and each submission has its own
life. Looking up "is this mixture approved here" therefore means a query, not a
field, and that is the right way round: approval is a fact about a pairing.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slumpcone.errors import ConflictError, NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.project.project import Project, SpecifiedClass
from slumpcone.project.submittal import Submittal, SubmittalBasis, SubmittalStatus
from slumpcone.spec.exposure import ExposureSet
from slumpcone.store.db import Database
from slumpcone.store.rows import band_columns, band_from
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


def _class_from_row(row: sqlite3.Row) -> SpecifiedClass:
    return SpecifiedClass(
        code=str(row["code"]),
        specified_strength=Quantity(float(row["specified_strength_psi"]), "psi"),
        test_age_days=int(row["test_age_days"]),
        exposure=ExposureSet.parse(str(row["exposure"])),
        slump_band=band_from(
            None if row["slump_target_in"] is None else float(row["slump_target_in"]),
            None if row["slump_minus_in"] is None else float(row["slump_minus_in"]),
            None if row["slump_plus_in"] is None else float(row["slump_plus_in"]),
        ),
        air_band=band_from(
            None if row["air_target_pct"] is None else float(row["air_target_pct"]),
            None if row["air_minus_pct"] is None else float(row["air_minus_pct"]),
            None if row["air_plus_pct"] is None else float(row["air_plus_pct"]),
        ),
        max_water_cementitious=(
            None
            if row["max_water_cementitious"] is None
            else float(row["max_water_cementitious"])
        ),
        min_cementitious=(
            None
            if row["min_cementitious_lb"] is None
            else Quantity(float(row["min_cementitious_lb"]), "lb")
        ),
        nominal_max_size=(
            None
            if row["nominal_max_size_mm"] is None
            else Quantity(float(row["nominal_max_size_mm"]), "mm")
        ),
        description=str(row["description"]),
    )


def _submittal_from_row(row: sqlite3.Row) -> Submittal:
    return Submittal(
        reference=str(row["reference"]),
        project_code=str(row["project_code"]),
        class_code=str(row["class_code"]),
        mix_code=str(row["mix_code"]),
        mix_revision=int(row["mix_revision"]),
        submitted_on=date.fromisoformat(str(row["submitted_on"])),
        basis=SubmittalBasis(str(row["basis"])),
        status=SubmittalStatus(str(row["status"])),
        required_average=(
            None
            if row["required_average_psi"] is None
            else Quantity(float(row["required_average_psi"]), "psi")
        ),
        decided_on=(
            None if row["decided_on"] is None else date.fromisoformat(str(row["decided_on"]))
        ),
        expires_on=(
            None if row["expires_on"] is None else date.fromisoformat(str(row["expires_on"]))
        ),
        reviewer=None if row["reviewer"] is None else str(row["reviewer"]),
        comments=str(row["comments"]),
    )


class ProjectRepository:
    """Projects, classes and submittals, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, project: Project) -> Project:
        """Write a project and replace its classes wholesale."""
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO project (code, name, owner, specifier, unit_system, "
                "started_on, finished_on, notes) VALUES (:code, :name, :owner, :specifier, "
                ":system, :started, :finished, :notes) ON CONFLICT(code) DO UPDATE SET "
                "name = :name, owner = :owner, specifier = :specifier, "
                "unit_system = :system, started_on = :started, finished_on = :finished, "
                "notes = :notes",
                {
                    "code": project.code,
                    "name": project.name,
                    "owner": project.owner,
                    "specifier": project.specifier,
                    "system": project.unit_system.value,
                    "started": (
                        None if project.started_on is None else project.started_on.isoformat()
                    ),
                    "finished": (
                        None if project.finished_on is None else project.finished_on.isoformat()
                    ),
                    "notes": project.notes,
                },
            )
            self._db.execute(
                "DELETE FROM project_class WHERE project_code = ?", (project.code,)
            )
            for entry in project.classes:
                slump = band_columns(entry.slump_band)
                air = band_columns(entry.air_band)
                self._db.execute(
                    "INSERT INTO project_class (project_code, code, specified_strength_psi, "
                    "test_age_days, exposure, slump_target_in, slump_minus_in, slump_plus_in, "
                    "air_target_pct, air_minus_pct, air_plus_pct, max_water_cementitious, "
                    "min_cementitious_lb, nominal_max_size_mm, description) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        project.code,
                        entry.code,
                        entry.specified_strength.to("psi").value,
                        entry.test_age_days,
                        str(entry.exposure),
                        *slump,
                        *air,
                        entry.max_water_cementitious,
                        (
                            None
                            if entry.min_cementitious is None
                            else entry.min_cementitious.to("lb").value
                        ),
                        (
                            None
                            if entry.nominal_max_size is None
                            else entry.nominal_max_size.to("mm").value
                        ),
                        entry.description,
                    ),
                )
        return project

    def get(self, code: str) -> Project:
        """One project with its classes."""
        key = normalize_code(code, field="project_code")
        row = self._db.query_one("SELECT * FROM project WHERE code = ?", (key,))
        if row is None:
            raise NotFoundError("project", key)
        classes = self._db.query(
            "SELECT * FROM project_class WHERE project_code = ? ORDER BY code", (key,)
        )
        return Project(
            code=str(row["code"]),
            name=str(row["name"]),
            classes=tuple(_class_from_row(entry) for entry in classes),
            owner=None if row["owner"] is None else str(row["owner"]),
            specifier=None if row["specifier"] is None else str(row["specifier"]),
            unit_system=UnitSystem(str(row["unit_system"])),
            started_on=(
                None
                if row["started_on"] is None
                else date.fromisoformat(str(row["started_on"]))
            ),
            finished_on=(
                None
                if row["finished_on"] is None
                else date.fromisoformat(str(row["finished_on"]))
            ),
            notes=str(row["notes"]),
        )

    def all(self) -> tuple[Project, ...]:
        """Every project, in code order."""
        rows = self._db.query("SELECT code FROM project ORDER BY code")
        return tuple(self.get(str(row["code"])) for row in rows)

    def open_on(self, on: date) -> tuple[Project, ...]:
        """Every project running on ``on``."""
        return tuple(project for project in self.all() if project.is_open(on))

    def delete(self, code: str) -> None:
        """Remove a project and its classes."""
        key = normalize_code(code, field="project_code")
        cursor = self._db.execute("DELETE FROM project WHERE code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("project", key)

    def save_submittal(self, submittal: Submittal) -> Submittal:
        """Insert or update a submittal by reference."""
        self._db.execute(
            "INSERT INTO submittal (reference, project_code, class_code, mix_code, "
            "mix_revision, submitted_on, basis, status, required_average_psi, decided_on, "
            "expires_on, reviewer, comments) VALUES (:ref, :project, :class_code, :mix, "
            ":revision, :submitted, :basis, :status, :required, :decided, :expires, "
            ":reviewer, :comments) ON CONFLICT(reference) DO UPDATE SET "
            "project_code = :project, class_code = :class_code, mix_code = :mix, "
            "mix_revision = :revision, submitted_on = :submitted, basis = :basis, "
            "status = :status, required_average_psi = :required, decided_on = :decided, "
            "expires_on = :expires, reviewer = :reviewer, comments = :comments",
            {
                "ref": submittal.reference,
                "project": submittal.project_code,
                "class_code": submittal.class_code,
                "mix": submittal.mix_code,
                "revision": submittal.mix_revision,
                "submitted": submittal.submitted_on.isoformat(),
                "basis": submittal.basis.value,
                "status": submittal.status.value,
                "required": (
                    None
                    if submittal.required_average is None
                    else submittal.required_average.to("psi").value
                ),
                "decided": (
                    None if submittal.decided_on is None else submittal.decided_on.isoformat()
                ),
                "expires": (
                    None if submittal.expires_on is None else submittal.expires_on.isoformat()
                ),
                "reviewer": submittal.reviewer,
                "comments": submittal.comments,
            },
        )
        return submittal

    def submittal(self, reference: str) -> Submittal:
        """One submittal by reference."""
        key = normalize_code(reference, field="submittal_reference")
        row = self._db.query_one("SELECT * FROM submittal WHERE reference = ?", (key,))
        if row is None:
            raise NotFoundError("submittal", key)
        return _submittal_from_row(row)

    def submittals_for(self, project_code: str) -> tuple[Submittal, ...]:
        """Every submittal on one job, oldest first."""
        key = normalize_code(project_code, field="project_code")
        rows = self._db.query(
            "SELECT * FROM submittal WHERE project_code = ? ORDER BY submitted_on, reference",
            (key,),
        )
        return tuple(_submittal_from_row(row) for row in rows)

    def approved_mixes(
        self, project_code: str, class_code: str, on: date
    ) -> tuple[Submittal, ...]:
        """Every mixture a class may be batched from on ``on``."""
        key = normalize_code(class_code, field="class_code")
        return tuple(
            submittal
            for submittal in self.submittals_for(project_code)
            if submittal.class_code == key and submittal.is_valid_on(on)
        )

    def require_approval(
        self, project_code: str, class_code: str, mix_code: str, revision: int, on: date
    ) -> Submittal:
        """The approval covering one mixture, or a refusal naming what is missing."""
        wanted = normalize_code(mix_code, field="mix_code")
        for submittal in self.approved_mixes(project_code, class_code, on):
            if submittal.mix_code == wanted and submittal.mix_revision == revision:
                return submittal
        raise ConflictError("approved submittal", f"{wanted} r{revision}")
