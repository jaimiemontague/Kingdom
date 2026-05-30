"""WK61 R11 — hold-G gold overlay world-space Y above building meshes (Agent 03 BUG-004)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# WK87: _sync_building_worldspace_ui moved to ursina_building_ui; patch Text/Vec3/scene
# on the module where the function now reads them ("patch where it's used").
from game.graphics import ursina_building_ui as ur
from game.graphics.ursina_renderer import (
    _building_gold_overlay_world_y,
    _sync_building_worldspace_ui,
    set_tax_gold_overlay_held,
)


class _StubGoldLabel:
    def __init__(self) -> None:
        self.text = ""
        self.color = None
        self.enabled = False
        self.parent = None
        self.world_position = None


def test_building_gold_overlay_world_y_prefab_includes_terrain_and_clearance() -> None:
    ent = SimpleNamespace(_ks_building_mode="prefab", _ks_prefab_top_y=2.4, children=[])
    terrain_y = 3.5
    world_y = _building_gold_overlay_world_y(ent, terrain_y=terrain_y, hy=2.0)
    # local roof = 2.4 + 0.50 = 2.9; + terrain 3.5 + 1.2 clearance
    assert world_y == pytest.approx(3.5 + 2.9 + 1.2)


def test_building_gold_overlay_world_y_billboard_includes_terrain() -> None:
    ent = SimpleNamespace(_ks_billboard_configured=True)
    terrain_y = 1.0
    hy = 2.0
    world_y = _building_gold_overlay_world_y(ent, terrain_y=terrain_y, hy=hy)
    local_roof = max(hy * 0.75, 0.9)
    assert world_y == pytest.approx(terrain_y + local_roof + 1.2)


def test_sync_building_worldspace_ui_gold_label_scene_parent_and_world_position() -> None:
    building = SimpleNamespace(
        has_tax_stash_data=True,
        get_overlay_tax_gold=lambda: 42,
    )
    ent = SimpleNamespace(_ks_building_mode="prefab", _ks_prefab_top_y=2.0, children=[])
    created: list[_StubGoldLabel] = []
    scene_stub = object()

    def _fake_text(**kwargs):
        lab = _StubGoldLabel()
        lab.text = kwargs.get("text", "")
        lab.color = kwargs.get("color")
        lab.parent = kwargs.get("parent")
        created.append(lab)
        return lab

    set_tax_gold_overlay_held(True)
    try:
        with patch.object(ur, "scene", scene_stub):
            with patch.object(ur, "Text", side_effect=_fake_text):
                with patch.object(ur, "Vec3", side_effect=lambda x, y, z: (x, y, z)):
                    _sync_building_worldspace_ui(
                        building,
                        "marketplace",
                        ent,
                        is_lair=False,
                        wx=10.5,
                        wz=-20.25,
                        terrain_y=4.0,
                        hy=2.5,
                    )

        assert len(created) == 1
        assert created[0].parent is scene_stub
        assert created[0].text == "$42"
        gold = ent._ks_gold_label
        assert gold.world_position == pytest.approx((10.5, _building_gold_overlay_world_y(ent, terrain_y=4.0, hy=2.5), -20.25))
    finally:
        set_tax_gold_overlay_held(False)


def test_sync_building_worldspace_ui_zero_stash_still_scene_parented() -> None:
    building = SimpleNamespace(
        has_tax_stash_data=True,
        get_overlay_tax_gold=lambda: 0,
    )
    ent = SimpleNamespace(_ks_building_mode="prefab", _ks_prefab_top_y=1.8, children=[])
    scene_stub = object()

    def _fake_text(**kwargs):
        lab = _StubGoldLabel()
        lab.text = kwargs.get("text", "")
        lab.color = kwargs.get("color")
        lab.parent = kwargs.get("parent")
        return lab

    set_tax_gold_overlay_held(True)
    try:
        with patch.object(ur, "scene", scene_stub):
            with patch.object(ur, "Text", side_effect=_fake_text):
                with patch.object(ur, "Vec3", side_effect=lambda x, y, z: (x, y, z)):
                    _sync_building_worldspace_ui(
                        building,
                        "marketplace",
                        ent,
                        is_lair=False,
                        wx=0.0,
                        wz=0.0,
                        terrain_y=0.0,
                        hy=2.0,
                    )

        assert ent._ks_gold_label.parent is scene_stub
        assert ent._ks_gold_label.text == "$0"
        assert ent._ks_gold_label.color.r == pytest.approx(0.55)
    finally:
        set_tax_gold_overlay_held(False)
