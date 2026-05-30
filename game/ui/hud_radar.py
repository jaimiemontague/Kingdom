"""Radar minimap rendering for the HUD bottom bar (WK93 slice of hud.py).

Extracted VERBATIM from game/ui/hud.py (WK93 Round B-10): the radar-minimap
cluster — ``world_to_radar`` (coordinate map), ``ensure_radar_terrain_surface``
(cached terrain underlay), and ``render_radar_minimap`` (entity/POI dot overlay).
The cache state (``_radar_terrain_cache_key`` / ``_radar_terrain_surface``) lives
on the HUD instance and is accessed here via the ``hud`` argument. HUD keeps
1-line delegating wrappers so the render call site is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from game.ui.hud import HUD


def world_to_radar(
    wx: float, wy: float, inner: pygame.Rect, world_w: int, world_h: int
) -> tuple[int, int]:
    """Map a world-pixel coordinate to a radar minimap pixel coordinate (WK52)."""
    mx = inner.x + int(wx / world_w * inner.width)
    my = inner.y + int(wy / world_h * inner.height)
    mx = max(inner.left, min(inner.right - 1, mx))
    my = max(inner.top, min(inner.bottom - 1, my))
    return (mx, my)


def ensure_radar_terrain_surface(hud: "HUD", inner: pygame.Rect, world) -> pygame.Surface | None:
    """Sampled terrain under radar dots; cached by inner size + world dimensions (WK52 R4)."""
    if world is None:
        return None
    from config import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE
    from game.world import TileType, Visibility

    key = (inner.width, inner.height, int(world.width), int(world.height))
    if hud._radar_terrain_cache_key == key and hud._radar_terrain_surface is not None:
        return hud._radar_terrain_surface

    surf = pygame.Surface((inner.width, inner.height))
    grass = (25, 50, 25)
    water = (25, 50, 100)
    unseen = (12, 14, 22)
    mountain_rgb = (80, 80, 90)
    ww = float(MAP_WIDTH * TILE_SIZE)
    wh = float(MAP_HEIGHT * TILE_SIZE)
    tree_dot = (40, 75, 40)
    mountain_type = getattr(TileType, "MOUNTAIN", None)
    for my in range(inner.height):
        for mx in range(inner.width):
            wx = (mx + 0.5) / inner.width * ww
            wy = (my + 0.5) / inner.height * wh
            gx, gy = world.world_to_grid(wx, wy)
            if not (0 <= gx < world.width and 0 <= gy < world.height):
                surf.set_at((mx, my), unseen)
                continue
            vis = world.visibility[gy][gx]
            if vis == Visibility.UNSEEN:
                surf.set_at((mx, my), unseen)
                continue
            tt = world.tiles[gy][gx]
            if tt == TileType.WATER:
                surf.set_at((mx, my), water)
            elif mountain_type is not None and tt == mountain_type:
                surf.set_at((mx, my), mountain_rgb)
            else:
                # PATH / GRASS share macro fill; TREE second pass draws lighter dot.
                # TODO: render mountain tiles when world.TileType.MOUNTAIN exists
                surf.set_at((mx, my), grass)
    for my in range(inner.height):
        for mx in range(inner.width):
            wx = (mx + 0.5) / inner.width * ww
            wy = (my + 0.5) / inner.height * wh
            gx, gy = world.world_to_grid(wx, wy)
            if not (0 <= gx < world.width and 0 <= gy < world.height):
                continue
            if world.visibility[gy][gx] == Visibility.UNSEEN:
                continue
            if world.tiles[gy][gx] == TileType.TREE:
                surf.set_at((mx, my), tree_dot)

    hud._radar_terrain_surface = surf
    hud._radar_terrain_cache_key = key
    return surf


def render_radar_minimap(
    hud: "HUD",
    surface: pygame.Surface,
    minimap_rect: pygame.Rect,
    game_state: dict,
) -> None:
    """Colored entity dots in bottom-bar minimap (WK52)."""
    from config import MAP_HEIGHT, MAP_WIDTH, TILE_SIZE

    world_w = MAP_WIDTH * TILE_SIZE
    world_h = MAP_HEIGHT * TILE_SIZE
    inner = minimap_rect.inflate(-6, -6)
    if inner.width <= 0 or inner.height <= 0:
        return

    world = game_state.get("world")
    terr = ensure_radar_terrain_surface(hud, inner, world)
    if terr is not None:
        surface.blit(terr, inner.topleft)
    else:
        pygame.draw.rect(surface, (12, 14, 22), inner)

    heroes = game_state.get("heroes") or []
    enemies = game_state.get("enemies") or []
    buildings = game_state.get("buildings") or []
    pin = hud._pin_slot

    def to_radar(wx: float, wy: float) -> tuple[int, int]:
        return world_to_radar(wx, wy, inner, world_w, world_h)

    def is_revealed(x: float, y: float) -> bool:
        if world is None:
            return True
        try:
            from game.world import Visibility

            gx, gy = world.world_to_grid(float(x), float(y))
            if 0 <= gx < world.width and 0 <= gy < world.height:
                return world.visibility[gy][gx] != Visibility.UNSEEN
        except Exception:
            pass
        return True

    for b in buildings:
        bx, by = getattr(b, "x", None), getattr(b, "y", None)
        if bx is None:
            sz = getattr(b, "size", (1, 1))
            bx = (getattr(b, "grid_x", 0) + sz[0] / 2) * TILE_SIZE
        if by is None:
            sz = getattr(b, "size", (1, 1))
            by = (getattr(b, "grid_y", 0) + sz[1] / 2) * TILE_SIZE
        if not is_revealed(float(bx), float(by)):
            continue
        btype = str(getattr(b, "building_type", "") or "").lower()
        is_lair = bool(getattr(b, "is_lair", False)) or "lair" in btype or "crypt" in btype
        rx, ry = to_radar(float(bx), float(by))
        if btype == "castle":
            pygame.draw.rect(surface, (220, 220, 220), pygame.Rect(rx - 3, ry - 3, 6, 6), 1)
        elif is_lair:
            pygame.draw.circle(surface, (140, 30, 30), (rx, ry), 2)
        elif "guild" in btype or btype in (
            "warrior_guild",
            "ranger_guild",
            "rogue_guild",
            "wizard_guild",
        ):
            pygame.draw.circle(surface, (50, 180, 180), (rx, ry), 2)
        else:
            pygame.draw.circle(surface, (80, 100, 160), (rx, ry), 2)

    # WK55: POI icons on minimap
    _poi_colors = {
        "shrine": (100, 180, 255),
        "loot": (255, 215, 0),
        "combat": (220, 120, 30),
        "knowledge": (180, 100, 255),
        "npc": (100, 200, 100),
        "dungeon": (160, 40, 40),
        "boss": (255, 50, 50),
    }
    for b in buildings:
        if not getattr(b, "is_poi", False):
            continue
        if not getattr(b, "is_discovered", False):
            continue
        poi_def = getattr(b, "poi_def", None)
        if poi_def is None:
            continue
        sz = getattr(b, "size", (1, 1))
        bx = (getattr(b, "grid_x", 0) + sz[0] / 2) * TILE_SIZE
        by = (getattr(b, "grid_y", 0) + sz[1] / 2) * TILE_SIZE
        if not is_revealed(float(bx), float(by)):
            continue
        rx, ry = to_radar(float(bx), float(by))
        itype = getattr(poi_def, "interaction_type", "") or ""
        color = _poi_colors.get(itype, (150, 150, 150))
        if itype == "boss":
            pygame.draw.circle(surface, (255, 255, 255), (rx, ry), 4)
        pygame.draw.circle(surface, color, (rx, ry), 3)

    # WK55: Undiscovered-but-seen POIs shown as gray "?" dots on minimap
    for b in buildings:
        if not getattr(b, "is_poi", False):
            continue
        if getattr(b, "is_discovered", False):
            continue  # Already drawn above with full color
        poi_def = getattr(b, "poi_def", None)
        if poi_def is None:
            continue
        sz = getattr(b, "size", (1, 1))
        bx = (getattr(b, "grid_x", 0) + sz[0] / 2) * TILE_SIZE
        by = (getattr(b, "grid_y", 0) + sz[1] / 2) * TILE_SIZE
        # Only show if the tile has been SEEN (explored) — not UNSEEN
        if world is not None:
            try:
                gx, gy = world.world_to_grid(float(bx), float(by))
                if 0 <= gx < world.width and 0 <= gy < world.height:
                    if world.visibility[gy][gx] < 1:  # UNSEEN = 0
                        continue
                else:
                    continue
            except Exception:
                continue
        rx, ry = to_radar(float(bx), float(by))
        pygame.draw.circle(surface, (150, 150, 150), (rx, ry), 2)

    for en in enemies:
        ex, ey = float(getattr(en, "x", 0.0)), float(getattr(en, "y", 0.0))
        if int(getattr(en, "hp", 1)) <= 0:
            continue
        if not is_revealed(ex, ey):
            continue
        rx, ry = to_radar(ex, ey)
        pygame.draw.circle(surface, (200, 50, 50), (rx, ry), 2)

    pinned_pos = None
    for h in heroes:
        hx, hy = float(getattr(h, "x", 0.0)), float(getattr(h, "y", 0.0))
        if int(getattr(h, "hp", 1)) <= 0:
            continue
        if not is_revealed(hx, hy):
            continue
        rx, ry = to_radar(hx, hy)
        hid = str(getattr(h, "hero_id", "") or "")
        if pin.hero_id and hid == pin.hero_id:
            pinned_pos = (rx, ry)
        else:
            pygame.draw.circle(surface, (220, 180, 50), (rx, ry), 2)

    if pinned_pos is not None:
        px, py = pinned_pos
        pygame.draw.circle(surface, (255, 255, 255), (px, py), 4, 1)
        pygame.draw.circle(surface, (220, 180, 50), (px, py), 3)

    pygame.draw.rect(surface, (60, 65, 80), inner, 1)
