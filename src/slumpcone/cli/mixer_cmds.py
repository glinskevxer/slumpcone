"""Commands for mixer uniformity testing.

A uniformity sample carries eight readings and the pair carries sixteen. Sixteen
command line options is not a command anybody would use, so a sample arrives as
one key=value string and the command takes two of them. The keys are the short
names off the C94 data sheet rather than the long attribute names, because the
person typing this is reading the sheet.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import click

from slumpcone.batching.uniformity import (
    Comparison,
    UniformityError,
    UniformitySample,
)
from slumpcone.cli.common import CliContext, day_option, handle_errors, window_options
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume

# The sheet's short names against what they set. Anything not in here is a typo
# and is refused rather than ignored, because a silently dropped reading gives a
# verdict that looks exactly like a real one.
SAMPLE_KEYS = {
    "label": "label",
    "uw": "unit weight, lb/ft3",
    "air": "air content, percent",
    "slump": "slump, inches",
    "retained": "coarse retained on the No. 4, percent",
    "g": "coarse aggregate specific gravity",
    "vol": "measure volume, ft3",
    "coarse": "coarse aggregate mass, lb",
    "psi": "seven day strength, optional",
}

REQUIRED_KEYS = ("label", "uw", "air", "slump", "retained", "g", "vol", "coarse")


def parse_sample(raw: str) -> UniformitySample:
    """One sample off a key=value string."""
    fields: dict[str, str] = {}
    for chunk in raw.split(","):
        if not chunk.strip():
            continue
        if "=" not in chunk:
            raise UniformityError(
                "UNIFORMITY_SAMPLE_UNREADABLE", f"cannot read {chunk.strip()!r} as key=value"
            )
        key, value = chunk.split("=", 1)
        key = key.strip().lower()
        if key not in SAMPLE_KEYS:
            raise UniformityError(
                "UNIFORMITY_SAMPLE_UNKNOWN_KEY",
                f"{key!r} is not a reading this test takes",
            )
        fields[key] = value.strip()
    missing = [key for key in REQUIRED_KEYS if key not in fields]
    if missing:
        raise UniformityError(
            "UNIFORMITY_SAMPLE_INCOMPLETE",
            f"the sample is missing {', '.join(missing)}",
        )
    try:
        return UniformitySample(
            fields["label"],
            MassPerVolume(float(fields["uw"]), "lb", "ft3"),
            Percent(float(fields["air"])),
            Quantity(float(fields["slump"]), "in"),
            Percent(float(fields["retained"])),
            float(fields["g"]),
            Quantity(float(fields["vol"]), "ft3"),
            Quantity(float(fields["coarse"]), "lb"),
            Quantity(float(fields["psi"]), "psi") if "psi" in fields else None,
        )
    except ValueError as error:
        raise UniformityError(
            "UNIFORMITY_SAMPLE_UNREADABLE", f"a reading in {raw!r} is not a number"
        ) from error


def rows_table(comparisons: Sequence[Comparison]) -> str:
    """The six comparison rows as a table."""
    return render_table(
        (
            Column("comparison"),
            Column("found", Align.RIGHT),
            Column("limit", Align.RIGHT),
            Column("basis"),
            Column("verdict"),
        ),
        [
            [
                row.name,
                f"{row.found:.2f}",
                f"{row.limit:.2f}",
                str(row.basis),
                "ok" if row.passed else "over",
            ]
            for row in comparisons
        ],
    )


@click.group("mixer")
def mixer_group() -> None:
    """Record and read mixer uniformity tests."""


@mixer_group.command("keys")
def keys_command() -> None:
    """What a sample string can carry."""
    click.echo(heading("Sample readings"))
    click.echo(
        render_table(
            (Column("key"), Column("reading"), Column("required")),
            [
                [key, meaning, "yes" if key in REQUIRED_KEYS else "no"]
                for key, meaning in SAMPLE_KEYS.items()
            ],
        )
    )


@mixer_group.command("uniformity")
@click.argument("mixer")
@day_option("--on", "The day the test was run.")
@click.option(
    "--sample",
    "samples",
    multiple=True,
    metavar="KEY=VALUE,...",
    help="One sample. Give this twice, once for each draw.",
)
@click.option("--plant", "plant_code", default="")
@click.option("--technician", default="")
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def uniformity_command(
    context: CliContext,
    mixer: str,
    on: date,
    samples: tuple[str, ...],
    plant_code: str,
    technician: str,
    notes: str,
) -> None:
    """Record a uniformity test and print the verdict."""
    if len(samples) != 2:
        raise UniformityError(
            "UNIFORMITY_NEEDS_TWO_SAMPLES",
            f"the test takes exactly two samples, {len(samples)} given",
        )
    first, second = (parse_sample(raw) for raw in samples)
    with context.register() as register:
        record = register.uniformity.save(
            mixer,
            on,
            first,
            second,
            plant_code=plant_code,
            technician=technician,
            notes=notes,
        )
    verdict = record.judge()
    click.echo(verdict.describe())
    click.echo("")
    click.echo(rows_table(verdict.comparisons))


@mixer_group.command("show")
@click.argument("mixer")
@day_option("--on")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, mixer: str, on: date) -> None:
    """Print one uniformity test."""
    with context.register() as register:
        record = register.uniformity.get(mixer, on)
    verdict = record.judge()
    click.echo(heading(f"Uniformity, {record.mixer} on {on.isoformat()}"))
    click.echo(
        render_pairs(
            [
                ("plant", record.plant_code or "-"),
                ("technician", record.technician or "-"),
                ("notes", record.notes or "-"),
                ("samples", f"{record.first.label} and {record.second.label}"),
                ("comparisons", len(verdict.comparisons)),
                ("inside the limit", verdict.passes),
                ("verdict", "uniform" if verdict.is_uniform else "not uniform"),
            ]
        )
    )
    click.echo("")
    click.echo(rows_table(verdict.comparisons))


@mixer_group.command("history")
@click.argument("mixer")
@click.pass_obj
@handle_errors
def history_command(context: CliContext, mixer: str) -> None:
    """Every uniformity test on one mixer."""
    with context.register() as register:
        records = [(record, record.judge()) for record in register.uniformity.for_mixer(mixer)]
    click.echo(
        render_table(
            (
                Column("tested"),
                Column("plant"),
                Column("passes", Align.RIGHT),
                Column("of", Align.RIGHT),
                Column("verdict"),
            ),
            [
                [
                    record.tested_on.isoformat(),
                    record.plant_code or "-",
                    verdict.passes,
                    len(verdict.comparisons),
                    "uniform" if verdict.is_uniform else "not uniform",
                ]
                for record, verdict in records
            ],
        )
    )
    click.echo(f"{len(records)} test(s)")


@mixer_group.command("list")
@window_options
@click.option("--plant", "plant_code", default=None)
@click.option("--failing", is_flag=True, help="Only the mixers that did not make five.")
@click.pass_obj
@handle_errors
def list_command(
    context: CliContext, start: date, end: date, plant_code: str | None, failing: bool
) -> None:
    """Uniformity tests in a window."""
    with context.register() as register:
        pairs = [
            (record, record.judge())
            for record in register.uniformity.between(start, end, plant_code=plant_code)
        ]
    if failing:
        pairs = [pair for pair in pairs if not pair[1].is_uniform]
    click.echo(
        render_table(
            (
                Column("mixer"),
                Column("tested"),
                Column("passes", Align.RIGHT),
                Column("verdict"),
            ),
            [
                [
                    record.mixer,
                    record.tested_on.isoformat(),
                    verdict.passes,
                    "uniform" if verdict.is_uniform else "not uniform",
                ]
                for record, verdict in pairs
            ],
        )
    )
    click.echo(f"{len(pairs)} test(s)")


@mixer_group.command("due")
@click.argument("mixers", nargs=-1)
@day_option("--on")
@click.option("--every", "every_days", type=int, default=365, help="Interval in days.")
@click.pass_obj
@handle_errors
def due_command(
    context: CliContext, mixers: tuple[str, ...], on: date, every_days: int
) -> None:
    """Which of these mixers has run out of uniformity test."""
    with context.register() as register:
        overdue = register.uniformity.due(mixers, on, every_days=every_days)
        rows = []
        for mixer in mixers:
            last = register.uniformity.latest(mixer)
            rows.append(
                [
                    mixer.strip().upper(),
                    "never" if last is None else last.tested_on.isoformat(),
                    "due" if mixer.strip().upper() in overdue else "current",
                ]
            )
    click.echo(render_table((Column("mixer"), Column("last"), Column("status")), rows))
    click.echo(f"{len(overdue)} of {len(mixers)} due")
