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
    cleric: Tuple[int, int, int] = (48, 186, 178)


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
        if hc == "cleric":
            return spec.cleric
        return spec.warrior

    @classmethod
    def _try_load_asset_frames(cls, hero_class: str, action: str, size: int) -> list[pygame.Surface]:
        folder = cls._assets_dir() / (hero_class or "warrior") / action
        return load_png_frames(folder, scale_to=(int(size), int(size)))

    @staticmethod
    def _procedural_frames(hero_class: str, action: str, base_color: Tuple[int, int, int], spec: HeroSpriteSpec) -> list[pygame.Surface]:
        # NOTE: This procedural style is intentionally "pixel-hero" (head/torso/legs),
        # matching the CC0 placeholder look used elsewhere in the project. It avoids
        # font glyphs so hero classes always read consistently, even in headless modes.
        s = int(spec.size)
        cx = cy = s // 2

        def mk_surface() -> pygame.Surface:
            return pygame.Surface((s, s), pygame.SRCALPHA)

        def shade(c: Tuple[int, int, int], delta: int) -> Tuple[int, int, int]:
            return (max(0, min(255, c[0] + delta)), max(0, min(255, c[1] + delta)), max(0, min(255, c[2] + delta)))

        dark = (20, 20, 25)
        skin = (255, 210, 180)

        def draw_pixel_hero(surf: pygame.Surface, *, t: float, st: str) -> tuple[int, int]:
            # A simple 32x32 pixel hero: head + torso + legs + tiny class accents.
            # Returns (bx, by) body center-ish for weapon placement.
            surf.fill((0, 0, 0, 0))
            bob = int(max(0, math.sin(t * math.tau) * 2)) if st == "idle" else 0
            lean = int(math.sin(t * math.tau) * 2) if st == "walk" else 0
            if st == "hurt":
                lean = -2 if int(t * 10) % 2 == 0 else 2
            elif st == "attack":
                lean = 3 if t > 0.3 else -1

            bx, by = cx + lean, cy + 2 + bob

            # Head
            pygame.draw.rect(surf, dark, pygame.Rect(bx - 4, by - 12, 8, 8))
            pygame.draw.rect(surf, skin, pygame.Rect(bx - 3, by - 11, 6, 6))

            # Torso
            pygame.draw.rect(surf, dark, pygame.Rect(bx - 5, by - 4, 10, 8))
            pygame.draw.rect(surf, base_color, pygame.Rect(bx - 4, by - 3, 8, 5))
            pygame.draw.rect(surf, shade(base_color, -18), pygame.Rect(bx - 4, by + 2, 8, 2))

            # Legs
            leg_base = by + 4
            if st == "walk":
                l_off = int(math.sin(t * math.tau) * 3)
                r_off = int(math.cos(t * math.tau) * 3)
            else:
                l_off, r_off = -2, 2

            pygame.draw.rect(surf, dark, pygame.Rect(bx - 3 + l_off, leg_base, 4, 6))
            pygame.draw.rect(surf, (110, 110, 110), pygame.Rect(bx - 2 + l_off, leg_base, 2, 5))
            pygame.draw.rect(surf, dark, pygame.Rect(bx - 1 + r_off, leg_base, 4, 6))
            pygame.draw.rect(surf, (110, 110, 110), pygame.Rect(bx + r_off, leg_base, 2, 5))

            # Class micro-accent (a single pixel "tabard" highlight)
            hc = (hero_class or "warrior").lower()
            if hc == "cleric":
                pygame.draw.rect(surf, (230, 245, 245), pygame.Rect(bx - 1, by - 1, 2, 2))
            elif hc == "wizard":
                pygame.draw.rect(surf, (245, 225, 255), pygame.Rect(bx - 1, by - 1, 2, 2))
            elif hc == "rogue":
                pygame.draw.rect(surf, (225, 225, 235), pygame.Rect(bx - 1, by - 1, 2, 2))
            elif hc == "ranger":
                pygame.draw.rect(surf, (235, 255, 235), pygame.Rect(bx - 1, by - 1, 2, 2))

            return bx, by

        if action == "idle":
            frames = []
            for i in range(6):
                t = i / 6.0
                surf = mk_surface()
                draw_pixel_hero(surf, t=t, st="idle")
                frames.append(surf)
            return frames

        if action == "walk":
            frames = []
            for i in range(8):
                t = i / 8.0
                surf = mk_surface()
                draw_pixel_hero(surf, t=t, st="walk")
                frames.append(surf)
            return frames

        if action == "attack":
            frames = []
            hc_lower = (hero_class or "").lower()

            for i in range(6):
                t = i / 5.0
                surf = mk_surface()
                bx, by = draw_pixel_hero(surf, t=t, st="attack")

                # Weapon cues (simple, readable at gameplay zoom)
                if hc_lower == "ranger":
                    # bow + arrow cue
                    pygame.draw.line(surf, dark, (bx - 6, by - 10), (bx - 6, by + 4), 2)
                    pygame.draw.line(surf, (200, 200, 210), (bx - 5, by - 10), (bx - 5, by + 4), 1)
                    if t > 0.2:
                        pygame.draw.line(surf, (245, 235, 200), (bx - 2, by - 2), (bx + 14, by - 4), 2)
                elif hc_lower == "wizard":
                    # staff + glow
                    pygame.draw.line(surf, (100, 60, 20), (bx + 2, by + 8), (bx + 10, by - 10), 2)
                    glow_r = int(5 * math.sin(t * math.pi))
                    if glow_r > 0:
                        pygame.draw.circle(surf, (200, 150, 255, 140), (bx + 10, by - 10), glow_r)
                        pygame.draw.circle(surf, (255, 255, 255), (bx + 10, by - 10), 2)
                elif hc_lower == "rogue":
                    # twin daggers
                    dx1, dy1 = bx + 8, by - 4 + int(8 * t)
                    dx2, dy2 = bx + 10, by + 6 - int(10 * t)
                    pygame.draw.line(surf, (180, 180, 190), (bx, by - 2), (dx1, dy1), 2)
                    pygame.draw.line(surf, (180, 180, 190), (bx + 2, by + 2), (dx2, dy2), 2)
                elif hc_lower == "cleric":
                    # mace cue (readable "holy bonk")
                    end_x, end_y = bx + 10, by - 12 + int(28 * t)
                    pygame.draw.line(surf, (230, 235, 235), (bx - 2, by - 4), (end_x, end_y), 3)
                    pygame.draw.circle(surf, (255, 230, 140), (end_x, end_y), 3)
                else:
                    # warrior/default sword
                    end_x, end_y = bx + 10, by - 12 + int(28 * t)
                    pygame.draw.line(surf, (220, 220, 225), (bx - 2, by - 4), (end_x, end_y), 3)
                    pygame.draw.circle(surf, (255, 200, 50), (end_x, end_y), 3)
                frames.append(surf)
            return frames

        if action == "hurt":
            frames = []
            for i in range(4):
                t = i / 4.0
                surf = mk_surface()
                draw_pixel_hero(surf, t=t, st="hurt")
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








