"""WK61-R11-BUG-003: Marketplace passive taxable income accrues on interval."""

from __future__ import annotations

from config import (
    MARKETPLACE_PASSIVE_TAX_INTERVAL_MS,
    MARKETPLACE_PASSIVE_TAX_MAX,
    MARKETPLACE_PASSIVE_TAX_MIN,
)
from game.entities.buildings.economic import Marketplace
from game.sim.determinism import set_sim_seed
from game.sim.timebase import set_sim_now_ms


def test_marketplace_passive_tax_accrues_into_stored_tax_gold() -> None:
    set_sim_seed(42)
    set_sim_now_ms(0)
    market = Marketplace(10, 10)
    market.is_constructed = True
    market._passive_tax_next_ms = MARKETPLACE_PASSIVE_TAX_INTERVAL_MS

    set_sim_now_ms(MARKETPLACE_PASSIVE_TAX_INTERVAL_MS)
    market.update(0.0, economy=None)

    assert MARKETPLACE_PASSIVE_TAX_MIN <= market.stored_tax_gold <= MARKETPLACE_PASSIVE_TAX_MAX


def test_marketplace_passive_tax_deterministic_with_seed() -> None:
    set_sim_seed(99)
    set_sim_now_ms(0)

    first = Marketplace(0, 0)
    first.is_constructed = True
    first._passive_tax_next_ms = MARKETPLACE_PASSIVE_TAX_INTERVAL_MS

    set_sim_seed(99)
    set_sim_now_ms(0)
    second = Marketplace(0, 0)
    second.is_constructed = True
    second._passive_tax_next_ms = MARKETPLACE_PASSIVE_TAX_INTERVAL_MS

    set_sim_now_ms(MARKETPLACE_PASSIVE_TAX_INTERVAL_MS)
    first.update(0.0, economy=None)

    set_sim_seed(99)
    set_sim_now_ms(0)
    set_sim_now_ms(MARKETPLACE_PASSIVE_TAX_INTERVAL_MS)
    second.update(0.0, economy=None)

    assert first.stored_tax_gold == second.stored_tax_gold
    assert first.stored_tax_gold > 0
