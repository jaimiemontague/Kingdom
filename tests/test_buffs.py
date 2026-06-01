"""Generic buff-infrastructure tests.

The Royal Gardens aura — the only aura *producer* — was removed in WK114 Round B.
These tests pin the generic, reusable buff infrastructure that survives the purge:

  * ``game.systems.buffs.Buff`` (the dataclass + ``is_expired`` boundary semantics)
  * a hero's ``apply_or_refresh_buff`` (apply-once / refresh-not-stack contract)
  * ``BuffSystem.update`` pruning expired hero buffs via ``remove_expired_buffs``

so future aura sources have a covered foundation to build on.
"""
from __future__ import annotations

from game.events import EventBus
from game.systems.buffs import Buff, BuffSystem
from game.systems.protocol import SystemContext


def _make_context(*, heroes: list, buildings: list) -> SystemContext:
    return SystemContext(
        heroes=heroes,
        enemies=[],
        buildings=buildings,
        world=object(),
        economy=object(),
        event_bus=EventBus(),
    )


# ---------------------------------------------------------------------------
# Buff dataclass — expiry boundary semantics.
# ---------------------------------------------------------------------------

def test_buff_is_expired_at_and_after_expiry_timestamp() -> None:
    buff = Buff(name="test_aura", atk_delta=3, def_delta=2, expires_at_ms=1000)
    # Strictly before expiry -> alive.
    assert buff.is_expired(999) is False
    # At/after the expiry timestamp -> expired (>= boundary).
    assert buff.is_expired(1000) is True
    assert buff.is_expired(1001) is True


# ---------------------------------------------------------------------------
# apply_or_refresh_buff — apply once, then refresh in place (no stacking drift).
# ---------------------------------------------------------------------------

def test_apply_buff_adds_single_entry(make_hero) -> None:
    hero = make_hero(name="AuraTarget")
    hero.apply_or_refresh_buff(
        name="test_aura", atk_delta=3, def_delta=2, duration_s=1.25, now_ms=1000
    )

    assert len(hero.buffs) == 1
    assert hero.buffs[0]["name"] == "test_aura"
    assert hero.buffs[0]["atk_delta"] == 3
    assert hero.buffs[0]["def_delta"] == 2
    assert hero.buffs[0]["expires_at_ms"] == int(1000 + 1.25 * 1000.0)


def test_apply_buff_refreshes_instead_of_stacking(make_hero) -> None:
    hero = make_hero(name="Refresh")
    hero.apply_or_refresh_buff(
        name="test_aura", atk_delta=2, def_delta=1, duration_s=1.25, now_ms=1000
    )
    first_expiry = int(hero.buffs[0]["expires_at_ms"])

    # Re-apply the same-named buff at a later tick: refresh in place, not stack.
    hero.apply_or_refresh_buff(
        name="test_aura", atk_delta=2, def_delta=1, duration_s=1.25, now_ms=1400
    )
    second_expiry = int(hero.buffs[0]["expires_at_ms"])

    assert len(hero.buffs) == 1
    assert second_expiry > first_expiry


# ---------------------------------------------------------------------------
# BuffSystem.update — prunes expired hero buffs (the surviving system behavior).
# ---------------------------------------------------------------------------

def test_buff_system_prunes_expired_buffs(make_hero, monkeypatch) -> None:
    now = {"value": 1000}
    monkeypatch.setattr("game.systems.buffs.sim_now_ms", lambda: now["value"])
    system = BuffSystem()
    hero = make_hero(name="Expires")
    hero.apply_or_refresh_buff(
        name="test_aura", atk_delta=1, def_delta=1, duration_s=1.25, now_ms=1000
    )
    assert len(hero.buffs) == 1

    # Before expiry: update keeps the buff.
    now["value"] = 2000
    system.update(_make_context(heroes=[hero], buildings=[]), dt=0.016)
    assert len(hero.buffs) == 1

    # Past expiry (1000 + 1.25s = 2250): update prunes it.
    now["value"] = 2600
    system.update(_make_context(heroes=[hero], buildings=[]), dt=0.016)
    assert hero.buffs == []


def test_buff_system_skips_dead_heroes(make_hero, monkeypatch) -> None:
    """A dead hero is not pruned (the system skips non-alive heroes)."""
    now = {"value": 1000}
    monkeypatch.setattr("game.systems.buffs.sim_now_ms", lambda: now["value"])
    system = BuffSystem()
    hero = make_hero(name="Downed", hp=0)  # hp=0 -> is_alive is False
    hero.apply_or_refresh_buff(
        name="test_aura", atk_delta=1, def_delta=1, duration_s=1.25, now_ms=1000
    )
    assert hero.is_alive is False

    now["value"] = 9999  # well past expiry
    system.update(_make_context(heroes=[hero], buildings=[]), dt=0.016)

    # Dead heroes are skipped, so the (now-expired) buff is left untouched.
    assert len(hero.buffs) == 1
