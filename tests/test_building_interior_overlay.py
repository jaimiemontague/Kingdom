"""WK52 building interior overlay smoke tests."""

import pygame

from game.entities.buildings.castle import Castle
from game.entities.hero import Hero
from game.ui.building_interior_overlay import BuildingInteriorOverlay, _building_interior_heading


def test_heading_formats_type():
    c = Castle(2, 2)
    h = _building_interior_heading(c)
    assert "Castle" in h
    assert "Interior" in h


def test_overlay_show_hide_and_close_click():
    pygame.init()
    ov = BuildingInteriorOverlay()
    b = Castle(1, 1)
    h = Hero(10.0, 10.0, hero_class="warrior", hero_id="in1", name="Innie")
    b.occupants = [h]

    ov.show(b)
    assert ov.visible
    surf = pygame.Surface((640, 480))
    ov.render(surf)
    assert ov._close_rect is not None
    assert ov.handle_click((ov._close_rect.centerx, ov._close_rect.centery)) is True
    ov.hide()
    assert not ov.visible
