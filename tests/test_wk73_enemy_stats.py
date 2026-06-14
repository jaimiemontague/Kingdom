"""
WK73 Round B-2b — stat-parity lock for the enemy.py ENEMY_STATS table.

WK73 collapsed the 7 near-identical enemy *stat-block* subclasses
(Goblin, Wolf, Skeleton, Spider, Bandit, BanditLord, DemonOverlord) into a
single ``ENEMY_STATS`` table applied by ``Enemy.__init__``. Each of the 7 is
now a 1-line shim (``super().__init__(x, y, "<key>")``). ``SkeletonArcher`` is
NOT in the table — it is the one real behavioral subclass (kiting ``update``)
and keeps its own ``__init__`` verbatim. ``register_attacker`` was lifted to the
``Enemy`` base, gated on an ``attackers`` set existing.

This is Agent 11's WAVE W2 deliverable: prove that constructing each of the 8
enemy types TODAY yields the EXACT per-type attribute surface and stat values
that the PRE-WK73 (WK72, commit 065efa6) subclasses produced.

WK74 hotfix (round wk74_hotfix_wk73test): this test is now SELF-CONTAINED. The
original version exec'd ``git show HEAD:game/entities/enemy.py`` at import to
build the "old" subclasses as the parity gold standard. That only worked while
HEAD was still the pre-WK73 source. Once WK73 was committed, ``git show HEAD``
returns the POST-refactor source whose ``@dataclass class EnemyStats`` crashes
the dataclass machinery when exec'd into a synthetic module that is not
registered in ``sys.modules`` (Python 3.13: ``cls.__module__`` is ``None`` →
``AttributeError: 'NoneType' object has no attribute '__dict__'``), so the whole
file failed to collect and turned the suite red.

The gold standard is now the EMBEDDED literal expected values below — captured
verbatim from the pre-WK73 subclass ``__init__`` bodies. No live ``git show``
exec happens at any point, so the test is stable across future history.

Attribute-surface invariants this test enforces (from Agent 05's parity notes):
  * ``wolf`` / ``skeleton`` / ``skeleton_archer`` must NOT have an ``attackers``
    attribute.
  * non-boss types must NOT have ``name`` / ``is_boss`` attributes.

This is the only file Agent 11 creates for WK73. No production code is touched.
"""
from __future__ import annotations

import pytest

from game.entities.enemy import (
    Enemy,
    ENEMY_STATS,
    Goblin,
    GoblinWarchief,
    Wolf,
    Skeleton,
    Spider,
    Bandit,
    BanditLord,
    DemonOverlord,
    Dragon,
    SkeletonArcher,
)

# Volatile keys excluded from every __dict__ comparison:
#   entity_id  — monotonic per-instance id; proves nothing about stats.
#   x, y       — the constructor arguments (we always pass 0.0, 0.0 anyway).
# There are NO per-instance random fields on Enemy (ids are monotonic, no RNG),
# so this is the complete volatile set.
_VOLATILE_KEYS = ("entity_id", "x", "y")

# The stat-block shims, paired with their ENEMY_STATS key. SkeletonArcher is
# deliberately excluded — it is behavioral and not in the table.
# WK132: Dragon (Dragon Cave boss) added as the 8th pure stat-block shim.
# WK137: GoblinWarchief (initial-wave boss) added as the 9th pure stat-block shim.
SHIMS = [
    (Goblin, "goblin"),
    (GoblinWarchief, "goblin_warchief"),
    (Wolf, "wolf"),
    (Skeleton, "skeleton"),
    (Spider, "spider"),
    (Bandit, "bandit"),
    (BanditLord, "bandit_lord"),
    (DemonOverlord, "demon_overlord"),
    (Dragon, "dragon"),
]

# All enemy types: shims + the behavioral SkeletonArcher.
ALL_TYPES = [(cls, key) for cls, key in SHIMS] + [(SkeletonArcher, "skeleton_archer")]

CLASS_NAMES = {
    "goblin": "Goblin",
    "goblin_warchief": "GoblinWarchief",
    "wolf": "Wolf",
    "skeleton": "Skeleton",
    "spider": "Spider",
    "bandit": "Bandit",
    "bandit_lord": "BanditLord",
    "demon_overlord": "DemonOverlord",
    "dragon": "Dragon",
    "skeleton_archer": "SkeletonArcher",
}


# ---------------------------------------------------------------------------
# Embedded PRE-WK73 expected attributes, captured VERBATIM from the WK72
# (commit 065efa6) subclass __init__ bodies. These literals ARE the gold
# standard: constructing each type today must reproduce exactly these stats and
# this attribute surface. (There is no live git-exec cross-check anymore — see
# the module docstring for why; the literals stand on their own.)
#
# Note: every type also inherits the base-init values it did NOT override
# (e.g. attack_range=38.4, attack_cooldown_max=1500, layer=0, size=18 for the
# non-boss types). The per-type OVERRIDES are documented here; the within-build
# shim==base test below proves the shims add nothing beyond selecting the key.
# ---------------------------------------------------------------------------
EXPECTED_STATS = {
    "goblin": dict(
        hp=30, max_hp=30, attack_power=10, speed=90.0,
        xp_reward=25, gold_reward=15, color=(139, 69, 19), size=18,
        has_attackers=True, is_boss=False,
    ),
    "wolf": dict(
        hp=22, max_hp=22, attack_power=4, speed=138.0,
        xp_reward=20, gold_reward=9, color=(160, 160, 160), size=18,
        has_attackers=False, is_boss=False,
    ),
    "skeleton": dict(
        hp=55, max_hp=55, attack_power=7, speed=66.0,
        xp_reward=35, gold_reward=21, color=(220, 220, 240), size=18,
        has_attackers=False, is_boss=False,
    ),
    "spider": dict(
        hp=18, max_hp=18, attack_power=4, speed=156.0,
        xp_reward=18, gold_reward=8, color=(30, 30, 30), size=18,
        has_attackers=True, is_boss=False,
    ),
    "bandit": dict(
        hp=42, max_hp=42, attack_power=9, speed=102.0,
        xp_reward=32, gold_reward=18, color=(120, 80, 50), size=18,
        has_attackers=True, is_boss=False,
    ),
    # WK137: Goblin Warchief — initial-wave boss; 2x goblin HP / 1.5x goblin attack.
    "goblin_warchief": dict(
        hp=60, max_hp=60, attack_power=15, speed=90.0,
        xp_reward=50, gold_reward=40, color=(96, 48, 12), size=24,
        has_attackers=True, is_boss=True, name="The Goblin Warchief",
    ),
    "bandit_lord": dict(
        hp=300, max_hp=300, attack_power=20, speed=90.0,
        xp_reward=150, gold_reward=200, color=(180, 100, 30), size=28,
        has_attackers=True, is_boss=True, name="The Bandit Lord",
    ),
    "demon_overlord": dict(
        hp=500, max_hp=500, attack_power=30, speed=72.0,
        xp_reward=300, gold_reward=500, color=(200, 30, 30), size=32,
        has_attackers=True, is_boss=True, name="The Demon Overlord",
    ),
    # WK132: Dragon Cave boss — NEW type (not a pre-WK73 literal); values are
    # the WK132 design of record (~1.3x DemonOverlord, speed kept at 72).
    "dragon": dict(
        hp=650, max_hp=650, attack_power=39, speed=72.0,
        xp_reward=390, gold_reward=650, color=(220, 60, 20), size=36,
        has_attackers=True, is_boss=True, name="The Dragon",
    ),
    # SkeletonArcher: behavioral subclass (not in ENEMY_STATS). Stats + ranged
    # fields captured verbatim from its __init__. No `attackers`.
    "skeleton_archer": dict(
        hp=40, max_hp=40, attack_power=4, speed=81.0,
        xp_reward=35, gold_reward=21, color=(200, 200, 220), size=18,
        has_attackers=False, is_boss=False,
        attack_range=192.0, min_range=64.0, attack_cooldown_max=1400,
        is_ranged_attacker=True,
    ),
}


def _stripped_dict(obj) -> dict:
    """The instance ``__dict__`` minus volatile (per-instance) keys."""
    d = dict(obj.__dict__)
    for k in _VOLATILE_KEYS:
        d.pop(k, None)
    return d


def _make(key):
    """Construct an enemy of the given ENEMY_STATS/CLASS_NAMES key."""
    cls = getattr(
        __import__("game.entities.enemy", fromlist=[CLASS_NAMES[key]]),
        CLASS_NAMES[key],
    )
    return cls(0.0, 0.0)


# ===========================================================================
# 1. EMBEDDED-LITERAL stat parity (the gold standard, self-documenting).
#    Constructing each of the 8 types TODAY must reproduce the exact pre-WK73
#    stat values AND attribute surface recorded in EXPECTED_STATS. This catches
#    a missed attribute, a wrong value, OR a wrong surface (an
#    `attackers`/`name`/`is_boss` that shouldn't be there, or a missing one).
# ===========================================================================
@pytest.mark.parametrize(
    "key",
    list(EXPECTED_STATS.keys()),
    ids=list(EXPECTED_STATS.keys()),
)
def test_embedded_stats_match_live_build(key):
    obj = _make(key)
    exp = EXPECTED_STATS[key]

    # Core numeric/visual stats every type carries.
    for attr in ("hp", "max_hp", "attack_power", "speed",
                 "xp_reward", "gold_reward", "color", "size"):
        assert getattr(obj, attr) == exp[attr], (
            f"{key}.{attr}: expected {exp[attr]!r}, got {getattr(obj, attr)!r}"
        )

    # Boss-only fields.
    if exp["is_boss"]:
        assert getattr(obj, "is_boss", None) is True, f"{key} should be a boss"
        assert getattr(obj, "name", None) == exp["name"], (
            f"{key}.name: expected {exp['name']!r}"
        )
    else:
        assert not hasattr(obj, "is_boss"), (
            f"{key} is not a boss; must NOT have is_boss attribute"
        )
        assert not hasattr(obj, "name"), (
            f"{key} is not a boss; must NOT have name attribute"
        )

    # Attacker set surface.
    if exp["has_attackers"]:
        assert hasattr(obj, "attackers"), f"{key} should have an attackers set"
        assert obj.attackers == set(), f"{key}.attackers should start empty"
    else:
        assert not hasattr(obj, "attackers"), (
            f"{key} must NOT have an attackers attribute"
        )

    # Ranged fields (skeleton_archer only).
    if "attack_range" in exp:
        assert obj.attack_range == exp["attack_range"], f"{key}.attack_range"
        assert obj.min_range == exp["min_range"], f"{key}.min_range"
        assert obj.attack_cooldown_max == exp["attack_cooldown_max"], (
            f"{key}.attack_cooldown_max"
        )
        assert getattr(obj, "is_ranged_attacker", False) is True, (
            f"{key}.is_ranged_attacker"
        )


# ===========================================================================
# 2. ATTRIBUTE-SURFACE invariants (Agent 05's notes, stated explicitly).
# ===========================================================================
def test_attackerless_types_have_no_attackers_attr():
    for key in ("wolf", "skeleton", "skeleton_archer"):
        obj = _make(key)
        assert not hasattr(obj, "attackers"), (
            f"{key} must NOT have an `attackers` attribute (it never did pre-WK73)"
        )


def test_nonboss_types_have_no_name_or_is_boss():
    nonboss = ("goblin", "wolf", "skeleton", "spider", "bandit", "skeleton_archer")
    for key in nonboss:
        obj = _make(key)
        assert not hasattr(obj, "name"), f"{key} must NOT have a `name` attribute"
        assert not hasattr(obj, "is_boss"), f"{key} must NOT have an `is_boss` attribute"


def test_boss_types_have_name_and_is_boss():
    for key, name in (("bandit_lord", "The Bandit Lord"),
                      ("demon_overlord", "The Demon Overlord")):
        obj = _make(key)
        assert getattr(obj, "is_boss", None) is True
        assert getattr(obj, "name", None) == name


# ===========================================================================
# 3. SHIM STRUCTURE: the 7 stat subclasses are Enemy subclasses, and
#    constructing via the shim == constructing Enemy(x, y, key) for stats.
# ===========================================================================
@pytest.mark.parametrize("cls,key", SHIMS, ids=[k for _, k in SHIMS])
def test_shim_is_enemy_subclass(cls, key):
    assert issubclass(cls, Enemy), f"{cls.__name__} must subclass Enemy"
    assert cls is not Enemy


@pytest.mark.parametrize("cls,key", SHIMS, ids=[k for _, k in SHIMS])
def test_shim_equals_base_enemy_with_key(cls, key):
    """Goblin(x, y) must produce the same attributes as Enemy(x, y, "goblin"),
    etc. — proving the shim adds nothing beyond selecting the ENEMY_STATS key.
    The only legitimate difference is the volatile entity_id (stripped)."""
    via_shim = cls(0.0, 0.0)
    via_base = Enemy(0.0, 0.0, key)
    assert _stripped_dict(via_shim) == _stripped_dict(via_base), (
        f"{cls.__name__}(0,0) != Enemy(0,0,{key!r}); the shim is not a pure "
        f"ENEMY_STATS selector"
    )


def test_enemy_stats_table_covers_the_seven_shims():
    """ENEMY_STATS must have exactly an entry for each shim key (7 originals +
    WK132 dragon), and skeleton_archer must NOT be in the table (behavioral)."""
    shim_keys = {key for _, key in SHIMS}
    assert shim_keys <= set(ENEMY_STATS.keys()), (
        f"ENEMY_STATS missing keys: {shim_keys - set(ENEMY_STATS.keys())}"
    )
    assert "skeleton_archer" not in ENEMY_STATS, (
        "skeleton_archer is behavioral and must NOT be folded into ENEMY_STATS"
    )
    # The table holds exactly the shim keys — no strays.
    assert set(ENEMY_STATS.keys()) == shim_keys, (
        f"ENEMY_STATS has unexpected keys: {set(ENEMY_STATS.keys()) - shim_keys}"
    )


def test_register_attacker_lifted_to_base_and_gated():
    """register_attacker is on the Enemy base, gated on an `attackers` set:
      * a type WITH attackers records the hero name;
      * a type WITHOUT attackers is a safe no-op (no AttributeError, no attr
        materialised) — byte-identical to pre-WK73 behavior."""
    assert "register_attacker" in vars(Enemy), (
        "register_attacker must be defined on the Enemy base (WK73 lift)"
    )

    class _Hero:
        name = "Aria"

    # With-attackers type records the hit.
    g = Goblin(0.0, 0.0)
    g.register_attacker(_Hero())
    assert g.attackers == {"Aria"}

    # Without-attackers type: no-op, and no `attackers` attr is created.
    w = Wolf(0.0, 0.0)
    w.register_attacker(_Hero())  # must not raise
    assert not hasattr(w, "attackers"), (
        "register_attacker must NOT materialise an attackers set on a type "
        "that never had one (wolf)"
    )
