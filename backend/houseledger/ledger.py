"""The household ledger: expenses, payments, balances, settle-up, undo.

This is the only place that calculates money. Callers (the MCP server, the seed
script) pass integer paise in and get integer paise out.

Balance convention: a positive balance means the household owes that member money;
a negative balance means the member owes the household. Balances always sum to zero.
"""

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import date as Date
from datetime import datetime, timezone

from .models import (
    CATEGORIES,
    MAX_AMOUNT_PAISE,
    Expense,
    Member,
    MonthlySummary,
    NotFoundError,
    Payment,
    Transfer,
    UndoResult,
    ValidationError,
)
from .money import format_inr
from .splits import SplitSpec, compute_shares

MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Ledger:
    def __init__(self, conn: sqlite3.Connection, now: Callable[[], datetime] | None = None):
        self.conn = conn
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ----------------------------------------------------------------- household

    def household_name(self) -> str:
        row = self.conn.execute("SELECT name FROM household WHERE id = 1").fetchone()
        return row["name"] if row else "Household"

    def set_household_name(self, name: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO household (id, name) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET name = excluded.name",
                (name,),
            )

    def add_member(self, name: str) -> Member:
        name = name.strip()
        if not name:
            raise ValidationError("A member needs a name.")
        try:
            with self.conn:
                cur = self.conn.execute("INSERT INTO members (name) VALUES (?)", (name,))
        except sqlite3.IntegrityError:
            raise ValidationError(f"{name} is already in this household.") from None
        return Member(id=cur.lastrowid, name=name, position=cur.lastrowid)

    def members(self) -> list[Member]:
        rows = self.conn.execute("SELECT id, name FROM members ORDER BY id").fetchall()
        return [Member(id=r["id"], name=r["name"], position=r["id"]) for r in rows]

    def member(self, name: str) -> Member:
        """Find a member by name, ignoring case and surrounding spaces."""
        row = self.conn.execute("SELECT id, name FROM members WHERE name = ? COLLATE NOCASE", (name.strip(),)).fetchone()
        if row is None:
            known = _join_names([m.name for m in self.members()])
            raise NotFoundError(f"I don't know anyone called {name.strip()} in this household. The members are {known}.")
        return Member(id=row["id"], name=row["name"], position=row["id"])

    # ------------------------------------------------------------------ expenses

    def preview_split(self, total_paise: int, split: SplitSpec) -> dict[str, int]:
        """Calculate a split without saving anything, so it can be read back for confirmation."""
        _check_amount(total_paise)
        return {m.name: paise for m, paise in compute_shares(total_paise, split, self.member).items()}

    def add_expense(
        self,
        *,
        actor: str,
        payer: str,
        total_paise: int,
        description: str,
        split: SplitSpec,
        category: str = "other",
        date: str | None = None,
        request_id: str | None = None,
    ) -> Expense:
        if request_id:
            row = self.conn.execute("SELECT id FROM expenses WHERE request_id = ?", (request_id,)).fetchone()
            if row:
                expense = self.get_expense(row["id"], include_deleted=True)
                expense.replayed = True
                return expense

        actor_m, payer_m = self.member(actor), self.member(payer)
        _check_amount(total_paise)
        description = _check_description(description)
        category = _check_category(category)
        date = _check_date(date) or self._today()
        shares = compute_shares(total_paise, split, self.member)

        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO expenses (payer_id, total_paise, description, category, date, split_json,
                                         created_by, created_at, request_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payer_m.id, total_paise, description, category, date, split.model_dump_json(),
                 actor_m.id, self._timestamp(), request_id),
            )
            expense_id = cur.lastrowid
            self._write_shares(expense_id, shares)
            self._audit(actor_m, "add_expense", "expense", expense_id, None, self._snapshot("expense", expense_id))
        return self.get_expense(expense_id)

    def edit_expense(
        self,
        *,
        actor: str,
        expense_id: int,
        payer: str | None = None,
        total_paise: int | None = None,
        description: str | None = None,
        split: SplitSpec | None = None,
        category: str | None = None,
        date: str | None = None,
    ) -> Expense:
        if all(v is None for v in (payer, total_paise, description, split, category, date)):
            raise ValidationError("Tell me what to change: the amount, payer, description, split, category or date.")
        actor_m = self.member(actor)
        current = self.get_expense(expense_id)

        new_payer = self.member(payer) if payer is not None else self.member(current.payer)
        new_total = total_paise if total_paise is not None else current.total_paise
        _check_amount(new_total)
        new_split = split if split is not None else SplitSpec.model_validate(current.split)
        shares = compute_shares(new_total, new_split, self.member)
        new_description = _check_description(description) if description is not None else current.description
        new_category = _check_category(category) if category is not None else current.category
        new_date = _check_date(date) or current.date

        before = self._snapshot("expense", expense_id)
        with self.conn:
            self.conn.execute(
                """UPDATE expenses SET payer_id = ?, total_paise = ?, description = ?, category = ?, date = ?,
                                       split_json = ? WHERE id = ?""",
                (new_payer.id, new_total, new_description, new_category, new_date,
                 new_split.model_dump_json(), expense_id),
            )
            self.conn.execute("DELETE FROM expense_shares WHERE expense_id = ?", (expense_id,))
            self._write_shares(expense_id, shares)
            self._audit(actor_m, "edit_expense", "expense", expense_id, before, self._snapshot("expense", expense_id))
        return self.get_expense(expense_id)

    def get_expense(self, expense_id: int, include_deleted: bool = False) -> Expense:
        row = self.conn.execute(
            """SELECT e.*, p.name AS payer_name, c.name AS creator_name FROM expenses e
               JOIN members p ON p.id = e.payer_id JOIN members c ON c.id = e.created_by
               WHERE e.id = ?""",
            (expense_id,),
        ).fetchone()
        if row is None or (row["deleted"] and not include_deleted):
            raise NotFoundError(f"I couldn't find expense number {expense_id}.")
        return self._expense_from_row(row)

    def list_expenses(
        self, *, limit: int = 10, month: str | None = None, category: str | None = None, member: str | None = None
    ) -> list[Expense]:
        sql = """SELECT e.*, p.name AS payer_name, c.name AS creator_name FROM expenses e
                 JOIN members p ON p.id = e.payer_id JOIN members c ON c.id = e.created_by
                 WHERE e.deleted = 0"""
        params: list = []
        if month is not None:
            sql += " AND substr(e.date, 1, 7) = ?"
            params.append(_check_month(month))
        if category is not None:
            sql += " AND e.category = ?"
            params.append(_check_category(category))
        if member is not None:
            m = self.member(member)
            sql += " AND (e.payer_id = ? OR e.id IN (SELECT expense_id FROM expense_shares WHERE member_id = ?))"
            params += [m.id, m.id]
        sql += " ORDER BY e.date DESC, e.id DESC LIMIT ?"
        params.append(max(1, min(limit, 100)))
        return [self._expense_from_row(r) for r in self.conn.execute(sql, params).fetchall()]

    # ------------------------------------------------------------------ payments

    def record_payment(
        self,
        *,
        actor: str,
        from_member: str,
        to_member: str,
        amount_paise: int,
        date: str | None = None,
        note: str = "",
        request_id: str | None = None,
    ) -> Payment:
        if request_id:
            row = self.conn.execute("SELECT id FROM payments WHERE request_id = ?", (request_id,)).fetchone()
            if row:
                payment = self.get_payment(row["id"], include_deleted=True)
                payment.replayed = True
                return payment

        actor_m, from_m, to_m = self.member(actor), self.member(from_member), self.member(to_member)
        if from_m.id == to_m.id:
            raise ValidationError("A payment needs two different people.")
        _check_amount(amount_paise)
        date = _check_date(date) or self._today()

        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO payments (from_id, to_id, amount_paise, date, note, created_by, created_at, request_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (from_m.id, to_m.id, amount_paise, date, note.strip(), actor_m.id, self._timestamp(), request_id),
            )
            payment_id = cur.lastrowid
            self._audit(actor_m, "record_payment", "payment", payment_id, None, self._snapshot("payment", payment_id))
        return self.get_payment(payment_id)

    def get_payment(self, payment_id: int, include_deleted: bool = False) -> Payment:
        row = self.conn.execute(
            """SELECT pay.*, f.name AS from_name, t.name AS to_name, c.name AS creator_name FROM payments pay
               JOIN members f ON f.id = pay.from_id JOIN members t ON t.id = pay.to_id
               JOIN members c ON c.id = pay.created_by WHERE pay.id = ?""",
            (payment_id,),
        ).fetchone()
        if row is None or (row["deleted"] and not include_deleted):
            raise NotFoundError(f"I couldn't find payment number {payment_id}.")
        return self._payment_from_row(row)

    def list_payments(self, *, limit: int = 10) -> list[Payment]:
        rows = self.conn.execute(
            """SELECT pay.*, f.name AS from_name, t.name AS to_name, c.name AS creator_name FROM payments pay
               JOIN members f ON f.id = pay.from_id JOIN members t ON t.id = pay.to_id
               JOIN members c ON c.id = pay.created_by WHERE pay.deleted = 0
               ORDER BY pay.date DESC, pay.id DESC LIMIT ?""",
            (max(1, min(limit, 100)),),
        ).fetchall()
        return [self._payment_from_row(r) for r in rows]

    # ------------------------------------------------------------ balances, settle

    def balances(self) -> dict[str, int]:
        """Net position per member, in household order. Positive = is owed money."""
        net = {m.id: 0 for m in self.members()}
        queries = (
            ("SELECT payer_id AS mid, SUM(total_paise) AS s FROM expenses WHERE deleted = 0 GROUP BY payer_id", 1),
            ("""SELECT sh.member_id AS mid, SUM(sh.share_paise) AS s FROM expense_shares sh
                JOIN expenses e ON e.id = sh.expense_id WHERE e.deleted = 0 GROUP BY sh.member_id""", -1),
            ("SELECT from_id AS mid, SUM(amount_paise) AS s FROM payments WHERE deleted = 0 GROUP BY from_id", 1),
            ("SELECT to_id AS mid, SUM(amount_paise) AS s FROM payments WHERE deleted = 0 GROUP BY to_id", -1),
        )
        for sql, sign in queries:
            for row in self.conn.execute(sql):
                net[row["mid"]] += sign * row["s"]
        return {m.name: net[m.id] for m in self.members()}

    def settle_up_plan(self) -> list[Transfer]:
        """Suggest payments that bring every balance to zero.

        Greedy: repeatedly the member who owes the most pays the member who is owed the
        most (ties broken by household order). This uses at most (members - 1) transfers
        and is usually the fewest, but is not guaranteed to be the theoretical minimum.
        """
        order = {m.name: m.position for m in self.members()}
        balance = {name: paise for name, paise in self.balances().items() if paise != 0}
        transfers: list[Transfer] = []
        while balance:
            debtor = min(balance, key=lambda n: (balance[n], order[n]))
            creditor = max(balance, key=lambda n: (balance[n], -order[n]))
            amount = min(-balance[debtor], balance[creditor])
            transfers.append(Transfer(from_member=debtor, to_member=creditor, amount_paise=amount))
            for name, delta in ((debtor, amount), (creditor, -amount)):
                balance[name] += delta
                if balance[name] == 0:
                    del balance[name]
        return transfers

    def monthly_summary(self, month: str | None = None) -> MonthlySummary:
        month = _check_month(month) if month else self._today()[:7]
        summary = MonthlySummary(month=month, total_paise=0, expense_count=0)
        for row in self.conn.execute(
            """SELECT category, COUNT(*) AS n, SUM(total_paise) AS s FROM expenses
               WHERE deleted = 0 AND substr(date, 1, 7) = ? GROUP BY category ORDER BY s DESC, category""",
            (month,),
        ):
            summary.by_category[row["category"]] = row["s"]
            summary.total_paise += row["s"]
            summary.expense_count += row["n"]
        for m in self.members():
            paid = self.conn.execute(
                """SELECT COALESCE(SUM(total_paise), 0) FROM expenses
                   WHERE deleted = 0 AND payer_id = ? AND substr(date, 1, 7) = ?""",
                (m.id, month),
            ).fetchone()[0]
            share = self.conn.execute(
                """SELECT COALESCE(SUM(sh.share_paise), 0) FROM expense_shares sh JOIN expenses e ON e.id = sh.expense_id
                   WHERE e.deleted = 0 AND sh.member_id = ? AND substr(e.date, 1, 7) = ?""",
                (m.id, month),
            ).fetchone()[0]
            summary.paid_by_member[m.name] = paid
            summary.share_by_member[m.name] = share
        return summary

    # ---------------------------------------------------------------------- undo

    def undo_last(self, *, actor: str) -> UndoResult:
        """Undo the actor's most recent expense, edit or payment.

        Refuses if someone changed that entry afterwards, so an undo never silently
        discards another person's change.
        """
        actor_m = self.member(actor)
        row = self.conn.execute(
            "SELECT * FROM audit WHERE actor_id = ? AND undoable = 1 AND undone = 0 ORDER BY id DESC LIMIT 1",
            (actor_m.id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"There's nothing of {actor_m.name}'s to undo.")

        entity, entity_id = row["entity"], row["entity_id"]
        current = self._snapshot(entity, entity_id)
        if json.loads(row["after_json"]) != json.loads(json.dumps(current)):
            raise ValidationError(f"That {entity} was changed after your last action, so I can't undo it safely.")

        before = json.loads(row["before_json"]) if row["before_json"] else None
        with self.conn:
            if row["action"] in ("add_expense", "record_payment"):
                table = "expenses" if entity == "expense" else "payments"
                self.conn.execute(f"UPDATE {table} SET deleted = 1 WHERE id = ?", (entity_id,))
            else:  # edit_expense
                self._restore_expense(before)
            self.conn.execute("UPDATE audit SET undone = 1 WHERE id = ?", (row["id"],))
            self._audit(actor_m, "undo", entity, entity_id, current, self._snapshot(entity, entity_id), undoable=False)

        summary = _describe_undo(row["action"], current)
        return UndoResult(action=row["action"], entity=entity, entity_id=entity_id, summary=summary)

    # ------------------------------------------------------------------ internals

    def _today(self) -> str:
        return self._now().date().isoformat()

    def _timestamp(self) -> str:
        return self._now().isoformat(timespec="seconds")

    def _write_shares(self, expense_id: int, shares: dict[Member, int]) -> None:
        self.conn.executemany(
            "INSERT INTO expense_shares (expense_id, member_id, share_paise) VALUES (?, ?, ?)",
            [(expense_id, m.id, paise) for m, paise in shares.items()],
        )

    def _audit(self, actor: Member, action: str, entity: str, entity_id: int, before, after, undoable=True) -> None:
        self.conn.execute(
            """INSERT INTO audit (actor_id, action, entity, entity_id, before_json, after_json, at, undoable)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (actor.id, action, entity, entity_id, json.dumps(before) if before is not None else None,
             json.dumps(after), self._timestamp(), int(undoable)),
        )

    def _snapshot(self, entity: str, entity_id: int) -> dict:
        if entity == "expense":
            row = self.conn.execute(
                """SELECT id, payer_id, total_paise, description, category, date, split_json, deleted
                   FROM expenses WHERE id = ?""",
                (entity_id,),
            ).fetchone()
            shares = self.conn.execute(
                "SELECT member_id, share_paise FROM expense_shares WHERE expense_id = ? ORDER BY member_id",
                (entity_id,),
            ).fetchall()
            return {**dict(row), "shares": [[s["member_id"], s["share_paise"]] for s in shares]}
        row = self.conn.execute(
            "SELECT id, from_id, to_id, amount_paise, date, note, deleted FROM payments WHERE id = ?", (entity_id,)
        ).fetchone()
        return dict(row)

    def _restore_expense(self, snap: dict) -> None:
        self.conn.execute(
            """UPDATE expenses SET payer_id = ?, total_paise = ?, description = ?, category = ?, date = ?,
                                   split_json = ?, deleted = ? WHERE id = ?""",
            (snap["payer_id"], snap["total_paise"], snap["description"], snap["category"], snap["date"],
             snap["split_json"], snap["deleted"], snap["id"]),
        )
        self.conn.execute("DELETE FROM expense_shares WHERE expense_id = ?", (snap["id"],))
        self.conn.executemany(
            "INSERT INTO expense_shares (expense_id, member_id, share_paise) VALUES (?, ?, ?)",
            [(snap["id"], mid, paise) for mid, paise in snap["shares"]],
        )

    def _expense_from_row(self, row: sqlite3.Row) -> Expense:
        shares = self.conn.execute(
            """SELECT m.name, sh.share_paise FROM expense_shares sh JOIN members m ON m.id = sh.member_id
               WHERE sh.expense_id = ? ORDER BY m.id""",
            (row["id"],),
        ).fetchall()
        return Expense(
            id=row["id"],
            payer=row["payer_name"],
            total_paise=row["total_paise"],
            description=row["description"],
            category=row["category"],
            date=row["date"],
            shares={s["name"]: s["share_paise"] for s in shares},
            split=json.loads(row["split_json"]),
            created_by=row["creator_name"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _payment_from_row(row: sqlite3.Row) -> Payment:
        return Payment(
            id=row["id"],
            from_member=row["from_name"],
            to_member=row["to_name"],
            amount_paise=row["amount_paise"],
            date=row["date"],
            note=row["note"],
            created_by=row["creator_name"],
            created_at=row["created_at"],
        )


def _check_amount(paise: int) -> None:
    if isinstance(paise, bool) or not isinstance(paise, int):
        raise ValidationError("Amounts must be whole paise.")
    if paise <= 0:
        raise ValidationError("The amount must be more than zero.")
    if paise > MAX_AMOUNT_PAISE:
        raise ValidationError(f"That's more than {format_inr(MAX_AMOUNT_PAISE)}. Please check the amount.")


def _check_description(description: str) -> str:
    description = description.strip()
    if not description:
        raise ValidationError("What was this expense for?")
    if len(description) > 200:
        raise ValidationError("Please keep the description under 200 characters.")
    return description


def _check_category(category: str) -> str:
    category = category.strip().lower()
    if category not in CATEGORIES:
        raise ValidationError(f"'{category}' isn't a category. Use one of: {', '.join(CATEGORIES)}.")
    return category


def _check_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return Date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValidationError(f"'{value}' isn't a date in YYYY-MM-DD form.") from None


def _check_month(value: str) -> str:
    if not MONTH_RE.match(value):
        raise ValidationError(f"'{value}' isn't a month in YYYY-MM form.")
    return value


def _join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names) or "nobody yet"
    return ", ".join(names[:-1]) + " and " + names[-1]


def _describe_undo(action: str, snap: dict) -> str:
    if action == "add_expense":
        return f"Removed the {format_inr(snap['total_paise'])} expense for {snap['description']}."
    if action == "edit_expense":
        return f"Reverted your last change to the {snap['description']} expense."
    return f"Removed the {format_inr(snap['amount_paise'])} payment."
