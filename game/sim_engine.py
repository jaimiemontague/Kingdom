"""
SimEngine: pure simulation core (no UI/camera/display/audio/VFX).

Stage 2 refactor: split the former GameEngine "god object" into:
- SimEngine (this file): owns world + event bus + entities + systems + sim-owned state.
- PresentationLayer (still in game/engine.py for now): owns pygame init, camera, UI, rendering, audio, VFX.
"""

from __future__ import annotations

from game.world import World
from game.events import EventBus, GameEventType
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_time_multiplier
from game.sim.timebase import set_sim_now_ms, get_time_multiplier

from config import (
    EARLY_PACING_NUDGE_MODE,
    SIM_SEED,
    DEFAULT_SPEED_TIER,
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
)

from game.entities import Castle, Hero, TaxCollector, Peasant, Guard


class SimEngine:
    """
    Headless simulation core.

    This class must not depend on pygame UI concepts (camera, window, panels).
    """

    def __init__(self, early_nudge_mode: str | None = None):
        # Determinism knobs (future multiplayer enablement).
        # Seed early so world gen + initial lairs are reproducible when enabled.
        set_sim_seed(SIM_SEED)
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
        self.heroes = []
        self.enemies = []
        self.bounties = []
        self.peasants = []
        self.guards = []
        self.peasant_spawn_timer = 0.0

        # Systems (sim-owned)
        self.combat_system = CombatSystem()
        self.economy = EconomySystem()
        self.spawner = EnemySpawner(self.world)
        self.lair_system = LairSystem(self.world)
        self.neutral_building_system = NeutralBuildingSystem(self.world)
        self.buff_system = BuffSystem()
        self.building_factory = BuildingFactory()
        self.bounty_system = BountySystem()

        # Selection (sim-owned: used by coordinate queries + gameplay)
        self.selected_building = None
        self.selected_peasant = None
        self.selected_hero = None

        # AI controller (wired by main.py / UrsinaApp)
        self.ai_controller = None

        # Tax collector (created after castle is placed)
        self.tax_collector = None

        # Fog-of-war dirty check state (Ursina consumes via snapshot.fog_revision)
        self._fog_revision = 0
        self._fog_revealers_snapshot = None

    def _emit_hud_message(self, text: str, color_rgb: tuple[int, int, int] | None = None) -> None:
        self.event_bus.emit(
            {
                "type": GameEventType.HUD_MESSAGE.value,
                "text": str(text),
                "color": tuple(color_rgb or (255, 255, 255)),
            }
        )

    def setup_initial_state(self) -> None:
        """Set up initial sim state (no camera/UI side effects)."""
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

        self.lair_system.spawn_initial_lairs(self.buildings, castle)
        self._update_fog_of_war()

    def _build_system_context(self) -> SystemContext:
        return SystemContext(
            heroes=self.heroes,
            enemies=self.enemies,
            buildings=self.buildings,
            world=self.world,
            economy=self.economy,
            event_bus=self.event_bus,
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
            "selected_hero": self.selected_hero,
            "selected_building": getattr(self, "selected_building", None),
            "selected_peasant": getattr(self, "selected_peasant", None),
            "castle": castle,
            "economy": self.economy,
            "world": self.world,
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

    def build_snapshot(
        self,
        *,
        vfx_projectiles: tuple,
        screen_w: int,
        screen_h: int,
        camera_x: float,
        camera_y: float,
        zoom: float,
        default_zoom: float,
        paused: bool,
        running: bool,
        pause_menu_visible: bool,
    ):
        from game.sim.snapshot import SimStateSnapshot

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
        return SimStateSnapshot(
            buildings=tuple(self.buildings),
            heroes=tuple(self.heroes),
            enemies=tuple(self.enemies),
            peasants=tuple(self.peasants),
            guards=tuple(self.guards),
            bounties=tuple(self.bounty_system.get_unclaimed_bounties()),
            world=self.world,
            fog_revision=int(getattr(self, "_fog_revision", 0)),
            gold=int(getattr(self.economy, "player_gold", 0)),
            wave=int(getattr(self.spawner, "wave_number", 0)),
            buildings_construction_progress=tuple(
                float(getattr(b, "construction_progress", 1.0)) for b in self.buildings
            ),
            selected_hero=self.selected_hero,
            selected_building=getattr(self, "selected_building", None),
            castle=castle,
            tax_collector=getattr(self, "tax_collector", None),
            vfx_projectiles=tuple(vfx_projectiles or ()),
            screen_w=int(screen_w),
            screen_h=int(screen_h),
            camera_x=float(camera_x),
            camera_y=float(camera_y),
            zoom=float(zoom) if zoom else 1.0,
            default_zoom=float(default_zoom) if default_zoom else 1.0,
            paused=bool(paused),
            running=bool(running),
            pause_menu_visible=bool(pause_menu_visible),
        )

    def update(self, dt: float, game_state: dict) -> None:
        """Core sim update loop (no UI/render/vfx)."""
        # Deterministic sim-time accounting
        if DETERMINISTIC_SIM:
            self._sim_now_ms += int(round(float(dt) * 1000.0))
            set_sim_now_ms(self._sim_now_ms)
        else:
            set_sim_now_ms(None)

        # Ensure all buildings have event bus for interior enter/exit events.
        for building in self.buildings:
            if getattr(building, "_event_bus", None) is None and hasattr(building, "set_event_bus"):
                building.set_event_bus(self.event_bus)

        system_ctx = self._build_system_context()

        # AI + hero updates
        if self.ai_controller:
            self.ai_controller.update(dt, self.heroes, game_state)

        from game.entities.hero import HeroState
        for hero in self.heroes:
            if getattr(hero, "llm_move_request", None) is not None:
                wx, wy = hero.llm_move_request
                hero.set_target_position(wx, wy)
                hero.llm_move_request = None
        for hero in self.heroes:
            hero.update(dt, game_state)

        # Fog + buffs + early pacing (castle from game_state)
        self._update_fog_of_war()
        self.buff_system.update(system_ctx, dt)
        castle = game_state.get("castle")
        self._maybe_apply_early_pacing_nudge(dt, castle)

        # Peasants
        self.peasant_spawn_timer += dt
        alive_peasants = [p for p in self.peasants if getattr(p, "is_alive", False)]
        if castle and len(alive_peasants) < 2 and self.peasant_spawn_timer >= 5.0:
            self.peasant_spawn_timer = 0.0
            self.peasants.append(Peasant(castle.center_x, castle.center_y))
        for peasant in self.peasants:
            peasant.update(dt, game_state)

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

        # Separation (copied from engine; sim-owned)
        self._apply_entity_separation(dt)

        # Combat
        self.combat_system.update(system_ctx, dt)
        if enemy_ranged_events:
            self.event_bus.emit_batch(enemy_ranged_events)
        events = self.combat_system.get_emitted_events()
        self._route_combat_events(events)

        # Cleanup
        self.enemies = [e for e in self.enemies if getattr(e, "is_alive", False)]
        self.guards = [g for g in self.guards if getattr(g, "is_alive", False)]

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
                }
            )
        if bounty_claimed_events:
            self.event_bus.emit_batch(bounty_claimed_events)
        self.bounty_system.cleanup()

        # Neutral systems
        self.neutral_building_system.tick(dt, self.buildings, self.heroes, castle)
        if self.tax_collector:
            self.tax_collector.update(dt, self.buildings, self.economy, world=self.world)

        # Buildings
        self._update_buildings(dt)

    # --- Below are sim helpers copied/adapted from engine.py ---
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
            elif building.building_type == "ballista_tower" and hasattr(building, "update"):
                building.update(dt, self.enemies)
            elif building.building_type == "wizard_tower" and hasattr(building, "update"):
                building.update(dt, self.enemies)
            elif building.building_type == "fairgrounds" and hasattr(building, "update"):
                building.update(dt, self.economy, self.heroes)
            elif building.building_type == "guardhouse" and hasattr(building, "update"):
                should_spawn = building.update(dt, [g for g in self.guards if g.home_building == building])
                if should_spawn:
                    g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                    self.guards.append(g)
                    if hasattr(building, "guards_spawned"):
                        building.guards_spawned += 1
            elif building.building_type == "palace":
                max_guards = getattr(building, "max_palace_guards", 0)
                if max_guards > 0 and getattr(building, "is_constructed", True):
                    current = len([g for g in self.guards if g.home_building == building])
                    if current < max_guards:
                        g = Guard(building.center_x + TILE_SIZE, building.center_y, home_building=building)
                        self.guards.append(g)

        for building in self.buildings:
            if hasattr(building, "_last_ranged_event") and building._last_ranged_event is not None:
                building_ranged_events.append(building._last_ranged_event)
                building._last_ranged_event = None
        if building_ranged_events:
            self.event_bus.emit_batch(building_ranged_events)

    def _apply_entity_separation(self, dt: float) -> None:
        import math

        min_dist_px = 16.0
        strength_per_sec = 250.0
        max_step = 120.0 * dt
        cell = min_dist_px

        alive = []
        for lst in (self.heroes, self.enemies, self.peasants, self.guards):
            alive.extend(e for e in lst if getattr(e, "is_alive", True))
        if self.tax_collector and getattr(self.tax_collector, "is_alive", True):
            alive.append(self.tax_collector)
        if len(alive) < 2:
            return

        grid: dict[tuple[int, int], list[int]] = {}
        for idx, ent in enumerate(alive):
            if getattr(ent, "is_inside_building", False):
                continue
            cx = int(ent.x // cell)
            cy = int(ent.y // cell)
            key = (cx, cy)
            bucket = grid.get(key)
            if bucket is None:
                grid[key] = [idx]
            else:
                bucket.append(idx)

        for key, indices in grid.items():
            kx, ky = key
            neighbours: list[int] = []
            for ox in range(kx - 1, kx + 2):
                for oy in range(ky - 1, ky + 2):
                    nb = grid.get((ox, oy))
                    if nb is not None:
                        neighbours.extend(nb)

            for i in indices:
                ent = alive[i]
                dx_sum, dy_sum = 0.0, 0.0
                ex, ey = ent.x, ent.y
                for j in neighbours:
                    if j == i:
                        continue
                    other = alive[j]
                    dx = ex - other.x
                    dy = ey - other.y
                    d2 = dx * dx + dy * dy
                    if d2 < min_dist_px * min_dist_px and d2 > 1e-12:
                        dist = math.sqrt(d2)
                        push = (min_dist_px - dist) * strength_per_sec * dt / dist
                        dx_sum += dx * push
                        dy_sum += dy * push
                if dx_sum != 0 or dy_sum != 0:
                    step = math.sqrt(dx_sum * dx_sum + dy_sum * dy_sum)
                    if step > max_step:
                        scale = max_step / step
                        dx_sum *= scale
                        dy_sum *= scale
                    ent.x += dx_sum
                    ent.y += dy_sum

    def _route_combat_events(self, events: list) -> None:
        for event in events:
            if event.get("type") == GameEventType.ENEMY_KILLED.value:
                self._emit_hud_message(
                    f"{event['hero']} slew a {event['enemy']}! (+{event['gold']}g, +{event['xp']}xp)",
                    (255, 215, 0),
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
                                        }
                                    )
                except Exception:
                    pass

                if bounty_claimed_events:
                    self.event_bus.emit_batch(bounty_claimed_events)

                if lair_obj in self.buildings:
                    self.buildings.remove(lair_obj)
                if lair_obj in getattr(self.lair_system, "lairs", []):
                    self.lair_system.lairs.remove(lair_obj)

    def _maybe_apply_early_pacing_nudge(self, dt: float, castle) -> None:
        if not castle:
            return
        mode = getattr(self, "_early_nudge_mode", "auto")
        if mode == "off":
            return
        if mode not in ("auto", "force"):
            mode = "auto"
        self._early_nudge_elapsed_s += float(dt)

        unclaimed = self.bounty_system.get_unclaimed_bounties()
        has_any_bounty = bool(unclaimed)
        tip_time_s = 0.0 if mode == "force" else 35.0
        starter_time_s = 0.0 if mode == "force" else 90.0

        if (not self._early_nudge_tip_shown) and (self._early_nudge_elapsed_s >= tip_time_s) and (not has_any_bounty):
            self._early_nudge_tip_shown = True
            self._emit_hud_message("Tip: Press B to place a bounty and guide heroes.", (220, 220, 255))
            self._emit_hud_message("Try targeting a lair for big stash payouts.", (220, 220, 255))

        if self._early_nudge_starter_bounty_done:
            return
        if self._early_nudge_elapsed_s < starter_time_s:
            return
        if has_any_bounty:
            self._early_nudge_starter_bounty_done = True
            return

        lair = self._nearest_lair_to(float(castle.center_x), float(castle.center_y))
        if lair is None:
            self._early_nudge_starter_bounty_done = True
            return

        reward = int(LAIR_BOUNTY_COST) if LAIR_BOUNTY_COST else 75
        if not self.economy.add_bounty(reward):
            self._early_nudge_starter_bounty_done = True
            self._emit_hud_message("Tip: Earn more gold to place bounties that guide heroes.", (220, 220, 255))
            return

        bx = float(getattr(lair, "center_x", getattr(lair, "x", 0.0)))
        by = float(getattr(lair, "center_y", getattr(lair, "y", 0.0)))
        self.bounty_system.place_bounty(bx, by, reward, BountyType.ATTACK_LAIR.value, target=lair)
        self._early_nudge_starter_bounty_done = True
        self._emit_hud_message(f"Starter bounty placed: Clear the lair (+${reward})", (255, 215, 0))

    def _nearest_lair_to(self, x: float, y: float):
        best = None
        best_d2 = None
        for b in self.buildings:
            if not hasattr(b, "stash_gold"):
                continue
            bx = float(getattr(b, "center_x", getattr(b, "x", 0.0)))
            by = float(getattr(b, "center_y", getattr(b, "y", 0.0)))
            dx = bx - x
            dy = by - y
            d2 = dx * dx + dy * dy
            if best_d2 is None or d2 < best_d2:
                best = b
                best_d2 = d2
        return best

    def _update_fog_of_war(self) -> None:
        """Update fog-of-war visibility around the castle, living heroes, neutral buildings, and guards.

        WK22 Agent-10 perf fix: cache the tile-grid positions of every revealer and
        skip the expensive ``world.update_visibility`` call when no vision source has
        moved by at least one full tile since the last rebuild.

        WK34: All constructed player-placed buildings reveal 3 tiles (building LoS).
        """
        # Tunables (tile radius). Kept local to avoid cross-agent config conflicts.
        # WK17: per docs/vision_rules_fog_of_war.md (Agent 05 spec).
        CASTLE_VISION_TILES = 10
        HERO_VISION_TILES = 7
        GUARD_VISION_TILES = 6
        NEUTRAL_VISION = {"house": 3, "farm": 5, "food_stand": 3}

        castle = next((b for b in self.buildings if getattr(b, "building_type", None) == "castle"), None)
        revealers = []
        hero_revealers = []  # Track which revealers are heroes (for XP tracking)

        if castle is not None:
            revealers.append((castle.center_x, castle.center_y, CASTLE_VISION_TILES))

        for hero in self.heroes:
            if getattr(hero, "is_alive", True):
                revealers.append((hero.x, hero.y, HERO_VISION_TILES))
                hero_revealers.append((hero, hero.x, hero.y, HERO_VISION_TILES))

        # WK17: Neutral buildings (house, farm, food_stand) as vision sources.
        for building in self.buildings:
            btype = getattr(building, "building_type", None)
            if btype not in NEUTRAL_VISION:
                continue
            if getattr(building, "is_constructed", True) is not True:
                continue
            if getattr(building, "hp", 1) <= 0:
                continue
            radius = NEUTRAL_VISION[btype]
            revealers.append((building.center_x, building.center_y, radius))

        # WK34: All constructed player-placed buildings get a small LoS ring; see
        # `PLAYER_BUILDING_VISION_TILES` / `PLAYER_GUILD_EXTRA_VISION_TILES` in config.
        for building in self.buildings:
            if not getattr(building, "is_constructed", False):
                continue
            if getattr(building, "hp", 1) <= 0:
                continue
            if getattr(building, "is_neutral", False):
                continue
            # Lairs are hostile world structures, not player vision sources.
            if getattr(building, "is_lair", False) or hasattr(building, "stash_gold"):
                continue
            raw_bt = getattr(building, "building_type", None)
            btype_name = str(getattr(raw_bt, "value", raw_bt) or "")
            if btype_name == "castle":
                continue
            r = int(PLAYER_BUILDING_VISION_TILES)
            if btype_name in PLAYER_GUILD_TYPES:
                r += int(PLAYER_GUILD_EXTRA_VISION_TILES)
            revealers.append((building.center_x, building.center_y, r))

        # WK17: Living guards as vision sources.
        for guard in self.guards:
            if not getattr(guard, "is_alive", True):
                continue
            revealers.append((guard.x, guard.y, GUARD_VISION_TILES))

        if not revealers:
            return

        # ---- Dirty check: skip update if no revealer moved a full tile ----
        w2g = self.world.world_to_grid
        grid_snapshot = tuple(
            sorted((w2g(wx, wy)[0], w2g(wx, wy)[1], r) for wx, wy, r in revealers)
        )
        prev = getattr(self, "_fog_revealers_snapshot", None)
        if prev is not None and prev == grid_snapshot:
            return
        self._fog_revealers_snapshot = grid_snapshot
        self._fog_revision = getattr(self, "_fog_revision", 0) + 1

        # ---- Perform the full visibility update ----
        newly_revealed = self.world.update_visibility(revealers, return_new_reveals=True)

        # WK6: Award XP to Rangers for newly revealed tiles
        if newly_revealed:
            for hero, hx, hy, radius in hero_revealers:
                if hero.hero_class == "ranger":
                    hero_grid_x, hero_grid_y = self.world.world_to_grid(hx, hy)
                    radius_sq = radius * radius

                    for grid_x, grid_y in newly_revealed:
                        dx = grid_x - hero_grid_x
                        dy = grid_y - hero_grid_y
                        if (dx * dx + dy * dy) <= radius_sq:
                            if (grid_x, grid_y) not in hero._revealed_tiles:
                                hero._revealed_tiles.add((grid_x, grid_y))
                                hero.xp += 1

