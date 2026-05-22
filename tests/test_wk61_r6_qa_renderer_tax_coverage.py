"""Agent 11 QA bridge: renderer tax snapshot must cover all tax-stash building classes."""
from __future__ import annotations

import pytest

from game.graphics.ursina_renderer import building_tax_overlay_snapshot
from tests.test_wk61_r6_tax_gold_overlay_data import NON_TAX_STASH_INSTANCES, TAX_STASH_INSTANCES


@pytest.mark.parametrize("type_key,building", TAX_STASH_INSTANCES)
def test_renderer_snapshot_reads_every_tax_stash_building_type(
    type_key: str, building
) -> None:
    """WK61-R6: hold-G overlay data path must not be marketplace-only."""
    if hasattr(building, "add_tax_gold"):
        building.add_tax_gold(25)
    else:
        building.stored_tax_gold = 25

    has_data, amount = building_tax_overlay_snapshot(building, is_lair=False)
    assert has_data is True, type_key
    assert amount == 25, type_key


@pytest.mark.parametrize("type_key,building", NON_TAX_STASH_INSTANCES)
def test_renderer_snapshot_skips_non_tax_stash_building_types(
    type_key: str, building
) -> None:
    """Regression: snapshot must return (False, 0) without calling int(None)."""
    assert building.has_tax_stash_data is False
    assert building.get_overlay_tax_gold() is None
    has_data, amount = building_tax_overlay_snapshot(building, is_lair=False)
    assert has_data is False, type_key
    assert amount == 0
