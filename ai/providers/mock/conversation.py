"""Conversation (in-character chat) mock responder (wk14). Extracted WK81 from
ai/providers/mock_provider.py via pure move.

Determinism note: uses the SAME shared `_MOCK_RNG` stream instance as the
MockProvider facade (imported lazily to keep the singleton and avoid an import
cycle -- see legacy_decision.py for the rationale)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai.providers.mock_provider import MockProvider


def mock_conversation_response(provider: "MockProvider", system_prompt: str, user_prompt: str) -> str:
    """Return a canned in-character response by hero class (wk14). Deterministic RNG."""
    from ai.providers.mock_provider import _MOCK_RNG

    hero_class = "warrior"
    if "ranger" in system_prompt.lower():
        hero_class = "ranger"
    elif "rogue" in system_prompt.lower():
        hero_class = "rogue"
    elif "wizard" in system_prompt.lower():
        hero_class = "wizard"
    templates = {
        "warrior": [
            "Aye, Sovereign. I live to serve. Point me at the next threat.",
            "My blade is yours. Just say where the fight is.",
            "Honored to speak with you. I'll keep the realm safe.",
        ],
        "ranger": [
            "The wilds call, but I hear you. What do you need?",
            "Sovereign. I've seen much from the trails. Ask what you will.",
            "Nature and kingdom both deserve protection. I'm with you.",
        ],
        "rogue": [
            "Gold talks, Sovereign. But so do I. What's the job?",
            "A pleasure. Let's just say we're aligned on profitable outcomes.",
            "You've got my ear. And my skills, when the price is right.",
        ],
        "wizard": [
            "Knowledge serves the realm. I am at your disposal, Sovereign.",
            "The arcane obeys its own laws—but I obey yours. How may I help?",
            "Wise of you to seek counsel. The world holds many secrets.",
        ],
    }
    choices = templates.get(hero_class, templates["warrior"])
    idx = int(_MOCK_RNG.random() * len(choices)) % len(choices)
    return choices[idx]
