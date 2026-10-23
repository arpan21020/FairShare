"""Calling FairShare's MCP tools and recording each call for the on-screen trace."""

import re
import time
from dataclasses import dataclass, field

from mcp import Client

ERROR_PREFIX = re.compile(r"^Error executing tool \w+:\s*")


@dataclass
class ToolCall:
    """One `tools/call`, as shown in the MCP trace panel."""

    tool: str
    arguments: dict
    ok: bool
    speech: str
    text: str  # what the LLM reads back
    card: dict | None
    data: dict = field(default_factory=dict)
    ms: int = 0

    def trace(self) -> dict:
        return {"tool": self.tool, "arguments": self.arguments, "ok": self.ok, "speech": self.speech,
                "data": self.data, "ms": self.ms}


async def call_tool(client: Client, name: str, arguments: dict) -> ToolCall:
    started = time.perf_counter()
    result = await client.call_tool(name, arguments)
    ms = round((time.perf_counter() - started) * 1000)
    text = "".join(block.text for block in result.content if getattr(block, "type", "") == "text")

    if result.is_error:
        message = ERROR_PREFIX.sub("", text).strip() or "Something went wrong."
        return ToolCall(tool=name, arguments=arguments, ok=False, speech=message, text=f"Error: {message}",
                        card={"card": "error", "data": {"message": message}}, data={"error": message}, ms=ms)

    structured = result.structured_content or {}
    return ToolCall(tool=name, arguments=arguments, ok=True, speech=structured.get("speech", text), text=text,
                    card=structured.get("display"), data=structured.get("data", {}), ms=ms)


def to_openai_tools(tools) -> list[dict]:
    """Convert MCP tool definitions to OpenAI-style function tools for the LLM."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": inline_refs(tool.input_schema),
            },
        }
        for tool in tools
    ]


def inline_refs(schema: dict) -> dict:
    """Replace `$ref`s with their `$defs` entries; some LLM endpoints don't resolve references."""
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = defs[node["$ref"].rsplit("/", 1)[-1]]
                return walk({**target, **{k: v for k, v in node.items() if k != "$ref"}})
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(item) for item in node]
        return node

    return walk(schema)
