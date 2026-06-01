"""
WK50 Phase 2B: validate direct-prompt (player chat) JSON before any physical action.

LLM output is advisory; this module enforces intent allowlists, tool_action bounds,
known-place targets, and MVP deferral of attack commands.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai.prompt_templates import OBEY_DEFY_VALUES, TOOL_ACTIONS
from ai.vocab import (
    DEFERRED_COMBAT_INTENTS as _VOCAB_DEFERRED_COMBAT_INTENTS,
    DirectIntent,
    PLACE_TYPE_TO_MOVE_TARGET,
    PLAYER_HOME_TYPES,
)
from game.sim.direct_prompt_targets import parse_compass_direction

# WK110: derived from the canonical ``ai.vocab`` definitions. Re-exported under the SAME
# names, collection types (frozenset / dict), and membership as the pre-WK110 literals so
# every by-name importer and read-site is unchanged and the WK67 digest stays byte-identical.
SUPPORTED_DIRECT_INTENTS = frozenset(i.value for i in DirectIntent)

# Not supported in MVP; explicit labels the model might emit.
DEFERRED_COMBAT_INTENTS = frozenset(_VOCAB_DEFERRED_COMBAT_INTENTS)

_PLACE_TYPE_TO_MOVE_TARGET = PLACE_TYPE_TO_MOVE_TARGET

_PLAYER_HOME_TYPES = PLAYER_HOME_TYPES


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
    if ptype in _PLAYER_HOME_TYPES:
        return ptype
    if ptype in _PLACE_TYPE_TO_MOVE_TARGET:
        return _PLACE_TYPE_TO_MOVE_TARGET[ptype]
    dn = _norm_str(row.get("display_name")).lower()
    return dn.split()[0] if dn else ptype


def _pick_home_place(
    places: list[dict[str, Any]],
    hero_context: dict[str, Any],
) -> dict[str, Any] | None:
    """Prefer authoritative hire/spawn home (guild/temple), then castle/inn fallbacks."""

    canon = _norm_str(hero_context.get("hero_home_place_id")).lower()
    if canon:
        for p in places:
            if _norm_str(p.get("place_id")).lower() == canon:
                return p
    hb_type = _norm_str((hero_context.get("hero") or {}).get("home_building_type")).lower()
    if hb_type:
        for p in places:
            if _norm_str(p.get("place_type")).lower() == hb_type:
                return p
        for key in ("castle", "inn"):
            for p in places:
                if _norm_str(p.get("place_type")).lower() == key:
                    return p
        return None
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


# ---------------------------------------------------------------------------
# WK112: per-intent handler table. The 8-branch intent chain of
# validate_direct_prompt_output was lifted, branch-for-branch, into the
# handlers below. Each handler is a faithful transcription of one former
# ``elif`` block (LOCAL -> st.LOCAL; context reads -> inp.*); the dispatch
# table preserves the original "exactly one branch runs, unknown -> no-op"
# semantics. The prelude, the critical-HP redirect, and the output-assembly
# tail remain in validate_direct_prompt_output. Behavior is byte-identical;
# see tests/test_wk112_direct_prompt_validator.py (38-case golden).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ValidationInputs:
    """Immutable read context shared by the per-intent handlers."""

    places: list[dict[str, Any]]
    hero_context: dict[str, Any]
    situation: dict[str, Any]
    critical: bool
    has_potions: bool
    can_shop: bool
    player_message: str


@dataclass
class _ResolveState:
    """Mutable working state threaded through the per-intent handlers.

    Holds exactly the locals the original inline if/elif chain mutated, so each
    handler is a verbatim lift of one branch. The caller seeds it from the
    normalized inputs, applies the critical-HP redirect, dispatches to the
    matching handler, then reads it back to assemble the output dict.
    """

    intent: str
    tool: str | None
    target_id: str
    target_description: str
    obey: str
    refusal: str
    safety: str
    spoken: str
    move_target: str = ""
    target_row: dict[str, Any] | None = None


def _apply_critical_health_redirect(st: _ResolveState, inp: _ValidationInputs) -> None:
    """Critical-HP override (orig lines 184-211). Runs BEFORE intent dispatch and
    may rewrite ``st.intent`` to ``seek_healing`` (which the dispatch then re-runs)."""
    if inp.critical and st.intent in ("explore_direction", "go_to_known_place") and inp.has_potions:
        st.intent = "seek_healing"
        st.tool = "use_potion"
        st.target_id = ""
        st.target_description = ""
        st.obey = "Obey"
        st.safety = "critical_redirect"
        if not st.spoken or len(st.spoken) < 10:
            st.spoken = "Forgive me—I am too badly hurt to wander. I will drink what I have."
    elif inp.critical and st.intent in ("explore_direction", "go_to_known_place"):
        st.intent = "seek_healing"
        home = _pick_home_place(inp.places, inp.hero_context)
        if home:
            st.tool = "retreat"
            st.target_id = _norm_str(home.get("place_id"))
            st.target_description = _norm_str(home.get("display_name")) or "castle"
            st.obey = "Obey"
            st.safety = "critical_redirect"
            if not st.spoken or len(st.spoken) < 10:
                st.spoken = "I must find safety first—I am barely on my feet."
        else:
            st.tool = None
            st.refusal = st.refusal or "no_safe_haven_known"
            st.safety = "impossible"
            st.obey = "Defy"
            st.target_id = ""
            st.target_description = ""
            st.spoken = st.spoken or "I am too badly hurt and know no hearth—send help if you can, Sovereign."


def _handle_clear_tool(st: _ResolveState, inp: _ValidationInputs) -> None:
    """status_report / no_action_chat_only (orig 216-219): just clear the tool."""
    st.tool = None


def _handle_return_home(st: _ResolveState, inp: _ValidationInputs) -> None:
    home = _pick_home_place(inp.places, inp.hero_context)
    if home:
        st.target_row = home
        st.move_target = _target_for_place_row(home)
        if st.tool not in ("move_to", "retreat", None):
            st.tool = "move_to"
        if st.tool is None:
            st.tool = "move_to"
    else:
        if inp.situation.get("near_safety") and inp.can_shop:
            st.tool = "move_to"
            st.move_target = "castle"
        else:
            st.tool = None
            st.obey = "Defy" if st.obey == "Obey" else st.obey
            st.refusal = st.refusal or "no_known_home"
            st.safety = "impossible"
            st.spoken = st.spoken or "I know of nowhere safe to run, Sovereign."


def _handle_seek_healing(st: _ResolveState, inp: _ValidationInputs) -> None:
    if inp.has_potions and inp.situation.get("low_health"):
        st.tool = "use_potion"
        st.move_target = ""
    else:
        home = _pick_home_place(inp.places, inp.hero_context)
        if home:
            st.target_row = home
            st.move_target = _target_for_place_row(home)
            st.tool = "retreat" if st.tool not in ("retreat", "move_to", None) else st.tool
            if st.tool is None:
                st.tool = "retreat"
        else:
            st.tool = None
            st.refusal = st.refusal or "no_safe_haven_known"
            st.safety = "impossible"
            st.obey = "Defy"
            st.spoken = st.spoken or "I know of no hall or inn to limp toward, Sovereign."


def _handle_go_to_known_place(st: _ResolveState, inp: _ValidationInputs) -> None:
    st.target_row = _find_place_by_hint(inp.places, st.target_id, st.target_description)
    if st.target_row:
        st.move_target = _target_for_place_row(st.target_row)
        if st.tool not in ("move_to", "retreat", None):
            st.tool = "move_to"
        if st.tool is None:
            st.tool = "move_to"
        st.target_id = _norm_str(st.target_row.get("place_id"))
        st.target_description = _norm_str(st.target_row.get("display_name")) or st.target_description
    else:
        st.tool = None
        st.intent = "no_action_chat_only"
        st.refusal = st.refusal or "unknown_place"
        st.safety = "unknown_target"
        st.spoken = st.spoken or "I do not know that place yet, my liege."


def _handle_buy_potions(st: _ResolveState, inp: _ValidationInputs) -> None:
    hero_d = inp.hero_context.get("hero") or {}
    gold = int(hero_d.get("gold", 0) or 0)
    if inp.can_shop:
        items = list(inp.hero_context.get("shop_items") or [])
        potion_item = next(
            (i for i in items if "potion" in _norm_str(i.get("name")).lower()),
            None,
        )
        # WK50 R17: direct prompt blob may omit proximity shop_items; use remembered/nearest
        # marketplace catalog from ContextBuilder so MockProvider validation matches reality.
        if potion_item is None:
            catalog = list(inp.hero_context.get("market_catalog_items") or [])
            potion_item = next(
                (i for i in catalog if "potion" in _norm_str(i.get("name")).lower()),
                None,
            )
        if potion_item and potion_item.get("can_afford"):
            st.tool = "buy_item"
            st.move_target = _norm_str(potion_item.get("name")) or "Health Potion"
        elif potion_item and not potion_item.get("can_afford"):
            st.tool = None
            st.intent = "no_action_chat_only"
            st.refusal = st.refusal or ("no_gold" if gold <= 0 else "insufficient_gold")
            st.safety = "impossible"
            st.obey = "Defy"
            st.spoken = st.spoken or (
                "I haven't the coin for that draught, Sovereign."
                if gold > 0
                else "I haven't the coin for potions, Sovereign."
            )
        else:
            st.tool = None
            st.intent = "no_action_chat_only"
            st.refusal = st.refusal or "no_potions_here"
            st.safety = "impossible"
            st.obey = "Defy"
            st.spoken = st.spoken or "No healing vials here—I'll need another stall or apothecary."
    else:
        m = _pick_marketplace(inp.places)
        if m:
            st.target_row = m
            st.tool = "move_to"
            st.move_target = _target_for_place_row(m)
        else:
            st.tool = None
            st.refusal = st.refusal or "no_market_known"
            st.safety = "impossible"
            st.intent = "no_action_chat_only"
            st.obey = "Defy"
            st.spoken = st.spoken or "I know of no market where I can spend coin."


def _handle_explore_direction(st: _ResolveState, inp: _ValidationInputs) -> None:
    dirn = parse_compass_direction(
        _norm_str(inp.player_message),
        st.target_description,
        st.target_id,
    )
    if not dirn:
        st.tool = None
        st.intent = "no_action_chat_only"
        st.refusal = st.refusal or "unknown_heading"
        st.safety = "unknown_target"
        st.obey = "Defy"
        st.spoken = st.spoken or (
            "Name a compass way—east, west, north, or south—and I'll scout it, Sovereign."
        )
        st.move_target = ""
    else:
        if st.tool not in ("explore", None):
            st.tool = "explore"
        if st.tool is None:
            st.tool = "explore"
        st.move_target = ""
        st.target_description = dirn


def _handle_rest_until_healed(st: _ResolveState, inp: _ValidationInputs) -> None:
    if _norm_str(inp.hero_context.get("current_location", "")).lower() not in ("outdoors", ""):
        st.tool = "leave_building" if st.tool not in ("leave_building", None) else "leave_building"
        st.move_target = ""
    else:
        home = _pick_home_place(inp.places, inp.hero_context)
        if home:
            st.tool = "move_to"
            st.move_target = _target_for_place_row(home)
        else:
            st.tool = None
            st.refusal = st.refusal or "no_known_rest_place"
            st.safety = "impossible"
            st.obey = "Defy"
            st.spoken = st.spoken or "I know of no roof to rest under—point me to an inn or hold."


_INTENT_HANDLERS: dict[str, Callable[[_ResolveState, _ValidationInputs], None]] = {
    "status_report": _handle_clear_tool,
    "no_action_chat_only": _handle_clear_tool,
    "return_home": _handle_return_home,
    "seek_healing": _handle_seek_healing,
    "go_to_known_place": _handle_go_to_known_place,
    "buy_potions": _handle_buy_potions,
    "explore_direction": _handle_explore_direction,
    "rest_until_healed": _handle_rest_until_healed,
}


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

    st = _ResolveState(
        intent=intent,
        tool=tool,
        target_id=target_id,
        target_description=target_description,
        obey=obey,
        refusal=refusal,
        safety=safety,
        spoken=spoken,
    )
    inp = _ValidationInputs(
        places=places,
        hero_context=hero_context,
        situation=situation,
        critical=critical,
        has_potions=has_potions,
        can_shop=can_shop,
        player_message=player_message,
    )

    _apply_critical_health_redirect(st, inp)

    handler = _INTENT_HANDLERS.get(st.intent)
    if handler is not None:
        handler(st, inp)

    target_id_out = _norm_str(st.target_row.get("place_id")) if st.target_row else ""
    if st.intent == "go_to_known_place":
        target_id_out = st.target_id

    out: dict[str, Any] = {
        "spoken_response": st.spoken,
        "interpreted_intent": st.intent,
        "tool_action": st.tool,
        "action": st.tool,
        "target": st.move_target,
        "target_kind": (
            "direction"
            if st.tool == "explore" and st.intent == "explore_direction"
            else (_norm_str(raw.get("target_kind")) or ("known_place" if st.target_row else ""))
        ),
        "target_id": target_id_out,
        "target_description": st.target_description,
        "obey_defy": st.obey,
        "refusal_reason": st.refusal,
        "safety_assessment": st.safety,
        "confidence": conf,
    }

    if st.tool is None:
        out["action"] = None
        out["target"] = ""
        out["target_kind"] = out.get("target_kind") or ""
    else:
        out["obey_defy"] = "Obey"
        out["refusal_reason"] = ""
        if str(out.get("safety_assessment") or "") in ("", "unknown"):
            out["safety_assessment"] = "safe"

    if st.tool == "buy_item":
        out["target"] = st.move_target or "Health Potion"

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
