"""The two shapes every command prints.

Reading through the command modules, almost everything that prints is one of
two things.

A **listing** is a table and then how many rows were in it. The count line
matters more than it looks: a table with no rows and a table that was never
filled look identical, and "0 tank(s)" is the difference between "nothing was
read today" and "this command is broken". Twenty three commands wrote that line
by hand and four of them worded the noun differently for the same thing.

A **page** is a heading, a block of labelled figures, and then usually a table.
Seven commands wrote the same five lines to lay one out, including the blank
line between the pairs and the table, which two of them forgot.

Neither of these is clever and that is the point. They exist so the twenty
fourth listing looks like the first without anybody checking.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import click

from slumpcone.textout import Column, heading, render_pairs, render_table


def plural(count: int, noun: str) -> str:
    """``3 tank(s)``, the way every one of these commands already said it."""
    return f"{count} {noun}(s)"


def listing(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Any]],
    noun: str,
    *,
    title: str | None = None,
) -> None:
    """A table, then how many rows it had."""
    if title is not None:
        click.echo(heading(title))
    click.echo(render_table(tuple(columns), [list(row) for row in rows]))
    click.echo(plural(len(rows), noun))


def page(
    title: str,
    pairs: Sequence[tuple[str, Any]],
    columns: Sequence[Column] | None = None,
    rows: Sequence[Sequence[Any]] | None = None,
) -> None:
    """A heading, a block of figures, and a table under it.

    The table is skipped entirely when there is nothing in it, rather than
    printed as a bare header. A header with no rows under it reads as a bug.
    """
    click.echo(heading(title))
    click.echo(render_pairs(list(pairs)))
    if not columns or not rows:
        return
    click.echo("")
    click.echo(render_table(tuple(columns), [list(row) for row in rows]))
