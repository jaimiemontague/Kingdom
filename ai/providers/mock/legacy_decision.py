"""Legacy rule-based decision mock responder. Extracted WK81 from
ai/providers/mock_provider.py via pure move.

Determinism note: this responder consumes the SAME shared `_MOCK_RNG` stream
instance that lives on the MockProvider facade module (ai/providers/mock_provider.py).
`get_rng("mock_provider")` returns a fresh Random each call, so re-deriving it
here would fork the stream and break byte-identical output. We therefore import
the singleton lazily inside the function (no top-level mock_provider import, no
import cycle)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai.providers.mock_provider import MockProvider


def make_decision(
    provider: "MockProvider",
    personality: str,
    health_pct: int,
    in_combat: bool,
    has_potions: bool,
    can_shop: bool,
    low_health: bool,
    critical_health: bool,
    outnumbered: bool
) -> dict:
    """Make a decision based on the situation."""
    # Lazy import keeps the shared deterministic RNG instance (no top-level
    # mock_provider import -> no import cycle).
    from ai.providers.mock_provider import _MOCK_RNG

    # Critical health - everyone considers survival
    if critical_health:
        if has_potions:
            return {
                "action": "use_potion",
                "target": "",
                "reasoning": f"Critical health at {health_pct}%, using potion for survival"
            }
        else:
            return {
                "action": "retreat",
                "target": "castle",
                "reasoning": f"Critical health at {health_pct}% and no potions, must retreat"
            }

    # Low health handling varies by personality
    if low_health:
        if personality == "brave":
            # Brave heroes fight longer
            if has_potions and health_pct < 30:
                return {
                    "action": "use_potion",
                    "target": "",
                    "reasoning": "Getting low, using potion to continue fighting"
                }
            elif in_combat and not outnumbered:
                return {
                    "action": "fight",
                    "target": "",
                    "reasoning": "Still got fight left in me!"
                }
        elif personality == "cautious" or personality == "greedy":
            # Cautious/greedy heroes retreat earlier
            if has_potions:
                return {
                    "action": "use_potion",
                    "target": "",
                    "reasoning": "Health getting low, using potion"
                }
            else:
                return {
                    "action": "retreat",
                    "target": "marketplace",
                    "reasoning": "Low health and no potions, retreating to restock"
                }
        else:
            # Balanced
            if has_potions and health_pct < 40:
                return {
                    "action": "use_potion",
                    "target": "",
                    "reasoning": "Using potion at moderate health"
                }

    # Outnumbered handling
    if outnumbered and in_combat:
        if personality == "brave":
            if _MOCK_RNG.random() < 0.3:  # 30% chance to retreat
                return {
                    "action": "retreat",
                    "target": "castle",
                    "reasoning": "Outnumbered, making tactical retreat"
                }
        elif personality == "cautious" or personality == "greedy":
            return {
                "action": "retreat",
                "target": "castle",
                "reasoning": "Outnumbered, discretion is the better part of valor"
            }

    # Shopping opportunities
    if can_shop and not in_combat:
        if low_health:
            return {
                "action": "buy_item",
                "target": "Health Potion",
                "reasoning": "Buying potion while I can"
            }
        if personality == "greedy":
            # Greedy heroes love shopping
            return {
                "action": "buy_item",
                "target": "Health Potion",
                "reasoning": "Stocking up on supplies"
            }
        elif _MOCK_RNG.random() < 0.4:
            return {
                "action": "buy_item",
                "target": "Health Potion",
                "reasoning": "Good opportunity to stock up"
            }

    # Combat behavior
    if in_combat:
        return {
            "action": "fight",
            "target": "",
            "reasoning": "Engaging the enemy!"
        }

    # Default: explore
    return {
        "action": "explore",
        "target": "",
        "reasoning": "Looking for adventure"
    }
