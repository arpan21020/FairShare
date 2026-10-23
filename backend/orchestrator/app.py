"""HTTP API for the simulated Alexa+ device.

Run:  uv run python -m orchestrator.app        (http://127.0.0.1:8001)

Needs the FairShare MCP server running (see houseledger.mcp_server). Live mode needs an
LLM key in .env; scripted mode works without one. If the simulator has been built
(simulator/dist), it is served from the same address.
"""

import argparse
import time
from typing import Literal

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from mcp import Client
from pydantic import BaseModel, Field

from .config import SIMULATOR_DIST, load_settings
from .llm_loop import LiveAssistant
from .mcp_tools import call_tool
from .scripted import ScriptedAssistant, demo_script
from .speakers import identify_speaker

settings = load_settings()
live = LiveAssistant(settings) if settings.live_available else None
scripted = ScriptedAssistant(settings)

app = FastAPI(title="FairShare — simulated Alexa+ orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TurnRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    speaker: str = Field(default="", max_length=40, description="Simulated voice ID; empty if unknown.")
    utterance: str = Field(min_length=1, max_length=500)
    mode: Literal["live", "scripted"] | None = None


async def household() -> tuple[list[str], str, bool]:
    """(members, household name, reachable). Never raises: a stopped server shows as a warning."""
    try:
        async with Client(settings.mcp_url) as mcp:
            call = await call_tool(mcp, "list_household_members", {})
            # Something answered, but only a successful call means it is FairShare.
            return call.data.get("members", []), call.data.get("household", ""), call.ok
    except Exception:
        return [], "", False


@app.get("/api/config")
async def config() -> dict:
    members, household_name, mcp_ok = await household()
    return {
        "modes": ["live", "scripted"] if live else ["scripted"],
        "default_mode": "live" if live else "scripted",
        "model": settings.llm_model if live else None,
        "mcp_url": settings.mcp_url,
        "mcp_ok": mcp_ok,
        "household": household_name,
        "members": members,
        "script": [{"speaker": s.speaker, "utterance": s.utterance} for s in demo_script()],
    }


@app.post("/api/turn")
async def turn(request: TurnRequest) -> dict:
    mode = request.mode or ("live" if live else "scripted")
    assistant = live if mode == "live" and live else scripted
    started = time.perf_counter()
    utterance = request.utterance.strip()

    # Someone saying who they are ("This is Priya…") overrides the simulated voice ID.
    members, _, _ = await household()
    said = identify_speaker(utterance, members)
    speaker = said or request.speaker.strip() or None
    source = "said" if said else "voice_id" if speaker else None

    result = await assistant.turn(request.conversation_id, speaker or "unknown", utterance)
    if result.speaker is None:
        result.speaker, result.speaker_source = speaker, source
    return {**result.__dict__, "ms": round((time.perf_counter() - started) * 1000)}


@app.post("/api/conversations/{conversation_id}/reset")
async def reset(conversation_id: str) -> dict:
    scripted.reset(conversation_id)
    if live:
        live.reset(conversation_id)
    return {"ok": True}


if SIMULATOR_DIST.is_dir():
    app.mount("/", StaticFiles(directory=SIMULATOR_DIST, html=True), name="simulator")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the simulated Alexa+ orchestrator.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
