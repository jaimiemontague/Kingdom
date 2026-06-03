"""
Hero entity with stats, inventory, and AI state machine.
"""
import math
from enum import Enum, auto
from typing import TYPE_CHECKING
from game.systems.buffs import Buff
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms
from game.sim.contracts import HeroDecisionRecord  # type hint for Hero.last_decision (set in __init__)
from game.sim.hero_profile import HeroMemoryEntry, KnownPlaceSnapshot  # type hints in __init__
from config import (
    TILE_SIZE, HERO_BASE_HP, HERO_BASE_ATTACK, HERO_BASE_DEFENSE,
    HERO_SPEED, COLOR_BLUE, HUNGER_INTERVAL_MS,
    WIZARD_ATTACK_RANGE_TILES, WIZARD_SPELL_COLOR, WIZARD_SPELL_SIZE_PX,
)
from game.sim.hero_guardrails_tunables import PATH_REPLAN_MIN_INTERVAL_MS

if TYPE_CHECKING:
    from game.entities.buildings.base import Building


class HeroState(Enum):
    IDLE = auto()
    MOVING = auto()
    FIGHTING = auto()
    SHOPPING = auto()
    RETREATING = auto()
    RESTING = auto()
    DEAD = auto()


# Random hero names
HERO_NAMES = [
    "Brock", "Aria", "Theron", "Lyra", "Gareth", "Mira", "Roland", "Elara",
    "Cedric", "Kira", "Magnus", "Freya", "Aldric", "Seraphina", "Dante", "Nova"
]

_fallback_hero_seq = 0


def _allocate_fallback_hero_id() -> str:
    """Monotonic id when caller did not supply ``hero_id`` (deterministic spawn order)."""
    global _fallback_hero_seq
    _fallback_hero_seq += 1
    return f"h{_fallback_hero_seq:08d}"


# WK71: behavior clusters extracted into MRO-identical mixins. Imported AFTER
# ``HeroState`` is defined above so the mixin modules (which import HeroState
# from this module at load time) resolve without a circular-import error.
from game.entities.hero_rest import HeroRestMixin
from game.entities.hero_economy import HeroEconomyMixin
from game.entities.hero_memory import HeroMemoryMixin


class Hero(HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin):
    """A hero unit controlled by basic AI + LLM decisions."""
    
    def __init__(
        self,
        x: float,
        y: float,
        hero_class: str = "warrior",
        *,
        hero_id: str | None = None,
        name: str | None = None,
    ):
        self.x = x
        self.y = y
        self.hero_class = hero_class
        # Stable profile identity (never ``id(self)``); optional explicit id from engine/tests.
        hid = str(hero_id).strip() if hero_id is not None else ""
        self.hero_id = hid if hid else _allocate_fallback_hero_id()
        # Deterministic (seeded) identity when determinism is enabled.
        if name is not None:
            self.name = str(name)
        else:
            self.name = get_rng().choice(HERO_NAMES)

        self._event_bus: object | None = None  # WK52: set by engine after spawn

        # Stats
        self.level = 1
        self.xp = 0
        self.xp_to_level = 100
        self.hp = HERO_BASE_HP
        self.max_hp = HERO_BASE_HP
        self.base_attack = HERO_BASE_ATTACK
        self.base_defense = HERO_BASE_DEFENSE
        self.speed = HERO_SPEED
        
        # Resources
        self.gold = 0  # Spendable gold
        self.taxed_gold = 0  # Gold reserved for taxes (25% of earnings)

        # Buffs / auras (temporary stat modifiers)
        self.buffs = []  # list[Buff]
        
        # Home building reference (set when hired)
        self.home_building = None
        
        # Healing/rest tracking
        self.hp_when_left_home = self.max_hp  # Track HP when leaving home
        self.hp_healed_this_rest = 0  # Track how much healed during current rest
        self.last_heal_time = 0  # For timing heal ticks
        self.damage_since_left_home = 0  # Track damage taken since leaving
        
        # Inventory
        self.weapon = None  # {"name": str, "attack": int}
        self.armor = None   # {"name": str, "defense": int}
        self.potions = 0
        self.max_potions = 5  # Can carry up to 5 potions
        self.potion_heal_amount = 50
        # Shopping / purchase tracking (sim-time)
        self.last_purchase_ms: int | None = None
        self.last_purchase_type: str = ""
        
        # AI State
        self.state = HeroState.IDLE
        self.target = None  # Could be position tuple, enemy, or building
        self.target_position = None
        self.path = []
        # Grid tile (gx, gy) we last planned A* toward — avoids replanning every tick on sub-tile float jitter.
        self._path_goal: tuple[int, int] | None = None
        self._path_last_replan_ms: int = 0
        
        # Combat
        self.attack_cooldown = 0
        self.attack_cooldown_max = 1000  # ms between attacks
        # WK5 Hotfix: Rangers have proper ranged attack range (5-7 tiles, using 6 tiles)
        if self.hero_class == "ranger":
            self.attack_range = TILE_SIZE * 6  # 6 tiles = 192 pixels at 32px/tile
        elif self.hero_class == "wizard":
            # WK124-T3a: wizard casts spells at stand-off range (wizard-gated;
            # ranger/cleric/warrior values unchanged).
            self.attack_range = TILE_SIZE * WIZARD_ATTACK_RANGE_TILES
        else:
            self.attack_range = TILE_SIZE * 1.5  # Melee range for other classes

        # WK124-T4a: per-cleric heal cooldown (sim-ms). Inert for non-clerics; not
        # part of the WK67 AI-decision digest (which hashes only x,y,state,intent,
        # target-type,gold).
        self._heal_cooldown_until_ms = 0

        # LLM decision tracking
        self.last_llm_decision_time = 0
        self.pending_llm_decision = False
        self.last_llm_action = None
        # WK18: Physical hook — when set by behavior, engine applies to state (move_to).
        self.llm_move_request: tuple[float, float] | None = None

        # Intent + last decision snapshot (for UI/debug/QA).
        # Keep this data simple for future determinism/networking friendliness.
        self.intent = "idle"  # intent taxonomy label
        self.last_decision = None  # {"action","reason","at_ms","inputs_summary","source","intent"}
        self.personality = get_rng().choice([
            "brave and aggressive",
            "cautious and strategic", 
            "greedy but cowardly",
            "balanced and reliable"
        ])

        # Thin, UI/AI-facing "why did you do that?" records.
        # Kept small and deterministic-friendly (sim time only).
        self.intent: str = "idle"
        self.last_decision: HeroDecisionRecord | None = None
        self._intent_prev_key: tuple | None = None
        
        # WK57: Layer tracking (0 = surface, -1 = underground)
        self.layer = 0
        # WK57 Wave 5: Underground area tracking
        self.underground_area_id: str | None = None  # which area hero is in
        self.underground_local_x: int = 0  # position in area local coords
        self.underground_local_z: int = 0

        # Visual
        self.size = 20
        self.color = COLOR_BLUE
        self._render_anim_trigger: str | None = None
        self._anim_trigger_seq: int = 0  # WK66 Move 1a: monotonic one-shot trigger counter

        # Building interaction
        self.is_inside_building = False
        self.inside_building = None
        self.inside_timer = 0.0  # for short non-rest "enter" moments (e.g. shopping)
        self.pending_task: str | None = None
        self.pending_task_building: Building | None = None
        self._rest_heal_progress = 0.0

        # WK61-R10: hero hunger — meal cadence for food-stand economy loop (Agent 06 drives AI).
        self.next_meal_due_ms: int = int(sim_now_ms()) + int(HUNGER_INTERVAL_MS)

        # -----------------------------
        # WK2 contracts: combat gating + stuck signals (Hero-owned, UI-readable)
        # -----------------------------
        self.can_attack: bool = True
        self.attack_blocked_reason: str = ""

        self.stuck_active: bool = False
        self.stuck_since_ms: int | None = None
        self.last_progress_ms: int = int(sim_now_ms())
        self.last_progress_pos: tuple[float, float] = (float(self.x), float(self.y))
        self.unstuck_attempts: int = 0
        self.stuck_reason: str = ""
        # Internal bookkeeping for backoff/caps (not a public contract)
        self._last_unstuck_attempt_ms: int = 0
        self._unstuck_attempts_for_target: int = 0
        self._unstuck_target_key: tuple | None = None

        # WK5: Ranged attacker interface.
        # WK124-T3a: wizard is also a ranged attacker (casts a magic projectile);
        # ranger keeps its existing arrow visuals (see get_ranged_spec).
        self.is_ranged_attacker = self.hero_class in ("ranger", "wizard")
        
        # WK6: Per-hero revealed tile tracking (for XP awards)
        # Only used for Rangers; other classes can ignore this
        self._revealed_tiles: set[tuple[int, int]] = set()  # (grid_x, grid_y) tuples
        
        # Anti-oscillation commitment windows (sim-time based; controlled by AI)
        self._target_commit_until_ms: int = 0
        self._bounty_commit_until_ms: int = 0

        # WK49: Bounded profile memory + known places + career counters (mutable sim state).
        self._next_profile_memory_entry_id: int = 1
        self.profile_memory: list[HeroMemoryEntry] = []
        self.known_places: dict[str, KnownPlaceSnapshot] = {}
        # WK123 perf: monotonically bumped whenever profile_memory / known_places mutate
        # (add / update / evict). build_hero_profile_snapshot caches the sorted-tuple work
        # (the per-frame sort over <=100 places + <=30 memories) keyed on this version, so a
        # hero whose memory hasn't changed this frame reuses the prior sorted tuples instead
        # of re-sorting. Volatile fields (hp/xp/state/intent/location) still rebuild every
        # frame, so the emitted HeroProfileSnapshot is byte-identical to the uncached path.
        self._profile_memory_version: int = 0
        self.profile_career: dict[str, int] = {
            "tiles_revealed": 0,
            "places_discovered": 0,
            "enemies_defeated": 0,
            "bounties_claimed": 0,
            "gold_earned": 0,
            "purchases_made": 0,
        }

    def set_event_bus(self, event_bus) -> None:
        """Wire the sim event bus so level-up can emit HERO_LEVEL_UP (WK52)."""
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # WK57 Wave 5: Underground transition methods
    # ------------------------------------------------------------------

    def begin_descent(self, area_id: str, entrance_x: int, entrance_y: int):
        """Start descending into an underground area."""
        self.layer = -1
        self.underground_area_id = area_id
        # Place hero at entrance chamber (local coords: center_x, z=0)
        self.underground_local_x = 0
        self.underground_local_z = 0

    def begin_ascent(self):
        """Start ascending back to surface."""
        self.layer = 0
        self.underground_area_id = None
        self.underground_local_x = 0
        self.underground_local_z = 0

    @property
    def attack(self) -> int:
        """Total attack including weapon bonus."""
        now_ms_val = sim_now_ms()
        weapon_bonus = self.weapon.get("attack", 0) if self.weapon else 0
        buff_bonus = 0
        for b in getattr(self, "buffs", []):
            if getattr(b, "expires_at_ms", 0) > now_ms_val:
                buff_bonus += int(getattr(b, "atk_delta", 0))
        return self.base_attack + weapon_bonus + buff_bonus + (self.level - 1) * 2
    
    @property
    def defense(self) -> int:
        """Total defense including armor bonus."""
        now_ms_val = sim_now_ms()
        armor_bonus = self.armor.get("defense", 0) if self.armor else 0
        buff_bonus = 0
        for b in getattr(self, "buffs", []):
            if getattr(b, "expires_at_ms", 0) > now_ms_val:
                buff_bonus += int(getattr(b, "def_delta", 0))
        return self.base_defense + armor_bonus + buff_bonus + (self.level - 1)

    def apply_or_refresh_buff(
        self,
        name: str,
        atk_delta: int = 0,
        def_delta: int = 0,
        duration_s: float = 1.0,
        now_ms: int | None = None,
    ):
        """Apply a buff by name, or refresh its duration if already present (prevents stacking drift)."""
        if now_ms is None:
            now_ms = sim_now_ms()
        expires_at_ms = int(now_ms + max(0.0, float(duration_s)) * 1000.0)

        # Refresh existing buff if present.
        for b in self.buffs:
            if getattr(b, "name", None) == name:
                b.atk_delta = int(atk_delta)
                b.def_delta = int(def_delta)
                b.expires_at_ms = expires_at_ms
                return

        self.buffs.append(
            Buff(
                name=str(name),
                atk_delta=int(atk_delta),
                def_delta=int(def_delta),
                expires_at_ms=expires_at_ms,
            )
        )

    def remove_expired_buffs(self, now_ms: int | None = None):
        if now_ms is None:
            now_ms = sim_now_ms()
        self.buffs = [b for b in self.buffs if not b.is_expired(now_ms)]
    
    @property
    def is_alive(self) -> bool:
        return self.hp > 0
    
    @property
    def health_percent(self) -> float:
        return self.hp / self.max_hp

    @property
    def render_state(self) -> "Hero":
        """Render accessor used by render-side systems."""
        return self
    
    def take_damage(self, amount: int) -> bool:
        """Take damage, returns True if killed."""
        actual_damage = max(1, amount - self.defense)
        self.hp = max(0, self.hp - actual_damage)
        self.damage_since_left_home += actual_damage
        # Hurt "one-shot" animation (if still alive)
        if self.hp > 0:
            self._queue_render_animation("hurt")
        if self.hp <= 0:
            self.state = HeroState.DEAD
            self.intent = "idle"
            try:
                self.record_decision(action="dead", reason="killed in combat")
            except Exception:
                pass
            return True
        return False

    def heal(self, amount: int):
        """Heal the hero."""
        self.hp = min(self.max_hp, self.hp + amount)

    def add_xp(self, amount: int):
        """Add experience points, level up if enough."""
        self.xp += amount
        while self.xp >= self.xp_to_level:
            self.xp -= self.xp_to_level
            self.level_up()

    def grant_tile_exploration_xp(self, tiles: int = 1) -> None:
        """XP for revealing overworld tiles (ranger fog). Must route through level-ups."""
        n = int(tiles)
        if n <= 0:
            return
        self.add_xp(n)

    def level_up(self):
        """Level up the hero."""
        self.level += 1
        self.max_hp += 20
        self.hp = self.max_hp  # Full heal on level up
        self.xp_to_level = int(self.xp_to_level * 1.5)
        if self._event_bus is not None:
            try:
                from game.events import GameEventType

                self._event_bus.emit(
                    {
                        "type": GameEventType.HERO_LEVEL_UP.value,
                        "hero_id": str(self.hero_id),
                        "hero_name": str(self.name),
                        "new_level": int(self.level),
                    }
                )
            except Exception:
                pass
    
    @property
    def hunger_urgent(self) -> bool:
        """True when sim time has reached the next meal deadline."""
        return int(sim_now_ms()) >= int(self.next_meal_due_ms)

    def set_target_position(self, x: float, y: float):
        """Set a position to move towards."""
        self.target_position = (x, y)
        self.state = HeroState.MOVING
    
    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance to a point."""
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)
    
    def move_towards(self, target_x: float, target_y: float, dt: float):
        """Move towards a target position."""
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist > 0:
            # Normalize and apply speed
            move_dist = self.speed * dt
            if move_dist >= dist:
                self.x = target_x
                self.y = target_y
            else:
                self.x += (dx / dist) * move_dist
                self.y += (dy / dist) * move_dist
    
    def update(self, dt: float, game_state: dict):
        """Update hero state and behavior."""
        if not self.is_alive:
            self.intent = "idle"
            return

        # Keep intent/decision data fresh even when AI is disabled (best-effort, non-blocking).
        try:
            self._update_intent_and_decision(game_state)
        except Exception:
            pass

        # Combat gating: source of truth for Build A is inside-building state.
        # Combat system must treat can_attack=False as a hard gate (no damage/events).
        if getattr(self, "is_inside_building", False):
            self.can_attack = False
            self.attack_blocked_reason = "inside_building"
        else:
            self.can_attack = True
            self.attack_blocked_reason = ""

        # Handle brief "inside building" timer (shopping etc.)
        if self.is_inside_building and self.state != HeroState.RESTING and self.inside_timer > 0:
            # WK18-FEAT-002: Inn loiter fee and eject when broke
            inn = self.inside_building
            if getattr(inn, "building_type", None) == "inn":
                from config import INN_LOITER_FEE_GOLD_PER_SEC
                deduct = max(0.0, float(INN_LOITER_FEE_GOLD_PER_SEC)) * dt
                if deduct > 0 and getattr(self, "gold", 0) > 0:
                    accum = getattr(self, "_loiter_fee_accum", 0.0) + deduct
                    if accum >= 1.0:
                        drop = int(accum)
                        self.gold = max(0, self.gold - drop)
                        self._loiter_fee_accum = accum - drop
                    else:
                        self._loiter_fee_accum = accum
                if getattr(self, "gold", 0) < 1:
                    self.pop_out_of_building()
                    return
            self.inside_timer = max(0.0, self.inside_timer - dt)
            if self.inside_timer <= 0:
                self.pop_out_of_building()
        
        # Update attack cooldown
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt * 1000
        
        # State machine transitions are handled by `ai/basic_ai.py`.
        # This method only performs movement (now with pathfinding around buildings).
        # Note: RETREATING still moves towards a target_position, so treat it like MOVING here.
        if self.state in (HeroState.MOVING, HeroState.RETREATING) and self.target_position and not self.is_inside_building:
            world = game_state.get("world")
            buildings = game_state.get("buildings", [])
            if world:
                from game.systems.navigation import compute_path_worldpoints, follow_path, best_adjacent_tile
                from game.world import Visibility

                goal_x, goal_y = self.target_position
                
                # WK6: Fog bounty pathing - use direct steering for long-distance black-fog targets
                # (matches enemy AI pattern for consistency)
                dist = self.distance_to(goal_x, goal_y)
                goal_grid_x, goal_grid_y = world.world_to_grid(goal_x, goal_y)
                goal_in_black_fog = False

                # Check if goal is in black fog (UNSEEN)
                if (0 <= goal_grid_x < world.width and 0 <= goal_grid_y < world.height):
                    goal_visibility = world.visibility[goal_grid_y][goal_grid_x]
                    goal_in_black_fog = (goal_visibility == Visibility.UNSEEN)

                # Use direct steering for far-away targets (avoids expensive A* on large maps).
                # WK59 perf: also use direct steering for long revealed-terrain paths (>20 tiles).
                if dist > TILE_SIZE * 20 or (goal_in_black_fog and dist > TILE_SIZE * 12):
                    self.move_towards(goal_x, goal_y, dt)
                    return

                # Replan when we have no path or the *destination tile* changed (not every float nudge).
                goal_gx, goal_gy = world.world_to_grid(goal_x, goal_y)
                goal_key = (goal_gx, goal_gy)
                path_empty = not self.path
                goal_changed = self._path_goal != goal_key
                need_replan = path_empty or goal_changed

                # WK59 perf: apply rate limit to ALL replans (not just goal-changed).
                # Prevents heroes with failed paths from spamming A* every tick.
                if need_replan:
                    now_ms = int(sim_now_ms())
                    last = int(getattr(self, "_path_last_replan_ms", 0) or 0)
                    # Stagger offset: each hero has a different effective cooldown phase
                    # to spread 30 heroes across a 200ms window instead of all replanning
                    # at the same boundary. Uses stable hero_id via crc32 (determinism-safe).
                    stagger = getattr(self, "_path_stagger_offset_ms", None)
                    if stagger is None:
                        import zlib
                        self._path_stagger_offset_ms = (zlib.crc32(self.hero_id.encode()) % 6) * 40  # 0-200ms spread
                        stagger = self._path_stagger_offset_ms
                    effective_interval = int(PATH_REPLAN_MIN_INTERVAL_MS) + stagger
                    if (now_ms - last) < effective_interval:
                        need_replan = False

                if need_replan:
                    _new_path = compute_path_worldpoints(
                        world, buildings, self.x, self.y, goal_x, goal_y
                    )
                    if _new_path is not None:
                        self.path = _new_path
                        self._path_goal = goal_key
                        self._path_last_replan_ms = int(sim_now_ms())
                    elif not self.path:
                        # WK64 A2.1: budget DEFERRED and we have NO path to follow.
                        # Do NOT stall -- direct-steer toward the goal this frame (the
                        # same fallback the far-target/black-fog branch above uses, and
                        # that guard.py/tax_collector.py already use). A precise A* path
                        # is acquired on a later frame once budget frees up. This prevents
                        # first-path starvation under heavy entity load (30+ heroes) from
                        # registering as a stuck unit. Do NOT stamp _path_last_replan_ms.
                        self.move_towards(goal_x, goal_y, dt)
                        return
                    # else: budget DEFERRED but we still have a path -- keep following it
                    # and retry the replan next frame. Do NOT stamp _path_last_replan_ms
                    # (so the replan is re-attempted ASAP rather than rate-limited 200ms+).

                follow_path(self, dt)
            else:
                self.move_towards(self.target_position[0], self.target_position[1], dt)

    def _queue_render_animation(self, name: str) -> None:
        """Queue a one-shot render animation to be consumed by the renderer."""
        self._render_anim_trigger = str(name)
        # WK66 Move 1a: sim-owned monotonic counter so the renderer can detect a
        # new trigger without writing back (setattr-clear) onto this entity.
        self._anim_trigger_seq = int(getattr(self, "_anim_trigger_seq", 0)) + 1

    def on_attack_landed(self, target, damage: int, killed: bool):
        """Called by CombatSystem when this hero lands an attack."""
        if killed and getattr(target, "enemy_type", None) is not None:
            self.increment_career_stat("enemies_defeated", 1)
        _ = damage
        self._queue_render_animation("attack")

    def get_ranged_spec(self):
        """Projectile metadata for ranged attackers (consumed by CombatSystem).

        WK124-T3a: the WIZARD gets a ``kind: "magic"`` arcane projectile spec.
        Every OTHER class returns ``None`` — combat.py reads this only when
        ``is_ranged_attacker`` and treats ``None`` as "use the default arrow
        spec" (``(spec or {}).get(...)`` → kind "arrow"). The real ``Hero`` had
        no ``get_ranged_spec`` before this sprint, so for the ranger this is
        byte-identical to its prior behavior (the same arrow defaults). Do NOT
        return a non-None spec for non-wizards — that would change the ranger.
        """
        if self.hero_class == "wizard":
            return {
                "kind": "magic",
                "color": WIZARD_SPELL_COLOR,
                "size_px": WIZARD_SPELL_SIZE_PX,
            }
        return None
