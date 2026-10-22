"""Create the demo household (Aarav, Priya, Sam), optionally with a few weeks of SEEDED
(fictional) expenses.

Usage:  uv run python -m houseledger.seed [--reset] [--empty] [--db PATH]

  --reset   delete the database first
  --empty   members only: no expenses or payments, so every balance starts at zero

Re-running is safe: every seeded entry has a fixed request_id, so nothing is duplicated.
"""

import argparse
import sys
from pathlib import Path

from .db import connect, db_path_from_env
from .ledger import Ledger
from .models import ValidationError
from .money import format_inr
from .splits import ExclusiveItem, SplitSpec

HOUSEHOLD_NAME = "Demo flat (seeded demo data)"
EMPTY_HOUSEHOLD_NAME = "Demo flat"
MEMBERS = ("Aarav", "Priya", "Sam")
ALL = list(MEMBERS)


def create_household(ledger: Ledger, name: str = EMPTY_HOUSEHOLD_NAME) -> None:
    """Name the household and add the members, with no expenses or payments."""
    ledger.set_household_name(name)
    existing = {m.name for m in ledger.members()}
    for member in MEMBERS:
        if member not in existing:
            ledger.add_member(member)


def seed(ledger: Ledger) -> None:
    create_household(ledger, HOUSEHOLD_NAME)

    expenses = [
        ("seed-rent-oct", "Aarav", 45_000_00, "October rent", "rent", "2026-10-01", SplitSpec(participants=ALL)),
        ("seed-wifi-oct", "Sam", 999_00, "Wi-Fi bill", "utilities", "2026-10-03", SplitSpec(participants=ALL)),
        ("seed-groc-1", "Priya", 1_860_00, "Weekly groceries", "groceries", "2026-10-05",
         SplitSpec(participants=ALL)),
        ("seed-elec-oct", "Priya", 3_150_00, "Electricity bill", "utilities", "2026-10-08",
         SplitSpec(participants=ALL)),
        ("seed-pizza", "Sam", 1_400_00, "Friday pizza night", "food", "2026-10-10",
         SplitSpec(participants=ALL, exclusive_items=[
             ExclusiveItem(amount_paise=350_00, members=["Sam"], description="Sam's extra garlic bread"),
         ])),
        ("seed-groc-2", "Aarav", 2_240_00, "Weekly groceries", "groceries", "2026-10-12",
         SplitSpec(participants=ALL)),
        ("seed-cleaning", "Priya", 600_00, "Cleaning supplies", "household", "2026-10-15",
         SplitSpec(participants=ALL)),
    ]
    for request_id, payer, total, description, category, date, split in expenses:
        ledger.add_expense(actor=payer, payer=payer, total_paise=total, description=description,
                           split=split, category=category, date=date, request_id=request_id)

    ledger.record_payment(actor="Sam", from_member="Sam", to_member="Aarav", amount_paise=10_000_00,
                          date="2026-10-06", note="Part of October rent", request_id="seed-pay-sam-rent")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=db_path_from_env())
    parser.add_argument("--reset", action="store_true", help="delete the database first")
    parser.add_argument("--empty", action="store_true", help="members only, no expenses or payments")
    args = parser.parse_args()

    if args.reset and args.db.exists():
        try:
            args.db.unlink()
        except PermissionError:
            raise SystemExit("The database is in use. Stop the MCP server first, then run this again.")
    ledger = Ledger(connect(args.db))
    try:
        create_household(ledger) if args.empty else seed(ledger)
    except ValidationError as err:
        raise SystemExit(f"Seeding failed: {err}")
    sys.stdout.reconfigure(encoding="utf-8")  # the Windows console defaults to cp1252, which lacks ₹
    print(f"Created {ledger.household_name()} in {args.db}")
    for name, paise in ledger.balances().items():
        print(f"  {name:6} {format_inr(paise):>12}")


if __name__ == "__main__":
    main()
