# Command reference

Generated from the command line itself. To change a description,
change the docstring on the command.

## Groups

- **`config`** Read and write the settings file.
- **`register`** Create and inspect the register file.
- **`material`** File materials and their certificates.
- **`plant`** File plants, scales and vessels.
- **`mix`** File and check mix designs.
- **`batch`** Plan batches and write tickets.
- **`field`** Record and judge fresh property tests.
- **`lab`** Cast cylinders, break them and read the record.
- **`delivery`** File trucks, deliveries and the water added at the job.
- **`project`** File jobs, classes, submittals and orders.
- **`inventory`** Receive material, draw on it and reconcile the ledger.
- **`import`** Load batch recorder, lab and supplier files.
- **`report`** Print the reports a plant has to produce.
- **`price`** File material prices and cost a mixture out.
- **`export`** Write records out as delimited text or as a document.
- **`audit`** Record and read the audit log.
- **`control`** Read how consistent the plant and the laboratory are.
- **`beam`** Break beams and read the modulus of rupture.
- **`core`** Take cores and judge the structure on them.
- **`maturity`** Fit maturity curves and read in place strength off them.
- **`account`** File customers, their terms and their prices.
- **`invoice`** Draft, issue and settle invoices.
- **`bleed`** Record and read bleeding and segregation tests.
- **`mixer`** Record and read mixer uniformity tests.
- **`carbon`** Emission factors, footprints and benchmark tables.
- **`dispatch`** Lay pours out and put trucks against them.
- **`crew`** Technicians, their certifications and what they may run.
- **`reclaim`** Wash water tanks and loads that came back.
- **`probe`** Moisture probes and the checks that keep them honest.
- **`demo`** Fill a register with a worked example.

## `config`

Read and write the settings file.

### `config show`

What the settings file says, and where the values actually came from.

```
slumpcone config show
```

### `config path`

Where the settings file was found, if anywhere.

```
slumpcone config path
```

### `config init`

Write a starter settings file.

```
slumpcone config init [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--out` |  | Where to write it. | `slumpcone.toml` |
| `--force` |  | Write over one that is already there. |  |
| `--plant` |  |  |  |
| `--actor` |  |  |  |

### `config check`

Read a settings file and say whether this build understands all of it.

```
slumpcone config check <path>
```

## `register`

Create and inspect the register file.

### `register init`

Create the register and bring it to the current schema.

```
slumpcone register init
```

### `register check`

Verify the schema is the one this build expects.

```
slumpcone register check
```

### `register info`

Show the schema version and what is on file.

```
slumpcone register info
```

### `register verify`

Check the pages and the references, which are two different questions.

```
slumpcone register verify
```

### `register backup`

Take a consistent snapshot, even while the plant is batching.

```
slumpcone register backup <destination> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--into` |  | A folder to name the file in. |  |
| `--stem` |  | What to call it, before the stamp. | `register` |

### `register restore`

Put a backup back, after checking it.

```
slumpcone register restore <backup> <destination> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--force` |  | Write over a register that is already there. |  |

### `register backups`

Every backup in a folder.

```
slumpcone register backups <folder>
```

### `register prune`

Delete all but the newest backups.

```
slumpcone register prune <folder> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--keep` |  | How many to keep. | `7` |
| `--dry-run` |  | Say what would go, delete nothing. |  |

### `register vacuum`

Rewrite the file to reclaim free pages.

```
slumpcone register vacuum [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--minimum` |  | Refuse unless this share of the file is free, 0 to 1. | `0.0` |

### `register plans`

Check that the queries the reports run still use an index.

Timings are printed and never judged. What is judged is whether SQLite
    planned to read a table whole, which is a property of the schema rather
    than of this machine, and which will still be true on the plant's.

```
slumpcone register plans [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--all` |  | Show every probe, not just the bad ones. |  |

### `register reference`

Print the command reference, generated from the commands themselves.

```
slumpcone register reference [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--out` |  | Write to a file instead of the screen. |  |

### `register versions`

Everything worth pasting into a bug report.

```
slumpcone register versions [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--one-line` |  | Print one line, for a log. |  |

### `register doctor`

Run every check there is and say what stops the plant working.

Nothing here has an opinion of its own. Every finding comes from a rule that
    already refuses work somewhere else, so this and the command that refused
    cannot disagree.

```
slumpcone register doctor [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--all` |  | Show notes as well. |  |

## `material`

File materials and their certificates.

### `material add`

File a material the plant can batch.

```
slumpcone material add <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--class` |  | cement, scm, coarse_aggregate... | required |
| `--supplier` |  |  |  |
| `--source` |  |  |  |
| `--sg` |  | Specific gravity. |  |
| `--absorption` |  | Absorption, percent. |  |
| `--fm` |  |  |  |
| `--nms` |  | Nominal maximum size, for example "1 in". |  |
| `--dry-rodded` |  | For example "101.5 lb/ft3". |  |
| `--cement-type` |  |  |  |
| `--scm-kind` |  |  |  |
| `--admixture-type` |  |  |  |
| `--solids` |  | Solids content, percent. |  |
| `--chloride` |  | Chloride assay, percent. |  |
| `--alkali` |  | Alkali equivalent, percent. |  |
| `--water-source` |  |  |  |
| `--notes` |  |  | `` |

### `material list`

List what the plant stocks.

```
slumpcone material list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--class` |  | Only this class. |  |

### `material show`

Show one material and the state of its paper.

```
slumpcone material show <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `material certify`

File a certificate against a material.

```
slumpcone material certify <code> <reference> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--kind` |  | mill_certificate, gradation, source_approval... | required |
| `--issued` | YYYY-MM-DD |  | required |
| `--expires` | YYYY-MM-DD |  |  |
| `--days` |  | Term in days, instead of an expiry. |  |
| `--issuer` |  |  |  |
| `--lot` |  |  |  |

### `material expiring`

List certificates that lapse soon.

```
slumpcone material expiring [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--within` |  | Days ahead to look. | `21` |

### `material blocked`

List materials that cannot be batched for want of paper.

```
slumpcone material blocked [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

## `plant`

File plants, scales and vessels.

### `plant add`

File a plant. Its scales are added separately.

```
slumpcone plant add <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--system` |  | customary or metric. | `customary` |
| `--mixing` |  | How the plant mixes. | `truck_mixed` |
| `--water` |  |  | `potable` |
| `--max-load` |  | For example "11 yd3". |  |
| `--certified-to` | YYYY-MM-DD |  |  |
| `--location` |  |  |  |

### `plant list`

List the plants and whether they can run.

```
slumpcone plant list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `plant show`

Show one plant, its scales and its vessels.

```
slumpcone plant show <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `plant scale`

Add or replace a scale on a plant.

```
slumpcone plant scale <plant_code> <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--capacity` |  | For example "12000 lb". | required |
| `--graduation` |  | For example "2 lb". | required |
| `--weighs` |  | Comma separated material classes. | required |
| `--calibrated` | YYYY-MM-DD |  | required |
| `--interval` |  | Calibration interval in days. | `182` |

### `plant silo`

Add or replace a vessel on a plant.

```
slumpcone plant silo <plant_code> <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--material` |  |  | required |
| `--capacity` |  | For example "200000 lb". | required |
| `--level` |  |  | `0 lb` |
| `--low` |  | Low level mark. |  |

### `plant silos`

List the vessels on a plant.

```
slumpcone plant silos <plant_code>
```

## `mix`

File and check mix designs.

### `mix add`

File the first revision of a mix design.

```
slumpcone mix add <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--strength` |  | For example "4000 psi". | required |
| `--nms` |  | Nominal maximum size, "1 in". | required |
| `--slump` |  | Target slump, "4 in". | required |
| `--age` |  | Test age in days. | `28` |
| `--air` |  | Design air content, percent. | `0.0` |
| `--exposure` |  | For example "F2 S1". | `` |
| `--plant` |  |  |  |
| `--charge` |  | CODE:CLASS:CONTENT, repeatable. |  |
| `--admixture` |  | CODE:DOSE, repeatable. |  |
| `--notes` |  |  | `` |

### `mix list`

List the newest revision of every mix design.

```
slumpcone mix list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  | Only mixes tied to this plant. |  |

### `mix show`

Show a mix design and its proportions.

```
slumpcone mix show <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--revision` |  | A particular revision. |  |

### `mix check`

Check a design against its exposure classes and its own yield.

```
slumpcone mix check <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--revision` |  |  |  |

### `mix proportion`

Work a mixture up from the tables and print the working.

```
slumpcone mix proportion [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--strength` |  | Required average strength, "4800 psi". | required |
| `--slump` |  | Target slump, "4 in". | required |
| `--cement` |  | Cement material code. | required |
| `--coarse` |  | Coarse aggregate code. | required |
| `--fine` |  | Fine aggregate code. | required |
| `--water` |  | Water material code. | required |
| `--scm` |  |  |  |
| `--replacement` |  | SCM share of the binder. | `0.0` |
| `--air` |  |  | on |
| `--severity` |  | mild, moderate or severe. | `moderate` |
| `--max-wcm` |  |  |  |
| `--min-cementitious` |  | For example "564 lb". |  |

### `mix revisions`

List every revision of one design.

```
slumpcone mix revisions <code>
```

## `batch`

Plan batches and write tickets.

### `batch plan`

Work out the weights for one load.

```
slumpcone batch plan [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--mix` |  |  | required |
| `--volume` |  | For example "9 yd3". | required |
| `--moisture` |  | CODE:TOTAL:ABSORPTION. |  |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `batch check`

Say whether a load can be batched, without batching it.

```
slumpcone batch check [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--mix` |  |  | required |
| `--volume` |  |  | required |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `batch ticket`

Batch a load and file its ticket.

```
slumpcone batch ticket <number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--mix` |  |  | required |
| `--volume` |  |  | required |
| `--at` | YYYY-MM-DDTHH:MM |  |  |
| `--truck` |  |  |  |
| `--purchaser` |  |  |  |
| `--project` |  |  |  |
| `--moisture` |  | CODE:TOTAL:ABSORPTION. |  |
| `--actual` |  | CODE:WEIGHT as recorded. |  |
| `--dose` |  | CODE:AMOUNT as dispensed. |  |
| `--notes` |  |  | `` |

### `batch show`

Print one ticket.

```
slumpcone batch show <number>
```

### `batch audit`

Audit a run of tickets.

```
slumpcone batch audit [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--plant` |  |  |  |

### `batch day`

What was recorded on one day.

```
slumpcone batch day [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `batch print`

Print a delivery ticket, laid out and checked against C94 clause 14.

```
slumpcone batch print <ticket_number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--check` |  | Only say whether it is complete. |  |
| `--no-water-line` |  | Leave off the water form. |  |

## `field`

Record and judge fresh property tests.

### `field record`

Record every reading taken off one sample.

```
slumpcone field record <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--at` | YYYY-MM-DDTHH:MM |  |  |
| `--slump` |  | For example "4.5 in". |  |
| `--air` |  | Air content, percent. |  |
| `--air-method` |  | pressure or volumetric. | `pressure` |
| `--temp` |  | Concrete temperature, degF. |  |
| `--unit-weight` |  | Density, lb/ft3. |  |
| `--discharged` |  | Discharged before the sample, "3 yd3". |  |
| `--technician` |  |  |  |
| `--retest` |  | This is the second sample on a property. |  |

### `field list`

List every test taken on one load.

```
slumpcone field list <ticket>
```

### `field judge`

Judge one load against its mix design's bands.

```
slumpcone field judge <ticket>
```

### `field sample`

Say whether a sample can carry an acceptance result.

```
slumpcone field sample <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--load` |  | The load size, "9 yd3". | required |
| `--discharged` |  | Discharged before the sample, "3 yd3". | required |
| `--portions` |  |  | `2` |
| `--span` |  | Minutes between the portions. | `0.0` |
| `--delay` |  | Minutes before testing started. | `0.0` |
| `--for-specimens` |  | Judge against the moulding limit. |  |

### `field outstanding`

Loads in a window whose fresh tests have not settled.

```
slumpcone field outstanding [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

## `lab`

Cast cylinders, break them and read the record.

### `lab set`

Open a set of specimens against a mix design.

```
slumpcone lab set <set_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--mix` |  |  | required |
| `--revision` |  |  | `1` |
| `--sampled` | YYYY-MM-DDTHH:MM |  | required |
| `--size` |  |  | `4x8` |
| `--cure` |  |  | `standard` |
| `--purpose` |  |  | `acceptance` |
| `--ticket` |  |  |  |
| `--project` |  |  |  |
| `--notes` |  |  | `` |

### `lab cylinder`

Cast one cylinder into a set.

```
slumpcone lab cylinder <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--set` |  |  | required |
| `--ticket` |  |  | required |
| `--cast` | YYYY-MM-DDTHH:MM |  | required |
| `--age` |  | Planned test age in days. | `28` |
| `--size` |  |  | `4x8` |
| `--cure` |  |  | `standard` |
| `--purpose` |  |  | `acceptance` |

### `lab break`

Record a break against a cylinder.

```
slumpcone lab break <specimen_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--tested` | YYYY-MM-DDTHH:MM |  | required |
| `--age` |  | Age at test in days. | required |
| `--d1` |  | For example "4.00 in". | required |
| `--d2` |  | The second diameter. |  |
| `--length` |  | Measured length. |  |
| `--load` |  | Peak load, "63000 lbf". | required |
| `--fracture` |  |  | `cone` |
| `--by` |  |  |  |

### `lab pending`

Cylinders that are due or overdue and have not been broken.

```
slumpcone lab pending [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `lab test`

Show the strength test one set adds up to.

```
slumpcone lab test <set_code>
```

### `lab strength`

The strength record for one mixture.

```
slumpcone lab strength <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--specified` |  | For example "4000 psi". | required |

### `lab project-strength`

The strength record for one job, across every mixture on it.

```
slumpcone lab project-strength <project> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--specified` |  |  | required |

## `delivery`

File trucks, deliveries and the water added at the job.

### `delivery truck`

File a truck mixer.

```
slumpcone delivery truck <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--drum` |  | Gross drum volume, "11 yd3". | required |
| `--fleet` |  |  |  |
| `--uniformity` | YYYY-MM-DD |  |  |
| `--interval` |  |  | `365` |

### `delivery trucks`

List the fleet.

```
slumpcone delivery trucks
```

### `delivery record`

Record or update a delivery, keeping any water additions on it.

```
slumpcone delivery record <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--truck` |  |  | required |
| `--batched` | YYYY-MM-DDTHH:MM |  | required |
| `--left` | YYYY-MM-DDTHH:MM |  |  |
| `--arrived` | YYYY-MM-DDTHH:MM |  |  |
| `--start` | YYYY-MM-DDTHH:MM |  |  |
| `--finish` | YYYY-MM-DDTHH:MM |  |  |
| `--rev-arrival` |  |  |  |
| `--rev-discharge` |  |  |  |
| `--returned` |  | Concrete brought back, "0.5 yd3". |  |
| `--notes` |  |  | `` |

### `delivery water`

Record water added at the job and judge it.

```
slumpcone delivery water <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--amount` |  | Water added, "5 gal". | required |
| `--at` | YYYY-MM-DDTHH:MM |  | required |
| `--by` |  |  | `purchaser` |
| `--revolutions` |  |  | `30` |
| `--discharged` |  | Concrete already placed. |  |

### `delivery haul`

Judge one load's haul against the limits that apply to it.

```
slumpcone delivery haul <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--retarder` |  | The mixture carries a retarder. |  |
| `--temp` |  | Concrete temperature, degF. |  |
| `--waived` |  | The purchaser waived the time limit. |  |

### `delivery list`

List deliveries in a window.

```
slumpcone delivery list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--unfinished` |  | Only loads that never finished. |  |
| `--truck` |  |  |  |

## `project`

File jobs, classes, submittals and orders.

### `project add`

File a job, keeping any classes already on it.

```
slumpcone project add <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--owner` |  |  |  |
| `--specifier` |  |  |  |
| `--system` |  |  | `customary` |
| `--start` | YYYY-MM-DD |  |  |
| `--finish` | YYYY-MM-DD |  |  |

### `project class`

Add or replace a class of concrete on a job.

```
slumpcone project class <project_code> <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--strength` |  | For example "4000 psi". | required |
| `--age` |  |  | `28` |
| `--exposure` |  |  | `` |
| `--max-wcm` |  |  |  |
| `--min-cementitious` |  |  |  |
| `--nms` |  |  |  |
| `--description` |  |  | `` |

### `project list`

List the jobs and whether they are open.

```
slumpcone project list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `project show`

Show a job, its classes and its submittals.

```
slumpcone project show <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `project submit`

Submit a mixture to a class, checking it satisfies the class first.

```
slumpcone project submit <reference> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--project` |  |  | required |
| `--class` |  |  | required |
| `--mix` |  |  | required |
| `--revision` |  |  | `1` |
| `--on` | YYYY-MM-DD |  | required |
| `--basis` |  |  | `trial_batch` |
| `--required-average` |  | For example "5200 psi". |  |

### `project approve`

Approve or reject a submittal.

```
slumpcone project approve <reference> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD |  | required |
| `--reviewer` |  |  |  |
| `--days` |  |  | `365` |
| `--reject` |  | Reject instead of approving. |  |
| `--comments` |  |  | `` |

### `project approved`

Which mixtures a class may be batched from.

```
slumpcone project approved <project_code> <class_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `project order`

Book an order against a class.

```
slumpcone project order <number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--project` |  |  | required |
| `--class` |  |  | required |
| `--volume` |  | For example "60 yd3". | required |
| `--on` | YYYY-MM-DD |  | required |
| `--mix` |  |  |  |
| `--rate` |  | Delivery rate, "24 yd3". |  |
| `--placement` |  |  |  |

### `project board`

The dispatch board for one day.

```
slumpcone project board [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

## `inventory`

Receive material, draw on it and reconcile the ledger.

### `inventory receive`

Take a delivery into a vessel, raising its level and the ledger.

```
slumpcone inventory receive <reference> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--silo` |  |  | required |
| `--material` |  |  | required |
| `--quantity` |  | For example "48000 lb". | required |
| `--at` | YYYY-MM-DDTHH:MM |  | required |
| `--supplier` |  |  |  |
| `--bol` |  |  |  |
| `--certificate` |  |  |  |
| `--notes` |  |  | `` |

### `inventory draw`

Take material out of a vessel.

```
slumpcone inventory draw [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--silo` |  |  | required |
| `--quantity` |  |  | required |
| `--at` | YYYY-MM-DDTHH:MM |  |  |
| `--reference` |  | The ticket the draw was for. |  |

### `inventory reconcile`

Set a vessel to a measured level and record the correction.

```
slumpcone inventory reconcile [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--silo` |  |  | required |
| `--measured` |  | The probed level, "115000 lb". | required |
| `--at` | YYYY-MM-DDTHH:MM |  |  |
| `--reference` |  |  |  |

### `inventory ledger`

List the movements at a plant over a window.

```
slumpcone inventory ledger [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--silo` |  |  |  |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `inventory report`

The inventory report for one plant.

```
slumpcone inventory report [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `inventory receipts`

List receipts at a plant over a window.

```
slumpcone inventory receipts [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

## `import`

Load batch recorder, lab and supplier files.

### `import profiles`

List the mapping profiles this build ships.

```
slumpcone import profiles
```

### `import run`

Read one file through one profile.

```
slumpcone import run <path> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--profile` |  |  | required |
| `--apply` |  | Turn the rows into records. |  |
| `--encoding` |  |  | `utf-8` |

### `import runs`

List the loads made under one profile, newest first.

```
slumpcone import runs [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--profile` |  |  | required |

### `import quarantine`

List every row still sitting in quarantine under one profile.

```
slumpcone import quarantine [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--profile` |  |  | required |

### `import forget`

Drop a run and release the content hashes it claimed.

```
slumpcone import forget <run_id>
```

## `report`

Print the reports a plant has to produce.

### `report production`

Volume, loads and returned concrete over a window.

```
slumpcone report production [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `report nonconformance`

Everything the register objects to over a window.

```
slumpcone report nonconformance [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `report compliance`

Everything that expires, in one list.

```
slumpcone report compliance [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--within` |  | Days ahead to look. | `45` |

### `report yield`

Relative yield and gravimetric air for one mixture's loads.

```
slumpcone report yield <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `report fleet`

Where the trucks went and where the time went.

```
slumpcone report fleet [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--shift` |  | Shift length in minutes. | `600.0` |
| `--cycle` |  | Expected cycle in minutes. | `90.0` |

### `report frequency`

Whether each mixture was sampled often enough over a window.

```
slumpcone report frequency [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--area` |  | Slab surface area, "24000 ft2". |  |

### `report day`

The one page a plant manager reads first.

```
slumpcone report day [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--plant` |  |  |  |
| `--findings` |  | How many findings to print. | `10` |

### `report week`

A line per day across a window.

```
slumpcone report week [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--plant` |  |  |  |

### `report utilisation`

What the fleet did with its hours.

```
slumpcone report utilisation [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `report cusum`

Has the mean moved on one mixture.

```
slumpcone report cusum <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--target` |  | Target strength, "4600 psi". |  |
| `--deviation` |  | Standard deviation, "400 psi". |  |
| `--slack` |  | Slack, in deviations. | `0.5` |
| `--limit` |  | Decision limit, in deviations. | `5.0` |

### `report witness`

Would the results on file stand up if somebody asked who took them.

```
slumpcone report witness [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--retests` |  | Only what needs a retest. |  |
| `--ticket` |  | Just one load. |  |

## `price`

File material prices and cost a mixture out.

### `price set`

File a price for a material.

```
slumpcone price set <material_code> <amount> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--per` |  | The basis, for example "1 ton". | required |
| `--currency` |  |  | `USD` |
| `--from` | YYYY-MM-DD |  |  |
| `--to` | YYYY-MM-DD |  |  |
| `--close-previous` |  | End any open window first. |  |

### `price list`

The price in force for every material on a day.

```
slumpcone price list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `price history`

Every price ever filed for one material.

```
slumpcone price history <material_code>
```

### `price cost`

Cost a mixture out at a day's prices.

```
slumpcone price cost <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--volume` |  | The batch to cost. | `1 yd3` |
| `--sale` |  | Sale price per unit, "$118.00". |  |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `price compare`

Cost several mixtures out side by side.

```
slumpcone price compare <mix_codes> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--volume` |  |  | `1 yd3` |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

## `export`

Write records out as delimited text or as a document.

### `export tickets`

Delivery tickets over a window.

```
slumpcone export tickets [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--out` |  |  |  |
| `--delimiter` |  |  | `,` |

### `export strength`

Strength tests for one mixture.

```
slumpcone export strength <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--out` |  |  |  |
| `--delimiter` |  |  | `,` |

### `export materials`

The material catalogue.

```
slumpcone export materials [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--out` |  |  |  |
| `--delimiter` |  |  | `,` |

### `export mix`

One mix design as an exchange document.

```
slumpcone export mix <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--revision` |  |  |  |
| `--out` |  |  |  |

### `export load-mix`

Read an exchange document back into the register.

```
slumpcone export load-mix <path> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--revision` |  | File it as this revision. |  |

## `audit`

Record and read the audit log.

### `audit record`

Append one event to the log.

```
slumpcone audit record <action> <subject> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--actor` |  |  | required |
| `--detail` |  |  | `` |

### `audit log`

Read the log, filtered by window, actor or subject.

```
slumpcone audit log [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--actor` |  |  |  |
| `--subject` |  |  |  |

### `audit verify`

Check the chain has not been edited in the middle.

```
slumpcone audit verify
```

## `control`

Read how consistent the plant and the laboratory are.

### `control read`

The two variations, and which of them needs attention.

```
slumpcone control read <mix_code>
```

### `control charts`

All three control charts for one mixture.

```
slumpcone control charts <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--specified` |  | For example "4000 psi". | required |

### `control chart`

One chart on its own.

```
slumpcone control chart <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--kind` |  |  | `individual` |
| `--specified` |  | Needed for the average chart. | `4000 psi` |

## `beam`

Break beams and read the modulus of rupture.

### `beam break`

Record one beam.

```
slumpcone beam break <specimen_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--set` |  |  | required |
| `--mix` |  |  | required |
| `--tested` | YYYY-MM-DDTHH:MM |  | required |
| `--age` |  |  | `28.0` |
| `--span` |  |  | `18 in` |
| `--width` |  |  | `6 in` |
| `--depth` |  |  | `6 in` |
| `--load` |  | Peak load, "6200 lbf". | required |
| `--fracture-at` |  | Distance to the nearer support. | required |

### `beam set`

The beams in one set and the average they give.

```
slumpcone beam set <set_code>
```

### `beam estimate`

Convert between compressive strength and modulus of rupture.

```
slumpcone beam estimate [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--compressive` |  | For example "4000 psi". |  |
| `--rupture` |  | For example "600 psi". |  |
| `--factor` |  |  | `7.5` |

## `core`

Take cores and judge the structure on them.

### `core take`

Record one core.

```
slumpcone core take <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--location` |  |  | required |
| `--specified` |  | For example "4000 psi". | required |
| `--taken` | YYYY-MM-DDTHH:MM |  | required |
| `--diameter` |  |  | `4 in` |
| `--length` |  | Measured length after trimming. | required |
| `--load` |  |  | required |
| `--condition` |  | soaked, air dried or as received. | `soaked` |
| `--reinforced` |  | The core contains steel. |  |

### `core judge`

Judge one location on the cores taken from it.

```
slumpcone core judge <location>
```

### `core locations`

Every location that has been cored.

```
slumpcone core locations
```

## `maturity`

Fit maturity curves and read in place strength off them.

### `maturity fit`

File a strength maturity relationship.

```
slumpcone maturity fit <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--name` |  | For example "summer". | required |
| `--point` |  | MATURITY:STRENGTH. | required |
| `--on` | YYYY-MM-DD | The day the curve was fitted. |  |
| `--notes` |  |  | `` |

### `maturity curves`

Every curve on file for one mixture.

```
slumpcone maturity curves <mix_code>
```

### `maturity log`

Record one logger reading.

```
slumpcone maturity log <sensor> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--placement` |  |  | required |
| `--at` | YYYY-MM-DDTHH:MM |  | required |
| `--temp` |  | Reading in degF. | required |

### `maturity history`

One sensor's readings and the maturity they add up to.

```
slumpcone maturity history <sensor>
```

### `maturity estimate`

Read an in place strength off a curve and a logger.

```
slumpcone maturity estimate <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--name` |  | Which curve to read against. | required |
| `--sensor` |  |  | required |

## `account`

File customers, their terms and their prices.

### `account add`

File a customer.

```
slumpcone account add <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--status` |  |  | `open` |
| `--terms` |  | Days to pay. | `30` |
| `--discount-days` |  |  | `0` |
| `--discount` |  | Prompt payment discount. | `0.0` |
| `--limit` |  | Credit limit, "$25000". |  |
| `--contact` |  |  |  |
| `--phone` |  |  |  |
| `--notes` |  |  | `` |

### `account list`

List the customers.

```
slumpcone account list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--open` |  | Only accounts taking work. |  |

### `account show`

Show one customer, their terms and their quotes.

```
slumpcone account show <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--balance` |  | What they owe right now. | `0.00` |

### `account quote`

Quote one customer a price for one mixture.

```
slumpcone account quote <account_code> <mix_code> <price> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD |  |  |
| `--to` | YYYY-MM-DD |  |  |

### `account check`

Say whether an account can take one more order.

```
slumpcone account check <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--balance` |  | What they owe right now. | required |
| `--order` |  | What the order is worth. | required |

### `account margin`

What one customer pays for a mixture against what it costs to make.

```
slumpcone account margin <account_code> <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--volume` |  |  | `1 yd3` |

## `invoice`

Draft, issue and settle invoices.

### `invoice draft`

Draft an invoice from a run of tickets.

```
slumpcone invoice draft <number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--account` |  |  | required |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--project` |  | Only tickets on this job. |  |
| `--tax` |  |  | `0.0` |
| `--charges` |  |  | on |
| `--winter` |  | Add the cold weather charges. |  |

### `invoice show`

Print one invoice.

```
slumpcone invoice show <number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `invoice issue`

Issue a draft.

```
slumpcone invoice issue <number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD |  |  |

### `invoice pay`

Record a payment.

```
slumpcone invoice pay <number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--amount` |  |  | required |
| `--on` | YYYY-MM-DD |  | required |
| `--reference` |  |  |  |

### `invoice void`

Void an invoice that has taken no money.

```
slumpcone invoice void <number>
```

### `invoice list`

List invoices.

```
slumpcone invoice list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--account` |  |  |  |
| `--owed` |  | Only invoices still expecting money. |  |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `invoice aging`

The outstanding balance split into aging buckets.

```
slumpcone invoice aging [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--account` |  |  |  |

### `invoice unbilled`

Tickets in a window that no invoice has picked up.

```
slumpcone invoice unbilled [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

## `bleed`

Record and read bleeding and segregation tests.

### `bleed record`

Record a bleeding test with every draw it took.

```
slumpcone bleed record <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The day the test was run. |  |
| `--sample` |  | Mass of the sample, with a unit. | required |
| `--batch` |  | Mass of the whole batch. | required |
| `--water` |  | Net mixing water in the batch. | required |
| `--area` |  | Surface area of the sample. | `0.0785 ft2` |
| `--draw` | MINUTES:POUNDS | One draw off the surface. Repeat for every draw taken. |  |
| `--technician` |  |  | `` |
| `--replace` |  | Overwrite a test already on file. |  |

### `bleed show`

Print one bleeding test.

```
slumpcone bleed show <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--after` |  | Rate window start, in minutes. | `0.0` |

### `bleed list`

Bleeding tests in a window, heaviest bleeder called out.

```
slumpcone bleed list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

### `bleed column`

Record a column segregation result.

```
slumpcone bleed column <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--top` |  | Coarse aggregate in the top section. | required |
| `--bottom` |  | Coarse aggregate in the bottom section. | required |
| `--visual` |  | Visual stability index, 0 through 3. |  |
| `--technician` |  |  | `` |

### `bleed columns`

Column segregation results in a window.

```
slumpcone bleed columns [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--failing` |  | Only results over the ten percent cap. |  |

## `mixer`

Record and read mixer uniformity tests.

### `mixer keys`

What a sample string can carry.

```
slumpcone mixer keys
```

### `mixer uniformity`

Record a uniformity test and print the verdict.

```
slumpcone mixer uniformity <mixer> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The day the test was run. |  |
| `--sample` | KEY=VALUE,... | One sample. Give this twice, once for each draw. |  |
| `--plant` |  |  | `` |
| `--technician` |  |  | `` |
| `--notes` |  |  | `` |

### `mixer show`

Print one uniformity test.

```
slumpcone mixer show <mixer> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `mixer history`

Every uniformity test on one mixer.

```
slumpcone mixer history <mixer>
```

### `mixer list`

Uniformity tests in a window.

```
slumpcone mixer list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |
| `--plant` |  |  |  |
| `--failing` |  | Only the mixers that did not make five. |  |

### `mixer due`

Which of these mixers has run out of uniformity test.

```
slumpcone mixer due <mixers> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--every` |  | Interval in days. | `365` |

## `carbon`

Emission factors, footprints and benchmark tables.

### `carbon seed`

Load the shipped industry averages and benchmark shape.

```
slumpcone carbon seed [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--table` |  |  | `national average` |

### `carbon factor`

File an emission factor for one material.

```
slumpcone carbon factor <material> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--class` |  |  | required |
| `--value` |  | kg CO2e per kg of material. | required |
| `--stage` |  |  | `A1-A3` |
| `--provenance` |  |  | `industry average` |
| `--source` |  | The document the figure came from. | `` |
| `--published` | YYYY-MM-DD |  |  |

### `carbon factors`

Every emission factor on file.

```
slumpcone carbon factors [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--stale` |  | Only the declarations that have aged out. |  |

### `carbon drop`

Forget an emission factor.

```
slumpcone carbon drop <material>
```

### `carbon density`

File the density an admixture is counted through.

```
slumpcone carbon density <material> <density>
```

### `carbon mix`

What one mixture carries, and how it reads against a benchmark.

```
slumpcone carbon mix <mix_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--revision` |  |  |  |
| `--volume` |  |  | `1 yd3` |
| `--table` |  |  | `national average` |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `carbon compare`

Order mixtures by what they carry, lightest first.

```
slumpcone carbon compare <mix_codes> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--volume` |  |  | `1 yd3` |

### `carbon tables`

Every benchmark table on file, with its rows.

```
slumpcone carbon tables
```

## `dispatch`

Lay pours out and put trucks against them.

### `dispatch schedule`

Lay one order out into loads.

```
slumpcone dispatch schedule <order_number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--load` |  | Load size. | `9 yd3` |
| `--rate` |  | Placing rate, "30 yd3". |  |
| `--start` | YYYY-MM-DDTHH:MM |  |  |
| `--ignore-profile` |  | Use the given cycle, not the job's. |  |
| `--load` |  | Loading at the plant. Minutes. | `10` |
| `--out` |  | Driving out to the job. Minutes. | `20` |
| `--site` |  | On site, waiting and discharging. Minutes. | `15` |
| `--back` |  | Driving back to the plant. Minutes. | `20` |
| `--wash` |  | Washing out after the load. Minutes. | `5` |

### `dispatch board`

Put trucks against one order.

```
slumpcone dispatch board <order_number> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--truck` |  | A truck code. Repeatable. |  |
| `--load` |  |  | `9 yd3` |
| `--rate` |  |  |  |
| `--start` | YYYY-MM-DDTHH:MM |  |  |
| `--no-slip` |  | Leave loads unassigned rather than late. |  |
| `--load` |  | Loading at the plant. Minutes. | `10` |
| `--out` |  | Driving out to the job. Minutes. | `20` |
| `--site` |  | On site, waiting and discharging. Minutes. | `15` |
| `--back` |  | Driving back to the plant. Minutes. | `20` |
| `--wash` |  | Washing out after the load. Minutes. | `5` |

### `dispatch at`

What every truck is doing at one moment.

```
slumpcone dispatch at <order_number> <moment> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--truck` |  |  |  |
| `--load` |  |  | `9 yd3` |
| `--rate` |  |  |  |
| `--load` |  | Loading at the plant. Minutes. | `10` |
| `--out` |  | Driving out to the job. Minutes. | `20` |
| `--site` |  | On site, waiting and discharging. Minutes. | `15` |
| `--back` |  | Driving back to the plant. Minutes. | `20` |
| `--wash` |  | Washing out after the load. Minutes. | `5` |

### `dispatch day`

Every order booked for a day, and which of them collide.

```
slumpcone dispatch day [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The day to lay out. |  |
| `--load` |  |  | `9 yd3` |
| `--rate` |  |  | `30 yd3` |
| `--load` |  | Loading at the plant. Minutes. | `10` |
| `--out` |  | Driving out to the job. Minutes. | `20` |
| `--site` |  | On site, waiting and discharging. Minutes. | `15` |
| `--back` |  | Driving back to the plant. Minutes. | `20` |
| `--wash` |  | Washing out after the load. Minutes. | `5` |

### `dispatch haul`

File a haul profile for one job by hand.

```
slumpcone dispatch haul <project_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--load` |  | Loading at the plant. Minutes. | `10` |
| `--out` |  | Driving out to the job. Minutes. | `20` |
| `--site` |  | On site, waiting and discharging. Minutes. | `15` |
| `--back` |  | Driving back to the plant. Minutes. | `20` |
| `--wash` |  | Washing out after the load. Minutes. | `5` |
| `--notes` |  |  | `` |

### `dispatch fit`

Fit a haul profile from the deliveries already on file for a job.

A ticket carries the job as the free text the dispatcher typed, not as the
    project code, and the two are rarely the same string. So the label the
    tickets actually carry is an option, and it defaults to the code for the
    plants where somebody was disciplined about it.

```
slumpcone dispatch fit <project_code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The day to record the fit against. |  |
| `--load` |  |  | `10` |
| `--wash` |  |  | `5` |
| `--label` |  | The job name written on the tickets. Defaults to the project code. |  |

### `dispatch profiles`

Every haul profile on file.

```
slumpcone dispatch profiles
```

### `dispatch forget`

Drop a haul profile.

```
slumpcone dispatch forget <project_code>
```

## `crew`

Technicians, their certifications and what they may run.

### `crew add`

File a technician. Keeps any cards already on record.

```
slumpcone crew add <code> <name> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--employer` |  |  | `` |

### `crew card`

Add a certification to somebody already on file.

```
slumpcone crew card <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--grade` |  | For example "field grade I". | required |
| `--number` |  |  | required |
| `--issued` | YYYY-MM-DD |  | required |
| `--expires` | YYYY-MM-DD |  | required |

### `crew show`

One technician, their cards and what they may run today.

```
slumpcone crew show <code> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `crew list`

Everybody on file.

```
slumpcone crew list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `crew roster`

Who may run one test today.

```
slumpcone crew roster <test> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `crew gaps`

What nobody on file may run today.

```
slumpcone crew gaps [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `crew expiring`

Cards running out, or cards already run out.

```
slumpcone crew expiring [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--days` |  | How far ahead to look. | `60` |
| `--lapsed` |  | Show what has run out. |  |

### `crew drop`

Forget a technician and their cards.

```
slumpcone crew drop <code>
```

## `reclaim`

Wash water tanks and loads that came back.

### `reclaim tank`

Record a wash tank density reading.

```
slumpcone reclaim tank <tank> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--sg` |  |  | required |
| `--volume` |  | For example "2000 gal". | required |
| `--on` | YYYY-MM-DD | The day the tank was read. |  |
| `--notes` |  |  | `` |
| `--replace` |  | Overwrite today's reading. |  |

### `reclaim tanks`

Every tank read on one day.

```
slumpcone reclaim tanks [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--usable` |  | Only the tanks clean enough to batch from. |  |

### `reclaim draw`

How much of a draw is water and how much is cement that already reacted.

```
slumpcone reclaim draw <tank> <amount> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `reclaim returned`

Record a load that came back.

```
slumpcone reclaim returned <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--mix` |  |  | required |
| `--volume` |  | For example "3 yd3". | required |
| `--age` |  | Minutes since batching. | required |
| `--on` | YYYY-MM-DD | The day it came back. |  |

### `reclaim yard`

What is still sitting on the yard, and how much of it can be used.

```
slumpcone reclaim yard [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--into` |  | The load being planned. | `9 yd3` |
| `--waited` |  | Extra minutes on the yard. | `0.0` |
| `--cap` |  | Share of a new load returned concrete may be, percent. | `15.0` |

### `reclaim use`

Record that a returned load went into a later one.

```
slumpcone reclaim use <ticket> <new_ticket>
```

### `reclaim dispose`

Record that a returned load was dumped.

```
slumpcone reclaim dispose <ticket> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `reclaim history`

Every load that came back in a window, and what became of it.

```
slumpcone reclaim history [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

## `probe`

Moisture probes and the checks that keep them honest.

### `probe check`

Record a probe check against an oven dried sample.

```
slumpcone probe check <probe> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--probe-read` |  |  | required |
| `--oven` |  |  | required |
| `--on` | YYYY-MM-DD | The day the check was run. |  |
| `--technician` |  |  | `` |
| `--notes` |  |  | `` |
| `--replace` |  |  |  |

### `probe show`

One probe's history and where it stands today.

```
slumpcone probe show <probe> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `probe correct`

Apply a probe's standing offset to a reading.

```
slumpcone probe correct <probe> <reading> [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--on` | YYYY-MM-DD | The date to judge against. |  |

### `probe list`

Every probe at one plant.

```
slumpcone probe list [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--on` | YYYY-MM-DD | The date to judge against. |  |
| `--attention` |  | Only the ones to do something about. |  |

### `probe checks`

Every check run in a window.

```
slumpcone probe checks [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--plant` |  |  | required |
| `--from` | YYYY-MM-DD | First day of the window. |  |
| `--to` | YYYY-MM-DD | Last day of the window. |  |

## `demo`

Fill a register with a worked example.

### `demo seed`

File one plant, one mixture and one day's work.

```
slumpcone demo seed [options]
```

| option | value | what it does | default |
| --- | --- | --- | --- |
| `--force` |  | Seed even if the register has rows in it. |  |
| `--yard` |  | Also file the crew, tanks, probes and account. | on |

### `demo tour`

Print the commands worth running against a seeded register.

```
slumpcone demo tour
```
