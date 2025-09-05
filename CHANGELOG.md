# Changelog

Dates are the day the work landed on `main`.

## 1.0.0 — 2025-09-05

The version number is the only thing that changed in the concrete. Everything
in 0.9.0 is here unchanged; what this release says is that the interfaces are
now ones a plant can build a script against and expect to keep working.

### Added

- `register doctor`, which runs every check the package has and sorts what it
  finds into what stops work, what will stop work, and what is only worth
  knowing. It has no rules of its own: every finding comes from a rule that
  already refuses work somewhere else, so the two cannot disagree.
- `register versions`, for the message somebody pastes into a bug report. It
  prints the schema version of the register on this machine next to the one
  this build ships, which is the pair that explains most confusing failures.
- `python -m slumpcone`, for the machines where the console script is not on
  the path.
- A `py.typed` marker, so a project depending on this gets the types.

### Fixed

- **A usage error exited 1 rather than 2 through the console script.** Click is
  run with standalone mode off so the command line is testable in process,
  which makes click raise where it would have exited. The exception carries the
  code and it was being dropped. Two is the one code scripts branch on.
- **A moisture probe merely due for a check refused to correct a reading.**
  Booked is not broken, and refusing there stops a plant batching because a
  technician is on holiday. Overdue and failed still refuse. Found by writing
  `register doctor` and disagreeing with the answer it gave.
- **`--help` through the console script raised instead of printing.** Same root
  cause as the exit code: click signals "printed and stopped" by raising when
  standalone mode is off, and that was landing as a traceback.
- The wheel was not carrying the schema scripts or the typing marker, because
  neither is a `.py` file. Both are declared now, and the smoke job installs
  from the wheel and drives the whole command line.

### Compatibility

The register schema is at 27 migrations. A register written by 0.9.0 opens and
migrates forward. Nothing is removed and no command changed its output shape.

## Unreleased

Nothing yet.

## 0.9.0 — 2025-08-30

The last release before 1.0. Everything below is in it.

### Added

- **Delivery ticket printing.** `batch print` lays a ticket out for the back of
  the truck and checks it against the ten items C94 clause 14.1 requires, plus
  the six of 14.2 that appear when the specification asks. A ticket missing one
  of the ten is not a delivery ticket, and the command says which one.
- **Moisture probe calibration.** `probe` records checks against oven dried
  samples, tracks offset and drift separately, and refuses to correct a reading
  from a probe whose last check has run out.
- **Technician certifications.** `crew` holds cards and grades. `report witness`
  asks whether the results already on file were run by somebody entitled to run
  them, judging each card on the day of the test rather than today.
- **Wash water and returned concrete.** `reclaim` turns a hydrometer reading
  into a solids concentration under C1602, and tracks what came back on the yard
  under C1798 including the age it will be when somebody decides to use it.
- **Carbon.** `carbon` computes a footprint per cubic metre from emission
  factors that carry their provenance, and judges it against a benchmark table
  that steps rather than interpolating.
- **Dispatch.** `dispatch` lays a pour out into loads from the placing rate,
  works out the trucks needed from the cycle time, and fits a haul profile from
  the delivery records already on file.
- **Mixer uniformity.** C94 Annex A1, which asks for five of six comparisons
  rather than six of six.
- **Bleeding and segregation.** C232 and C1610.
- **Cusum.** `report cusum` catches a drifting mean that an individuals chart
  cannot see, and names the test the run started at.
- **A daily page.** `report day` is the one page a plant manager reads first.
- **Utilisation.** `report utilisation` gives yards per truck hour, dividing
  totals rather than averaging rates.
- **Register maintenance.** `register backup` takes a consistent snapshot
  through SQLite's own backup API; `register verify` runs both the page check
  and the reference check; `register plans` checks that the queries the reports
  run still use an index.
- **A generated command reference**, in `docs/commands.md`, with a CI job that
  refuses a build where it has drifted.
- **Tab completion** for mix, plant, material, account, technician and truck
  codes, read from the register on the command line being typed.
- **Distinct exit codes**, so a script can tell "not on file" from "the rule
  refused it" from "the register is broken".
- **An actor on the root command**, so the writes that matter say who did them
  in the audit log.

### Changed

- The settings file had been written and never read. It is now read for the
  register path and the actor, behind the option and the environment.
- The found and conflict guards were being retyped in every repository. They are
  two functions in `store/guards.py` now, and two of the hand written copies had
  already drifted.
- The five truck cycle legs were five integer minute counts in four command
  signatures. They are one argument now, assembled inside the decorator.
- `demo seed` fills the rest of the plant as well as the day's concrete. Pass
  `--no-yard` for just the batching example.

### Fixed

- Two missing indexes, both the same mistake: a composite index whose leading
  column was not the one the query filtered on. Found by writing the probe set
  in `store/timing.py` and running it, not by anybody noticing it was slow.
- A benchmark table that had been interpolating between strength classes. The
  published tables step, and interpolating always favours the plant.
