"""WK67 Round A-2 (Move 5): AiGameView -> legacy game_state-dict bridge.

The AI consumer path now receives a frozen :class:`game.sim.ai_view.AiGameView`
(a read-only ``WorldView`` + immutable facts, with NO ``economy``/``sim``/
``engine``). A handful of LLM-context builders and one ``game/sim`` direction
resolver still take the legacy ``game_state`` dict and read it via ``.get(...)``:

* ``ai.context_builder.ContextBuilder.build_hero_context`` (reads ``bounties``/
  ``buildings``/``enemies``/``heroes``/``micro_view_building`` and, via
  ``get_nearby_pois_for_hero``, ``world``/``pois``),
* ``ai.decision_moments.determine_decision_moment`` (reads ``enemies``/
  ``buildings``),
* ``ai.profile_context_adapter.build_llm_context_for_moment`` (delegates to the
  context builder),
* ``game.sim.direct_prompt_targets.resolve_explore_direction_target`` (reads
  ``world``).

Those modules are outside Agent 06's Move-5 lane (top-level ``ai/`` context
builders + ``game/sim``). Rather than change their signatures here, the AI
behaviors call this bridge at the boundary: it projects the typed view into the
exact dict shape those consumers expect — built fresh from the view, carrying
ONLY the fields they actually read.

Boundary contract preserved:

* It carries NO ``economy``/``sim``/``engine`` — those were the L3 leak and none
  of the consumers above read them.
* ``world`` is the read-only ``WorldView`` straight off the view (a drop-in for
  the live ``World`` for every read these consumers perform).
* ``pois`` is populated from the view, so ``get_nearby_pois_for_hero`` resolves
  POIs directly and never reaches the old live-``sim`` POI fallback.
* ``micro_view_building`` is ``None``: that is pure UI/presentation state the AI
  is no longer handed (the headless/AI path never had a player-viewed interior),
  so ``player_is_present`` evaluates exactly as it did on the AI path before.

This is a fresh dict literal built from the typed view, not a read off the live
UI game-state mapping — the Move-5 DoD grep (no live world/sim/engine reads off
the AI game-state dict in ``ai/``) stays satisfied.
"""

from __future__ import annotations

from typing import Any


class _DictGameStateView:
    """Read-only view adapter over a legacy ``game_state`` dict.

    WK67 Move 5: the AI consumer path receives an :class:`AiGameView`. One
    production caller outside the AI lane still drives the AI through the legacy
    UI dict — the direct-prompt chat path
    (``game.sim.direct_prompt_exec.apply_validated_direct_prompt_physical`` fed by
    ``game.engine`` with ``get_game_state()``) calls
    :func:`ai.behaviors.llm_bridge.apply_llm_decision` with that dict. Rather than
    edit ``game/sim/**`` (Agent 03's lane), ``apply_llm_decision`` normalizes its
    incoming ``view``-or-dict through :func:`as_ai_view`, which wraps a dict in
    this adapter so every migrated behavior downstream reads the same view
    surface. Behavior is preserved: the same entities/world the dict carried are
    exposed read-only under the view's attribute names.

    POIs match the legacy dict path exactly: prefer an explicit ``pois`` key,
    else fall back to ``sim.pois`` (the same two-source resolution the old
    ``poi_awareness`` helper used for the UI dict).
    """

    __slots__ = ("_gs",)

    def __init__(self, game_state: dict):
        self._gs = game_state

    @property
    def world(self):
        return self._gs.get("world")

    @property
    def buildings(self):
        return self._gs.get("buildings", []) or []

    @property
    def enemies(self):
        return self._gs.get("enemies", []) or []

    @property
    def heroes(self):
        return self._gs.get("heroes", []) or []

    @property
    def bounties(self):
        return self._gs.get("bounties", []) or []

    @property
    def pois(self):
        pois = self._gs.get("pois")
        if pois:
            return pois
        sim = self._gs.get("sim")
        if sim is not None:
            return getattr(sim, "pois", None) or []
        return []

    @property
    def quest_chains(self):
        return self._gs.get("quest_chains", []) or []

    @property
    def captured_heroes(self):
        return self._gs.get("captured_heroes", []) or []

    @property
    def rescue_opportunities(self):
        return self._gs.get("rescue_opportunities", []) or []

    @property
    def boss_kill_memories(self):
        return self._gs.get("boss_kill_memories", []) or []

    @property
    def revenge_opportunities(self):
        return self._gs.get("revenge_opportunities", []) or []

    @property
    def boss_encounters(self):
        return self._gs.get("boss_encounters", []) or []

    @property
    def elite_enemies(self):
        return self._gs.get("elite_enemies", []) or []

    @property
    def elite_encounters(self):
        return self._gs.get("elite_encounters", self._gs.get("elite_enemies", [])) or []

    @property
    def castle(self):
        return self._gs.get("castle")

    @property
    def player_gold(self) -> int:
        return int(self._gs.get("gold", 0) or 0)


def as_ai_view(view_or_game_state: Any) -> Any:
    """Return an AiGameView-shaped object.

    Pass-through when the AI path already supplied an ``AiGameView`` (anything
    exposing ``.buildings``); wrap a legacy ``game_state`` dict (the direct-prompt
    chat path) in :class:`_DictGameStateView` otherwise.
    """
    if isinstance(view_or_game_state, dict):
        return _DictGameStateView(view_or_game_state)
    return view_or_game_state


def view_to_legacy_context(view: Any) -> dict:
    """Project an :class:`AiGameView` into the legacy ``game_state`` dict shape
    that the LLM-context builders + the ``game/sim`` direction resolver consume.

    Built fresh from the view; carries only the fields those consumers read and
    NO ``economy``/``sim``/``engine``.
    """
    return {
        "world": view.world,
        "buildings": view.buildings,
        "enemies": view.enemies,
        "heroes": view.heroes,
        "bounties": view.bounties,
        "pois": view.pois,
        "quest_chains": getattr(view, "quest_chains", ()) or (),
        "captured_heroes": getattr(view, "captured_heroes", ()) or (),
        "rescue_opportunities": getattr(view, "rescue_opportunities", ()) or (),
        "boss_kill_memories": getattr(view, "boss_kill_memories", ()) or (),
        "revenge_opportunities": getattr(view, "revenge_opportunities", ()) or (),
        "boss_encounters": getattr(view, "boss_encounters", ()) or (),
        "elite_enemies": getattr(view, "elite_enemies", ()) or (),
        "elite_encounters": getattr(view, "elite_encounters", ()) or (),
        "gold": view.player_gold,
        "castle": view.castle,
        "micro_view_building": None,
    }
