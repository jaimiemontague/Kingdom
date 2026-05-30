"""
WK71 Round B-2a — structure-lock test for the hero.py mixin split.

Agent 03 split ``game/entities/hero.py`` (1156 -> ~543 LOC) into three
MRO-identical mixins:
    - HeroRestMixin    (game/entities/hero_rest.py)    — 8 resting methods
    - HeroEconomyMixin (game/entities/hero_economy.py) — 10 economy methods
    - HeroMemoryMixin  (game/entities/hero_memory.py)  — 9 memory/intent methods

``Hero`` is now ``class Hero(HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin)``.
This test locks the structure so a future refactor cannot silently reorder the
MRO, move a method to the wrong mixin, re-introduce the duplicate
``set_event_bus``, or break attribute resolution between mixins and
``Hero.__init__``.

This is Agent 11's WAVE W2 deliverable (the only file Agent 11 creates).
"""
from __future__ import annotations

import inspect
import types

from game.entities.hero import Hero, HeroState
from game.entities.hero_rest import HeroRestMixin
from game.entities.hero_economy import HeroEconomyMixin
from game.entities.hero_memory import HeroMemoryMixin


# ---------------------------------------------------------------------------
# The 27 moved methods, grouped by the mixin they MUST resolve from.
# (8 rest + 10 economy + 9 memory = 27, per the WK71 plan section 1.)
# ---------------------------------------------------------------------------
REST_METHODS = [
    "should_go_home_to_rest",
    "start_resting",
    "start_resting_at_building",
    "update_resting",
    "pop_out_of_building",
    "can_rest_at_home",
    "finish_resting",
    "enter_building_briefly",
]

ECONOMY_METHODS = [
    "add_gold",
    "increment_career_stat",
    "transfer_taxes_to_home",
    "use_potion",
    "_is_at_food_stand",
    "buy_meal_at_food_stand",
    "_shop_for_tax_deposit",
    "buy_item",
    "wants_to_shop",
    "get_shopping_context",
]

MEMORY_METHODS = [
    "record_profile_memory",
    "remember_known_place",
    "_trim_known_places_if_needed",
    "record_decision",
    "get_intent_snapshot",
    "get_stuck_snapshot",
    "_derive_intent",
    "_update_intent_and_decision",
    "get_context_for_llm",
]

MOVED_METHODS_BY_MIXIN = {
    HeroRestMixin: REST_METHODS,
    HeroEconomyMixin: ECONOMY_METHODS,
    HeroMemoryMixin: MEMORY_METHODS,
}


def _make_headless_hero() -> Hero:
    """Construct a Hero with no pygame/display dependency.

    Hero.__init__ touches no SDL/pygame surfaces (purely sets instance attrs),
    so a plain construction is headless-safe. We avoid importing pygame at all.
    """
    return Hero(0.0, 0.0, hero_class="warrior")


# ---------------------------------------------------------------------------
# A. MRO is exactly the mixin chain (DoD F).
# ---------------------------------------------------------------------------
def test_hero_mro_is_exact_mixin_chain():
    assert [c.__name__ for c in Hero.__mro__] == [
        "Hero",
        "HeroRestMixin",
        "HeroEconomyMixin",
        "HeroMemoryMixin",
        "object",
    ]


def test_hero_subclasses_all_three_mixins():
    for mixin in (HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin):
        assert issubclass(Hero, mixin), f"Hero must inherit {mixin.__name__}"


# ---------------------------------------------------------------------------
# B. Each of the 27 moved methods is present on Hero AND resolves from the
#    expected mixin (defined in that mixin's own __dict__, not Hero or another
#    mixin). This catches a method moved to the wrong module.
# ---------------------------------------------------------------------------
def test_all_27_moved_methods_present_and_resolve_from_expected_mixin():
    total = 0
    for mixin, names in MOVED_METHODS_BY_MIXIN.items():
        for name in names:
            total += 1
            # Present on Hero (resolvable via the MRO).
            assert hasattr(Hero, name), f"Hero is missing moved method {name!r}"
            # Defined in the expected mixin's own namespace.
            assert name in vars(mixin), (
                f"{name!r} should be defined in {mixin.__name__} "
                f"(vars({mixin.__name__})), but is not"
            )
            # And it must NOT also be defined on Hero itself (would shadow / mean
            # the move was incomplete) nor on a different mixin.
            assert name not in vars(Hero), (
                f"{name!r} is still defined on Hero itself; the move is incomplete"
            )
            for other in MOVED_METHODS_BY_MIXIN:
                if other is mixin:
                    continue
                assert name not in vars(other), (
                    f"{name!r} is duplicated into {other.__name__}; "
                    f"it must live only in {mixin.__name__}"
                )
            # Resolution on Hero comes from the expected mixin.
            owner = next(
                klass for klass in Hero.__mro__ if name in vars(klass)
            )
            assert owner is mixin, (
                f"Hero.{name} resolves from {owner.__name__}, expected {mixin.__name__}"
            )
    assert total == 27, f"expected 27 moved methods, checked {total}"


# ---------------------------------------------------------------------------
# C. Exactly ONE set_event_bus on Hero, callable, owned by Hero core (the
#    duplicate def was deleted in WK71). Also: _event_bus initialised once.
# ---------------------------------------------------------------------------
def test_single_set_event_bus_no_duplicate():
    # set_event_bus stays on Hero core (not a mixin).
    assert "set_event_bus" in vars(Hero), "set_event_bus must remain defined on Hero"
    # Not duplicated into any mixin.
    for mixin in (HeroRestMixin, HeroEconomyMixin, HeroMemoryMixin):
        assert "set_event_bus" not in vars(mixin), (
            f"set_event_bus must not be on {mixin.__name__}"
        )
    # Callable bound method on an instance.
    hero = _make_headless_hero()
    assert callable(hero.set_event_bus)
    assert isinstance(hero.set_event_bus, types.MethodType)
    # Functional: wires the bus, no duplicate-init weirdness.
    assert hero._event_bus is None
    sentinel = object()
    hero.set_event_bus(sentinel)
    assert hero._event_bus is sentinel

    # Source-level guard: the def appears exactly once across hero.py + mixins.
    import game.entities.hero as hero_mod
    import game.entities.hero_rest as rest_mod
    import game.entities.hero_economy as econ_mod
    import game.entities.hero_memory as mem_mod

    count = 0
    for mod in (hero_mod, rest_mod, econ_mod, mem_mod):
        src = inspect.getsource(mod)
        count += src.count("def set_event_bus")
    assert count == 1, f"expected exactly one 'def set_event_bus', found {count}"


# ---------------------------------------------------------------------------
# D. A headless Hero exposes the moved methods as callable BOUND methods, and
#    instance state set in Hero.__init__ is visible (proving the mixins, which
#    hold only methods, see Hero's instance attrs through self).
# ---------------------------------------------------------------------------
def test_moved_methods_are_bound_on_instance():
    hero = _make_headless_hero()
    for names in MOVED_METHODS_BY_MIXIN.values():
        for name in names:
            attr = getattr(hero, name)
            assert isinstance(attr, types.MethodType), (
                f"hero.{name} is not a bound method ({type(attr)!r})"
            )
            assert attr.__self__ is hero


def test_instance_state_from_init_is_visible_to_mixins():
    hero = _make_headless_hero()
    # A representative slice of state initialised in Hero.__init__ that the
    # mixins read through self.* — proves cross-mixin attribute resolution.
    assert hero.gold == 0
    assert hero.taxed_gold == 0
    assert hero.buffs == []
    assert hero.known_places == {}
    assert hero.profile_memory == []
    assert hero.profile_career["gold_earned"] == 0
    assert hero.state is HeroState.IDLE
    assert hero.home_building is None
    assert hero.potions == 0
    assert hero.max_potions == 5


def test_representative_moved_methods_execute_end_to_end():
    """Call a representative method from each mixin and assert real behaviour,
    proving the methods operate correctly on Hero's __init__ state."""
    # --- Rest mixin: should_go_home_to_rest reads hp/damage state ---
    hero = _make_headless_hero()
    assert hero.should_go_home_to_rest() is False  # fresh hero, no damage
    hero.damage_since_left_home = 50
    assert hero.should_go_home_to_rest() is True

    # --- Economy mixin: add_gold applies tax split; wants_to_shop; buy_item ---
    hero = _make_headless_hero()
    hero.add_gold(100)
    assert hero.gold > 0 and hero.taxed_gold > 0
    assert hero.gold + hero.taxed_gold == 100
    assert hero.profile_career["gold_earned"] == 100
    assert hero.wants_to_shop(marketplace_has_potions=True) is True
    before_gold = hero.gold
    ok = hero.buy_item({"name": "Potion", "type": "potion", "price": 20, "effect": 50})
    assert ok is True
    assert hero.potions == 1
    assert hero.gold == before_gold - 20

    # --- Memory mixin: record_decision + get_intent_snapshot round-trip ---
    hero = _make_headless_hero()
    hero.record_decision(action="shopping", reason="needs potions", now_ms=1234)
    snap = hero.get_intent_snapshot(now_ms=1234)
    assert isinstance(snap, dict)
    assert snap.get("last_decision", {}).get("action") == "shopping"
    stuck = hero.get_stuck_snapshot(now_ms=1234)
    assert stuck["stuck_active"] is False
    intent, reason, ctx = hero._derive_intent()
    assert isinstance(intent, str) and isinstance(reason, str) and isinstance(ctx, dict)


# ---------------------------------------------------------------------------
# E. Mixin modules are pure method-holders (no instance state leaked into the
#    class body besides methods) and the chain has no shared-name collisions.
# ---------------------------------------------------------------------------
def test_mixins_define_only_their_methods_no_collisions():
    seen: dict[str, str] = {}
    for mixin, names in MOVED_METHODS_BY_MIXIN.items():
        public = {
            n
            for n, v in vars(mixin).items()
            if callable(v) and not n.startswith("__")
        }
        # The mixin defines exactly its assigned method set.
        assert public == set(names), (
            f"{mixin.__name__} defines {sorted(public)}, expected {sorted(names)}"
        )
        # No name is defined by two different mixins.
        for n in public:
            assert n not in seen, (
                f"{n!r} defined in both {seen[n]} and {mixin.__name__}"
            )
            seen[n] = mixin.__name__
