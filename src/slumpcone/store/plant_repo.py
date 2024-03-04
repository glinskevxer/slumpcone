"""Reading and writing plants, with their scales and silos.

A plant is stored across three tables and read back as one object, because
nothing in the register wants a plant without its scales. The write is one
transaction that replaces the whole set rather than diffing it: a plant has a
handful of scales, and a partial update that leaves a removed scale behind is a
much worse outcome than rewriting four rows.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from slumpcone.errors import NotFoundError
from slumpcone.identity import normalize_code
from slumpcone.materials.kinds import MaterialClass, WaterSource
from slumpcone.plant.plant import MixingMethod, Plant
from slumpcone.plant.scale import Scale
from slumpcone.plant.silo import Silo
from slumpcone.store.db import Database
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


def _scale_from_row(row: sqlite3.Row) -> Scale:
    return Scale(
        code=str(row["code"]),
        name=str(row["name"]),
        capacity=Quantity(float(row["capacity_lb"]), "lb"),
        graduation=Quantity(float(row["graduation_lb"]), "lb"),
        weighs=tuple(MaterialClass(part) for part in str(row["weighs"]).split(",") if part),
        last_calibrated=date.fromisoformat(str(row["last_calibrated"])),
        calibration_days=int(row["calibration_days"]),
    )


def _silo_from_row(row: sqlite3.Row) -> Silo:
    return Silo(
        code=str(row["code"]),
        name=str(row["name"]),
        material_code=str(row["material_code"]),
        capacity=Quantity(float(row["capacity_lb"]), "lb"),
        level=Quantity(float(row["level_lb"]), "lb"),
        low_level=(
            None if row["low_level_lb"] is None else Quantity(float(row["low_level_lb"]), "lb")
        ),
    )


class PlantRepository:
    """Plants, scales and silos, on disk."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def save(self, plant: Plant, silos: tuple[Silo, ...] = ()) -> Plant:
        """Write a plant and replace its scales and silos wholesale."""
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO plant (code, name, unit_system, mixing_method, water_source, "
                "max_load_yd3, certification_expires, location, notes) "
                "VALUES (:code, :name, :unit_system, :mixing_method, :water_source, "
                ":max_load_yd3, :certification_expires, :location, :notes) "
                "ON CONFLICT(code) DO UPDATE SET name = :name, unit_system = :unit_system, "
                "mixing_method = :mixing_method, water_source = :water_source, "
                "max_load_yd3 = :max_load_yd3, "
                "certification_expires = :certification_expires, "
                "location = :location, notes = :notes",
                {
                    "code": plant.code,
                    "name": plant.name,
                    "unit_system": plant.unit_system.value,
                    "mixing_method": plant.mixing_method.value,
                    "water_source": plant.water_source.value,
                    "max_load_yd3": (
                        None if plant.max_load is None else plant.max_load.to("yd3").value
                    ),
                    "certification_expires": (
                        None
                        if plant.certification_expires is None
                        else plant.certification_expires.isoformat()
                    ),
                    "location": plant.location,
                    "notes": plant.notes,
                },
            )
            self._db.execute("DELETE FROM plant_scale WHERE plant_code = ?", (plant.code,))
            for scale in plant.scales:
                self._db.execute(
                    "INSERT INTO plant_scale (plant_code, code, name, capacity_lb, "
                    "graduation_lb, weighs, last_calibrated, calibration_days) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        plant.code,
                        scale.code,
                        scale.name,
                        scale.capacity.to("lb").value,
                        scale.graduation.to("lb").value,
                        ",".join(k.value for k in scale.weighs),
                        scale.last_calibrated.isoformat(),
                        scale.calibration_days,
                    ),
                )
            self._db.execute("DELETE FROM plant_silo WHERE plant_code = ?", (plant.code,))
            for silo in silos:
                self._db.execute(
                    "INSERT INTO plant_silo (plant_code, code, name, material_code, "
                    "capacity_lb, level_lb, low_level_lb) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        plant.code,
                        silo.code,
                        silo.name,
                        silo.material_code,
                        silo.capacity.to("lb").value,
                        silo.level.to("lb").value,
                        None if silo.low_level is None else silo.low_level.to("lb").value,
                    ),
                )
        return plant

    def get(self, code: str) -> Plant:
        """The plant filed under ``code``, with its scales."""
        key = normalize_code(code, field="plant_code")
        row = self._db.query_one("SELECT * FROM plant WHERE code = ?", (key,))
        if row is None:
            raise NotFoundError("plant", key)
        scales = self._db.query(
            "SELECT * FROM plant_scale WHERE plant_code = ? ORDER BY code", (key,)
        )
        return Plant(
            code=str(row["code"]),
            name=str(row["name"]),
            unit_system=UnitSystem(str(row["unit_system"])),
            mixing_method=MixingMethod(str(row["mixing_method"])),
            water_source=WaterSource(str(row["water_source"])),
            scales=tuple(_scale_from_row(scale_row) for scale_row in scales),
            max_load=(
                None
                if row["max_load_yd3"] is None
                else Quantity(float(row["max_load_yd3"]), "yd3")
            ),
            certification_expires=(
                None
                if row["certification_expires"] is None
                else date.fromisoformat(str(row["certification_expires"]))
            ),
            location=None if row["location"] is None else str(row["location"]),
            notes=str(row["notes"]),
        )

    def all(self) -> tuple[Plant, ...]:
        """Every plant, in code order."""
        rows = self._db.query("SELECT code FROM plant ORDER BY code")
        return tuple(self.get(str(row["code"])) for row in rows)

    def silos(self, code: str) -> tuple[Silo, ...]:
        """Every vessel on a plant, in code order."""
        key = normalize_code(code, field="plant_code")
        rows = self._db.query(
            "SELECT * FROM plant_silo WHERE plant_code = ? ORDER BY code", (key,)
        )
        return tuple(_silo_from_row(row) for row in rows)

    def silo(self, plant_code: str, silo_code: str) -> Silo:
        """One vessel by code."""
        key = normalize_code(silo_code, field="silo_code")
        for candidate in self.silos(plant_code):
            if candidate.code == key:
                return candidate
        raise NotFoundError("silo", key)

    def save_silo(self, plant_code: str, silo: Silo) -> Silo:
        """Write one vessel back, which is what a drawdown does."""
        key = normalize_code(plant_code, field="plant_code")
        self.get(key)
        self._db.execute(
            "INSERT INTO plant_silo (plant_code, code, name, material_code, capacity_lb, "
            "level_lb, low_level_lb) VALUES (:plant, :code, :name, :material, :capacity, "
            ":level, :low) ON CONFLICT(plant_code, code) DO UPDATE SET name = :name, "
            "material_code = :material, capacity_lb = :capacity, level_lb = :level, "
            "low_level_lb = :low",
            {
                "plant": key,
                "code": silo.code,
                "name": silo.name,
                "material": silo.material_code,
                "capacity": silo.capacity.to("lb").value,
                "level": silo.level.to("lb").value,
                "low": None if silo.low_level is None else silo.low_level.to("lb").value,
            },
        )
        return silo

    def silos_holding(self, material_code: str) -> tuple[tuple[str, Silo], ...]:
        """Every vessel across every plant holding one material."""
        key = normalize_code(material_code, field="material_code")
        rows = self._db.query(
            "SELECT * FROM plant_silo WHERE material_code = ? ORDER BY plant_code, code",
            (key,),
        )
        return tuple((str(row["plant_code"]), _silo_from_row(row)) for row in rows)

    def delete(self, code: str) -> None:
        """Remove a plant and everything on it."""
        key = normalize_code(code, field="plant_code")
        cursor = self._db.execute("DELETE FROM plant WHERE code = ?", (key,))
        if cursor.rowcount == 0:
            raise NotFoundError("plant", key)
