"""Working out who is speaking.

On a real Echo, Alexa+ voice ID recognises household members by their voice. The simulator
stands in for that with a "Voice ID (simulated)" selector, and people can also simply say
who they are: "This is Priya…", "It's Neha", "I'm Rahul", "Priya here", or just "Priya" when
Alexa asks who's speaking.
"""

import re

_LEAD_IN = r"^(?:(?:hey|hi|hello|ok|okay)[,\s]+)?(?:alexa[,\s]+)?"
_SELF_INTRO = re.compile(_LEAD_IN + r"(?:this is|it'?s|it is|i'?m|i am|my name is)\s+([a-z]+)\b", re.IGNORECASE)
_NAME_HERE = re.compile(_LEAD_IN + r"([a-z]+)\s+here\b", re.IGNORECASE)


def identify_speaker(utterance: str, members: list[str]) -> str | None:
    """Return the member who introduced themselves in `utterance`, if any."""
    by_lower = {m.lower(): m for m in members}
    text = utterance.strip().strip(".!?,; ").lower()
    if text in by_lower:  # a bare name, e.g. answering "Who's speaking?"
        return by_lower[text]
    for pattern in (_SELF_INTRO, _NAME_HERE):
        match = pattern.match(text)
        if match and match.group(1).lower() in by_lower:
            return by_lower[match.group(1).lower()]
    return None
