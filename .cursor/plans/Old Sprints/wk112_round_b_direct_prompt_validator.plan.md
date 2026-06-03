# WK112 Round B — `ai/direct_prompt_validator.py` per-intent handler-table decomposition

**Author:** Agent 01 (Executive Producer / PM)
**Status:** PLANNED → in execution
**Plan doc:** this file
**Sprint key (PM hub):** `wk112_round_b_direct_prompt_validator`
**Version target:** patch bump (behavior-preserving refactor; no feature change)
**Verification class:** HEADLESS, pure-logic (NO UI, NO rendering → NO screenshots needed)
**Model for all sub-agents:** `claude-opus-4-8` (opus)

---

## 0. TL;DR for the executing agents

`ai/direct_prompt_validator.py` contains ONE 294-line god-function,
`validate_direct_prompt_output(raw, hero_context, player_message="")` (lines 118–412).
Its body is a cross-cutting prelude (normalize → deferred-combat early-return →
allow-list gating → critical-HP redirect) followed by an **8-branch
`if/elif` intent chain** (lines 216–361) and a tail that assembles the output dict.

**This sprint decomposes the 8-branch intent chain into a per-intent handler table**
(`_INTENT_HANDLERS: dict[str, Callable]`), with each branch lifted VERBATIM into a
small handler function that mutates a shared `_ResolveState` dataclass. The prelude,
the critical-HP redirect, and the output-assembly tail stay in the main function
(the redirect becomes one extracted helper). **The public surface
(`validate_direct_prompt_output` name + signature) is byte-identical, and the
function's output is byte-identical for every input.**

This is a **behavior-preserving refactor**. The load-bearing safety net is a
**differential golden characterization test** (`tests/test_wk112_direct_prompt_validator.py`)
that pins the EXACT output dict for a 38-case matrix covering every branch. PM
captured the golden from current HEAD; it is embedded verbatim in this plan (§4).

**Wave order is mandatory:** Agent 11 writes the golden net FIRST and proves it
GREEN on the UNMODIFIED code (Wave 0); only then does Agent 06 refactor (Wave 1);
then Agent 11 re-verifies full DoD (Wave 2). If the net were written after the
refactor it would pin the new behavior — defeating the point.

**DO NOT COMMIT. DO NOT `git add`. DO NOT `git push`.** PM (Agent 01) owns the commit.

---

## 1. Why this is safe (read before you touch anything)

- The function is the **player-CHAT direct-prompt validator**. It is NOT on the
  autonomous hero-decision path. Therefore the **WK67 keystone AI-decision digest**
  (`b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`) is expected
  to stay byte-identical *trivially* — the digest never calls this function. We
  still gate on it (it must not move).
- The function is **pure** (no I/O, no global mutation, no randomness). Output is a
  deterministic function of `(raw, hero_context, player_message)`. That is what
  makes the differential golden net a complete proof of equivalence.
- The 8 `elif` branches mutate a fixed set of locals:
  `intent, tool, target_id, target_description, obey, refusal, safety, spoken,
  move_target, target_row`. We hoist exactly those into a `_ResolveState`
  dataclass so each branch becomes a faithful lift (`tool = X` → `st.tool = X`).
- **Subtle interplay you MUST preserve** (the golden net pins it, but understand it
  so you don't "fix" it):
  - The critical-HP redirect (orig lines 184–211) runs BEFORE the intent chain and
    can REWRITE `intent` to `"seek_healing"`. The chain then dispatches on the
    *post-redirect* intent, so `_handle_seek_healing` RE-RUNS on top of the
    redirect's writes. Example golden case `critical_explore_has_potion`:
    redirect sets `use_potion`/`critical_redirect`, then seek_healing (low_health
    True) confirms `use_potion`. Case `critical_explore_no_potion_home`: redirect
    sets `retreat` + `target_description="Castle"`, then seek_healing's else-branch
    overwrites `target_row`/`move_target` (→ `target="castle"`, `target_kind="known_place"`)
    but leaves `target_description="Castle"`. **Keep redirect-before-dispatch ordering.**
  - `go_to_known_place`, `buy_potions`, `explore_direction` handlers may reassign
    `st.intent = "no_action_chat_only"`. That happens INSIDE the handler (after it
    is dispatched on the original intent), so it does NOT re-dispatch. The output
    tail reads the final `st.intent`. Faithful as long as the handler runs once.
  - Unknown / unsupported intents: the prelude already forces
    `intent = "no_action_chat_only"` if not in `SUPPORTED_DIRECT_INTENTS`. So every
    dispatched intent is one of the 8 known keys. `_INTENT_HANDLERS.get(intent)`
    returning `None` for any other value (→ no handler runs) exactly matches the
    original "no matching `elif`" no-op.

---

## 2. Current structure (orient yourself — DO NOT change the prelude/tail logic)

`validate_direct_prompt_output` (lines 118–412) in order:

1. **Prelude A — situation flags** (127–131): `situation, critical, has_potions, can_shop, places`.
2. **Prelude B — raw→dict fallback** (133–138).
3. **Prelude C — field normalization** (140–154): `spoken, intent, tool, target_id,
   target_description, obey (+OBEY_DEFY_VALUES clamp), refusal, safety, conf (clamp)`.
4. **Deferred-combat early-return** (156–172): `if intent in DEFERRED_COMBAT_INTENTS
   or intent.startswith("attack_")` → returns a fixed dict. **STAYS INLINE.**
5. **Allow-list gating** (174–182): `fight`→None; unsupported intent→`no_action_chat_only`+tool None;
   tool not in `TOOL_ACTIONS`→None. **STAYS INLINE.**
6. **Critical-HP redirect** (184–211): two branches. **EXTRACT to `_apply_critical_health_redirect`.**
7. **`target_row = None; move_target = ""`** (213–214): becomes `_ResolveState` defaults.
8. **8-branch intent chain** (216–361): **EXTRACT each branch to a handler fn + dispatch table.**
9. **Output assembly + post-processing tail** (363–412). **STAYS INLINE.**

Helpers (keep as module-level functions, called directly by handlers):
`_norm_str`, `_norm_tool_action`, `_places_index`, `_target_for_place_row`,
`_pick_home_place`, `_pick_marketplace`, `_find_place_by_hint`.
Imports kept: `OBEY_DEFY_VALUES, TOOL_ACTIONS` (prompt_templates),
the `ai.vocab` re-exports (`SUPPORTED_DIRECT_INTENTS, DEFERRED_COMBAT_INTENTS,
_PLACE_TYPE_TO_MOVE_TARGET, _PLAYER_HOME_TYPES`), `parse_compass_direction`.

Public consumers that must keep working (signature unchanged):
- `ai/llm_brain.py` (5 call sites: L142, 279, 294, 298, 311)
- `ai/providers/mock/direct_prompt.py` (L41)

---

## 3. Target structure (Agent 06 — implement EXACTLY this)

Add at the top of the module (after the existing imports), then rewrite the
function body. **Every handler body below is a verbatim lift of the matching orig
lines with `LOCAL` → `st.LOCAL` and `places/hero_context/situation/can_shop/
has_potions/player_message` → `inp.*`. Change NOTHING else — no reordering, no
"cleanup," no renamed string literals.**

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ai.prompt_templates import OBEY_DEFY_VALUES, TOOL_ACTIONS
from ai.vocab import (
    DEFERRED_COMBAT_INTENTS as _VOCAB_DEFERRED_COMBAT_INTENTS,
    DirectIntent,
    PLACE_TYPE_TO_MOVE_TARGET,
    PLAYER_HOME_TYPES,
)
from game.sim.direct_prompt_targets import parse_compass_direction

# ... (KEEP the existing module constants block: SUPPORTED_DIRECT_INTENTS,
#      DEFERRED_COMBAT_INTENTS, _PLACE_TYPE_TO_MOVE_TARGET, _PLAYER_HOME_TYPES,
#      and the 7 helper fns _norm_str ... _find_place_by_hint — UNCHANGED.)


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
    """Critical-HP override (orig lines 184–211). Runs BEFORE intent dispatch and
    may rewrite ``st.intent`` to ``seek_healing`` (which the dispatch then re-runs)."""
    if st.intent in ("explore_direction", "go_to_known_place") and inp.critical and inp.has_potions:
        st.intent = "seek_healing"
        st.tool = "use_potion"
        st.target_id = ""
        st.target_description = ""
        st.obey = "Obey"
        st.safety = "critical_redirect"
        if not st.spoken or len(st.spoken) < 10:
            st.spoken = "Forgive me—I am too badly hurt to wander. I will drink what I have."
    elif st.intent in ("explore_direction", "go_to_known_place") and inp.critical:
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


# NOTE: the orig used ``if critical and intent in (...) and has_potions``. The
# transcription above reorders the SAME boolean ``and`` conjuncts (commutative,
# no short-circuit side effects since all are plain reads) only for readability.
# If you prefer zero risk, keep the EXACT original order:
#   ``if inp.critical and st.intent in (...) and inp.has_potions:``  — either is
# byte-identical; the golden net is the arbiter. Prefer the EXACT original order.


def _handle_clear_tool(st: _ResolveState, inp: _ValidationInputs) -> None:
    """status_report / no_action_chat_only (orig 216–219): just clear the tool."""
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
```

Then the **rewritten main function** (prelude + redirect call + dispatch + tail):

```python
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
```

**`field` import note:** the skeleton imports `field` for completeness; if no
default-factory is used, drop `field` from the import to avoid an unused-import
lint. (`target_row`/`move_target` use plain literal defaults, so `field` is NOT
needed — import only `dataclass`.)

**IMPORTANT — critical-redirect conjunct order:** Use the EXACT original ordering
`if inp.critical and st.intent in ("explore_direction", "go_to_known_place") and inp.has_potions:`
(do NOT reorder, despite the readability note in §3). Zero-risk transcription.

---

## 4. Wave 0 — Agent 11: write the golden net FIRST (against UNMODIFIED code)

Create `tests/test_wk112_direct_prompt_validator.py` EXACTLY as below. The
`_GOLDEN_JSON` blob is the byte-exact output PM captured from current HEAD — copy
it VERBATIM. After writing, run it on the UNMODIFIED `direct_prompt_validator.py`
and confirm **all cases GREEN** (this proves the golden + the matrix builders are
correct before any refactor). DO NOT COMMIT.

```python
"""WK112 — differential golden characterization of validate_direct_prompt_output.

Pins the EXACT output dict for a 38-case matrix covering every branch of the
validator (raw-fallback, deferred-combat, allow-list gating, critical-HP redirect,
all 8 intents + their sub-branches, output-tail post-processing). The golden was
captured from the pre-WK112 HEAD code and is embedded as a JSON literal (NOT read
from git — so it stays valid after the refactor commits; cf. the "no git show HEAD
in parity tests" rule). The WK112 per-intent handler-table decomposition must
reproduce every dict byte-for-byte.
"""
from __future__ import annotations

import inspect
import json

import pytest

from ai import direct_prompt_validator as dpv
from ai.direct_prompt_validator import validate_direct_prompt_output


def _ctx(**overrides):
    base = {
        "hero": {
            "name": "Aldric", "class": "warrior", "level": 2, "hp": 80,
            "max_hp": 100, "health_percent": 80, "gold": 50,
        },
        "inventory": {"potions": 2},
        "situation": {
            "in_combat": False, "low_health": False, "critical_health": False,
            "has_potions": True, "can_shop": False, "near_safety": True,
        },
        "current_location": "outdoors",
        "distances": {"castle": 3.0, "marketplace": 12.0},
        "known_places_llm": [
            {"place_id": "castle:main", "place_type": "castle", "display_name": "Castle"},
            {"place_id": "inn:1", "place_type": "inn", "display_name": "The Inn"},
            {"place_id": "market:1", "place_type": "marketplace", "display_name": "Market"},
        ],
        "shop_items": [],
    }
    base.update(overrides)
    return base


def _sit(**kw):
    s = {
        "in_combat": False, "low_health": False, "critical_health": False,
        "has_potions": True, "can_shop": False, "near_safety": True,
    }
    s.update(kw)
    return s


def _guild_ctx():
    c = _ctx()
    c["hero_home_place_id"] = "ranger_guild:10:12"
    c["hero"] = {**c["hero"], "class": "ranger", "home_building_type": "ranger_guild"}
    c["known_places_llm"] = [
        {"place_id": "castle:main", "place_type": "castle", "display_name": "Castle"},
        {"place_id": "ranger_guild:10:12", "place_type": "ranger_guild", "display_name": "Ranger Guild"},
    ]
    return c


def _synthetic_guild_ctx():
    c = _ctx()
    c["hero_home_place_id"] = "ranger_guild:5:3"
    c["hero"] = {**c["hero"], "class": "ranger", "home_building_type": "ranger_guild"}
    c["known_places_llm"] = [
        {"place_id": "ranger_guild:5:3", "place_type": "ranger_guild", "display_name": "Ranger Guild"},
    ]
    return c


def _no_home_ctx(near_safety=True, can_shop=False):
    c = _ctx(situation=_sit(near_safety=near_safety, can_shop=can_shop))
    c["known_places_llm"] = []
    return c


def _critical_goto_no_home_ctx():
    c = _ctx()
    c["situation"] = _sit(low_health=True, critical_health=True, has_potions=False, near_safety=False)
    c["known_places_llm"] = []
    return c


# (case_id, raw, ctx, player_message) — MUST match the §4 golden keys exactly.
CASES = [
    ("raw_not_dict", "just a string", _ctx(), ""),
    ("deferred_attack_lair", {"spoken_response": "I'll charge!", "interpreted_intent": "attack_known_lair", "tool_action": "fight"}, _ctx(), ""),
    ("deferred_attack_prefix", {"interpreted_intent": "attack_goblin_camp", "tool_action": "fight"}, _ctx(), ""),
    ("status_report", {"spoken_response": "All well.", "interpreted_intent": "status_report"}, _ctx(), "how are you"),
    ("no_action_chat_only", {"spoken_response": "Hello.", "interpreted_intent": "no_action_chat_only"}, _ctx(), "hi"),
    ("return_home_castle_default", {"spoken_response": "Home.", "interpreted_intent": "return_home", "tool_action": "move_to"}, _ctx(), "go home"),
    ("return_home_guild", {"spoken_response": "To my hall.", "interpreted_intent": "return_home", "tool_action": "move_to"}, _guild_ctx(), "go home"),
    ("return_home_synthetic_guild_only", {"interpreted_intent": "return_home", "tool_action": "move_to"}, _synthetic_guild_ctx(), "head home"),
    ("return_home_no_home_near_safety_shop", {"interpreted_intent": "return_home", "tool_action": "move_to"}, _no_home_ctx(near_safety=True, can_shop=True), "go home"),
    ("return_home_no_home_not_safe", {"interpreted_intent": "return_home", "tool_action": "move_to"}, _no_home_ctx(near_safety=False, can_shop=False), "go home"),
    ("seek_healing_potion", {"interpreted_intent": "seek_healing"}, _ctx(situation=_sit(low_health=True, has_potions=True)), "heal up"),
    ("seek_healing_retreat_home", {"interpreted_intent": "seek_healing"}, _ctx(situation=_sit(low_health=True, has_potions=False)), "heal up"),
    ("seek_healing_no_home", {"interpreted_intent": "seek_healing"}, _no_home_ctx(near_safety=True, can_shop=False), "heal up"),
    ("go_to_known_place_found", {"interpreted_intent": "go_to_known_place", "tool_action": "move_to", "target_id": "inn:1", "target_description": "The Inn"}, _ctx(), "go to inn"),
    ("go_to_known_place_unknown", {"interpreted_intent": "go_to_known_place", "tool_action": "move_to", "target_id": "nowhere:xx", "target_description": "Moon"}, _ctx(), "go to moon"),
    ("buy_potions_shop_afford", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[{"name": "Health Potion", "type": "potion", "price": 20, "can_afford": True}]), "buy a potion"),
    ("buy_potions_shop_cant_afford_has_gold", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[{"name": "Health Potion", "price": 100, "can_afford": False}]), "buy a potion"),
    ("buy_potions_shop_cant_afford_no_gold", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), hero={**_ctx()["hero"], "gold": 0}, shop_items=[{"name": "Health Potion", "price": 100, "can_afford": False}]), "buy a potion"),
    ("buy_potions_shop_no_potion", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[{"name": "Short Sword", "price": 10, "can_afford": True}]), "buy a potion"),
    ("buy_potions_catalog_fallback", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=True), shop_items=[], market_catalog_items=[{"name": "Health Potion", "price": 20, "can_afford": True}]), "buy a potion"),
    ("buy_potions_no_shop_market_known", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _ctx(situation=_sit(can_shop=False)), "buy a potion"),
    ("buy_potions_no_shop_no_market", {"interpreted_intent": "buy_potions", "tool_action": "buy_item"}, _no_home_ctx(near_safety=True, can_shop=False), "buy a potion"),
    ("explore_compass_in_message", {"interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(), "explore east please"),
    ("explore_no_compass", {"interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(), "explore the frontier"),
    ("explore_compass_in_target_desc", {"interpreted_intent": "explore_direction", "tool_action": "explore", "target_description": "north"}, _ctx(), "scout"),
    ("rest_indoors", {"interpreted_intent": "rest_until_healed"}, _ctx(current_location="inn"), "rest"),
    ("rest_outdoors_home", {"interpreted_intent": "rest_until_healed"}, _ctx(current_location="outdoors"), "rest"),
    ("rest_outdoors_no_home", {"interpreted_intent": "rest_until_healed"}, _no_home_ctx(), "rest"),
    ("critical_explore_has_potion", {"spoken_response": "I scout east!", "interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(situation=_sit(low_health=True, critical_health=True, has_potions=True, near_safety=False)), "explore east"),
    ("critical_explore_no_potion_home", {"interpreted_intent": "explore_direction", "tool_action": "explore"}, _ctx(situation=_sit(low_health=True, critical_health=True, has_potions=False, near_safety=False)), "explore east"),
    ("critical_goto_no_potion_no_home", {"interpreted_intent": "go_to_known_place", "tool_action": "move_to", "target_id": "inn:1"}, _critical_goto_no_home_ctx(), "go to inn"),
    ("unsupported_intent", {"interpreted_intent": "frobnicate", "tool_action": "move_to"}, _ctx(), "do a thing"),
    ("fight_tool_noncombat_intent", {"interpreted_intent": "return_home", "tool_action": "fight"}, _ctx(), "go home"),
    ("unknown_tool_value", {"interpreted_intent": "return_home", "tool_action": "teleport"}, _ctx(), "go home"),
    ("invalid_obey_defy", {"interpreted_intent": "status_report", "obey_defy": "Maybe"}, _ctx(), "status"),
    ("confidence_clamp_high", {"interpreted_intent": "status_report", "confidence": 5.0}, _ctx(), "status"),
    ("confidence_nonnumeric", {"interpreted_intent": "status_report", "confidence": "abc"}, _ctx(), "status"),
    ("physical_clears_refusal_forces_obey", {"spoken_response": "Nay", "interpreted_intent": "return_home", "tool_action": "move_to", "obey_defy": "Defy", "refusal_reason": "should_not_appear"}, _ctx(), "go home"),
]

# Byte-exact golden captured from pre-WK112 HEAD (PM capture 2026-05-31).
_GOLDEN_JSON = r"""
<<<PASTE THE EXACT 38-CASE JSON FROM §4-GOLDEN HERE>>>
"""

GOLDEN = json.loads(_GOLDEN_JSON)


@pytest.mark.parametrize("case_id", [c[0] for c in CASES])
def test_validator_output_matches_golden(case_id):
    raw, ctx, msg = next((r, c, m) for cid, r, c, m in CASES if cid == case_id)
    got = validate_direct_prompt_output(raw, ctx, msg)
    assert got == GOLDEN[case_id], (
        f"WK112 behavior drift for case '{case_id}':\n got={got}\n exp={GOLDEN[case_id]}"
    )


def test_every_case_has_golden_and_vice_versa():
    case_ids = {c[0] for c in CASES}
    assert case_ids == set(GOLDEN), (
        f"CASES/GOLDEN key mismatch: only-in-cases={case_ids - set(GOLDEN)} "
        f"only-in-golden={set(GOLDEN) - case_ids}"
    )
    assert len(CASES) == 38


def test_public_signature_unchanged():
    sig = inspect.signature(validate_direct_prompt_output)
    assert list(sig.parameters) == ["raw", "hero_context", "player_message"]
    assert sig.parameters["player_message"].default == ""


def test_intent_handler_table_covers_all_supported_intents():
    """Structural pin: after the decomposition the dispatch table must exist and
    cover every supported intent + the two tool-clearing chat intents."""
    table = dpv._INTENT_HANDLERS
    for intent in dpv.SUPPORTED_DIRECT_INTENTS:
        assert intent in table, f"intent '{intent}' missing a handler in _INTENT_HANDLERS"
    # The 8 keys are exactly the former if/elif branches.
    assert set(table) == {
        "status_report", "no_action_chat_only", "return_home", "seek_healing",
        "go_to_known_place", "buy_potions", "explore_direction", "rest_until_healed",
    }
    for fn in table.values():
        assert callable(fn)
```

**`test_intent_handler_table_covers_all_supported_intents` is the one pin that
FAILS on unmodified code** (no `_INTENT_HANDLERS` yet). In Wave 0, mark it
`@pytest.mark.xfail(reason="WK112: _INTENT_HANDLERS lands in Wave 1", strict=True)`
so the net is GREEN on HEAD; Agent 06 REMOVES the xfail in Wave 1 (it must XPASS,
then pass). All OTHER tests MUST be GREEN on unmodified HEAD.

### §4-GOLDEN — paste this exact JSON into `_GOLDEN_JSON`

```json
{
  "raw_not_dict": {"spoken_response": "I could not make sense of that, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "deferred_attack_lair": {"spoken_response": "I'll charge!", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "mvp_combat_deferred", "safety_assessment": "deferred", "confidence": 0.0},
  "deferred_attack_prefix": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "mvp_combat_deferred", "safety_assessment": "deferred", "confidence": 0.0},
  "status_report": {"spoken_response": "All well.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "no_action_chat_only": {"spoken_response": "Hello.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "return_home_castle_default": {"spoken_response": "Home.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_guild": {"spoken_response": "To my hall.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "ranger_guild", "target_kind": "known_place", "target_id": "ranger_guild:10:12", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_synthetic_guild_only": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "ranger_guild", "target_kind": "known_place", "target_id": "ranger_guild:5:3", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_no_home_near_safety_shop": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "return_home_no_home_not_safe": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_known_home", "safety_assessment": "impossible", "confidence": 0.0},
  "seek_healing_potion": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": "use_potion", "action": "use_potion", "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "seek_healing_retreat_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": "retreat", "action": "retreat", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "seek_healing_no_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_safe_haven_known", "safety_assessment": "impossible", "confidence": 0.0},
  "go_to_known_place_found": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "go_to_known_place", "tool_action": "move_to", "action": "move_to", "target": "inn", "target_kind": "known_place", "target_id": "inn:1", "target_description": "The Inn", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "go_to_known_place_unknown": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "Moon", "obey_defy": "Defy", "refusal_reason": "unknown_place", "safety_assessment": "unknown_target", "confidence": 0.0},
  "buy_potions_shop_afford": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "buy_potions", "tool_action": "buy_item", "action": "buy_item", "target": "Health Potion", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "buy_potions_shop_cant_afford_has_gold": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "insufficient_gold", "safety_assessment": "impossible", "confidence": 0.0},
  "buy_potions_shop_cant_afford_no_gold": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_gold", "safety_assessment": "impossible", "confidence": 0.0},
  "buy_potions_shop_no_potion": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_potions_here", "safety_assessment": "impossible", "confidence": 0.0},
  "buy_potions_catalog_fallback": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "buy_potions", "tool_action": "buy_item", "action": "buy_item", "target": "Health Potion", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "buy_potions_no_shop_market_known": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "buy_potions", "tool_action": "move_to", "action": "move_to", "target": "marketplace", "target_kind": "known_place", "target_id": "market:1", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "buy_potions_no_shop_no_market": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_market_known", "safety_assessment": "impossible", "confidence": 0.0},
  "explore_compass_in_message": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "explore_direction", "tool_action": "explore", "action": "explore", "target": "", "target_kind": "direction", "target_id": "", "target_description": "east", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "explore_no_compass": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "unknown_heading", "safety_assessment": "unknown_target", "confidence": 0.0},
  "explore_compass_in_target_desc": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "explore_direction", "tool_action": "explore", "action": "explore", "target": "", "target_kind": "direction", "target_id": "", "target_description": "north", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "rest_indoors": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "rest_until_healed", "tool_action": "leave_building", "action": "leave_building", "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "rest_outdoors_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "rest_until_healed", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "rest_outdoors_no_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "rest_until_healed", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_known_rest_place", "safety_assessment": "impossible", "confidence": 0.0},
  "critical_explore_has_potion": {"spoken_response": "I scout east!", "interpreted_intent": "seek_healing", "tool_action": "use_potion", "action": "use_potion", "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "critical_redirect", "confidence": 0.0},
  "critical_explore_no_potion_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": "retreat", "action": "retreat", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "Castle", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "critical_redirect", "confidence": 0.0},
  "critical_goto_no_potion_no_home": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "seek_healing", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Defy", "refusal_reason": "no_safe_haven_known", "safety_assessment": "impossible", "confidence": 0.0},
  "unsupported_intent": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "no_action_chat_only", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "fight_tool_noncombat_intent": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "unknown_tool_value": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0},
  "invalid_obey_defy": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "confidence_clamp_high": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 1.0},
  "confidence_nonnumeric": {"spoken_response": "Aye, Sovereign.", "interpreted_intent": "status_report", "tool_action": null, "action": null, "target": "", "target_kind": "", "target_id": "", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "unknown", "confidence": 0.0},
  "physical_clears_refusal_forces_obey": {"spoken_response": "Nay", "interpreted_intent": "return_home", "tool_action": "move_to", "action": "move_to", "target": "castle", "target_kind": "known_place", "target_id": "castle:main", "target_description": "", "obey_defy": "Obey", "refusal_reason": "", "safety_assessment": "safe", "confidence": 0.0}
}
```

---

## 5. Wave 1 — Agent 06: implement the decomposition

1. Onboard as Agent 06 via `.cursor/rules/agent-06-*.mdc`; read this plan + your PM log entry.
2. Edit ONLY `ai/direct_prompt_validator.py` per §3. Lift each branch VERBATIM.
   Keep all 7 helpers + the constants block + all imports unchanged (add
   `dataclass`, `Callable`). Use the EXACT original critical-redirect conjunct order.
3. Remove the `@pytest.mark.xfail` from `test_intent_handler_table_covers_all_supported_intents`.
4. Self-verify (all from repo root):
   - `python -m pytest tests/test_wk112_direct_prompt_validator.py -q` → ALL green (40 tests).
   - `python -m pytest tests/test_wk50_phase2b_direct_prompt_contracts.py tests/test_direct_prompt_integration.py tests/test_wk65_ai_characterization.py tests/test_wk110_ai_vocab.py -q` → all green (53).
   - `python -c "import ai.direct_prompt_validator"` → no error.
   - `python -c "from ai.llm_brain import LLMBrain; from ai.providers.mock.direct_prompt import *"` → no error (consumers import-clean).
   - Confirm NO `self`-style leftovers and NO behavior edits: the only NEW names
     are `_ValidationInputs`, `_ResolveState`, `_apply_critical_health_redirect`,
     the 7 `_handle_*`, `_INTENT_HANDLERS`.
5. **DO NOT COMMIT.** Update your Agent 06 log with what changed + verification output, then report to PM.

---

## 6. Wave 2 — Agent 11: full DoD verification

Run from repo root and paste raw output into your log:
1. `python -m pytest -q` → **0 failed** (record passed/skipped counts).
2. `python tools/determinism_guard.py` → clean PASS.
3. `python -m pytest tests/test_wk67_ai_boundary.py::test_ai_decision_digest_is_stable -q`
   → GREEN (digest still `b73961340c…d148ded`). Also run
   `tests/test_wk67_ai_boundary.py::test_chat_path_consumes_pure_ai_view` and
   `::test_engine_chat_caller_uses_build_ai_view_not_get_game_state` → GREEN
   (chat-path purity pins — most relevant to this file).
4. `python tools/qa_smoke.py --quick` → `DONE: PASS`.
5. `python -m pytest tests/test_wk112_direct_prompt_validator.py -q` → 40 green, 0 xfail/xpass.
6. Confirm `ai/direct_prompt_validator.py` line count dropped only modestly (the
   logic moved, not deleted) and the main function is now ~prelude+dispatch+tail.
7. **DO NOT COMMIT.** Report PASS/FAIL table to PM.

---

## 7. Definition of done (PM gate before commit)

- [ ] `tests/test_wk112_direct_prompt_validator.py` exists, 40 tests, all GREEN, no xfail left.
- [ ] Full `pytest -q`: 0 failed (≈1366 passed, 4 skipped — record actual).
- [ ] `determinism_guard.py` clean.
- [ ] WK67 digest byte-identical (`b73961340c…d148ded`); chat-purity pins green.
- [ ] `qa_smoke.py --quick` = DONE: PASS.
- [ ] Public signature unchanged; both consumer modules import clean.
- [ ] **PM cross-check:** re-run `python _pm_wk112_capture.py` (regenerates
      `_pm_wk112_golden.json` from the REFACTORED code) and
      `diff`/compare against the frozen `_pm_wk112_golden_HEAD.json` → IDENTICAL.
      (PM-only; throwaway files never committed.)
- [ ] Agent 06 + Agent 11 logs updated. Then PM commits (scoped add of
      `ai/direct_prompt_validator.py` + `tests/test_wk112_direct_prompt_validator.py`
      + the two plan/PM-hub files) and pushes.

---

## 8. Grounding for the NEXT sprint (WK113 candidate)

**HELD: WK34 zombie-type purge** (was WK111) — the 8 `purge_candidate=True`
building types at `game/content/buildings.py:135-148` (gnome_hovel, elven_bungalow,
dwarven_settlement, ballista_tower, wizard_tower, fairgrounds, library,
royal_gardens). **DO NOT execute without an explicit keep/purge ruling from the
Sovereign** — several read as unfinished *features*, not slop; PM flagged this and
the user has not yet ratified deletion. This is a product decision, not a
code-quality one, so it stays parked behind the behavior-preserving refactors.

Next behavior-preserving headless candidates (any is a clean WK113):
- `world.py:60` `_currently_visible: list` → `set` (prove determinism-neutral via
  the WK67 fog-revision sequence pin + determinism_guard).
- De-slop dead `WATCH_MINIMAP_SIZE` (`game/ui/hud.py:57`) if still unreferenced.
- `game/graphics/ursina_app.py` hot-path further extraction (render slice;
  deferred-screenshot model).

Deferred / RISKIEST (land last, digest-fragile, reorder live flow): TaskRouter
(`ai/basic_ai.py update_hero` → `ai/task_router.py`, roadmap Move 12); Move 9
SystemRunner (sim_engine update ordering).
