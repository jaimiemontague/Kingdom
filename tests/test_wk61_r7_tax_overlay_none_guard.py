"""WK61 R7 — guard hold-G overlay snapshot when non-tax buildings return None (Agent 03)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from game.graphics.ursina_renderer import (
    building_tax_overlay_snapshot,
    is_tax_gold_overlay_held,
    set_tax_gold_overlay_held,
)
from tests.test_wk61_r6_tax_gold_overlay_data import NON_TAX_STASH_INSTANCES


class _NonTaxBuildingWithMixinMethods:
    """Building that exposes overlay methods but has no tax stash (WK61-R7-BUG-001)."""

    has_tax_stash_data = False

    def get_overlay_tax_gold(self) -> None:
        return None


def test_building_tax_overlay_snapshot_none_guard_without_int_crash() -> None:
    """Regression: int(None) must not run when get_overlay_tax_gold returns None."""
    building = _NonTaxBuildingWithMixinMethods()
    assert building.get_overlay_tax_gold() is None
    has_data, amount = building_tax_overlay_snapshot(building, is_lair=False)
    assert has_data is False
    assert amount == 0


@pytest.mark.parametrize("type_key,building", NON_TAX_STASH_INSTANCES)
def test_non_tax_stash_instances_skip_overlay_snapshot(type_key: str, building) -> None:
    assert building.has_tax_stash_data is False
    assert building.get_overlay_tax_gold() is None
    has_data, amount = building_tax_overlay_snapshot(building, is_lair=False)
    assert has_data is False, type_key
    assert amount == 0, type_key


def test_release_g_clears_overlay_held_flag() -> None:
    set_tax_gold_overlay_held(True)
    assert is_tax_gold_overlay_held() is True
    set_tax_gold_overlay_held(False)
    with patch("ursina.held_keys", {}, create=True):
        assert is_tax_gold_overlay_held() is False
    set_tax_gold_overlay_held(False)


def test_tax_stash_snapshot_still_returns_amount() -> None:
    tax_building = SimpleNamespace(
        has_tax_stash_data=True,
        get_overlay_tax_gold=lambda: 42,
    )
    has_data, amount = building_tax_overlay_snapshot(tax_building, is_lair=False)
    assert has_data is True
    assert amount == 42
