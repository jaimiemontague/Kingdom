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
enemy types TODAY yields the EXACT same attribute surface and values as the
PRE-WK73 (git HEAD = WK72 commit 065efa6) subclasses did. The gold standard is
the old source itself: we exec ``git show HEAD:game/entities/enemy.py`` in an
isolated namespace, construct the OLD class, and compare ``__dict__`` minus the
volatile keys (``entity_id`` — a monotonic per-instance id; ``x``/``y`` — the
constructor args). A redundant set of embedded expected literals (captured
verbatim from the HEAD subclass ``__init__`` bodies) documents the values and is
itself cross-checked against HEAD so it cannot silently drift.

Attribute-surface invariants this test enforces (from Agent 05's parity notes):
  * ``wolf`` / ``skeleton`` / ``skeleton_archer`` must NOT have an ``attackers``
    attribute.
  * non-boss types must NOT have ``name`` / ``is_boss`` attributes.

This is the only file Agent 11 creates for WK73. No production code is touched.
"""
from __future__ import annotations

import enum
import subprocess
import types

import pytest

from game.entities.enemy import (
    Enemy,
    ENEMY_STATS,
    Goblin,
    Wolf,
    Skeleton,
    Spider,
    Bandit,
    BanditLord,
    DemonOverlord,
    SkeletonArcher,
)

# Volatile keys excluded from every __dict__ comparison:
#   entity_id  — monotonic per-instance id (differs between the old module's
#                counter and the live one); proves nothing about stats.
#   x, y       — the constructor arguments (we always pass 0.0, 0.0 anyway).
# There are NO per-instance random fields on Enemy (ids are monotonic, no RNG),
# so this is the complete volatile set.
_VOLATILE_KEYS = ("entity_id", "x", "y")

# The 7 stat-block shims, paired with their ENEMY_STATS key. SkeletonArcher is
# deliberately excluded — it is behavioral and not in the table.
SHIMS = [
    (Goblin, "goblin"),
    (Wolf, "wolf"),
    (Skeleton, "skeleton"),
    (Spider, "spider"),
    (Bandit, "bandit"),
    (BanditLord, "bandit_lord"),
    (DemonOverlord, "demon_overlord"),
]

# All 8 enemy types: shims + the behavioral SkeletonArcher.
ALL_TYPES = [(cls, key) for cls, key in SHIMS] + [(SkeletonArcher, "skeleton_archer")]


# ---------------------------------------------------------------------------
# Embedded PRE-WK73 expected attributes, captured VERBATIM from the git-HEAD
# (WK72) subclass __init__ bodies. These are the stat values; the full per-type
# attribute surface (which of name/is_boss/attackers/ranged-fields each type
# carries) is asserted separately. ``test_embedded_literals_match_git_head``
# cross-checks every value here against the live HEAD source so this table
# cannot drift from the real history.
#
# Note: every type also inherits the base-init values it did NOT override
# (e.g. attack_range=38.4, attack_cooldown_max=1500, layer=0, size=18 for the
# non-boss types). Those base values are validated by the full-__dict__ parity
# test below (current vs HEAD); here we document the per-type OVERRIDES.
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
    # SkeletonArcher: behavioral subclass (not in ENEMY_STATS). Stats + ranged
    # fields captured verbatim from its HEAD __init__. No `attackers`.
    "skeleton_archer": dict(
        hp=40, max_hp=40, attack_power=4, speed=81.0,
        xp_reward=35, gold_reward=21, color=(200, 200, 220), size=18,
        has_attackers=False, is_boss=False,
        attack_range=192.0, min_range=64.0, attack_cooldown_max=1400,
        is_ranged_attacker=True,
    ),
}


def _normalize(value):
    """Make a value comparable across the live module and the exec'd HEAD module.

    The only non-trivial case is the ``state`` attribute: it holds an
    ``EnemyState`` enum member. Exec-ing the HEAD source defines a SEPARATE
    ``EnemyState`` class, so ``HEAD.EnemyState.IDLE != live.EnemyState.IDLE`` by
    enum identity even though they are the same logical value. Compare enum
    members by ``(qualname, name)`` so the duplicate-class artifact does not
    masquerade as a stat divergence. Everything else passes through unchanged.
    """
    if isinstance(value, enum.Enum):
        return (type(value).__qualname__, value.name)
    return value


def _stripped_dict(obj) -> dict:
    """The instance ``__dict__`` minus volatile (per-instance) keys, with enum
    values normalized so cross-module enum identity is not mistaken for drift."""
    d = dict(obj.__dict__)
    for k in _VOLATILE_KEYS:
        d.pop(k, None)
    return {k: _normalize(v) for k, v in d.items()}


# ---------------------------------------------------------------------------
# HEAD source: exec the PRE-WK73 enemy.py from git HEAD (WK72) in an isolated
# module namespace so we can construct the OLD subclasses and use their objects
# as the parity gold standard. Cached at import for all tests.
# ---------------------------------------------------------------------------
def _load_head_enemy_module() -> types.ModuleType:
    proc = subprocess.run(
        ["git", "show", "HEAD:game/entities/enemy.py"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git show HEAD:game/entities/enemy.py failed: {proc.stderr!r}"
        )
    src = proc.stdout
    mod = types.ModuleType("wk73_old_enemy_head")
    mod.__file__ = "HEAD:game/entities/enemy.py"
    exec(compile(src, "HEAD:game/entities/enemy.py", "exec"), mod.__dict__)
    return mod


_HEAD = _load_head_enemy_module()


def _old_class(name: str):
    cls = getattr(_HEAD, name, None)
    assert cls is not None, f"HEAD enemy.py is missing class {name!r}"
    return cls


CLASS_NAMES = {
    "goblin": "Goblin",
    "wolf": "Wolf",
    "skeleton": "Skeleton",
    "spider": "Spider",
    "bandit": "Bandit",
    "bandit_lord": "BanditLord",
    "demon_overlord": "DemonOverlord",
    "skeleton_archer": "SkeletonArcher",
}


# ===========================================================================
# 1. FULL __dict__ PARITY vs git HEAD (the byte-identical proof).
#    For every one of the 8 types, the live instance's stripped __dict__ must
#    equal the PRE-WK73 instance's stripped __dict__ — exactly. This catches a
#    missed attribute, a wrong value, an extra attribute, OR a wrong attribute
#    surface (e.g. an `attackers`/`name`/`is_boss` that shouldn't be there).
# ===========================================================================
@pytest.mark.parametrize(
    "cls,key",
    ALL_TYPES,
    ids=[k for _, k in ALL_TYPES],
)
def test_dict_parity_vs_git_head(cls, key):
    new_obj = cls(0.0, 0.0)
    old_obj = _old_class(CLASS_NAMES[key])(0.0, 0.0)

    new_d = _stripped_dict(new_obj)
    old_d = _stripped_dict(old_obj)

    # Pinpoint diffs for a readable failure (which sends Agent 05 back).
    only_new = {k: new_d[k] for k in new_d.keys() - old_d.keys()}
    only_old = {k: old_d[k] for k in old_d.keys() - new_d.keys()}
    changed = {
        k: (old_d[k], new_d[k])
        for k in new_d.keys() & old_d.keys()
        if new_d[k] != old_d[k]
    }
    assert new_d == old_d, (
        f"{cls.__name__} ({key!r}) DIVERGES from pre-WK73 (git HEAD):\n"
        f"  attrs only on new build: {only_new}\n"
        f"  attrs only on old build: {only_old}\n"
        f"  changed (old -> new):    {changed}"
    )


# ===========================================================================
# 2. EMBEDDED-LITERAL stat parity (self-documenting per-type coverage).
#    Each stat the test documents must equal the live build. Cross-checked
#    against HEAD by test #3 so the literals can't drift.
# ===========================================================================
@pytest.mark.parametrize(
    "key",
    list(EXPECTED_STATS.keys()),
    ids=list(EXPECTED_STATS.keys()),
)
def test_embedded_stats_match_live_build(key):
    cls = getattr(__import__("game.entities.enemy", fromlist=[CLASS_NAMES[key]]),
                  CLASS_NAMES[key])
    obj = cls(0.0, 0.0)
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


def test_embedded_literals_match_git_head():
    """The embedded EXPECTED_STATS literals must equal the PRE-WK73 (git HEAD)
    instance values exactly — guards the literals against silent drift."""
    mismatches: list[str] = []
    for key, exp in EXPECTED_STATS.items():
        old = _old_class(CLASS_NAMES[key])(0.0, 0.0)
        for attr in ("hp", "max_hp", "attack_power", "speed",
                     "xp_reward", "gold_reward", "color", "size"):
            if getattr(old, attr) != exp[attr]:
                mismatches.append(
                    f"{key}.{attr}: literal={exp[attr]!r} HEAD={getattr(old, attr)!r}"
                )
        if exp["is_boss"]:
            if getattr(old, "name", None) != exp["name"]:
                mismatches.append(
                    f"{key}.name: literal={exp['name']!r} HEAD={getattr(old, 'name', None)!r}"
                )
        if "attack_range" in exp:
            for attr in ("attack_range", "min_range", "attack_cooldown_max"):
                if getattr(old, attr) != exp[attr]:
                    mismatches.append(
                        f"{key}.{attr}: literal={exp[attr]!r} HEAD={getattr(old, attr)!r}"
                    )
    assert not mismatches, "Embedded literals drifted from git HEAD:\n" + "\n".join(mismatches)


# ===========================================================================
# 3. ATTRIBUTE-SURFACE invariants (Agent 05's notes, stated explicitly).
# ===========================================================================
def test_attackerless_types_have_no_attackers_attr():
    for key in ("wolf", "skeleton", "skeleton_archer"):
        obj = getattr(
            __import__("game.entities.enemy", fromlist=[CLASS_NAMES[key]]),
            CLASS_NAMES[key],
        )(0.0, 0.0)
        assert not hasattr(obj, "attackers"), (
            f"{key} must NOT have an `attackers` attribute (it never did pre-WK73)"
        )


def test_nonboss_types_have_no_name_or_is_boss():
    nonboss = ("goblin", "wolf", "skeleton", "spider", "bandit", "skeleton_archer")
    for key in nonboss:
        obj = getattr(
            __import__("game.entities.enemy", fromlist=[CLASS_NAMES[key]]),
            CLASS_NAMES[key],
        )(0.0, 0.0)
        assert not hasattr(obj, "name"), f"{key} must NOT have a `name` attribute"
        assert not hasattr(obj, "is_boss"), f"{key} must NOT have an `is_boss` attribute"


def test_boss_types_have_name_and_is_boss():
    for key, name in (("bandit_lord", "The Bandit Lord"),
                      ("demon_overlord", "The Demon Overlord")):
        obj = getattr(
            __import__("game.entities.enemy", fromlist=[CLASS_NAMES[key]]),
            CLASS_NAMES[key],
        )(0.0, 0.0)
        assert getattr(obj, "is_boss", None) is True
        assert getattr(obj, "name", None) == name


# ===========================================================================
# 4. SHIM STRUCTURE: the 7 stat subclasses are Enemy subclasses, and
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
    """ENEMY_STATS must have exactly an entry for each of the 7 shim keys, and
    skeleton_archer must NOT be in the table (it is behavioral)."""
    shim_keys = {key for _, key in SHIMS}
    assert shim_keys <= set(ENEMY_STATS.keys()), (
        f"ENEMY_STATS missing keys: {shim_keys - set(ENEMY_STATS.keys())}"
    )
    assert "skeleton_archer" not in ENEMY_STATS, (
        "skeleton_archer is behavioral and must NOT be folded into ENEMY_STATS"
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
