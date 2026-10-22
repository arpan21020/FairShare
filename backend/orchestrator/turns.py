"""The result of one spoken turn, returned to the simulator."""

from dataclasses import dataclass, field

from .mcp_tools import ToolCall


@dataclass
class TurnResult:
    speech: str
    mode: str
    cards: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    speaker: str | None = None  # who this turn was attributed to
    speaker_source: str | None = None  # "voice_id" (selector), "said" (introduced themselves) or "script"

    @classmethod
    def from_calls(cls, speech: str, mode: str, calls: list[ToolCall]) -> "TurnResult":
        cards = [c.card for c in calls if c.card]
        if not calls:
            cards = [{"card": "question", "data": {"text": speech}}]
        return cls(speech=speech, mode=mode, cards=cards, trace=[c.trace() for c in calls])

    @classmethod
    def failure(cls, speech: str, mode: str) -> "TurnResult":
        return cls(speech=speech, mode=mode, cards=[{"card": "error", "data": {"message": speech}}])
