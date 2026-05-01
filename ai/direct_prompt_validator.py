"""
WK50 Phase 2B: validate direct-prompt (player chat) JSON before any physical action.

LLM output is advisory; this module enforces intent allowlists, tool_action bounds,
known-place targets, and MVP deferral of attack commands.
"""

from __future__ import annotations

from typing import Any

from ai.prompt_templates import OBEY_DEFY_VALUES, TOOL_ACTIONS
from game.sim.direct_prompt_targets import parse_compass_direction

SUPPORTED_DIRECT_INTENTS = frozenset(
    {
        "status_report",
        "return_home",
        "seek_healing",
        "go_to_known_place",
        "buy_potions",
        "explore_direction",
        "rest_until_healed",
        "no_action_chat_only",
    }
)

# Not supported in MVP; explicit labels the model might emit.
DEFERRED_COMBAT_INTENTS = frozenset(
    {
        "attack_known_lair",
        "attack_nearest_enemy",
        "attack_lair",
        "attack_enemy",
    }
)

_PLACE_TYPE_TO_MOVE_TARGET = {
    "castle": "castle",
    "inn": "inn",
    "marketplace": "marketplace",
    "blacksmith": "blacksmith",
    "warrior_guild": "castle",
}


def _norm_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _norm_tool_action(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s or s in ("null", "none"):
        return None
    return s


def _places_index(hero_context: dict[str, Any]) -> list[dict[str, Any]]:
    return list(hero_context.get("known_places_llm") or [])


def _target_for_place_row(row: dict[str, Any]) -> str:
    ptype = _norm_str(row.get("place_type")).lower()
    if ptype in _PLACE_TYPE_TO_MOVE_TARGET:
        return _PLACE_TYPE_TO_MOVE_TARGET[ptype]
    dn = _norm_str(row.get("display_name")).lower()
    return dn.split()[0] if dn else ptype


def _pick_home_place(places: list[dict[str, Any]]) -> dict[str, Any] | None:
    for key in ("castle", "inn"):
        for p in places:
            if _norm_str(p.get("place_type")).lower() == key:
                return p
    return None


def _pick_marketplace(places: list[dict[str, Any]]) -> dict[str, Any] | None:
    for p in places:
        if _norm_str(p.get("place_type")).lower() == "marketplace":
            return p
    return None


def _find_place_by_hint(places: list[dict[str, Any]], target_id: str, description: str) -> dict[str, Any] | None:
    tid = target_id.strip().lower()
    desc = description.strip().lower()
    for p in places:
        pid = _norm_str(p.get("place_id")).lower()
        if tid and pid == tid:
            return p
        ptype = _norm_str(p.get("place_type")).lower()
        dn = _norm_str(p.get("display_name")).lower()
        if tid and tid in pid:
            return p
        if desc and (desc in dn or desc in ptype or ptype in desc):
            return p
    if desc in ("inn", "castle", "marketplace", "blacksmith"):
        for p in places:
            if _norm_str(p.get("place_type")).lower() == desc:
                return p
    return None


def validate_direct_prompt_output(
    raw: Any,
    hero_context: dict[str, Any],
    player_message: str = "",
) -> dict[str, Any]:
    """
    Return a dict safe for GameEngine chat polling: spoken_response, optional tool_action/action/target,
    plus interpreted_intent and audit fields. Physical fields are omitted or nulled when invalid.
    """
    situation = hero_context.get("situation") or {}
    critical = bool(situation.get("critical_health"))
    has_potions = bool(situation.get("has_potions"))
    can_shop = bool(situation.get("can_shop"))
    places = _places_index(hero_context)

    if not isinstance(raw, dict):
        raw = {
            "spoken_response": "I could not make sense of that, Sovereign.",
            "interpreted_intent": "no_action_chat_only",
            "tool_action": None,
        }

    spoken = _norm_str(raw.get("spoken_response")) or "Aye, Sovereign."
    intent = _norm_str(raw.get("interpreted_intent")).lower() or "no_action_chat_only"
    tool = _norm_tool_action(raw.get("tool_action"))
    target_id = _norm_str(raw.get("target_id"))
    target_description = _norm_str(raw.get("target_description"))
    obey = _norm_str(raw.get("obey_defy"))
    if obey not in OBEY_DEFY_VALUES:
        obey = "Obey"
    refusal = _norm_str(raw.get("refusal_reason"))
    safety = _norm_str(raw.get("safety_assessment")) or "unknown"
    try:
        conf = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    deferred_combat = intent in DEFERRED_COMBAT_INTENTS or intent.startswith("attack_")
    if deferred_combat:
        return {
            "spoken_response": spoken
            or "My lord, I cannot march on a lair or duel by decree—not yet. Ask me to heal, return home, or scout.",
            "interpreted_intent": "no_action_chat_only",
            "tool_action": None,
            "action": None,
            "target": "",
            "target_kind": "",
            "target_id": "",
            "target_description": "",
            "obey_defy": "Defy",
            "refusal_reason": "mvp_combat_deferred",
            "safety_assessment": "deferred",
            "confidence": conf,
        }

    if tool == "fight":
        tool = None

    if intent not in SUPPORTED_DIRECT_INTENTS:
        intent = "no_action_chat_only"
        tool = None

    if tool is not None and tool not in TOOL_ACTIONS:
        tool = None

    if critical and intent in ("explore_direction", "go_to_known_place") and has_potions:
        intent = "seek_healing"
        tool = "use_potion"
        target_id = ""
        target_description = ""
        obey = "Obey"
        safety = "critical_redirect"
        if not spoken or len(spoken) < 10:
            spoken = "Forgive me—I am too badly hurt to wander. I will drink what I have."
    elif critical and intent in ("explore_direction", "go_to_known_place"):
        intent = "seek_healing"
        home = _pick_home_place(places)
        if home:
            tool = "retreat"
            target_id = _norm_str(home.get("place_id"))
            target_description = _norm_str(home.get("display_name")) or "castle"
            obey = "Obey"
            safety = "critical_redirect"
            if not spoken or len(spoken) < 10:
                spoken = "I must find safety first—I am barely on my feet."
        else:
            tool = None
            refusal = refusal or "no_safe_haven_known"
            safety = "impossible"
            obey = "Defy"
            target_id = ""
            target_description = ""
            spoken = spoken or "I am too badly hurt and know no hearth—send help if you can, Sovereign."

    target_row: dict[str, Any] | None = None
    move_target = ""

    if intent == "status_report":
        tool = None
    elif intent == "no_action_chat_only":
        tool = None
    elif intent == "return_home":
        home = _pick_home_place(places)
        if home:
            target_row = home
            move_target = _target_for_place_row(home)
            if tool not in ("move_to", "retreat", None):
                tool = "move_to"
            if tool is None:
                tool = "move_to"
        else:
            if situation.get("near_safety") and can_shop:
                tool = "move_to"
                move_target = "castle"
            else:
                tool = None
                obey = "Defy" if obey == "Obey" else obey
                refusal = refusal or "no_known_home"
                safety = "impossible"
                spoken = spoken or "I know of nowhere safe to run, Sovereign."
    elif intent == "seek_healing":
        if has_potions and situation.get("low_health"):
            tool = "use_potion"
            move_target = ""
        else:
            home = _pick_home_place(places)
            if home:
                target_row = home
                move_target = _target_for_place_row(home)
                tool = "retreat" if tool not in ("retreat", "move_to", None) else tool
                if tool is None:
                    tool = "retreat"
            else:
                tool = None
                refusal = refusal or "no_safe_haven_known"
                safety = "impossible"
                obey = "Defy"
                spoken = spoken or "I know of no hall or inn to limp toward, Sovereign."
    elif intent == "go_to_known_place":
        target_row = _find_place_by_hint(places, target_id, target_description)
        if target_row:
            move_target = _target_for_place_row(target_row)
            if tool not in ("move_to", "retreat", None):
                tool = "move_to"
            if tool is None:
                tool = "move_to"
            target_id = _norm_str(target_row.get("place_id"))
            target_description = _norm_str(target_row.get("display_name")) or target_description
        else:
            tool = None
            intent = "no_action_chat_only"
            refusal = refusal or "unknown_place"
            safety = "unknown_target"
            spoken = spoken or "I do not know that place yet, my liege."
    elif intent == "buy_potions":
        hero_d = hero_context.get("hero") or {}
        gold = int(hero_d.get("gold", 0) or 0)
        if can_shop:
            items = list(hero_context.get("shop_items") or [])
            potion_item = next(
                (i for i in items if "potion" in _norm_str(i.get("name")).lower()),
                None,
            )
            if potion_item and potion_item.get("can_afford"):
                tool = "buy_item"
                move_target = _norm_str(potion_item.get("name")) or "Health Potion"
            elif potion_item and not potion_item.get("can_afford"):
                tool = None
                intent = "no_action_chat_only"
                refusal = refusal or ("no_gold" if gold <= 0 else "insufficient_gold")
                safety = "impossible"
                obey = "Defy"
                spoken = spoken or (
                    "I haven't the coin for that draught, Sovereign."
                    if gold > 0
                    else "I haven't the coin for potions, Sovereign."
                )
            else:
                tool = None
                intent = "no_action_chat_only"
                refusal = refusal or "no_potions_here"
                safety = "impossible"
                obey = "Defy"
                spoken = spoken or "No healing vials here—I'll need another stall or apothecary."
        else:
            m = _pick_marketplace(places)
            if m:
                target_row = m
                tool = "move_to"
                move_target = _target_for_place_row(m)
            else:
                tool = None
                refusal = refusal or "no_market_known"
                safety = "impossible"
                intent = "no_action_chat_only"
                obey = "Defy"
                spoken = spoken or "I know of no market where I can spend coin."
    elif intent == "explore_direction":
        dirn = parse_compass_direction(
            _norm_str(player_message),
            target_description,
            target_id,
        )
        if not dirn:
            tool = None
            intent = "no_action_chat_only"
            refusal = refusal or "unknown_heading"
            safety = "unknown_target"
            obey = "Defy"
            spoken = spoken or (
                "Name a compass way—east, west, north, or south—and I'll scout it, Sovereign."
            )
            move_target = ""
        else:
            if tool not in ("explore", None):
                tool = "explore"
            if tool is None:
                tool = "explore"
            move_target = ""
            target_description = dirn
    elif intent == "rest_until_healed":
        if _norm_str(hero_context.get("current_location", "")).lower() not in ("outdoors", ""):
            tool = "leave_building" if tool not in ("leave_building", None) else "leave_building"
            move_target = ""
        else:
            home = _pick_home_place(places)
            if home:
                tool = "move_to"
                move_target = _target_for_place_row(home)
            else:
                tool = None
                refusal = refusal or "no_known_rest_place"
                safety = "impossible"
                obey = "Defy"
                spoken = spoken or "I know of no roof to rest under—point me to an inn or hold."

    target_id_out = _norm_str(target_row.get("place_id")) if target_row else ""
    if intent == "go_to_known_place":
        target_id_out = target_id

    out: dict[str, Any] = {
        "spoken_response": spoken,
        "interpreted_intent": intent,
        "tool_action": tool,
        "action": tool,
        "target": move_target,
        "target_kind": (
            "direction"
            if tool == "explore" and intent == "explore_direction"
            else (_norm_str(raw.get("target_kind")) or ("known_place" if target_row else ""))
        ),
        "target_id": target_id_out,
        "target_description": target_description,
        "obey_defy": obey,
        "refusal_reason": refusal,
        "safety_assessment": safety,
        "confidence": conf,
    }

    if tool is None:
        out["action"] = None
        out["target"] = ""
        out["target_kind"] = out.get("target_kind") or ""
    else:
        out["obey_defy"] = "Obey"
        out["refusal_reason"] = ""
        if str(out.get("safety_assessment") or "") in ("", "unknown"):
            out["safety_assessment"] = "safe"

    if tool == "buy_item":
        out["target"] = move_target or "Health Potion"

    if out.get("tool_action") is None:
        tin = str(out.get("interpreted_intent") or "")
        if tin in ("status_report", "no_action_chat_only"):
            if out.get("refusal_reason"):
                out["obey_defy"] = "Defy"
        else:
            out["obey_defy"] = "Defy"
            if not out.get("refusal_reason"):
                out["refusal_reason"] = "not_executable"
            sa = str(out.get("safety_assessment") or "")
            if sa in ("", "unknown", "safe"):
                out["safety_assessment"] = "impossible"

    return out
