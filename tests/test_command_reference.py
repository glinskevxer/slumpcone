from __future__ import annotations

import click
import pytest

from slumpcone.cli.main import cli
from slumpcone.tools.command_reference import (
    CommandPage,
    OptionLine,
    command_count,
    render_reference,
    walk,
)


@click.group("toy")
def toy() -> None:
    """A toy root.

    With a second paragraph nobody sees at the terminal.
    """


@toy.group("thing")
def thing_group() -> None:
    """Do things."""


@thing_group.command("make")
@click.argument("name")
@click.option("--size", default="9 yd3", help="How big.")
@click.option("--force", is_flag=True, help="Do it anyway.")
@click.option("--who", required=True)
@click.option("--secret", hidden=True, default="x")
def make_command(name: str, size: str, force: bool, who: str, secret: str) -> None:
    """Make one.

    The body, which the reference keeps.
    """


class CaseWalking:
    def test_it_finds_the_group_and_the_command(self) -> None:
        paths = [one.path for one in walk(toy)]
        assert paths == ["thing", "thing make"]

    def test_the_summary_is_the_first_line(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        assert page.summary == "Make one."

    def test_the_body_is_the_rest(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        assert "The body, which the reference keeps." in page.body

    def test_the_arguments_come_in_order(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        assert page.arguments == ("name",)

    def test_hidden_options_are_left_out(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        assert all("secret" not in one.flags for one in page.options)

    def test_help_is_left_out(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        assert all("--help" not in one.flags for one in page.options)

    def test_a_default_shows(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        size = next(one for one in page.options if "--size" in one.flags)
        assert size.default == "`9 yd3`"

    def test_a_flag_shows_no_default(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        force = next(one for one in page.options if "--force" in one.flags)
        assert force.default == ""

    def test_a_required_option_says_so(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        who = next(one for one in page.options if "--who" in one.flags)
        assert who.default == "required"


class CaseRendering:
    def test_the_usage_line(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        assert page.usage == "slumpcone thing make <name> [options]"

    def test_a_command_with_no_options(self) -> None:
        page = CommandPage("thing", "Do things.", "", (), ())
        assert page.usage == "slumpcone thing"

    def test_a_page_renders_a_table(self) -> None:
        page = next(one for one in walk(toy) if one.path == "thing make")
        text = page.render()
        assert "| option | value | what it does | default |" in text
        assert "`--size`" in text

    def test_a_page_with_no_description(self) -> None:
        page = CommandPage("thing", "", "", (), ())
        assert "_No description._" in page.render()

    def test_a_pipe_in_a_help_string_is_escaped(self) -> None:
        line = OptionLine("`--x`", "", "one | other", "")
        assert "one \\| other" in line.as_row()

    def test_the_reference_lists_the_groups(self) -> None:
        text = render_reference(toy)
        assert "- **`thing`** Do things." in text

    def test_the_reference_carries_the_commands(self) -> None:
        text = render_reference(toy)
        assert "### `thing make`" in text

    def test_the_title_can_be_chosen(self) -> None:
        assert render_reference(toy, "Toy manual").startswith("# Toy manual")

    def test_it_ends_with_one_newline(self) -> None:
        text = render_reference(toy)
        assert text.endswith("\n")
        assert not text.endswith("\n\n")


class CaseTheRealCommandLine:
    def test_it_walks_without_raising(self) -> None:
        assert list(walk(cli))

    def test_every_group_has_a_summary(self) -> None:
        missing = [one.path for one in walk(cli) if not one.summary]
        assert missing == []

    def test_the_counts_agree_with_the_walk(self) -> None:
        groups, leaves = command_count(cli)
        assert groups + leaves == len(list(walk(cli)))

    def test_there_are_a_lot_of_commands(self) -> None:
        groups, leaves = command_count(cli)
        assert groups >= 25
        assert leaves >= 150

    def test_the_reference_mentions_every_group(self) -> None:
        text = render_reference(cli)
        for page in walk(cli):
            if " " not in page.path:
                assert f"## `{page.path}`" in text

    @pytest.mark.parametrize("name", ["batch", "carbon", "crew", "dispatch", "probe"])
    def test_a_few_groups_by_name(self, name: str) -> None:
        assert f"## `{name}`" in render_reference(cli)
