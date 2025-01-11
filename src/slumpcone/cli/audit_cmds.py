"""Commands for the audit log."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, handle_errors, window_options
from slumpcone.textout import Align, Column, heading, render_pairs, render_table


@click.group("audit")
def audit_group() -> None:
    """Record and read the audit log."""


@audit_group.command("record")
@click.argument("action")
@click.argument("subject")
@click.option("--actor", required=True)
@click.option("--detail", default="")
@click.pass_obj
@handle_errors
def record_command(
    context: CliContext, action: str, subject: str, actor: str, detail: str
) -> None:
    """Append one event to the log."""
    with context.register() as register:
        event = register.audit.record(actor, action, subject, detail)
    click.echo(event.describe())


@audit_group.command("log")
@window_options
@click.option("--actor", default=None)
@click.option("--subject", default=None)
@click.pass_obj
@handle_errors
def log_command(
    context: CliContext, start: date, end: date, actor: str | None, subject: str | None
) -> None:
    """Read the log, filtered by window, actor or subject."""
    with context.register() as register:
        if subject is not None:
            events = register.audit.for_subject(subject)
        elif actor is not None:
            events = register.audit.by_actor(actor)
        else:
            events = register.audit.between(start, end)
    columns = (
        Column("id", Align.RIGHT),
        Column("at"),
        Column("actor"),
        Column("action"),
        Column("subject"),
        Column("detail"),
    )
    rows = [
        [
            event.identifier,
            event.at.isoformat(sep=" ", timespec="seconds"),
            event.actor,
            event.action,
            event.subject,
            event.detail,
        ]
        for event in events
    ]
    click.echo(render_table(columns, rows))


@audit_group.command("verify")
@click.pass_obj
@handle_errors
def verify_command(context: CliContext) -> None:
    """Check the chain has not been edited in the middle."""
    with context.register() as register:
        broken = register.audit.verify()
        count = register.audit.count()
    click.echo(heading("Audit chain"))
    click.echo(
        render_pairs(
            [
                ("events", count),
                ("intact", "yes" if not broken else "no"),
            ]
        )
    )
    if broken:
        click.echo(f"first break at event {broken[0]}")
        raise click.ClickException(f"{len(broken)} event(s) do not follow the chain")
