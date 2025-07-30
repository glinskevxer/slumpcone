# slumpcone

Production, quality control and delivery compliance for a ready-mix concrete
plant. Named for the Abrams cone that measures slump, which is the test everyone
on a job site knows and the one that starts most arguments.

This is a command line tool over a single SQLite file. A plant runs it on the
batch computer in the room next to the mixer. There is no server, no daemon and
nothing to keep running.

## What it is for

A ready-mix plant has to answer four questions, every day, on paper, to somebody
who is not on its side:

- **Did the load match the ticket.** Weighing tolerances under ASTM C94,
  moisture-corrected batch weights, yield by absolute volume under C138.
- **Was it any good when it arrived.** Slump, air, temperature and unit weight
  under C143, C231, C173 and C1064, sampled at the frequency ACI 318 asks for,
  with the one-retest rule applied the way C94 actually writes it.
- **Did it get there in time.** Ninety minutes or three hundred revolutions,
  water added at the job and who asked for it, and what that does to the
  warranty.
- **Will it reach strength.** Cylinders, ACI 214 standards of control, the ACI
  318 acceptance criteria, cores under C42, and a maturity curve when the job
  cannot wait.

Everything else here exists because a plant that can answer those four questions
still gets caught out by something: a scale that went out of calibration, a
technician's card that lapsed, a mixer that stopped mixing uniformly, an invoice
that never went out for a load that did.

## Installing

```
pip install slumpcone
```

Python 3.12 or newer. The only runtime dependency is click.

## Five minutes

```
slumpcone register init
slumpcone demo seed
slumpcone report day --on 2024-06-12
```

`demo seed` files a worked example: one plant, one paving mix, one day of four
loads with their tests and cylinders, plus the crew, the wash tanks, the probes
and the account. Every figure in it hangs together, so it is a reasonable thing
to read while working out what a command does.

Then try these, in this order:

```
slumpcone mix check 4000P-57
slumpcone batch audit --from 2024-06-12 --to 2024-06-12
slumpcone lab strength --mix 4000P-57
slumpcone report compliance --on 2024-06-12
slumpcone carbon mix 4000P-57
```

## What it covers

| area | what is in it |
| --- | --- |
| materials | catalogue, certificates, sieve analysis and C33 grading, blending, workability |
| mix design | proportions, absolute volume yield, ACI 211 tables, exposure classes, chloride and alkali limits, mass concrete |
| batching | moisture correction, C94 weighing tolerances, tickets, mixer uniformity under C94 Annex A1 |
| delivery | haul limits, revolutions, jobsite water and the warranty, slump loss, trucks |
| fresh tests | the five tests, sampling frequency, acceptance and the one-retest rule, weather, setting time, bleeding and segregation |
| strength | specimens, breaks, ACI 214 control, required average strength, acceptance, cores, beams, maturity |
| plant | silos, scales, receipts, inventory, moisture probe calibration |
| dispatch | pour schedules, the truck board, haul profiles fitted from the tickets |
| sales | accounts, price quotes, surcharges, invoices, aging |
| carbon | emission factors with their provenance, footprints per cubic metre, benchmark tables |
| people | technician certifications, and whether the results on file would stand up |
| reporting | production, compliance, yield, strength, fleet, inventory, non-conformance, control charts, cusum, and one daily page |

The full command reference is in [docs/commands.md](docs/commands.md), and it is
generated from the commands themselves:

```
slumpcone register reference --out docs/commands.md
```

## The register

One SQLite file, migrated forward by numbered scripts with a checksum guard so a
schema that was edited by hand is refused rather than half-applied.

```
slumpcone register info
slumpcone register verify
slumpcone register backup --into backups/
slumpcone register plans
```

`verify` runs two different checks: whether the pages are internally consistent,
and whether every reference points at a row that is there. A register can fail
one and pass the other.

`backup` uses SQLite's own backup API, which takes a consistent snapshot while
the plant is batching. Copying the file is not a backup and there is no code
path here that does it.

`plans` checks that the queries the reports run still use an index. It is a
property of the schema rather than of the machine, so it means the same thing in
CI as it does on the plant's computer.

## Units

Quantities carry their units and refuse to be added to the wrong dimension. A
slump is a length, a strength is a pressure, and a temperature is not a
temperature difference. Cement content is a mass per unit volume and is its own
type, because dividing one by another is a ratio and dividing it by a volume is
a mistake.

Both customary and metric go in and come out; the conversions happen at the
edges and the arithmetic in the middle is done in one system.

## Who is running it

```
slumpcone --actor j.mercer mix add ...
```

The writes that matter go into an append-only audit log, chained so that one row
changed in the middle can be detected. Set `SLUMPCONE_ACTOR` and forget about it.

## Development

```
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
```

`mypy` runs strict. The test suite is about four thousand tests and takes
around a minute.

## Licence

MIT.
