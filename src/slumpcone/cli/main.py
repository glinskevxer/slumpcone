"""The entry point.

One group, one register option, and every subcommand hanging off it. The groups
are registered here rather than discovering themselves, because a command that
appears in ``--help`` only when some import happened is a command nobody can
rely on.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from slumpcone import __version__
from slumpcone.cli.account_cmds import account_group
from slumpcone.cli.audit_cmds import audit_group
from slumpcone.cli.batch_cmds import batch_group
from slumpcone.cli.bleed_cmds import bleed_group
from slumpcone.cli.carbon_cmds import carbon_group
from slumpcone.cli.common import (
    ACTOR_ENV,
    DEFAULT_REGISTER,
    REGISTER_ENV,
    UNATTRIBUTED,
    CliContext,
)
from slumpcone.cli.completion import attach
from slumpcone.cli.config_cmds import config_group
from slumpcone.cli.control_cmds import control_group
from slumpcone.cli.crew_cmds import crew_group
from slumpcone.cli.delivery_cmds import delivery_group
from slumpcone.cli.demo_cmds import demo_group
from slumpcone.cli.dispatch_cmds import dispatch_group
from slumpcone.cli.export_cmds import export_group
from slumpcone.cli.field_cmds import field_group
from slumpcone.cli.hardened_cmds import beam_group, core_group
from slumpcone.cli.import_cmds import import_group
from slumpcone.cli.inventory_cmds import inventory_group
from slumpcone.cli.invoice_cmds import invoice_group
from slumpcone.cli.lab_cmds import lab_group
from slumpcone.cli.material_cmds import material_group
from slumpcone.cli.maturity_cmds import maturity_group
from slumpcone.cli.mix_cmds import mix_group
from slumpcone.cli.mixer_cmds import mixer_group
from slumpcone.cli.plant_cmds import plant_group
from slumpcone.cli.price_cmds import price_group
from slumpcone.cli.probe_cmds import probe_group
from slumpcone.cli.project_cmds import project_group
from slumpcone.cli.reclaim_cmds import reclaim_group
from slumpcone.cli.register_cmds import register_group
from slumpcone.cli.report_cmds import report_group
from slumpcone.config import Settings, load_settings
from slumpcone.errors import SlumpconeError


def _settings() -> Settings:
    """The settings file, or the defaults when it is missing or unreadable.

    A settings file that cannot be parsed must not stop somebody reading a
    report. It is a convenience, it is not the register, and the commands all
    work without one. So a broken file degrades to the defaults and the next
    ``config show`` says why.
    """
    try:
        return load_settings()
    except SlumpconeError:
        return Settings()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--register",
    "register_path",
    default=None,
    metavar="PATH",
    help=f"The register file. Defaults to ${REGISTER_ENV} or ./{DEFAULT_REGISTER}.",
)
@click.option("--quiet", "-q", is_flag=True, help="Print less.")
@click.option(
    "--actor",
    default=None,
    metavar="WHO",
    help=f"Who is running this, for the audit log. Defaults to ${ACTOR_ENV}.",
)
@click.version_option(__version__, "-V", "--version", prog_name="slumpcone")
@click.pass_context
def cli(
    ctx: click.Context,
    register_path: str | None,
    quiet: bool,
    actor: str | None,
) -> None:
    """Ready-mix concrete production, quality control and delivery compliance."""
    settings = _settings()
    chosen = (
        register_path
        or os.environ.get(REGISTER_ENV)
        or settings.register_path
        or DEFAULT_REGISTER
    )
    who = actor or os.environ.get(ACTOR_ENV) or settings.actor or UNATTRIBUTED
    ctx.obj = CliContext(
        Path(chosen),
        quiet=quiet,
        actor=who.strip() or UNATTRIBUTED,
        settings=settings,
    )
    # Said once, on stderr, so it cannot get into a report somebody is piping.
    if not settings.is_clean and not quiet:
        named = ", ".join(settings.unknown_keys)
        click.echo(
            f"warning: {settings.source} carries keys this build does not know: {named}",
            err=True,
        )


cli.add_command(config_group)
cli.add_command(register_group)
cli.add_command(material_group)
cli.add_command(plant_group)
cli.add_command(mix_group)
cli.add_command(batch_group)
cli.add_command(field_group)
cli.add_command(lab_group)
cli.add_command(delivery_group)
cli.add_command(project_group)
cli.add_command(inventory_group)
cli.add_command(import_group)
cli.add_command(report_group)
cli.add_command(price_group)
cli.add_command(export_group)
cli.add_command(audit_group)
cli.add_command(control_group)
cli.add_command(beam_group)
cli.add_command(core_group)
cli.add_command(maturity_group)
cli.add_command(account_group)
cli.add_command(invoice_group)
cli.add_command(bleed_group)
cli.add_command(mixer_group)
cli.add_command(carbon_group)
cli.add_command(dispatch_group)
cli.add_command(crew_group)
cli.add_command(reclaim_group)
cli.add_command(probe_group)
cli.add_command(demo_group)


# Give every mix, plant, material, account, technician and truck argument its
# completer in one pass, rather than at a hundred and seventy call sites.
attach(cli)


def main(argv: list[str] | None = None) -> int:
    """Run the command line and return an exit status.

    Click is run with ``standalone_mode`` off so that the caller decides what
    to do with the result, which is what makes the whole command line testable
    in process. The cost is that click then raises where it would have exited,
    and every one of those exceptions carries the code the shell was supposed
    to see. Losing them is how a usage error came back as one instead of two,
    which is the one code a script actually branches on.
    """
    try:
        cli.main(args=argv, standalone_mode=False, prog_name="slumpcone")
    except click.exceptions.Exit as exc:
        # --help and --version both come through here, having already printed.
        return int(exc.exit_code)
    except click.ClickException as exc:
        exc.show()
        return exc.exit_code
    except click.exceptions.Abort:
        click.echo("Aborted.", err=True)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.py
    sys.exit(main())
