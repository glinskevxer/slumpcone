"""Commands for technicians and the cards they hold."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.errors import NotFoundError
from slumpcone.people.certification import (
    Certification,
    CertificationError,
    Grade,
    Technician,
    TestKind,
)
from slumpcone.textout import Align, Column, heading, render_pairs, render_table


def parse_grade(raw: str) -> Grade:
    """A grade off the command line, by value or by name."""
    text = raw.strip().lower().replace("_", " ")
    for grade in Grade:
        if text in {grade.value, grade.name.lower(), grade.name.lower().replace("_", " ")}:
            return grade
    named = ", ".join(grade.value for grade in Grade)
    raise CertificationError(
        "CERTIFICATION_UNKNOWN_GRADE", f"{raw!r} is not a grade. Try one of: {named}"
    )


def parse_kind(raw: str) -> TestKind:
    """A test kind off the command line."""
    text = raw.strip().lower().replace(" ", "_")
    for kind in TestKind:
        if text == kind.value:
            return kind
    named = ", ".join(kind.value for kind in TestKind)
    raise CertificationError(
        "CERTIFICATION_UNKNOWN_TEST", f"{raw!r} is not a test. Try one of: {named}"
    )


@click.group("crew")
def crew_group() -> None:
    """Technicians, their certifications and what they may run."""


@crew_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--employer", default="")
@click.pass_obj
@handle_errors
def add_command(context: CliContext, code: str, name: str, employer: str) -> None:
    """File a technician. Keeps any cards already on record."""
    with context.register() as register:
        try:
            existing = register.people.get(code)
            cards = existing.certifications
        except NotFoundError:
            cards = ()
        person = Technician(code, name, cards, employer)
        register.people.save(person)
    click.echo(f"{person.code} {person.name}, {len(person.certifications)} card(s)")


@crew_group.command("card")
@click.argument("code")
@click.option("--grade", required=True, help='For example "field grade I".')
@click.option("--number", required=True)
@click.option("--issued", required=True, metavar="YYYY-MM-DD")
@click.option("--expires", required=True, metavar="YYYY-MM-DD")
@click.pass_obj
@handle_errors
def card_command(
    context: CliContext, code: str, grade: str, number: str, issued: str, expires: str
) -> None:
    """Add a certification to somebody already on file."""
    card = Certification(parse_grade(grade), number, parse_day(issued), parse_day(expires))
    with context.register() as register:
        person = register.people.get(code)
        register.people.save(
            Technician(
                person.code,
                person.name,
                (*person.certifications, card),
                person.employer,
            )
        )
        context.note(register, "crew.card", person.code, card.describe())
    click.echo(f"{code.strip().upper()}: {card.describe()}")


@crew_group.command("show")
@click.argument("code")
@day_option("--on")
@click.pass_obj
@handle_errors
def show_command(context: CliContext, code: str, on: date) -> None:
    """One technician, their cards and what they may run today."""
    with context.register() as register:
        person = register.people.get(code)
    click.echo(heading(f"{person.code} {person.name}"))
    allowed = sorted(str(kind) for kind in TestKind if person.may_run(kind, on))
    click.echo(
        render_pairs(
            [
                ("employer", person.employer or "-"),
                ("cards", len(person.certifications)),
                ("current", len(person.current(on))),
                ("lapsed", len(person.lapsed(on))),
                ("may run today", ", ".join(allowed) or "nothing"),
            ]
        )
    )
    click.echo("")
    click.echo(
        render_table(
            (
                Column("number"),
                Column("grade"),
                Column("issued"),
                Column("expires"),
                Column("days", Align.RIGHT),
                Column("standing"),
            ),
            [
                [
                    card.number,
                    str(card.grade),
                    card.issued_on.isoformat(),
                    card.expires_on.isoformat(),
                    card.days_left(on),
                    "current" if card.is_current(on) else "lapsed",
                ]
                for card in person.certifications
            ],
        )
    )


@crew_group.command("list")
@day_option("--on")
@click.pass_obj
@handle_errors
def list_command(context: CliContext, on: date) -> None:
    """Everybody on file."""
    with context.register() as register:
        people = register.people.all()
    click.echo(
        render_table(
            (
                Column("code"),
                Column("name"),
                Column("employer"),
                Column("current", Align.RIGHT),
                Column("lapsed", Align.RIGHT),
            ),
            [
                [
                    person.code,
                    person.name,
                    person.employer or "-",
                    len(person.current(on)),
                    len(person.lapsed(on)),
                ]
                for person in people
            ],
        )
    )
    click.echo(f"{len(people)} technician(s)")


@crew_group.command("roster")
@click.argument("test")
@day_option("--on")
@click.pass_obj
@handle_errors
def roster_command(context: CliContext, test: str, on: date) -> None:
    """Who may run one test today."""
    kind = parse_kind(test)
    with context.register() as register:
        found = register.people.may_run(kind, on)
    click.echo(heading(f"{kind}, {on.isoformat()}"))
    for person in found:
        click.echo(f"  {person.code} {person.name}")
    click.echo(f"{len(found)} certified")
    if not found:
        click.echo("nobody on file may run this test today")


@crew_group.command("gaps")
@day_option("--on")
@click.pass_obj
@handle_errors
def gaps_command(context: CliContext, on: date) -> None:
    """What nobody on file may run today."""
    with context.register() as register:
        gaps = register.people.gaps(on)
    click.echo(heading(f"Uncovered tests, {on.isoformat()}"))
    for kind in gaps:
        click.echo(f"  {kind}")
    click.echo(f"{len(gaps)} of {len(list(TestKind))} test(s) uncovered")


@crew_group.command("expiring")
@day_option("--on")
@click.option("--days", type=int, default=60, help="How far ahead to look.")
@click.option("--lapsed", "show_lapsed", is_flag=True, help="Show what has run out.")
@click.pass_obj
@handle_errors
def expiring_command(context: CliContext, on: date, days: int, show_lapsed: bool) -> None:
    """Cards running out, or cards already run out."""
    with context.register() as register:
        pairs = (
            register.people.lapsed(on)
            if show_lapsed
            else register.people.expiring(on, days=days)
        )
        names = {person.code: person.name for person in register.people.all()}
    click.echo(
        render_table(
            (
                Column("technician"),
                Column("name"),
                Column("number"),
                Column("grade"),
                Column("expires"),
                Column("days", Align.RIGHT),
            ),
            [
                [
                    code,
                    names.get(code, "-"),
                    card.number,
                    str(card.grade),
                    card.expires_on.isoformat(),
                    card.days_left(on),
                ]
                for code, card in pairs
            ],
        )
    )
    click.echo(f"{len(pairs)} card(s) {'lapsed' if show_lapsed else 'expiring'}")


@crew_group.command("drop")
@click.argument("code")
@click.pass_obj
@handle_errors
def drop_command(context: CliContext, code: str) -> None:
    """Forget a technician and their cards."""
    with context.register() as register:
        register.people.forget(code)
    click.echo(f"{code.strip().upper()} dropped")
