"""Commands for jobs, the classes they specify, submittals and orders."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.project.order import Order, OrderStatus, progress_of
from slumpcone.project.project import Project, SpecifiedClass
from slumpcone.project.submittal import (
    Submittal,
    SubmittalBasis,
    check_against_class,
)
from slumpcone.spec.exposure import ExposureSet
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.system import UnitSystem


@click.group("project")
def project_group() -> None:
    """File jobs, classes, submittals and orders."""


@project_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option("--owner", default=None)
@click.option("--specifier", default=None)
@click.option("--system", default="customary")
@click.option("--start", "started_on", default=None, metavar="YYYY-MM-DD")
@click.option("--finish", "finished_on", default=None, metavar="YYYY-MM-DD")
@click.pass_obj
@handle_errors
def add_command(
    context: CliContext,
    code: str,
    name: str,
    owner: str | None,
    specifier: str | None,
    system: str,
    started_on: str | None,
    finished_on: str | None,
) -> None:
    """File a job, keeping any classes already on it."""
    with context.register() as register:
        try:
            classes = register.projects.get(code).classes
        except Exception:
            classes = ()
        project = Project(
            code=code,
            name=name,
            classes=classes,
            owner=owner,
            specifier=specifier,
            unit_system=UnitSystem.parse(system),
            started_on=None if started_on is None else parse_day(started_on),
            finished_on=None if finished_on is None else parse_day(finished_on),
        )
        register.projects.save(project)
    click.echo(project.describe())


@project_group.command("class")
@click.argument("project_code")
@click.argument("code")
@click.option("--strength", required=True, help='For example "4000 psi".')
@click.option("--age", type=int, default=28)
@click.option("--exposure", default="")
@click.option("--max-wcm", type=float, default=None)
@click.option("--min-cementitious", default=None)
@click.option("--nms", default=None)
@click.option("--description", default="")
@click.pass_obj
@handle_errors
def class_command(
    context: CliContext,
    project_code: str,
    code: str,
    strength: str,
    age: int,
    exposure: str,
    max_wcm: float | None,
    min_cementitious: str | None,
    nms: str | None,
    description: str,
) -> None:
    """Add or replace a class of concrete on a job."""
    entry = SpecifiedClass(
        code=code,
        specified_strength=Quantity.parse(strength),
        test_age_days=age,
        exposure=ExposureSet.parse(exposure) if exposure else ExposureSet(),
        max_water_cementitious=max_wcm,
        min_cementitious=None if min_cementitious is None else Quantity.parse(min_cementitious),
        nominal_max_size=None if nms is None else Quantity.parse(nms),
        description=description,
    )
    with context.register() as register:
        project = register.projects.get(project_code)
        kept = tuple(item for item in project.classes if item.code != entry.code)
        register.projects.save(replace(project, classes=(*kept, entry)))
    click.echo(entry.describe())


@project_group.command("list")
@day_option()
@click.pass_obj
@handle_errors
def list_command(context: CliContext, on: date) -> None:
    """List the jobs and whether they are open."""
    with context.register() as register:
        projects = register.projects.all()
    columns = (
        Column("code"),
        Column("name"),
        Column("owner"),
        Column("classes", Align.RIGHT),
        Column("open"),
    )
    rows = [
        [
            project.code,
            project.name,
            project.owner or "-",
            len(project.classes),
            "yes" if project.is_open(on) else "no",
        ]
        for project in projects
    ]
    click.echo(render_table(columns, rows))


@project_group.command("show")
@click.argument("code")
@day_option()
@click.pass_obj
@handle_errors
def show_command(context: CliContext, code: str, on: date) -> None:
    """Show a job, its classes and its submittals."""
    with context.register() as register:
        project = register.projects.get(code)
        submittals = register.projects.submittals_for(project.code)
    click.echo(heading(project.describe()))
    click.echo(
        render_pairs(
            [
                ("owner", project.owner or "-"),
                ("specifier", project.specifier or "-"),
                (
                    "started",
                    "-" if project.started_on is None else project.started_on.isoformat(),
                ),
                (
                    "finished",
                    "-" if project.finished_on is None else project.finished_on.isoformat(),
                ),
                ("open", "yes" if project.is_open(on) else "no"),
            ]
        )
    )
    if project.classes:
        click.echo("")
        for entry in project.classes:
            click.echo(entry.describe())
    if submittals:
        click.echo("")
        click.echo(heading("Submittals", underline="-"))
        for submittal in submittals:
            click.echo(submittal.describe(on))


@project_group.command("submit")
@click.argument("reference")
@click.option("--project", "project_code", required=True)
@click.option("--class", "class_code", required=True)
@click.option("--mix", "mix_code", required=True)
@click.option("--revision", type=int, default=1)
@click.option("--on", "submitted_on", required=True, metavar="YYYY-MM-DD")
@click.option("--basis", default="trial_batch")
@click.option("--required-average", default=None, help='For example "5200 psi".')
@click.pass_obj
@handle_errors
def submit_command(
    context: CliContext,
    reference: str,
    project_code: str,
    class_code: str,
    mix_code: str,
    revision: int,
    submitted_on: str,
    basis: str,
    required_average: str | None,
) -> None:
    """Submit a mixture to a class, checking it satisfies the class first."""
    submittal = Submittal(
        reference=reference,
        project_code=project_code,
        class_code=class_code,
        mix_code=mix_code,
        mix_revision=revision,
        submitted_on=parse_day(submitted_on),
        basis=SubmittalBasis.parse(basis),
        required_average=None if required_average is None else Quantity.parse(required_average),
    )
    with context.register() as register:
        project = register.projects.get(project_code)
        specified = project.specified_class(class_code)
        design = register.mixes.get(mix_code, revision)
        findings = check_against_class(design, specified)
        register.projects.save_submittal(submittal)
    click.echo(submittal.describe())
    for finding in findings:
        click.echo(f"  {finding}")


@project_group.command("approve")
@click.argument("reference")
@click.option("--on", "decided_on", required=True, metavar="YYYY-MM-DD")
@click.option("--reviewer", default=None)
@click.option("--days", type=int, default=365)
@click.option("--reject", is_flag=True, help="Reject instead of approving.")
@click.option("--comments", default="")
@click.pass_obj
@handle_errors
def approve_command(
    context: CliContext,
    reference: str,
    decided_on: str,
    reviewer: str | None,
    days: int,
    reject: bool,
    comments: str,
) -> None:
    """Approve or reject a submittal."""
    when = parse_day(decided_on)
    with context.register() as register:
        submittal = register.projects.submittal(reference)
        decided = (
            submittal.reject(when, reviewer=reviewer, comments=comments)
            if reject
            else submittal.approve(when, reviewer=reviewer, days=days, comments=comments)
        )
        register.projects.save_submittal(decided)
    click.echo(decided.describe(when))


@project_group.command("approved")
@click.argument("project_code")
@click.argument("class_code")
@day_option()
@click.pass_obj
@handle_errors
def approved_command(context: CliContext, project_code: str, class_code: str, on: date) -> None:
    """Which mixtures a class may be batched from."""
    with context.register() as register:
        submittals = register.projects.approved_mixes(project_code, class_code, on)
    columns = (Column("reference"), Column("mix"), Column("expires"))
    rows = [
        [
            submittal.reference,
            submittal.mix_identity,
            "-" if submittal.expires_on is None else submittal.expires_on.isoformat(),
        ]
        for submittal in submittals
    ]
    click.echo(render_table(columns, rows))


@project_group.command("order")
@click.argument("number")
@click.option("--project", "project_code", required=True)
@click.option("--class", "class_code", required=True)
@click.option("--volume", required=True, help='For example "60 yd3".')
@click.option("--on", "placement_date", required=True, metavar="YYYY-MM-DD")
@click.option("--mix", "mix_code", default=None)
@click.option("--rate", default=None, help='Delivery rate, "24 yd3".')
@click.option("--placement", default=None)
@click.pass_obj
@handle_errors
def order_command(
    context: CliContext,
    number: str,
    project_code: str,
    class_code: str,
    volume: str,
    placement_date: str,
    mix_code: str | None,
    rate: str | None,
    placement: str | None,
) -> None:
    """Book an order against a class."""
    order = Order(
        number=number,
        project_code=project_code,
        class_code=class_code,
        volume=Quantity.parse(volume),
        placement_date=parse_day(placement_date),
        mix_code=mix_code,
        rate=None if rate is None else Quantity.parse(rate),
        placement=placement,
        status=OrderStatus.BOOKED,
    )
    with context.register() as register:
        register.orders.save(order)
    click.echo(order.describe())


@project_group.command("board")
@day_option()
@click.pass_obj
@handle_errors
def board_command(context: CliContext, on: date) -> None:
    """The dispatch board for one day."""
    with context.register() as register:
        orders = register.orders.on_date(on)
        rows: list[list[object]] = []
        for order in orders:
            tickets = [
                ticket
                for ticket in register.batches.between(on, on)
                if order.placement is not None and ticket.project == order.placement
            ]
            progress = progress_of(order, [ticket.volume for ticket in tickets])
            rows.append(
                [
                    order.number,
                    f"{order.project_code}/{order.class_code}",
                    order.mix_code or "-",
                    order.volume.format(1),
                    progress.delivered.format(1),
                    progress.completion.format(0),
                    str(order.status),
                ]
            )
    columns = (
        Column("order"),
        Column("job"),
        Column("mix"),
        Column("ordered", Align.RIGHT),
        Column("delivered", Align.RIGHT),
        Column("done", Align.RIGHT),
        Column("status"),
    )
    click.echo(heading(f"Dispatch board, {on.isoformat()}"))
    click.echo(render_table(columns, rows))
