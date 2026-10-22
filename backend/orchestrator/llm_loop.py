"""Live mode: an LLM plays Alexa and calls HouseLedger's MCP tools.

Each turn opens an MCP session over Streamable HTTP, offers the server's tools to the LLM
(any OpenAI-compatible endpoint, NVIDIA by default), runs the tool calls it asks for, and
loops until the model replies in words. The LLM never does arithmetic: the server's
instructions and the system prompt below tell it to take every number from tool results,
and when a tool succeeds, Alexa speaks the tool's own reply rather than the LLM's paraphrase.
"""

import json
import logging
import re
from datetime import date

from mcp import Client
from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from .config import Settings
from .mcp_tools import ToolCall, call_tool, to_openai_tools
from .turns import TurnResult

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_HISTORY_MESSAGES = 40

SYSTEM_PROMPT = """\
You are Alexa on a kitchen Echo Show, helping a household keep track of shared expenses with \
the HouseLedger tools.

{server_instructions}

Today is {today}. The household members are {members}. Amounts are in Indian rupees (₹).

Each user message begins with [Speaker: Name]. That person is the `actor` in every tool call for \
that message, and "I", "me" and "my" refer to them. If it says [Speaker: unknown], you don't know \
who is talking: you may answer questions such as who owes what, but before saving, changing or \
undoing anything, ask "Who's speaking?" and wait for the answer. Never guess the speaker.

Reply in plain spoken English: one to three short sentences, no markdown, no lists, no emoji. \
Refer to household members by name, never as he or she. \
When a tool result has a `speech` field, base your reply on it, and never mention a number that \
is not in a tool result.\
"""

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class LiveAssistant:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key, timeout=90)
        self.histories: dict[str, list[dict]] = {}

    def reset(self, conversation_id: str) -> None:
        self.histories.pop(conversation_id, None)

    async def turn(self, conversation_id: str, speaker: str, utterance: str) -> TurnResult:
        history = self.histories.setdefault(conversation_id, [])
        user_message = {"role": "user", "content": f"[Speaker: {speaker}] {utterance}"}
        history.append(user_message)
        calls: list[ToolCall] = []
        try:
            async with Client(self.settings.mcp_url) as mcp:
                tools = to_openai_tools((await mcp.list_tools()).tools)
                members = (await call_tool(mcp, "list_household_members", {})).data.get("members", [])
                system = {"role": "system", "content": SYSTEM_PROMPT.format(
                    server_instructions=mcp.instructions or "",
                    today=date.today().isoformat(),
                    members=", ".join(members),
                )}
                speech, llm_error = await self._run_loop(mcp, system, history, tools, calls)
        except Exception:  # MCP connection failures arrive as httpx errors or exception groups
            logger.exception("Live turn failed")
            del history[history.index(user_message):]  # drop this turn so the history stays well-formed
            return TurnResult.failure("I can't reach HouseLedger right now. Is the MCP server running?", "live")
        finally:
            self._trim(conversation_id)

        if llm_error and not calls:
            del history[history.index(user_message):]
            return TurnResult.failure(
                f"I couldn't reach the language model ({llm_error}). Try again, or switch to scripted mode.", "live")
        return TurnResult.from_calls(speech, "live", calls)

    async def _run_loop(self, mcp: Client, system: dict, history: list[dict], tools: list[dict],
                        calls: list[ToolCall]) -> tuple[str, str | None]:
        """Returns (speech, llm_error). LLM errors are returned, not raised, so they are not
        wrapped by the MCP client's task group."""
        for _ in range(MAX_TOOL_ROUNDS):
            try:
                response = await self.llm.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=[system, *history],
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.3,
                    max_tokens=2048,
                    extra_body={"chat_template_kwargs": {"enable_thinking": self.settings.llm_thinking}},
                )
            except (APIConnectionError, APIStatusError) as err:
                logger.warning("LLM call failed: %s", err)
                # If tools already ran this turn, report what they did rather than losing it.
                speech = calls[-1].speech if calls else ""
                if calls:
                    history.append({"role": "assistant", "content": speech})
                return speech, _short_error(err)
            message = response.choices[0].message
            if not message.tool_calls:
                speech = _clean(message.content) or "Sorry, I didn't catch that. Could you say it again?"
                if calls and calls[-1].ok:
                    # Say the server's own reply: it is written from exact ledger numbers, while
                    # an LLM paraphrase can attach the right amounts to the wrong people.
                    speech = calls[-1].speech
                history.append({"role": "assistant", "content": speech})
                return speech, None

            history.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in message.tool_calls
                ],
            })
            for tc in message.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    history.append({"role": "tool", "tool_call_id": tc.id,
                                    "content": "Error: the arguments were not valid JSON. Please try again."})
                    continue
                call = await call_tool(mcp, tc.function.name, arguments)
                calls.append(call)
                history.append({"role": "tool", "tool_call_id": tc.id, "content": call.text})

        speech = "Sorry, I got stuck on that one. Could you say it a different way?"
        history.append({"role": "assistant", "content": speech})
        return speech, None

    def _trim(self, conversation_id: str) -> None:
        """Keep recent history, cutting only at a user message so tool calls stay paired."""
        history = self.histories.get(conversation_id, [])
        if len(history) <= MAX_HISTORY_MESSAGES:
            return
        for i in range(len(history) - MAX_HISTORY_MESSAGES, len(history)):
            if history[i]["role"] == "user":
                del history[:i]
                return


def _clean(text: str | None) -> str:
    return THINK_BLOCK.sub("", text or "").strip()


def _short_error(err: Exception) -> str:
    if isinstance(err, APIStatusError):
        return "rate limited" if err.status_code == 429 else f"error {err.status_code}"
    return "connection failed"
