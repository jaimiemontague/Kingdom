"""Unit sprite atlas generator for instanced rendering (wk47)."""
from __future__ import annotations

import pygame
from typing import Dict, Tuple

import config
from game.graphics.hero_sprites import HeroSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.vfx import (
    get_heal_billboard_surface,
    get_magic_billboard_surface,
    get_projectile_billboard_surface,
)
from game.graphics.worker_sprites import WorkerSpriteLibrary

# Normalized UV region on the atlas: (u_start, v_start, u_width, v_height)
UVRegion = Tuple[float, float, float, float]

# Key for looking up a specific frame: (unit_type, class_key, action, frame_index)
# Examples: ("hero", "warrior", "idle", 0), ("enemy", "goblin", "walk", 3)
AtlasKey = Tuple[str, str, str, int]

ATLAS_SIZE = 2048
FRAME_SIZE = int(getattr(config, "UNIT_SPRITE_PIXELS", 32))


class UnitAtlasBuilder:
    """Packs all unit sprite frames into one GPU-friendly atlas."""

    _instance: "UnitAtlasBuilder | None" = None

    def __init__(self):
        self._atlas_surface: pygame.Surface | None = None
        self._uv_map: Dict[AtlasKey, UVRegion] = {}
        self._ursina_tex = None

    @classmethod
    def get(cls) -> "UnitAtlasBuilder":
        """Singleton access. Builds atlas on first call."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._build()
        return cls._instance

    @property
    def atlas_surface(self) -> pygame.Surface:
        assert self._atlas_surface is not None
        return self._atlas_surface

    @property
    def frame_count(self) -> int:
        return len(self._uv_map)

    def lookup_uv(self, unit_type: str, class_key: str, action: str, frame_idx: int) -> UVRegion:
        """Look up the atlas UV region for a given unit frame."""
        key: AtlasKey = (unit_type, class_key, action, frame_idx)
        fallback: UVRegion = (0.0, 0.0, FRAME_SIZE / ATLAS_SIZE, FRAME_SIZE / ATLAS_SIZE)
        return self._uv_map.get(key, fallback)

    def _pack_frame(self, surf: pygame.Surface, key: AtlasKey, cursor: list[int]) -> None:
        """Blit one frame onto the atlas and record its UV region."""
        cx, cy = cursor
        if cx + FRAME_SIZE > ATLAS_SIZE:
            cx = 0
            cy += FRAME_SIZE
        self._atlas_surface.blit(surf, (cx, cy))
        self._uv_map[key] = (
            cx / ATLAS_SIZE,
            cy / ATLAS_SIZE,
            FRAME_SIZE / ATLAS_SIZE,
            FRAME_SIZE / ATLAS_SIZE,
        )
        cursor[0] = cx + FRAME_SIZE
        cursor[1] = cy

    def _build(self) -> None:
        self._atlas_surface = pygame.Surface((ATLAS_SIZE, ATLAS_SIZE), pygame.SRCALPHA)
        self._atlas_surface.fill((0, 0, 0, 0))
        cursor = [0, 0]  # [x, y] mutable for _pack_frame

        # Heroes
        for hc in ("warrior", "ranger", "rogue", "wizard", "cleric"):
            clips = HeroSpriteLibrary.clips_for(hc, size=FRAME_SIZE)
            for action, clip in clips.items():
                for fi, surf in enumerate(clip.frames):
                    self._pack_frame(surf, ("hero", hc, action, fi), cursor)

        # Enemies
        for et in ("goblin", "wolf", "skeleton", "skeleton_archer", "spider", "bandit"):
            clips = EnemySpriteLibrary.clips_for(et, size=FRAME_SIZE)
            for action, clip in clips.items():
                for fi, surf in enumerate(clip.frames):
                    self._pack_frame(surf, ("enemy", et, action, fi), cursor)

        # Workers
        for wt in ("peasant", "peasant_builder", "guard", "tax_collector"):
            clips = WorkerSpriteLibrary.clips_for(wt, size=FRAME_SIZE)
            for action, clip in clips.items():
                for fi, surf in enumerate(clip.frames):
                    self._pack_frame(surf, ("worker", wt, action, fi), cursor)

        # Ranged VFX — shared billboard textures with pygame/Ursina legacy path (wk48 instancing).
        # Mythos S6 (`inst-parity-gap-fixes`): also pack the WK124 wizard "magic"
        # and cleric "heal" orbs so instanced volleys render per-kind like the
        # legacy per-Entity path (ursina_misc_props_sync.py) instead of as arrows.
        proj_surf = get_projectile_billboard_surface()
        self._pack_frame(proj_surf, ("vfx", "projectile", "arrow", 0), cursor)
        self._pack_frame(get_magic_billboard_surface(), ("vfx", "projectile", "magic", 0), cursor)
        self._pack_frame(get_heal_billboard_surface(), ("vfx", "projectile", "heal", 0), cursor)

    def get_ursina_texture(self):
        """Return the single GPU-resident atlas Texture (lazy-created, cached)."""
        if self._ursina_tex is not None:
            return self._ursina_tex
        from game.graphics.terrain_texture_bridge import TerrainTextureBridge
        self._ursina_tex = TerrainTextureBridge.surface_to_texture(
            self._atlas_surface, cache_key="__unit_atlas_master__"
        )
        return self._ursina_tex

    def get_texture_offset_scale(self, unit_type: str, class_key: str, action: str, frame_idx: int):
        """Return (offset_x, offset_y, scale_x, scale_y) for atlas UV sub-region."""
        uv = self.lookup_uv(unit_type, class_key, action, frame_idx)
        # uv = (u_start, v_start, u_width, v_height)
        return (uv[0], uv[1], uv[2], uv[3])
