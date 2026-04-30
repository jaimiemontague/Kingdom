from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import pygame

from game.graphics.animation import AnimationClip, AnimationPlayer, load_png_frames


@dataclass(frozen=True)
class WorkerSpriteSpec:
    size: int = 32
    outline: Tuple[int, int, int] = (240, 240, 240)
    peasant: Tuple[int, int, int] = (200, 180, 120)
    tax_collector: Tuple[int, int, int] = (218, 165, 32)  # Gold color
    guard: Tuple[int, int, int] = (100, 110, 145)  # Steel blue-gray


class WorkerSpriteLibrary:
    """
    Animated worker sprites (pixel-art-first).

    If PNG frames exist under:
      assets/sprites/workers/<worker_type>/<action>/*.png
    they will be used. Otherwise we generate simple procedural frames so the game
    still has visible "animations" even without art assets.
    """

    _cache: Dict[tuple[str, int], Dict[str, AnimationClip]] = {}

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _assets_dir(cls) -> Path:
        return cls._repo_root() / "assets" / "sprites" / "workers"

    @classmethod
    def clips_for(cls, worker_type: str, size: int = 32) -> Dict[str, AnimationClip]:
        wt = (worker_type or "peasant").lower()
        key = (wt, int(size))
        if key in cls._cache:
            return cls._cache[key]

        spec = WorkerSpriteSpec(size=int(size))
        base_color = cls._type_color(wt)

        # Define actions per worker type
        if wt == "tax_collector":
            # Frame counts match `tools/legacy_vania_export_worker_frames.py` (npc-cape2 only).
            actions = {
                "idle": dict(frame_time=0.14, loop=True),  # 4
                "walk": dict(frame_time=0.09, loop=True),  # 10 (stance + walk)
                "collect": dict(frame_time=0.12, loop=True),  # 3 (jab only, no knife strip)
                "return": dict(frame_time=0.09, loop=True),  # 10 (same as walk)
                "rest": dict(frame_time=0.22, loop=True),  # 3 waiting crouch variants
                "hurt": dict(frame_time=0.075, loop=False),  # 5 (stronghurt + hurt + recover)
                "dead": dict(frame_time=0.11, loop=False),  # 10 fall
            }
        elif wt == "peasant_builder":
            # Same contract as peasant; distinct asset folder (green-hat builder variant).
            actions = {
                "idle": dict(frame_time=0.14, loop=True),
                "walk": dict(frame_time=0.10, loop=True),
                "work": dict(frame_time=0.12, loop=True),
                "hurt": dict(frame_time=0.06, loop=False),
                "dead": dict(frame_time=0.10, loop=False),
            }
        elif wt == "guard":
            actions = {
                "idle": dict(frame_time=0.14, loop=True),
                "walk": dict(frame_time=0.10, loop=True),
                "attack": dict(frame_time=0.12, loop=True),  # Loop while in ATTACKING state
                "hurt": dict(frame_time=0.06, loop=False),
                "dead": dict(frame_time=0.10, loop=False),
            }
        else:  # peasant (default)
            actions = {
                "idle": dict(frame_time=0.14, loop=True),
                "walk": dict(frame_time=0.10, loop=True),
                "work": dict(frame_time=0.12, loop=True),
                "hurt": dict(frame_time=0.06, loop=False),
                "dead": dict(frame_time=0.10, loop=False),
            }

        clips: Dict[str, AnimationClip] = {}
        for action, meta in actions.items():
            frames = cls._try_load_asset_frames(wt, action, size=int(size))
            if not frames:
                frames = cls._procedural_frames(wt, action, base_color, spec)
            clips[action] = AnimationClip(frames=frames, frame_time_sec=meta["frame_time"], loop=meta["loop"])

        cls._cache[key] = clips
        return clips

    @classmethod
    def create_player(cls, worker_type: str, size: int = 32) -> AnimationPlayer:
        clips = cls.clips_for(worker_type, size=int(size))
        return AnimationPlayer(clips=clips, initial="idle")

    @staticmethod
    def _type_color(worker_type: str) -> Tuple[int, int, int]:
        wt = (worker_type or "").lower()
        spec = WorkerSpriteSpec()
        if wt == "tax_collector":
            return spec.tax_collector
        if wt == "guard":
            return spec.guard
        if wt == "peasant_builder":
            return spec.peasant
        return spec.peasant

    @classmethod
    def _try_load_asset_frames(cls, worker_type: str, action: str, *, size: int) -> list[pygame.Surface]:
        folder = cls._assets_dir() / (worker_type or "peasant") / action
        return load_png_frames(folder, scale_to=(int(size), int(size)))

    @staticmethod
    def _guard_procedural_frames(
        action: str,
        base_color: Tuple[int, int, int],
        spec: WorkerSpriteSpec,
    ) -> list[pygame.Surface]:
        """Pixel-art procedural frames for guard: helmet, body, spear/shield silhouette."""
        s = int(spec.size)
        cx, cy = s // 2, s // 2
        ol = (0, 0, 0)  # Black outline for guard (pixel-art readability)

        def mk() -> pygame.Surface:
            return pygame.Surface((s, s), pygame.SRCALPHA)

        def color(brighten: float = 1.0) -> Tuple[int, int, int]:
            return (
                min(255, int(base_color[0] * brighten)),
                min(255, int(base_color[1] * brighten)),
                min(255, int(base_color[2] * brighten)),
            )

        def draw_guard_silhouette(
            surf: pygame.Surface,
            bob_px: float = 0.0,
            lean: float = 0.0,
            weapon_angle: float = 0.0,
            brighten: float = 1.0,
        ) -> None:
            col = color(brighten)
            # Shadow
            shadow = pygame.Rect(0, 0, 14, 6)
            shadow.center = (cx, cy + 10 + int(bob_px))
            pygame.draw.ellipse(surf, (0, 0, 0, 50), shadow)
            # Body (rounded rect: torso)
            by = int(cy + bob_px + 2)
            body = pygame.Rect(cx - 6, by - 4, 12, 14)
            body.x += int(lean * 2)
            pygame.draw.rect(surf, col, body, 0, 2)
            pygame.draw.rect(surf, ol, body, 1, 2)
            # Helmet (dome on top)
            helm_center = (cx + int(lean), int(by - 10))
            pygame.draw.circle(surf, (80, 85, 100), helm_center, 6)
            pygame.draw.circle(surf, ol, helm_center, 6, 1)
            # Visor hint (2px line)
            pygame.draw.line(
                surf, (40, 42, 50),
                (helm_center[0] - 3, helm_center[1]),
                (helm_center[0] + 3, helm_center[1]),
                1,
            )
            # Spear (vertical line + tip)
            tip_x = cx + 8 + int(lean * 2) + int(weapon_angle * 4)
            tip_y = by - 12 + int(weapon_angle * 2)
            pygame.draw.line(surf, (90, 85, 75), (cx + 6, by - 2), (tip_x, tip_y), 2)
            pygame.draw.line(surf, ol, (cx + 6, by - 2), (tip_x, tip_y), 1)
            # Small shield (rectangle left of body)
            sh_x = cx - 10 + int(lean)
            sh_y = int(by - 2)
            pygame.draw.rect(surf, (80, 90, 110), (sh_x, sh_y, 5, 8), 0, 1)
            pygame.draw.rect(surf, ol, (sh_x, sh_y, 5, 8), 1, 1)

        if action == "idle":
            frames = []
            for i in range(6):
                surf = mk()
                bob = math.sin(i / 6.0 * math.tau) * 1.0
                draw_guard_silhouette(surf, bob_px=bob, brighten=1.0)
                frames.append(surf)
            return frames
        if action == "walk":
            frames = []
            for i in range(8):
                surf = mk()
                t = i / 8.0
                bob = abs(math.sin(t * math.tau)) * 1.5
                lean = math.sin(t * math.tau) * 1.2
                draw_guard_silhouette(surf, bob_px=-bob, lean=lean, brighten=1.02)
                frames.append(surf)
            return frames
        if action == "attack":
            frames = []
            for i in range(6):
                surf = mk()
                t = i / 6.0
                # Thrust forward
                weapon_angle = -2.0 + t * 4.0 if t < 0.5 else 4.0 - (t - 0.5) * 8.0
                weapon_angle = max(-2, min(2, weapon_angle))
                lean = 1.5 if t < 0.5 else -0.5
                draw_guard_silhouette(surf, lean=lean, weapon_angle=weapon_angle, brighten=1.1)
                frames.append(surf)
            return frames
        if action == "hurt":
            frames = []
            for i in range(4):
                surf = mk()
                flash = 1.0 + (i % 2) * 0.25
                draw_guard_silhouette(surf, brighten=flash)
                frames.append(surf)
            return frames
        if action == "dead":
            surf = mk()
            draw_guard_silhouette(surf, brighten=0.5)
            return [surf]
        surf = mk()
        draw_guard_silhouette(surf)
        return [surf]

    @staticmethod
    def _procedural_frames(
        worker_type: str,
        action: str,
        base_color: Tuple[int, int, int],
        spec: WorkerSpriteSpec,
    ) -> list[pygame.Surface]:
        """Generate procedural fallback frames if assets are missing."""
        if (worker_type or "").lower() == "guard":
            return WorkerSpriteLibrary._guard_procedural_frames(action, base_color, spec)

        s = int(spec.size)
        cx = cy = s // 2
        r = max(6, s // 3)

        def mk_surface() -> pygame.Surface:
            surf = pygame.Surface((s, s), pygame.SRCALPHA)
            return surf

        def draw_base(surf: pygame.Surface, bob_px: float = 0.0, lean: float = 0.0, brighten: float = 1.0):
            col = (
                min(255, int(base_color[0] * brighten)),
                min(255, int(base_color[1] * brighten)),
                min(255, int(base_color[2] * brighten)),
            )
            shadow = pygame.Rect(0, 0, int(r * 1.8), int(r * 0.9))
            shadow.center = (cx, cy + r // 2 + 6)
            pygame.draw.ellipse(surf, (0, 0, 0, 55), shadow)

            body_center = (int(cx + lean * 4), int(cy + bob_px))
            pygame.draw.circle(surf, col, body_center, r)
            pygame.draw.circle(surf, spec.outline, body_center, r, 2)

            # Simple worker glyph (fallback only)
            glyph = "P" if (worker_type or "").lower() in ("peasant", "peasant_builder") else "$"
            font = pygame.font.Font(None, max(12, s // 2))
            txt = font.render(glyph, True, (250, 250, 250))
            rect = txt.get_rect(center=body_center)
            surf.blit(txt, rect)

        if action == "rest":
            frames = []
            for i in range(6):
                t = i / 6.0
                surf = mk_surface()
                bob = math.sin(t * math.tau) * 1.2
                draw_base(surf, bob_px=bob, lean=0.0, brighten=1.0)
                frames.append(surf)
            return frames

        if action == "idle":
            frames = []
            for i in range(6):
                t = i / 6.0
                surf = mk_surface()
                bob = math.sin(t * math.tau) * 1.2
                draw_base(surf, bob_px=bob, lean=0.0, brighten=1.0)
                frames.append(surf)
            return frames

        if action == "walk":
            frames = []
            for i in range(8):
                t = i / 8.0
                surf = mk_surface()
                bob = abs(math.sin(t * math.tau)) * 1.6
                lean = math.sin(t * math.tau) * 0.6
                draw_base(surf, bob_px=-bob, lean=lean, brighten=1.05)

                # feet ticks
                y = cy + r + 2
                x_off = int(math.sin(t * math.tau) * 4)
                pygame.draw.line(surf, (230, 230, 230), (cx - 6 + x_off, y), (cx - 2 + x_off, y), 2)
                pygame.draw.line(surf, (230, 230, 230), (cx + 2 - x_off, y), (cx + 6 - x_off, y), 2)
                frames.append(surf)
            return frames

        if action in ("work", "collect"):
            frames = []
            for i in range(6):
                t = i / 6.0
                surf = mk_surface()
                bob = math.sin(t * math.tau) * 0.8
                draw_base(surf, bob_px=bob, lean=0.0, brighten=1.1)
                frames.append(surf)
            return frames

        if action == "return":
            # Same as walk for tax collector
            frames = []
            for i in range(8):
                t = i / 8.0
                surf = mk_surface()
                bob = abs(math.sin(t * math.tau)) * 1.6
                lean = math.sin(t * math.tau) * 0.6
                draw_base(surf, bob_px=-bob, lean=lean, brighten=1.05)
                frames.append(surf)
            return frames

        if action == "hurt":
            frames = []
            for i in range(4):
                surf = mk_surface()
                flash = 1.0 + (i % 2) * 0.3
                draw_base(surf, bob_px=0.0, lean=0.0, brighten=flash)
                frames.append(surf)
            return frames

        if action == "dead":
            frames = []
            surf = mk_surface()
            draw_base(surf, bob_px=0.0, lean=0.0, brighten=0.5)
            frames.append(surf)
            return frames

        # Default: single idle frame
        surf = mk_surface()
        draw_base(surf)
        return [surf]
