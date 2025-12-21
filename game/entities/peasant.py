"""
Peasant worker unit.

Peasants spawn from the castle and:
1) Build newly placed (unconstructed) buildings.
2) Repair damaged buildings (lowest % HP first).
3) If nothing to do, move inside the castle for protection.

Peasants are attackable and can die.
"""

import math
import pygame
from enum import Enum, auto
from config import TILE_SIZE, COLOR_WHITE, COLOR_GREEN, COLOR_RED
from game.systems.navigation import compute_path_worldpoints, follow_path, best_adjacent_tile
from game.graphics.font_cache import get_font, render_text_cached
from game.sim.timebase import now_ms as sim_now_ms


class PeasantState(Enum):
    IN_CASTLE = auto()
    MOVING = auto()
    WORKING = auto()
    DEAD = auto()


class Peasant:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

        self.max_hp = 40
        self.hp = self.max_hp
        self.speed = 1.6
        self.size = 14

        self.state = PeasantState.MOVING
        self.target_building = None
        self.target_position = None
        self.is_inside_castle = False
        self.path = []
        self._path_goal = None
        # Backoff timer to avoid spamming A* when no path exists (or search budget bails out).
        self._next_replan_ms = 0

        self.color = (200, 180, 120)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def health_percent(self) -> float:
        return self.hp / self.max_hp if self.max_hp else 0.0

    def distance_to(self, x: float, y: float) -> float:
        return math.sqrt((self.x - x) ** 2 + (self.y - y) ** 2)

    def take_damage(self, amount: int) -> bool:
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.state = PeasantState.DEAD
            return True
        return False

    def move_towards(self, target_x: float, target_y: float, dt: float) -> bool:
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 3:
            self.x = target_x
            self.y = target_y
            return True
        if dist > 0:
            move_dist = self.speed * dt * 60
            self.x += (dx / dist) * move_dist
            self.y += (dy / dist) * move_dist
        return False

    def _adjacent_to_building(self, building) -> bool:
        """
        Returns True if the peasant is "adjacent" to the building footprint.

        Important: using distance-to-center breaks for large buildings (you can be right next
        to the wall but still far from the center). Instead, compute distance to the building
        rectangle in world-space.
        """
        rect = None
        if hasattr(building, "get_rect"):
            try:
                rect = building.get_rect()
            except Exception:
                rect = None

        if rect is None:
            # Fallback: best effort using center distance (kept for safety).
            dist = self.distance_to(getattr(building, "center_x", self.x), getattr(building, "center_y", self.y))
            return dist <= TILE_SIZE * 1.5

        # Distance from a point to an axis-aligned rectangle (0 if inside/on edge).
        dx = 0.0
        if self.x < rect.left:
            dx = rect.left - self.x
        elif self.x > rect.right:
            dx = self.x - rect.right

        dy = 0.0
        if self.y < rect.top:
            dy = rect.top - self.y
        elif self.y > rect.bottom:
            dy = self.y - rect.bottom

        dist = math.sqrt(dx * dx + dy * dy)
        # Adjacent tile centers are typically TILE_SIZE/2 away from the footprint edge.
        return dist <= TILE_SIZE * 0.75

    def _pick_build_target(self, buildings: list):
        # Priority 1: any unconstructed building (prefer ones not started, then oldest)
        candidates = [b for b in buildings if getattr(b, "is_constructed", True) is False and b.hp > 0]
        if not candidates:
            return None
        # Prefer unstarted construction, then oldest placement time
        candidates.sort(
            key=lambda b: (
                0 if getattr(b, "construction_started", False) is False else 1,
                getattr(b, "placed_time_ms", 0),
            )
        )
        return candidates[0]

    def _pick_repair_target(self, buildings: list):
        # Priority 2: repair constructed buildings that are damaged (lowest % HP first)
        candidates = [
            b
            for b in buildings
            if getattr(b, "is_constructed", True) is True and b.hp > 0 and b.hp < b.max_hp
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda b: (b.hp / b.max_hp))
        return candidates[0]

    def update(self, dt: float, game_state: dict):
        if not self.is_alive:
            return

        castle = game_state.get("castle")
        world = game_state.get("world")
        buildings = game_state.get("buildings", [])
        # Gnome hovel bonus: faster construction/repair for peasants.
        gnome_bonus = any(
            getattr(b, "building_type", "") == "gnome_hovel" and getattr(b, "is_constructed", True)
            for b in buildings
        )
        speed_mult = 1.5 if gnome_bonus else 1.0

        # Decide what to do each tick (simple, responsive)
        # Priority 1: repair castle if damaged
        castle_repair = castle if (castle and castle.hp > 0 and castle.hp < castle.max_hp) else None
        build_target = None if castle_repair else self._pick_build_target(buildings)
        repair_target = None
        if not castle_repair and not build_target:
            repair_target = self._pick_repair_target(buildings)

        # If something needs work, leave the castle immediately.
        if (castle_repair or build_target or repair_target) and self.is_inside_castle:
            self.is_inside_castle = False
            self.state = PeasantState.MOVING

        if castle_repair:
            self.target_building = castle_repair
            # Approach adjacent tile so we don't walk through the building.
            if world:
                adj = best_adjacent_tile(world, buildings, castle_repair, self.x, self.y)
                if adj:
                    self.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                else:
                    self.target_position = (castle_repair.center_x, castle_repair.center_y)
            else:
                self.target_position = (castle_repair.center_x, castle_repair.center_y)
        elif build_target:
            self.target_building = build_target
            if world:
                adj = best_adjacent_tile(world, buildings, build_target, self.x, self.y)
                if adj:
                    self.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                else:
                    self.target_position = (build_target.center_x, build_target.center_y)
            else:
                self.target_position = (build_target.center_x, build_target.center_y)
        elif repair_target:
            self.target_building = repair_target
            if world:
                adj = best_adjacent_tile(world, buildings, repair_target, self.x, self.y)
                if adj:
                    self.target_position = (adj[0] * TILE_SIZE + TILE_SIZE / 2, adj[1] * TILE_SIZE + TILE_SIZE / 2)
                else:
                    self.target_position = (repair_target.center_x, repair_target.center_y)
            else:
                self.target_position = (repair_target.center_x, repair_target.center_y)
        else:
            # Priority 4: go inside the castle
            self.target_building = None
            if castle:
                self.target_position = (castle.center_x, castle.center_y)
            else:
                self.target_position = None

        # If no target position, idle
        if not self.target_position:
            self.state = PeasantState.IN_CASTLE if self.is_inside_castle else PeasantState.MOVING
            return

        # Move toward target (pathfinding around buildings)
        reached = False
        if world and self.target_position:
            goal_x, goal_y = self.target_position
            goal_key = (int(goal_x), int(goal_y))

            # Avoid long-distance A*: far away, just head toward the goal; pathing matters most near buildings.
            dist_to_goal = self.distance_to(goal_x, goal_y)
            if dist_to_goal > TILE_SIZE * 12:
                reached = self.move_towards(goal_x, goal_y, dt)
            else:
                now_ms = sim_now_ms()
                want_replan = (not self.path) or (self._path_goal != goal_key)
                if want_replan and now_ms >= int(getattr(self, "_next_replan_ms", 0) or 0):
                    self.path = compute_path_worldpoints(world, buildings, self.x, self.y, goal_x, goal_y)
                    self._path_goal = goal_key
                    if not self.path:
                        # If no path, wait a bit before retrying to avoid CPU spikes.
                        self._next_replan_ms = now_ms + 800
                    else:
                        self._next_replan_ms = now_ms + 150

                if self.path:
                    follow_path(self, dt)
                    reached = self.distance_to(goal_x, goal_y) < 4
                else:
                    reached = self.move_towards(goal_x, goal_y, dt)
        else:
            reached = self.move_towards(self.target_position[0], self.target_position[1], dt)

        # Handle inside-castle behavior
        if castle and self.target_building is None:
            if reached or self.distance_to(castle.center_x, castle.center_y) < TILE_SIZE * 1.5:
                self.is_inside_castle = True
                self.state = PeasantState.IN_CASTLE
                self.x = castle.center_x
                self.y = castle.center_y
                return

        # Work on building if adjacent
        if self.target_building and self._adjacent_to_building(self.target_building):
            self.state = PeasantState.WORKING
            # Become targetable as soon as we begin building.
            if hasattr(self.target_building, "start_construction"):
                self.target_building.start_construction()
            if hasattr(self.target_building, "apply_work"):
                # Construction is fast (10x) to support rapid iteration; repairs remain at the base rate.
                is_constructed = getattr(self.target_building, "is_constructed", True)
                rate = (0.10 if not is_constructed else 0.01) * speed_mult
                done = self.target_building.apply_work(dt, percent_per_sec=rate)
                if done:
                    self.target_building = None
            return

        self.state = PeasantState.MOVING

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        if not self.is_alive:
            return
        if self.is_inside_castle:
            return

        cam_x, cam_y = camera_offset
        sx = self.x - cam_x
        sy = self.y - cam_y

        pygame.draw.circle(surface, self.color, (int(sx), int(sy)), self.size // 2)
        pygame.draw.circle(surface, COLOR_WHITE, (int(sx), int(sy)), self.size // 2, 1)
        
        # Draw peasant symbol (P for Peasant)
        # Cache the font + static glyph surface (cheap per-frame blit).
        _ = get_font(14)
        symbol_text = render_text_cached(14, "P", COLOR_WHITE)
        symbol_rect = symbol_text.get_rect(center=(int(sx), int(sy)))
        surface.blit(symbol_text, symbol_rect)

        # Health bar
        bar_w = self.size + 8
        bar_h = 3
        bx = sx - bar_w // 2
        by = sy - self.size // 2 - 7
        pygame.draw.rect(surface, (60, 60, 60), (bx, by, bar_w, bar_h))
        hc = COLOR_GREEN if self.health_percent > 0.5 else COLOR_RED
        pygame.draw.rect(surface, hc, (bx, by, bar_w * self.health_percent, bar_h))


