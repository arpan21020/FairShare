from datetime import datetime, timezone

import pytest

from houseledger.db import connect
from houseledger.ledger import Ledger


@pytest.fixture
def ledger() -> Ledger:
    """An in-memory ledger with Aarav, Priya and Sam, and a fixed clock (2026-10-22)."""
    ledger = Ledger(connect(":memory:"), now=lambda: datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc))
    for name in ("Aarav", "Priya", "Sam"):
        ledger.add_member(name)
    return ledger
