"""Orchestrator tests: scripted mode against the real MCP server, and the live tool loop with a
stand-in LLM (so no network or API key is needed)."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from orchestrator.config import Settings
from orchestrator.llm_loop import LiveAssistant
from orchestrator.mcp_tools import inline_refs
from orchestrator.scripted import ScriptedAssistant, demo_script
from tests.helpers import running_mcp_server


@pytest.fixture
def settings(tmp_path):
    with running_mcp_server(tmp_path / "ledger.db") as url:
        yield Settings(mcp_url=url, llm_base_url="http://unused", llm_api_key="test-key",
                       llm_model="test-model", llm_thinking=False)


def test_scripted_demo_runs_end_to_end(settings):
    assistant = ScriptedAssistant(settings)

    async def play():
        return [await assistant.turn("demo", line.speaker, line.utterance) for line in demo_script()]

    results = asyncio.run(play())
    speech = [r.speech for r in results]
    cards = [r.cards[-1]["card"] for r in results]

    assert speech[0] == ("₹2,400 for groceries, paid by Rahul, split as Rahul ₹960, Priya ₹960 and Neha ₹480. "
                         "Shall I save it?")
    assert speech[1].startswith("Saved: ₹2,400 for Groceries, paid by Rahul.")
    assert speech[2] == "Sure. How much was the pizza, and who shared it?"
    assert speech[4] == "Done. Removed the ₹900 expense for Pizza."
    assert speech[6] == "Recorded: Priya paid Rahul ₹500."
    assert speech[7].startswith("To settle up:")
    assert cards == ["confirm_split", "expense_added", "question", "expense_added", "balances", "balances",
                     "balances", "settle_up", "monthly_summary"]
    assert all(call["ok"] for r in results for call in r.trace)
    assert [r.speaker for r in results] == [line.speaker for line in demo_script()]
    assert {r.speaker_source for r in results} == {"script"}
    assert [len(r.trace) for r in results] == [1, 1, 0, 1, 1, 1, 1, 1, 1]


def test_scripted_mode_suggests_the_next_line_for_unknown_input(settings):
    result = asyncio.run(ScriptedAssistant(settings).turn("demo", "Neha", "Play some music"))
    assert result.speech.startswith("In scripted demo mode I follow the demo script. Try:")
    assert result.trace == []


def test_scripted_mode_reports_a_missing_server():
    settings = Settings(mcp_url="http://127.0.0.1:9/mcp", llm_base_url="", llm_api_key=None,
                        llm_model="", llm_thinking=False)
    result = asyncio.run(ScriptedAssistant(settings).turn("demo", "Priya", "Who owes what?"))
    assert "can't reach FairShare" in result.speech
    assert result.cards[0]["card"] == "error"


def test_inline_refs():
    schema = {
        "type": "object",
        "$defs": {"Item": {"type": "object", "properties": {"x": {"type": "number"}}}},
        "properties": {"items": {"type": "array", "items": {"$ref": "#/$defs/Item"}},
                       "one": {"$ref": "#/$defs/Item", "description": "kept"}},
    }
    assert inline_refs(schema) == {
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "object", "properties": {"x": {"type": "number"}}}},
            "one": {"type": "object", "properties": {"x": {"type": "number"}}, "description": "kept"},
        },
    }


class FakeLLM:
    """Stands in for the OpenAI-compatible client: returns scripted responses in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self.responses.pop(0))])


def tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, type="function",
                           function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def test_live_loop_calls_mcp_tools_and_replies(settings):
    assistant = LiveAssistant(settings)
    assistant.llm = FakeLLM([
        SimpleNamespace(content=None, tool_calls=[tool_call("c1", "preview_split", {
            "actor": "Rahul", "amount_rupees": 2400,
            "split": {"method": "weights", "weights": {"Rahul": 1, "Priya": 1, "Neha": 0.5}}})]),
        SimpleNamespace(content="That's ₹960 for you and Priya, and ₹480 for Neha. Shall I save it?",
                        tool_calls=None),
    ])

    result = asyncio.run(assistant.turn("conv", "Rahul", "Groceries 2400, Neha half"))

    # After a successful tool call, Alexa speaks the server's reply, not the LLM's paraphrase.
    assert result.speech == ("₹2,400, paid by Rahul, split as Rahul ₹960, Priya ₹960 and Neha ₹480. "
                             "Shall I save it?")
    assert result.cards[-1]["card"] == "confirm_split"
    assert [t["tool"] for t in result.trace] == ["preview_split"]

    first_request = assistant.llm.requests[0]
    assert {t["function"]["name"] for t in first_request["tools"]} >= {"add_expense", "preview_split"}
    assert "$defs" not in json.dumps(first_request["tools"])
    system = first_request["messages"][0]["content"]
    assert "Rahul, Priya, Neha" in system and "Never calculate amounts" in system
    assert "[Speaker: unknown]" in system and "Who's speaking?" in system
    assert first_request["messages"][1] == {"role": "user", "content": "[Speaker: Rahul] Groceries 2400, Neha half"}

    # The tool result went back to the LLM, and the history is well-formed for the next turn.
    tool_message = assistant.llm.requests[1]["messages"][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_call_id"] == "c1"
    assert tool_message["content"].startswith("₹2,400, paid by Rahul")
    assert [m["role"] for m in assistant.histories["conv"]] == ["user", "assistant", "tool", "assistant"]


def test_live_loop_passes_tool_errors_back_to_the_llm(settings):
    assistant = LiveAssistant(settings)
    assistant.llm = FakeLLM([
        SimpleNamespace(content=None, tool_calls=[tool_call("c1", "record_payment", {
            "actor": "Raj", "from_member": "Raj", "to_member": "Rahul", "amount_rupees": 100})]),
        SimpleNamespace(content="I don't know anyone called Raj here.", tool_calls=None),
    ])
    result = asyncio.run(assistant.turn("conv", "Priya", "Raj paid Rahul 100"))
    assert result.trace[0]["ok"] is False
    assert result.cards[-1]["card"] == "error"
    assert assistant.llm.requests[1]["messages"][-1]["content"].startswith("Error: I don't know anyone called Raj")


def test_live_loop_reports_unreachable_llm(settings):
    import httpx2  # the HTTP library used by openai v3
    from openai import APIConnectionError

    class DownLLM:
        def __init__(self):
            async def create(**kwargs):
                raise APIConnectionError(request=httpx2.Request("POST", "http://unused"))
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    assistant = LiveAssistant(settings)
    assistant.llm = DownLLM()
    result = asyncio.run(assistant.turn("conv", "Neha", "Who owes what?"))
    assert "couldn't reach the language model" in result.speech
    assert assistant.histories["conv"] == []  # the failed turn is not kept
