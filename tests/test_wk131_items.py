"""WK131 — Items & Inventory Core tests.

Covers (per the WK131 roadmap section + Agent 05 kickoff rails):
- item registry validation (slots/rarities/prices sane, unique ids/names)
- shop stock BYTE-COMPATIBLE with the pre-WK131 hardcoded dicts
- hero equip / auto-equip-if-better (weapon, armor, accessory incl. max_hp &
  speed deltas, consumable absorb) + backpack cap
- combat math provably unchanged for the same stats (legacy dict vs equip())
- loot determinism: same seed -> same drops; different seed -> differs
- enemy / boss / POI drop paths (incl. the sim_engine ENEMY_KILLED routing)
- shop buy/sell round trip incl. the 25% tax reservation
- HeroInventorySnapshot -> _compact_profile_dict carries accessory + backpack
- digest safety: NO loot-RNG draws when no kill / no POI interaction occurs
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from config import TAX_RATE
from game.content import items as items_registry
from game.content.items import ItemDef, RARITIES, SLOTS, get_item
from game.entities.buildings.base import RESEARCH_UNLOCKS
from game.entities.buildings.economic import Blacksmith, Marketplace
from game.entities.hero import Hero
from game.sim.determinism import set_sim_seed, get_rng
from game.systems import loot as loot_mod
from game.systems.loot import LootSystem
from game.systems.poi_interaction import POIInteractionSystem


@pytest.fixture(autouse=True)
def _reset_research_unlocks():
    snapshot = dict(RESEARCH_UNLOCKS)
    try:
        yield
    finally:
        RESEARCH_UNLOCKS.clear()
        RESEARCH_UNLOCKS.update(snapshot)


@pytest.fixture(autouse=True)
def _stable_seed():
    set_sim_seed(7)
    try:
        yield
    finally:
        set_sim_seed(1)


def _strip_id(d: dict) -> dict:
    out = dict(d)
    out.pop("id", None)
    return out


# ---------------------------------------------------------------------------
# 1. Registry validation
# ---------------------------------------------------------------------------

def test_registry_validation_all_items_sane():
    items = items_registry.all_items()
    assert 20 <= len(items) <= 25

    ids = [i.item_id for i in items]
    names = [i.name for i in items]
    assert len(set(ids)) == len(ids), "item ids must be unique"
    assert len(set(names)) == len(names), "item names must be unique"

    for item in items:
        assert isinstance(item, ItemDef)
        assert item.slot in SLOTS, item.item_id
        assert item.rarity in RARITIES, item.item_id
        assert item.buy_price > 0, item.item_id
        assert 0 < item.sell_price <= item.buy_price, item.item_id
        assert item.attack >= 0 and item.defense >= 0 and item.max_hp >= 0
        if item.slot == "weapon":
            assert item.attack > 0, item.item_id
        if item.slot == "armor":
            assert item.defense > 0, item.item_id
        if item.slot == "accessory":
            assert (item.attack + item.defense + item.max_hp) > 0 or item.speed > 0


def test_registry_has_required_slot_coverage():
    items = items_registry.all_items()
    by_slot = {s: [i for i in items if i.slot == s] for s in SLOTS}
    assert len(by_slot["weapon"]) >= 8
    assert len(by_slot["armor"]) >= 3
    assert 3 <= len(by_slot["accessory"]) <= 5
    assert len(by_slot["consumable"]) >= 2
    # All drop-pool ids resolve.
    for pool in (loot_mod.COMMON_DROP_POOL, loot_mod.UNCOMMON_DROP_POOL, loot_mod.RARE_PLUS_DROP_POOL):
        for item_id in pool:
            get_item(item_id)
    # Rare+ pool really is rare or better (boss drops).
    for item_id in loot_mod.RARE_PLUS_DROP_POOL:
        assert get_item(item_id).rarity in ("rare", "legendary")
    for item_id in loot_mod.COMMON_DROP_POOL:
        assert get_item(item_id).rarity == "common"


# ---------------------------------------------------------------------------
# 2. Shop stock unchanged (byte-compatible with pre-WK131 hardcoded dicts)
# ---------------------------------------------------------------------------

_LEGACY_MARKETPLACE_ITEMS = [
    {"name": "Dagger", "type": "weapon", "style": "melee", "price": 60, "attack": 4},
    {"name": "Short Bow", "type": "weapon", "style": "ranged", "price": 70, "attack": 4},
    {"name": "Apprentice Staff", "type": "weapon", "style": "magic", "price": 90, "attack": 6},
    {"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5},
    {"name": "Long Bow", "type": "weapon", "style": "ranged", "price": 140, "attack": 8},
    {"name": "Poison Dagger", "type": "weapon", "style": "melee", "price": 120, "attack": 7},
    {"name": "Steel Sword", "type": "weapon", "price": 150, "attack": 10},
    {"name": "Wizard Staff", "type": "weapon", "style": "magic", "price": 180, "attack": 12},
    {"name": "Leather Armor", "type": "armor", "price": 60, "defense": 3},
    {"name": "Chain Mail", "type": "armor", "price": 120, "defense": 7},
]

_LEGACY_BLACKSMITH_BASE = [
    {"name": "Iron Sword", "type": "weapon", "price": 48, "attack": 5},
    {"name": "Leather Armor", "type": "armor", "price": 36, "defense": 3},
]
_LEGACY_BLACKSMITH_WEAPONS = [
    {"name": "Steel Sword", "type": "weapon", "price": 90, "attack": 10},
    {"name": "Mithril Blade", "type": "weapon", "price": 150, "attack": 15},
]
_LEGACY_BLACKSMITH_ARMOR = [
    {"name": "Chain Mail", "type": "armor", "price": 72, "defense": 7},
    {"name": "Plate Armor", "type": "armor", "price": 120, "defense": 12},
]


def test_marketplace_stock_matches_pre_wk131_dicts_exactly():
    market = Marketplace(0, 0)
    assert [_strip_id(d) for d in market.items] == _LEGACY_MARKETPLACE_ITEMS
    available = market.get_available_items()
    assert _strip_id(available[0]) == {
        "name": "Healing Potion", "type": "potion", "price": 15, "effect": 50,
    }
    assert [_strip_id(d) for d in available[1:]] == _LEGACY_MARKETPLACE_ITEMS


def test_blacksmith_stock_matches_pre_wk131_dicts_exactly():
    smith = Blacksmith(0, 0)
    assert [_strip_id(d) for d in smith.base_items] == _LEGACY_BLACKSMITH_BASE
    assert [_strip_id(d) for d in smith.upgraded_weapons] == _LEGACY_BLACKSMITH_WEAPONS
    assert [_strip_id(d) for d in smith.upgraded_armor] == _LEGACY_BLACKSMITH_ARMOR
    # Without research: base only.
    assert [_strip_id(d) for d in smith.get_available_items()] == _LEGACY_BLACKSMITH_BASE


def test_shop_dicts_carry_registry_id_for_mapping():
    market = Marketplace(0, 0)
    for d in market.get_available_items():
        assert get_item(d["id"]).name == d["name"]


# ---------------------------------------------------------------------------
# 3. Equip / auto-equip / backpack
# ---------------------------------------------------------------------------

def test_equip_weapon_only_if_strictly_better():
    hero = Hero(0.0, 0.0, name="Equipper")
    assert hero.equip(get_item("iron_sword")) is True
    assert hero.weapon["name"] == "Iron Sword"
    assert hero.weapon["attack"] == 5
    # Equal or worse is refused.
    assert hero.equip(get_item("dagger")) is False
    assert hero.weapon["name"] == "Iron Sword"
    # Strictly better swaps in.
    assert hero.equip(get_item("steel_sword")) is True
    assert hero.weapon["attack"] == 10


def test_equip_armor_only_if_strictly_better():
    hero = Hero(0.0, 0.0, name="Armorer")
    hero.armor = {"name": "Chain Mail", "defense": 7}
    assert hero.equip(get_item("leather_armor")) is False
    assert hero.equip(get_item("plate_armor")) is True
    assert hero.armor == {"name": "Plate Armor", "defense": 12, "id": "plate_armor"}


def test_equip_accessory_applies_and_replaces_max_hp_speed_deltas():
    hero = Hero(0.0, 0.0, name="Trinketeer")
    base_max_hp = hero.max_hp
    base_speed = hero.speed

    pendant = get_item("vitality_pendant")  # +25 max_hp, rare
    assert hero.equip(pendant) is True
    assert hero.accessory["name"] == "Vitality Pendant"
    assert hero.max_hp == base_max_hp + 25
    assert hero.hp == base_max_hp + 25  # hp granted with the max bump

    # A weaker accessory is refused.
    assert hero.equip(get_item("ring_of_strength")) is False
    assert hero.accessory["name"] == "Vitality Pendant"
    assert hero.max_hp == base_max_hp + 25
    assert hero.speed == pytest.approx(base_speed)


def test_equip_accessory_swap_removes_old_deltas():
    hero = Hero(0.0, 0.0, name="Swapper")
    base_speed = hero.speed
    base_max_hp = hero.max_hp
    assert hero.equip(get_item("swift_boots")) is True  # +0.35 speed
    assert hero.speed == pytest.approx(base_speed + 0.35)
    # hawk_signet scores higher (atk2+def2=4 > 0.35*10=3.5).
    assert hero.equip(get_item("hawk_signet")) is True
    assert hero.accessory["name"] == "Hawk Signet"
    assert hero.speed == pytest.approx(base_speed)
    assert hero.max_hp == base_max_hp


def test_equip_consumable_absorbs_into_potion_counter():
    hero = Hero(0.0, 0.0, name="Drinker")
    hero.potions = 0
    assert hero.equip(get_item("healing_potion")) is True
    assert hero.potions == 1
    assert hero.potion_heal_amount == 50
    hero.potions = hero.max_potions
    assert hero.equip(get_item("healing_potion")) is False  # full -> backpack path


def test_receive_item_stores_then_drops_when_backpack_full():
    hero = Hero(0.0, 0.0, name="Carrier")
    hero.weapon = {"name": "Runed Warhammer", "attack": 18}  # nothing beats this
    hero.armor = {"name": "Dragonscale Armor", "defense": 16}
    dagger = get_item("dagger")
    for _ in range(hero.backpack_capacity):
        assert hero.receive_item(dagger) == "stored"
    assert len(hero.backpack) == hero.backpack_capacity
    assert hero.receive_item(dagger) == "dropped"
    assert len(hero.backpack) == hero.backpack_capacity
    assert 4 <= hero.backpack_capacity <= 6


# ---------------------------------------------------------------------------
# 4. Combat math provably unchanged for the same stats
# ---------------------------------------------------------------------------

def test_attack_defense_identical_legacy_dict_vs_equip():
    legacy = Hero(0.0, 0.0, name="Legacy", hero_class="warrior")
    modern = Hero(0.0, 0.0, name="Modern", hero_class="warrior")
    legacy.weapon = {"name": "Steel Sword", "attack": 10}   # pre-WK131 buy_item shape
    legacy.armor = {"name": "Chain Mail", "defense": 7}
    assert modern.equip(get_item("steel_sword")) is True
    assert modern.equip(get_item("chain_mail")) is True
    assert modern.attack == legacy.attack
    assert modern.defense == legacy.defense
    # No accessory -> totals match the raw formula exactly.
    assert legacy.attack == legacy.base_attack + 10 + (legacy.level - 1) * 2
    assert legacy.defense == legacy.base_defense + 7 + (legacy.level - 1)


def test_buy_item_legacy_dict_shape_still_works():
    hero = Hero(0.0, 0.0, name="Buyer")
    hero.gold = 200
    ok = hero.buy_item({"name": "Iron Sword", "type": "weapon", "price": 80, "attack": 5})
    assert ok is True
    assert hero.weapon == {"name": "Iron Sword", "attack": 5}
    assert hero.attack == hero.base_attack + 5


# ---------------------------------------------------------------------------
# 5. Loot determinism
# ---------------------------------------------------------------------------

def _roll_sequence(seed: int, n: int = 300) -> list[str]:
    set_sim_seed(seed)
    ls = LootSystem()
    out = []
    for i in range(n):
        item = ls.roll_enemy_drop("goblin" if i % 3 else "bandit_lord")
        out.append(item.item_id if item else "-")
    return out


def test_loot_same_seed_same_drops_different_seed_differs():
    a1 = _roll_sequence(123)
    a2 = _roll_sequence(123)
    b = _roll_sequence(456)
    assert a1 == a2
    assert a1 != b  # 300 mixed rolls: identical sequences are practically impossible


# ---------------------------------------------------------------------------
# 6. Drop paths: regular enemy, boss, sim_engine routing, POI
# ---------------------------------------------------------------------------

class _ScriptedRng:
    """random()/choice with scripted random() values (deterministic path tests)."""

    def __init__(self, randoms: list[float]):
        self._randoms = list(randoms)
        self._choice = random.Random(0)

    def random(self) -> float:
        return self._randoms.pop(0)

    def choice(self, seq):
        return seq[0]


def test_boss_always_drops_rare_plus():
    ls = LootSystem()
    for boss in ("bandit_lord", "demon_overlord"):
        for _ in range(20):
            item = ls.roll_enemy_drop(boss)
            assert item is not None
            assert item.rarity in ("rare", "legendary")


def test_regular_enemy_common_drop_chance_band():
    assert 0.05 <= loot_mod.ENEMY_DROP_CHANCE <= 0.08
    # Path check with scripted rng: below threshold drops, above doesn't.
    ls_hit = LootSystem(rng=_ScriptedRng([loot_mod.ENEMY_DROP_CHANCE - 0.001]))
    item = ls_hit.roll_enemy_drop("goblin")
    assert item is not None and item.rarity == "common"
    ls_miss = LootSystem(rng=_ScriptedRng([loot_mod.ENEMY_DROP_CHANCE + 0.001]))
    assert ls_miss.roll_enemy_drop("goblin") is None


def test_sim_engine_enemy_killed_routes_loot_to_killer():
    from game.sim_engine import SimEngine

    hero = Hero(0.0, 0.0, name="Killer")
    hero.weapon = None
    stub = SimpleNamespace(
        heroes=[hero],
        loot_system=LootSystem(rng=_ScriptedRng([0.01])),  # guaranteed common drop
        _emit_hud_message=lambda *a, **k: None,
    )
    event = {"type": "enemy_killed", "hero": "Killer", "enemy": "goblin",
             "gold": 10, "xp": 5}
    SimEngine._route_combat_events(stub, [event])
    # COMMON_DROP_POOL[0] = dagger -> auto-equipped (hero had no weapon).
    assert hero.weapon is not None and hero.weapon["name"] == "Dagger"


def test_sim_engine_no_loot_when_no_kill_event():
    from game.sim_engine import SimEngine

    hero = Hero(0.0, 0.0, name="Idle")
    ls = LootSystem()
    state_before = ls._rng.getstate()
    stub = SimpleNamespace(heroes=[hero], loot_system=ls,
                           _emit_hud_message=lambda *a, **k: None)
    SimEngine._route_combat_events(stub, [{"type": "hero_attack"}])
    SimEngine._route_combat_events(stub, [])
    assert ls._rng.getstate() == state_before
    assert hero.backpack == [] and hero.weapon is None


def _fake_poi(tier: int = 4):
    poi_def = SimpleNamespace(difficulty_tier=tier, display_name="Old Cache",
                              size=(1, 1), interaction_type="loot")
    return SimpleNamespace(poi_def=poi_def, grid_x=3, grid_y=3,
                           is_depleted=False, is_interacted=False,
                           interaction_count=0)


def test_poi_loot_handler_grants_gold_plus_item():
    system = POIInteractionSystem()
    system._loot_system = LootSystem(rng=_ScriptedRng([0.01]))  # guaranteed drop
    hero = Hero(0.0, 0.0, name="Looter")
    hero.gold = 0
    poi = _fake_poi(tier=4)
    events: list[dict] = []
    bus = SimpleNamespace(emit=lambda payload: events.append(payload))

    system._handle_loot(hero, poi, None, None, bus, (1, 2))

    assert hero.gold > 0  # legacy gold roll untouched
    assert poi.is_depleted is True
    # Tier 4 -> rare+ pool; pool[0] = wizard_staff, auto-equipped (no weapon).
    assert hero.weapon is not None and hero.weapon["name"] == "Wizard Staff"
    loot_events = [e for e in events if e.get("interaction_type") == "loot"]
    assert loot_events and loot_events[0]["item_name"] == "Wizard Staff"
    assert loot_events[0]["item_outcome"] == "equipped"


def test_poi_loot_handler_no_item_path_keeps_legacy_payload():
    system = POIInteractionSystem()
    system._loot_system = LootSystem(rng=_ScriptedRng([0.99]))  # guaranteed miss
    hero = Hero(0.0, 0.0, name="Unlucky")
    hero.gold = 0
    poi = _fake_poi(tier=1)
    events: list[dict] = []
    bus = SimpleNamespace(emit=lambda payload: events.append(payload))

    system._handle_loot(hero, poi, None, None, bus, (1, 2))

    assert hero.gold > 0
    assert hero.weapon is None and hero.backpack == []
    assert events[0]["item_name"] == "" and events[0]["item_outcome"] == ""


# ---------------------------------------------------------------------------
# 7. Shop sell flow (round trip incl. 25% tax)
# ---------------------------------------------------------------------------

def test_sell_backpack_items_pays_through_add_gold_with_tax():
    hero = Hero(0.0, 0.0, name="Seller")
    hero.gold = 0
    hero.taxed_gold = 0
    dagger = get_item("dagger")          # sell 30
    boots = get_item("swift_boots")      # sell 50
    hero.backpack = [dagger, boots]

    gross = hero.sell_backpack_items()

    assert gross == dagger.sell_price + boots.sell_price
    expected_tax = int(dagger.sell_price * TAX_RATE) + int(boots.sell_price * TAX_RATE)
    assert hero.taxed_gold == expected_tax
    assert hero.gold == gross - expected_tax
    assert hero.backpack == []


def test_buy_then_loot_then_sell_round_trip():
    hero = Hero(0.0, 0.0, name="RoundTrip")
    hero.gold = 100
    market = Marketplace(0, 0)
    iron = next(d for d in market.get_available_items() if d["name"] == "Iron Sword")
    assert hero.buy_item(iron, shop_building=market) is True
    assert hero.gold == 100 - 80
    # Loot a worse weapon -> carried, then sold.
    assert hero.receive_item(get_item("dagger")) == "stored"
    gross = hero.sell_backpack_items(market)
    assert gross == get_item("dagger").sell_price
    assert hero.backpack == []


def test_do_shopping_sells_backpack_before_buying():
    from ai.behaviors import shopping

    hero = Hero(0.0, 0.0, name="ShopSeller")
    hero.gold = 0
    hero.potions = 5  # skip potion priorities
    hero.weapon = {"name": "Runed Warhammer", "attack": 18}
    hero.armor = {"name": "Dragonscale Armor", "defense": 16}
    hero.backpack = [get_item("steel_sword")]  # sell 75 -> 57 spendable after tax

    class _Journey:
        def _maybe_start_journey(self, *_a, **_k):
            return False

    ai = SimpleNamespace(journey_behavior=_Journey())

    class _Sink:
        def propose(self, _cmd):
            return False

    view = SimpleNamespace(commands=_Sink(), world=None, buildings=[], enemies=[],
                           heroes=[hero], bounties=[], pois=[], player_gold=0, castle=None)
    building = SimpleNamespace(get_available_items=lambda: [])

    shopping.do_shopping(ai, hero, building, view)

    assert hero.backpack == []
    sell = get_item("steel_sword").sell_price
    assert hero.gold == sell - int(sell * TAX_RATE)


# ---------------------------------------------------------------------------
# 8. LLM snapshot carries items into _compact_profile_dict
# ---------------------------------------------------------------------------

def test_snapshot_and_compact_profile_dict_carry_accessory_and_backpack():
    from ai.profile_context_adapter import _compact_profile_dict
    from game.sim.hero_profile import build_hero_profile_snapshot

    hero = Hero(0.0, 0.0, name="Snapped")
    assert hero.equip(get_item("hawk_signet")) is True
    hero.backpack = [get_item("dagger"), get_item("swiftness_draught")]

    snap = build_hero_profile_snapshot(hero, None, now_ms=1000)
    assert snap.inventory.accessory_name == "Hawk Signet"
    assert snap.inventory.backpack == ("Dagger", "Swiftness Draught")

    compact = _compact_profile_dict(snap)
    inv = compact["inventory"]
    assert inv["accessory_name"] == "Hawk Signet"
    assert tuple(inv["backpack"]) == ("Dagger", "Swiftness Draught")


def test_snapshot_defaults_empty_for_fresh_hero():
    from game.sim.hero_profile import build_hero_profile_snapshot

    hero = Hero(0.0, 0.0, name="Fresh")
    snap = build_hero_profile_snapshot(hero, None, now_ms=1000)
    assert snap.inventory.accessory_name == ""
    assert snap.inventory.backpack == ()


# ---------------------------------------------------------------------------
# 9. Digest safety: no loot RNG outside kill/interaction events
# ---------------------------------------------------------------------------

def test_no_loot_rng_drawn_without_kill_or_interaction():
    """Constructing the systems, shops and heroes (everything the digest
    scenario does) must draw NOTHING from the 'loot' stream: the stream's
    first values must still match a virgin get_rng('loot') stream."""
    set_sim_seed(7)
    virgin = get_rng("loot")
    expected_first = [virgin.random() for _ in range(5)]

    set_sim_seed(7)
    ls = LootSystem()                       # sim_engine construction analog
    poi_sys = POIInteractionSystem()        # owns its own LootSystem
    market = Marketplace(0, 0)
    smith = Blacksmith(0, 0)
    hero = Hero(0.0, 0.0, name="DigestSafe")
    market.get_available_items()
    smith.get_available_items()
    hero.equip(get_item("iron_sword"))      # equip itself draws no RNG
    poi_sys.check_interactions([hero], [], None, None, None, 0.016)

    assert [ls._rng.random() for _ in range(5)] == expected_first
    # And the POI system's own loot stream is untouched too.
    set_sim_seed(7)
    fresh = get_rng("loot")
    poi_first = [poi_sys._loot_system._rng.random() for _ in range(5)]
    assert poi_first == [fresh.random() for _ in range(5)]


def test_default_hero_fields_do_not_change_digest_hashed_values():
    """New WK131 fields must leave the digest-hashed tuple inputs untouched:
    (x, y, state, intent, target-type, gold) plus attack/defense math."""
    hero = Hero(10.0, 20.0, name="DigestHero")
    assert hero.accessory is None
    assert hero.backpack == []
    assert hero.gold == 0
    # attack/defense identical to the pre-WK131 formula with no items.
    assert hero.attack == hero.base_attack + (hero.level - 1) * 2
    assert hero.defense == hero.base_defense + (hero.level - 1)
