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

from slumpcone.errors import ExitCode, SlumpconeError, exit_code_for
from slumpcone.register import Register

DEFAULT_REGISTER = "slumpcone.sqlite3"
REGISTER_ENV = "SLUMPCONE_REGISTER"
ACTOR_ENV = "SLUMPCONE_ACTOR"

# What the log says when nobody said who they were. Deliberately a word nobody
# would type as a name, so a log full of these is obviously a log nobody has
# configured rather than a log full of somebody called "unknown".
UNATTRIBUTED = "unattributed"

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(slots=True)
class CliContext:
    """What every command needs: where the register is, and how loud to be."""

    path: Path
    quiet: bool = False
    actor: str = UNATTRIBUTED

    def register(self) -> Register:
        """Open the register, creating and migrating it if it is not there."""
        return Register.open(self.path)

    def note(self, register: Register, action: str, subject: str, detail: str = "") -> None:
        """Append what just happened to the audit log.

        Called after the write, never before, so the log does not carry things
        that were refused. A failure to write the log is deliberately not caught
        here: a plant that cannot record what it did should stop rather than
        carry on quietly unlogged.
        """
        register.audit.record(self.actor, action, subject, detail)

    def say(self, message: str) -> None:
        """Print a progress line unless the caller asked for quiet."""
        if not self.quiet:
            click.echo(message)


class Refused(click.ClickException):
    """A deliberate error, carrying the exit code the shell should see."""

    def __init__(self, message: str, code: ExitCode) -> None:
        super().__init__(message)
        self.exit_code = int(code)
        self.reason = code


def handle_errors(command: F) -> F:
    """Turn a deliberate error into one line and the right exit code.

    The code is worked out from the exception type rather than written at the
    raise site, so a new error class gets a sensible code without anybody
    remembering, and a script that branches on "not on file" keeps working when
    a command starts raising it from somewhere new.
    """

    @wraps(command)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return command(*args, **kwargs)
        except SlumpconeError as exc:
            raise Refused(str(exc), exit_code_for(exc)) from exc

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
