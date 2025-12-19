from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import pygame

from game.graphics.animation import AnimationClip, AnimationPlayer, load_png_frames


@dataclass(frozen=True)
class HeroSpriteSpec:
    size: int = 32
    outline: Tuple[int, int, int] = (240, 240, 240)
    warrior: Tuple[int, int, int] = (70, 120, 255)
    ranger: Tuple[int, int, int] = (70, 200, 120)
    rogue: Tuple[int, int, int] = (180, 180, 200)
    wizard: Tuple[int, int, int] = (170, 90, 230)


class HeroSpriteLibrary:
    """
    Provides animated frames for heroes.

    If PNG frames exist under:
      assets/sprites/heroes/<hero_class>/<action>/*.png
    they'll be used. Otherwise, we generate simple procedural frames so the game
    still has visible "animations" even without art assets.
    """

    _cache: Dict[tuple[str, int], Dict[str, AnimationClip]] = {}

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def _assets_dir(cls) -> Path:
        return cls._repo_root() / "assets" / "sprites" / "heroes"

    @classmethod
    def clips_for(cls, hero_class: str, size: int = 32) -> Dict[str, AnimationClip]:
        key = (str(hero_class or "warrior"), int(size))
        if key in cls._cache:
            return cls._cache[key]

        spec = HeroSpriteSpec(size=int(size))
        base_color = cls._class_color(spec, hero_class)

        actions = {
            "idle": dict(frame_time=0.14, loop=True),
            "walk": dict(frame_time=0.10, loop=True),
            "attack": dict(frame_time=0.07, loop=False),
            "hurt": dict(frame_time=0.06, loop=False),
            "inside": dict(frame_time=0.12, loop=True),
        }

        clips: Dict[str, AnimationClip] = {}
        for action, meta in actions.items():
            frames = cls._try_load_asset_frames(hero_class, action, size)
            if not frames:
                frames = cls._procedural_frames(hero_class, action, base_color, spec)
            clips[action] = AnimationClip(frames=frames, frame_time_sec=meta["frame_time"], loop=meta["loop"])

        cls._cache[key] = clips
        return clips

    @classmethod
    def create_player(cls, hero_class: str, size: int = 32) -> AnimationPlayer:
        clips = cls.clips_for(hero_class, size=size)
        return AnimationPlayer(clips=clips, initial="idle")

    @staticmethod
    def _class_color(spec: HeroSpriteSpec, hero_class: str) -> Tuple[int, int, int]:
        hc = (hero_class or "").lower()
        if hc == "ranger":
            return spec.ranger
        if hc == "rogue":
            return spec.rogue
        if hc == "wizard":
            return spec.wizard
        return spec.warrior

    @classmethod
    def _try_load_asset_frames(cls, hero_class: str, action: str, size: int) -> list[pygame.Surface]:
        folder = cls._assets_dir() / (hero_class or "warrior") / action
        return load_png_frames(folder, scale_to=(int(size), int(size)))

    @staticmethod
    def _procedural_frames(hero_class: str, action: str, base_color: Tuple[int, int, int], spec: HeroSpriteSpec) -> list[pygame.Surface]:
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

            # Simple class glyph
            glyph = (hero_class or "warrior").lower()[:1].upper()
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

        if action == "attack":
            frames = []
            for i in range(6):
                t = i / 5.0
                surf = mk_surface()
                lean = 0.9 if t > 0.3 else 0.2
                draw_base(surf, bob_px=0.0, lean=lean, brighten=1.10)

                # sword arc
                start = (cx + r - 2, cy - 2)
                end = (cx + r + 10, cy - 12 + int(18 * t))
                pygame.draw.line(surf, (245, 245, 245), start, end, 3)
                pygame.draw.circle(surf, (255, 220, 120), end, 3)
                frames.append(surf)
            return frames

        if action == "hurt":
            frames = []
            for i in range(4):
                surf = mk_surface()
                draw_base(surf, bob_px=0.0, lean=(-1) ** i * 0.8, brighten=0.8)
                # red flash overlay
                overlay = pygame.Surface((s, s), pygame.SRCALPHA)
                overlay.fill((255, 40, 40, 70))
                surf.blit(overlay, (0, 0))
                frames.append(surf)
            return frames

        # inside: used as a tiny looping "bubble" icon (e.g. shopping)
        frames = []
        for i in range(6):
            t = i / 6.0
            surf = mk_surface()
            rad = int(6 + 2 * math.sin(t * math.tau))
            pygame.draw.circle(surf, (255, 255, 255, 220), (cx, cy), rad, 2)
            pygame.draw.circle(surf, (255, 215, 0, 200), (cx + 1, cy - 1), 2)
            frames.append(surf)
        return frames





