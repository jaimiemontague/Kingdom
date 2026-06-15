from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

import pygame

from config import TILE_SIZE
from game.graphics.font_cache import render_text_shadowed_cached


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
    kind: str = "arrow"  # WK124-T3c/T4c: "arrow" (default) | "magic" | "heal" — picks the 3D billboard

    @property
    def x(self) -> float:
        """World pixel X (matches VFX render interpolation; Ursina billboards use this)."""
        return self.from_x + (self.to_x - self.from_x) * self.progress

    @property
    def y(self) -> float:
        """World pixel Y (matches VFX render interpolation)."""
        return self.from_y + (self.to_y - self.from_y) * self.progress


@dataclass
class DebrisDecal:
    """Visual-only debris/rubble left behind after building destruction."""
    x: float
    y: float
    building_type: str  # For deterministic pattern variation
    pattern_seed: int  # Deterministic seed for debris pattern
    w: float = 0.0  # Building footprint width (0 = use default radius)
    h: float = 0.0  # Building footprint height (0 = use default radius)


@dataclass
class BossTelegraphVFX:
    boss_id: str
    boss_type: str
    boss_name: str
    ability_id: str
    ability_name: str
    current_phase_title: str
    telegraph_ms: int
    resolve_at_ms: int
    started_at_ms: int
    warning_event: str = ""
    impact_event: str = ""
    shape: str = ""
    range_tiles: float = 0.0
    angle_degrees: float = 0.0
    origin_position: tuple[float, float] | None = None
    target_position: tuple[float, float] | None = None
    direction: tuple[float, float] | None = None
    target_hero_id: str = ""
    target_hero_name: str = ""
    life_sec: float = 0.0
    age_sec: float = 0.0


@dataclass
class BossImpactVFX:
    boss_id: str
    boss_type: str
    boss_name: str
    ability_id: str
    ability_name: str
    current_phase_title: str
    impact_event: str
    shape: str
    range_tiles: float
    angle_degrees: float
    origin_position: tuple[float, float] | None
    target_position: tuple[float, float] | None
    direction: tuple[float, float] | None
    life_sec: float
    age_sec: float = 0.0


def _point_from_value(value: object) -> tuple[float, float] | None:
    try:
        if value is None:
            return None
        x, y = value[:2]
        return float(x), float(y)
    except Exception:
        return None


def _normalize_vector(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return (1.0, 0.0)
    return (dx / length, dy / length)


def _rotate_vector(dx: float, dy: float, angle_degrees: float) -> tuple[float, float]:
    radians = math.radians(float(angle_degrees))
    cos_a = math.cos(radians)
    sin_a = math.sin(radians)
    return (dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a)


def _point_add(point: tuple[float, float], vec: tuple[float, float], scale: float) -> tuple[float, float]:
    return (point[0] + vec[0] * scale, point[1] + vec[1] * scale)


def _cone_points(
    origin: tuple[float, float],
    direction: tuple[float, float],
    *,
    length: float,
    angle_degrees: float,
    steps: int = 7,
) -> list[tuple[int, int]]:
    points = [(int(round(origin[0])), int(round(origin[1])))]
    half_angle = max(4.0, min(85.0, float(angle_degrees) / 2.0))
    if steps < 3:
        steps = 3
    for idx in range(steps + 1):
        frac = idx / float(steps)
        ang = -half_angle + (2.0 * half_angle * frac)
        vec = _rotate_vector(direction[0], direction[1], ang)
        px, py = _point_add(origin, vec, length)
        points.append((int(round(px)), int(round(py))))
    return points


def _blit_polygon_overlay(
    surface: pygame.Surface,
    points: list[tuple[int, int]],
    *,
    fill_color: tuple[int, int, int, int],
    edge_color: tuple[int, int, int, int],
    extra_pad: int = 6,
) -> None:
    if len(points) < 3:
        return
    xs = [pt[0] for pt in points]
    ys = [pt[1] for pt in points]
    left = max(0, min(xs) - extra_pad)
    top = max(0, min(ys) - extra_pad)
    right = min(surface.get_width(), max(xs) + extra_pad + 1)
    bottom = min(surface.get_height(), max(ys) + extra_pad + 1)
    if right <= left or bottom <= top:
        return

    overlay = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA)
    shifted = [(x - left, y - top) for x, y in points]
    pygame.draw.polygon(overlay, fill_color, shifted)
    pygame.draw.polygon(overlay, edge_color, shifted, 2)
    surface.blit(overlay, (left, top))


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
        self._boss_telegraphs: dict[str, BossTelegraphVFX] = {}
        self._boss_impacts: dict[str, BossImpactVFX] = {}
        self.enabled = True

    def get_active_projectiles(self) -> List[ProjectileVFX]:
        """Snapshot for external renderers (e.g. Ursina 3D) without exposing private lists."""
        return list(self._projectiles)

    def emit_from_events(self, events: list[dict]):
        if not self.enabled:
            return
        for e in events or []:
            self._emit_event(e)

    def on_event(self, event: dict):
        """
        EventBus subscriber callback for single event dispatch.
        """
        if not self.enabled:
            return
        self._emit_event(event)

    def _emit_event(self, event: dict):
        et = event.get("type")
        if et in ("boss_ability_telegraphed", "boss_ability_resolved", "boss_defeated", "boss_phase_changed"):
            boss_id = str(event.get("boss_id", "") or "").strip()
            if boss_id:
                if et == "boss_ability_telegraphed":
                    telegraph_ms = int(event.get("telegraph_ms", 0) or 0)
                    self._boss_telegraphs[boss_id] = BossTelegraphVFX(
                        boss_id=boss_id,
                        boss_type=str(event.get("boss_type", "") or ""),
                        boss_name=str(event.get("name", "") or ""),
                        ability_id=str(event.get("ability_id", "") or ""),
                        ability_name=str(
                            event.get("ability_name", "")
                            or event.get("detail", "")
                            or event.get("ability_id", "")
                            or ""
                        ),
                        current_phase_title=str(event.get("current_phase_title", "") or ""),
                        telegraph_ms=telegraph_ms,
                        resolve_at_ms=int(event.get("resolve_at_ms", 0) or 0),
                        started_at_ms=int(event.get("time_ms", 0) or 0),
                        warning_event=str(event.get("warning_event", "") or event.get("detail", "") or ""),
                        impact_event=str(event.get("impact_event", "") or ""),
                        shape=str(event.get("shape", "") or ""),
                        range_tiles=float(event.get("range_tiles", event.get("range", 0.0)) or 0.0),
                        angle_degrees=float(event.get("angle_degrees", 0.0) or 0.0),
                        origin_position=_point_from_value(event.get("origin_position")),
                        target_position=_point_from_value(event.get("target_position")),
                        direction=_point_from_value(event.get("direction")),
                        target_hero_id=str(event.get("target_hero_id", "") or ""),
                        target_hero_name=str(event.get("target_hero_name", "") or ""),
                        life_sec=max(0.35, float(telegraph_ms) / 1000.0 if telegraph_ms > 0 else 0.4),
                    )
                elif et == "boss_ability_resolved":
                    telegraph = self._boss_telegraphs.pop(boss_id, None)
                    telegraph_ms = int(event.get("telegraph_ms", 0) or getattr(telegraph, "telegraph_ms", 0) or 0)
                    self._boss_impacts[boss_id] = BossImpactVFX(
                        boss_id=boss_id,
                        boss_type=str(event.get("boss_type", "") or getattr(telegraph, "boss_type", "") or ""),
                        boss_name=str(event.get("name", "") or getattr(telegraph, "boss_name", "") or ""),
                        ability_id=str(event.get("ability_id", "") or getattr(telegraph, "ability_id", "") or ""),
                        ability_name=str(
                            event.get("ability_name", "")
                            or getattr(telegraph, "ability_name", "")
                            or event.get("detail", "")
                            or ""
                        ),
                        current_phase_title=str(
                            event.get("current_phase_title", "")
                            or getattr(telegraph, "current_phase_title", "")
                            or ""
                        ),
                        impact_event=str(event.get("impact_event", "") or event.get("detail", "") or getattr(telegraph, "impact_event", "") or ""),
                        shape=str(event.get("shape", "") or getattr(telegraph, "shape", "") or ""),
                        range_tiles=float(event.get("range_tiles", event.get("range", getattr(telegraph, "range_tiles", 0.0))) or getattr(telegraph, "range_tiles", 0.0) or 0.0),
                        angle_degrees=float(event.get("angle_degrees", getattr(telegraph, "angle_degrees", 0.0)) or getattr(telegraph, "angle_degrees", 0.0) or 0.0),
                        origin_position=_point_from_value(event.get("origin_position"))
                        or getattr(telegraph, "origin_position", None),
                        target_position=_point_from_value(event.get("target_position"))
                        or getattr(telegraph, "target_position", None),
                        direction=_point_from_value(event.get("direction"))
                        or getattr(telegraph, "direction", None),
                        life_sec=max(0.28, min(0.60, float(telegraph_ms) / 3000.0 if telegraph_ms > 0 else 0.42)),
                    )
                elif et == "boss_phase_changed":
                    current_phase = str(event.get("current_phase", "") or "")
                    if current_phase and current_phase != "rally":
                        self._boss_telegraphs.pop(boss_id, None)
                    self._boss_impacts.pop(boss_id, None)
                else:
                    self._boss_telegraphs.pop(boss_id, None)
                    self._boss_impacts.pop(boss_id, None)
            return
        if et == "ranged_projectile":
            # WK5: Handle ranged projectile events (these do not use generic x/y fields)
            from_x = event.get("from_x")
            from_y = event.get("from_y")
            to_x = event.get("to_x")
            to_y = event.get("to_y")
            if from_x is not None and from_y is not None and to_x is not None and to_y is not None:
                kind = event.get("projectile_kind", "arrow")
                color = event.get("color")
                size_px = event.get("size_px", 2)  # Build B: default 2px for readability
                self._spawn_projectile(
                    float(from_x), float(from_y),
                    float(to_x), float(to_y),
                    kind, color, size_px
                )
            return

        # World-space burst events require x/y
        x = event.get("x")
        y = event.get("y")
        if x is None or y is None:
            return

        if et == "hero_heal":
            # WK124-T4c: cleric heal — green/gold particle burst on the healed
            # target (pygame) PLUS a short-lived green heal bolt from the cleric
            # to the target (so it reads in the Ursina 3D billboard path too).
            self._spawn_heal(float(x), float(y))
            from_x = event.get("from_x")
            from_y = event.get("from_y")
            if from_x is not None and from_y is not None:
                self._spawn_projectile(
                    float(from_x), float(from_y),
                    float(x), float(y),
                    "heal", None, 3,
                )
            return

        if et in ("hero_attack", "hero_attack_lair"):
            self._spawn_hit(float(x), float(y))
        elif et == "enemy_killed":
            self._spawn_kill(float(x), float(y))
        elif et == "lair_cleared":
            self._spawn_big(float(x), float(y))
        elif et == "building_destroyed":
            # WK5 Build B: Spawn debris decal at building location
            building_type = event.get("building_type", "unknown")
            w = event.get("w", 0.0)  # Footprint width (optional, 0 = use default)
            h = event.get("h", 0.0)  # Footprint height (optional, 0 = use default)
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

    def _spawn_heal(self, x: float, y: float):
        """WK124-T4c: cleric heal burst — gentle GREEN/GOLD motes rising on the
        healed ally (modeled on ``_spawn_big`` but lighter/upward). Deterministic
        position-seeded RNG — no wall-clock/global randomness."""
        rnd = random.Random((int(x) << 16) ^ int(y) ^ 0x4EA1)
        for _ in range(14):
            ang = rnd.random() * 6.283
            spd = 18 + rnd.random() * 50
            vx = math.cos(ang) * spd
            vy = math.sin(ang) * spd
            # Mostly soft green with a few gold sparkles; bias velocity upward.
            col = (120, 230, 130) if rnd.random() < 0.7 else (255, 225, 120)
            self._particles.append(
                VFXParticle(
                    x=x,
                    y=y,
                    vx=vx,
                    vy=vy - 45.0,  # rise (counteracts gravity in update())
                    life=0.40 + rnd.random() * 0.25,
                    color=col,
                    size=2 + rnd.randint(0, 1),
                )
            )

    def _spawn_projectile(self, from_x: float, from_y: float, to_x: float, to_y: float,
                          kind: str, color: Optional[Tuple[int, int, int]], size_px: int):
        """
        Spawn a visual-only projectile traveling from source to target.

        WK5 Build B (arrows): Improved readability
        - Color: Warm wood brown (#8B4513) for arrows
        - Tip highlight: Bright near-white pixel (#F5F5F5) at leading edge
        - Size: Default 2px, optional 3px variant (tip + shaft + tiny trail)
        - Lifetime: 250-450ms travel time (visible mid-flight)
        - Deterministic: seeded RNG from event fields

        WK124 (kinds): ``kind`` selects the 3D billboard in the Ursina sync.
        - "arrow" (default): wood-brown arrow (unchanged behavior).
        - "magic":  wizard spell — arcane purple orb (color from spec).
        - "heal":   cleric heal bolt — green orb (T4c).
        For "magic"/"heal" the spec ``color`` is honored (not overridden); for
        "arrow" the art-contract brown is always used.
        """
        # Deterministic seed from event fields (not wall-clock)
        seed = (int(from_x) << 16) ^ int(from_y) ^ (int(to_x) << 8) ^ int(to_y) ^ 0x4A2B
        rnd = random.Random(seed)

        # Lifetime: 250-450ms (0.25-0.45 seconds) with deterministic jitter for visibility
        lifetime = 0.25 + rnd.random() * 0.20

        kind = (kind or "arrow")
        if kind == "magic":
            # WK124-T3c: wizard spell — arcane purple orb, use the spec color/size.
            # Core color from spec (default WIZARD_SPELL_COLOR), bright lilac highlight.
            color = tuple(color) if color else (170, 90, 230)
            tip_color = (235, 200, 255)  # bright lilac highlight
            size_px = max(2, min(4, int(size_px) if size_px else 4))
        elif kind == "heal":
            # WK124-T4c: cleric heal bolt — green core, pale-gold highlight.
            color = tuple(color) if color else (90, 220, 120)
            tip_color = (235, 255, 200)  # pale gold-green highlight
            size_px = max(2, min(4, int(size_px) if size_px else 3))
        else:
            # Arrows: always warm wood brown (art contract: same color for all
            # arrow attackers) + bright near-white tip on dark backgrounds.
            kind = "arrow"
            color = (139, 69, 19)  # SaddleBrown #8B4513
            tip_color = (245, 245, 245)  # #F5F5F5
            # Size: default 2px, allow up to 3px for variants
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
                kind=kind,
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

    def _render_boss_telegraphs(
        self,
        surface: pygame.Surface,
        camera_offset: tuple[int, int],
        *,
        boss_encounters: tuple | list | None = None,
        visible_enemy_ids: set[str] | None = None,
        visible_enemy_dtos: dict[str, object] | None = None,
        hero_dtos: tuple | list | None = None,
    ) -> None:
        if not (self._boss_telegraphs or self._boss_impacts) or not boss_encounters:
            return

        cam_x, cam_y = camera_offset
        boss_views = {
            str(getattr(boss, "boss_id", "") or ""): boss
            for boss in boss_encounters
            if str(getattr(boss, "boss_id", "") or "")
        }
        if not boss_views:
            return

        visible_dtos = visible_enemy_dtos or {}
        hero_views: dict[str, tuple[float, float]] = {}
        for hero in hero_dtos or ():
            hero_id = str(getattr(hero, "hero_id", "") or getattr(hero, "entity_id", "") or "").strip()
            if not hero_id:
                continue
            try:
                hero_views[hero_id] = (float(getattr(hero, "x", 0.0)), float(getattr(hero, "y", 0.0)))
            except Exception:
                continue

        def _nearest_hero_position(origin: tuple[float, float] | None) -> tuple[float, float] | None:
            if not hero_views:
                return None
            if origin is None:
                return next(iter(hero_views.values()))
            ox, oy = origin
            return min(
                hero_views.values(),
                key=lambda pos: (pos[0] - ox) ** 2 + (pos[1] - oy) ** 2,
            )

        def _resolve_geometry(
            boss_id: str,
            *,
            telegraph: BossTelegraphVFX | None = None,
            impact: BossImpactVFX | None = None,
        ) -> dict[str, object] | None:
            boss_snapshot = boss_views.get(boss_id)
            dto = visible_dtos.get(boss_id)
            if boss_snapshot is None and dto is None:
                return None

            payload = getattr(dto, "current_boss_ability_payload", None) or getattr(dto, "boss_ability_payload", None) or {}
            if not isinstance(payload, dict):
                try:
                    payload = dict(payload or {})
                except Exception:
                    payload = {}

            phase_title = str(
                (telegraph.current_phase_title if telegraph is not None else "")
                or (impact.current_phase_title if impact is not None else "")
                or getattr(boss_snapshot, "current_phase_title", "")
                or getattr(dto, "current_boss_phase_title", "")
                or getattr(dto, "boss_phase_title", "")
                or ""
            ).strip()

            boss_name = str(
                (telegraph.boss_name if telegraph is not None else "")
                or (impact.boss_name if impact is not None else "")
                or getattr(boss_snapshot, "name", "")
                or getattr(dto, "name", "")
                or ""
            ).strip()

            ability_name = str(
                (telegraph.ability_name if telegraph is not None else "")
                or (impact.ability_name if impact is not None else "")
                or payload.get("ability_name", "")
                or getattr(dto, "current_boss_ability_name", "")
                or ""
            ).strip()

            ability_id = str(
                (telegraph.ability_id if telegraph is not None else "")
                or (impact.ability_id if impact is not None else "")
                or payload.get("telegraph_id", "")
                or payload.get("ability_id", "")
                or getattr(dto, "current_boss_ability_id", "")
                or ""
            ).strip()

            shape = str(
                (telegraph.shape if telegraph is not None else "")
                or (impact.shape if impact is not None else "")
                or payload.get("shape", "")
                or ""
            ).strip().lower()

            try:
                range_tiles = float(
                    (telegraph.range_tiles if telegraph is not None else 0.0)
                    or (impact.range_tiles if impact is not None else 0.0)
                    or payload.get("range", 0.0)
                    or payload.get("range_tiles", 0.0)
                    or getattr(dto, "current_boss_ability_payload", {}).get("range", 0.0)
                    or 0.0
                )
            except Exception:
                range_tiles = 0.0

            try:
                angle_degrees = float(
                    (telegraph.angle_degrees if telegraph is not None else 0.0)
                    or (impact.angle_degrees if impact is not None else 0.0)
                    or payload.get("angle_degrees", 0.0)
                    or 0.0
                )
            except Exception:
                angle_degrees = 0.0

            origin = (
                (telegraph.origin_position if telegraph is not None else None)
                or (impact.origin_position if impact is not None else None)
                or _point_from_value(payload.get("origin_position"))
                or _point_from_value(getattr(boss_snapshot, "position", None))
                or _point_from_value(getattr(dto, "boss_ability_origin_position", None))
                or _point_from_value(getattr(dto, "position", None))
            )

            target = (
                (telegraph.target_position if telegraph is not None else None)
                or (impact.target_position if impact is not None else None)
                or _point_from_value(payload.get("target_position"))
            )

            target_hero_id = str(
                (telegraph.target_hero_id if telegraph is not None else "")
                or payload.get("target_hero_id", "")
                or getattr(boss_snapshot, "target_hero_id", "")
                or getattr(dto, "boss_ability_target_hero_id", "")
                or ""
            ).strip()

            if target is None and target_hero_id:
                target = hero_views.get(target_hero_id)
            if target is None:
                target = _nearest_hero_position(origin)

            direction = (
                (telegraph.direction if telegraph is not None else None)
                or (impact.direction if impact is not None else None)
                or _point_from_value(payload.get("direction"))
                or _point_from_value(getattr(dto, "boss_ability_direction", None))
            )
            if direction is None and origin is not None and target is not None:
                direction = _normalize_vector(target[0] - origin[0], target[1] - origin[1])
            if direction is None:
                direction = (1.0, 0.0)
            if origin is None:
                origin = (0.0, 0.0)

            if not range_tiles and target is not None:
                range_tiles = max(1.0, math.hypot(target[0] - origin[0], target[1] - origin[1]) / float(TILE_SIZE))
            if not angle_degrees and shape == "cone":
                angle_degrees = 60.0

            boss_size = int(getattr(dto, "size", 18) or 18)
            screen_x = int(round(float(origin[0]) - cam_x))
            screen_y = int(round(float(origin[1]) - cam_y))
            target_screen = None if target is None else (int(round(target[0] - cam_x)), int(round(target[1] - cam_y)))
            range_px = float(range_tiles) * float(TILE_SIZE)
            if range_px <= 0.0 and target_screen is not None:
                range_px = math.hypot(target_screen[0] - screen_x, target_screen[1] - screen_y)

            return {
                "boss_snapshot": boss_snapshot,
                "dto": dto,
                "phase_title": phase_title,
                "boss_name": boss_name,
                "ability_name": ability_name,
                "ability_id": ability_id,
                "shape": shape,
                "range_px": range_px,
                "angle_degrees": angle_degrees,
                "origin": origin,
                "origin_screen": (screen_x, screen_y),
                "target": target,
                "target_screen": target_screen,
                "direction": direction,
                "boss_size": boss_size,
            }

        def _render_attack(
            geometry: dict[str, object] | None,
            *,
            resolved: bool,
            telegraph: BossTelegraphVFX | None = None,
            impact: BossImpactVFX | None = None,
        ) -> None:
            if geometry is None:
                return
            origin_screen = geometry["origin_screen"]  # type: ignore[index]
            target_screen = geometry["target_screen"]  # type: ignore[index]
            direction = geometry["direction"]  # type: ignore[index]
            range_px = float(geometry["range_px"] or 0.0)
            shape = str(geometry["shape"] or "").strip().lower()
            boss_size = int(geometry["boss_size"] or 18)
            boss_status = str(getattr(geometry["boss_snapshot"], "status", "active") or "active")  # type: ignore[index]
            if boss_status == "defeated":
                return

            badge_color = (255, 146, 56) if not resolved else (220, 54, 34)
            badge_fill = (38, 18, 10) if not resolved else (54, 20, 12)
            badge_radius = 10 if not resolved else 11
            badge_center_y = origin_screen[1] - (boss_size // 2) - 42
            center = (origin_screen[0], badge_center_y)
            pygame.draw.circle(surface, badge_fill, center, badge_radius)
            pygame.draw.circle(surface, badge_color, center, badge_radius, 2)

            icon = render_text_shadowed_cached(13 if not resolved else 14, "!", (255, 245, 210))
            icon_rect = icon.get_rect(center=center)
            surface.blit(icon, icon_rect)

            if shape == "cone" and range_px > 0.0:
                points = _cone_points(origin_screen, direction, length=range_px, angle_degrees=float(geometry["angle_degrees"] or 60.0))
                if resolved:
                    fill_color = (255, 74, 48, 84)
                    edge_color = (255, 246, 220, 220)
                else:
                    fill_color = (255, 146, 56, 58)
                    edge_color = (255, 236, 190, 200)
                _blit_polygon_overlay(
                    surface,
                    points,
                    fill_color=fill_color,
                    edge_color=edge_color,
                    extra_pad=10,
                )
                tip = target_screen if target_screen is not None else (points[-1][0], points[-1][1])
                pygame.draw.line(surface, edge_color[:3], origin_screen, tip, 2)
                pygame.draw.circle(surface, edge_color[:3], tip, 4 if not resolved else 5, 1)
                if resolved and target_screen is not None:
                    tx, ty = target_screen
                    burst_color = (220, 54, 34)
                    burst_hi = (255, 244, 210)
                    for radius, width in ((15, 2), (9, 2), (5, 0)):
                        pygame.draw.circle(surface, burst_color, (tx, ty), radius, width or 1)
                    pygame.draw.circle(surface, burst_hi, (tx, ty), 3)
                    pygame.draw.line(surface, burst_color, (tx - 16, ty), (tx + 16, ty), 1)
                    pygame.draw.line(surface, burst_color, (tx, ty - 16), (tx, ty + 16), 1)
            elif resolved and target_screen is not None:
                tx, ty = target_screen
                burst_color = (220, 54, 34)
                burst_hi = (255, 244, 210)
                for radius, width in ((14, 2), (8, 2), (4, 0)):
                    pygame.draw.circle(surface, burst_color, (tx, ty), radius, width or 1)
                pygame.draw.circle(surface, burst_hi, (tx, ty), 3)

            label_text = (
                (impact.ability_name if impact is not None else "")
                or (telegraph.ability_name if telegraph is not None else "")
                or geometry["ability_name"]  # type: ignore[index]
                or geometry["ability_id"]  # type: ignore[index]
                or geometry["phase_title"]  # type: ignore[index]
                or "TELEGRAPH"
            ).upper()
            label = render_text_shadowed_cached(11 if not resolved else 12, label_text, badge_color)
            label_rect = label.get_rect(midtop=(origin_screen[0], center[1] + badge_radius + 2))
            surface.blit(label, label_rect)

        for boss_id, telegraph in self._boss_telegraphs.items():
            if visible_enemy_ids is not None and boss_id not in visible_enemy_ids:
                continue
            geometry = _resolve_geometry(boss_id, telegraph=telegraph)
            if geometry is None:
                continue
            _render_attack(geometry, resolved=False, telegraph=telegraph)

        for boss_id, impact in self._boss_impacts.items():
            if visible_enemy_ids is not None and boss_id not in visible_enemy_ids:
                continue
            geometry = _resolve_geometry(boss_id, impact=impact)
            if geometry is None:
                continue
            _render_attack(geometry, resolved=True, impact=impact)

    def update(self, dt: float):
        if not self.enabled:
            self._particles.clear()
            self._projectiles.clear()
            self._debris.clear()
            self._boss_telegraphs.clear()
            self._boss_impacts.clear()
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

        active_telegraphs: dict[str, BossTelegraphVFX] = {}
        for boss_id, telegraph in self._boss_telegraphs.items():
            telegraph.age_sec += dt
            if telegraph.life_sec > 0.0 and telegraph.age_sec >= telegraph.life_sec:
                continue
            active_telegraphs[boss_id] = telegraph
        self._boss_telegraphs = active_telegraphs

        active_impacts: dict[str, BossImpactVFX] = {}
        for boss_id, impact in self._boss_impacts.items():
            impact.age_sec += dt
            if impact.life_sec > 0.0 and impact.age_sec >= impact.life_sec:
                continue
            active_impacts[boss_id] = impact
        self._boss_impacts = active_impacts

    def render(
        self,
        surface: pygame.Surface,
        camera_offset: tuple[int, int] = (0, 0),
        *,
        boss_encounters: tuple | list | None = None,
        visible_enemy_ids: set[str] | None = None,
        visible_enemy_dtos: dict[str, object] | None = None,
        hero_dtos: tuple | list | None = None,
    ):
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

        self._render_boss_telegraphs(
            surface,
            camera_offset,
            boss_encounters=boss_encounters,
            visible_enemy_ids=visible_enemy_ids,
            visible_enemy_dtos=visible_enemy_dtos,
            hero_dtos=hero_dtos,
        )


# Cached 32×32 arrow for Ursina 3D billboards (WK5 palette: wood shaft + bright tip).
_PROJ_BILLBOARD_CACHE: pygame.Surface | None = None


def get_projectile_billboard_surface() -> pygame.Surface:
    """RGBA sprite matching 2D ranged VFX (SaddleBrown shaft + near-white tip)."""
    global _PROJ_BILLBOARD_CACHE
    if _PROJ_BILLBOARD_CACHE is not None:
        return _PROJ_BILLBOARD_CACHE
    s = 32
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    brown = (139, 69, 19, 255)
    tip = (245, 245, 245, 255)
    cy = s // 2
    pygame.draw.line(surf, brown, (4, cy), (18, cy), 4)
    pygame.draw.polygon(surf, tip, [(18, cy), (28, cy - 8), (28, cy + 8)])
    pygame.draw.polygon(surf, brown, [(16, cy), (22, cy - 5), (22, cy + 5)])
    _PROJ_BILLBOARD_CACHE = surf
    return surf


def _make_orb_surface(core_rgb: Tuple[int, int, int], halo_rgb: Tuple[int, int, int]) -> pygame.Surface:
    """Build a glowing 32×32 RGBA orb: soft translucent halo → solid core →
    bright highlight. Used for the wizard-spell and cleric-heal billboards.
    Generated once per palette and cached by the public getters (no per-frame alloc)."""
    s = 32
    surf = pygame.Surface((s, s), pygame.SRCALPHA)
    cx = cy = s // 2
    # Outer halo rings (large→small), increasing alpha for a soft glow falloff.
    for radius, alpha in ((14, 40), (11, 80), (8, 140)):
        pygame.draw.circle(surf, (halo_rgb[0], halo_rgb[1], halo_rgb[2], alpha), (cx, cy), radius)
    # Solid core orb.
    pygame.draw.circle(surf, (core_rgb[0], core_rgb[1], core_rgb[2], 255), (cx, cy), 6)
    # Bright off-center highlight for an energetic, readable read.
    hi = (min(255, core_rgb[0] + 70), min(255, core_rgb[1] + 70), min(255, core_rgb[2] + 70), 255)
    pygame.draw.circle(surf, hi, (cx - 2, cy - 2), 2)
    return surf


# Cached 32×32 arcane orb for Ursina 3D billboards (WK124-T3c: wizard spell).
_MAGIC_BILLBOARD_CACHE: pygame.Surface | None = None
# Cached 32×32 green orb for Ursina 3D billboards (WK124-T4c: cleric heal).
_HEAL_BILLBOARD_CACHE: pygame.Surface | None = None


def get_magic_billboard_surface() -> pygame.Surface:
    """RGBA arcane glowing ORB for the wizard spell (purple core + lighter halo).
    Cached — generated once (FPS guardrail: no per-frame surface regeneration)."""
    global _MAGIC_BILLBOARD_CACHE
    if _MAGIC_BILLBOARD_CACHE is not None:
        return _MAGIC_BILLBOARD_CACHE
    # Wizard spell purple (matches config.WIZARD_SPELL_COLOR / spec default).
    _MAGIC_BILLBOARD_CACHE = _make_orb_surface(core_rgb=(170, 90, 230), halo_rgb=(200, 150, 255))
    return _MAGIC_BILLBOARD_CACHE


def get_heal_billboard_surface() -> pygame.Surface:
    """RGBA green glowing ORB for the cleric heal bolt (green core + pale halo).
    Cached — generated once (FPS guardrail: no per-frame surface regeneration)."""
    global _HEAL_BILLBOARD_CACHE
    if _HEAL_BILLBOARD_CACHE is not None:
        return _HEAL_BILLBOARD_CACHE
    _HEAL_BILLBOARD_CACHE = _make_orb_surface(core_rgb=(90, 220, 120), halo_rgb=(170, 255, 190))
    return _HEAL_BILLBOARD_CACHE

