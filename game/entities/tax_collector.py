"""
Tax Collector NPC that collects gold from warrior guilds.
"""
import math
from enum import Enum, auto
from config import (
    TILE_SIZE,
    TAX_COLLECTION_INTERVAL_SEC,
    TAX_COLLECTOR_REST_AFTER_RETURN_SEC,
    TAX_COLLECTOR_NICE_HAUL_GOLD,
)


class CollectorState(Enum):
    WAITING = auto()           # At castle, looking for work (go out immediately if any guild has gold)
    MOVING_TO_GUILD = auto()
    COLLECTING = auto()
    RETURNING = auto()
    RESTING_AT_CASTLE = auto()  # Short rest (e.g. 10s) after returning a nice haul


class TaxCollector:
    """Tax collector NPC that goes to warrior guilds and collects taxes."""
    
    def __init__(self, castle):
        self.castle = castle
        self.x = castle.center_x
        self.y = castle.center_y
        self.home_x = castle.center_x
        self.home_y = castle.center_y
        
        self.state = CollectorState.WAITING
        self.target_guild = None
        self.guilds_to_visit = []
        
        self.speed = 1.5
        self.size = 14
        self.color = (218, 165, 32)  # Gold color
        
        # Collection timing (wk15: from config for pacing)
        self.collection_interval = float(TAX_COLLECTION_INTERVAL_SEC)
        self.time_since_last_collection = 0
        self.collection_delay = 1.0  # Time spent at each guild
        self.collection_timer = 0

        # Rest at castle after a good return (only time we sit at castle)
        self.rest_after_return_sec = float(TAX_COLLECTOR_REST_AFTER_RETURN_SEC)
        self.nice_haul_gold = int(TAX_COLLECTOR_NICE_HAUL_GOLD)
        self.rest_timer = 0.0
        
        # Gold being carried
        self.carried_gold = 0
        self.total_collected = 0
        self._render_anim_trigger: str | None = None
    
    def distance_to(self, x: float, y: float) -> float:
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    @property
    def render_state(self) -> "TaxCollector":
        """Render accessor used by render-side systems."""
        return self
    
    def move_towards(self, target_x: float, target_y: float, dt: float) -> bool:
        """Move towards target. Returns True if reached."""
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        
        if dist < 5:
            self.x = target_x
            self.y = target_y
            return True
        
        move_dist = self.speed * dt * 60
        self.x += (dx / dist) * move_dist
        self.y += (dy / dist) * move_dist
        return False

    def _sorted_tax_targets(self, buildings: list) -> tuple[list, list]:
        """
        Return (rich_targets, all_tax_targets) sorted by distance from collector.
        rich_targets have stored_tax_gold > 0.
        """
        rich_targets = []
        all_targets = []
        for b in buildings:
            if not hasattr(b, "collect_taxes"):
                continue
            if getattr(b, "hp", 1) <= 0:
                continue
            all_targets.append(b)
            if getattr(b, "stored_tax_gold", 0) > 0:
                rich_targets.append(b)

        key_fn = lambda b: self.distance_to(getattr(b, "center_x", self.x), getattr(b, "center_y", self.y))
        all_targets.sort(key=key_fn)
        rich_targets.sort(key=key_fn)
        return rich_targets, all_targets
    
    def update(self, dt: float, buildings: list, economy, world=None):
        """Update tax collector behavior. Nearly always out collecting; only at castle to deposit and rest 10s after a nice haul."""

        if self.state == CollectorState.RESTING_AT_CASTLE:
            self.rest_timer += dt
            if self.rest_timer >= self.rest_after_return_sec:
                self.rest_timer = 0.0
                self.state = CollectorState.WAITING
            return

        if self.state == CollectorState.WAITING:
            # Prefer buildings that currently have tax gold.
            rich_targets, all_targets = self._sorted_tax_targets(buildings)
            if rich_targets:
                self.guilds_to_visit = rich_targets
                self.target_guild = self.guilds_to_visit.pop(0)
                self.state = CollectorState.MOVING_TO_GUILD
                self.time_since_last_collection = 0.0
            elif all_targets:
                # Keep collector active by patrolling tax-capable buildings even when they are empty.
                # This avoids long idle periods at the castle.
                self.time_since_last_collection += dt
                patrol_interval = min(self.collection_interval, 8.0)
                if self.time_since_last_collection >= patrol_interval:
                    self.time_since_last_collection = 0.0
                    self.guilds_to_visit = all_targets
                    self.target_guild = self.guilds_to_visit.pop(0)
                    self.state = CollectorState.MOVING_TO_GUILD
            else:
                self.time_since_last_collection += dt

        elif self.state == CollectorState.MOVING_TO_GUILD:
            if self.target_guild:
                tx, ty = self.target_guild.center_x, self.target_guild.center_y
                reached = False
                if world is not None:
                    from game.systems.navigation import best_adjacent_tile, compute_path_worldpoints, follow_path
                    adj = best_adjacent_tile(world, buildings, self.target_guild, self.x, self.y)
                    if adj:
                        tx = adj[0] * TILE_SIZE + TILE_SIZE / 2
                        ty = adj[1] * TILE_SIZE + TILE_SIZE / 2
                    if not hasattr(self, "path"):
                        self.path = []
                        self._path_goal = None
                    goal_key = (int(tx), int(ty))
                    if (not self.path) or (getattr(self, "_path_goal", None) != goal_key):
                        self.path = compute_path_worldpoints(world, buildings, self.x, self.y, tx, ty)
                        self._path_goal = goal_key
                    if self.path:
                        follow_path(self, dt)
                        reached = self.distance_to(tx, ty) < 5
                    else:
                        # If pathfinder can't solve from current tile (e.g. starting inside castle footprint),
                        # still move directly toward the target to break out of deadlock.
                        reached = self.move_towards(tx, ty, dt)
                else:
                    reached = self.move_towards(tx, ty, dt)
                if reached:
                    self.state = CollectorState.COLLECTING
                    self.collection_timer = 0
        
        elif self.state == CollectorState.COLLECTING:
            self.collection_timer += dt
            
            if self.collection_timer >= self.collection_delay:
                # Collect gold from this guild
                if self.target_guild:
                    gold = self.target_guild.collect_taxes()
                    self.carried_gold += gold
                    self.total_collected += gold
                
                # More guilds to visit?
                if self.guilds_to_visit:
                    self.target_guild = self.guilds_to_visit.pop(0)
                    self.state = CollectorState.MOVING_TO_GUILD
                else:
                    self.target_guild = None
                    # Only return to castle if we have taxes to deposit.
                    # Otherwise keep patrolling/working outside.
                    if self.carried_gold > 0:
                        self.state = CollectorState.RETURNING
                    else:
                        self.state = CollectorState.WAITING
        
        elif self.state == CollectorState.RETURNING:
            tx, ty = self.home_x, self.home_y
            reached = False
            if world is not None:
                from game.systems.navigation import best_adjacent_tile, compute_path_worldpoints, follow_path
                adj = best_adjacent_tile(world, buildings, self.castle, self.x, self.y)
                if adj:
                    tx = adj[0] * TILE_SIZE + TILE_SIZE / 2
                    ty = adj[1] * TILE_SIZE + TILE_SIZE / 2
                if not hasattr(self, "path"):
                    self.path = []
                    self._path_goal = None
                goal_key = (int(tx), int(ty))
                if (not self.path) or (getattr(self, "_path_goal", None) != goal_key):
                    self.path = compute_path_worldpoints(world, buildings, self.x, self.y, tx, ty)
                    self._path_goal = goal_key
                if self.path:
                    follow_path(self, dt)
                    reached = self.distance_to(tx, ty) < 5
                else:
                    reached = self.move_towards(tx, ty, dt)
            else:
                reached = self.move_towards(tx, ty, dt)
            if reached:
                # Deposit gold to player
                deposited = self.carried_gold
                if deposited > 0:
                    economy.player_gold += deposited
                    economy.total_tax_collected += deposited
                    self.carried_gold = 0
                # Rest 10s at castle only after returning a nice haul; otherwise go straight back out
                if deposited >= self.nice_haul_gold:
                    self.state = CollectorState.RESTING_AT_CASTLE
                    self.rest_timer = 0.0
                else:
                    self.state = CollectorState.WAITING

