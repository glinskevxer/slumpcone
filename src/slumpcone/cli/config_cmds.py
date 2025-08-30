"""Commands for the settings file.

The file only ever holds what a person would otherwise retype: which register,
which plant, who they are. Nothing in it changes what a number means, and that
is a rule rather than an accident. A setting that changed how a batch is
calculated would mean two plants running the same command on the same register
could get different concrete, and nobody would find out from the ticket.
"""

from __future__ import annotations

from pathlib import Path

import click

from slumpcone.cli.common import CliContext, handle_errors
from slumpcone.cli.output import page
from slumpcone.config import CONFIG_NAME, find_config, load_settings, render_settings


@click.group("config")
def config_group() -> None:
    """Read and write the settings file."""


@config_group.command("show")
@click.pass_obj
@handle_errors
def show_command(context: CliContext) -> None:
    """What the settings file says, and where the values actually came from."""
    settings = context.settings
    found = find_config()
    page(
        "Settings",
        [
            ("file", str(found) if found else "none found"),
            ("read from", settings.source or "built in defaults"),
            ("register in use", str(context.path)),
            ("actor in use", context.actor),
            ("plant default", settings.plant or "-"),
            ("unit system", settings.unit_system or "-"),
            ("output width", settings.width),
            ("unknown keys", ", ".join(settings.unknown_keys) or "none"),
        ],
    )
    if not settings.is_clean:
        raise click.ClickException("the settings file carries keys this build does not know")


@config_group.command("path")
@handle_errors
def path_command() -> None:
    """Where the settings file was found, if anywhere."""
    found = find_config()
    if found is None:
        raise click.ClickException(f"no {CONFIG_NAME} found in this directory or above")
    click.echo(str(found))


@config_group.command("init")
@click.option("--out", "path", default=CONFIG_NAME, help="Where to write it.")
@click.option("--force", is_flag=True, help="Write over one that is already there.")
@click.option("--plant", default=None)
@click.option("--actor", "who", default=None)
@click.pass_obj
@handle_errors
def init_command(
    context: CliContext, path: str, force: bool, plant: str | None, who: str | None
) -> None:
    """Write a starter settings file."""
    target = Path(path)
    if target.exists() and not force:
        raise click.ClickException(f"{target} is already there, pass --force to replace it")
    settings = context.settings
    text = render_settings(
        type(settings)(
            register_path=settings.register_path or str(context.path),
            plant=plant or settings.plant,
            actor=who or (None if context.actor == "unattributed" else context.actor),
            unit_system=settings.unit_system,
            width=settings.width,
            colour=settings.colour,
        )
    )
    target.write_text(text, encoding="utf-8")
    click.echo(f"wrote {target}")


@config_group.command("check")
@click.argument("path", required=False)
@handle_errors
def check_command(path: str | None) -> None:
    """Read a settings file and say whether this build understands all of it."""
    settings = load_settings(Path(path) if path else None)
    click.echo(settings.describe())
    if settings.is_clean:
        click.echo("every key is one this build knows")
        return
    for key in settings.unknown_keys:
        click.echo(f"  unknown: {key}")
    raise click.ClickException(f"{len(settings.unknown_keys)} key(s) this build does not know")
