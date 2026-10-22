import random

import pytest

from houseledger.db import connect
from houseledger.ledger import Ledger
from houseledger.models import NotFoundError, Transfer, ValidationError
from houseledger.seed import create_household, seed
from houseledger.splits import SplitSpec

ALL = ["Aarav", "Priya", "Sam"]


def add(ledger, payer="Aarav", total=90000, actor=None, split=None, **kwargs):
    return ledger.add_expense(actor=actor or payer, payer=payer, total_paise=total, description="Groceries",
                              split=split or SplitSpec(participants=ALL), category="groceries", **kwargs)


def test_add_expense_and_balances(ledger):
    expense = add(ledger)
    assert expense.shares == {"Aarav": 30000, "Priya": 30000, "Sam": 30000}
    assert expense.date == "2026-10-22"  # defaults to today
    assert ledger.balances() == {"Aarav": 60000, "Priya": -30000, "Sam": -30000}


def test_demo_conversation_balances(ledger):
    add(ledger, total=240000, split=SplitSpec(method="weights", weights={"Aarav": 1, "Priya": 1, "Sam": 0.5}))
    assert ledger.balances() == {"Aarav": 144000, "Priya": -96000, "Sam": -48000}
    assert ledger.settle_up_plan() == [
        Transfer("Priya", "Aarav", 96000),
        Transfer("Sam", "Aarav", 48000),
    ]


def test_payment_reduces_debt(ledger):
    add(ledger)
    ledger.record_payment(actor="Priya", from_member="Priya", to_member="Aarav", amount_paise=30000)
    assert ledger.balances() == {"Aarav": 30000, "Priya": 0, "Sam": -30000}
    assert ledger.settle_up_plan() == [Transfer("Sam", "Aarav", 30000)]


def test_payment_validation(ledger):
    with pytest.raises(ValidationError, match="two different"):
        ledger.record_payment(actor="Sam", from_member="Sam", to_member="sam", amount_paise=100)
    with pytest.raises(ValidationError, match="more than zero"):
        ledger.record_payment(actor="Sam", from_member="Sam", to_member="Aarav", amount_paise=0)


def test_settle_up_clears_all_balances(ledger):
    add(ledger, payer="Aarav", total=45_000_00)
    add(ledger, payer="Priya", total=3_150_00)
    add(ledger, payer="Sam", total=999_00, split=SplitSpec(method="weights", weights={"Aarav": 2, "Sam": 1}))
    plan = ledger.settle_up_plan()
    assert len(plan) <= 2
    for t in plan:
        ledger.record_payment(actor=t.from_member, from_member=t.from_member, to_member=t.to_member,
                              amount_paise=t.amount_paise)
    assert set(ledger.balances().values()) == {0}
    assert ledger.settle_up_plan() == []


def test_balances_always_sum_to_zero_random_operations(ledger):
    rng = random.Random(42)
    for _ in range(200):
        a, b = rng.sample(ALL, 2)
        if rng.random() < 0.7:
            weights = {name: rng.choice([0.5, 1, 1.5, 2]) for name in rng.sample(ALL, rng.randint(1, 3))}
            add(ledger, payer=a, total=rng.randint(1, 5_000_00), split=SplitSpec(method="weights", weights=weights))
        else:
            ledger.record_payment(actor=a, from_member=a, to_member=b, amount_paise=rng.randint(1, 2_000_00))
        if rng.random() < 0.1:
            try:
                ledger.undo_last(actor=a)
            except NotFoundError:
                pass  # nothing left to undo for this member
        assert sum(ledger.balances().values()) == 0
    for t in ledger.settle_up_plan():
        ledger.record_payment(actor=t.from_member, from_member=t.from_member, to_member=t.to_member,
                              amount_paise=t.amount_paise)
    assert set(ledger.balances().values()) == {0}


def test_undo_add_expense(ledger):
    expense = add(ledger)
    result = ledger.undo_last(actor="Aarav")
    assert result.action == "add_expense"
    assert "₹900" in result.summary
    assert set(ledger.balances().values()) == {0}
    with pytest.raises(NotFoundError):
        ledger.get_expense(expense.id)


def test_undo_is_per_actor(ledger):
    add(ledger, payer="Aarav")
    add(ledger, payer="Priya", total=30000)
    ledger.undo_last(actor="Aarav")  # removes Aarav's expense, not Priya's later one
    assert [e.payer for e in ledger.list_expenses()] == ["Priya"]
    with pytest.raises(NotFoundError, match="nothing of Aarav's"):
        ledger.undo_last(actor="Aarav")


def test_undo_payment(ledger):
    add(ledger)
    ledger.record_payment(actor="Sam", from_member="Sam", to_member="Aarav", amount_paise=30000)
    assert ledger.undo_last(actor="Sam").action == "record_payment"
    assert ledger.balances() == {"Aarav": 60000, "Priya": -30000, "Sam": -30000}


def test_edit_expense_and_undo_edit(ledger):
    expense = add(ledger)
    edited = ledger.edit_expense(actor="Aarav", expense_id=expense.id, total_paise=60000)
    assert edited.shares == {"Aarav": 20000, "Priya": 20000, "Sam": 20000}  # original split re-applied
    edited = ledger.edit_expense(actor="Aarav", expense_id=expense.id,
                                 split=SplitSpec(participants=["Aarav", "Priya"]))
    assert edited.shares == {"Aarav": 30000, "Priya": 30000}
    ledger.undo_last(actor="Aarav")
    assert ledger.get_expense(expense.id).shares == {"Aarav": 20000, "Priya": 20000, "Sam": 20000}
    ledger.undo_last(actor="Aarav")
    assert ledger.get_expense(expense.id).total_paise == 90000


def test_edit_requires_a_change(ledger):
    expense = add(ledger)
    with pytest.raises(ValidationError, match="what to change"):
        ledger.edit_expense(actor="Aarav", expense_id=expense.id)


def test_undo_refuses_if_someone_changed_it_since(ledger):
    expense = add(ledger)
    ledger.edit_expense(actor="Priya", expense_id=expense.id, description="Groceries and snacks")
    with pytest.raises(ValidationError, match="changed after"):
        ledger.undo_last(actor="Aarav")
    assert ledger.get_expense(expense.id).description == "Groceries and snacks"


def test_idempotent_retry(ledger):
    first = add(ledger, request_id="req-1")
    again = add(ledger, request_id="req-1")
    assert again.id == first.id and again.replayed
    assert len(ledger.list_expenses()) == 1
    p1 = ledger.record_payment(actor="Sam", from_member="Sam", to_member="Aarav", amount_paise=100, request_id="p-1")
    p2 = ledger.record_payment(actor="Sam", from_member="Sam", to_member="Aarav", amount_paise=100, request_id="p-1")
    assert p2.id == p1.id and p2.replayed
    assert len(ledger.list_payments()) == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"category": "gadgets"}, "isn't a category"),
        ({"date": "22/10/2026"}, "YYYY-MM-DD"),
        ({"payer": "Raj"}, "anyone called Raj"),
    ],
)
def test_add_expense_validation(ledger, kwargs, message):
    args = {"actor": "Aarav", "payer": "Aarav", "total_paise": 100, "description": "x",
            "split": SplitSpec(participants=ALL), **kwargs}
    with pytest.raises((ValidationError, NotFoundError), match=message):
        ledger.add_expense(**args)


def test_blank_description(ledger):
    with pytest.raises(ValidationError, match="What was this"):
        ledger.add_expense(actor="Aarav", payer="Aarav", total_paise=100, description="  ",
                           split=SplitSpec(participants=ALL))


def test_list_expenses_filters(ledger):
    add(ledger, payer="Aarav", date="2026-09-30")
    add(ledger, payer="Priya", date="2026-10-02", split=SplitSpec(participants=["Priya", "Sam"]))
    assert len(ledger.list_expenses(month="2026-10")) == 1
    assert [e.payer for e in ledger.list_expenses(member="Aarav")] == ["Aarav"]
    assert len(ledger.list_expenses(member="Sam")) == 2
    with pytest.raises(ValidationError):
        ledger.list_expenses(month="October")


def test_monthly_summary(ledger):
    add(ledger, payer="Aarav", total=90000, date="2026-10-02")
    ledger.add_expense(actor="Priya", payer="Priya", total_paise=30000, description="Power", category="utilities",
                       split=SplitSpec(participants=ALL), date="2026-10-05")
    add(ledger, payer="Sam", total=99900, date="2026-09-29")  # different month
    summary = ledger.monthly_summary("2026-10")
    assert summary.total_paise == 120000
    assert summary.expense_count == 2
    assert summary.by_category == {"groceries": 90000, "utilities": 30000}
    assert summary.paid_by_member == {"Aarav": 90000, "Priya": 30000, "Sam": 0}
    assert summary.share_by_member == {"Aarav": 40000, "Priya": 40000, "Sam": 40000}
    assert ledger.monthly_summary().month == "2026-10"  # defaults to the current month


def test_data_survives_reopening_the_database(tmp_path):
    path = tmp_path / "ledger.db"
    first = Ledger(connect(path))
    seed(first)
    balances = first.balances()
    first.conn.close()

    reopened = Ledger(connect(path))
    assert reopened.balances() == balances
    assert [m.name for m in reopened.members()] == ALL


def test_seed_is_idempotent_and_balanced(tmp_path):
    ledger = Ledger(connect(tmp_path / "ledger.db"))
    seed(ledger)
    seed(ledger)
    assert len(ledger.list_expenses(limit=100)) == 7
    assert len(ledger.list_payments()) == 1
    assert sum(ledger.balances().values()) == 0
    assert ledger.household_name().endswith("(seeded demo data)")


def test_empty_household_has_members_but_no_history(tmp_path):
    ledger = Ledger(connect(tmp_path / "ledger.db"))
    create_household(ledger)
    assert [m.name for m in ledger.members()] == ALL
    assert ledger.list_expenses() == [] and ledger.list_payments() == []
    assert ledger.balances() == {"Aarav": 0, "Priya": 0, "Sam": 0}
    assert ledger.settle_up_plan() == []


def test_duplicate_member_name(ledger):
    with pytest.raises(ValidationError, match="already"):
        ledger.add_member("priya")
