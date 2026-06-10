"""WK131 items UI (Agent 08): hero panel Gear section (Weapon/Armor/Accessory + Bag)
and the watch-card compact gear line.

Headless pygame harness (SDL dummy video driver, same pattern as
tests/test_wk96_hud_watch_card.py). The hero-panel assertions spy on
``TextLabel.render`` to capture exactly which text lines the panel drew, then
check content + pixel-width fit inside the narrow (246px) hero column.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

# Headless: never bring up a real display when ui / pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from game.content.items import get_item
from game.ui import widgets
from game.ui.hero_panel import (
    HeroPanel,
    fit_panel_line,
    format_accessory_mods,
    format_gear_line,
    wrap_bag_names,
)
from game.ui.theme import UITheme

PANEL_W = 246  # the left hero-card column width the WK131 brief pins
PAD = 10  # UITheme.margin


# ------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def pygame_headless():
    pygame.init()
    pygame.display.set_mode((320, 240))
    yield
    # leave pygame initialized for other test modules in the same session


@pytest.fixture
def panel(pygame_headless) -> HeroPanel:
    return HeroPanel(
        UITheme(),
        frame_inner=(70, 70, 90),
        frame_highlight=(110, 110, 140),
    )


def _hero(**overrides) -> SimpleNamespace:
    """Duck-typed hero with every attribute _render_standard_hero reads."""
    base = dict(
        name="Aldous",
        hero_id="h1",
        hero_class="warrior",
        level=3,
        personality="bold",
        xp=40,
        xp_to_level=100,
        hp=55,
        max_hp=80,
        attack=12,
        defense=8,
        gold=120,
        taxed_gold=15,
        potions=2,
        max_potions=3,
        weapon=None,
        armor=None,
        accessory=None,
        backpack=[],
        backpack_capacity=5,
        state=SimpleNamespace(name="IDLE"),
        target=None,
        last_llm_action=None,
        last_llm_decision_time=0,
        is_inside_building=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _full_gear_hero() -> SimpleNamespace:
    return _hero(
        weapon={"name": "Iron Sword", "attack": 5, "id": "iron_sword"},
        armor={"name": "Chain Mail", "defense": 7, "id": "chain_mail"},
        accessory={
            "name": "Hawk Signet", "attack": 2, "defense": 2,
            "speed": 0.0, "max_hp": 0, "id": "hawk_signet",
        },
        backpack=[get_item("healing_potion"), get_item("swiftness_draught")],
    )


def _render_and_capture(panel: HeroPanel, hero, monkeypatch, *, hero_profile=None):
    """Render the hero card and capture every (font, text) TextLabel drew."""
    captured: list[tuple[pygame.font.Font, str]] = []
    original = widgets.TextLabel.render.__func__

    def spy(cls, surface, font, text, pos, color, **kwargs):
        captured.append((font, str(text)))
        return original(cls, surface, font, text, pos, color, **kwargs)

    monkeypatch.setattr(widgets.TextLabel, "render", classmethod(spy))

    surface = pygame.Surface((1280, 720), pygame.SRCALPHA)
    rect = pygame.Rect(8, 56, PANEL_W, 600)
    panel.render(surface, hero, rect, right_close_rect=None, hero_profile=hero_profile)
    return captured, rect


def _texts(captured) -> list[str]:
    return [t for _f, t in captured]


# ------------------------------------------------------------------
# (1) Pure helpers
# ------------------------------------------------------------------

def test_format_gear_line():
    assert format_gear_line("W", "Iron Sword", 5) == "W: Iron Sword (+5)"
    assert format_gear_line("A", "Chain Mail", 7) == "A: Chain Mail (+7)"
    assert format_gear_line("W", "Fists", 0) == "W: Fists"
    assert format_gear_line("A", "", 0) == "A: None"


def test_format_accessory_mods():
    assert format_accessory_mods({"attack": 2, "defense": 2}) == "+2 atk, +2 def"
    assert format_accessory_mods({"speed": 0.35}) == "+0.35 spd"
    assert format_accessory_mods({"max_hp": 25}) == "+25 hp"
    assert format_accessory_mods({}) == ""
    assert format_accessory_mods(None) == ""


def test_wrap_bag_names():
    assert wrap_bag_names([]) == []
    assert wrap_bag_names(["Healing Potion"]) == ["Healing Potion"]
    lines = wrap_bag_names(
        ["Greater Healing Potion", "Swiftness Draught", "Runed Warhammer",
         "Dragonscale Armor", "Healing Potion"]
    )
    assert 1 < len(lines) <= 3
    for line in lines:
        assert len(line) <= 38
    # every name shows up somewhere (last line may be ellipsized)
    joined = " ".join(lines)
    assert "Greater Healing Potion" in joined
    assert "Swiftness Draught" in joined


def test_fit_panel_line_pixel_truncates(pygame_headless):
    font = pygame.font.Font(None, 16)
    wide = "W" * 80
    fitted = fit_panel_line(font, wide, 200)
    assert fitted.endswith("…")
    assert font.size(fitted)[0] <= 200
    assert fit_panel_line(font, "short", 200) == "short"


# ------------------------------------------------------------------
# (2) Full gear renders the new lines
# ------------------------------------------------------------------

def test_full_gear_renders_gear_lines(panel, monkeypatch):
    captured, _rect = _render_and_capture(panel, _full_gear_hero(), monkeypatch)
    texts = _texts(captured)
    assert "W: Iron Sword (+5)" in texts
    assert "A: Chain Mail (+7)" in texts
    assert "Acc: Hawk Signet (+2 atk, +2 def)" in texts
    assert "Bag: 2/5" in texts
    bag_lines = [t for t in texts if "Healing Potion" in t]
    assert bag_lines, "backpack item names should render under the Bag line"
    assert any("Swiftness Draught" in t for t in texts)


def test_profile_inventory_snapshot_preferred(panel, monkeypatch):
    """When a hero profile is supplied, the panel reads the WK131 snapshot
    fields (weapon_attack / armor_defense / accessory_name / backpack)."""
    hero = _full_gear_hero()
    prof = SimpleNamespace(
        identity=SimpleNamespace(name="Aldous", hero_id="h1", hero_class="warrior",
                                 level=3, personality="bold"),
        progression=SimpleNamespace(xp=40, xp_to_level=100),
        vitals=SimpleNamespace(hp=55, max_hp=80, attack=12, defense=8),
        inventory=SimpleNamespace(
            gold=120, taxed_gold=15, potions=2, max_potions=3,
            weapon_name="Steel Sword", weapon_attack=10,
            armor_name="Plate Armor", armor_defense=12,
            accessory_name="Hawk Signet",
            backpack=("Healing Potion",),
        ),
        last_decision=None,
        current_intent="idle",
        current_state="IDLE",
        current_location="castle",
        current_target="",
        known_places=(),
        career=SimpleNamespace(tiles_revealed=0, places_discovered=0, enemies_defeated=0,
                               bounties_claimed=0, gold_earned=0, purchases_made=0),
        recent_memory=(),
    )
    captured, _rect = _render_and_capture(panel, hero, monkeypatch, hero_profile=prof)
    texts = _texts(captured)
    assert "W: Steel Sword (+10)" in texts
    assert "A: Plate Armor (+12)" in texts
    assert any(t.startswith("Acc: Hawk Signet") for t in texts)
    assert "Bag: 1/5" in texts


# ------------------------------------------------------------------
# (3) Empty gear renders sane defaults
# ------------------------------------------------------------------

def test_empty_gear_renders_defaults(panel, monkeypatch):
    captured, _rect = _render_and_capture(panel, _hero(), monkeypatch)
    texts = _texts(captured)
    assert "W: Fists" in texts
    assert "A: None" in texts
    assert "Acc: None" in texts
    assert "Bag: 0/5" in texts
    # no stray bag item lines under an empty bag
    bag_idx = texts.index("Bag: 0/5")
    assert not texts[bag_idx + 1].startswith(" "), "empty bag must not render item lines"


# ------------------------------------------------------------------
# (4) Long item names do not overflow the 246px panel column
# ------------------------------------------------------------------

def test_long_item_names_do_not_overflow(panel, monkeypatch):
    long_name = "Worldsplitting Warhammer of the Wandering Westwood Warden"
    hero = _hero(
        weapon={"name": long_name, "attack": 18, "id": "x"},
        armor={"name": long_name, "defense": 16, "id": "y"},
        accessory={"name": long_name, "attack": 2, "defense": 2,
                   "speed": 0.35, "max_hp": 25, "id": "z"},
        backpack=[SimpleNamespace(name=long_name) for _ in range(5)],
    )
    captured, rect = _render_and_capture(panel, hero, monkeypatch)
    inner_w = rect.width - 2 * PAD
    gear_prefixes = ("W: ", "A: ", "Acc: ", "Bag", " ")
    checked = 0
    for font, text in captured:
        if not text.startswith(gear_prefixes):
            continue
        checked += 1
        assert font.size(text)[0] <= inner_w, (
            f"line overflows {inner_w}px panel column: {text!r} "
            f"({font.size(text)[0]}px)"
        )
    assert checked >= 5, "expected gear + bag lines to be rendered and checked"


# ------------------------------------------------------------------
# (5) Watch card: compact gear line in the stats band (no card growth)
# ------------------------------------------------------------------

def _watch_profile() -> SimpleNamespace:
    return SimpleNamespace(
        vitals=SimpleNamespace(hp=30, max_hp=50),
        progression=SimpleNamespace(xp=20, xp_to_level=100),
        identity=SimpleNamespace(level=3),
        inventory=SimpleNamespace(weapon_name="Steel Sword", armor_name="Chain Mail"),
    )


def test_watch_card_gear_line_renders_without_growing_card(pygame_headless):
    import game.ui.hud_watch_card as hud_watch_card
    from game.ui.hud import HUD

    # The card layout constants must be untouched (do NOT grow the watch card).
    assert hud_watch_card.WATCH_CARD_STATS_COMPACT_H == 58
    assert hud_watch_card.WATCH_CARD_STATS_H == 78
    assert hud_watch_card.WATCH_CARD_FULL_H_NO_CHAT == 236
    assert hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT == 446

    hud = HUD(1920, 1080)
    hud._pin_slot.hero_id = "h1"
    hud._pin_slot.pinned_name = "Nova"
    hud._watch_card_expanded = True
    hud._left_watch_rect = None
    game_state = {"hero_profiles_by_id": {"h1": _watch_profile()}}

    surface = pygame.Surface((1920, 1080))
    minimap_rect = pygame.Rect(8, 600, 180, 160)
    hud._render_watch_card_chrome(surface, minimap_rect, game_state)  # must not raise

    assert hud._watch_card_rect is not None
    gear_surf = getattr(hud, "_watch_gear_label_surf", None)
    gear_sig = getattr(hud, "_watch_gear_sig", None)
    assert gear_surf is not None, "watch card should cache a gear label surface"
    assert gear_sig is not None and gear_sig[0] == "Steel Sword / Chain Mail"


def test_watch_card_gear_line_dirty_gates(pygame_headless):
    from game.ui.hud import HUD

    hud = HUD(1920, 1080)
    hud._pin_slot.hero_id = "h1"
    hud._pin_slot.pinned_name = "Nova"
    hud._watch_card_expanded = True
    hud._left_watch_rect = None
    game_state = {"hero_profiles_by_id": {"h1": _watch_profile()}}
    surface = pygame.Surface((1920, 1080))
    minimap_rect = pygame.Rect(8, 600, 180, 160)

    hud._render_watch_card_chrome(surface, minimap_rect, game_state)
    first = hud._watch_gear_label_surf
    hud._render_watch_card_chrome(surface, minimap_rect, game_state)
    assert hud._watch_gear_label_surf is first, (
        "same gear values must reuse the cached label surface (dirty-gate)"
    )
    # change gear -> new surface
    game_state["hero_profiles_by_id"]["h1"].inventory.weapon_name = "Mithril Blade"
    hud._render_watch_card_chrome(surface, minimap_rect, game_state)
    assert hud._watch_gear_label_surf is not first
    assert hud._watch_gear_sig[0] == "Mithril Blade / Chain Mail"
