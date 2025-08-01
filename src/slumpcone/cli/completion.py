"""Tab completion that reads the register.

Completing a subcommand name is something click does for free. Completing a mix
code is not, and it is the one that matters: a plant has forty mixtures with
names like 4000P-57 and 4000P-67 and nobody remembers which is which. Getting
that wrong is not a typo that fails loudly either, because both exist.

So these completers read the register the command would have used. That means a
completer can be asked to run when the register is missing, locked, on a schema
older than this build, or a directory somebody typed by accident. None of that
is an error worth reporting: a shell completing a word is not a place to raise.
Every completer here swallows everything and offers nothing, because a shell
that prints a traceback where a completion should have been is worse than one
that offers nothing.

The register path is worked out the same way the commands work it out, and it
comes from the partly typed command line rather than from a fresh default, so
completing after ``--register other.sqlite3`` completes against that register.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import click
from click.shell_completion import CompletionItem

from slumpcone.cli.common import DEFAULT_REGISTER, REGISTER_ENV
from slumpcone.register import Register


def register_path(ctx: click.Context | None) -> Path:
    """Where the register is, as far as the half typed command line knows."""
    chosen: str | None = None
    cursor = ctx
    while cursor is not None and chosen is None:
        value = cursor.params.get("register_path")
        if isinstance(value, str) and value:
            chosen = value
        cursor = cursor.parent
    return Path(chosen or os.environ.get(REGISTER_ENV) or DEFAULT_REGISTER)


def _codes(ctx: click.Context | None, read: Callable[[Register], Iterable[str]]) -> list[str]:
    """Run a read against the register, or give nothing back.

    Everything is caught. A completer is not a command and has nowhere to
    report to.
    """
    path = register_path(ctx)
    if not path.exists():
        return []
    try:
        with Register.open(path) as register:
            return sorted(set(read(register)))
    except Exception:  # noqa: BLE001 - a completer never raises
        return []


def _completer(
    read: Callable[[Register], Iterable[str]],
) -> Callable[[click.Context, click.Parameter, str], list[CompletionItem]]:
    """Turn a register read into a click completer."""

    def complete(
        ctx: click.Context, param: click.Parameter, incomplete: str
    ) -> list[CompletionItem]:
        wanted = incomplete.strip().upper()
        return [
            CompletionItem(code)
            for code in _codes(ctx, read)
            if code.upper().startswith(wanted)
        ]

    return complete


def _mix_codes(register: Register) -> Iterable[str]:
    return register.mixes.codes()


def _plant_codes(register: Register) -> Iterable[str]:
    return [plant.code for plant in register.plants.all()]


def _material_codes(register: Register) -> Iterable[str]:
    return [material.code for material in register.materials.all()]


def _account_codes(register: Register) -> Iterable[str]:
    return [account.code for account in register.accounts.all()]


def _technician_codes(register: Register) -> Iterable[str]:
    return [person.code for person in register.people.all()]


def _truck_codes(register: Register) -> Iterable[str]:
    return [truck.code for truck in register.deliveries.trucks()]


complete_mix = _completer(_mix_codes)
complete_plant = _completer(_plant_codes)
complete_material = _completer(_material_codes)
complete_account = _completer(_account_codes)
complete_technician = _completer(_technician_codes)
complete_truck = _completer(_truck_codes)

# Which completer belongs to which parameter name. Wiring by name rather than at
# every call site means a new command that calls its argument ``mix_code`` gets
# completion without anybody remembering to ask for it.
BY_PARAMETER: dict[str, Any] = {
    "mix_code": complete_mix,
    "plant_code": complete_plant,
    "material_code": complete_material,
    "account_code": complete_account,
    "technician_code": complete_technician,
    "truck_code": complete_truck,
}


def attach(group: click.Group) -> int:
    """Give every parameter with a known name its completer, and say how many.

    Called once on the root command. Walking the tree is cheaper than touching
    a hundred and seventy commands, and it cannot go stale.
    """
    attached = 0
    for command in group.commands.values():
        if isinstance(command, click.Group):
            attached += attach(command)
            continue
        for parameter in command.params:
            completer = BY_PARAMETER.get(str(parameter.name))
            if completer is None or parameter._custom_shell_complete is not None:
                continue
            parameter._custom_shell_complete = completer
            attached += 1
    return attached
