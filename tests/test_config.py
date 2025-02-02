from __future__ import annotations

from pathlib import Path

import pytest

from slumpcone.config import (
    CONFIG_NAME,
    Settings,
    find_config,
    load_settings,
    parse_settings,
    render_settings,
)
from slumpcone.errors import ValidationError

FULL = """
[register]
path = "plant.sqlite3"

[defaults]
plant = "PL-1"
actor = "DK"
unit_system = "customary"

[output]
width = 120
colour = true
"""


class CaseParse:
    def test_a_full_file(self) -> None:
        settings = parse_settings(FULL, "slumpcone.toml")
        assert settings.register_path == "plant.sqlite3"
        assert settings.plant == "PL-1"
        assert settings.actor == "DK"
        assert settings.width == 120
        assert settings.colour is True
        assert settings.is_clean

    def test_an_empty_file_gives_defaults(self) -> None:
        settings = parse_settings("")
        assert settings.register_path is None
        assert settings.width == 96
        assert settings.colour is False

    def test_an_unknown_key_is_reported(self) -> None:
        settings = parse_settings('[defaults]\nplant = "PL-1"\nplan = "PL-2"\n')
        assert not settings.is_clean
        assert settings.unknown_keys == ("defaults.plan",)

    def test_an_unknown_section_is_reported(self) -> None:
        settings = parse_settings("[nonsense]\na = 1\n")
        assert settings.unknown_keys == ("nonsense",)

    def test_a_section_that_is_not_a_table(self) -> None:
        with pytest.raises(ValidationError, match="table of settings"):
            parse_settings("register = 1\n")

    def test_something_that_is_not_toml(self) -> None:
        with pytest.raises(ValidationError, match="not TOML"):
            parse_settings("this is not toml [[[")

    def test_a_silly_width(self) -> None:
        with pytest.raises(ValidationError, match="at least forty"):
            parse_settings("[output]\nwidth = 10\n")

    def test_a_width_that_is_not_a_number(self) -> None:
        with pytest.raises(ValidationError, match="whole number"):
            parse_settings('[output]\nwidth = "wide"\n')

    def test_a_colour_that_is_not_a_flag(self) -> None:
        with pytest.raises(ValidationError, match="true or false"):
            parse_settings('[output]\ncolour = "yes"\n')

    def test_describe(self) -> None:
        assert "PL-1" in parse_settings(FULL, "here.toml").describe()

    def test_describe_with_no_source(self) -> None:
        assert "defaults" in Settings().describe()


class CaseFinding:
    def test_it_finds_a_file_in_the_directory(self, tmp_path: Path) -> None:
        (tmp_path / CONFIG_NAME).write_text(FULL)
        assert find_config(tmp_path) == tmp_path / CONFIG_NAME

    def test_it_looks_upward(self, tmp_path: Path) -> None:
        (tmp_path / CONFIG_NAME).write_text(FULL)
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert find_config(nested) == tmp_path / CONFIG_NAME

    def test_the_nearest_one_wins(self, tmp_path: Path) -> None:
        (tmp_path / CONFIG_NAME).write_text(FULL)
        nested = tmp_path / "a"
        nested.mkdir()
        (nested / CONFIG_NAME).write_text('[defaults]\nplant = "PL-2"\n')
        found = find_config(nested)
        assert found == nested / CONFIG_NAME

    def test_nothing_to_find(self, tmp_path: Path) -> None:
        assert find_config(tmp_path) is None


class CaseLoading:
    def test_it_loads_what_it_finds(self, tmp_path: Path) -> None:
        (tmp_path / CONFIG_NAME).write_text(FULL)
        settings = load_settings(start=tmp_path)
        assert settings.plant == "PL-1"
        assert settings.source is not None

    def test_no_file_gives_defaults(self, tmp_path: Path) -> None:
        assert load_settings(start=tmp_path).plant is None

    def test_an_explicit_path(self, tmp_path: Path) -> None:
        target = tmp_path / "other.toml"
        target.write_text(FULL)
        assert load_settings(target).plant == "PL-1"

    def test_an_explicit_path_that_is_not_there(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="no settings file"):
            load_settings(tmp_path / "gone.toml")


class CaseRendering:
    def test_it_round_trips(self) -> None:
        settings = parse_settings(FULL)
        again = parse_settings(render_settings(settings))
        assert again.plant == settings.plant
        assert again.width == settings.width
        assert again.colour == settings.colour

    def test_empty_defaults_are_left_out(self) -> None:
        text = render_settings(Settings())
        assert "plant =" not in text
        assert "[defaults]" in text

    def test_a_starter_file_names_the_register(self) -> None:
        assert "slumpcone.sqlite3" in render_settings(Settings())
