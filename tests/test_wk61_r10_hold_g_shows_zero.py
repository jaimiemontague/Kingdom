"""WK61 R10 — hold-G shows $0 on tax-stash buildings while G is held (Agent 03)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from game.entities.buildings.economic import Marketplace
from game.graphics.ursina_renderer import (
    _sync_building_worldspace_ui,
    building_tax_overlay_snapshot,
    is_tax_gold_overlay_held,
    set_tax_gold_overlay_held,
)


class _StubGoldLabel:
    def __init__(self) -> None:
        self.text = ""
        self.color = None
        self.enabled = False
        self.y = 0.0
        self.parent = None
        self.world_position = None


def test_marketplace_zero_stash_snapshot_while_g_held() -> None:
    marketplace = Marketplace(0, 0)
    assert marketplace.stored_tax_gold == 0

    set_tax_gold_overlay_held(True)
    try:
        has_tax, amount = building_tax_overlay_snapshot(marketplace, is_lair=False)
        assert has_tax is True
        assert amount == 0
        assert is_tax_gold_overlay_held() is True
    finally:
        set_tax_gold_overlay_held(False)


def test_sync_building_worldspace_ui_shows_zero_dollar_while_g_held() -> None:
    marketplace = Marketplace(0, 0)
    ent = SimpleNamespace(_ks_building_mode="prefab", _ks_prefab_top_y=2.0, children=[])
    created: list[_StubGoldLabel] = []
    scene_stub = object()

    def _fake_text(**kwargs):
        lab = _StubGoldLabel()
        lab.text = kwargs.get("text", "")
        lab.color = kwargs.get("color")
        lab.y = kwargs.get("y", 0.0)
        lab.parent = kwargs.get("parent")
        created.append(lab)
        return lab

    set_tax_gold_overlay_held(True)
    try:
        from game.graphics import ursina_building_ui as ur

        with patch.object(ur, "scene", scene_stub):
            with patch("game.graphics.ursina_building_ui.Text", side_effect=_fake_text):
                with patch("game.graphics.ursina_building_ui.Vec3", side_effect=lambda x, y, z: (x, y, z)):
                    _sync_building_worldspace_ui(
                        marketplace,
                        "marketplace",
                        ent,
                        is_lair=False,
                        wx=1.0,
                        wz=2.0,
                        terrain_y=0.5,
                        hy=2.0,
                    )

        assert len(created) == 1
        assert created[0].text == "$0"
        assert created[0].parent is scene_stub
        assert getattr(ent, "_ks_gold_label") is created[0]
    finally:
        set_tax_gold_overlay_held(False)


def test_sync_building_worldspace_ui_zero_stash_uses_dim_grey() -> None:
    building = SimpleNamespace(
        has_tax_stash_data=True,
        get_overlay_tax_gold=lambda: 0,
    )
    ent = SimpleNamespace(_ks_billboard_configured=True, children=[])
    created: list[_StubGoldLabel] = []

    def _fake_text(**kwargs):
        lab = _StubGoldLabel()
        lab.text = kwargs.get("text", "")
        lab.color = kwargs.get("color")
        created.append(lab)
        return lab

    set_tax_gold_overlay_held(True)
    try:
        from game.graphics import ursina_building_ui as ur

        with patch.object(ur, "scene", object()):
            with patch("game.graphics.ursina_building_ui.Text", side_effect=_fake_text):
                with patch("game.graphics.ursina_building_ui.Vec3", side_effect=lambda x, y, z: (x, y, z)):
                    _sync_building_worldspace_ui(
                        building, "food_stand", ent, is_lair=False, wx=0.0, wz=0.0, terrain_y=0.0, hy=2.0
                    )

        assert created[0].text == "$0"
        assert created[0].color is not None
        assert created[0].color.r == pytest.approx(0.55)
        assert created[0].color.g == pytest.approx(0.55)
        assert created[0].color.b == pytest.approx(0.55)
    finally:
        set_tax_gold_overlay_held(False)


def test_sync_building_worldspace_ui_positive_stash_uses_gold_color() -> None:
    building = SimpleNamespace(
        has_tax_stash_data=True,
        get_overlay_tax_gold=lambda: 17,
    )
    ent = SimpleNamespace(_ks_billboard_configured=True, children=[])
    created: list[_StubGoldLabel] = []

    def _fake_text(**kwargs):
        lab = _StubGoldLabel()
        lab.text = kwargs.get("text", "")
        lab.color = kwargs.get("color")
        created.append(lab)
        return lab

    set_tax_gold_overlay_held(True)
    try:
        from game.graphics import ursina_building_ui as ur

        with patch.object(ur, "scene", object()):
            with patch("game.graphics.ursina_building_ui.Text", side_effect=_fake_text):
                with patch("game.graphics.ursina_building_ui.Vec3", side_effect=lambda x, y, z: (x, y, z)):
                    _sync_building_worldspace_ui(
                        building, "marketplace", ent, is_lair=False, wx=0.0, wz=0.0, terrain_y=0.0, hy=2.0
                    )

        assert created[0].text == "$17"
        assert created[0].color.r == pytest.approx(1.0)
        assert created[0].color.g == pytest.approx(0.8)
        assert created[0].color.b == pytest.approx(0.2)
    finally:
        set_tax_gold_overlay_held(False)


def test_release_g_hides_existing_gold_label_without_rebuild() -> None:
    building = SimpleNamespace(
        has_tax_stash_data=True,
        get_overlay_tax_gold=lambda: 0,
    )
    ent = SimpleNamespace(_ks_billboard_configured=True, children=[])
    gold_ent = _StubGoldLabel()
    gold_ent.text = "$0"
    gold_ent.enabled = True
    ent._ks_gold_label = gold_ent

    set_tax_gold_overlay_held(False)
    with patch("ursina.held_keys", {}, create=True):
        with patch("game.graphics.ursina_building_ui.Vec3", side_effect=lambda x, y, z: (x, y, z)):
            with patch("game.graphics.ursina_building_ui.Text", MagicMock()) as mock_text:
                _sync_building_worldspace_ui(
                    building, "marketplace", ent, is_lair=False, wx=0.0, wz=0.0, terrain_y=0.0, hy=2.0
                )

    mock_text.assert_not_called()
    assert gold_ent.enabled is False
    assert ent._ks_gold_label is gold_ent
