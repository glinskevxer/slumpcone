"""Commands for the material catalogue and its paper."""

from __future__ import annotations

from datetime import date

import click

from slumpcone.cli.common import CliContext, day_option, handle_errors, parse_day
from slumpcone.materials.catalog import required_certificates
from slumpcone.materials.certification import Certificate, CertificateKind
from slumpcone.materials.kinds import (
    AdmixtureType,
    CementType,
    MaterialClass,
    ScmKind,
    WaterSource,
)
from slumpcone.materials.spec import Material
from slumpcone.percent import Percent
from slumpcone.textout import Align, Column, heading, render_pairs, render_table
from slumpcone.units.quantity import Quantity
from slumpcone.units.rate import MassPerVolume


@click.group("material")
def material_group() -> None:
    """File materials and their certificates."""


@material_group.command("add")
@click.argument("code")
@click.argument("name")
@click.option(
    "--class", "material_class", required=True, help="cement, scm, coarse_aggregate..."
)
@click.option("--supplier", default=None)
@click.option("--source", default=None)
@click.option("--sg", "specific_gravity", type=float, default=None, help="Specific gravity.")
@click.option("--absorption", type=float, default=None, help="Absorption, percent.")
@click.option("--fm", "fineness_modulus", type=float, default=None)
@click.option("--nms", default=None, help='Nominal maximum size, for example "1 in".')
@click.option("--dry-rodded", default=None, help='For example "101.5 lb/ft3".')
@click.option("--cement-type", default=None)
@click.option("--scm-kind", default=None)
@click.option("--admixture-type", default=None)
@click.option("--solids", type=float, default=None, help="Solids content, percent.")
@click.option("--water-source", default=None)
@click.option("--notes", default="")
@click.pass_obj
@handle_errors
def add_command(
    context: CliContext,
    code: str,
    name: str,
    material_class: str,
    supplier: str | None,
    source: str | None,
    specific_gravity: float | None,
    absorption: float | None,
    fineness_modulus: float | None,
    nms: str | None,
    dry_rodded: str | None,
    cement_type: str | None,
    scm_kind: str | None,
    admixture_type: str | None,
    solids: float | None,
    water_source: str | None,
    notes: str,
) -> None:
    """File a material the plant can batch."""
    material = Material(
        code=code,
        name=name,
        material_class=MaterialClass.parse(material_class),
        supplier=supplier,
        source=source,
        specific_gravity=specific_gravity,
        absorption=None if absorption is None else Percent(absorption),
        fineness_modulus=fineness_modulus,
        nominal_max_size=None if nms is None else Quantity.parse(nms),
        dry_rodded_unit_weight=None if dry_rodded is None else MassPerVolume.parse(dry_rodded),
        cement_type=None if cement_type is None else CementType.parse(cement_type),
        scm_kind=None if scm_kind is None else ScmKind.parse(scm_kind),
        admixture_type=None if admixture_type is None else AdmixtureType.parse(admixture_type),
        solids_content=None if solids is None else Percent(solids),
        water_source=None if water_source is None else WaterSource.parse(water_source),
        notes=notes,
    )
    with context.register() as register:
        register.materials.save(material)
    click.echo(material.describe())


@material_group.command("list")
@click.option("--class", "material_class", default=None, help="Only this class.")
@click.pass_obj
@handle_errors
def list_command(context: CliContext, material_class: str | None) -> None:
    """List what the plant stocks."""
    with context.register() as register:
        if material_class is None:
            materials = register.materials.all()
        else:
            materials = register.materials.of_class(MaterialClass.parse(material_class))
    columns = (
        Column("code"),
        Column("name"),
        Column("class"),
        Column("sg", Align.RIGHT),
        Column("supplier"),
    )
    rows = [
        [
            material.code,
            material.name,
            str(material.material_class),
            "-" if material.specific_gravity is None else f"{material.specific_gravity:.3f}",
            material.supplier or "-",
        ]
        for material in materials
    ]
    click.echo(render_table(columns, rows))


@material_group.command("show")
@click.argument("code")
@day_option()
@click.pass_obj
@handle_errors
def show_command(context: CliContext, code: str, on: date) -> None:
    """Show one material and the state of its paper."""
    with context.register() as register:
        material = register.materials.get(code)
        certificates = register.materials.certificates_for(material.code)
        catalog = register.materials.load_catalog()
        missing = catalog.missing_certificates(material.code, on)
    click.echo(heading(material.describe()))
    click.echo(
        render_pairs(
            [
                ("class", str(material.material_class)),
                ("supplier", material.supplier or "-"),
                ("source", material.source or "-"),
                (
                    "specific gravity",
                    "-" if material.specific_gravity is None else material.specific_gravity,
                ),
                ("absorption", "-" if material.absorption is None else material.absorption),
                (
                    "fineness modulus",
                    "-" if material.fineness_modulus is None else material.fineness_modulus,
                ),
                (
                    "nominal max size",
                    "-" if material.nominal_max_size is None else material.nominal_max_size,
                ),
                (
                    "needs",
                    ", ".join(str(kind) for kind in required_certificates(material)) or "-",
                ),
                ("missing", ", ".join(str(kind) for kind in missing) or "none"),
            ]
        )
    )
    if certificates:
        click.echo("")
        columns = (
            Column("reference"),
            Column("kind"),
            Column("issued"),
            Column("expires"),
            Column("state"),
        )
        rows = [
            [
                certificate.reference,
                str(certificate.kind),
                certificate.issued.isoformat(),
                certificate.expires.isoformat(),
                str(certificate.state(on)),
            ]
            for certificate in certificates
        ]
        click.echo(render_table(columns, rows))


@material_group.command("certify")
@click.argument("code")
@click.argument("reference")
@click.option("--kind", required=True, help="mill_certificate, gradation, source_approval...")
@click.option("--issued", required=True, metavar="YYYY-MM-DD")
@click.option("--expires", default=None, metavar="YYYY-MM-DD")
@click.option("--days", type=int, default=None, help="Term in days, instead of an expiry.")
@click.option("--issuer", default=None)
@click.option("--lot", default=None)
@click.pass_obj
@handle_errors
def certify_command(
    context: CliContext,
    code: str,
    reference: str,
    kind: str,
    issued: str,
    expires: str | None,
    days: int | None,
    issuer: str | None,
    lot: str | None,
) -> None:
    """File a certificate against a material."""
    certificate_kind = CertificateKind.parse(kind)
    issued_on = parse_day(issued)
    if expires is not None:
        certificate = Certificate(
            code, certificate_kind, reference, issued_on, parse_day(expires), issuer, lot
        )
    else:
        certificate = Certificate.for_term(
            code, certificate_kind, reference, issued_on, days=days, issuer=issuer, lot=lot
        )
    with context.register() as register:
        register.materials.save_certificate(certificate)
    click.echo(certificate.describe(date.today()))


@material_group.command("expiring")
@day_option()
@click.option("--within", type=int, default=21, help="Days ahead to look.")
@click.pass_obj
@handle_errors
def expiring_command(context: CliContext, on: date, within: int) -> None:
    """List certificates that lapse soon."""
    with context.register() as register:
        catalog = register.materials.load_catalog()
    soon = catalog.expiring_soon(on, within_days=within)
    columns = (
        Column("material"),
        Column("reference"),
        Column("kind"),
        Column("expires"),
        Column("days", Align.RIGHT),
    )
    rows = [
        [
            certificate.material_code,
            certificate.reference,
            str(certificate.kind),
            certificate.expires.isoformat(),
            certificate.days_remaining(on),
        ]
        for certificate in soon
    ]
    click.echo(render_table(columns, rows))


@material_group.command("blocked")
@day_option()
@click.pass_obj
@handle_errors
def blocked_command(context: CliContext, on: date) -> None:
    """List materials that cannot be batched for want of paper."""
    with context.register() as register:
        catalog = register.materials.load_catalog()
    columns = (Column("material"), Column("missing"))
    rows = [
        [code, ", ".join(str(kind) for kind in catalog.missing_certificates(code, on))]
        for code in catalog.codes()
        if not catalog.is_batchable(code, on)
    ]
    click.echo(render_table(columns, rows))
