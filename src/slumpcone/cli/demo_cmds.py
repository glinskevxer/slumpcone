"""Commands that fill a register with the worked example."""

from __future__ import annotations

import click

from slumpcone.cli.common import CliContext, handle_errors
from slumpcone.demo import DEMO_DAY, DEMO_MIX, DEMO_PLANT, DEMO_PROJECT, seed
from slumpcone.textout import heading, render_pairs


@click.group("demo")
def demo_group() -> None:
    """Fill a register with a worked example."""


@demo_group.command("seed")
@click.option("--force", is_flag=True, help="Seed even if the register has rows in it.")
@click.pass_obj
@handle_errors
def seed_command(context: CliContext, force: bool) -> None:
    """File one plant, one mixture and one day's work."""
    with context.register() as register:
        health = register.health()
        if not health.is_empty and not force:
            raise click.ClickException(
                f"{health.path} already holds {health.total_rows} rows; "
                "seed an empty register or pass --force"
            )
        counts = seed(register)
    click.echo(heading("Seeded"))
    click.echo(render_pairs(list(counts.items())))
    click.echo("")
    click.echo(
        render_pairs(
            [
                ("plant", DEMO_PLANT),
                ("mix", DEMO_MIX),
                ("project", DEMO_PROJECT),
                ("day", DEMO_DAY.isoformat()),
            ]
        )
    )


@demo_group.command("tour")
@click.pass_obj
@handle_errors
def tour_command(context: CliContext) -> None:
    """Print the commands worth running against a seeded register."""
    day = DEMO_DAY.isoformat()
    click.echo(heading("Worth running next"))
    for line in (
        f"slumpcone plant show {DEMO_PLANT} --on {day}",
        f"slumpcone mix show {DEMO_MIX}",
        f"slumpcone mix check {DEMO_MIX}",
        f"slumpcone batch audit --from {day} --to {day}",
        "slumpcone field judge 881206",
        f"slumpcone lab strength {DEMO_MIX} --specified 4000 psi",
        f"slumpcone report production --from {day} --to {day}",
        f"slumpcone report nonconformance --from {day} --to {day}",
        f"slumpcone report yield {DEMO_MIX} --from {day} --to {day}",
        f"slumpcone report compliance --on {day} --within 120",
    ):
        click.echo(f"  {line}")
