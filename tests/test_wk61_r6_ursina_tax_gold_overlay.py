"""WK61 R6 — Ursina hold-G taxable gold overlay coverage (Agent 03)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from game.graphics.ursina_renderer import (
    _building_gold_overlay_y,
    _prefab_local_top_y,
    building_tax_overlay_snapshot,
    is_tax_gold_overlay_held,
    set_tax_gold_overlay_held,
)


class _TaxBuilding:
    has_tax_stash_data = True

    def __init__(self, amount: int) -> None:
        self.stored_tax_gold = amount

    def get_overlay_tax_gold(self) -> int:
        return int(self.stored_tax_gold)


class _StubChild:
    def __init__(self, y: float, scale_y: float) -> None:
        self.y = y
        self.scale = SimpleNamespace(y=scale_y)


def test_building_tax_overlay_snapshot_uses_mixin_contract() -> None:
    has_data, amount = building_tax_overlay_snapshot(_TaxBuilding(75), is_lair=False)
    assert has_data is True
    assert amount == 75


def test_building_tax_overlay_snapshot_covers_marketplace_blacksmith_guilds() -> None:
    for amount in (42, 17, 0):
        has_data, got = building_tax_overlay_snapshot(_TaxBuilding(amount), is_lair=False)
        assert has_data is True
        assert got == amount


def test_building_tax_overlay_snapshot_skips_lairs_and_pois() -> None:
    lair = SimpleNamespace(stash_gold=200, stored_tax_gold=0)
    poi = SimpleNamespace(stored_tax_gold=50, is_poi=True)

    assert building_tax_overlay_snapshot(lair, is_lair=True) == (False, 0)
    assert building_tax_overlay_snapshot(poi, is_lair=False) == (False, 0)


def test_building_tax_overlay_snapshot_legacy_stored_tax_gold() -> None:
    has_data, amount = building_tax_overlay_snapshot(
        SimpleNamespace(stored_tax_gold=12),
        is_lair=False,
    )
    assert has_data is True
    assert amount == 12


def test_hold_release_tax_gold_overlay_flag() -> None:
    set_tax_gold_overlay_held(True)
    assert is_tax_gold_overlay_held() is True
    set_tax_gold_overlay_held(False)
    with patch("ursina.held_keys", {}, create=True):
        assert is_tax_gold_overlay_held() is False
    with patch("ursina.held_keys", {"g": 1}, create=True):
        assert is_tax_gold_overlay_held() is True
    set_tax_gold_overlay_held(False)


def test_prefab_local_top_y_uses_child_bounds() -> None:
    ent = SimpleNamespace(children=[_StubChild(0.4, 2.0), _StubChild(1.1, 1.5)])
    top = _prefab_local_top_y(ent)
    assert top >= 1.9
    assert getattr(ent, "_ks_prefab_top_y") == top


def test_building_gold_overlay_y_prefers_prefab_roof() -> None:
    ent = SimpleNamespace(_ks_prefab_container=True, _ks_prefab_top_y=2.4, children=[])
    assert _building_gold_overlay_y(ent) == pytest.approx(2.9)


def test_building_gold_overlay_y_billboard_uses_height() -> None:
    ent = SimpleNamespace(_ks_billboard_configured=True)
    assert _building_gold_overlay_y(ent, hy=2.0) == pytest.approx(1.5)
