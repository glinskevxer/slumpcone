# slumpcone

Ready-mix concrete production, quality control and delivery compliance.

The plant proportions a mix design into a truck, a technician tests the load at
the point of discharge, cylinders are cast and broken at 7 and 28 days, and the
producer has to be able to show the concrete met the specification. slumpcone is
the register all of that lands in.

## Try it

```
pip install -e ".[dev]"
slumpcone --register demo.sqlite3 demo seed
slumpcone --register demo.sqlite3 demo tour
```

`demo seed` files one plant, one paving mixture and one day's work, with a load
that fails its slump and a set of cylinders that comes out low, so the reports
have something to say.

## What it holds

- **Materials** and the certificates that have to cover them on the day a load
  was batched
- **Mix designs**, one row per revision, checked against exposure classes and
  their own absolute volume yield
- **Batches**, moisture corrected, against ASTM C94 weighing tolerances
- **Fresh tests** and the one retest each property is allowed
- **Cylinders and breaks**, and the two ACI strength acceptance rules
- **Deliveries**, discharge limits and water added at the job
- **Projects, classes and submittals**, with approvals that expire
- **Inventory**, as a movement ledger rather than a level
- **Imports** from batch recorders, laboratories and suppliers

## The register

One SQLite file. `slumpcone register init` creates it and brings it to the
current schema; `slumpcone register info` says what is in it. The path comes
from `--register`, then `$SLUMPCONE_REGISTER`, then `./slumpcone.sqlite3`.
