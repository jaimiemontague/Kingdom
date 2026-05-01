"""WK49: stable ``hero_id`` on ``Hero`` (duplicate-safe identity)."""

from __future__ import annotations

from game.entities.hero import Hero


def test_hero_id_non_empty_default() -> None:
    h = Hero(0.0, 0.0, hero_class="warrior")
    assert isinstance(h.hero_id, str)
    assert len(h.hero_id) > 0


def test_duplicate_names_remain_distinct_hero_ids() -> None:
    a = Hero(0.0, 0.0, hero_class="warrior", hero_id="wk49_a", name="Aria")
    b = Hero(1.0, 1.0, hero_class="ranger", hero_id="wk49_b", name="Aria")
    assert a.name == b.name == "Aria"
    assert a.hero_id != b.hero_id


def test_explicit_whitespace_only_hero_id_falls_back_to_allocator(monkeypatch) -> None:
    monkeypatch.setattr("game.entities.hero._fallback_hero_seq", 0)
    h = Hero(0.0, 0.0, hero_class="warrior", hero_id="   ")
    assert h.hero_id.startswith("h")
    assert len(h.hero_id) >= 8
