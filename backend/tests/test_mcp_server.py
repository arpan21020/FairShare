"""MCP server tests.

The in-process tests call the tools through a real MCP `Client` connected directly to the
server object. The protocol tests start the server as a separate process and talk to it
over Streamable HTTP, exactly as a host such as Alexa+ or Claude would.
"""

import asyncio

import pytest
from mcp import Client

from houseledger.db import connect
from houseledger.ledger import Ledger
from houseledger.mcp_server import build_server
from houseledger.seed import seed
from tests.helpers import running_mcp_server

EXPECTED_TOOLS = {
    "list_household_members", "preview_split", "add_expense", "edit_expense", "undo_last",
    "record_payment", "get_balances", "settle_up_plan", "list_expenses", "monthly_summary",
}
SAM_HALF = {"method": "weights", "weights": {"Aarav": 1, "Priya": 1, "Sam": 0.5}}


def call_all(server_or_url, calls, **client_kwargs):
    """Open one MCP session and make each (tool, args) call in order."""
    async def go():
        async with Client(server_or_url, **client_kwargs) as client:
            return client.protocol_version, [await client.call_tool(name, args) for name, args in calls]
    return asyncio.run(go())


@pytest.fixture
def server(ledger):
    return build_server(ledger)


def test_tools_are_listed_with_schemas(server):
    async def go():
        async with Client(server) as client:
            return (await client.list_tools()).tools
    tools = {t.name: t for t in asyncio.run(go())}
    assert set(tools) == EXPECTED_TOOLS
    assert all(t.output_schema for t in tools.values())
    assert tools["get_balances"].annotations.read_only_hint is True
    assert tools["add_expense"].annotations.read_only_hint is False
    assert "actor" in tools["add_expense"].input_schema["required"]


def test_preview_does_not_save(server, ledger):
    _, [result] = call_all(server, [("preview_split", {"actor": "Aarav", "amount_rupees": 2400, "split": SAM_HALF})])
    out = result.structured_content
    assert not result.is_error
    assert [s["amount"]["paise"] for s in out["data"]["shares"]] == [96000, 96000, 48000]
    assert out["display"]["card"] == "confirm_split"
    assert out["speech"].startswith("₹2,400, paid by Aarav, split as Aarav ₹960, Priya ₹960 and Sam ₹480")
    assert ledger.list_expenses() == []


def test_add_expense_returns_speech_data_and_card(server):
    _, [result] = call_all(server, [("add_expense", {
        "actor": "Aarav", "amount_rupees": 2400, "description": "Groceries", "category": "groceries",
        "split": SAM_HALF})])
    out = result.structured_content
    assert out["speech"] == "Saved: ₹2,400 for Groceries, paid by Aarav. Priya's share is ₹960 and Sam's share is ₹480."
    assert result.content[0].text.startswith(out["speech"])  # spoken reply is the text content
    assert out["display"]["card"] == "expense_added"
    assert {b["member"]: (b["net"]["paise"], b["status"]) for b in out["data"]["balances"]} == {
        "Aarav": (144000, "is_owed"), "Priya": (-96000, "owes"), "Sam": (-48000, "owes"),
    }


def test_rupee_inputs_are_converted_exactly(server):
    _, [result] = call_all(server, [("add_expense", {
        "actor": "Priya", "amount_rupees": 1800.5, "description": "Dinner",
        "split": {"participants": ["Aarav", "Priya", "Sam"],
                  "exclusive_items": [{"amount_rupees": 600.25, "members": ["Aarav"]}]}})])
    shares = {s["member"]: s["amount"]["paise"] for s in result.structured_content["data"]["expense"]["shares"]}
    # Wine 60025 to Aarav; the rest, 120025, is 40008.33 each, so the leftover paisa goes to Aarav.
    assert shares == {"Aarav": 100034, "Priya": 40008, "Sam": 40008}
    assert sum(shares.values()) == 180050


def test_errors_are_speakable(server):
    _, results = call_all(server, [
        ("add_expense", {"actor": "Raj", "amount_rupees": 10, "description": "x", "split": {"participants": ["Sam"]}}),
        ("preview_split", {"actor": "Sam", "amount_rupees": 100,
                           "split": {"method": "percent", "percent": {"Sam": 50, "Priya": 40}}}),
        ("undo_last", {"actor": "Sam"}),
        ("edit_expense", {"actor": "Sam", "expense_id": 999, "description": "x"}),
        ("add_expense", {"actor": "Sam", "amount_rupees": -5, "description": "x", "split": {"participants": ["Sam"]}}),
    ])
    assert all(r.is_error for r in results)
    texts = [r.content[0].text for r in results]
    assert "I don't know anyone called Raj" in texts[0]
    assert "add up to 90%" in texts[1]
    assert "nothing of Sam's to undo" in texts[2]
    assert "couldn't find expense number 999" in texts[3]


def test_full_conversation_flow(server):
    _, results = call_all(server, [
        ("add_expense", {"actor": "Aarav", "amount_rupees": 2400, "description": "Groceries", "split": SAM_HALF,
                         "request_id": "turn-1"}),
        ("add_expense", {"actor": "Aarav", "amount_rupees": 2400, "description": "Groceries", "split": SAM_HALF,
                         "request_id": "turn-1"}),  # retried turn: must not double-count
        ("record_payment", {"actor": "Priya", "from_member": "Priya", "to_member": "Aarav", "amount_rupees": 500}),
        ("undo_last", {"actor": "Priya"}),
        ("record_payment", {"actor": "Priya", "from_member": "Priya", "to_member": "Aarav", "amount_rupees": 960}),
        ("get_balances", {}),
        ("settle_up_plan", {}),
        ("list_expenses", {"limit": 5}),
        ("monthly_summary", {"month": "2026-10"}),
    ])
    assert not any(r.is_error for r in results)
    speech = [r.structured_content["speech"] for r in results]
    assert speech[1] == "That ₹2,400 expense for Groceries was already saved."
    assert speech[3] == "Done. Removed the ₹500 payment."
    assert speech[5] == "Aarav is owed ₹480, Priya is settled up and Sam owes ₹480."
    assert speech[6] == "To settle up: Sam pays Aarav ₹480. That's one payment."
    assert results[7].structured_content["display"]["card"] == "expense_list"
    assert speech[8] == ("In October 2026, the household spent ₹2,400 across 1 expense. "
                         "The biggest category was other at ₹2,400.")


def test_members_tool(tmp_path):
    ledger = Ledger(connect(tmp_path / "l.db"))
    seed(ledger)
    _, [result] = call_all(build_server(ledger), [("list_household_members", {})])
    assert result.structured_content["data"] == {"household": "Demo flat (seeded demo data)",
                                                 "members": ["Aarav", "Priya", "Sam"]}


# ------------------------------------------------------------- over Streamable HTTP


@pytest.fixture(scope="module")
def http_server(tmp_path_factory):
    with running_mcp_server(tmp_path_factory.mktemp("http") / "ledger.db") as url:
        yield url


def test_streamable_http_with_2025_11_25_handshake(http_server):
    # mode="legacy" forces the initialize handshake; the server must agree on 2025-11-25.
    version, results = call_all(http_server, [
        ("get_balances", {}),
        ("preview_split", {"actor": "Sam", "amount_rupees": 2400, "split": SAM_HALF}),
        ("add_expense", {"actor": "Sam", "amount_rupees": 300, "description": "Milk",
                         "split": {"participants": ["Aarav", "Priya", "Sam"]}}),
        ("settle_up_plan", {}),
    ], mode="legacy")
    assert version == "2025-11-25"
    assert not any(r.is_error for r in results)
    assert results[0].structured_content["speech"] == (
        "Aarav is owed ₹18,940.33, Priya owes ₹12,689.67 and Sam owes ₹6,250.66.")
    assert results[2].structured_content["data"]["status"] == "added"
    transfers = results[3].structured_content["data"]["transfers"]
    assert sum(t["amount"]["paise"] for t in transfers) > 0


def test_fresh_database_starts_with_predefined_members_and_no_history(tmp_path):
    with running_mcp_server(tmp_path / "fresh.db", seed=False) as url:
        _, [members, balances] = call_all(url, [("list_household_members", {}), ("get_balances", {})])
    assert members.structured_content["data"]["members"] == ["Aarav", "Priya", "Sam"]
    assert balances.structured_content["speech"] == "Everyone is settled up."


def test_streamable_http_lists_tools_on_newest_protocol(http_server):
    async def go():
        async with Client(http_server) as client:  # mode="auto": newest version both sides support
            return client.protocol_version, {t.name for t in (await client.list_tools()).tools}
    version, names = asyncio.run(go())
    assert version >= "2025-11-25"
    assert names == EXPECTED_TOOLS
