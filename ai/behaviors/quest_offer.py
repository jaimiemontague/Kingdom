"""WK126 T5+T6 — quest-giver approach + LLM accept/decline behavior.

T5 (:func:`maybe_approach_quest_giver`): an otherwise-idle hero OCCASIONALLY
walks up to an open quest-giver NPC. Modeled on
``bounty_pursuit.maybe_take_bounty`` but with the WK126 digest-critical guard
ordering (plan section "CENTRAL CONSTRAINT", rule 1):

    (a) ``if not view.quest_givers: return False``  — FIRST, before ANYTHING
        (no RNG, no state change). The WK67 digest scenario has zero givers, so
        the whole behavior is structurally unreachable there.
    (b) health gate (``QUEST_MIN_ACCEPT_HEALTH_PCT``).
    (c) not already committed (state/target preemptible, no pending offer or
        LLM decision, quest-offer commit + approach cooldown elapsed).
    (d) candidate list: open givers, NOT on this hero's 15-min decline
        cooldown, within range.
    (e) ``if not candidates: return False``  — still no RNG draw.
    (f) the "occasionally" probability roll from ``ai._ai_rng`` is the LAST
        gate — the ONLY RNG draw, and it happens only when a real candidate
        exists. Consuming the seeded stream earlier would shift every
        downstream draw and break the WK67 digest even with no hero moving.

T6 (:func:`begin_quest_offer_decision` / :func:`maybe_apply_quest_offer_decision`):
on arrival the hero asks the LLM whether to take the quest (async, via the
existing WK50 autonomous pipeline — a new ``QUEST_OFFER`` decision moment in
``ai.decision_moments``). accept → ``quest.accept(hero)`` + objective target per
quest type + ``QUEST_STARTED``; decline → 15-sim-min per-giver cooldown
(``hero._quest_decline_until_ms[giver_id] = now + QUEST_DECLINE_COOLDOWN_MS``)
+ ``QUEST_DECLINED``.

ACTION-CARRIER NOTE (decision of record, documented per plan T6 "pick one and
document it"): the semantic verbs ``accept_quest`` / ``decline_quest`` CANNOT
transit ``ai.llm_brain._parse_response`` (it hard-rejects any action outside
the seven ``ai.vocab.ToolAction`` strings) nor
``ai.decision_output_validator.validate_autonomous_decision`` (which also
forces ``obey_defy`` back to "Obey", killing the plan's alternative carrier).
Both modules are OUTSIDE Agent 06's WK133 lane. The QUEST_OFFER moment
therefore uses two existing tool-action verbs as carriers —
``QUEST_OFFER_ACCEPT_ACTION = "explore"`` (set out on the quest) and
``QUEST_OFFER_DECLINE_ACTION = "retreat"`` (beg off and withdraw) — declared in
``ai.decision_moments`` and explained to the model in the prompt's
``quest_offer.decision_rule`` block. This keeps the model's REAL decision alive
end-to-end (a rejected/unparseable response falls back deterministically to
accept — the same documented choice as the ``llm_brain=None`` path).

LIVE-OBJECT ACCESS NOTE: the accept path must call
``quest_system.open_quest_for(giver_id)`` / ``quest.accept(hero)`` and emit
events, but the read-only ``AiGameView`` deliberately carries only plain-data
quest tuples. The ONLY sim handle on the view is the sim-owned
``view.commands`` (``SimCommandSink``); :func:`_live_sim_from_view` reaches the
engine through it (a scoped T6 exception, mirroring how the sink itself wraps
the sim for the Move-6 purchase writes). Heroes on the view are live by
contract, so ``quest.accept(hero)`` mutates nothing the boundary forbids.
Agent 03's Wave-3 boundary review may formalize this as a QuestAcceptCommand.

Determinism: time only via ``sim_now_ms``; the ONLY RNG is the single
``ai._ai_rng`` approach roll (f) — never reached without a live candidate.
"""

from __future__ import annotations

from typing import Any

from config import (
    QUEST_APPROACH_CHANCE,
    QUEST_APPROACH_COOLDOWN_MS,
    QUEST_DECLINE_COOLDOWN_MS,
    QUEST_MIN_ACCEPT_HEALTH_PCT,
    QUEST_OFFER_COMMIT_MS,
    RANGER_REROAM_COMMIT_MS,
    TILE_SIZE,
)
from game.entities.hero import HeroState
from game.events import GameEventType
from game.sim.timebase import now_ms as sim_now_ms
from game.systems.navigation import best_adjacent_tile

from ai.behaviors.view_compat import as_ai_view
from ai.decision_moments import (
    QUEST_OFFER_ACCEPT_ACTION,
    QUEST_OFFER_DECLINE_ACTION,
)

# How far a hero will consider walking to a quest-giver (plan: "a sane range").
QUEST_APPROACH_MAX_RANGE_TILES = 30

# How long an unanswered pending offer survives before it silently expires
# (the giver stays open; the approach cooldown stops instant re-pathing).
QUEST_OFFER_DECISION_TTL_MS = 30_000

# Wander target types the quest approach may preempt. Deliberately ONLY the
# terminal patrol wander — never bounty/shopping/defense/meal/POI commitments,
# and not the ranger "explore_frontier" commitment either (it carries its own
# commit-window semantics from WK6/WK124).
_PREEMPTIBLE_TARGET_TYPES = frozenset({"patrol"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hero_is_preemptible(hero: Any) -> bool:
    """Guard (c) body: True only for an otherwise-idle, uncommitted hero."""
    if getattr(hero, "is_inside_building", False):
        return False
    if getattr(hero, "pending_llm_decision", False):
        return False
    if getattr(hero, "_pending_quest_offer", None):
        return False
    state = getattr(hero, "state", None)
    if state == HeroState.IDLE:
        return True
    if state == HeroState.MOVING:
        target = getattr(hero, "target", None)
        if target is None:
            return True
        return isinstance(target, dict) and target.get("type") in _PREEMPTIBLE_TARGET_TYPES
    return False


def _live_sim_from_view(view: Any) -> Any:
    """The live SimEngine via the sim-owned CommandSink (see module docstring)."""
    sink = getattr(view, "commands", None)
    return getattr(sink, "_sim", None)


def _emit(sim: Any, payload: dict) -> None:
    bus = getattr(sim, "event_bus", None) if sim is not None else None
    if bus is not None:
        bus.emit(payload)


def _clear_pending_offer(hero: Any) -> None:
    hero._pending_quest_offer = None
    hero._quest_offer_commit_until_ms = 0


# ---------------------------------------------------------------------------
# T5 — occasional approach (digest-critical guard ordering)
# ---------------------------------------------------------------------------

def maybe_approach_quest_giver(ai: Any, hero: Any, view: Any) -> bool:
    """Occasionally commit an idle hero to walk to an open quest-giver.

    Returns True iff the hero committed to a ``quest_offer`` target. GUARD
    ORDER IS LOAD-BEARING (WK67 digest) — see the module docstring.
    """
    view = as_ai_view(view)

    # (a) FIRST — digest guard #1: complete no-op when there are no givers.
    # No RNG, no sim-time read, no hero mutation may happen above this line.
    quest_givers = getattr(view, "quest_givers", ()) or ()
    if not quest_givers:
        return False

    # (b) Health gate — don't go quest-shopping while hurt (matches bounty).
    if float(getattr(hero, "health_percent", 0.0) or 0.0) < float(QUEST_MIN_ACCEPT_HEALTH_PCT):
        return False

    # (c) Not already committed + cooldowns elapsed.
    if not _hero_is_preemptible(hero):
        return False
    now = int(sim_now_ms())
    if now < int(getattr(hero, "_quest_offer_commit_until_ms", 0) or 0):
        return False
    if now < int(getattr(hero, "_quest_approach_cooldown_until_ms", 0) or 0):
        return False

    # (d) Candidate list: open givers, not on this hero's 15-min decline
    # cooldown, within a sane range. Pure reads only.
    decline_map = getattr(hero, "_quest_decline_until_ms", None) or {}
    max_range_px = float(TILE_SIZE) * float(QUEST_APPROACH_MAX_RANGE_TILES)
    candidates: list[tuple[float, str, Any]] = []
    for giver in quest_givers:
        if not getattr(giver, "is_open", False):
            continue
        gid = str(getattr(giver, "giver_id", "") or "")
        if now < int(decline_map.get(gid, 0) or 0):
            continue  # the 15-min "don't come back" skip
        dist = float(hero.distance_to(float(giver.x), float(giver.y)))
        if dist > max_range_px:
            continue
        candidates.append((dist, gid, giver))

    # (e) Still no RNG draw when nothing is eligible.
    if not candidates:
        return False

    # (f) "Occasionally" gate — LAST, the ONLY ai._ai_rng draw in this
    # behavior, reached only when a real candidate exists (digest rule 1).
    # A failed roll arms the approach cooldown so the hero re-rolls at most
    # once per QUEST_APPROACH_COOLDOWN_MS instead of every tick.
    if ai._ai_rng.random() >= float(QUEST_APPROACH_CHANCE):
        hero._quest_approach_cooldown_until_ms = now + int(QUEST_APPROACH_COOLDOWN_MS)
        return False

    # Commit: nearest candidate (deterministic tie-break on giver_id).
    candidates.sort(key=lambda c: (c[0], c[1]))
    _, gid, giver = candidates[0]
    hero.set_target_position(float(giver.x), float(giver.y))
    hero.target = {"type": "quest_offer", "giver_id": gid, "started_ms": now}
    hero.state = HeroState.MOVING
    hero._quest_offer_commit_until_ms = now + int(QUEST_OFFER_COMMIT_MS)
    hero._quest_approach_cooldown_until_ms = now + int(QUEST_APPROACH_COOLDOWN_MS)
    ai._debug_log(f"{hero.name} -> walking to quest-giver {gid}")
    return True


# ---------------------------------------------------------------------------
# T6 — arrival: stage the offer + kick off the async LLM decision
# ---------------------------------------------------------------------------

def begin_quest_offer_decision(ai: Any, hero: Any, giver_id: str, view: Any) -> None:
    """Called by the ``quest_offer`` arrival handler when the hero reaches the NPC.

    Stages the offer details on the hero (``hero._pending_quest_offer``) and
    requests the async LLM decision via the existing WK50 autonomous pipeline
    (the QUEST_OFFER decision moment). With ``llm_brain=None`` the verdict is an
    immediate DETERMINISTIC ACCEPT (decision of record — keeps the headless /
    no-LLM game functional and assertable without a network call).
    """
    view = as_ai_view(view)
    gid = str(giver_id or "")
    now = int(sim_now_ms())

    # The giver must still exist and still be open (and not have been declined
    # by this hero in the meantime — e.g. a stale walk that outlived a decline).
    giver = None
    for g in getattr(view, "quest_givers", ()) or ():
        if str(getattr(g, "giver_id", "") or "") == gid:
            giver = g
            break
    decline_map = getattr(hero, "_quest_decline_until_ms", None) or {}
    if giver is None or not getattr(giver, "is_open", False) or now < int(decline_map.get(gid, 0) or 0):
        _clear_pending_offer(hero)
        return

    # The open offer's plain-data summary (from the boundary tuple, not live).
    offer_info = None
    for q in getattr(view, "quests", ()) or ():
        if getattr(q, "is_open", False) and str(getattr(q, "giver_id", "") or "") == gid:
            offer_info = q
            break

    hero._pending_quest_offer = {
        "giver_id": gid,
        "quest_id": int(getattr(offer_info, "quest_id", 0) or 0),
        "quest_type": str(getattr(offer_info, "quest_type", "") or ""),
        "target": str(getattr(offer_info, "target", "") or ""),
        "reward": int(getattr(offer_info, "reward", 0) or 0),
        "count": int(getattr(offer_info, "count", 1) or 1),
        "x": float(getattr(offer_info, "x", 0.0) or 0.0),
        "y": float(getattr(offer_info, "y", 0.0) or 0.0),
        "staged_ms": now,
        "expires_ms": now + QUEST_OFFER_DECISION_TTL_MS,
    }

    if ai.llm_brain:
        # Drop any stale in-flight decision so it cannot be misread as the
        # quest verdict, then request the QUEST_OFFER consult (the moment
        # resolver sees the staged offer and selects QUEST_OFFER).
        ai.llm_brain.get_decision(hero.name)
        ai.llm_bridge_behavior.request_llm_decision(ai, hero, view)
        return

    # llm_brain=None: deterministic ACCEPT, synchronously (documented choice).
    decision = {
        "action": QUEST_OFFER_ACCEPT_ACTION,
        "target": "",
        "reasoning": "No LLM wired; deterministic fallback accepts the quest",
    }
    maybe_apply_quest_offer_decision(ai, hero, decision, view, source="fallback")


# ---------------------------------------------------------------------------
# T6 — resolve the LLM verdict (called from llm_bridge.apply_llm_decision)
# ---------------------------------------------------------------------------

def maybe_apply_quest_offer_decision(
    ai: Any,
    hero: Any,
    decision: dict,
    view: Any,
    *,
    source: str = "llm",
) -> bool:
    """Consume an arriving LLM decision as the quest accept/decline verdict.

    Returns True iff the decision was consumed by the pending quest offer (the
    caller then returns without generic action dispatch). Mapping:

      * ``QUEST_OFFER_DECLINE_ACTION`` ("retreat") or a literal
        ``decline_quest`` → DECLINE (15-sim-min per-giver cooldown).
      * anything else (incl. the ``QUEST_OFFER_ACCEPT_ACTION`` carrier and any
        fallback-munged action) → ACCEPT — the documented deterministic-accept
        bias on ambiguity, consistent with the ``llm_brain=None`` choice.
    """
    offer = getattr(hero, "_pending_quest_offer", None)
    if not isinstance(offer, dict):
        return False
    # A hero pulled into combat resolves the fight first; the staged offer
    # waits (and expires) rather than consuming a combat decision.
    if getattr(hero, "state", None) == HeroState.FIGHTING:
        return False
    now = int(sim_now_ms())
    if now >= int(offer.get("expires_ms", 0) or 0):
        _clear_pending_offer(hero)
        return False

    view = as_ai_view(view)
    gid = str(offer.get("giver_id", "") or "")
    action = str(decision.get("action", "") or "").strip().lower()
    reason = str(decision.get("reasoning", "") or "")

    if action in (QUEST_OFFER_DECLINE_ACTION, "decline_quest"):
        _decline(ai, hero, gid, view, source=source, reason=reason)
    else:
        _accept(ai, hero, gid, view, source=source, reason=reason)
    return True


def _decline(ai: Any, hero: Any, giver_id: str, view: Any, *, source: str, reason: str) -> None:
    now = int(sim_now_ms())
    until = now + int(QUEST_DECLINE_COOLDOWN_MS)
    decline_map = getattr(hero, "_quest_decline_until_ms", None)
    if decline_map is None:
        decline_map = {}
        hero._quest_decline_until_ms = decline_map
    decline_map[str(giver_id)] = until
    _clear_pending_offer(hero)

    sim = _live_sim_from_view(view)
    _emit(
        sim,
        {
            "type": GameEventType.QUEST_DECLINED.value,
            "giver_id": str(giver_id),
            "hero": str(getattr(hero, "name", "") or ""),
            "hero_id": str(getattr(hero, "hero_id", "") or ""),
            "until_ms": until,
        },
    )
    ai.record_decision(
        hero,
        action="decline_quest",
        reason=reason or "Declined the quest offer",
        intent=getattr(hero, "intent", "idle") or "idle",
        source=source,
    )
    ai._debug_log(f"{hero.name} -> declined quest at {giver_id} (15 sim-min cooldown)")


def _accept(ai: Any, hero: Any, giver_id: str, view: Any, *, source: str, reason: str) -> None:
    _clear_pending_offer(hero)

    sim = _live_sim_from_view(view)
    quest_system = getattr(sim, "quest_system", None) if sim is not None else None
    quest = quest_system.open_quest_for(giver_id) if quest_system is not None else None
    if quest is None or not quest.accept(hero):
        # Offer vanished between staging and the verdict (taken/expired) or the
        # live sim is unreachable: no acceptance, no decline cooldown — the
        # approach cooldown alone stops instant re-pathing.
        ai._debug_log(f"{hero.name} -> quest at {giver_id} no longer available")
        return

    _set_objective_for_quest(ai, hero, quest, view)
    _emit(
        sim,
        {
            "type": GameEventType.QUEST_STARTED.value,
            "quest_id": int(quest.quest_id),
            "quest_type": str(quest.quest_type),
            "giver_id": str(quest.giver_id),
            "reward": int(quest.reward),
            "hero": str(getattr(hero, "name", "") or ""),
            "hero_id": str(getattr(hero, "hero_id", "") or ""),
        },
    )
    ai.record_decision(
        hero,
        action="accept_quest",
        reason=reason or f"Accepted a {quest.quest_type} quest ({quest.reward}g)",
        intent=getattr(hero, "intent", "idle") or "idle",
        inputs_summary={"quest_id": int(quest.quest_id), "quest_type": str(quest.quest_type)},
        source=source,
    )
    ai._debug_log(f"{hero.name} -> accepted {quest.quest_type} quest #{quest.quest_id}")


def _set_objective_for_quest(ai: Any, hero: Any, quest: Any, view: Any) -> None:
    """Point the hero at the quest objective per type (plan T6 mapping)."""
    now = int(sim_now_ms())
    qtype = str(getattr(quest, "quest_type", "") or "")

    if qtype == "raid_lair":
        lair = quest.target
        hero.target = lair  # live-entity target: the MOVING/FIGHTING path raids it
        world = getattr(view, "world", None)
        buildings = getattr(view, "buildings", ()) or ()
        adj = best_adjacent_tile(world, list(buildings), lair, hero.x, hero.y) if world else None
        if adj:
            hero.set_target_position(
                adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2
            )
        else:
            hero.set_target_position(
                float(getattr(lair, "center_x", hero.x)), float(getattr(lair, "center_y", hero.y))
            )
        hero.state = HeroState.MOVING
        return

    if qtype == "find_poi":
        gx, gy = quest.get_goal_position()
        hero.set_target_position(float(gx), float(gy))
        hero.target = {"type": "visit_poi", "poi": quest.target}
        hero.state = HeroState.MOVING
        return

    if qtype == "explore_far":
        gx, gy = quest.get_goal_position()
        hero.set_target_position(float(gx), float(gy))
        hero.target = {"type": "explore_frontier"}
        # Long commit so the hero actually travels there (WK124 re-roam const).
        hero._frontier_commit_until_ms = now + int(RANGER_REROAM_COMMIT_MS)
        hero.state = HeroState.MOVING
        return

    # slay_enemy_type: no fixed objective — roam and hunt; kills are counted by
    # QuestSystem.on_enemy_killed. explore() sets a wander/frontier leg (its RNG
    # is fine here: this path never runs in the WK67 digest scenario).
    hero.state = HeroState.IDLE
    hero.target = None
    hero.target_position = None
    ai.exploration_behavior.explore(ai, hero, view)
