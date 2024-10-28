"""Commands for loading other people's files.

A run is always recorded, even a dry one, because the question an operator asks
the next morning is "did that file go in", and a load that left no trace
because it was refused is exactly the one they cannot answer.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import click

from slumpcone.cli.common import CliContext, handle_errors
from slumpcone.ingest.adapters import (
    to_break_result,
    to_delivery,
    to_fresh_tests,
    to_receipt,
)
from slumpcone.ingest.pipeline import run_ingest
from slumpcone.ingest.profiles import PROFILES, profile, validators_for
from slumpcone.ingest.result import AcceptedRow, IngestResult
from slumpcone.register import Register
from slumpcone.textout import Align, Column, heading, render_table


@click.group("import")
def import_group() -> None:
    """Load batch recorder, lab and supplier files."""


@import_group.command("profiles")
@click.pass_obj
@handle_errors
def profiles_command(context: CliContext) -> None:
    """List the mapping profiles this build ships."""
    columns = (
        Column("code"),
        Column("name"),
        Column("fields", Align.RIGHT),
        Column("required"),
    )
    rows = [
        [
            candidate.code,
            candidate.name,
            len(candidate.fields),
            ", ".join(candidate.required_names),
        ]
        for candidate in PROFILES
    ]
    click.echo(render_table(columns, rows))


def _apply(register: Register, profile_code: str, rows: tuple[AcceptedRow, ...]) -> int:
    """Turn accepted rows into records, returning how many landed."""
    landed = 0
    for row in rows:
        if profile_code == "BATCH-RECORDER":
            register.deliveries.save(to_delivery(row))
            landed += 1
        elif profile_code == "LAB-BREAKS":
            register.strength.save_break(to_break_result(row))
            landed += 1
        elif profile_code == "FIELD-TESTS":
            for test in to_fresh_tests(row):
                register.fresh.save(test)
            landed += 1
        elif profile_code == "MATERIAL-RECEIPTS":
            register.inventory.save_receipt(to_receipt(row))
            landed += 1
    return landed


def _echo_result(result: IngestResult) -> None:
    click.echo(result.describe())


@import_group.command("run")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--profile", "profile_code", required=True)
@click.option("--apply", "should_apply", is_flag=True, help="Turn the rows into records.")
@click.option("--encoding", default="utf-8")
@click.pass_obj
@handle_errors
def run_command(
    context: CliContext,
    path: Path,
    profile_code: str,
    should_apply: bool,
    encoding: str,
) -> None:
    """Read one file through one profile."""
    chosen = profile(profile_code)
    text = path.read_text(encoding=encoding)
    with context.register() as register:
        result = run_ingest(
            chosen,
            text,
            path.name,
            known_digests=register.ingest.known_digests(chosen.code),
            validators=validators_for(chosen.code),
            run_at=datetime.now(),
        )
        run_id = register.ingest.record(result)
        landed = _apply(register, chosen.code, result.accepted) if should_apply else 0
    _echo_result(result)
    click.echo(f"run {run_id}")
    if should_apply:
        click.echo(f"{landed} record(s) written")


@import_group.command("runs")
@click.option("--profile", "profile_code", required=True)
@click.pass_obj
@handle_errors
def runs_command(context: CliContext, profile_code: str) -> None:
    """List the loads made under one profile, newest first."""
    chosen = profile(profile_code)
    with context.register() as register:
        runs = register.ingest.runs_for(chosen.code)
    columns = (
        Column("run", Align.RIGHT),
        Column("at"),
        Column("source"),
        Column("accepted", Align.RIGHT),
        Column("quarantined", Align.RIGHT),
        Column("duplicate", Align.RIGHT),
    )
    rows = [
        [
            entry["id"],
            str(entry["run_at"])[:16].replace("T", " "),
            entry["source_name"],
            entry["accepted_count"],
            entry["quarantined_count"],
            entry["duplicate_count"],
        ]
        for entry in runs
    ]
    click.echo(render_table(columns, rows))


@import_group.command("quarantine")
@click.option("--profile", "profile_code", required=True)
@click.pass_obj
@handle_errors
def quarantine_command(context: CliContext, profile_code: str) -> None:
    """List every row still sitting in quarantine under one profile."""
    chosen = profile(profile_code)
    with context.register() as register:
        held = register.ingest.open_quarantine(chosen.code)
    columns = (
        Column("run", Align.RIGHT),
        Column("line", Align.RIGHT),
        Column("reasons"),
    )
    rows = [[run_id, row.line_number, "; ".join(row.reasons)] for run_id, row in held]
    click.echo(heading(f"Quarantine under {chosen.code}"))
    click.echo(render_table(columns, rows))


@import_group.command("forget")
@click.argument("run_id", type=int)
@click.pass_obj
@handle_errors
def forget_command(context: CliContext, run_id: int) -> None:
    """Drop a run and release the content hashes it claimed."""
    with context.register() as register:
        register.ingest.forget_run(run_id)
    click.echo(f"run {run_id} forgotten")
