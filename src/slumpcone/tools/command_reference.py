"""Generating the command reference out of the command line itself.

A reference kept by hand goes stale the day somebody adds an option, and the
stale part is always the option that was just added, which is the one people are
looking for. So this walks the click tree and writes the reference from it.

Two things it deliberately does not do.

It does not invent prose. Every word of description in the output is the
docstring already on the command, so the way to improve the reference is to
improve the help text, which is what a person reads at the terminal anyway.

It does not sort the groups. They come out in the order they were added to the
root command, which is roughly the order a plant uses them: set the register up,
file materials and mixtures, batch, deliver, test, report, bill. Alphabetical
would put ``account`` first and ``register`` in the middle, which is nobody's
order of operations.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import click


@dataclass(frozen=True, slots=True)
class OptionLine:
    """One option, as the reference shows it."""

    flags: str
    metavar: str
    help_text: str
    default: str

    def as_row(self) -> str:
        """A markdown table row."""
        cells = (self.flags, self.metavar or "", self.help_text, self.default)
        return "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"


@dataclass(frozen=True, slots=True)
class CommandPage:
    """One command, with everything the reference says about it."""

    path: str
    summary: str
    body: str
    arguments: tuple[str, ...]
    options: tuple[OptionLine, ...]

    @property
    def usage(self) -> str:
        """The line somebody would type."""
        parts = ["slumpcone", self.path]
        parts.extend(f"<{name}>" for name in self.arguments)
        if self.options:
            parts.append("[options]")
        return " ".join(parts)

    def render(self) -> str:
        """This command as a markdown section."""
        lines = [f"### `{self.path}`", "", self.summary or "_No description._", ""]
        if self.body:
            lines.extend([self.body, ""])
        lines.extend(["```", self.usage, "```", ""])
        if self.options:
            lines.extend(
                [
                    "| option | value | what it does | default |",
                    "| --- | --- | --- | --- |",
                ]
            )
            lines.extend(one.as_row() for one in self.options)
            lines.append("")
        return "\n".join(lines)


def _default_of(parameter: click.Parameter) -> str:
    """How a default reads in the table."""
    if parameter.required:
        return "required"
    value = parameter.default
    if value is None or value is False:
        return ""
    if value is True:
        return "on"
    return f"`{value}`"


def _options_of(command: click.Command) -> tuple[OptionLine, ...]:
    """Every option on a command, help and version left out."""
    lines: list[OptionLine] = []
    for parameter in command.params:
        if not isinstance(parameter, click.Option) or parameter.hidden:
            continue
        if parameter.name in {"help", "version"}:
            continue
        lines.append(
            OptionLine(
                ", ".join(f"`{opt}`" for opt in parameter.opts),
                parameter.metavar or "",
                parameter.help or "",
                _default_of(parameter),
            )
        )
    return tuple(lines)


def _arguments_of(command: click.Command) -> tuple[str, ...]:
    """Every positional argument, in order."""
    return tuple(
        str(parameter.name)
        for parameter in command.params
        if isinstance(parameter, click.Argument)
    )


def _split_help(command: click.Command) -> tuple[str, str]:
    """A docstring as its first line and the rest."""
    text = (command.help or "").strip()
    if not text:
        return ("", "")
    head, _, tail = text.partition("\n")
    return (head.strip(), tail.strip())


def walk(group: click.Group, prefix: str = "") -> Iterator[CommandPage]:
    """Every command under a group, depth first, in declaration order."""
    for name, command in group.commands.items():
        path = f"{prefix}{name}"
        summary, body = _split_help(command)
        yield CommandPage(path, summary, body, _arguments_of(command), _options_of(command))
        if isinstance(command, click.Group):
            yield from walk(command, f"{path} ")


def render_reference(root: click.Group, title: str = "Command reference") -> str:
    """The whole reference as markdown."""
    pages = list(walk(root))
    groups = [one for one in pages if " " not in one.path]
    lines = [f"# {title}", ""]
    lines.extend(
        [
            "Generated from the command line itself. To change a description,",
            "change the docstring on the command.",
            "",
            "## Groups",
            "",
        ]
    )
    for one in groups:
        lines.append(f"- **`{one.path}`** {one.summary}")
    lines.append("")
    for one in groups:
        lines.extend([f"## `{one.path}`", "", one.summary or "", ""])
        children = [page for page in pages if page.path.startswith(f"{one.path} ")]
        for child in children:
            lines.append(child.render())
    return "\n".join(lines).rstrip() + "\n"


def command_count(root: click.Group) -> tuple[int, int]:
    """How many groups and how many leaf commands there are."""
    pages = list(walk(root))
    groups = sum(1 for one in pages if " " not in one.path)
    return (groups, len(pages) - groups)
