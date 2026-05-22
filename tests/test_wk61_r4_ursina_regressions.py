"""WK61 R4 Ursina regression helpers (Agent 03)."""
from __future__ import annotations

from unittest.mock import patch

from game.graphics.ursina_pick import _billboard_y_offsets, pick_unit_at_screen
from game.graphics.ursina_renderer import (
    is_tax_gold_overlay_held,
    set_tax_gold_overlay_held,
)


class _StubEntity:
    def __init__(self, x: float, y: float, *, alive: bool = True, hp: int = 100):
        self.x = x
        self.y = y
        self.is_alive = alive
        self.hp = hp
        self.size = 16


def test_tax_gold_overlay_flag_without_ursina() -> None:
    set_tax_gold_overlay_held(True)
    assert is_tax_gold_overlay_held() is True
    set_tax_gold_overlay_held(False)
    with patch("ursina.held_keys", {"g": 1}, create=True):
        assert is_tax_gold_overlay_held() is True
    set_tax_gold_overlay_held(False)


def test_billboard_y_offsets_positive() -> None:
    offs = _billboard_y_offsets()
    assert offs["hero"] > 0
    assert offs["enemy"] > 0
    assert offs["guard"] > offs["enemy"]


def test_pick_unit_at_screen_uses_projection(monkeypatch) -> None:
    hero = _StubEntity(100.0, 200.0)
    monkeypatch.setattr(
        "game.graphics.ursina_pick.sim_xy_to_virtual_screen",
        lambda sx, sy, yoff, virtual_w=1920, virtual_h=1080: (50.0, 60.0),
    )
    hit = pick_unit_at_screen((52, 58), heroes=[hero], pick_radius_px=10.0)
    assert hit == ("hero", hero)


def test_pick_unit_at_screen_respects_radius(monkeypatch) -> None:
    hero = _StubEntity(100.0, 200.0)
    monkeypatch.setattr(
        "game.graphics.ursina_pick.sim_xy_to_virtual_screen",
        lambda sx, sy, yoff, virtual_w=1920, virtual_h=1080: (50.0, 60.0),
    )
    assert pick_unit_at_screen((200, 200), heroes=[hero], pick_radius_px=10.0) is None
