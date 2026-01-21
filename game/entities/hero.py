"""
Hero entity with stats, inventory, and AI state machine.
"""
import pygame
import random
import math
from enum import Enum, auto
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.font_cache import get_font
from game.systems.buffs import Buff
from game.sim.determinism import get_rng
from game.sim.timebase import now_ms as sim_now_ms
from game.sim.contracts import HeroDecisionRecord, HeroIntentSnapshot
from config import (
    TILE_SIZE, HERO_BASE_HP, HERO_BASE_ATTACK, HERO_BASE_DEFENSE,
    HERO_SPEED, COLOR_BLUE, COLOR_WHITE, COLOR_GREEN, COLOR_RED
)


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


class Hero:
    """A hero unit controlled by basic AI + LLM decisions."""
    
    def __init__(self, x: float, y: float, hero_class: str = "warrior"):
        self.x = x
        self.y = y
        self.hero_class = hero_class
        # Deterministic (seeded) identity when determinism is enabled.
        self.name = get_rng().choice(HERO_NAMES)
        
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
        self._path_goal = None  # (goal_x, goal_y) we last planned towards
        
        # Combat
        self.attack_cooldown = 0
        self.attack_cooldown_max = 1000  # ms between attacks
        # WK5 Hotfix: Rangers have proper ranged attack range (5-7 tiles, using 6 tiles)
        if self.hero_class == "ranger":
            self.attack_range = TILE_SIZE * 6  # 6 tiles = 192 pixels at 32px/tile
        else:
            self.attack_range = TILE_SIZE * 1.5  # Melee range for other classes
        
        # LLM decision tracking
        self.last_llm_decision_time = 0
        self.pending_llm_decision = False
        self.last_llm_action = None

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
        
        # Visual
        self.size = 20
        self.color = COLOR_BLUE
        self.facing = 1  # 1=right, -1=left (used for mirroring sprites)
        self._last_pos = (float(self.x), float(self.y))

        # Animation
        # Uses real sprite frames if present in assets; otherwise procedural placeholder frames.
        self._anim = HeroSpriteLibrary.create_player(self.hero_class, size=32)
        self._anim_base = "idle"
        self._anim_lock_one_shot = None  # e.g. "attack" or "hurt"

        # Building interaction
        self.is_inside_building = False
        self.inside_building = None
        self.inside_timer = 0.0  # for short non-rest "enter" moments (e.g. shopping)

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

        # WK5: Ranged attacker interface
        self.is_ranged_attacker = (self.hero_class == "ranger")
        
        # WK6: Per-hero revealed tile tracking (for XP awards)
        # Only used for Rangers; other classes can ignore this
        self._revealed_tiles: set[tuple[int, int]] = set()  # (grid_x, grid_y) tuples
        
        # Anti-oscillation commitment windows (sim-time based; controlled by AI)
        self._target_commit_until_ms: int = 0
        self._bounty_commit_until_ms: int = 0
        
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
    
    def take_damage(self, amount: int) -> bool:
        """Take damage, returns True if killed."""
        actual_damage = max(1, amount - self.defense)
        self.hp = max(0, self.hp - actual_damage)
        self.damage_since_left_home += actual_damage
        # Hurt "one-shot" animation (if still alive)
        if self.hp > 0:
            self._play_one_shot("hurt")
        if self.hp <= 0:
            self.state = HeroState.DEAD
            self.intent = "idle"
            try:
                self.record_decision(action="dead", reason="killed in combat")
            except Exception:
                pass
            return True
        return False
    
    def add_gold(self, amount: int):
        """Add gold with automatic 25% tax reservation."""
        tax_amount = int(amount * 0.25)
        spendable = amount - tax_amount
        self.gold += spendable
        self.taxed_gold += tax_amount
    
    def should_go_home_to_rest(self) -> bool:
        """Check if hero should return home to rest."""
        damage_taken = self.max_hp - self.hp
        
        # If we've taken more than 10 total damage since last leaving home
        # and we're not already resting
        if self.state == HeroState.RESTING:
            return False
        
        # First time threshold: took 10+ damage total
        if self.damage_since_left_home >= 10:
            return True
        
        # If we left home damaged and took 5 more damage
        hp_missing_when_left = self.max_hp - self.hp_when_left_home
        if hp_missing_when_left > 10:
            # We left home still hurt, only return if we've taken 5 more
            additional_damage = self.damage_since_left_home
            if additional_damage >= 5:
                return True
        
        return False
    
    def start_resting(self):
        """Start resting at home."""
        # Can't rest if building is damaged
        if self.home_building and self.home_building.is_damaged:
            self.state = HeroState.IDLE
            return False
        
        # Enter the home building (Majesty-style: hero disappears inside).
        if self.home_building:
            self.is_inside_building = True
            self.inside_building = self.home_building
            self.inside_timer = 0.0
            self.x = self.home_building.center_x
            self.y = self.home_building.center_y

        self.state = HeroState.RESTING
        self.hp_healed_this_rest = 0
        self.last_heal_time = 0
        return True
    
    def update_resting(self, dt: float) -> bool:
        """Update resting state. Returns True if still resting."""
        if self.state != HeroState.RESTING:
            return False
        
        # Check if building is damaged - must pop out and defend!
        if self.home_building and self.home_building.is_damaged:
            self.pop_out_of_building()
            return False
        
        self.last_heal_time += dt
        
        # Heal 1 HP every 2 seconds
        if self.last_heal_time >= 2.0:
            self.last_heal_time = 0
            if self.hp < self.max_hp:
                self.hp += 1
                self.hp_healed_this_rest += 1
        
        # Stop resting if fully healed or healed 30 points
        if self.hp >= self.max_hp or self.hp_healed_this_rest >= 30:
            self.finish_resting()
            return False
        
        return True
    
    def pop_out_of_building(self):
        """Hero pops out of building (when building takes damage)."""
        self.state = HeroState.IDLE
        self.hp_healed_this_rest = 0
        self.is_inside_building = False
        self.inside_timer = 0.0
        self.inside_building = None
        # Stay near the building to defend it
        if self.home_building:
            # Position slightly outside the building
            self.x = self.home_building.center_x + TILE_SIZE
            self.y = self.home_building.center_y
    
    def can_rest_at_home(self) -> bool:
        """Check if hero can rest at their home building."""
        if not self.home_building:
            return False
        # Cannot rest in damaged buildings
        return not self.home_building.is_damaged
    
    def finish_resting(self):
        """Finish resting and leave home."""
        self.state = HeroState.IDLE
        self.hp_when_left_home = self.hp
        self.damage_since_left_home = 0
        self.hp_healed_this_rest = 0
        # Exit building after resting.
        if self.is_inside_building:
            self.pop_out_of_building()

    def enter_building_briefly(self, building, duration_sec: float = 0.6):
        """Enter a building briefly (e.g. shopping) then auto-exit after duration."""
        if not building:
            return
        self.is_inside_building = True
        self.inside_building = building
        self.inside_timer = max(0.0, float(duration_sec))
        self.x = building.center_x
        self.y = building.center_y
    
    def transfer_taxes_to_home(self):
        """Transfer taxed gold to home building."""
        if self.home_building and self.taxed_gold > 0:
            self.home_building.add_tax_gold(self.taxed_gold)
            self.taxed_gold = 0
    
    def heal(self, amount: int):
        """Heal the hero."""
        self.hp = min(self.max_hp, self.hp + amount)
    
    def use_potion(self) -> bool:
        """Use a healing potion if available."""
        if self.potions > 0:
            self.potions -= 1
            self.heal(self.potion_heal_amount)
            return True
        return False
    
    def add_xp(self, amount: int):
        """Add experience points, level up if enough."""
        self.xp += amount
        while self.xp >= self.xp_to_level:
            self.xp -= self.xp_to_level
            self.level_up()
    
    def level_up(self):
        """Level up the hero."""
        self.level += 1
        self.max_hp += 20
        self.hp = self.max_hp  # Full heal on level up
        self.xp_to_level = int(self.xp_to_level * 1.5)
    
    def buy_item(self, item: dict) -> bool:
        """Attempt to buy an item using spendable (non-taxed) gold. Returns True if successful."""
        if self.gold < item["price"]:
            return False
        
        self.gold -= item["price"]
        
        if item["type"] == "potion":
            if self.potions < self.max_potions:
                self.potions += 1
                self.potion_heal_amount = item.get("effect", 50)
            else:
                # Refund if at max potions
                self.gold += item["price"]
                return False
        elif item["type"] == "weapon":
            self.weapon = {"name": item["name"], "attack": item["attack"]}
        elif item["type"] == "armor":
            self.armor = {"name": item["name"], "defense": item["defense"]}

        # Track successful purchase for journey triggers (sim-time only).
        try:
            self.last_purchase_ms = int(sim_now_ms())
        except Exception:
            self.last_purchase_ms = None
        self.last_purchase_type = str(item.get("type", "")) if item else ""
        return True
    
    def wants_to_shop(self, marketplace_has_potions: bool) -> bool:
        """Check if hero wants to go shopping."""
        # Only shop when at full health and idle
        if self.hp < self.max_hp:
            return False
        
        # Need at least 30 gold to feel the need to shop
        if self.gold < 30:
            return False
        
        # If no potions and gold >= 30, want to buy one potion
        if self.potions == 0 and marketplace_has_potions:
            return True
        
        # If gold >= 50, might want to buy more potions (LLM decides)
        if self.gold >= 50 and self.potions < self.max_potions and marketplace_has_potions:
            return True
        
        return False
    
    def get_shopping_context(self) -> dict:
        """Get context for LLM shopping decisions."""
        return {
            "spendable_gold": self.gold,
            "taxed_gold": self.taxed_gold,
            "current_potions": self.potions,
            "max_potions": self.max_potions,
            "potion_price": 20,
            "hero_class": self.hero_class,
            "personality": self.personality,
        }
    
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
            move_dist = self.speed * dt * 60  # 60 is base FPS
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

        prev_x, prev_y = self.x, self.y

        # Handle brief "inside building" timer (shopping etc.)
        if self.is_inside_building and self.state != HeroState.RESTING and self.inside_timer > 0:
            self.inside_timer = max(0.0, self.inside_timer - dt)
            if self.inside_timer <= 0 and self.inside_building is not None:
                # Pop out near the building we entered.
                b = self.inside_building
                self.is_inside_building = False
                self.inside_building = None
                self.x = b.center_x + TILE_SIZE
                self.y = b.center_y
        
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
                
                # Use direct steering for far-away black-fog targets (like enemy AI does)
                # Switch to A* pathfinding when close or terrain is revealed
                if goal_in_black_fog and dist > TILE_SIZE * 12:
                    # Direct steering toward black-fog target (optimistic pathing)
                    # When hero gets close, terrain will be revealed and we can switch to A*
                    self.move_towards(goal_x, goal_y, dt)
                    return

                # Replan if needed
                goal_key = (int(goal_x), int(goal_y))
                if (not self.path) or (self._path_goal != goal_key):
                    self.path = compute_path_worldpoints(world, buildings, self.x, self.y, goal_x, goal_y)
                    self._path_goal = goal_key

                follow_path(self, dt)
            else:
                self.move_towards(self.target_position[0], self.target_position[1], dt)

        # Update facing (based on motion)
        dx = self.x - prev_x
        if abs(dx) > 0.01:
            self.facing = 1 if dx >= 0 else -1

        # Animation base state selection (one-shots can override)
        if self.is_inside_building:
            self._anim_base = "inside"
        elif self.state in (HeroState.MOVING, HeroState.RETREATING):
            self._anim_base = "walk"
        else:
            self._anim_base = "idle"

        self._update_animation(dt)

        self._last_pos = (float(self.x), float(self.y))

    # -----------------------------
    # Intent + last decision contract
    # -----------------------------

    def record_decision(self, action: str, reason: str, now_ms: int | None = None, context: dict | None = None):
        if now_ms is None:
            now_ms = sim_now_ms()
        self.last_decision = HeroDecisionRecord(
            action=str(action),
            reason=str(reason)[:120],
            at_ms=int(now_ms),
            context={} if context is None else dict(context),
        )

    def get_intent_snapshot(self, now_ms: int | None = None) -> dict:
        if now_ms is None:
            now_ms = sim_now_ms()
        snap = HeroIntentSnapshot(intent=str(getattr(self, "intent", "idle")), last_decision=getattr(self, "last_decision", None))
        return snap.to_dict(now_ms=now_ms)

    def get_stuck_snapshot(self, now_ms: int | None = None) -> dict:
        """
        UI/QA-friendly stuck status snapshot (contract field names).
        """
        if now_ms is None:
            now_ms = sim_now_ms()
        since = getattr(self, "stuck_since_ms", None)
        age_ms = 0
        if since is not None:
            try:
                age_ms = max(0, int(now_ms) - int(since))
            except Exception:
                age_ms = 0
        return {
            "stuck_active": bool(getattr(self, "stuck_active", False)),
            "stuck_since_ms": since,
            "stuck_age_ms": int(age_ms),
            "last_progress_ms": int(getattr(self, "last_progress_ms", 0) or 0),
            "unstuck_attempts": int(getattr(self, "unstuck_attempts", 0) or 0),
            "stuck_reason": str(getattr(self, "stuck_reason", "") or ""),
        }

    def _derive_intent(self) -> tuple[str, str, dict]:
        """
        Derive (intent, reason, context) from state + target.

        Intents are aligned with the current sprint taxonomy:
        idle, pursuing_bounty, shopping, returning_to_safety, engaging_enemy, defending_building, attacking_lair.
        """
        # Default
        intent = "idle"
        reason = "no urgent goal"
        context: dict = {}

        t = getattr(self, "target", None)
        state = getattr(self, "state", HeroState.IDLE)

        # Enemy engagement
        if state == HeroState.FIGHTING or (t is not None and hasattr(t, "is_alive") and getattr(t, "is_alive", False)):
            return "engaging_enemy", "engaging nearby enemy", {"target": "enemy", "enemy_type": getattr(t, "enemy_type", None)}

        # Dict targets (AI/controller activities)
        if isinstance(t, dict):
            ttype = t.get("type")
            if ttype == "bounty":
                btype = t.get("bounty_type", "explore")
                bid = t.get("bounty_id")
                if btype == "attack_lair":
                    return "attacking_lair", "pursuing lair bounty", {"target": "bounty", "bounty_id": bid, "bounty_type": btype}
                if btype == "defend_building":
                    return "defending_building", "pursuing defense bounty", {"target": "bounty", "bounty_id": bid, "bounty_type": btype}
                return "pursuing_bounty", "pursuing bounty", {"target": "bounty", "bounty_id": bid, "bounty_type": btype}
            if ttype == "shopping":
                return "shopping", "heading to marketplace", {"target": "marketplace", "item": t.get("item")}
            if ttype == "going_home":
                return "returning_to_safety", "returning home to rest", {"target": "home"}

        # Movement without a specific activity is usually "idle/exploring" for now.
        if state in (HeroState.MOVING, HeroState.RETREATING):
            intent = "idle"
            reason = "moving"
            if state == HeroState.RETREATING:
                intent = "returning_to_safety"
                reason = "retreating to safety"

        # Resting maps to safety intent (taxonomy-friendly).
        if state == HeroState.RESTING:
            intent = "returning_to_safety"
            reason = "resting at home"
            context = {"target": "home"}

        return intent, reason, context

    def _update_intent_and_decision(self, game_state: dict | None):
        now_ms = sim_now_ms()
        intent, reason, ctx = self._derive_intent()

        # Detect meaningful changes and store a new "last decision" snapshot.
        t = getattr(self, "target", None)
        key_target = None
        if isinstance(t, dict) and t.get("type") == "bounty":
            key_target = ("bounty", t.get("bounty_id"), t.get("bounty_type"))
        elif isinstance(t, dict):
            key_target = ("dict", t.get("type"))
        elif t is None:
            key_target = None
        else:
            # Avoid non-deterministic identities (id()) in snapshots.
            key_target = ("obj", t.__class__.__name__)

        new_key = (intent, getattr(self, "state", None), key_target)
        if self._intent_prev_key != new_key:
            self.intent = str(intent)
            self.record_decision(action=intent, reason=reason, now_ms=now_ms, context=ctx)
            self._intent_prev_key = new_key

    def _play_one_shot(self, name: str):
        """Play a non-looping clip and prevent base animation from overriding until it finishes."""
        if not hasattr(self, "_anim") or self._anim is None:
            return
        self._anim_lock_one_shot = name
        self._anim.play(name, restart=True)

    def _update_animation(self, dt: float):
        if not hasattr(self, "_anim") or self._anim is None:
            return

        # If a one-shot is active, keep it until finished.
        if self._anim_lock_one_shot:
            if self._anim.current != self._anim_lock_one_shot:
                self._anim.play(self._anim_lock_one_shot, restart=True)
            self._anim.update(dt)
            if self._anim.finished:
                self._anim_lock_one_shot = None
                self._anim.play(self._anim_base, restart=True)
            return

        # Otherwise follow the base state
        self._anim.play(self._anim_base, restart=False)
        self._anim.update(dt)

    def on_attack_landed(self, target, damage: int, killed: bool):
        """Called by CombatSystem when this hero lands an attack."""
        # For now, just play an attack one-shot.
        self._play_one_shot("attack")
    
    def get_context_for_llm(self, game_state: dict) -> dict:
        """Build context dictionary for LLM decision making."""
        context = {
            "hero": {
                "name": self.name,
                "class": self.hero_class,
                "level": self.level,
                "hp": self.hp,
                "max_hp": self.max_hp,
                "health_percent": round(self.health_percent * 100),
                "gold": self.gold,
                "attack": self.attack,
                "defense": self.defense,
            },
            "inventory": {
                "weapon": self.weapon["name"] if self.weapon else "Fists",
                "armor": self.armor["name"] if self.armor else "None",
                "potions": self.potions,
            },
            "personality": self.personality,
            "current_state": self.state.name,
            "nearby_enemies": [],
            "available_bounties": game_state.get("bounties", []),
            "shop_items": [],
            "situation": {
                "in_combat": False,
                "low_health": self.health_percent < 0.5,
                "critical_health": self.health_percent < 0.25,
                "has_potions": self.potions > 0,
                "near_safety": False,
            },
        }
        
        # Add nearby enemies
        for enemy in game_state.get("enemies", []):
            if enemy.is_alive:
                dist = self.distance_to(enemy.x, enemy.y)
                if dist < TILE_SIZE * 10:  # Within 10 tiles
                    context["nearby_enemies"].append({
                        "type": enemy.enemy_type,
                        "hp": enemy.hp,
                        "max_hp": enemy.max_hp,
                        "distance": round(dist / TILE_SIZE, 1),
                    })
        
        # Add shop items if near marketplace
        for building in game_state.get("buildings", []):
            if building.building_type == "marketplace":
                dist = self.distance_to(building.center_x, building.center_y)
                if dist < TILE_SIZE * 5:
                    context["shop_items"] = building.get_available_items()
                    context["near_marketplace"] = True
        
        return context
    
    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the hero."""
        if not self.is_alive:
            return
            
        cam_x, cam_y = camera_offset
        screen_x = self.x - cam_x
        screen_y = self.y - cam_y

        # If inside a building, render a small animated "bubble" at the building location.
        if self.is_inside_building and self.inside_building is not None:
            bx = getattr(self.inside_building, "center_x", self.x) - cam_x
            by = getattr(self.inside_building, "center_y", self.y) - cam_y
            bubble = self._anim.frame() if self._anim is not None else None
            if bubble is not None:
                # Small and subtle
                # Pixel art: keep nearest-neighbor scaling (avoid blur + extra cost).
                bubble_small = pygame.transform.scale(bubble, (16, 16))
                surface.blit(bubble_small, (int(bx - 8), int(by - 28)))
            return

        # Draw animated sprite frame (procedural placeholder until real assets exist)
        if hasattr(self, "_anim") and self._anim is not None:
            frame = self._anim.frame()
            if self.facing < 0:
                frame = pygame.transform.flip(frame, True, False)
            fw, fh = frame.get_width(), frame.get_height()
            surface.blit(frame, (int(screen_x - fw // 2), int(screen_y - fh // 2)))
        else:
            # Fallback: old circle render
            pygame.draw.circle(surface, self.color, (int(screen_x), int(screen_y)), self.size // 2)
            pygame.draw.circle(surface, COLOR_WHITE, (int(screen_x), int(screen_y)), self.size // 2, 2)
        
        # Draw health bar
        bar_width = self.size + 10
        bar_height = 4
        bar_x = screen_x - bar_width // 2
        bar_y = screen_y - self.size // 2 - 8
        
        # Background
        pygame.draw.rect(surface, (60, 60, 60), (bar_x, bar_y, bar_width, bar_height))
        
        # Health
        health_color = COLOR_GREEN if self.health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(
            surface, 
            health_color, 
            (bar_x, bar_y, bar_width * self.health_percent, bar_height)
        )
        
        # Draw name
        font = get_font(16)
        name_text = font.render(self.name, True, COLOR_WHITE)
        name_rect = name_text.get_rect(center=(screen_x, screen_y + self.size // 2 + 10))
        surface.blit(name_text, name_rect)
        
        # Draw gold if any (show both spendable and taxed)
        total_gold = self.gold + self.taxed_gold
        if total_gold > 0:
            gold_text = font.render(f"${self.gold}(+{self.taxed_gold})", True, (255, 215, 0))
            gold_rect = gold_text.get_rect(center=(screen_x, screen_y + self.size // 2 + 22))
            surface.blit(gold_text, gold_rect)
        
        # Show resting indicator
        if self.state == HeroState.RESTING:
            rest_text = font.render("Zzz", True, (150, 200, 255))
            rest_rect = rest_text.get_rect(center=(screen_x + 15, screen_y - self.size // 2 - 15))
            surface.blit(rest_text, rest_rect)

