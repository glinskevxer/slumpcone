"""Commands for the register file itself."""

from __future__ import annotations

import click

from slumpcone.cli.common import CliContext, handle_errors
from slumpcone.textout import Align, Column, heading, render_pairs, render_table


@click.group("register")
def register_group() -> None:
    """Create and inspect the register file."""


@register_group.command("init")
@click.pass_obj
@handle_errors
def init_command(context: CliContext) -> None:
    """Create the register and bring it to the current schema."""
    with context.register() as register:
        health = register.health()
    click.echo(f"register at {health.path}, schema version {health.schema_version}")


@register_group.command("check")
@click.pass_obj
@handle_errors
def check_command(context: CliContext) -> None:
    """Verify the schema is the one this build expects."""
    with context.register() as register:
        health = register.health()
    if not health.is_current:
        raise click.ClickException(
            f"register is at schema {health.schema_version} and this build expects "
            f"{health.expected_version}"
        )
    click.echo(f"schema {health.schema_version} is current")


@register_group.command("info")
@click.pass_obj
@handle_errors
def info_command(context: CliContext) -> None:
    """Show the schema version and what is on file."""
    with context.register() as register:
        health = register.health()
    click.echo(heading("Register"))
    click.echo(
        render_pairs(
            [
                ("path", health.path),
                ("schema", health.schema_version),
                ("expected", health.expected_version),
                ("rows", health.total_rows),
            ]
        )
    )
    click.echo("")
    columns = (Column("table"), Column("rows", Align.RIGHT))
    rows = [[table, count] for table, count in health.counts.items()]
    click.echo(render_table(columns, rows))
