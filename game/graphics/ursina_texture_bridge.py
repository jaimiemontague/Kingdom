"""
Bridge pygame Surfaces from existing sprite libraries into Ursina Texture objects.

Used by the Ursina renderer for terrain tiles, building facades, and unit billboards.
Textures are cached by stable string keys to avoid per-frame uploads.

Ursina is lazy-imported inside conversion functions so headless tooling can import
this module without initializing Panda3D.
"""
from __future__ import annotations

from typing import Any, Dict

import pygame

from config import TILE_SIZE
from game.graphics.building_sprites import BuildingSpriteLibrary
from game.graphics.enemy_sprites import EnemySpriteLibrary
from game.graphics.hero_sprites import HeroSpriteLibrary, HeroSpriteSpec
from game.graphics.tile_sprites import TileSpriteLibrary
from game.graphics.worker_sprites import WorkerSpriteLibrary

_texture_cache: Dict[str, Any] = {}


def _building_type_key(building_type: object) -> str:
    """Match BuildingSpriteLibrary key normalization (see building_sprites.get)."""
    if building_type is None:
        return "building"
    return str(getattr(building_type, "value", building_type))


def clear_texture_cache() -> None:
    """Clear cached Ursina textures (e.g. after hot reload)."""
    _texture_cache.clear()


def pygame_surface_to_ursina_texture(
    surface: pygame.Surface,
    *,
    cache_key: str,
) -> Any:
    """
    Convert a pygame Surface to an Ursina Texture, with process-wide caching.

    Returns the Ursina Texture instance (typed as Any to avoid importing ursina at module load).
    """
    hit = _texture_cache.get(cache_key)
    if hit is not None:
        return hit

    from PIL import Image
    from ursina import Texture

    if surface.get_bytesize() == 0:
        raise ValueError("surface_to_texture: empty surface")
    w, h = surface.get_size()
    raw = pygame.image.tostring(surface, "RGBA", False)
    img = Image.frombytes("RGBA", (w, h), raw)
    tex = Texture(img)
    _texture_cache[cache_key] = tex
    return tex


def get_tile_texture(tile_type: int, tx: int, ty: int, *, tile_size: int | None = None) -> Any:
    """Terrain tile from TileSpriteLibrary → cached Ursina Texture."""
    ts = int(tile_size if tile_size is not None else TILE_SIZE)
    key = f"t:{int(tile_type)}:{int(tx)}:{int(ty)}:{ts}"
    hit = _texture_cache.get(key)
    if hit is not None:
        return hit

    surf = TileSpriteLibrary.get(int(tile_type), int(tx), int(ty), size=ts)
    if surf is None:
        raise RuntimeError(f"TileSpriteLibrary returned None for ({tile_type}, {tx}, {ty})")
    return pygame_surface_to_ursina_texture(surf, cache_key=key)


def get_building_texture(
    building_type: object,
    state: str,
    *,
    size_px: tuple[int, int],
) -> Any:
    """Building facade from BuildingSpriteLibrary → cached Ursina Texture."""
    bt = _building_type_key(building_type)
    w, h = int(size_px[0]), int(size_px[1])
    st = str(state or "built")
    key = f"b:{bt}:{st}:{w}:{h}"
    hit = _texture_cache.get(key)
    if hit is not None:
        return hit

    surf = BuildingSpriteLibrary.get(building_type, st, size_px=(w, h))
    if surf is None:
        raise RuntimeError(f"BuildingSpriteLibrary returned None for ({bt}, {st}, {w}x{h})")
    return pygame_surface_to_ursina_texture(surf, cache_key=key)


def _normalize_class_name(value: object) -> str:
    if value is None:
        return "warrior"
    v = getattr(value, "value", value)
    return str(v).lower()


def get_hero_idle_texture(hero_class: object, *, size: int = 32) -> Any:
    """First frame of hero idle clip → cached Ursina Texture."""
    hc = _normalize_class_name(hero_class)
    sz = int(size)
    spec = HeroSpriteSpec(size=sz)
    key = f"h:{hc}:{sz}:idle0:ph{hash(spec) & 0xffffffff:08x}"
    hit = _texture_cache.get(key)
    if hit is not None:
        return hit

    clips = HeroSpriteLibrary.clips_for(hc, size=sz)
    idle = clips.get("idle")
    if idle is None or not idle.frames:
        raise RuntimeError(f"HeroSpriteLibrary missing idle for {hc}")
    surf = idle.frames[0]
    return pygame_surface_to_ursina_texture(surf, cache_key=key)


def get_enemy_idle_texture(enemy_type: object, *, size: int = 32) -> Any:
    """First frame of enemy idle clip → cached Ursina Texture."""
    et = _normalize_class_name(enemy_type)
    if et in ("", "none"):
        et = "goblin"
    sz = int(size)
    key = f"e:{et}:{sz}:idle0"
    hit = _texture_cache.get(key)
    if hit is not None:
        return hit

    clips = EnemySpriteLibrary.clips_for(et, size=sz)
    idle = clips.get("idle")
    if idle is None or not idle.frames:
        raise RuntimeError(f"EnemySpriteLibrary missing idle for {et}")
    surf = idle.frames[0]
    return pygame_surface_to_ursina_texture(surf, cache_key=key)


def get_worker_idle_texture(worker_type: object, *, size: int = 32) -> Any:
    """First frame of worker idle clip → cached Ursina Texture."""
    wt = _normalize_class_name(worker_type)
    if wt in ("", "none"):
        wt = "peasant"
    sz = int(size)
    key = f"w:{wt}:{sz}:idle0"
    hit = _texture_cache.get(key)
    if hit is not None:
        return hit

    clips = WorkerSpriteLibrary.clips_for(wt, size=sz)
    idle = clips.get("idle")
    if idle is None or not idle.frames:
        raise RuntimeError(f"WorkerSpriteLibrary missing idle for {wt}")
    surf = idle.frames[0]
    return pygame_surface_to_ursina_texture(surf, cache_key=key)


def texture_cache_size() -> int:
    return len(_texture_cache)
