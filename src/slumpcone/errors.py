"""The exception hierarchy.

Everything raised on purpose derives from :class:`SlumpconeError`. Callers that
want to distinguish a bad input from a broken invariant catch the subclass; the
CLI catches the base and prints the message without a traceback.
"""

from __future__ import annotations

from enum import IntEnum


class SlumpconeError(Exception):
    """Base class for every error this package raises deliberately."""


class ValidationError(SlumpconeError):
    """A value handed in from outside does not make sense.

    The offending field is carried separately from the message so a caller that
    is filling a form can point at the right box.
    """

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field

    def __str__(self) -> str:
        base = super().__str__()
        if self.field is None:
            return base
        return f"{self.field}: {base}"


class UnitError(ValidationError):
    """A quantity was combined with, or converted to, an incompatible unit."""


class NotFoundError(SlumpconeError):
    """A record was asked for by identity and is not on file."""

    def __init__(self, kind: str, identity: str) -> None:
        super().__init__(f"no {kind} on file with identity {identity!r}")
        self.kind = kind
        self.identity = identity


class ConflictError(SlumpconeError):
    """A write would collide with a record that is already on file."""

    def __init__(self, kind: str, identity: str) -> None:
        super().__init__(f"{kind} {identity!r} is already on file")
        self.kind = kind
        self.identity = identity


class RuleViolationError(SlumpconeError):
    """An operation is refused because a standing rule forbids it.

    ``code`` is stable and is what reports group by. ``detail`` is free text
    written for whoever is holding the ticket.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class ExitCode(IntEnum):
    """What the command line gives back to the shell.

    A script that batches overnight has to tell the three cases apart without
    reading English: the mixture is not on file, the mixture is on file and the
    rule refused it, and the register itself is broken. One means "it did not
    work" and tells a script nothing.

    The numbers are chosen around what already exists rather than freely. Zero
    and one are what everything expects, and two is click's own code for a
    usage error, so nothing here may claim either of those three. The rest
    start above them.
    """

    OK = 0
    REFUSED = 1
    USAGE = 2
    NOT_FOUND = 3
    CONFLICT = 4
    INVALID = 5
    STORE = 6

    def __str__(self) -> str:
        return self.name.lower().replace("_", " ")


def exit_code_for(error: Exception) -> ExitCode:
    """Which code an error should leave with.

    Ordered most specific first, because the hierarchy nests: a
    :class:`UnitError` is a :class:`ValidationError`, and a store error that
    wraps a conflict should read as a conflict rather than as a broken file.
    """
    if isinstance(error, NotFoundError):
        return ExitCode.NOT_FOUND
    if isinstance(error, ConflictError):
        return ExitCode.CONFLICT
    if isinstance(error, ValidationError):
        return ExitCode.INVALID
    if isinstance(error, RuleViolationError):
        return ExitCode.REFUSED
    if isinstance(error, SlumpconeError):
        return ExitCode.REFUSED
    return ExitCode.REFUSED
