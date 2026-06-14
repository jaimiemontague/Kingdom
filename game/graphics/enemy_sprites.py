from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import pygame

from game.graphics.animation import AnimationClip, AnimationPlayer, load_png_frames
from game.paths import PROJECT_ROOT


@dataclass(frozen=True)
class EnemySpriteSpec:
    size: int = 32
    outline: Tuple[int, int, int] = (240, 240, 240)


# WK137: boss variants reuse their base type's PNG art when they have no folder
# of their own (assets/sprites/enemies/goblin_warchief/ does not exist; goblin does).
_ASSET_FOLDER_ALIASES = {"goblin_warchief": "goblin"}


class EnemySpriteLibrary:
    """
    Animated enemy sprites (pixel-art-first).

    If PNG frames exist under:
      assets/sprites/enemies/<enemy_type>/<action>/*.png
    they will be used. Otherwise we generate small procedural pixel sprites.
    """

    _cache: Dict[tuple[str, int], Dict[str, AnimationClip]] = {}

    @staticmethod
    def _repo_root():
        return PROJECT_ROOT

    @classmethod
    def _assets_dir(cls):
        return cls._repo_root() / "assets" / "sprites" / "enemies"

    @classmethod
    def clips_for(cls, enemy_type: str, *, size: int = 32) -> Dict[str, AnimationClip]:
        et = (enemy_type or "goblin").lower()
        key = (et, int(size))
        if key in cls._cache:
            return cls._cache[key]

        spec = EnemySpriteSpec(size=int(size))
        base_color = cls._type_color(et)

        actions = {
            "idle": dict(frame_time=0.16, loop=True),
            "walk": dict(frame_time=0.10, loop=True),
            "attack": dict(frame_time=0.07, loop=False),
            "hurt": dict(frame_time=0.06, loop=False),
            "dead": dict(frame_time=0.10, loop=False),
        }

        clips: Dict[str, AnimationClip] = {}
        for action, meta in actions.items():
            frames = cls._try_load_asset_frames(et, action, size=int(size))
            if not frames:
                frames = cls._procedural_frames(et, action, base_color, spec)
            clips[action] = AnimationClip(frames=frames, frame_time_sec=meta["frame_time"], loop=meta["loop"])

        cls._cache[key] = clips
        return clips

    @classmethod
    def create_player(cls, enemy_type: str, *, size: int = 32) -> AnimationPlayer:
        clips = cls.clips_for(enemy_type, size=int(size))
        return AnimationPlayer(clips=clips, initial="idle")

    @staticmethod
    def _type_color(enemy_type: str) -> Tuple[int, int, int]:
        et = (enemy_type or "").lower()
        if et == "wolf":
            return (160, 160, 160)
        if et in ("skeleton", "skeleton_archer"):
            return (220, 220, 240)
        if et == "spider":
            return (40, 40, 40)
        if et == "bandit":
            return (130, 90, 55)
        # WK137: boss colors — match ENEMY_STATS so procedural fallbacks read as
        # "elite" instead of all default brown.
        if et == "goblin_warchief":
            return (96, 48, 12)
        if et == "bandit_lord":
            return (180, 100, 30)
        if et == "demon_overlord":
            return (200, 30, 30)
        if et == "dragon":
            return (220, 60, 20)
        # goblin + default
        return (139, 69, 19)

    @classmethod
    def _try_load_asset_frames(cls, enemy_type: str, action: str, *, size: int) -> list[pygame.Surface]:
        # WK137: resolve boss variants to their base type's PNG folder (alias).
        folder_type = _ASSET_FOLDER_ALIASES.get(
            (enemy_type or "goblin").lower(), enemy_type or "goblin"
        )
        folder = cls._assets_dir() / folder_type / action
        return load_png_frames(folder, scale_to=(int(size), int(size)))

    @staticmethod
    def _procedural_frames(
        enemy_type: str,
        action: str,
        base_color: Tuple[int, int, int],
        spec: EnemySpriteSpec,
    ) -> list[pygame.Surface]:
        s = int(spec.size)
        cx = cy = s // 2
        r = max(6, s // 3)

        def mk() -> pygame.Surface:
            return pygame.Surface((s, s), pygame.SRCALPHA)

        def draw_body(surf: pygame.Surface, bob: float = 0.0, lean: float = 0.0, brighten: float = 1.0):
            col = (
                min(255, int(base_color[0] * brighten)),
                min(255, int(base_color[1] * brighten)),
                min(255, int(base_color[2] * brighten)),
            )
            # shadow
            sh = pygame.Rect(0, 0, int(r * 1.8), int(r * 0.9))
            sh.center = (cx, cy + r // 2 + 6)
            pygame.draw.ellipse(surf, (0, 0, 0, 55), sh)

            center = (int(cx + lean * 4), int(cy + bob))

            # enemy silhouette per type
            et = (enemy_type or "goblin").lower()
            if et == "wolf":
                pygame.draw.ellipse(surf, col, pygame.Rect(center[0] - r, center[1] - r // 2, r * 2, r))
            elif et == "skeleton":
                pygame.draw.rect(surf, col, pygame.Rect(center[0] - r // 2, center[1] - r, r, r * 2))
            elif et == "skeleton_archer":
                # skeleton-like body, plus a simple bow cue so it reads as ranged
                pygame.draw.rect(surf, col, pygame.Rect(center[0] - r // 2, center[1] - r, r, r * 2))
                pygame.draw.line(surf, (30, 30, 35), (center[0] + r // 2, center[1] - r // 2), (center[0] + r + 4, center[1] + r // 2), 2)
                pygame.draw.line(surf, (200, 200, 210), (center[0] + r // 2 + 1, center[1] - r // 2), (center[0] + r // 2 + 1, center[1] + r // 2), 1)
            elif et == "spider":
                pygame.draw.circle(surf, col, center, r - 2)
                # legs
                for i in range(4):
                    off = (i - 1.5) * 3
                    pygame.draw.line(surf, (80, 80, 80), (center[0] - r, center[1] + off), (center[0] - r - 6, center[1] + off + 2), 2)
                    pygame.draw.line(surf, (80, 80, 80), (center[0] + r, center[1] + off), (center[0] + r + 6, center[1] + off + 2), 2)
            else:
                pygame.draw.circle(surf, col, center, r)

            # Spider body is drawn at r-2; a full-radius outline reads as a bright halo ring.
            if et == "spider":
                orad = max(1, r - 2)
                pygame.draw.circle(surf, spec.outline, center, orad, 1)
            else:
                pygame.draw.circle(surf, spec.outline, center, max(2, r), 2)

        if action == "idle":
            frames = []
            for i in range(6):
                t = i / 6.0
                surf = mk()
                bob = math.sin(t * math.tau) * 1.0
                draw_body(surf, bob=bob, lean=0.0, brighten=1.0)
                frames.append(surf)
            return frames

        if action == "walk":
            frames = []
            for i in range(8):
                t = i / 8.0
                surf = mk()
                bob = abs(math.sin(t * math.tau)) * 1.4
                lean = math.sin(t * math.tau) * 0.5
                draw_body(surf, bob=-bob, lean=lean, brighten=1.05)
                frames.append(surf)
            return frames

        if action == "attack":
            frames = []
            for i in range(6):
                t = i / 5.0
                surf = mk()
                draw_body(surf, bob=0.0, lean=0.8 if t > 0.3 else 0.2, brighten=1.1)
                # simple slash
                start = (cx + r - 2, cy - 2)
                end = (cx + r + 10, cy - 10 + int(16 * t))
                pygame.draw.line(surf, (255, 245, 220), start, end, 3)
                frames.append(surf)
            return frames

        if action == "hurt":
            frames = []
            for i in range(4):
                surf = mk()
                draw_body(surf, bob=0.0, lean=(-1) ** i * 0.7, brighten=0.85)
                overlay = pygame.Surface((s, s), pygame.SRCALPHA)
                overlay.fill((255, 40, 40, 70))
                surf.blit(overlay, (0, 0))
                frames.append(surf)
            return frames

        # dead
        frames = []
        surf = mk()
        draw_body(surf, bob=0.0, lean=0.0, brighten=0.65)
        # fade overlay
        overlay = pygame.Surface((s, s), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 90))
        surf.blit(overlay, (0, 0))
        frames.append(surf)
        return frames





