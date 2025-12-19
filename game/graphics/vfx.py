from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame


@dataclass
class VFXParticle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    color: Tuple[int, int, int]
    size: int = 2


class VFXSystem:
    """
    Tiny, non-blocking VFX system meant for quick combat readability.

    Expected engine integration:
    - update(dt)
    - render(surface, camera_offset)
    - emit_from_events(events)
    """

    def __init__(self):
        self._particles: List[VFXParticle] = []
        self.enabled = True

    def emit_from_events(self, events: list[dict]):
        if not self.enabled:
            return
        for e in events or []:
            et = e.get("type")
            x = e.get("x")
            y = e.get("y")
            if x is None or y is None:
                continue

            if et in ("hero_attack", "hero_attack_lair"):
                self._spawn_hit(float(x), float(y))
            elif et == "enemy_killed":
                self._spawn_kill(float(x), float(y))
            elif et == "lair_cleared":
                self._spawn_big(float(x), float(y))

    def _spawn_hit(self, x: float, y: float):
        rnd = random.Random((int(x) << 16) ^ int(y))
        for _ in range(6):
            ang = rnd.random() * 6.283
            spd = 35 + rnd.random() * 55
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd
            self._particles.append(
                VFXParticle(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    life=0.22 + rnd.random() * 0.10,
                    color=(255, 220, 120),
                    size=2,
                )
            )

    def _spawn_kill(self, x: float, y: float):
        rnd = random.Random((int(x) << 16) ^ int(y) ^ 0xBEEF)
        for _ in range(10):
            ang = rnd.random() * 6.283
            spd = 20 + rnd.random() * 60
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd
            col = (240, 240, 240) if rnd.random() < 0.6 else (180, 180, 180)
            self._particles.append(
                VFXParticle(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy - 20.0,
                    life=0.35 + rnd.random() * 0.20,
                    color=col,
                    size=2,
                )
            )

    def _spawn_big(self, x: float, y: float):
        rnd = random.Random((int(x) << 16) ^ int(y) ^ 0xCAFE)
        for _ in range(18):
            ang = rnd.random() * 6.283
            spd = 30 + rnd.random() * 90
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd
            col = (255, 210, 70) if rnd.random() < 0.7 else (255, 120, 80)
            self._particles.append(
                VFXParticle(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy,
                    life=0.45 + rnd.random() * 0.25,
                    color=col,
                    size=3,
                )
            )

    def update(self, dt: float):
        if not self.enabled:
            self._particles.clear()
            return
        dt = float(dt)
        if dt <= 0:
            return

        alive: List[VFXParticle] = []
        for p in self._particles:
            p.life -= dt
            if p.life <= 0:
                continue
            # basic drag + gravity
            p.vx *= 0.90
            p.vy = p.vy * 0.90 + 35.0 * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self._particles = alive

    def render(self, surface: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)):
        if not self.enabled:
            return
        cam_x, cam_y = camera_offset
        for p in self._particles:
            sx = int(p.x - cam_x)
            sy = int(p.y - cam_y)
            # Pixel-y squares (no alpha blending for crispness)
            pygame.draw.rect(surface, p.color, pygame.Rect(sx, sy, int(p.size), int(p.size)))


