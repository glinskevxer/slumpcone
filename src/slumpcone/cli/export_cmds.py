"""Commands that get things back out of the register."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from slumpcone.cli.common import CliContext, handle_errors, window_options
from slumpcone.exporting import (
    materials_to_delimited,
    mix_from_json,
    mix_to_json,
    strength_to_delimited,
    tickets_to_delimited,
)


def _write(text: str, out: Path | None) -> None:
    if out is None:
        click.echo(text, nl=False)
        return
    out.write_text(text, encoding="utf-8")
    click.echo(f"{len(text.splitlines())} line(s) written to {out}")


@click.group("export")
def export_group() -> None:
    """Write records out as delimited text or as a document."""


@export_group.command("tickets")
@window_options
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--delimiter", default=",")
@click.pass_obj
@handle_errors
def tickets_command(
    context: CliContext, start: date, end: date, out: Path | None, delimiter: str
) -> None:
    """Delivery tickets over a window."""
    with context.register() as register:
        tickets = register.batches.between(start, end)
    _write(tickets_to_delimited(list(tickets), delimiter=delimiter), out)


@export_group.command("strength")
@click.argument("mix_code")
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--delimiter", default=",")
@click.pass_obj
@handle_errors
def strength_command(
    context: CliContext, mix_code: str, out: Path | None, delimiter: str
) -> None:
    """Strength tests for one mixture."""
    with context.register() as register:
        tests = register.strength.tests_for_mix(mix_code)
    _write(strength_to_delimited(list(tests), delimiter=delimiter), out)


@export_group.command("materials")
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--delimiter", default=",")
@click.pass_obj
@handle_errors
def materials_command(context: CliContext, out: Path | None, delimiter: str) -> None:
    """The material catalogue."""
    with context.register() as register:
        materials = register.materials.all()
    _write(materials_to_delimited(list(materials), delimiter=delimiter), out)


@export_group.command("mix")
@click.argument("mix_code")
@click.option("--revision", type=int, default=None)
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_obj
@handle_errors
def mix_command(
    context: CliContext, mix_code: str, revision: int | None, out: Path | None
) -> None:
    """One mix design as an exchange document."""
    with context.register() as register:
        design = (
            register.mixes.latest(mix_code)
            if revision is None
            else register.mixes.get(mix_code, revision)
        )
    _write(mix_to_json(design) + "\n", out)


@export_group.command("load-mix")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--revision", type=int, default=None, help="File it as this revision.")
@click.pass_obj
@handle_errors
def load_mix_command(context: CliContext, path: Path, revision: int | None) -> None:
    """Read an exchange document back into the register."""
    design = mix_from_json(path.read_text(encoding="utf-8"))
    if revision is not None:
        from dataclasses import replace

        design = replace(design, revision=revision)
    with context.register() as register:
        register.mixes.save(design)
    click.echo(design.describe())
