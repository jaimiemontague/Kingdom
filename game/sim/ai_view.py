"""WK67 Round A-2 (Move 5): read-only AI views.

The sim builds these (``SimEngine.build_ai_view``); ``ai/`` consumes them. This
closes the L3 read-side boundary leak where ``get_game_state()`` shipped the
live, mutable ``world``/``economy``/``sim``/``engine`` into the AI through an
untyped dict.

Design rules (see ``.cursor/plans/wk67_round_a2_ai_boundary.plan.md`` "Critical
Design Rules" 3 & 5):

* The AI MUST NOT be able to mutate sim state through this surface. ``WorldView``
  wraps the live ``World`` privately (``__slots__``) and exposes ONLY the reads
  the AI + the navigation helpers actually perform; ``AiGameView`` carries NO
  ``economy``/``sim``/``engine``.
* ``WorldView`` is a drop-in for ``world`` wherever the AI passed it. The
  navigation helper ``game.systems.navigation.best_adjacent_tile(world, ...)``
  duck-types ``world.is_walkable``; the AI reads ``world.width``/``height``/
  ``visibility``/``world_to_grid`` directly. That verified set is exactly what
  this facade exposes — no more, no less.

The actual AI/nav read surface off ``world`` (verified 2026-05-29 by grep across
``ai/`` + ``game/entities/hero.py`` + ``game/systems/navigation.py``):

    world.width                 -- ai/behaviors/exploration.py, bounty_pursuit.py,
                                   poi_awareness.py; game/entities/hero.py
    world.height                -- (same sites)
    world.visibility[gy][gx]    -- exploration.py, bounty_pursuit.py,
                                   poi_awareness.py; hero.py  (read-only indexing)
    world.world_to_grid(wx, wy) -- basic_ai.py, stuck_recovery.py; hero.py
    world.is_walkable(gx, gy)   -- stuck_recovery.py directly, and via
                                   navigation.best_adjacent_tile(world, ...) which
                                   every behavior calls

The AI does NOT call ``grid_to_world``, ``is_buildable``, ``find_path``, or
``compute_path_worldpoints`` off ``world`` (verified: zero hits in ``ai/``), so
those are intentionally NOT on ``WorldView`` — exposing them would over-expose
the boundary. (``hero.py`` imports ``compute_path_worldpoints`` but passes the
``world`` object straight through to it; that path is migrated by Agent 06 and
``find_path`` only reads ``is_walkable``/``world_to_grid``/grid dims, all present.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid a runtime import cycle (hero_commands is sim-internal)
    from game.sim.hero_commands import CommandSink


class WorldView:
    """Read-only facade over the live ``World`` for AI navigation/visibility.

    Drop-in for ``world`` wherever the AI/nav helpers passed it (they duck-type
    these reads). Wraps the live ``World`` privately so the AI cannot reach
    mutators (``set_tile``/``reveal``/etc.) through it.
    """

    __slots__ = ("_world", "width", "height")

    def __init__(self, world: Any):
        self._world = world
        # Cached read-only scalars (the AI reads these as plain attrs).
        self.width = world.width
        self.height = world.height

    @property
    def visibility(self):
        """Read-only access to the visibility grid (AI indexes ``[gy][gx]``)."""
        return self._world.visibility

    def world_to_grid(self, wx, wy):
        return self._world.world_to_grid(wx, wy)

    def is_walkable(self, gx, gy):
        return self._world.is_walkable(gx, gy)


@dataclass(frozen=True)
class AiGameView:
    """Immutable, AI-facing view of sim state. Built by ``SimEngine.build_ai_view``.

    Carries NO ``economy``/``sim``/``engine`` — those were the L3 leak. The entity
    lists stay live (AI-side DTOs are deferred, exactly like the render live
    tuples); the AI reads them, never writes. ``world`` is the read-only
    ``WorldView``, not the live ``World``.

    WK126: ``quests`` / ``quest_givers`` are plain-data tuples (primitives only,
    no live object refs) — see the inline field docs below for the exact
    per-entry shape. They default to ``()`` so a no-quest engine yields empty
    tuples and the AI quest behavior no-ops (digest safety).
    """

    world: WorldView
    heroes: tuple              # live entities (AI reads, never writes)
    enemies: tuple
    buildings: tuple
    bounties: tuple
    pois: tuple
    player_gold: int           # immutable fact (was the live economy)
    castle: Any                # read-only building reference
    wave: int
    # WK126 T4 (quests vertical slice): read-only quest surface for the AI,
    # mirroring ``bounties``/``pois`` above. BOUNDARY CONTRACT: both tuples carry
    # PLAIN DATA ONLY (tuples/namedtuples of primitives — str/int/float/bool) —
    # NO live Quest/QuestGiver/Building object refs the AI could mutate.
    # ``SimEngine.build_ai_view`` populates them (Agent 05); they default empty so
    # a no-quest engine produces empty tuples and the AI no-ops (digest guard #1).
    #
    # Per-entry shape:
    #   quests[i]       -> (id: str, quest_type: str, target: str, reward: int,
    #                       is_open: bool, accepted_by: str | None)
    #     * quest_type is the locked vocab: "raid_lair" | "slay_enemy_type" |
    #       "find_poi" | "explore_far"
    #     * target is a plain-data target summary (e.g. lair/poi id, enemy type,
    #       or "gx,gy" tile for explore_far) — an identifier, never an object
    #     * accepted_by is the accepting hero_id, or None while unaccepted
    #   quest_givers[i] -> (giver_id: str, x: float, y: float, is_open: bool)
    #     * giver_id == the owning Herald's Post building id (decline-tracking key)
    #     * x, y are world coordinates of the NPC; is_open mirrors whether the
    #       giver's post currently has an open quest
    quests: tuple = ()
    quest_givers: tuple = ()
    # WK67 Move 6 (L3b write side): the AI proposes hero writes (the shopping
    # purchase) through this sim-owned, synchronous CommandSink instead of
    # mutating economy/hero directly. NO economy, NO sim, NO engine on the view.
    # Defaulted so the frozen dataclass stays constructible without a live sink
    # (e.g. fixture/test construction); SimEngine.build_ai_view always supplies one.
    commands: "CommandSink | None" = None
