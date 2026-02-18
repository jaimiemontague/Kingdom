"""
Enemy entities.
"""
import math
from enum import Enum, auto
from config import (
    TILE_SIZE, GOBLIN_HP, GOBLIN_ATTACK, GOBLIN_SPEED,
    WOLF_HP, WOLF_ATTACK, WOLF_SPEED,
    SKELETON_HP, SKELETON_ATTACK, SKELETON_SPEED,
    SKELETON_ARCHER_HP, SKELETON_ARCHER_ATTACK, SKELETON_ARCHER_SPEED,
    SKELETON_ARCHER_ATTACK_RANGE_TILES, SKELETON_ARCHER_MIN_RANGE_TILES,
    SKELETON_ARCHER_ATTACK_COOLDOWN_MS,
    COLOR_RED
)
from game.sim.timebase import now_ms


class EnemyState(Enum):
    IDLE = auto()
    MOVING = auto()
    ATTACKING = auto()
    DEAD = auto()


class Enemy:
    """Base enemy class."""
    
    def __init__(self, x: float, y: float, enemy_type: str = "goblin"):
        self.x = x
        self.y = y
        self.enemy_type = enemy_type
        
        # Stats (set by subclass)
        self.hp = 30
        self.max_hp = 30
        self.attack_power = 5
        self.speed = 1.5
        self.xp_reward = 25
        self.gold_reward = 10
        
        # AI State
        self.state = EnemyState.IDLE
        self.target = None

        # Navigation helpers: cache an "approach point" for building targets.
        # Without caching, the chosen adjacent tile can fluctuate every frame as the enemy moves,
        # which forces frequent A* replans and causes severe slowdown once enemies spawn.
        self._approach_target = None
        self._approach_pos = None  # (x, y) world-space
        self._next_replan_ms = 0  # backoff timer for pathfinding (prevents A* spam on no-path)
        
        # WK5: Ranged projectile event storage (for engine collection)
        self._last_ranged_event = None
        
        # Combat
        self.attack_cooldown = 0
        self.attack_cooldown_max = 1500  # ms between attacks
        self.attack_range = TILE_SIZE * 1.2
        
        # Visual
        self.size = 18
        self.color = COLOR_RED
        self._render_anim_trigger: str | None = None
        
    @property
    def is_alive(self) -> bool:
        return self.hp > 0
    
    @property
    def health_percent(self) -> float:
        return self.hp / self.max_hp

    @property
    def render_state(self) -> "Enemy":
        """Render accessor used by render-side systems."""
        return self
    
    def take_damage(self, amount: int) -> bool:
        """Take damage, returns True if killed."""
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.state = EnemyState.DEAD
            self._queue_render_animation("dead")
            return True
        self._queue_render_animation("hurt")
        return False

    def _queue_render_animation(self, name: str) -> None:
        self._render_anim_trigger = str(name)
    
    def distance_to(self, x: float, y: float) -> float:
        """Calculate distance to a point."""
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    @staticmethod
    def _is_inside_building_target(target: object) -> bool:
        """Whether a target entity is currently inside any building."""
        try:
            return bool(getattr(target, "is_inside_building", False))
        except Exception:
            return False

    def _needs_new_target(self) -> bool:
        """Return True when the current target is invalid for attacking."""
        if self.target is None:
            return True
        if hasattr(self.target, "is_alive") and not self.target.is_alive:
            return True
        if self._is_inside_building_target(self.target):
            return True
        return False
    
    def move_towards(self, target_x: float, target_y: float, dt: float):
        """Move towards a target position."""
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist > 0:
            move_dist = self.speed * dt * 60
            if move_dist >= dist:
                self.x = target_x
                self.y = target_y
            else:
                self.x += (dx / dist) * move_dist
                self.y += (dy / dist) * move_dist
    
    def find_target(self, heroes: list, peasants: list, buildings: list, guards: list = None):
        """Find the nearest valid target (peasant, hero, guard, or targetable building)."""
        best_target = None
        best_dist = float('inf')

        # Check peasants that are NOT inside the castle
        for peasant in peasants or []:
            if getattr(peasant, "is_alive", False) and not getattr(peasant, "is_inside_castle", False):
                dist = self.distance_to(peasant.x, peasant.y)
                if dist < best_dist:
                    best_dist = dist
                    best_target = peasant
        
        # Check heroes that are NOT inside buildings (covers resting/shopping/etc).
        for hero in heroes:
            if hero.is_alive and not bool(getattr(hero, "is_inside_building", False)):
                dist = self.distance_to(hero.x, hero.y)
                if dist < best_dist:
                    best_dist = dist
                    best_target = hero

        # Check guards (always targetable)
        for guard in guards or []:
            if getattr(guard, "is_alive", False):
                dist = self.distance_to(guard.x, guard.y)
                if dist < best_dist:
                    best_dist = dist
                    best_target = guard
        
        # Check buildings
        for building in buildings:
            if building.hp <= 0:
                continue
            if hasattr(building, "is_targetable") and not building.is_targetable:
                continue
            
            dist = self.distance_to(building.center_x, building.center_y)
            
            # Castle is always a valid fallback target
            if building.building_type == "castle" and dist < best_dist * 0.8:
                best_dist = dist
                best_target = building
            # Neutral buildings (houses/farms/food stands) can be attacked if they are meaningfully closer
            # than any currently chosen target. This makes civilian infrastructure a "soft target" without
            # overriding the normal preference for heroes/peasants/guards.
            elif getattr(building, "is_neutral", False) and dist < best_dist * 0.9:
                best_dist = dist
                best_target = building
        
        self.target = best_target
        return best_target
    
    def update(self, dt: float, heroes: list, peasants: list, buildings: list, guards: list = None, world=None):
        """Update enemy state and behavior."""
        if not self.is_alive:
            return
        
        # Update attack cooldown
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt * 1000
        
        # Retarget if we don't have one, the target died, or the target moved inside a building.
        if self._needs_new_target():
            self.find_target(heroes, peasants, buildings, guards=guards)
        
        if self.target is None:
            self.state = EnemyState.IDLE
            return

        now_ms_val = now_ms()
        
        # Get target position
        if hasattr(self.target, 'x'):
            # Moving targets: don't use cached building approach.
            self._approach_target = None
            self._approach_pos = None
            target_x, target_y = self.target.x, self.target.y
        else:
            # For buildings, approach an adjacent tile instead of walking through the footprint.
            # Cache the chosen approach point per target to avoid per-frame A* thrash.
            if self._approach_target is not self.target or not self._approach_pos:
                if world is not None:
                    from game.systems.navigation import best_adjacent_tile
                    adj = best_adjacent_tile(world, buildings, self.target, self.x, self.y)
                    if adj:
                        self._approach_pos = (
                            adj[0] * TILE_SIZE + TILE_SIZE / 2,
                            adj[1] * TILE_SIZE + TILE_SIZE / 2,
                        )
                    else:
                        self._approach_pos = (self.target.center_x, self.target.center_y)
                else:
                    self._approach_pos = (self.target.center_x, self.target.center_y)
                self._approach_target = self.target

            target_x, target_y = self._approach_pos
        
        dist = self.distance_to(target_x, target_y)
        
        # Attack if in range
        if dist <= self.attack_range:
            self.state = EnemyState.ATTACKING
            if self.attack_cooldown <= 0:
                self.do_attack()
                self.attack_cooldown = self.attack_cooldown_max
        else:
            # Move towards target
            self.state = EnemyState.MOVING
            if world is not None:
                # Avoid long-distance A*: it is expensive on large maps and not needed until near the goal.
                # Far away, just steer straight towards the goal (we only truly need pathing to avoid
                # building footprints when we are close to them).
                if dist > TILE_SIZE * 12:
                    self.move_towards(target_x, target_y, dt)
                    return

                # Path around buildings/blocked tiles.
                from game.systems.navigation import compute_path_worldpoints, follow_path
                if not hasattr(self, "path"):
                    self.path = []
                    self._path_goal = None
                goal_key = (int(target_x), int(target_y))

                want_replan = (not self.path) or (getattr(self, "_path_goal", None) != goal_key)
                if want_replan and now_ms_val >= int(getattr(self, "_next_replan_ms", 0) or 0):
                    self.path = compute_path_worldpoints(world, buildings, self.x, self.y, target_x, target_y)
                    self._path_goal = goal_key
                    # If no path exists, avoid recomputing every frame.
                    if not self.path:
                        self._next_replan_ms = now_ms_val + 800
                    else:
                        # Throttle replans a bit even on success.
                        self._next_replan_ms = now_ms_val + 150

                if self.path:
                    follow_path(self, dt)
                else:
                    # Fallback: still move roughly toward the goal so enemies don't freeze.
                    self.move_towards(target_x, target_y, dt)
            else:
                self.move_towards(target_x, target_y, dt)
    
    def do_attack(self):
        """
        Perform an attack on the current target.
        
        WK5: For ranged attackers, stores ranged projectile event in _last_ranged_event
        for collection by engine.
        """
        if self.target is None or not hasattr(self.target, "take_damage"):
            self._last_ranged_event = None
            return
        if self._is_inside_building_target(self.target):
            # Hard safety gate: never apply damage to heroes while they are inside buildings.
            self.target = None
            self._last_ranged_event = None
            return

        if self.target and hasattr(self.target, 'take_damage'):
            self._queue_render_animation("attack")
            self.target.take_damage(self.attack_power)
            
            # WK5: Emit ranged projectile event for ranged attackers
            if getattr(self, "is_ranged_attacker", False):
                spec = None
                if hasattr(self, "get_ranged_spec"):
                    try:
                        spec = self.get_ranged_spec()
                    except Exception:
                        spec = None
                
                kind = (spec or {}).get("kind", "arrow")
                color = (spec or {}).get("color", (200, 200, 200))
                size = (spec or {}).get("size_px", 2)  # Build B: default 2px for readability
                
                # Get target position (handle both entities and buildings)
                if hasattr(self.target, "x") and hasattr(self.target, "y"):
                    to_x = float(self.target.x)
                    to_y = float(self.target.y)
                elif hasattr(self.target, "center_x") and hasattr(self.target, "center_y"):
                    to_x = float(self.target.center_x)
                    to_y = float(self.target.center_y)
                else:
                    to_x = float(getattr(self.target, "x", 0.0))
                    to_y = float(getattr(self.target, "y", 0.0))
                
                # Store event for engine collection (WK5: enemy attacks happen in update(), not combat system)
                self._last_ranged_event = {
                    "type": "ranged_projectile",
                    "from_x": float(self.x),
                    "from_y": float(self.y),
                    "to_x": to_x,
                    "to_y": to_y,
                    "projectile_kind": kind,
                    "color": color,
                    "size_px": size,
                }
            else:
                # Clear any stale event for non-ranged attackers
                self._last_ranged_event = None


class Goblin(Enemy):
    """Basic goblin enemy."""
    
    def __init__(self, x: float, y: float):
        super().__init__(x, y, "goblin")
        self.hp = GOBLIN_HP
        self.max_hp = GOBLIN_HP
        self.attack_power = GOBLIN_ATTACK * 2  # 2x damage (scaled back from 4x)
        self.speed = GOBLIN_SPEED
        self.xp_reward = 25
        self.gold_reward = 10  # Fixed 10 gold per goblin
        self.color = (139, 69, 19)  # Brown-ish green
        
        # Track who has hit this goblin for gold distribution
        self.attackers = set()  # Set of hero names who have hit this goblin
    
    def register_attacker(self, hero):
        """Register a hero as having attacked this goblin."""
        self.attackers.add(hero.name)


class Wolf(Enemy):
    """Fast, low-HP enemy usually spawned from Wolf Dens."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y, "wolf")
        self.hp = WOLF_HP
        self.max_hp = WOLF_HP
        self.attack_power = WOLF_ATTACK
        self.speed = WOLF_SPEED
        self.xp_reward = 20
        self.gold_reward = 6
        self.color = (160, 160, 160)


class Skeleton(Enemy):
    """Tougher slow enemy usually spawned from Skeleton Crypts."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y, "skeleton")
        self.hp = SKELETON_HP
        self.max_hp = SKELETON_HP
        self.attack_power = SKELETON_ATTACK
        self.speed = SKELETON_SPEED
        self.xp_reward = 35
        self.gold_reward = 14
        self.color = (220, 220, 240)


class SkeletonArcher(Enemy):
    """Ranged kiter enemy spawned from Skeleton Crypts. Maintains distance and attacks from range."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y, "skeleton_archer")
        self.hp = SKELETON_ARCHER_HP
        self.max_hp = SKELETON_ARCHER_HP
        self.attack_power = SKELETON_ARCHER_ATTACK
        self.speed = SKELETON_ARCHER_SPEED
        self.xp_reward = 35  # Same as skeleton
        self.gold_reward = 14  # Same as skeleton
        self.color = (200, 200, 220)
        
        # Ranged attack settings
        self.attack_range = SKELETON_ARCHER_ATTACK_RANGE_TILES * TILE_SIZE
        self.min_range = SKELETON_ARCHER_MIN_RANGE_TILES * TILE_SIZE
        self.attack_cooldown_max = SKELETON_ARCHER_ATTACK_COOLDOWN_MS
        
        # WK5: Ranged attacker interface
        self.is_ranged_attacker = True
        
        # Kiting behavior state (deterministic, sim-time based)
        self._kite_commit_until_ms = 0  # Hysteresis: commit to current kite decision
        self._kite_reposition_cooldown_ms = 0  # Rate-limit reposition evaluations
        self._kite_reposition_interval_ms = 800  # Re-evaluate kite position every ~0.8s
        self._kite_attempts = 0  # Bounded attempts per target to avoid infinite loops
        self._max_kite_attempts = 5  # Fallback to stand-and-shoot after N attempts
        self._kite_target_key = None  # Track target for attempt counting
    
    def update(self, dt: float, heroes: list, peasants: list, buildings: list, guards: list = None, world=None):
        """Override to add kiting behavior: maintain distance band with hysteresis/commitment."""
        if not self.is_alive:
            return
        now_ms_val = now_ms()
        
        # Update attack cooldown
        if self.attack_cooldown > 0:
            self.attack_cooldown -= dt * 1000
        
        # Update kite reposition cooldown
        if self._kite_reposition_cooldown_ms > 0:
            self._kite_reposition_cooldown_ms -= dt * 1000
        
        # Retarget if we don't have one, the target died, or the target moved inside a building.
        if self._needs_new_target():
            self.find_target(heroes, peasants, buildings, guards=guards)
            # Reset kite state on new target
            if self.target is not None:
                target_key = id(self.target) if hasattr(self.target, 'x') else (getattr(self.target, 'center_x', 0), getattr(self.target, 'center_y', 0))
                if self._kite_target_key != target_key:
                    self._kite_target_key = target_key
                    self._kite_attempts = 0
                    self._kite_commit_until_ms = now_ms_val + 500  # Initial commitment window
        
        if self.target is None:
            self.state = EnemyState.IDLE
            return

        # Get target position
        if hasattr(self.target, 'x'):
            target_x, target_y = self.target.x, self.target.y
        else:
            target_x, target_y = self.target.center_x, self.target.center_y
        
        dist = self.distance_to(target_x, target_y)
        
        # Kiting logic: maintain distance band (min_range to attack_range)
        # Use hysteresis/commitment to avoid jitter oscillation
        in_attack_range = dist <= self.attack_range
        too_close = dist < self.min_range
        can_reposition = (self._kite_reposition_cooldown_ms <= 0 and 
                         now_ms_val >= self._kite_commit_until_ms)
        
        # If too many kite attempts, fallback to stand-and-shoot
        if self._kite_attempts >= self._max_kite_attempts:
            # Stand and shoot: attack if in range, otherwise move closer
            if in_attack_range:
                self.state = EnemyState.ATTACKING
                if self.attack_cooldown <= 0:
                    self.do_attack()
                    self.attack_cooldown = self.attack_cooldown_max
            else:
                self.state = EnemyState.MOVING
                self.move_towards(target_x, target_y, dt)
        # Normal kiting behavior
        elif too_close and can_reposition:
            # Too close: kite away
            self._kite_attempts += 1
            self._kite_reposition_cooldown_ms = self._kite_reposition_interval_ms
            self._kite_commit_until_ms = now_ms_val + 500  # Commit to this decision
            
            # Calculate kite-away direction (away from target)
            dx = self.x - target_x
            dy = self.y - target_y
            kite_dist = math.sqrt(dx * dx + dy * dy)
            if kite_dist > 0:
                # Move away from target
                kite_x = self.x + (dx / kite_dist) * (self.min_range * 0.5)
                kite_y = self.y + (dy / kite_dist) * (self.min_range * 0.5)
                if world is not None:
                    from game.systems.navigation import compute_path_worldpoints, follow_path
                    if not hasattr(self, "path"):
                        self.path = []
                        self._path_goal = None
                    goal_key = (int(kite_x), int(kite_y))
                    if getattr(self, "_path_goal", None) != goal_key:
                        self.path = compute_path_worldpoints(world, buildings, self.x, self.y, kite_x, kite_y)
                        self._path_goal = goal_key
                    if self.path:
                        follow_path(self, dt)
                    else:
                        self.move_towards(kite_x, kite_y, dt)
                else:
                    self.move_towards(kite_x, kite_y, dt)
                self.state = EnemyState.MOVING
        elif in_attack_range:
            # In attack range: attack
            self.state = EnemyState.ATTACKING
            if self.attack_cooldown <= 0:
                self.do_attack()
                self.attack_cooldown = self.attack_cooldown_max
        else:
            # Too far: move closer (but respect min_range)
            self.state = EnemyState.MOVING
            # Move to optimal range (midpoint of min_range and attack_range)
            optimal_range = (self.min_range + self.attack_range) * 0.5
            if dist > optimal_range:
                # Move towards target
                if world is not None:
                    from game.systems.navigation import compute_path_worldpoints, follow_path
                    if not hasattr(self, "path"):
                        self.path = []
                        self._path_goal = None
                    goal_key = (int(target_x), int(target_y))
                    want_replan = (not self.path) or (getattr(self, "_path_goal", None) != goal_key)
                    if want_replan and now_ms_val >= int(getattr(self, "_next_replan_ms", 0) or 0):
                        self.path = compute_path_worldpoints(world, buildings, self.x, self.y, target_x, target_y)
                        self._path_goal = goal_key
                        if not self.path:
                            self._next_replan_ms = now_ms_val + 800
                        else:
                            self._next_replan_ms = now_ms_val + 150
                    if self.path:
                        follow_path(self, dt)
                    else:
                        self.move_towards(target_x, target_y, dt)
                else:
                    self.move_towards(target_x, target_y, dt)


class Spider(Enemy):
    """Fast, low-HP swarm enemy usually spawned from Spider Nests."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y, "spider")
        self.hp = 18
        self.max_hp = 18
        self.attack_power = 4
        self.speed = 2.6
        self.xp_reward = 18
        self.gold_reward = 5
        self.color = (30, 30, 30)
        self.attackers = set()

    def register_attacker(self, hero):
        self.attackers.add(hero.name)


class Bandit(Enemy):
    """Mid-tier humanoid enemy usually spawned from Bandit Camps."""

    def __init__(self, x: float, y: float):
        super().__init__(x, y, "bandit")
        self.hp = 42
        self.max_hp = 42
        self.attack_power = 9
        self.speed = 1.7
        self.xp_reward = 32
        self.gold_reward = 12
        self.color = (120, 80, 50)
        self.attackers = set()

    def register_attacker(self, hero):
        self.attackers.add(hero.name)

