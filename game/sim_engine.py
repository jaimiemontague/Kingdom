"""
SimEngine: pure simulation core (no UI/camera/display/audio/VFX).

Stage 2 refactor: split the former GameEngine "god object" into:
- SimEngine (this file): owns world + event bus + entities + systems + sim-owned state.
- PresentationLayer (still in game/engine.py for now): owns pygame init, camera, UI, rendering, audio, VFX.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # type-only; avoids a runtime import cycle with game.entities
    from game.entities.builder_peasant import LumberOps
    from game.sim.ai_view import AiGameView

from game.world import Visibility, World
from game.events import EventBus, GameEventType
from game.sim.determinism import get_rng, set_sim_seed
from game.sim.timebase import set_time_multiplier
from game.sim.timebase import set_sim_now_ms, get_time_multiplier

from config import (
    EARLY_PACING_NUDGE_MODE,
    SIM_SEED,
    DEFAULT_SPEED_TIER,
    STARTING_BUILDINGS,
)

from game.systems import (
    CombatSystem,
    EconomySystem,
    EnemySpawner,
    BountySystem,
    LairSystem,
    NeutralBuildingSystem,
)
from game.systems.buffs import BuffSystem
from game.systems.cleric_heal import ClericHealSystem
from game.systems.quest import QuestSystem
from game.systems.quest_chain import QuestChainSystem
from game.systems.difficulty import DifficultySystem, DifficultyLevel
from game.systems.wave_events import WaveEventSystem
from game.building_factory import BuildingFactory
from game.systems.protocol import SystemContext
from game.types import BountyType, HeroClass

from config import (
    TILE_SIZE,
    MAP_WIDTH,
    MAP_HEIGHT,
    MAX_ALIVE_ENEMIES,
    LAIR_BOUNTY_COST,
    DETERMINISTIC_SIM,
    PLAYER_BUILDING_VISION_TILES,
    PLAYER_GUILD_EXTRA_VISION_TILES,
    PLAYER_GUILD_TYPES,
    POI_DISCOVERY_RANGE_TILES,
)

from game.entities import Castle, Hero, TaxCollector, Peasant, Guard
from game.entities.builder_peasant import BuilderPeasant
from game.entities.quest_giver import QuestGiver
from game.entities.nature import LogStack, Tree
from game.systems.nature import NatureSystem
from game.systems.poi_interaction import POIInteractionSystem


# WK123 C2: how long (sim-ms) a dead hero is retained in ``self.heroes`` after death.
# Within this grace window the hero keeps building a ``HeroProfileSnapshot`` (so the
# watch card, recall button, pin-name capture, low-health-alert cooldown and the
# memorial/pin-liveness reads at hud.py:776/783 see exactly what they see today for a
# freshly-dead pinned hero); past it, the hero is culled in the dead-entity cleanup
# block so per-frame profile cost is bounded by O(alive + recently-dead) instead of
# O(all-time hires). 30 s comfortably exceeds the pin's 10 s fallen-display window
# (PIN_FALLEN_DISPLAY_MS) so nothing the player can interact with changes inside it.
DEAD_HERO_RETENTION_MS = 30_000

# ---------------------------------------------------------------------------
# Mythos S5 (sim-tick) env gates — read once at import. Each defaults to the
# OPTIMIZED path; the hatch restores pre-change behavior for A/B measurement
# (tools/mythos_tick_bench.py) and debugging. All optimized paths are
# value-equivalent to the originals (parity-pinned in tests/test_mythos_sim_tick.py;
# the WK67 AI-decision digest stays byte-identical).
# ---------------------------------------------------------------------------
import os as _os

# tree-growth-incremental: "1" restores the per-tick full dict rebuild.
_TREE_DICT_FULL_REBUILD = _os.environ.get("KINGDOM_TREE_DICT_FULL_REBUILD", "0") == "1"
# tree-blocking-set-walkability: "0" detaches the set from World (fallback chain).
_TREE_BLOCK_SET_ENABLED = _os.environ.get("KINGDOM_TREE_BLOCK_SET", "1") != "0"
# lazy-hero-profiles: "0" restores eager per-call profile builds.
_LAZY_HERO_PROFILES = _os.environ.get("KINGDOM_LAZY_HERO_PROFILES", "1") != "0"


class SimEngine:
    """
    Headless simulation core.

    This class must not depend on pygame UI concepts (camera, window, panels).
    """

    def __init__(self, early_nudge_mode: str | None = None):
        # Determinism knobs (future multiplayer enablement).
        # Seed early so world gen + initial lairs are reproducible when enabled.
        set_sim_seed(SIM_SEED)
        # WK68 Round R0 (Agent 04 — NetworkingDeterminism): a single sim-owned
        # per-build reset of every piece of module/class-global mutable state that
        # the sim reads, so two same-seed in-process GameEngine builds produce
        # byte-identical AI behavior. This folds in the WK67 `Peasant._spawn_counter`
        # fog reset and extends it to RESEARCH_UNLOCKS, the entity-ID counters, and
        # the shared AI RNG. See `_reset_global_sim_state` for the full rationale +
        # the digest guardrail it preserves.
        self._reset_global_sim_state()
        self._sim_now_ms = 0
        # wk12 Chronos: 5-tier speed control; default NORMAL (0.5x).
        set_time_multiplier(DEFAULT_SPEED_TIER)

        # Early pacing nudge state (sim-owned; driven by sim dt).
        self._early_nudge_elapsed_s = 0.0
        self._early_nudge_tip_shown = False
        self._early_nudge_starter_bounty_done = False
        self._early_nudge_mode = (early_nudge_mode or EARLY_PACING_NUDGE_MODE or "auto").strip().lower()

        # Initialize game world (pure simulation)
        self.world = World()
        self.event_bus = EventBus()

        # Game objects (entity lists)
        self.buildings = []
        self.pois = []  # WK54: quick-access list (POIs also live in self.buildings)
        self.heroes = []
        self.enemies = []
        self.bounties = []
        self.trees: list[Tree] = []
        # WK46 Stage 3: render-facing chopped logs (tile-anchored; non-blocking).
        self.log_stacks: list[LogStack] = []
        self.peasants = []
        self.guards = []
        self.peasant_spawn_timer = 0.0

        # WK44 Stage 2: nature growth system.
        self.nature_system = NatureSystem()
        self._tree_growth_by_tile: dict[tuple[int, int], float] = {}
        # Mythos S5 (tree-blocking-set-walkability): tiles whose tree growth is
        # >= 0.75 (the blocking threshold, world.py is_walkable/is_buildable).
        # Maintained in lockstep with _tree_growth_by_tile via _set_tree_growth /
        # _remove_tree_growth / _rebuild_tree_blocking_set so World's TREE branch
        # is one set lookup instead of the 5-call growth-lookup chain.
        self._blocked_tree_tiles: set[tuple[int, int]] = set()
        self._init_trees_from_world()
        self.world.tree_growth_lookup = self._tree_growth_lookup
        if _TREE_BLOCK_SET_ENABLED:
            self.world.blocked_tree_tiles = self._blocked_tree_tiles

        # WK60: Difficulty system (shared by spawner, lair system, wave events)
        self.difficulty_system = DifficultySystem()

        # Systems (sim-owned)
        self.combat_system = CombatSystem()
        self.economy = EconomySystem()
        self.spawner = EnemySpawner(self.world, difficulty=self.difficulty_system)
        self.lair_system = LairSystem(self.world, difficulty=self.difficulty_system)
        self.wave_event_system = WaveEventSystem(difficulty=self.difficulty_system)
        self.neutral_building_system = NeutralBuildingSystem(self.world)
        self.buff_system = BuffSystem()
        # WK124-T4a: clerics heal wounded allied heroes (deterministic, no RNG).
        # Inert when no ally is wounded -> keeps the WK67 AI-decision digest green.
        self.cleric_heal_system = ClericHealSystem()
        self.building_factory = BuildingFactory()
        self.bounty_system = BountySystem()
        self.poi_interaction_system = POIInteractionSystem()
        # WK126: player-funded quests (Herald's Post). Mirrors bounty_system; the
        # system tick EARLY-RETURNS when there are no quests and givers spawn only
        # from a constructed Herald's Post, so the WK67 digest scenario (no posts,
        # no quests) never executes any quest path.
        self.quest_system = QuestSystem()
        # WK138: quest-chain runtime registration. The system is a no-op while
        # no chains are live, so wiring it here keeps the cadence/read-model
        # surface available without changing the empty/default path.
        self.quest_chain_system = QuestChainSystem()
        self.quest_givers: list[QuestGiver] = []
        # WK131: seeded item drops on ENEMY_KILLED (constructing draws no RNG;
        # rolls happen only when a kill event routes through _route_combat_events,
        # so the WK67 digest scenario — which has no enemies — never draws).
        from game.systems.loot import LootSystem
        self.loot_system = LootSystem()

        # WK61-FEAT-004: Rubble records for destroyed buildings.
        self.rubble_records: list = []

        # Selection: WK63 moved to GameEngine.selection (SelectionState); WK67
        # Move 5 deleted the dead sim-side `selected_*` stubs. The live selection
        # is owned by presentation/selection_state.py and the GameEngine wrapper
        # overrides gs["selected_*"] from SelectionState (engine.py:1475-1479).

        # WK57: Underground areas keyed by area_id
        self.underground_areas = {}

        # AI controller (wired by main.py / UrsinaApp)
        self.ai_controller = None

        # Tax collector (created after castle is placed)
        self.tax_collector = None

        # Fog-of-war dirty check state (Ursina consumes via snapshot.fog_revision)
        self._fog_revision = 0
        self._fog_revealers_snapshot = None

        # WK125-T2: publish the pause-frozen sim clock NOW (= 0) so entities
        # constructed before the first update() (e.g. starter heroes/buildings)
        # stamp their timestamps from sim-time, not the wall clock. Without this
        # now_ms() would still fall back to pygame.time.get_ticks() during the
        # construction window, giving a huge first-stamp (negative stuck-delta /
        # delayed first meal) on the very first tick.
        set_sim_now_ms(self._sim_now_ms)

    def _reset_global_sim_state(self) -> None:
        """WK68 R0: reset every module/class-global piece of sim state per build.

        Several sim subsystems keep *module-level* or *class-level* mutable state
        that — unlike instance state — survives across `SimEngine`/`GameEngine`
        constructions inside one process. With seeded determinism that carry-over
        makes two same-seed in-process builds diverge (the keystone WK67
        AI-decision digest drifts build-to-build; observed in the
        `tests/test_wk67_ai_boundary.py` PM NOTE). A *fresh* process starts clean,
        so this reset is a NO-OP on the first build in a process and only matters
        on the 2nd+ in-process build — which is why it leaves the WK67 digest
        (`b73961…`) byte-identical (see the digest guardrail note below).

        Resets, in order:
        1. `Peasant._spawn_counter` (class-global) — drives the deterministic idle
           offset slot (peasant.py). Carry-over moves a fog revealer's grid tile
           and drifts `_fog_revision` ±1 cross-instance (WK67 fog reset).
        2. The monotonic entity-ID counters (`_next_*_id`) in each entity module —
           IDs are labels, not positions, so these do not move the digest, but
           folding them in here makes ID streams reproducible across in-process
           builds (a guardrail for any future ID-keyed determinism).
        3. `RESEARCH_UNLOCKS` (module-global dict in buildings/base.py) — mutated
           in place by `unlock_research()` and never reset; a prior build/test
           that unlocks weapon/armor upgrades changes the blacksmith catalogue and
           shifts hero shopping/decisions.
        4. The shared AI RNG `ai.basic_ai._AI_RNG` — re-seeded to the per-build
           seed so the patrol/wander stream does not keep advancing from where the
           previous in-process build's tick loop left off.

        The `_AI_RNG` reseed (step 4) is GUARDED behind `config.DETERMINISTIC_SIM`:
        in normal (non-deterministic) play `_AI_RNG` stays at its shipped
        import-frozen state, so this reset is a zero-real-play-behavior change
        there. The reseed only runs under deterministic mode, where it exists
        purely so in-process captures/tests reproduce. The other three resets
        (steps 1-3) are UNCONDITIONAL — they are per-new-game correctness, not
        determinism-only.

        DIGEST GUARDRAIL (read before changing the `_AI_RNG` reseed):
        The WK67 keystone digest `b73961…` was captured from
        `_build_digest_engine`, which re-seeds `_AI_RNG` with `.seed(SIM_SEED)`
        BEFORE building the engine (the "reference recipe"). To keep that digest
        byte-identical, this reset re-applies *exactly that same* reseed under
        deterministic mode: `_AI_RNG.seed(int(config.SIM_SEED))`. NOTE: the
        natural fresh-import state of `_AI_RNG` is
        `random.Random(_derive_seed("ai_basic"))` (base seed at import time),
        which is NOT the same state as `.seed(SIM_SEED)`; reseeding to that
        derived state instead WOULD move the digest. We deliberately mirror the
        established `.seed(SIM_SEED)` reference recipe so the digest pin holds and
        deterministic in-process builds stay reproducible. (Proper per-sim RNG
        injection is the deferred Round B `research_state.py`/RNG-injection
        refactor.)
        """
        import config
        import ai.basic_ai as _basic_ai
        import game.entities.buildings.base as _buildings_base
        from game.entities import enemy as _enemy
        from game.entities import guard as _guard
        from game.entities import peasant as _peasant
        from game.entities import rubble as _rubble

        # 1. Class-global peasant idle-offset counter (fog-revision determinism).
        Peasant._spawn_counter = 0

        # 2. Monotonic per-entity-module ID counters (deterministic spawn-order IDs).
        _enemy._next_enemy_id = 0
        _guard._next_guard_id = 0
        _peasant._next_peasant_id = 0
        _rubble._next_rubble_id = 0
        _buildings_base._next_building_id = 0
        # WK126: quest-ID counter (class-global on Quest, same family as above).
        from game.systems.quest import Quest as _Quest
        _Quest._NEXT_ID = 1

        # 3. Kingdom-wide research-unlock dict (module-global, mutated in place).
        for _research_key in _buildings_base.RESEARCH_UNLOCKS:
            _buildings_base.RESEARCH_UNLOCKS[_research_key] = False

        # 4. Shared AI RNG re-seed — ONLY under deterministic mode. In normal play
        #    _AI_RNG stays at its shipped import-frozen state (zero real-play
        #    behavior change); the reseed exists purely so deterministic in-process
        #    captures/tests reproduce (mirrors the WK67 digest reference recipe so
        #    the keystone digest stays byte-identical — see the guardrail note).
        if config.DETERMINISTIC_SIM:
            _basic_ai._AI_RNG.seed(int(config.SIM_SEED))

    def _init_trees_from_world(self) -> None:
        from game.sim import lumber
        lumber.init_trees_from_world(self)

    # ------------------------------------------------------------------
    # Mythos S5: tree growth index maintenance (dict + blocking-tile set)
    # ------------------------------------------------------------------
    # The blocking set mirrors {k for k, g in _tree_growth_by_tile.items() if
    # g >= 0.75} (the world.py walkability threshold). ALL growth-dict writes
    # must go through these helpers (or _rebuild_tree_blocking_set after a bulk
    # replace) so the two can never desync — pinned by tests/test_mythos_sim_tick.py.

    def _set_tree_growth(self, key: tuple[int, int], growth: float) -> None:
        self._tree_growth_by_tile[key] = growth
        if growth >= 0.75:
            self._blocked_tree_tiles.add(key)
        else:
            self._blocked_tree_tiles.discard(key)

    def _remove_tree_growth(self, key: tuple[int, int]) -> None:
        self._tree_growth_by_tile.pop(key, None)
        self._blocked_tree_tiles.discard(key)

    def _rebuild_tree_blocking_set(self) -> None:
        """Recompute the blocking set from the growth dict (bulk-replace sites)."""
        blocked = self._blocked_tree_tiles
        blocked.clear()
        for k, g in self._tree_growth_by_tile.items():
            if g >= 0.75:
                blocked.add(k)

    def _tree_growth_lookup(self, tx: int, ty: int) -> float:
        from game.sim import lumber
        return lumber.tree_growth_lookup(self, tx, ty)

    def remove_trees_in_footprint(self, grid_x: int, grid_y: int, w_tiles: int, h_tiles: int) -> int:
        from game.sim import lumber
        return lumber.remove_trees_in_footprint(self, grid_x, grid_y, w_tiles, h_tiles)

    def _emit_hud_message(self, text: str, color_rgb: tuple[int, int, int] | None = None) -> None:
        self.event_bus.emit(
            {
                "type": GameEventType.HUD_MESSAGE.value,
                "text": str(text),
                "color": tuple(color_rgb or (255, 255, 255)),
            }
        )

    def _on_boss_spawned(self, event: dict) -> None:
        """WK58: Handle boss_spawned event — add boss entity to enemies list."""
        boss = event.get("boss")
        if boss is not None and hasattr(self, "enemies"):
            self.enemies.append(boss)

    def _on_poi_combat_triggered(self, event: dict) -> None:
        """WK56: Handle poi_combat_triggered — spawn enemies at the POI location."""
        from game.entities.enemy import Goblin, Skeleton, Bandit

        _ENEMY_CLASSES = {
            "goblin": Goblin,
            "skeleton": Skeleton,
            "bandit": Bandit,
        }

        spawn_count = int(event.get("spawn_count", 2))
        enemy_types = event.get("enemy_types", ["goblin"])
        spawn_x = float(event.get("spawn_x", 0))
        spawn_y = float(event.get("spawn_y", 0))

        if not enemy_types:
            enemy_types = ["goblin"]

        rng = get_rng("poi_combat_spawn")
        for i in range(spawn_count):
            etype = enemy_types[i % len(enemy_types)]
            cls = _ENEMY_CLASSES.get(etype, Goblin)
            # Small random offset so enemies don't stack on top of each other.
            offset_x = (rng.random() - 0.5) * TILE_SIZE
            offset_y = (rng.random() - 0.5) * TILE_SIZE
            enemy = cls(spawn_x + offset_x, spawn_y + offset_y)
            self.enemies.append(enemy)

    def setup_initial_state(self) -> None:
        """Set up initial sim state (no camera/UI side effects)."""
        # WK58: Listen for boss spawn events from POI interactions.
        # WK56: Listen for POI combat trigger events to spawn enemies.
        if hasattr(self, "event_bus") and self.event_bus:
            self.event_bus.subscribe("boss_spawned", self._on_boss_spawned)
            self.event_bus.subscribe("poi_combat_triggered", self._on_poi_combat_triggered)

        center_x = MAP_WIDTH // 2 - 1
        center_y = MAP_HEIGHT // 2 - 1

        castle = Castle(center_x, center_y)
        if hasattr(castle, "is_constructed"):
            castle.is_constructed = True
        if hasattr(castle, "construction_started"):
            castle.construction_started = True
        self.buildings.append(castle)
        if hasattr(castle, "set_event_bus"):
            castle.set_event_bus(self.event_bus)

        self.tax_collector = TaxCollector(castle)

        for dy in range(castle.size[1]):
            for dx in range(castle.size[0]):
                self.world.set_tile(center_x + dx, center_y + dy, 2)  # PATH

        # WK60 Feature 6: Place pre-constructed starting buildings around the castle.
        for btype, gx, gy in STARTING_BUILDINGS:
            bld = self.building_factory.create(btype, gx, gy)
            if bld is None:
                continue
            bld.is_constructed = True
            bld.construction_started = True
            bld.hp = bld.max_hp
            self.buildings.append(bld)
            if hasattr(bld, "set_event_bus"):
                bld.set_event_bus(self.event_bus)
            # Clear trees from the footprint before placing path tiles.
            bw, bh = bld.size
            self.remove_trees_in_footprint(gx, gy, bw, bh)
            # Lay path tiles under the footprint (same pattern as castle).
            for dy in range(bh):
                for dx in range(bw):
                    self.world.set_tile(gx + dx, gy + dy, 2)  # PATH

        self.lair_system.spawn_initial_lairs(self.buildings, castle)

        # WK54: Generate POIs after buildings and lairs are placed
        try:
            from game.systems.poi_placement import POIPlacementSystem
            from game.sim.determinism import get_rng

            poi_system = POIPlacementSystem()
            poi_rng = get_rng("poi_placement")
            pois = poi_system.generate_pois(
                self.world, self.buildings,
                getattr(self.lair_system, 'lairs', []), poi_rng,
            )
            for poi in pois:
                poi.is_constructed = True
                self.buildings.append(poi)
            self.pois = pois  # quick-access list (also in self.buildings)
        except Exception:
            self.pois = []

        # WK57: Generate underground areas for cave/mine entrances
        self.underground_areas = {}
        try:
            from game.underground import generate_underground_area
            ug_rng = get_rng("underground_gen")
            for poi in getattr(self, 'pois', []):
                poi_type = getattr(getattr(poi, 'poi_def', None), 'poi_type', '')
                if poi_type in ('poi_cave_entrance', 'poi_mine_entrance'):
                    area = generate_underground_area(poi, ug_rng)
                    self.underground_areas[area.area_id] = area
        except (ImportError, Exception):
            self.underground_areas = {}

        # WK57 Wave 5: Wire underground areas into POI interaction system
        self.poi_interaction_system._underground_areas = self.underground_areas
        self.poi_interaction_system._sim_engine = self

        # WK57 Wave 4: Init underground fog grids + layer-aware pathfinder
        for _area_id, _area in self.underground_areas.items():
            self.world.init_underground_fog(_area)
        try:
            from game.systems.pathfinding import LayerPathfinder
            self.layer_pathfinder = LayerPathfinder(self.world, self.underground_areas)
        except (ImportError, Exception):
            self.layer_pathfinder = None

        # WK54: Flatten terrain under all buildings (including POIs)
        if hasattr(self.world, 'flatten_building_footprints'):
            self.world.flatten_building_footprints(self.buildings)

        self._update_fog_of_war()

    def _build_system_context(self) -> SystemContext:
        castle = next(
            (b for b in self.buildings if getattr(b, "building_type", None) == "castle"),
            None,
        )
        return SystemContext(
            heroes=self.heroes,
            enemies=self.enemies,
            buildings=self.buildings,
            world=self.world,
            economy=self.economy,
            event_bus=self.event_bus,
            peasants=self.peasants,
            guards=self.guards,
            bounties=self.bounty_system.get_unclaimed_bounties(),
            pois=list(getattr(self, "pois", []) or []),
            rubble_records=list(getattr(self, "rubble_records", []) or []),
            lairs=list(getattr(self.lair_system, "lairs", []) or []),
            castle=castle,
        )

    def get_game_state(
        self,
        *,
        screen_w: int,
        screen_h: int,
        display_mode: str,
        window_size: tuple[int, int],
        placing_building_type,
        debug_ui: bool,
        micro_view_mode,
        micro_view_building,
        micro_view_quest_hero,
        micro_view_quest_data,
        right_panel_rect,
        llm_available: bool,
        ui_cursor_pos,
    ) -> dict:
        from game.sim.hero_profile import LazyHeroProfiles, build_hero_profile_snapshot
        from game.sim.timebase import now_ms as sim_now_ms

        _ms = int(sim_now_ms())
        # WK123 C2: profiles cover alive heroes plus dead heroes still inside
        # the retention window. ``build_hero_profile_snapshot`` is the heaviest
        # per-hero per-frame work (it sorts known_places + profile_memory), so
        # skipping long-dead heroes bounds this O(all-time hires) cost to
        # O(alive + recently-dead). The window is enforced here AND by the cull in
        # ``tick`` — heroes past it are removed from self.heroes entirely. Within the
        # window the profile is identical to today's, preserving the watch-card /
        # recall / memorial reads for a freshly-dead pinned hero.
        #
        # Mythos S5 (lazy-hero-profiles): the eligible-id set is resolved HERE
        # (same as the old eager loop), but each snapshot is built only on first
        # HUD access (LazyHeroProfiles) — repo-wide the mapping is read via
        # .get()/`in` for at most the pinned/selected hero per frame, so the
        # ~26-hero x 20Hz eager build was almost entirely waste.
        # KINGDOM_LAZY_HERO_PROFILES=0 restores the eager build (A/B hatch).
        _eligible: dict[str, object] = {}
        for _h in self.heroes:
            _hid = getattr(_h, "hero_id", None)
            if _hid is None:
                continue
            if not getattr(_h, "is_alive", True):
                _dead_since = getattr(_h, "_dead_since_ms", None)
                if _dead_since is not None and (_ms - int(_dead_since)) > DEAD_HERO_RETENTION_MS:
                    continue
            _eligible[str(_hid)] = _h
        if _LAZY_HERO_PROFILES:
            hero_profiles_by_id: dict[str, object] = LazyHeroProfiles(_eligible, self, _ms)
        else:
            hero_profiles_by_id = {
                _hid: build_hero_profile_snapshot(_h, self, now_ms=_ms)
                for _hid, _h in _eligible.items()
            }
        # WK67 Move 5: dead sim-side selection reads removed. Selection is
        # presentation-owned; the GameEngine wrapper overrides these keys from
        # SelectionState and recomputes selected_hero_profile (engine.py:1475-1486).

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
        return {
            "screen_w": int(screen_w),
            "screen_h": int(screen_h),
            "display_mode": str(display_mode),
            "window_size": tuple(window_size),
            "gold": self.economy.player_gold,
            "heroes": self.heroes,
            "peasants": self.peasants,
            "guards": self.guards,
            "enemies": self.enemies,
            "buildings": self.buildings,
            "buildings_construction_progress": tuple(
                float(getattr(b, "construction_progress", 1.0)) for b in self.buildings
            ),
            "bounties": self.bounty_system.get_unclaimed_bounties(),
            "bounty_system": self.bounty_system,
            "wave": self.spawner.wave_number,
            # WK67 Move 5: sim no longer owns selection. These keys are placeholders
            # the GameEngine wrapper overrides from the presentation SelectionState
            # (engine.py:1475-1486); a direct (unwrapped) get_game_state() call gets
            # None selection, which is correct — the sim has no selection truth.
            "selected_hero": None,
            "hero_profiles_by_id": hero_profiles_by_id,
            "selected_hero_profile": None,
            "selected_building": None,
            "selected_peasant": None,
            "castle": castle,
            "economy": self.economy,
            "world": self.world,
            # WK46 Stage 3: pragmatic bridge so BuilderPeasant can call sim helpers without imports/cycles.
            "sim": self,
            "placing_building_type": placing_building_type,
            "debug_ui": bool(debug_ui),
            "micro_view_mode": micro_view_mode,
            "micro_view_building": micro_view_building,
            "micro_view_quest_hero": micro_view_quest_hero,
            "micro_view_quest_data": micro_view_quest_data,
            "right_panel_rect": right_panel_rect,
            "llm_available": bool(llm_available),
            "ui_cursor_pos": ui_cursor_pos,
        }

    def build_ai_view(self) -> "AiGameView":
        """Build the read-only AI-facing view of sim state (WK67 Move 5 / L3).

        This is the AI consumer path — separate from :meth:`get_game_state` (the
        UI dict). It exposes a read-only :class:`WorldView` and immutable facts
        (``player_gold``, ``wave``, read-only ``castle``); it carries NO
        ``economy``/``sim``/``engine``, so the AI can no longer hold or mutate a
        live sim service through it. Entity lists stay live (AI reads, never
        writes — AI-side DTOs are deferred).
        """
        from game.sim.ai_view import AiGameView, WorldView
        from game.sim.hero_commands import SimCommandSink

        castle = next(
            (b for b in self.buildings if getattr(b, "building_type", None) == "castle"),
            None,
        )
        # WK126-T4 (populate): plain-data quest/giver snapshots for the AI (no live
        # object refs the AI could mutate — namedtuples from game.systems.quest).
        # Both are EMPTY tuples when no quests/givers exist, which is what the AI's
        # quest branch early-returns on (digest guard #1). Passed conditionally so
        # this populate code lands cleanly even if Agent 03's ai_view dataclass
        # fields (quests / quest_givers, WK126-T4) ship in a parallel wave.
        _quest_kwargs = {}
        _view_fields = getattr(AiGameView, "__dataclass_fields__", {})
        if "quests" in _view_fields:
            _quest_kwargs["quests"] = tuple(
                q.to_ai_info() for q in self.quest_system.get_active_quests()
            )
        if "quest_givers" in _view_fields:
            _quest_kwargs["quest_givers"] = tuple(g.to_ai_info() for g in self.quest_givers)
        if "quest_chains" in _view_fields:
            _quest_kwargs["quest_chains"] = self._active_quest_chain_views()
        return AiGameView(
            world=WorldView(self.world),
            heroes=tuple(self.heroes),
            enemies=tuple(self.enemies),
            buildings=tuple(self.buildings),
            bounties=tuple(self.bounty_system.get_unclaimed_bounties()),
            pois=tuple(self.pois),
            player_gold=int(self.economy.player_gold),
            castle=castle,
            wave=int(self.spawner.wave_number),
            # WK67 Move 6 (L3b): the AI proposes the shopping purchase through this
            # sim-owned synchronous sink; the sim applies it immediately.
            commands=SimCommandSink(self),
            **_quest_kwargs,
        )

    def _active_quest_chain_views(self) -> tuple:
        """Return read-only quest-chain snapshots, or () when no chains are live."""
        chain_system = getattr(self, "quest_chain_system", None)
        if chain_system is None:
            return ()
        for getter_name in (
            "get_active_chain_snapshots",
            "get_active_chain_views",
            "get_active_chains",
        ):
            getter = getattr(chain_system, getter_name, None)
            if callable(getter):
                chains = getter()
                return () if chains is None else tuple(chains)
        return ()

    @property
    def lumber_ops(self) -> "LumberOps":
        """Typed lumber accessor for sim entities (WK67 Move 6 / L3b).

        ``SimEngine`` already implements ``find_nearest_choppable_tree_for_builder``
        / ``chop_tree_at`` / ``harvest_log_at`` (the :class:`LumberOps` surface), so
        it is its own facade. The BuilderPeasant receives this through the
        sim-internal peasant update context instead of pulling the live ``sim`` out
        of the UI ``game_state`` dict.
        """
        return self

    def create_quest(self, giver_id, quest_type, target, reward, *, count=1):
        """WK126: fund (escrow) + arm a quest on a Herald's Post giver.

        THE engine action the quest-create UI (T9) calls on confirm: debits the
        treasury via ``economy.fund_quest`` (returns ``None`` if the player cannot
        afford it — no quest is created), creates the ``Quest``, emits
        ``QUEST_OFFERED``, and flips the giver's ``is_open`` immediately so the
        "!" marker shows without waiting a tick. Never called in the WK67 digest
        scenario (player-UI only).
        """
        reward = int(reward)
        if not self.economy.fund_quest(reward):
            return None
        quest = self.quest_system.create_quest(
            giver_id, quest_type, target, reward, count=count
        )
        self.event_bus.emit(
            {
                "type": GameEventType.QUEST_OFFERED.value,
                "quest_id": int(quest.quest_id),
                "quest_type": str(quest.quest_type),
                "giver_id": str(quest.giver_id),
                "reward": reward,
            }
        )
        gid = str(giver_id)
        for giver in self.quest_givers:
            if giver.giver_id == gid:
                giver.is_open = True
        return quest

    def find_hero_by_id(self, hero_id: str):
        """Resolve a live hero by its stable ``hero_id`` (WK67 Move 6).

        The hero-command applier (``game.sim.hero_commands.apply_hero_command``)
        uses this to resolve the proposing hero before mutating it; the AI never
        gets the hero object, only proposes a command carrying the id.
        Returns the hero or ``None`` if no live hero matches.
        """
        if hero_id is None:
            return None
        target = str(hero_id)
        for hero in self.heroes:
            if str(getattr(hero, "hero_id", "")) == target:
                return hero
        return None

    def build_snapshot(
        self,
        *,
        vfx_projectiles: tuple,
    ):
        # WK67 Move 4 / L6: the sim snapshot is SIM TRUTH only — it no longer
        # accepts any presentation kwargs (camera/zoom/screen/paused/running/
        # pause_menu_visible/selected_*/sim_blend_fraction/sim_tick_id). Those are
        # engine-owned presentation state built into PresentationFrameState by
        # GameEngine.build_presentation_frame. ``vfx_projectiles`` stays a passed-in
        # kwarg (sim-effect data the sim doesn't store on itself frame-to-frame).
        from game.sim.snapshot import RenderSnapshot
        from game.sim.render_dto import (
            unit_dto_from,
            building_dto_from,
            bounty_dto_from,
        )

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)

        # WK68 R3 (Agent 03): bounty UI metrics are computed HERE, in the
        # render-prep path, immediately before the bounty DTOs are built — so
        # ``bounty_dto_from`` reads freshly-computed ``b.responders`` /
        # ``b.attractiveness_tier``. This call MUST live in build_snapshot (NOT in
        # the core ``SimEngine.update`` tick and NOT in ``build_ai_view``): it
        # mutates the live bounties' responders/attractiveness_tier, which
        # ``game/sim/contracts.py`` feeds into the WK67 AI contract. The WK67
        # AI-decision digest (b73961…) is computed by a HEADLESS sim that ticks but
        # does NOT build render snapshots, so running this only at render-prep time
        # keeps that digest byte-identical while giving Ursina (the default
        # renderer) correct bounty metrics too. Relocated out of pygame_renderer
        # (the last render-path reader of the live entity tuples) for WK68 R3 / L1.
        if hasattr(self.bounty_system, "update_ui_metrics"):
            try:
                self.bounty_system.update_ui_metrics(
                    self.heroes,
                    self.enemies,
                    self.buildings,
                )
            except Exception:
                pass

        # WK66 Round A-1 (ADDITIVE): build frozen render DTOs alongside the live
        # tuples. tile_visible is computed here from the sim's fog grid so the
        # render boundary does not have to read world.visibility for it.
        _world = self.world
        _world_vis = getattr(_world, "is_tile_visible_at", None)
        _bounties = self.bounty_system.get_unclaimed_bounties()
        _tax = getattr(self, "tax_collector", None)
        return RenderSnapshot(
            world=self.world,
            pois=tuple(getattr(self, 'pois', ())),
            trees=tuple(self.trees),
            log_stacks=tuple(self.log_stacks),
            fog_revision=int(getattr(self, "_fog_revision", 0)),
            gold=int(getattr(self.economy, "player_gold", 0)),
            wave=int(getattr(self.spawner, "wave_number", 0)),
            buildings_construction_progress=tuple(
                float(getattr(b, "construction_progress", 1.0)) for b in self.buildings
            ),
            castle=castle,
            vfx_projectiles=tuple(vfx_projectiles or ()),
            underground_areas=getattr(self, 'underground_areas', None),
            rubble_records=tuple(getattr(self, 'rubble_records', ())),
            # WK66 Round A-1: frozen render DTOs (additive; consumers flip in W2).
            # WK123 C2: skip dead heroes/peasants/guards at build time. Every render
            # consumer of these DTO tuples already early-outs on ``not is_alive``
            # (ursina_unit_sync :117/:289/:350, instanced_unit_renderer :466/:517/:537/:580,
            # and the pygame registry render_hero/peasant/guard via hero_renderer:130 /
            # worker_renderer:148,234 / registry:100) — so a dead unit's DTO is built every
            # frame only to be discarded. Skipping it removes the all-time accumulation that
            # made per-frame DTO cost scale with total hires instead of with the living set.
            # Enemies/guards are already culled when dead (cleanup block below), but the
            # guard filter is a cheap belt-and-suspenders guard against a mid-tick death.
            hero_dtos=tuple(unit_dto_from(h, "hero") for h in self.heroes if getattr(h, "is_alive", True)),
            enemy_dtos=tuple(unit_dto_from(e, "enemy") for e in self.enemies),
            peasant_dtos=tuple(unit_dto_from(p, "peasant") for p in self.peasants if getattr(p, "is_alive", True)),
            guard_dtos=tuple(unit_dto_from(g, "guard") for g in self.guards if getattr(g, "is_alive", True)),
            tax_collector_dto=(
                unit_dto_from(_tax, "tax_collector") if _tax is not None else None
            ),
            building_dtos=tuple(
                building_dto_from(
                    b,
                    tile_visible=bool(
                        _world_vis(float(getattr(b, "x", 0.0)), float(getattr(b, "y", 0.0)))
                    ) if _world_vis is not None else True,
                )
                for b in self.buildings
            ),
            bounty_dtos=tuple(bounty_dto_from(b) for b in _bounties),
            quest_chains=self._active_quest_chain_views(),
        )

    # ---------------------------------------------------------------------
    # WK46 Stage 3: Lumberjack builder helpers (deterministic + fog-respecting)
    # ---------------------------------------------------------------------
    @staticmethod
    def _wood_yield_for_growth(growth: float) -> int:
        from game.sim import lumber
        return lumber.wood_yield_for_growth(growth)

    def find_nearest_choppable_tree_for_builder(self, from_tx: int, from_ty: int) -> tuple[int, int, float] | None:
        from game.sim import lumber
        return lumber.find_nearest_choppable_tree_for_builder(self, from_tx, from_ty)

    def chop_tree_at(self, tx: int, ty: int) -> float | None:
        from game.sim import lumber
        return lumber.chop_tree_at(self, tx, ty)

    def harvest_log_at(self, tx: int, ty: int) -> int:
        from game.sim import lumber
        return lumber.harvest_log_at(self, tx, ty)

    def update(self, dt: float, game_state: dict) -> None:
        """Core sim update loop (no UI/render/vfx)."""
        # Reset per-frame pathfinding budget before any entity updates.
        from game.systems.navigation import get_pathfinding_budget
        get_pathfinding_budget().begin_frame()

        # Sim-time accounting: ALWAYS drive a monotonic, pause-frozen sim clock so
        # now_ms() never falls back to the real wall clock (pygame.time.get_ticks()).
        # update() is the ONLY set_sim_now_ms caller and is skipped while paused
        # (lifecycle._prepare_sim_and_camera returns False), so this clock freezes on
        # pause and never jumps on resume / with app uptime. DETERMINISTIC_SIM now
        # governs ONLY RNG/order determinism, not the clock — DET=1 already used this
        # exact accumulator, so the WK67 digest stays byte-identical.
        self._sim_now_ms += int(round(float(dt) * 1000.0))
        set_sim_now_ms(self._sim_now_ms)

        # Ensure all buildings have event bus for interior enter/exit events.
        for building in self.buildings:
            if getattr(building, "_event_bus", None) is None and hasattr(building, "set_event_bus"):
                building.set_event_bus(self.event_bus)

        system_ctx = self._build_system_context()

        # WK44 Stage 2: tree growth (affects world blocking + renderer scale).
        # Mythos S5 (tree-growth-incremental): NatureSystem.tick now reports the
        # trees whose growth actually changed (growth is discrete — 2-minute stage
        # boundaries — so most ticks change nothing). We update only those keys
        # instead of rebuilding the whole ~2k-entry dict + key-tuple churn every
        # tick. Removal paths (chop / building footprint) already pop their keys
        # in game/sim/lumber.py, so the incremental mapping is value-identical to
        # the old full rebuild (pinned by tests/test_mythos_sim_tick.py parity).
        # KINGDOM_TREE_DICT_FULL_REBUILD=1 restores the pre-change rebuild (A/B hatch).
        pre_keys = set(self._tree_growth_by_tile.keys()) if _TREE_DICT_FULL_REBUILD else ()
        try:
            # WK45: NatureSystem may spawn new saplings and may need world context.
            changed_trees = self.nature_system.tick(dt, self.trees, world=self.world, buildings=self.buildings)  # type: ignore[call-arg]
        except TypeError:
            changed_trees = self.nature_system.tick(dt, self.trees)

        # Ensure world tiles reflect newly spawned saplings (TileType.TREE immediately),
        # and keep growth lookup consistent for buildability/blocking rules.
        if _TREE_DICT_FULL_REBUILD or changed_trees is None:
            # Pre-change path (env hatch, or a legacy/stubbed NatureSystem.tick that
            # returns None — fall back to the full rebuild so the dict can't go stale).
            if self.trees:
                # First refresh growth lookup so newly spawned saplings don't default to 1.0.
                self._tree_growth_by_tile = {
                    t.key: float(getattr(t, "growth_percentage", 0.25)) for t in self.trees
                }
                self._rebuild_tree_blocking_set()
                new_keys = set(self._tree_growth_by_tile.keys()) - set(pre_keys)
                if new_keys:
                    try:
                        from game.world import TileType

                        for tx, ty in sorted(new_keys):
                            if int(self.world.get_tile(int(tx), int(ty))) != int(TileType.TREE):
                                self.world.set_tile(int(tx), int(ty), int(TileType.TREE))
                    except Exception:
                        pass
        elif changed_trees:
            growth_map = self._tree_growth_by_tile
            new_keys: list[tuple[int, int]] = []
            for t in changed_trees:
                k = t.key
                if k not in growth_map:
                    new_keys.append(k)
                self._set_tree_growth(k, float(getattr(t, "growth_percentage", 0.25)))
            if new_keys:
                try:
                    from game.world import TileType

                    for tx, ty in sorted(new_keys):
                        if int(self.world.get_tile(int(tx), int(ty))) != int(TileType.TREE):
                            self.world.set_tile(int(tx), int(ty), int(TileType.TREE))
                except Exception:
                    pass

        # AI + hero updates
        # WK67 Move 5 (L3): the AI consumes a read-only AiGameView built from sim
        # state — NOT the live UI dict (which still carries world/economy/sim/engine
        # for the UI/HUD/hero paths). Agent 06 migrates BasicAI.update + behaviors to
        # read the view in the immediately-following task; until then the AI path is
        # transitionally broken (BasicAI still expects the dict). The full-suite + AI
        # digest gate is AFTER Agent 06.
        if self.ai_controller:
            self.ai_controller.update(dt, self.heroes, self.build_ai_view())

        from game.entities.hero import HeroState
        for hero in self.heroes:
            if getattr(hero, "llm_move_request", None) is not None:
                wx, wy = hero.llm_move_request
                hero.set_target_position(wx, wy)
                hero.llm_move_request = None
        for hero in self.heroes:
            hero.update(dt, game_state)

        # WK57 Wave 5E: Check if underground heroes should retreat
        if self.underground_areas:
            from game.underground import check_underground_hero_retreat
            for hero in self.heroes:
                if getattr(hero, "is_alive", False) and getattr(hero, "layer", 0) == -1:
                    check_underground_hero_retreat(hero, self.underground_areas)

        # Fog + buffs + early pacing (castle from game_state)
        self._update_fog_of_war()
        self.buff_system.update(system_ctx, dt)
        # WK124-T4a: cleric heals (mirrors the buff_system tick; no-op when no
        # ally is wounded, so the WK67 digest scenario stays byte-identical).
        self.cleric_heal_system.update(system_ctx, dt)
        castle = game_state.get("castle")
        self._maybe_apply_early_pacing_nudge(dt, castle)

        # Peasants
        self.peasant_spawn_timer += dt
        # Keep at least 2 "regular" peasants alive. BuilderPeasants are task-specific and
        # should not suppress the baseline workforce for player-placed buildings.
        alive_regular_peasants = [
            p
            for p in self.peasants
            if getattr(p, "is_alive", False) and not isinstance(p, BuilderPeasant)
        ]
        if (
            not getattr(self, "_worker_scale_shot_hold", False)
            and castle
            and len(alive_regular_peasants) < 2
            and self.peasant_spawn_timer >= 5.0
        ):
            self.peasant_spawn_timer = 0.0
            self.peasants.append(Peasant(castle.center_x, castle.center_y))
        # WK67 Move 6 (L3b): build the sim-internal peasant update context. It
        # carries the typed lumber accessor (``lumber_ops``) so BuilderPeasant no
        # longer fishes the live ``sim`` out of the UI ``game_state`` dict. We
        # extend the existing dict rather than the UI dict in place so the UI
        # contract is untouched and the typed accessor is sim-owned.
        peasant_ctx = dict(game_state)
        peasant_ctx["lumber_ops"] = self.lumber_ops
        for peasant in self.peasants:
            peasant.update(dt, peasant_ctx)

        # Enemies + ranged events
        enemy_ranged_events: list[dict] = []
        for enemy in self.enemies:
            enemy.update(dt, self.heroes, self.peasants, self.buildings, guards=self.guards, world=self.world)
        for enemy in self.enemies:
            if hasattr(enemy, "_last_ranged_event") and enemy._last_ranged_event is not None:
                enemy_ranged_events.append(enemy._last_ranged_event)
                enemy._last_ranged_event = None

        # Guards
        for guard in self.guards:
            guard.update(dt, self.enemies, world=self.world, buildings=self.buildings)

        # Spawning (cap)
        alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
        remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
        if remaining_slots > 0:
            new_enemies = self.spawner.spawn(dt)
            if new_enemies:
                self.enemies.extend(new_enemies[:remaining_slots])
            alive_enemy_count = len([e for e in self.enemies if getattr(e, "is_alive", False)])
            remaining_slots = max(0, int(MAX_ALIVE_ENEMIES) - alive_enemy_count)
            if remaining_slots > 0:
                lair_enemies = self.lair_system.spawn_enemies(dt, self.buildings)
                if lair_enemies:
                    self.enemies.extend(lair_enemies[:remaining_slots])

        # WK60 Feature 1: Wave events (fires on timer, independent from trickle/lair spawns)
        self.wave_event_system.update(system_ctx, dt)

        # Separation (copied from engine; sim-owned)
        self._apply_entity_separation(dt)

        # Combat
        self.combat_system.update(system_ctx, dt)
        if enemy_ranged_events:
            self.event_bus.emit_batch(enemy_ranged_events)
        events = self.combat_system.get_emitted_events()
        self._route_combat_events(events)

        # R2-F: Dead-entity cleanup — only rebuild lists when something died
        # or every 60 ticks as a fallback safety net.
        if len(events) > 0:
            self._dead_entity_dirty = True
        cleanup_tick = getattr(self, '_cleanup_tick', 0)
        self._cleanup_tick = cleanup_tick + 1
        if getattr(self, '_dead_entity_dirty', False) or cleanup_tick % 60 == 0:
            # WK125-T1: read death time through timebase.now_ms() — the SAME single
            # clock the get_game_state profile-build retention window reads (hero_profile.py).
            # update() now ALWAYS publishes self._sim_now_ms via set_sim_now_ms in BOTH
            # modes, so now_ms() == self._sim_now_ms here in real play; the pre-WK125
            # wall-clock divergence (now_ms() on pygame ticks while self._sim_now_ms
            # stayed 0 in the non-deterministic path) is gone. We deliberately keep the
            # timebase read (not self._sim_now_ms) so the death-stamp and the profile
            # build remain a SINGLE clock even if a caller drives time via timebase
            # directly — the WK123-C2 contract the dead-hero TTL test pins.
            from game.sim.timebase import now_ms as _sim_now_ms
            _now_ms = int(_sim_now_ms())
            # WK60 Feature 3: decrement guild hero count for newly dead heroes
            for hero in self.heroes:
                if not getattr(hero, "is_alive", True) and not getattr(hero, "_guild_death_processed", False):
                    hero._guild_death_processed = True
                    # WK123 C2: stamp the moment of death (sim-ms) so the profile-build
                    # retention window in get_game_state and the hero cull below share a
                    # single death time. Stamped exactly once, alongside the existing
                    # one-shot guild-death bookkeeping.
                    hero._dead_since_ms = _now_ms
                    home = getattr(hero, "home_building", None)
                    if home is not None and hasattr(home, "on_hero_death"):
                        home.on_hero_death()
            self.enemies = [e for e in self.enemies if getattr(e, "is_alive", False)]
            self.guards = [g for g in self.guards if getattr(g, "is_alive", False)]
            # WK123 C2: cull dead PEASANTS immediately (they have no memorial / pin /
            # profile UX — nothing reads a dead peasant — so this mirrors the
            # enemy/guard cull and bounds self.peasants by the living set).
            self.peasants = [p for p in self.peasants if getattr(p, "is_alive", False)]
            # WK123 C2: TTL-cull dead HEROES. A dead hero is kept (and keeps building a
            # profile) until DEAD_HERO_RETENTION_MS after death, preserving the memorial /
            # pin-liveness / watch-card reads for a freshly-dead pinned hero; past the
            # window it is removed so per-frame hero work is bounded by O(alive +
            # recently-dead) instead of O(all-time hires). A hero that died this tick may
            # not yet carry a stamp (defensive ``is None`` keeps it until next pass).
            self.heroes = [
                h
                for h in self.heroes
                if getattr(h, "is_alive", True)
                or (
                    getattr(h, "_dead_since_ms", None) is None
                    or (_now_ms - int(getattr(h, "_dead_since_ms"))) <= DEAD_HERO_RETENTION_MS
                )
            ]
            self._dead_entity_dirty = False

        # WK61-FIX: Destroyed-building cleanup (was missing from SimEngine — only ran
        # in the old presentation-layer path via CleanupManager).
        self._cleanup_destroyed_buildings()

        # Bounties
        claimed = self.bounty_system.check_claims(self.heroes)
        bounty_claimed_events = []
        for bounty, hero in claimed:
            self._emit_hud_message(f"{hero.name} claimed bounty: +${bounty.reward}!", (255, 215, 0))
            bounty_claimed_events.append(
                {
                    "type": GameEventType.BOUNTY_CLAIMED.value,
                    "x": float(bounty.x),
                    "y": float(bounty.y),
                    "reward": bounty.reward,
                    "hero": hero.name,
                    "hero_id": str(getattr(hero, "hero_id", "") or ""),
                }
            )
        if bounty_claimed_events:
            self.event_bus.emit_batch(bounty_claimed_events)
        self.bounty_system.cleanup()

        # WK126: quests. QuestSystem.update EARLY-RETURNS (no events, no RNG, no
        # mutation) when there are no quests — digest guard #2. The giver-lifecycle
        # block below is gated on quest_givers existing at all; the WK67 digest
        # scenario has no Herald's Post, so neither branch ever runs there.
        self.quest_system.update(system_ctx, dt)
        # WK138: quest-chain cadence hook. Empty-update is a no-op when no
        # chains are live, so this stays digest-stable in the WK67 scenario.
        self.quest_chain_system.update(system_ctx, dt)
        if self.quest_givers:
            # Cull NPCs whose post was destroyed (mirrors guard cleanup — the
            # destroyed post has already been removed from self.buildings).
            # WK133 QA fix: a destroyed post also FAILS its OPEN (unaccepted)
            # offer — the NPC is gone, so the offer is unreachable and would
            # otherwise leak as a zombie open quest in view.quests. Accepted
            # quests survive (the hook skips them; it also early-returns when
            # there are no quests, preserving digest guard #2).
            dead_givers = [g for g in self.quest_givers if g.post not in self.buildings]
            if dead_givers:
                self.quest_givers = [g for g in self.quest_givers if g.post in self.buildings]
                for dead_giver in dead_givers:
                    self.quest_system.on_giver_destroyed(dead_giver.giver_id, self.event_bus)
            # Mirror the open-offer state onto each NPC (drives the "!" marker
            # and the AI candidate list).
            for giver in self.quest_givers:
                giver.is_open = self.quest_system.has_open_quest_for(giver.giver_id)

        # Neutral systems
        self.neutral_building_system.tick(dt, self.buildings, self.heroes, self.peasants, castle)
        if self.tax_collector:
            self.tax_collector.update(dt, self.buildings, self.economy, world=self.world)

        # Buildings
        self._update_buildings(dt)

        # WK61-FEAT-004: Expire old rubble records (2-minute lifetime).
        if self.rubble_records:
            from game.sim.timebase import now_ms as _rubble_now_ms
            _rub_now = int(_rubble_now_ms())
            self.rubble_records = [
                r for r in self.rubble_records
                if _rub_now - r.created_ms < r.duration_ms
            ]

        # WK55: POI discovery — check if any hero is within discovery range of undiscovered POIs
        self._check_poi_discovery()

        # WK56: POI interactions — tick cooldowns and resolve proximity interactions
        self.poi_interaction_system.tick_cooldowns(getattr(self, 'pois', []), dt)
        self.poi_interaction_system.check_interactions(
            self.heroes, getattr(self, 'pois', []), self.world,
            self.economy, self.event_bus, dt)

    # --- Below are sim helpers copied/adapted from engine.py ---
    def _check_poi_discovery(self):
        from game.sim import poi_discovery
        poi_discovery.check_poi_discovery(self)

    def _cleanup_destroyed_buildings(self) -> None:
        from game.sim import building_lifecycle
        building_lifecycle.cleanup_destroyed_buildings(self)

    def _update_buildings(self, dt: float) -> None:
        from game.sim.timebase import now_ms as sim_now_ms

        now_ms = int(sim_now_ms())
        for building in self.buildings:
            if getattr(building, "research_in_progress", None):
                advance = getattr(building, "advance_research", None)
                if callable(advance):
                    advance(now_ms)

        building_ranged_events = []
        for building in self.buildings:
            if building.building_type == "trading_post" and hasattr(building, "update"):
                building.update(dt, self.economy)
            elif building.building_type == "marketplace" and hasattr(building, "update"):
                building.update(dt, self.economy)
            elif building.building_type == "guardhouse" and hasattr(building, "update"):
                # WK60: pass enemies list for arrow attacks (Feature 5)
                should_spawn = building.update(dt, [g for g in self.guards if g.home_building == building], enemies=self.enemies)
                if should_spawn:
                    g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                    self.guards.append(g)
                    if hasattr(building, "guards_spawned"):
                        building.guards_spawned += 1
            elif building.building_type == "herald_post":
                # WK126: spawn exactly ONE Quest-Giver NPC beside a CONSTRUCTED
                # Herald's Post (guardhouse→guard pattern). Cap 1 per post; the
                # NPC is culled in the quest block of update() when the post is
                # destroyed. The WK67 digest scenario has no herald_post, so this
                # branch is structurally unreachable there.
                if getattr(building, "is_constructed", False) and not any(
                    g.post is building for g in self.quest_givers
                ):
                    self.quest_givers.append(QuestGiver(building))
            elif building.building_type == "palace":
                max_guards = getattr(building, "max_palace_guards", 0)
                if max_guards > 0 and getattr(building, "is_constructed", True):
                    current = len([g for g in self.guards if g.home_building == building])
                    if current < max_guards:
                        g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                        self.guards.append(g)

        for building in self.buildings:
            # WK122-BUG-B1: collect ALL ranged events. Buildings that fire a
            # multi-arrow volley (e.g. Guardhouse) expose a non-empty
            # ``_last_ranged_events`` LIST with one event per arrow (distinct
            # origins). Previously only the singular ``_last_ranged_event`` (the
            # first arrow) was collected, so arrow #2 was silently dropped and a
            # single ProjectileVFX spawned. Prefer the plural list when present;
            # otherwise fall back to the singular field (buildings that only set
            # the singular). Clear both so events fire exactly once.
            events_list = getattr(building, "_last_ranged_events", None)
            if events_list:
                building_ranged_events.extend(events_list)
                building._last_ranged_events = []
                building._last_ranged_event = None
            elif getattr(building, "_last_ranged_event", None) is not None:
                building_ranged_events.append(building._last_ranged_event)
                building._last_ranged_event = None
        if building_ranged_events:
            self.event_bus.emit_batch(building_ranged_events)

    def _apply_entity_separation(self, dt: float) -> None:
        from game.sim import separation
        separation.apply_entity_separation(self, dt)

    def _route_combat_events(self, events: list) -> None:
        for event in events:
            if event.get("type") == GameEventType.ENEMY_KILLED.value:
                self._emit_hud_message(
                    f"{event['hero']} slew a {event['enemy']}! (+{event['gold']}g, +{event['xp']}xp)",
                    (255, 215, 0),
                )
                # WK131: seeded loot roll for the killer (bosses always drop
                # rare+; regular enemies small common-drop chance). The drop
                # goes straight to the killer's inventory: auto-equip if
                # better, else backpack (carried for selling).
                try:
                    killer = next(
                        (h for h in self.heroes if getattr(h, "name", None) == event.get("hero")),
                        None,
                    )
                    if killer is not None:
                        item = self.loot_system.roll_enemy_drop(str(event.get("enemy", "")))
                        if item is not None:
                            outcome = self.loot_system.grant_item(killer, item)
                            if outcome != "dropped":
                                verb = "equipped" if outcome == "equipped" else "picked up"
                                self._emit_hud_message(
                                    f"{event['hero']} {verb} {item.name}!",
                                    (170, 220, 255),
                                )
                except Exception:
                    pass
                # WK126-T7 (slay_enemy_type): kill-counter progress for the
                # ACCEPTING hero. Gated on quests existing — a complete no-op in
                # the WK67 digest scenario (no quests, and no enemies anyway).
                # getattr: this method is also driven unbound against duck-typed
                # stubs without a quest_system (tests/test_wk131_items.py).
                _quest_system = getattr(self, "quest_system", None)
                if _quest_system is not None and _quest_system.quests:
                    killer = next(
                        (h for h in self.heroes if getattr(h, "name", None) == event.get("hero")),
                        None,
                    )
                    _quest_system.on_enemy_killed(
                        str(event.get("enemy", "")), killer, self.event_bus
                    )
            elif event.get("type") == GameEventType.CASTLE_DESTROYED.value:
                self._emit_hud_message("GAME OVER - Castle Destroyed!", (255, 0, 0))
            elif event.get("type") == GameEventType.LAIR_CLEARED.value:
                lair_name = event.get("lair_type", "lair").replace("_", " ").title()
                gold = event.get("gold", 0)
                hero_name = event.get("hero", "A hero")
                self._emit_hud_message(f"{hero_name} cleared {lair_name}! (+{gold}g)", (255, 215, 0))
                lair_obj = event.get("lair_obj")

                bounty_claimed_events = []
                try:
                    hero_obj = next((h for h in self.heroes if getattr(h, "name", None) == hero_name), None)
                    if hero_obj is not None and lair_obj is not None:
                        for b in list(getattr(self.bounty_system, "bounties", []) or []):
                            if getattr(b, "claimed", False):
                                continue
                            if getattr(b, "bounty_type", None) != BountyType.ATTACK_LAIR.value:
                                continue
                            if getattr(b, "target", None) is lair_obj:
                                if b.claim(hero_obj):
                                    bounty_claimed_events.append(
                                        {
                                            "type": GameEventType.BOUNTY_CLAIMED.value,
                                            "x": float(b.x),
                                            "y": float(b.y),
                                            "reward": b.reward,
                                            "hero": hero_name,
                                            "hero_id": str(getattr(hero_obj, "hero_id", "") or ""),
                                        }
                                    )
                except Exception:
                    pass

                if bounty_claimed_events:
                    self.event_bus.emit_batch(bounty_claimed_events)

                # WK126-T7 (raid_lair): complete accepted quests targeting this
                # lair (mirrors the attack_lair bounty match above). Gated on
                # quests existing — a complete no-op in the WK67 digest scenario.
                # getattr mirrors the ENEMY_KILLED hook (unbound stub callers).
                _quest_system = getattr(self, "quest_system", None)
                if _quest_system is not None and _quest_system.quests:
                    _quest_system.on_lair_cleared(lair_obj, self.heroes, self.event_bus)

                if lair_obj in self.buildings:
                    self.buildings.remove(lair_obj)
                if lair_obj in getattr(self.lair_system, "lairs", []):
                    self.lair_system.lairs.remove(lair_obj)

    def _maybe_apply_early_pacing_nudge(self, dt: float, castle) -> None:
        from game.sim import early_pacing
        early_pacing.maybe_apply_early_pacing_nudge(self, dt, castle)

    def _nearest_lair_to(self, x: float, y: float):
        from game.sim import early_pacing
        return early_pacing.nearest_lair_to(self, x, y)

    def _update_fog_of_war(self) -> None:
        from game.sim import fog
        fog.update_fog_of_war(self)

