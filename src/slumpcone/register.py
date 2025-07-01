"""One handle on the whole register.

Every repository takes the same database and none of them owns it, so
something has to open the file, run the migrations and hand the repositories
out. That is all this is. It deliberately does not wrap the repositories in
methods of its own: a facade that re-exports forty methods is a second API to
keep in step with the first, and the repositories are already the API.

The one thing it does add is the health check, which is the question an
operator actually asks of a register file: is this the schema this build
expects, and how much is in it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import TracebackType

from slumpcone.store.account_repo import AccountRepository
from slumpcone.store.audit import AuditLog
from slumpcone.store.batch_repo import BatchRepository
from slumpcone.store.bleeding_repo import BleedingRepository
from slumpcone.store.carbon_repo import CarbonRepository
from slumpcone.store.db import Database
from slumpcone.store.delivery_repo import DeliveryRepository
from slumpcone.store.fresh_repo import FreshTestRepository
from slumpcone.store.hardened_repo import HardenedRepository
from slumpcone.store.haul_repo import HaulRepository
from slumpcone.store.ingest_repo import IngestRepository
from slumpcone.store.inventory_repo import InventoryRepository
from slumpcone.store.invoice_repo import InvoiceRepository
from slumpcone.store.materials_repo import MaterialRepository
from slumpcone.store.maturity_repo import MaturityRepository
from slumpcone.store.migrations import current_version, load_migrations, migrate, verify
from slumpcone.store.mixdesign_repo import MixDesignRepository
from slumpcone.store.order_repo import OrderRepository
from slumpcone.store.people_repo import PeopleRepository
from slumpcone.store.plant_repo import PlantRepository
from slumpcone.store.pricing_repo import PricingRepository
from slumpcone.store.project_repo import ProjectRepository
from slumpcone.store.reclaim_repo import ReclaimRepository
from slumpcone.store.strength_repo import StrengthRepository
from slumpcone.store.uniformity_repo import UniformityRepository

# The tables a health check counts rows in, in the order a report reads them.
COUNTED_TABLES = (
    "material",
    "plant",
    "mix_design",
    "batch_ticket",
    "fresh_test",
    "specimen_set",
    "break_result",
    "delivery",
    "project",
    "concrete_order",
    "material_receipt",
    "inventory_movement",
    "ingest_run",
    "material_price",
    "audit_event",
    "flexural_break",
    "concrete_core",
    "maturity_curve",
    "bleed_test",
    "uniformity_test",
    "emission_factor",
    "technician",
    "returned_concrete",
    "temperature_log",
    "account",
    "invoice",
)


@dataclass(frozen=True, slots=True)
class RegisterHealth:
    """What a health check found."""

    path: str
    schema_version: int
    expected_version: int
    counts: dict[str, int]

    @property
    def is_current(self) -> bool:
        """True when the file is at the schema this build ships."""
        return self.schema_version == self.expected_version

    @property
    def total_rows(self) -> int:
        """Everything in the counted tables."""
        return sum(self.counts.values())

    @property
    def is_empty(self) -> bool:
        """True when nothing has been filed yet."""
        return self.total_rows == 0


class Register:
    """An open register, with a repository for each part of it."""

    def __init__(self, database: Database, path: str = ":memory:") -> None:
        self._db = database
        self.path = path
        self.materials = MaterialRepository(database)
        self.plants = PlantRepository(database)
        self.mixes = MixDesignRepository(database)
        self.batches = BatchRepository(database)
        self.fresh = FreshTestRepository(database)
        self.strength = StrengthRepository(database)
        self.deliveries = DeliveryRepository(database)
        self.projects = ProjectRepository(database)
        self.orders = OrderRepository(database)
        self.inventory = InventoryRepository(database)
        self.ingest = IngestRepository(database)
        self.prices = PricingRepository(database)
        self.audit = AuditLog(database)
        self.hardened = HardenedRepository(database)
        self.maturity = MaturityRepository(database)
        self.bleeding = BleedingRepository(database)
        self.uniformity = UniformityRepository(database)
        self.carbon = CarbonRepository(database)
        self.haul = HaulRepository(database)
        self.people = PeopleRepository(database)
        self.reclaim = ReclaimRepository(database)
        self.accounts = AccountRepository(database)
        self.invoices = InvoiceRepository(database)

    @classmethod
    def open(cls, path: str | Path) -> Register:
        """Open, create and migrate the register at ``path``."""
        database = Database.open(path)
        migrate(database)
        return cls(database, str(path))

    @classmethod
    def in_memory(cls) -> Register:
        """A register that lives only as long as this process."""
        database = Database.in_memory()
        migrate(database)
        return cls(database)

    @property
    def database(self) -> Database:
        """The underlying connection, for anything the repositories do not do."""
        return self._db

    def health(self) -> RegisterHealth:
        """Schema version and row counts."""
        verify(self._db)
        counts: dict[str, int] = {}
        present = set(self._db.table_names())
        for table in COUNTED_TABLES:
            if table in present:
                counts[table] = int(self._db.scalar(f"SELECT count(*) FROM {table}") or 0)
        return RegisterHealth(
            self.path, current_version(self._db), len(load_migrations()), counts
        )

    def day_summary(self, on: date) -> dict[str, int]:
        """How much of each kind of record a day carries."""
        return {
            "tickets": len(self.batches.between(on, on)),
            "fresh tests": len(self.fresh.between(on, on)),
            "deliveries": len(self.deliveries.between(on, on)),
            "receipts": 0,
        }

    def close(self) -> None:
        """Close the connection."""
        self._db.close()

    def __enter__(self) -> Register:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
