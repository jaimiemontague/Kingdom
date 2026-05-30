"""Direct-prompt mock responder (WK50 Phase 2B). Extracted WK81 from
ai/providers/mock_provider.py via pure move.

Owns the module helpers _hero_ctx_from_prompt_blob / _emit_validated_direct
(used only by this responder). _norm_msg is a leaf copy of the same trivial
helper kept on the MockProvider facade in ai/providers/mock_provider.py."""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from ai.direct_prompt_validator import validate_direct_prompt_output

if TYPE_CHECKING:
    from ai.providers.mock_provider import MockProvider


def _norm_msg(s: str) -> str:
    return str(s or "").strip().lower()


def _hero_ctx_from_prompt_blob(blob: dict) -> dict:
    """Rebuild hero_context shape expected by validate_direct_prompt_output."""
    return {
        "hero": blob.get("hero") or {},
        "situation": blob.get("situation") or {},
        "inventory": blob.get("inventory") or {},
        "current_location": blob.get("current_location", "outdoors"),
        "distances": blob.get("distances") or {},
        "known_places_llm": list(blob.get("known_places_llm") or []),
        "shop_items": list(blob.get("shop_items") or []),
        "market_catalog_items": list(blob.get("market_catalog_items") or []),
        "hero_home_place_id": str(blob.get("hero_home_place_id") or ""),
    }


def _emit_validated_direct(raw: dict, blob: dict) -> str:
    ctx = _hero_ctx_from_prompt_blob(blob)
    msg = str(blob.get("player_message") or "")
    return json.dumps(validate_direct_prompt_output(raw, ctx, msg))


def mock_direct_prompt(provider: "MockProvider", user_prompt: str) -> str:
    """Deterministic WK50 Phase 2B JSON; mirrors common player phrases from sprint plan."""
    cut = user_prompt.find("\n\nRespond")
    raw = user_prompt[:cut].strip() if cut > 0 else user_prompt.strip()
    try:
        blob = json.loads(raw)
    except json.JSONDecodeError:
        blob = {}
    msg = _norm_msg(blob.get("player_message", ""))
    places = list(blob.get("known_places_llm") or [])

    def find_place(*types: str) -> dict | None:
        tl = {t.lower() for t in types}
        for p in places:
            if str(p.get("place_type", "")).lower() in tl:
                return p
        return None

    def base(**kwargs: object) -> dict:
        out = {
            "spoken_response": str(kwargs.get("spoken_response", "")),
            "interpreted_intent": str(kwargs.get("interpreted_intent", "no_action_chat_only")),
            "tool_action": kwargs.get("tool_action"),
            "target_kind": str(kwargs.get("target_kind", "")),
            "target_id": str(kwargs.get("target_id", "")),
            "target_description": str(kwargs.get("target_description", "")),
            "obey_defy": str(kwargs.get("obey_defy", "Obey")),
            "refusal_reason": str(kwargs.get("refusal_reason", "")),
            "safety_assessment": str(kwargs.get("safety_assessment", "safe")),
            "confidence": float(kwargs.get("confidence", 0.88)),
        }
        return out

    if re.search(r"attack\b.*\blair\b|\blair\b.*attack", msg) or "attack the lair" in msg:
        return _emit_validated_direct(
            base(
                spoken_response="Sovereign, I am not commissioned to storm lairs by chat—let the realm place a bounty if we must strike.",
                interpreted_intent="no_action_chat_only",
                tool_action=None,
                safety_assessment="deferred",
                refusal_reason="mvp_combat_deferred",
                obey_defy="Defy",
            ),
            blob,
        )

    if "how are you" in msg or "how r you" in msg:
        return _emit_validated_direct(
            base(
                spoken_response="I stand ready, my liege—wounded or whole, I serve the crown.",
                interpreted_intent="status_report",
                tool_action=None,
                safety_assessment="safe",
            ),
            blob,
        )

    if "go home" in msg or "return home" in msg or "head home" in msg:
        home_bt = _norm_msg((blob.get("hero") or {}).get("home_building_type", ""))
        home = find_place(home_bt) if home_bt else None
        if home is None:
            home = find_place("castle", "inn", "warrior_guild", "ranger_guild", "rogue_guild", "wizard_guild", "temple")
        tid = str(home.get("place_id", "")) if home else ""
        tdesc = str(home.get("display_name", "")) if home else ""
        return _emit_validated_direct(
            base(
                spoken_response="Aye, Sovereign—I will make for hearth and shelter."
                if home
                else "",
                interpreted_intent="return_home",
                tool_action="move_to" if home else None,
                target_kind="known_place" if home else "",
                target_id=tid,
                target_description=tdesc or ("Castle" if home else ""),
            ),
            blob,
        )

    if "heal" in msg and "potion" not in msg:
        return _emit_validated_direct(
            base(
                spoken_response="I'll bind my wounds and find succor—potions or hearth.",
                interpreted_intent="seek_healing",
                tool_action="use_potion",
                target_kind="none",
                safety_assessment="safe",
            ),
            blob,
        )

    if "buy" in msg and "potion" in msg:
        mart = find_place("marketplace")
        tid = str(mart.get("place_id", "")) if mart else ""
        tdesc = str(mart.get("display_name", "Marketplace")) if mart else ""
        return _emit_validated_direct(
            base(
                spoken_response=""
                if not mart
                else (
                    "The market is known—I will march there and buy what draughts I can afford."
                    if not bool((blob.get("situation") or {}).get("can_shop"))
                    else ""
                ),
                interpreted_intent="buy_potions",
                tool_action="move_to" if mart else None,
                target_kind="known_place" if mart else "",
                target_id=tid,
                target_description=tdesc,
            ),
            blob,
        )

    if re.search(r"(?<![a-z0-9_])inn(?![a-z0-9_])", msg):
        inn = find_place("inn")
        if inn:
            return _emit_validated_direct(
                base(
                    spoken_response="The inn it is—I know the road.",
                    interpreted_intent="go_to_known_place",
                    tool_action="move_to",
                    target_kind="known_place",
                    target_id=str(inn.get("place_id", "")),
                    target_description=str(inn.get("display_name", "Inn")),
                ),
                blob,
            )
        return _emit_validated_direct(
            base(
                spoken_response="I don't recall an inn yet, Sovereign—I'll need to discover one first.",
                interpreted_intent="go_to_known_place",
                tool_action=None,
                refusal_reason="unknown_place",
                safety_assessment="unknown_target",
                obey_defy="Defy",
            ),
            blob,
        )

    if "explore" in msg and any(d in msg for d in ("east", "west", "north", "south")):
        return _emit_validated_direct(
            base(
                spoken_response="I'll scout that bearing and report what I find.",
                interpreted_intent="explore_direction",
                tool_action="explore",
                target_kind="direction",
                target_description="",
            ),
            blob,
        )

    if "rest" in msg and "heal" in msg:
        return _emit_validated_direct(
            base(
                spoken_response="I'll rest until the color returns to my cheeks.",
                interpreted_intent="rest_until_healed",
                tool_action=None,
            ),
            blob,
        )

    hero_name = str((blob.get("hero") or {}).get("name", "hero"))
    return _emit_validated_direct(
        base(
            spoken_response=f"I hear you, Sovereign—say again if you need a march, a market-run, or a reckoning of my wounds. ({hero_name})",
            interpreted_intent="no_action_chat_only",
            tool_action=None,
        ),
        blob,
    )
