from __future__ import annotations

import math
import random
import zlib
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


@dataclass
class ProjectileVFX:
    """Visual-only projectile (arrow/bolt) traveling from source to target."""
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    progress: float  # 0.0 to 1.0 (0 = at source, 1 = at target)
    lifetime: float  # Total travel time in seconds
    age: float  # Current age in seconds
    color: Tuple[int, int, int]  # Wood brown for arrows
    tip_color: Tuple[int, int, int]  # Bright tip pixel
    size_px: int  # 1, 2, or 3 pixels (default 2)


@dataclass
class DebrisDecal:
    """Visual-only debris/rubble left behind after building destruction."""
    x: float
    y: float
    building_type: str  # For deterministic pattern variation
    pattern_seed: int  # Deterministic seed for debris pattern
    w: float = 0.0  # Building footprint width (0 = use default radius)
    h: float = 0.0  # Building footprint height (0 = use default radius)


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
        self._projectiles: List[ProjectileVFX] = []
        self._debris: List[DebrisDecal] = []  # WK5 Build B: building debris decals
        self.enabled = True

    def emit_from_events(self, events: list[dict]):
        if not self.enabled:
            return
        for e in events or []:
            et = e.get("type")
            if et == "ranged_projectile":
                # WK5: Handle ranged projectile events (these do not use generic x/y fields)
                from_x = e.get("from_x")
                from_y = e.get("from_y")
                to_x = e.get("to_x")
                to_y = e.get("to_y")
                if from_x is not None and from_y is not None and to_x is not None and to_y is not None:
                    kind = e.get("projectile_kind", "arrow")
                    color = e.get("color")
                    size_px = e.get("size_px", 2)  # Build B: default 2px for readability
                    self._spawn_projectile(
                        float(from_x), float(from_y),
                        float(to_x), float(to_y),
                        kind, color, size_px
                    )
                continue

            # World-space burst events require x/y
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
            elif et == "building_destroyed":
                # WK5 Build B: Spawn debris decal at building location
                building_type = e.get("building_type", "unknown")
                w = e.get("w", 0.0)  # Footprint width (optional, 0 = use default)
                h = e.get("h", 0.0)  # Footprint height (optional, 0 = use default)
                self._spawn_debris(float(x), float(y), building_type, float(w), float(h))

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

    def _spawn_projectile(self, from_x: float, from_y: float, to_x: float, to_y: float,
                          kind: str, color: Optional[Tuple[int, int, int]], size_px: int):
        """
        Spawn a visual-only projectile (arrow/bolt) traveling from source to target.
        
        WK5 Build B: Improved readability
        - Color: Warm wood brown (#8B4513) for arrows
        - Tip highlight: Bright near-white pixel (#F5F5F5) at leading edge
        - Size: Default 2px, optional 3px variant (tip + shaft + tiny trail)
        - Lifetime: 250-450ms travel time (visible mid-flight)
        - Deterministic: seeded RNG from event fields
        """
        # Deterministic seed from event fields (not wall-clock)
        seed = (int(from_x) << 16) ^ int(from_y) ^ (int(to_x) << 8) ^ int(to_y) ^ 0x4A2B
        rnd = random.Random(seed)
        
        # Lifetime: 250-450ms (0.25-0.45 seconds) with deterministic jitter for visibility
        lifetime = 0.25 + rnd.random() * 0.20
        
        # Color: always use warm wood brown (art contract: same color for all ranged attackers)
        # Warm wood brown: SaddleBrown #8B4513 = (139, 69, 19)
        color = (139, 69, 19)
        
        # Tip color: bright near-white for visibility on dark backgrounds
        tip_color = (245, 245, 245)  # #F5F5F5
        
        # Size: default 2px, allow up to 3px for variants
        # If size_px is 1 or unset, default to 2px for Build B readability
        if size_px < 1:
            size_px = 2
        size_px = max(1, min(3, int(size_px)))
        if size_px == 1:
            size_px = 2  # Upgrade 1px to 2px for Build B
        
        self._projectiles.append(
            ProjectileVFX(
                from_x=from_x,
                from_y=from_y,
                to_x=to_x,
                to_y=to_y,
                progress=0.0,
                lifetime=lifetime,
                age=0.0,
                color=color,
                tip_color=tip_color,
                size_px=size_px,
            )
        )

    def _spawn_debris(self, x: float, y: float, building_type: str, w: float = 0.0, h: float = 0.0):
        """
        Spawn visual-only debris/rubble decal at building destruction site.
        
        WK5 Hotfix: Enhanced visibility with footprint-based scattering.
        - 10-25 pieces across footprint (or default radius if w/h not provided)
        - 2-3px chunks, higher contrast, darker underlay patch
        - Debris persists (no fade-out)
        """
        # Deterministic seed from position and building type
        # NOTE: Do NOT use Python's built-in hash() here; it is salted per-process and breaks determinism.
        bt_hash = int(zlib.crc32(str(building_type).encode("utf-8"))) & 0xFFFFFFFF
        seed = (int(x) << 16) ^ int(y) ^ bt_hash ^ 0xDEB715
        pattern_seed = seed
        
        self._debris.append(
            DebrisDecal(
                x=x,
                y=y,
                building_type=building_type,
                pattern_seed=pattern_seed,
                w=w,
                h=h,
            )
        )

    def update(self, dt: float):
        if not self.enabled:
            self._particles.clear()
            self._projectiles.clear()
            self._debris.clear()
            return
        dt = float(dt)
        if dt <= 0:
            return

        # Update particles (existing hit/kill/big bursts)
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
        
        # Update projectiles (WK5: visual-only arrows/bolts)
        active_projectiles: List[ProjectileVFX] = []
        for proj in self._projectiles:
            proj.age += dt
            if proj.age >= proj.lifetime:
                continue  # Expired
            # Update progress (0.0 to 1.0)
            proj.progress = proj.age / proj.lifetime
            active_projectiles.append(proj)
        self._projectiles = active_projectiles

    def render(self, surface: pygame.Surface, camera_offset: tuple[int, int] = (0, 0)):
        if not self.enabled:
            return
        cam_x, cam_y = camera_offset
        
        # Render particles (existing hit/kill/big bursts)
        for p in self._particles:
            sx = int(p.x - cam_x)
            sy = int(p.y - cam_y)
            # Pixel-y squares (no alpha blending for crispness)
            pygame.draw.rect(surface, p.color, pygame.Rect(sx, sy, int(p.size), int(p.size)))
        
        # Render projectiles (WK5: visual-only arrows/bolts)
        for proj in self._projectiles:
            # Interpolate position from source to target
            current_x = proj.from_x + (proj.to_x - proj.from_x) * proj.progress
            current_y = proj.from_y + (proj.to_y - proj.from_y) * proj.progress
            
            sx = int(current_x - cam_x)
            sy = int(current_y - cam_y)
            
            # Calculate direction vector for arrow orientation
            dx = proj.to_x - proj.from_x
            dy = proj.to_y - proj.from_y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 0.1:
                # Normalize direction
                dx_norm = dx / dist
                dy_norm = dy / dist
            else:
                dx_norm = 1.0
                dy_norm = 0.0
            
            # Render arrow/bolt with bright tip + shaft + optional trail
            # Build B: Improved rendering for 2px (default) and 3px (variant)
            if proj.size_px == 1:
                # Single pixel: bright tip (fallback, should be rare in Build B)
                pygame.draw.rect(surface, proj.tip_color, pygame.Rect(sx, sy, 1, 1))
            elif proj.size_px == 2:
                # 2 px: tip + shaft (default for Build B)
                # Leading edge (bright tip)
                tip_x = int(sx + dx_norm * 1.5)
                tip_y = int(sy + dy_norm * 1.5)
                pygame.draw.rect(surface, proj.tip_color, pygame.Rect(tip_x, tip_y, 1, 1))
                # Trailing edge (shaft)
                pygame.draw.rect(surface, proj.color, pygame.Rect(sx, sy, 1, 1))
            else:  # size_px == 3
                # 3 px: tip + shaft + tiny trail (variant for better visibility)
                # Leading edge (bright tip)
                tip_x = int(sx + dx_norm * 2)
                tip_y = int(sy + dy_norm * 2)
                pygame.draw.rect(surface, proj.tip_color, pygame.Rect(tip_x, tip_y, 1, 1))
                # Middle (shaft)
                mid_x = int(sx + dx_norm * 1)
                mid_y = int(sy + dy_norm * 1)
                pygame.draw.rect(surface, proj.color, pygame.Rect(mid_x, mid_y, 1, 1))
                # Trailing edge (darker trail for motion blur effect)
                trail_color = (int(proj.color[0] * 0.7), int(proj.color[1] * 0.7), int(proj.color[2] * 0.7))
                pygame.draw.rect(surface, trail_color, pygame.Rect(sx, sy, 1, 1))
        
        # Render debris decals (WK5 Hotfix: enhanced visibility with footprint-based scattering)
        for debris in self._debris:
            sx = int(debris.x - cam_x)
            sy = int(debris.y - cam_y)
            
            # Deterministic debris pattern based on seed
            rnd = random.Random(debris.pattern_seed)
            
            # Determine scatter area: use footprint if provided, otherwise default radius
            if debris.w > 0 and debris.h > 0:
                # Use footprint dimensions (scatter across building area)
                scatter_w = debris.w / 2.0  # Half-width for radius-like behavior
                scatter_h = debris.h / 2.0  # Half-height
                num_pieces = 10 + rnd.randint(0, 15)  # 10-25 pieces (WK5 Hotfix: more visible)
            else:
                # Fallback: default small radius (for backwards compatibility)
                scatter_w = scatter_h = 20.0
                num_pieces = 3 + rnd.randint(0, 3)  # 3-6 pieces (original)
            
            # WK5 Hotfix: Draw darker underlay patch for contrast
            if debris.w > 0 and debris.h > 0:
                # Darker underlay patch (subtle, doesn't block visibility)
                underlay_rect = pygame.Rect(
                    sx - int(scatter_w), sy - int(scatter_h),
                    int(scatter_w * 2), int(scatter_h * 2)
                )
                # Semi-transparent dark patch (very subtle)
                underlay_surf = pygame.Surface((underlay_rect.width, underlay_rect.height), pygame.SRCALPHA)
                underlay_surf.fill((20, 20, 20, 30))  # Very subtle dark patch
                surface.blit(underlay_surf, underlay_rect)
            
            # Generate rubble pieces across footprint
            for i in range(num_pieces):
                # Offset from center (deterministic, uniform distribution across footprint)
                if debris.w > 0 and debris.h > 0:
                    # Uniform distribution across footprint
                    px = sx + int((rnd.random() - 0.5) * scatter_w * 2)
                    py = sy + int((rnd.random() - 0.5) * scatter_h * 2)
                else:
                    # Fallback: circular distribution
                    angle = rnd.random() * 6.283  # 0 to 2π
                    radius = 8 + rnd.random() * 12  # 8-20 pixels from center
                    px = sx + int(math.cos(angle) * radius)
                    py = sy + int(math.sin(angle) * radius)
                
                # WK5 Hotfix: Higher contrast debris colors (2-3px chunks)
                # Dark gray/brown rubble with better contrast
                base_gray = 80 + rnd.randint(0, 50)  # Brighter base (80-130 vs 60-100)
                debris_color = (base_gray, base_gray - 15, base_gray - 25)  # More contrast
                
                # WK5 Hotfix: 2-3px chunks (was 1-2px)
                size = 2 + rnd.randint(0, 1)  # 2-3px (was 1-2px)
                pygame.draw.rect(surface, debris_color, pygame.Rect(px, py, size, size))


