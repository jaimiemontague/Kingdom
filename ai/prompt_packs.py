"""
Structured prompt packs for LLM modes (WK50 Phase 2A autonomous pack; Phase 2B direct prompt pack).
"""

from __future__ import annotations

import json
from typing import Any

from ai.direct_prompt_validator import SUPPORTED_DIRECT_INTENTS

DIRECT_PROMPT_MARK = "WK50_DIRECT_PROMPT_V1"


def format_direct_system_prompt(hero_name: str) -> str:
    return f"""{DIRECT_PROMPT_MARK}
You are {hero_name}, a hero in Kingdom Sim.
The Sovereign may speak to you in plain English.
You are not mind-controlled, but you usually try to honor clear requests if they are safe, possible, and within your abilities.

You may only choose supported command intents (see user message list). Do not invent places, enemies, items, spells, coordinates, memories, or quests.
Use only known places from the provided context and visible/current situation.
If a request is unsafe, impossible, unknown, or outside supported commands, refuse or redirect in character and pick the safest useful interpretation.

Return strict JSON only, with no markdown or commentary outside the JSON object."""

AUTONOMOUS_SYSTEM_PROMPT = """You are an autonomous hero in Kingdom Sim, an indirect-control fantasy kingdom simulation.
You are not directly controlled by the player. You make decisions based on your identity, personality, current situation, known places, and survival needs.

You must obey game reality:
- Use only actions listed in allowed_actions for this moment.
- Do not invent buildings, enemies, items, spells, coordinates, memories, or quests.
- Use known places when choosing destinations for move_to or retreat targets when applicable.
- Personality may bias your risk tolerance but must not override obvious survival.
- If uncertain, choose the safest valid action.

Return strict JSON only, with no markdown or commentary outside the JSON object."""

AUTONOMOUS_OUTPUT_KEYS = (
    "action",
    "target",
    "reasoning",
    "confidence",
    "memory_used",
    "personality_influence",
)


def build_direct_prompt_messages(hero_context: dict[str, Any], conversation_history: list, player_message: str) -> tuple[str, str]:
    """Build (system_prompt, user_prompt) for WK50 Phase 2B direct player commands."""
    hero = hero_context["hero"]
    system_prompt = format_direct_system_prompt(hero["name"])

    conv_lines: list[str] = []
    for msg in (conversation_history or [])[-6:]:
        role = msg.get("role", "")
        text = msg.get("text", "")
        if role == "player":
            conv_lines.append(f"Sovereign: {text}")
        else:
            conv_lines.append(f"{hero['name']}: {text}")
    conversation_tail = "\n".join(conv_lines) if conv_lines else "(No prior messages.)"

    output_schema = {
        "spoken_response": "in-character words the hero speaks aloud (2-3 sentences max)",
        "interpreted_intent": f"one of {sorted(SUPPORTED_DIRECT_INTENTS)}",
        "tool_action": "one of leave_building, move_to, fight, retreat, buy_item, use_potion, explore, or null",
        "target_kind": "known_place | none | direction",
        "target_id": "known place_id from context when applicable, else empty string",
        "target_description": "human label e.g. Inn, Castle",
        "obey_defy": "Obey or Defy — must match whether tool_action is non-null (Obey only when a safe command actually executes)",
        "refusal_reason": "short machine token when refusing, else empty string when obeying with a physical tool",
        "safety_assessment": "safe | critical_redirect | unsafe_requested_action | impossible | unknown_target | deferred | etc.",
        "confidence": "number 0..1",
    }
    blob = {
        "task": "Interpret the Sovereign's latest message. Choose one supported intent and optional safe physical action.",
        "supported_intents": sorted(SUPPORTED_DIRECT_INTENTS),
        "hero": hero_context.get("hero"),
        "situation": hero_context.get("situation", {}),
        "current_location": hero_context.get("current_location", "outdoors"),
        "inventory": hero_context.get("inventory", {}),
        "distances": hero_context.get("distances", {}),
        "known_places_llm": hero_context.get("known_places_llm", []),
        "hero_home_place_id": hero_context.get("hero_home_place_id", ""),
        "shop_items": hero_context.get("shop_items") or [],
        "market_catalog_items": hero_context.get("market_catalog_items") or [],
        "player_message": (player_message or "").strip(),
        "conversation_tail": conversation_tail,
        "output_schema": output_schema,
    }
    lines = [
        json.dumps(blob, indent=2, default=str),
        "",
        "Respond with a single JSON object matching output_schema. "
        "interpreted_intent must be exactly one of supported_intents. "
        "tool_action must be null when no physical action is appropriate. "
        "If you cannot honor the request (unknown place, no heading, no market, no coin), use Defy with a refusal_reason and null tool_action—do not claim Obey. "
        "Do not choose fight for direct commands in this MVP (combat requests should become no_action_chat_only with an in-character deferral).",
    ]
    user_prompt = "\n".join(lines)
    return system_prompt, user_prompt


def build_autonomous_user_prompt(context: dict[str, Any]) -> str:
    """Build the user message for an autonomous decision request."""
    allowed = context.get("allowed_actions", [])
    schema = {
        "action": "one of allowed_actions",
        "target": "string place/item label when required; else empty string",
        "reasoning": "brief factual justification",
        "confidence": "number 0..1",
        "memory_used": "optional list of entry_id strings you relied on",
        "personality_influence": "optional short phrase",
    }
    blob = {
        "task": "Choose the best next action for this decision moment.",
        "context": context,
        "output_schema": schema,
        "allowed_actions": allowed,
    }
    lines = [
        json.dumps(blob, indent=2, default=str),
        "",
        "Respond with a single JSON object matching output_schema. "
        "The action field must be exactly one of allowed_actions.",
    ]
    return "\n".join(lines)
