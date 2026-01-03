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
            actions = {
                "idle": dict(frame_time=0.14, loop=True),
                "walk": dict(frame_time=0.10, loop=True),
                "collect": dict(frame_time=0.12, loop=True),
                "return": dict(frame_time=0.10, loop=True),
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
        return spec.peasant

    @classmethod
    def _try_load_asset_frames(cls, worker_type: str, action: str, *, size: int) -> list[pygame.Surface]:
        folder = cls._assets_dir() / (worker_type or "peasant") / action
        return load_png_frames(folder, scale_to=(int(size), int(size)))

    @staticmethod
    def _procedural_frames(
        worker_type: str,
        action: str,
        base_color: Tuple[int, int, int],
        spec: WorkerSpriteSpec,
    ) -> list[pygame.Surface]:
        """Generate procedural fallback frames if assets are missing."""
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
            glyph = "P" if worker_type == "peasant" else "$"
            font = pygame.font.Font(None, max(12, s // 2))
            txt = font.render(glyph, True, (250, 250, 250))
            rect = txt.get_rect(center=body_center)
            surf.blit(txt, rect)

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
