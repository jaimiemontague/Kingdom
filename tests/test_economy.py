from __future__ import annotations

from config import HERO_HIRE_COST, TAX_RATE


def test_can_afford_building_with_sufficient_gold(make_economy) -> None:
    economy = make_economy(player_gold=500)

    assert economy.can_afford_building("marketplace") is True


def test_buy_building_deducts_gold_and_logs_transaction(make_economy) -> None:
    economy = make_economy(player_gold=500)
    before_gold = economy.player_gold

    success = economy.buy_building("marketplace")

    assert success is True
    assert economy.player_gold < before_gold
    assert economy.transaction_log[-1]["type"] == "building_purchase"
    assert economy.transaction_log[-1]["building"] == "marketplace"


def test_buy_building_fails_with_insufficient_gold(make_economy) -> None:
    economy = make_economy(player_gold=0)

    success = economy.buy_building("marketplace")

    assert success is False
    assert economy.player_gold == 0
    assert economy.transaction_log == []


def test_can_afford_and_hire_hero(make_economy) -> None:
    economy = make_economy(player_gold=HERO_HIRE_COST)

    assert economy.can_afford_hero() is True
    assert economy.hire_hero() is True
    assert economy.player_gold == 0
    assert economy.transaction_log[-1]["type"] == "hero_hire"


def test_hero_purchase_applies_tax_and_updates_totals(make_economy) -> None:
    economy = make_economy(player_gold=0)

    tax = economy.hero_purchase("Aria", "Potion", 40)

    assert tax == int(40 * TAX_RATE)
    assert economy.player_gold == tax
    assert economy.total_tax_collected == tax
    assert economy.total_spent_by_heroes == 40
    assert economy.transaction_log[-1]["type"] == "hero_purchase"


def test_add_and_claim_bounty_log_entries(make_economy) -> None:
    economy = make_economy(player_gold=200)

    placed = economy.add_bounty(50)
    economy.claim_bounty("Theron", 50)

    assert placed is True
    assert economy.player_gold == 150
    assert economy.transaction_log[-2]["type"] == "bounty_placed"
    assert economy.transaction_log[-1]["type"] == "bounty_claimed"
    assert economy.transaction_log[-1]["hero"] == "Theron"


def test_get_recent_transactions_returns_tail(make_economy) -> None:
    economy = make_economy(player_gold=1000)
    economy.buy_building("marketplace")
    economy.hire_hero()
    economy.add_bounty(25)

    recent = economy.get_recent_transactions(count=2)

    assert len(recent) == 2
    assert recent[0]["type"] == "hero_hire"
    assert recent[1]["type"] == "bounty_placed"
