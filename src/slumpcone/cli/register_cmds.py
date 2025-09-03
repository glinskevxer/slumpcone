"""Commands for the register file itself."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors
from slumpcone.cli.output import listing, page
from slumpcone.doctor import Level, examine
from slumpcone.store.maintenance import (
    back_up,
    backups_in,
    integrity,
    prune_backups,
    restore,
    space,
    timestamped_backup,
    vacuum,
)
from slumpcone.store.timing import run_all, unclean
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.versions import collect


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


@register_group.command("verify")
@click.pass_obj
@handle_errors
def verify_command(context: CliContext) -> None:
    """Check the pages and the references, which are two different questions."""
    with context.register() as register:
        report = integrity(register.database)
        room = space(register.database)
    click.echo(report.describe())
    click.echo(
        render_pairs(
            [
                ("pages", "consistent" if report.pages_ok else "problems found"),
                ("references", "all resolve" if report.keys_ok else "orphans found"),
                ("size", room.describe()),
                (
                    "vacuum",
                    "worth doing" if room.is_worth_vacuuming else "not worth doing yet",
                ),
            ]
        )
    )
    for line in report.page_problems:
        click.echo(f"  page: {line}")
    for line in report.orphan_rows:
        click.echo(f"  reference: {line}")
    if not report.is_sound:
        raise click.ClickException("the register did not pass its checks")


@register_group.command("backup")
@click.argument("destination", required=False)
@click.option("--into", "folder", default=None, help="A folder to name the file in.")
@click.option("--stem", default="register", help="What to call it, before the stamp.")
@click.pass_obj
@handle_errors
def backup_command(
    context: CliContext, destination: str | None, folder: str | None, stem: str
) -> None:
    """Take a consistent snapshot, even while the plant is batching."""
    if (destination is None) == (folder is None):
        raise click.UsageError("give a destination file or --into a folder, not both")
    with context.register() as register:
        made = (
            back_up(register.database, destination)
            if destination is not None
            else timestamped_backup(register.database, folder or ".", stem=stem)
        )
    click.echo(f"backed up to {made} ({made.stat().st_size / 1024:.0f} KiB)")


@register_group.command("restore")
@click.argument("backup")
@click.argument("destination")
@click.option("--force", is_flag=True, help="Write over a register that is already there.")
@handle_errors
def restore_command(backup: str, destination: str, force: bool) -> None:
    """Put a backup back, after checking it."""
    put = restore(backup, destination, force=force)
    click.echo(f"restored {backup} to {put}")


@register_group.command("backups")
@click.argument("folder")
@click.pass_obj
@handle_errors
def backups_command(context: CliContext, folder: str) -> None:
    """Every backup in a folder."""
    found = backups_in(folder)
    listing(
        (Column("file"), Column("KiB", Align.RIGHT)),
        [[path.name, f"{path.stat().st_size / 1024:.0f}"] for path in found],
        "backup",
    )


@register_group.command("prune")
@click.argument("folder")
@click.option("--keep", type=int, default=7, help="How many to keep.")
@click.option("--dry-run", is_flag=True, help="Say what would go, delete nothing.")
@handle_errors
def prune_command(folder: str, keep: int, dry_run: bool) -> None:
    """Delete all but the newest backups."""
    if dry_run:
        if keep < 1:
            raise click.ClickException("a prune has to keep at least one backup")
        found = backups_in(folder)
        doomed = found[: max(0, len(found) - keep)]
        for path in doomed:
            click.echo(f"  would delete {path.name}")
        click.echo(f"{len(doomed)} of {len(found)} would go")
        return
    gone = prune_backups(folder, keep)
    for path in gone:
        click.echo(f"  deleted {path.name}")
    click.echo(f"{len(gone)} deleted, {len(backups_in(folder))} kept")


@register_group.command("vacuum")
@click.option(
    "--minimum",
    type=float,
    default=0.0,
    help="Refuse unless this share of the file is free, 0 to 1.",
)
@click.pass_obj
@handle_errors
def vacuum_command(context: CliContext, minimum: float) -> None:
    """Rewrite the file to reclaim free pages."""
    with context.register() as register:
        before = vacuum(register.database, minimum_free_share=minimum)
        after = space(register.database)
    reclaimed = (before.total_bytes - after.total_bytes) / 1024
    click.echo(f"before: {before.describe()}")
    click.echo(f"after:  {after.describe()}")
    click.echo(f"{reclaimed:.0f} KiB reclaimed")


@register_group.command("plans")
@click.option(
    "--all", "show_all", is_flag=True, help="Show every probe, not just the bad ones."
)
@click.pass_obj
@handle_errors
def plans_command(context: CliContext, show_all: bool) -> None:
    """Check that the queries the reports run still use an index.

    Timings are printed and never judged. What is judged is whether SQLite
    planned to read a table whole, which is a property of the schema rather
    than of this machine, and which will still be true on the plant's.
    """
    with context.register() as register:
        readings = run_all(register.database)
    bad = unclean(readings)
    shown = readings if show_all else bad
    click.echo(heading("Query plans"))
    click.echo(
        render_table(
            (
                Column("query"),
                Column("ms", Align.RIGHT),
                Column("rows", Align.RIGHT),
                Column("searches"),
                Column("scans"),
            ),
            [
                [
                    one.name,
                    f"{one.milliseconds:.2f}",
                    one.rows,
                    ", ".join(one.searched) or "-",
                    ", ".join(one.scanned) or "-",
                ]
                for one in shown
            ],
        )
    )
    click.echo(f"{len(readings) - len(bad)} of {len(readings)} probe(s) use an index")
    if bad:
        raise click.ClickException(
            f"{len(bad)} quer(y/ies) read a table whole: " + ", ".join(one.name for one in bad)
        )


@register_group.command("reference")
@click.option("--out", "path", default=None, help="Write to a file instead of the screen.")
@click.pass_obj
@handle_errors
def reference_command(context: CliContext, path: str | None) -> None:
    """Print the command reference, generated from the commands themselves."""
    from slumpcone.cli.main import cli as root
    from slumpcone.tools.command_reference import command_count, render_reference

    text = render_reference(root)
    groups, leaves = command_count(root)
    if path is None:
        click.echo(text)
        return
    Path(path).write_text(text, encoding="utf-8")
    click.echo(f"wrote {path}: {groups} group(s), {leaves} command(s)")


@register_group.command("versions")
@click.option("--one-line", is_flag=True, help="Print one line, for a log.")
@click.pass_obj
@handle_errors
def versions_command(context: CliContext, one_line: bool) -> None:
    """Everything worth pasting into a bug report."""
    found = collect(context.path)
    if one_line:
        click.echo(found.describe())
        return
    page("Versions", found.as_pairs())
    if found.register_is_current is False:
        raise click.ClickException(
            "the register and this build are not at the same schema version"
        )


@register_group.command("doctor")
@day_option("--on")
@click.option("--all", "show_all", is_flag=True, help="Show notes as well.")
@click.pass_obj
@handle_errors
def doctor_command(context: CliContext, on: date, show_all: bool) -> None:
    """Run every check there is and say what stops the plant working.

    Nothing here has an opinion of its own. Every finding comes from a rule that
    already refuses work somewhere else, so this and the command that refused
    cannot disagree.
    """
    with context.register() as register:
        report = examine(register, on)
    click.echo(heading(f"Doctor, {on.isoformat()}"))
    click.echo(report.describe())
    shown = [one for one in report.findings if show_all or one.level is not Level.NOTE]
    if shown:
        click.echo("")
        for one in shown:
            click.echo(f"  {one.describe()}")
    if not report.is_well:
        raise click.ClickException(
            f"{len(report.failures)} failure(s) stop work until they are dealt with"
        )
