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
from game.graphics.worker_sprites import WorkerSpriteLibrary


class PeasantState(Enum):
    IN_CASTLE = auto()
    MOVING = auto()
    WORKING = auto()
    DEAD = auto()


class Peasant:
    _spawn_counter = 0
    _idle_offsets = [
        (TILE_SIZE * 0.9, 0.0),
        (-TILE_SIZE * 0.9, 0.0),
        (0.0, TILE_SIZE * 0.9),
        (0.0, -TILE_SIZE * 0.9),
        (TILE_SIZE * 0.7, TILE_SIZE * 0.7),
        (-TILE_SIZE * 0.7, TILE_SIZE * 0.7),
        (TILE_SIZE * 0.7, -TILE_SIZE * 0.7),
        (-TILE_SIZE * 0.7, -TILE_SIZE * 0.7),
    ]

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

        self.color = (200, 180, 120)

        # Deterministic idle slot so multiple peasants don't overlap.
        slot = Peasant._spawn_counter % len(Peasant._idle_offsets)
        Peasant._spawn_counter += 1
        self._idle_offset = Peasant._idle_offsets[slot]
        self._idle_outside = False

        # Animation / sprite rendering (pixel-art sprites; falls back procedurally if no assets exist)
        self._anim = WorkerSpriteLibrary.create_player("peasant", size=32)
        self._anim_base = "idle"
        self._anim_lock_one_shot = None
        self._last_hp = self.hp

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
            if hasattr(self, "_anim") and self._anim is not None:
                self._anim_lock_one_shot = "dead"
                self._anim.play("dead", restart=True)
            return True
        # Trigger hurt animation if damaged
        if hasattr(self, "_anim") and self._anim is not None and self.hp < self._last_hp:
            self._anim_lock_one_shot = "hurt"
            self._anim.play("hurt", restart=True)
        self._last_hp = self.hp
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
        # Adjacent ~= within ~1 tile of building edge/center (simple heuristic)
        dist = self.distance_to(building.center_x, building.center_y)
        return dist <= TILE_SIZE * 1.5

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
            self.target_position = (castle_repair.center_x, castle_repair.center_y)
            self._idle_outside = False
        elif build_target:
            self.target_building = build_target
            tx, ty = build_target.center_x, build_target.center_y
            self.target_position = (tx, ty)
            self._idle_outside = False
        elif repair_target:
            self.target_building = repair_target
            tx, ty = repair_target.center_x, repair_target.center_y
            self.target_position = (tx, ty)
            self._idle_outside = False
        else:
            # Priority 4: idle near the castle unless it's under attack.
            self.target_building = None
            if castle:
                if getattr(castle, "is_under_attack", False):
                    self._idle_outside = False
                    self.target_position = (castle.center_x, castle.center_y)
                else:
                    self._idle_outside = True
                    self.is_inside_castle = False
                    ox, oy = self._idle_offset
                    self.target_position = (castle.center_x + ox, castle.center_y + oy)
            else:
                self.target_position = None
                self._idle_outside = False

        # If no target position, idle
        if not self.target_position:
            self.state = PeasantState.IN_CASTLE if self.is_inside_castle else PeasantState.MOVING
            return

        # Move toward target
        reached = self.move_towards(self.target_position[0], self.target_position[1], dt)

        # Handle inside-castle behavior
        if castle and self.target_building is None and not self._idle_outside:
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

        # Update animation
        self._update_animation(dt)

    def _update_animation(self, dt: float):
        if not hasattr(self, "_anim") or self._anim is None:
            return

        if self._anim_lock_one_shot:
            if self._anim.current != self._anim_lock_one_shot:
                self._anim.play(self._anim_lock_one_shot, restart=True)
            self._anim.update(dt)
            if self._anim.finished:
                self._anim_lock_one_shot = None
                self._anim.play(self._anim_base, restart=True)
            return

        # Select base animation based on state
        if self.state == PeasantState.DEAD:
            self._anim_base = "dead"
        elif self.state == PeasantState.WORKING:
            self._anim_base = "work"
        elif self.state == PeasantState.MOVING:
            self._anim_base = "walk"
        else:
            self._anim_base = "idle"

        self._anim.play(self._anim_base, restart=False)
        self._anim.update(dt)

    def render(self, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        if not self.is_alive:
            return
        if self.is_inside_castle:
            return

        cam_x, cam_y = camera_offset
        sx = self.x - cam_x
        sy = self.y - cam_y

        # Sprite render (procedural fallback until art exists)
        if hasattr(self, "_anim") and self._anim is not None:
            frame = self._anim.frame()
            fw, fh = frame.get_width(), frame.get_height()
            surface.blit(frame, (int(sx - fw // 2), int(sy - fh // 2)))
        else:
            # Fallback: old glyph render
            pygame.draw.circle(surface, self.color, (int(sx), int(sy)), self.size // 2)
            pygame.draw.circle(surface, COLOR_WHITE, (int(sx), int(sy)), self.size // 2, 1)
            font = pygame.font.Font(None, 14)
            symbol_text = font.render("P", True, COLOR_WHITE)
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


