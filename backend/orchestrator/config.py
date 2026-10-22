"""Settings for the orchestrator, read from environment variables and the project's .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SIMULATOR_DIST = PROJECT_ROOT / "simulator" / "dist"

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    mcp_url: str
    llm_base_url: str
    llm_api_key: str | None
    llm_model: str
    llm_thinking: bool

    @property
    def live_available(self) -> bool:
        return bool(self.llm_api_key)


def load_settings() -> Settings:
    return Settings(
        mcp_url=os.environ.get("MCP_URL", "http://127.0.0.1:8010/mcp"),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY") or os.environ.get("NVIDIA_API_KEY") or None,
        # Fast and accurate enough with thinking on; nemotron-3-ultra is more careful but ~3x slower.
        llm_model=os.environ.get("LLM_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        llm_thinking=os.environ.get("LLM_THINKING", "true").lower() in ("1", "true", "yes"),
    )
