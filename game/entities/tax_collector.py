"""
Tax Collector NPC that collects gold from warrior guilds.
"""
import math
from enum import Enum, auto
from config import TILE_SIZE


class CollectorState(Enum):
    WAITING = auto()
    MOVING_TO_GUILD = auto()
    COLLECTING = auto()
    RETURNING = auto()


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
        
        # Collection timing
        self.collection_interval = 60.0  # 60 seconds = 1 minute
        self.time_since_last_collection = 0
        self.collection_delay = 1.0  # Time spent at each guild
        self.collection_timer = 0
        
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
    
    def update(self, dt: float, buildings: list, economy, world=None):
        """Update tax collector behavior."""
        
        if self.state == CollectorState.WAITING:
            self.time_since_last_collection += dt
            
            # Time to collect taxes?
            if self.time_since_last_collection >= self.collection_interval:
                self.time_since_last_collection = 0
                
                # Find all guild-like buildings with stored tax gold.
                # (We treat anything with collect_taxes + stored_tax_gold as a guild.)
                self.guilds_to_visit = []
                for b in buildings:
                    if not hasattr(b, "collect_taxes"):
                        continue
                    if getattr(b, "stored_tax_gold", 0) <= 0:
                        continue
                    self.guilds_to_visit.append(b)
                
                if self.guilds_to_visit:
                    self.target_guild = self.guilds_to_visit.pop(0)
                    self.state = CollectorState.MOVING_TO_GUILD
        
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
                    follow_path(self, dt)
                    reached = self.distance_to(tx, ty) < 5
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
                    # Return to castle
                    self.target_guild = None
                    self.state = CollectorState.RETURNING
        
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
                follow_path(self, dt)
                reached = self.distance_to(tx, ty) < 5
            else:
                reached = self.move_towards(tx, ty, dt)
            if reached:
                # Deposit gold to player
                if self.carried_gold > 0:
                    economy.player_gold += self.carried_gold
                    economy.total_tax_collected += self.carried_gold
                    self.carried_gold = 0
                self.state = CollectorState.WAITING

