"""Turn ledger results into what an Alexa-style host needs.

Every tool result has three parts:
- speech:  1-3 short sentences an assistant can say aloud;
- data:    structured facts (ids, amounts in paise and formatted rupees);
- display: a card for a screen device, {"card": <type>, "data": {...}}.

These functions only format results. They never calculate money: every amount comes
from the ledger.
"""

from datetime import date

from pydantic import BaseModel

from .ledger import Ledger
from .models import Expense, MonthlySummary, Payment, Transfer, UndoResult
from .money import format_inr


class ToolOutput(BaseModel):
    speech: str
    data: dict
    display: dict


def money(paise: int) -> dict:
    return {"paise": paise, "text": format_inr(paise)}


def balances_data(balances: dict[str, int]) -> list[dict]:
    """One entry per member, with a word for the status so screens don't rely on colour alone."""
    out = []
    for name, paise in balances.items():
        status = "is_owed" if paise > 0 else "owes" if paise < 0 else "settled"
        out.append({"member": name, "net": money(paise), "owes": money(max(-paise, 0)),
                    "is_owed": money(max(paise, 0)), "status": status})
    return out


def balances_speech(balances: dict[str, int]) -> str:
    if all(paise == 0 for paise in balances.values()):
        return "Everyone is settled up."
    parts = []
    for name, paise in balances.items():
        if paise > 0:
            parts.append(f"{name} is owed {format_inr(paise)}")
        elif paise < 0:
            parts.append(f"{name} owes {format_inr(-paise)}")
        else:
            parts.append(f"{name} is settled up")
    return _sentence(parts) + "."


def expense_data(e: Expense) -> dict:
    return {
        "id": e.id,
        "payer": e.payer,
        "amount": money(e.total_paise),
        "description": e.description,
        "category": e.category,
        "date": e.date,
        "shares": [{"member": name, "amount": money(paise)} for name, paise in e.shares.items()],
        "created_by": e.created_by,
    }


def payment_data(p: Payment) -> dict:
    return {"id": p.id, "from": p.from_member, "to": p.to_member, "amount": money(p.amount_paise),
            "date": p.date, "note": p.note, "created_by": p.created_by}


# ----------------------------------------------------------------------- per tool


def members(ledger: Ledger) -> ToolOutput:
    names = [m.name for m in ledger.members()]
    data = {"household": ledger.household_name(), "members": names}
    return ToolOutput(
        speech=f"This household has {_sentence(names)}." if names else "This household has no members yet.",
        data=data,
        display={"card": "members", "data": data},
    )


def preview(payer: str, total_paise: int, description: str, shares: dict[str, int]) -> ToolOutput:
    share_list = [{"member": name, "amount": money(paise)} for name, paise in shares.items()]
    parts = [f"{name} {format_inr(paise)}" for name, paise in shares.items()]
    what = f" for {description}" if description else ""
    data = {"payer": payer, "amount": money(total_paise), "description": description, "shares": share_list,
            "saved": False}
    return ToolOutput(
        speech=f"{format_inr(total_paise)}{what}, paid by {payer}, split as {_sentence(parts)}. Shall I save it?",
        data=data,
        display={"card": "confirm_split", "data": data},
    )


def expense_saved(e: Expense, balances: dict[str, int], status: str) -> ToolOutput:
    """status is 'added', 'updated' or 'already_saved' (an idempotent retry)."""
    others = [f"{name}'s share is {format_inr(paise)}" for name, paise in e.shares.items() if name != e.payer]
    if status == "already_saved":
        speech = f"That {format_inr(e.total_paise)} expense for {e.description} was already saved."
    else:
        verb = "Saved" if status == "added" else "Updated"
        speech = f"{verb}: {format_inr(e.total_paise)} for {e.description}, paid by {e.payer}."
        if others:
            speech += " " + _sentence(others) + "."
    data = {"status": status, "expense": expense_data(e), "balances": balances_data(balances)}
    return ToolOutput(speech=speech, data=data, display={"card": "expense_added", "data": data})


def payment_saved(p: Payment, balances: dict[str, int]) -> ToolOutput:
    if p.replayed:
        speech = f"That payment of {format_inr(p.amount_paise)} from {p.from_member} was already recorded."
    else:
        speech = f"Recorded: {p.from_member} paid {p.to_member} {format_inr(p.amount_paise)}."
    data = {"payment": payment_data(p), "already_recorded": p.replayed, "balances": balances_data(balances)}
    headline = f"{p.from_member} paid {p.to_member} {format_inr(p.amount_paise)}"
    return ToolOutput(speech=speech, data=data,
                      display={"card": "balances", "data": {"headline": headline, "balances": data["balances"]}})


def undone(result: UndoResult, balances: dict[str, int]) -> ToolOutput:
    data = {"undone": {"action": result.action, "entity": result.entity, "id": result.entity_id},
            "balances": balances_data(balances)}
    return ToolOutput(speech=f"Done. {result.summary}", data=data,
                      display={"card": "balances", "data": {"headline": result.summary,
                                                            "balances": data["balances"]}})


def balances(ledger: Ledger) -> ToolOutput:
    current = ledger.balances()
    data = {"household": ledger.household_name(), "balances": balances_data(current)}
    return ToolOutput(speech=balances_speech(current), data=data,
                      display={"card": "balances", "data": {"headline": "Who owes what", **data}})


def settle_up(transfers: list[Transfer]) -> ToolOutput:
    items = [{"from": t.from_member, "to": t.to_member, "amount": money(t.amount_paise)} for t in transfers]
    if not transfers:
        speech = "Everyone is already settled up. No payments needed."
    else:
        steps = [f"{t.from_member} pays {t.to_member} {format_inr(t.amount_paise)}" for t in transfers]
        count = "one payment" if len(transfers) == 1 else f"{len(transfers)} payments"
        speech = f"To settle up: {_sentence(steps)}. That's {count}."
    data = {"transfers": items, "count": len(items),
            "note": "Suggested payments only. Nothing is paid until someone records it."}
    return ToolOutput(speech=speech, data=data, display={"card": "settle_up", "data": data})


def expense_list(expenses: list[Expense], payments: list[Payment]) -> ToolOutput:
    if not expenses:
        speech = "There are no expenses matching that."
    else:
        latest = expenses[0]
        noun = "expense" if len(expenses) == 1 else f"{len(expenses)} expenses"
        speech = (f"Here {'is the latest' if len(expenses) == 1 else 'are the latest ' + noun}. "
                  f"The most recent is {format_inr(latest.total_paise)} for {latest.description}, "
                  f"paid by {latest.payer} on {_spoken_date(latest.date)}.")
    data = {"expenses": [expense_data(e) for e in expenses], "payments": [payment_data(p) for p in payments]}
    return ToolOutput(speech=speech, data=data, display={"card": "expense_list", "data": data})


def monthly(summary: MonthlySummary) -> ToolOutput:
    month_name = date.fromisoformat(summary.month + "-01").strftime("%B %Y")
    if summary.expense_count == 0:
        speech = f"There were no shared expenses in {month_name}."
    else:
        top_category, top_paise = next(iter(summary.by_category.items()))
        count = "1 expense" if summary.expense_count == 1 else f"{summary.expense_count} expenses"
        speech = (f"In {month_name}, the household spent {format_inr(summary.total_paise)} across {count}. "
                  f"The biggest category was {top_category} at {format_inr(top_paise)}.")
    data = {
        "month": summary.month,
        "month_name": month_name,
        "total": money(summary.total_paise),
        "expense_count": summary.expense_count,
        "by_category": [{"category": c, "amount": money(p)} for c, p in summary.by_category.items()],
        "by_member": [{"member": m, "paid": money(summary.paid_by_member[m]),
                       "share": money(summary.share_by_member[m])} for m in summary.paid_by_member],
    }
    return ToolOutput(speech=speech, data=data, display={"card": "monthly_summary", "data": data})


def _sentence(parts: list[str]) -> str:
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _spoken_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')}"
