"""Shared pieces of the command line.

Two decisions live here. The register path comes from an option, then an
environment variable, then a file in the working directory, in that order,
because a plant runs every command against the same register all day and typing
the path each time is how people end up writing to the wrong one.

And every deliberate error is caught at the top and printed as one line. A
technician typing a mix code that does not exist should see "no mix design on
file with identity '4000P-58'", not forty lines of traceback with the answer at
the bottom.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import click

from slumpcone.errors import SlumpconeError
from slumpcone.register import Register

DEFAULT_REGISTER = "slumpcone.sqlite3"
REGISTER_ENV = "SLUMPCONE_REGISTER"

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(slots=True)
class CliContext:
    """What every command needs: where the register is, and how loud to be."""

    path: Path
    quiet: bool = False

    def register(self) -> Register:
        """Open the register, creating and migrating it if it is not there."""
        return Register.open(self.path)

    def say(self, message: str) -> None:
        """Print a progress line unless the caller asked for quiet."""
        if not self.quiet:
            click.echo(message)


def handle_errors(command: F) -> F:
    """Turn a deliberate error into one line and a non zero exit."""

    @wraps(command)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return command(*args, **kwargs)
        except SlumpconeError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def parse_day(value: str) -> date:
    """Read a date from the command line, in ISO form only."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise click.BadParameter(f"{value!r} is not a date in YYYY-MM-DD form") from exc


def parse_moment(value: str) -> datetime:
    """Read a timestamp from the command line, falling back to midnight."""
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.combine(parse_day(value), datetime.min.time())


def day_option(
    name: str = "--on", help_text: str = "The date to judge against."
) -> Callable[[F], F]:
    """A date option that defaults to today."""

    def decorate(command: F) -> F:
        return click.option(
            name,
            "on",
            default=None,
            metavar="YYYY-MM-DD",
            help=help_text,
            callback=lambda _ctx, _param, value: date.today()
            if value is None
            else parse_day(value),
        )(command)

    return decorate


def window_options(command: F) -> F:
    """A pair of options describing a window, both defaulting to today."""
    command = click.option(
        "--to",
        "end",
        default=None,
        metavar="YYYY-MM-DD",
        help="Last day of the window.",
        callback=lambda _ctx, _param, value: date.today()
        if value is None
        else parse_day(value),
    )(command)
    return click.option(
        "--from",
        "start",
        default=None,
        metavar="YYYY-MM-DD",
        help="First day of the window.",
        callback=lambda _ctx, _param, value: date.today()
        if value is None
        else parse_day(value),
    )(command)


def echo_lines(lines: Sequence[str]) -> None:
    """Print a block, skipping nothing and adding nothing."""
    for line in lines:
        click.echo(line)


def require(value: Any, message: str) -> Any:
    """Refuse a command that is missing something it needs."""
    if value is None:
        raise click.UsageError(message)
    return value
