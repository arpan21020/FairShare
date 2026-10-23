"""HouseLedger MCP server (Streamable HTTP).

Run:   uv run python -m houseledger.mcp_server [--host 127.0.0.1] [--port 8010] [--db PATH] [--seed]
URL:   http://127.0.0.1:8010/mcp     Health: http://127.0.0.1:8010/health

Built on the official MCP Python SDK. Clients may negotiate MCP spec 2025-11-25 (the
initialize handshake) or 2026-07-28.

Every tool returns a short spoken reply as text content, plus structured content
{speech, data, display} for hosts with a screen. All money is calculated by the ledger
in integer paise; tool inputs take rupees for convenience and convert them exactly.
"""

import argparse
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import presenters
from .db import connect, db_path_from_env
from .ledger import Ledger
from .models import CATEGORIES, LedgerError
from .money import rupees_to_paise
from .presenters import ToolOutput
from .seed import create_household, seed
from .splits import ExclusiveItem, SplitSpec

INSTRUCTIONS = """\
HouseLedger keeps a household's shared expenses. You are the household's voice assistant.

- `actor` is always the household member who is speaking. Ask who is speaking if you don't know.
- Never calculate amounts, shares or balances yourself. Every number you say must come from a tool result.
  Describe splits the way the speaker did (who shares, and weights such as 0.5 for half a share)
  and let the tools work out the rupees.
- Before saving an expense whose split is anything other than an obvious equal split, call
  `preview_split`, read the split back, and call `add_expense` only after the speaker confirms.
- If the amount, the payer, who shares the cost, or how to split it is unclear, ask one short
  question instead of guessing.
- Keep spoken replies to one to three sentences. Use the `speech` field of results as a guide.
- HouseLedger never moves money. Settle-up plans are suggestions; record a payment only when
  someone says it happened.
"""

ACTOR = Field(description="The household member who is speaking, e.g. 'Aarav'.")
AMOUNT = Field(gt=0, description="Amount in rupees, e.g. 2400 or 99.50.")
CATEGORY = Field(description=f"One of: {', '.join(CATEGORIES)}.")
DATE = Field(description="Date as YYYY-MM-DD. Leave empty for today.")
REQUEST_ID = Field(description="Optional unique id for this request; retrying with the same id never saves twice.")

READ_ONLY = ToolAnnotations(read_only_hint=True)
WRITES = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False)

Result = Annotated[CallToolResult, ToolOutput]


class ItemInput(BaseModel):
    amount_rupees: float = Field(gt=0, description="Amount of this item in rupees.")
    members: list[str] = Field(min_length=1, description="Who this item is for; it is split equally between them.")
    description: str = ""


class SplitInput(BaseModel):
    """How to divide the bill. Exclusive items are taken out first; the rest uses `method`."""

    method: Literal["equal", "weights", "percent", "exact"] = Field(
        default="equal",
        description="equal: use `participants`. "
        "weights: relative shares; use this when someone should pay part of a share, e.g. "
        "'Sam was away half the week' -> {'Aarav': 1, 'Priya': 1, 'Sam': 0.5}. "
        "percent: percentages the speaker stated, adding up to 100. "
        "exact: ONLY when the speaker states each person's rupee amount. Never work out amounts yourself.",
    )
    participants: list[str] = Field(
        default_factory=list, description="For 'equal': everyone sharing the cost, including the payer if they share."
    )
    weights: dict[str, float] = Field(default_factory=dict, description="For 'weights': member -> relative share.")
    percent: dict[str, float] = Field(default_factory=dict, description="For 'percent': member -> percentage.")
    exact_rupees: dict[str, float] = Field(default_factory=dict, description="For 'exact': member -> rupees.")
    exclusive_items: list[ItemInput] = Field(
        default_factory=list,
        description="Parts of the bill that belong only to some people, e.g. wine only Aarav drank.",
    )

    def to_spec(self) -> SplitSpec:
        return SplitSpec(
            method=self.method,
            participants=self.participants,
            weights=self.weights,
            percent=self.percent,
            exact_paise={name: rupees_to_paise(str(v)) for name, v in self.exact_rupees.items()},
            exclusive_items=[
                ExclusiveItem(amount_paise=rupees_to_paise(str(i.amount_rupees)), members=i.members,
                              description=i.description)
                for i in self.exclusive_items
            ],
        )


def build_server(ledger: Ledger) -> MCPServer:
    mcp = MCPServer(
        name="houseledger",
        title="HouseLedger",
        description="Shared household expenses, settled by voice.",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )
    lock = threading.Lock()  # one SQLite connection; serialise tool calls

    def run(fn) -> CallToolResult:
        """Call the ledger, turn errors into speakable tool errors, and package the output."""
        try:
            with lock:
                output: ToolOutput = fn()
        except LedgerError as err:
            raise ToolError(str(err)) from err
        text = output.speech + "\n\n" + json.dumps(output.data, ensure_ascii=False)
        return CallToolResult(content=[TextContent(type="text", text=text)],
                              structured_content=output.model_dump(mode="json"))

    @mcp.tool(annotations=READ_ONLY)
    def list_household_members() -> Result:
        """List the household's members. Use these exact names in every other tool."""
        return run(lambda: presenters.members(ledger))

    @mcp.tool(annotations=READ_ONLY)
    def preview_split(
        actor: Annotated[str, ACTOR],
        amount_rupees: Annotated[float, AMOUNT],
        split: SplitInput,
        payer: Annotated[str | None, Field(description="Who paid. Defaults to the actor.")] = None,
        description: str = "",
    ) -> Result:
        """Work out how an expense would be split, WITHOUT saving it. Read the result back and ask the
        speaker to confirm before calling add_expense."""
        def go():
            paid_by = ledger.member(payer or actor).name
            shares = ledger.preview_split(rupees_to_paise(str(amount_rupees)), split.to_spec())
            return presenters.preview(paid_by, rupees_to_paise(str(amount_rupees)), description, shares)
        return run(go)

    @mcp.tool(annotations=WRITES)
    def add_expense(
        actor: Annotated[str, ACTOR],
        amount_rupees: Annotated[float, AMOUNT],
        description: Annotated[str, Field(description="What it was for, e.g. 'Groceries'.")],
        split: SplitInput,
        payer: Annotated[str | None, Field(description="Who paid. Defaults to the actor.")] = None,
        category: Annotated[str, CATEGORY] = "other",
        date: Annotated[str | None, DATE] = None,
        request_id: Annotated[str | None, REQUEST_ID] = None,
    ) -> Result:
        """Save a shared expense. For anything but an obvious equal split, call preview_split first and get
        the speaker's confirmation. Always set the closest category (e.g. groceries, food, utilities)."""
        def go():
            expense = ledger.add_expense(
                actor=actor, payer=payer or actor, total_paise=rupees_to_paise(str(amount_rupees)),
                description=description, split=split.to_spec(), category=category, date=date,
                request_id=request_id,
            )
            return presenters.expense_saved(expense, ledger.balances(),
                                            "already_saved" if expense.replayed else "added")
        return run(go)

    @mcp.tool(annotations=WRITES)
    def edit_expense(
        actor: Annotated[str, ACTOR],
        expense_id: Annotated[int, Field(description="The expense id from add_expense or list_expenses.")],
        amount_rupees: Annotated[float | None, Field(description="New amount in rupees.")] = None,
        payer: str | None = None,
        description: str | None = None,
        split: Annotated[SplitInput | None, Field(description="New split. If omitted, the old split is kept.")] = None,
        category: Annotated[str | None, CATEGORY] = None,
        date: Annotated[str | None, DATE] = None,
    ) -> Result:
        """Change an existing expense. Only the fields you pass are changed."""
        def go():
            expense = ledger.edit_expense(
                actor=actor, expense_id=expense_id,
                total_paise=rupees_to_paise(str(amount_rupees)) if amount_rupees is not None else None,
                payer=payer, description=description, split=split.to_spec() if split else None,
                category=category, date=date,
            )
            return presenters.expense_saved(expense, ledger.balances(), "updated")
        return run(go)

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True))
    def undo_last(actor: Annotated[str, ACTOR]) -> Result:
        """Undo the speaker's own most recent expense, edit or payment ("undo that")."""
        def go():
            result = ledger.undo_last(actor=actor)
            return presenters.undone(result, ledger.balances())
        return run(go)

    @mcp.tool(annotations=WRITES)
    def record_payment(
        actor: Annotated[str, ACTOR],
        from_member: Annotated[str, Field(description="Who paid the money.")],
        to_member: Annotated[str, Field(description="Who received it.")],
        amount_rupees: Annotated[float, AMOUNT],
        note: str = "",
        date: Annotated[str | None, DATE] = None,
        request_id: Annotated[str | None, REQUEST_ID] = None,
    ) -> Result:
        """Record that one member paid another back. Only use this when the speaker says the payment
        actually happened."""
        def go():
            payment = ledger.record_payment(
                actor=actor, from_member=from_member, to_member=to_member,
                amount_paise=rupees_to_paise(str(amount_rupees)), note=note, date=date, request_id=request_id,
            )
            return presenters.payment_saved(payment, ledger.balances())
        return run(go)

    @mcp.tool(annotations=READ_ONLY)
    def get_balances() -> Result:
        """Who owes what: each member's net balance across all expenses and payments."""
        return run(lambda: presenters.balances(ledger))

    @mcp.tool(annotations=READ_ONLY)
    def settle_up_plan() -> Result:
        """Suggest the payments that would settle everyone up, using few payments. Nothing is paid or
        recorded."""
        return run(lambda: presenters.settle_up(ledger.settle_up_plan()))

    @mcp.tool(annotations=READ_ONLY)
    def list_expenses(
        limit: Annotated[int, Field(ge=1, le=50, description="How many to return, newest first.")] = 5,
        month: Annotated[str | None, Field(description="Only this month, as YYYY-MM.")] = None,
        category: Annotated[str | None, CATEGORY] = None,
        member: Annotated[str | None, Field(description="Only expenses this member paid or shares.")] = None,
    ) -> Result:
        """Recent expenses (with their ids) and recent payments."""
        def go():
            expenses = ledger.list_expenses(limit=limit, month=month, category=category, member=member)
            return presenters.expense_list(expenses, ledger.list_payments(limit=5))
        return run(go)

    @mcp.tool(annotations=READ_ONLY)
    def monthly_summary(
        month: Annotated[str | None, Field(description="Month as YYYY-MM. Leave empty for this month.")] = None,
    ) -> Result:
        """Total shared spending for a month, by category and by member."""
        return run(lambda: presenters.monthly(ledger.monthly_summary(month)))

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "household": ledger.household_name()})

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the HouseLedger MCP server over Streamable HTTP.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--db", type=Path, default=db_path_from_env())
    parser.add_argument("--seed", action="store_true", help="also add seeded, fictional sample expenses")
    args = parser.parse_args()

    # Local time, so "today" matches the household's calendar.
    ledger = Ledger(connect(args.db), now=lambda: datetime.now().astimezone())
    if args.seed:
        seed(ledger)
    elif not ledger.members():
        # Household members are predefined, as Alexa+ household profiles would be.
        create_household(ledger)
    build_server(ledger).run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
