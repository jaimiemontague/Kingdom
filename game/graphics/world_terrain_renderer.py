"""WK66 Round A-1 (L10): graphics-side terrain + fog drawing for the pygame path.

The sim's :class:`game.world.World` used to own ``render``/``render_fog`` plus the
two reusable fog-overlay ``pygame.Surface`` objects, which dragged a ``pygame``
import (and Surface allocations) into the headless simulation for nothing. This
module moves that drawing out of the sim: ``WorldTerrainRenderer`` owns the fog
Surfaces and draws the tile map + fog-of-war overlay, reading world STATE
(``tiles``, ``visibility``, ``width``/``height``) off the ``world`` passed in.

This is a behavior-preserving code move — the bodies of ``render``/``render_fog``
are the former ``World.render``/``World.render_fog`` verbatim, with ``self.`` →
``world.`` for world-state reads and the fog Surfaces now owned here.
"""
from __future__ import annotations

import pygame

from config import TILE_SIZE, COLOR_GRASS
from game.graphics.tile_sprites import TileSpriteLibrary
from game.world import TILE_COLORS, Visibility


class WorldTerrainRenderer:
    """Pygame terrain + fog-of-war drawing for a :class:`game.world.World`.

    Instantiate once (the fog overlays are reusable Surfaces) and call
    :meth:`render` / :meth:`render_fog` per frame with the live ``world``.
    """

    def __init__(self) -> None:
        # Reusable fog tile overlays (avoid per-tile Surface allocations).
        self._fog_tile_unseen = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        self._fog_tile_unseen.fill((0, 0, 0, 255))
        self._fog_tile_seen = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
        self._fog_tile_seen.fill((0, 0, 0, 170))

    def render(self, world, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render the tile map."""
        cam_x, cam_y = camera_offset

        # Calculate visible tile range
        start_x = max(0, int(cam_x // TILE_SIZE))
        start_y = max(0, int(cam_y // TILE_SIZE))
        end_x = min(world.width, int((cam_x + surface.get_width()) // TILE_SIZE) + 1)
        end_y = min(world.height, int((cam_y + surface.get_height()) // TILE_SIZE) + 1)

        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                tile_type = world.tiles[y][x]

                screen_x = int(x * TILE_SIZE - cam_x)
                screen_y = int(y * TILE_SIZE - cam_y)

                # Pixel-art sprites (procedural fallback) for tiles.
                tile_img = TileSpriteLibrary.get(tile_type, x, y, size=TILE_SIZE)
                if tile_img is not None:
                    surface.blit(tile_img, (screen_x, screen_y))
                else:
                    # Safety fallback (shouldn't normally happen)
                    color = TILE_COLORS.get(tile_type, COLOR_GRASS)
                    pygame.draw.rect(surface, color, (screen_x, screen_y, TILE_SIZE, TILE_SIZE))

    def render_fog(self, world, surface: pygame.Surface, camera_offset: tuple = (0, 0)):
        """Render fog-of-war overlay over the currently-visible screen region."""
        cam_x, cam_y = camera_offset

        start_x = max(0, int(cam_x // TILE_SIZE))
        start_y = max(0, int(cam_y // TILE_SIZE))
        end_x = min(world.width, int((cam_x + surface.get_width()) // TILE_SIZE) + 1)
        end_y = min(world.height, int((cam_y + surface.get_height()) // TILE_SIZE) + 1)

        for y in range(start_y, end_y):
            vis_row = world.visibility[y]
            for x in range(start_x, end_x):
                state = vis_row[x]
                if state == Visibility.VISIBLE:
                    continue

                screen_x = x * TILE_SIZE - cam_x
                screen_y = y * TILE_SIZE - cam_y

                if state == Visibility.UNSEEN:
                    surface.blit(self._fog_tile_unseen, (screen_x, screen_y))
                else:
                    surface.blit(self._fog_tile_seen, (screen_x, screen_y))
