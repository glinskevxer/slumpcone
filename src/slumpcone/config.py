"""The settings file, so a plant does not retype its own name all day.

Every command wants the same three or four things: which register, which plant,
who is running it. Passing them each time is how somebody ends up batching
against the wrong plant at half past five.

The file is TOML and it is deliberately small. Anything that changes what the
register *means* stays in the register: a plant's unit system, its scales, its
tolerances. What lives here is only what a person would otherwise have to type,
plus the two settings that are genuinely a preference rather than a fact.

Unknown keys are reported rather than ignored. A misspelled setting that is
silently dropped looks exactly like one that had no effect, and the operator
spends an afternoon on it.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from slumpcone.errors import ValidationError

CONFIG_NAME = "slumpcone.toml"

# Every key the file may carry, by section.
_KNOWN: dict[str, set[str]] = {
    "register": {"path"},
    "defaults": {"plant", "actor", "unit_system"},
    "output": {"width", "colour"},
}


@dataclass(frozen=True, slots=True)
class Settings:
    """What the settings file says."""

    register_path: str | None = None
    plant: str | None = None
    actor: str | None = None
    unit_system: str | None = None
    width: int = 96
    colour: bool = False
    source: str | None = None
    unknown_keys: tuple[str, ...] = field(default=())

    @property
    def is_clean(self) -> bool:
        """True when every key in the file was one this build knows."""
        return not self.unknown_keys

    def describe(self) -> str:
        """One line for a diagnostic."""
        where = self.source or "defaults"
        return (
            f"{where}: register {self.register_path or '-'}, plant "
            f"{self.plant or '-'}, actor {self.actor or '-'}"
        )


def find_config(start: Path | None = None) -> Path | None:
    """The nearest settings file, looking upward from a directory.

    Upward, because a plant runs commands from wherever the operator happens to
    be and the settings belong to the site rather than to the folder.
    """
    here = (start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


def _check_sections(document: dict[str, Any]) -> tuple[str, ...]:
    unknown: list[str] = []
    for section, values in document.items():
        if section not in _KNOWN:
            unknown.append(section)
            continue
        if not isinstance(values, dict):
            raise ValidationError(f"[{section}] should be a table of settings", field=section)
        for key in values:
            if key not in _KNOWN[section]:
                unknown.append(f"{section}.{key}")
    return tuple(sorted(unknown))


def parse_settings(text: str, source: str | None = None) -> Settings:
    """Read settings out of TOML text."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ValidationError(f"the settings file is not TOML: {exc}", field="config") from exc
    unknown = _check_sections(document)
    register = document.get("register", {})
    defaults = document.get("defaults", {})
    output = document.get("output", {})
    width = output.get("width", 96)
    if not isinstance(width, int) or width < 40:
        raise ValidationError(
            "output.width has to be a whole number of at least forty", field="width"
        )
    colour = output.get("colour", False)
    if not isinstance(colour, bool):
        raise ValidationError("output.colour is true or false", field="colour")
    return Settings(
        register_path=register.get("path"),
        plant=defaults.get("plant"),
        actor=defaults.get("actor"),
        unit_system=defaults.get("unit_system"),
        width=width,
        colour=colour,
        source=source,
        unknown_keys=unknown,
    )


def load_settings(path: Path | None = None, *, start: Path | None = None) -> Settings:
    """Read the settings file, or return the defaults when there is none."""
    chosen = path or find_config(start)
    if chosen is None:
        return Settings()
    if not chosen.is_file():
        raise ValidationError(f"no settings file at {chosen}", field="config")
    return parse_settings(chosen.read_text(encoding="utf-8"), str(chosen))


def render_settings(settings: Settings) -> str:
    """The settings back out as TOML, for writing a starter file."""
    lines = ["[register]"]
    lines.append(
        f'path = "{settings.register_path or CONFIG_NAME.replace(".toml", ".sqlite3")}"'
    )
    lines.append("")
    lines.append("[defaults]")
    if settings.plant:
        lines.append(f'plant = "{settings.plant}"')
    if settings.actor:
        lines.append(f'actor = "{settings.actor}"')
    if settings.unit_system:
        lines.append(f'unit_system = "{settings.unit_system}"')
    lines.append("")
    lines.append("[output]")
    lines.append(f"width = {settings.width}")
    lines.append(f"colour = {'true' if settings.colour else 'false'}")
    return "\n".join(lines) + "\n"
