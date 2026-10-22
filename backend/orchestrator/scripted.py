"""Scripted mode: replays a fixed demo conversation through the real MCP server, no LLM needed.

Each scripted line maps to fixed tool calls. The replies come from the tools' `speech`, so
every number is still calculated by HouseLedger. Request ids are scoped to the conversation,
so replaying a line never saves twice.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from mcp import Client

from .config import Settings
from .mcp_tools import ToolCall, call_tool
from .turns import TurnResult

logger = logging.getLogger(__name__)

SAM_HALF = {"method": "weights", "weights": {"Aarav": 1, "Priya": 1, "Sam": 0.5}}


@dataclass
class Step:
    speaker: str
    utterance: str
    calls: list[tuple[str, dict]] = field(default_factory=list)
    reply: str | None = None  # for turns where Alexa asks a question instead of calling a tool


def demo_script() -> list[Step]:
    month = date.today().isoformat()[:7]
    return [
        Step("Aarav", "I paid ₹2,400 for groceries. Split it with Priya and Sam, but Sam was away half the week.",
             [("preview_split", {"actor": "Aarav", "amount_rupees": 2400, "description": "groceries",
                                 "split": SAM_HALF})]),
        Step("Aarav", "Yes, save it.",
             [("add_expense", {"actor": "Aarav", "amount_rupees": 2400, "description": "Groceries",
                               "category": "groceries", "split": SAM_HALF, "request_id": "{cid}-groceries"})]),
        Step("Priya", "Split the pizza.", reply="Sure. How much was the pizza, and who shared it?"),
        Step("Priya", "It was ₹900, just me and Sam.",
             [("add_expense", {"actor": "Priya", "amount_rupees": 900, "description": "Pizza", "category": "food",
                               "split": {"participants": ["Priya", "Sam"]}, "request_id": "{cid}-pizza"})]),
        Step("Priya", "Oops, that was the wrong amount. Undo that.", [("undo_last", {"actor": "Priya"})]),
        Step("Priya", "Who owes what?", [("get_balances", {})]),
        Step("Priya", "I paid Aarav back ₹500.",
             [("record_payment", {"actor": "Priya", "from_member": "Priya", "to_member": "Aarav",
                                  "amount_rupees": 500, "request_id": "{cid}-payback"})]),
        Step("Sam", "Settle up. What's the fewest payments?", [("settle_up_plan", {})]),
        Step("Sam", "How much did we spend this month?", [("monthly_summary", {"month": month})]),
    ]


class ScriptedAssistant:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.next_step: dict[str, int] = {}

    def reset(self, conversation_id: str) -> None:
        self.next_step.pop(conversation_id, None)

    async def turn(self, conversation_id: str, speaker: str, utterance: str) -> TurnResult:
        script = demo_script()
        index = _match(script, utterance)
        if index is None:
            upcoming = script[min(self.next_step.get(conversation_id, 0), len(script) - 1)]
            return TurnResult.from_calls(
                f'In scripted demo mode I follow the demo script. Try: "{upcoming.utterance}"', "scripted", [])

        step = script[index]
        self.next_step[conversation_id] = index + 1
        if step.reply:
            return _as(step.speaker, TurnResult.from_calls(step.reply, "scripted", []))

        calls: list[ToolCall] = []
        try:
            async with Client(self.settings.mcp_url) as mcp:
                for name, arguments in step.calls:
                    calls.append(await call_tool(mcp, name, _scoped(arguments, conversation_id)))
        except Exception:  # MCP connection failures arrive as httpx errors or exception groups
            logger.exception("Scripted turn failed")
            return TurnResult.failure("I can't reach HouseLedger right now. Is the MCP server running?", "scripted")
        return _as(step.speaker, TurnResult.from_calls(calls[-1].speech, "scripted", calls))


def _as(speaker: str, result: TurnResult) -> TurnResult:
    """Scripted lines always belong to the scripted speaker, whoever is selected."""
    result.speaker, result.speaker_source = speaker, "script"
    return result


def _match(script: list[Step], utterance: str) -> int | None:
    wanted = _normalise(utterance)
    return next((i for i, step in enumerate(script) if _normalise(step.utterance) == wanted), None)


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _scoped(arguments: dict, conversation_id: str) -> dict:
    out = dict(arguments)
    if "request_id" in out:
        out["request_id"] = out["request_id"].format(cid=conversation_id)
    return out
