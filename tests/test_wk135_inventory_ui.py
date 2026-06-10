"""WK135 inventory UI (Agent 08): InventoryPanel window + hero-panel Inventory
button + watch-card Bag button + ``I`` hotkey.

Headless pygame harness (SDL dummy video driver, same pattern as
tests/test_wk131_items_ui.py). Window-content assertions spy on
``pygame.font.Font.render`` to capture exactly which text the panel drew.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

# Headless: never bring up a real display when ui / pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from game.content.items import get_item
from game.ui.inventory_panel import (
    RARITY_COLORS,
    InventoryPanel,
    item_name,
    item_stats_text,
    rarity_color,
    resolve_rarity,
)
from game.ui.hero_panel import HeroPanel
from game.ui.theme import UITheme


# ------------------------------------------------------------------
# Fixtures / helpers
# ------------------------------------------------------------------

@pytest.fixture(scope="module")
def pygame_headless():
    pygame.init()
    pygame.display.set_mode((320, 240))
    yield
    # leave pygame initialized for other test modules in the same session


def _hero(**overrides) -> SimpleNamespace:
    base = dict(
        name="Sir Aldric",
        hero_id="h1",
        hero_class="warrior",
        level=1,
        personality="bold",
        xp=0,
        xp_to_level=100,
        hp=60,
        max_hp=60,
        attack=22,
        defense=14,
        gold=0,
        taxed_gold=0,
        potions=0,
        max_potions=5,
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
        is_alive=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hero_with_5_items() -> SimpleNamespace:
    """The exact WK135 Sovereign repro: 3 equipped + 2 backpack items."""
    return _hero(
        weapon={"name": "Steel Sword", "attack": 10, "id": "steel_sword"},
        armor={"name": "Chain Mail", "defense": 7, "id": "chain_mail"},
        accessory={
            "name": "Hawk Signet", "attack": 2, "defense": 2,
            "speed": 0.0, "max_hp": 0, "id": "hawk_signet",
        },
        backpack=[get_item("dagger"), get_item("long_bow")],
        potions=1,
    )


class _SpyFont:
    """Wraps a pygame Font, recording every rendered string (pygame.font.Font
    itself is an immutable C type and cannot be monkeypatched)."""

    def __init__(self, font: pygame.font.Font, sink: list[str]):
        self._font = font
        self._sink = sink

    def render(self, text, aa, color, *args, **kwargs):
        self._sink.append(str(text))
        return self._font.render(text, aa, color, *args, **kwargs)

    def size(self, text):
        return self._font.size(text)

    def get_height(self):
        return self._font.get_height()


def _render_and_spy_texts(panel: InventoryPanel, monkeypatch, size=(1920, 1080)) -> list[str]:
    """Render the window and capture every string the panel's fonts drew."""
    texts: list[str] = []
    panel.font_tiny = _SpyFont(panel.font_tiny, texts)
    panel.theme.font_title = _SpyFont(panel.theme.font_title, texts)
    panel.theme.font_body = _SpyFont(panel.theme.font_body, texts)
    panel.theme.font_small = _SpyFont(panel.theme.font_small, texts)
    surface = pygame.Surface(size, pygame.SRCALPHA)
    panel.render(surface)
    return texts


# ------------------------------------------------------------------
# (1) Rarity mapping
# ------------------------------------------------------------------

def test_rarity_color_mapping():
    assert rarity_color("common") == RARITY_COLORS["common"]
    assert rarity_color("uncommon") == (110, 200, 110)
    assert rarity_color("rare") == (95, 155, 235)
    assert rarity_color("legendary") == (235, 150, 60)
    # unknown / garbage falls back to common
    assert rarity_color("mythic") == RARITY_COLORS["common"]
    assert rarity_color("") == RARITY_COLORS["common"]


def test_resolve_rarity_itemdef_and_legacy_dicts():
    assert resolve_rarity(get_item("dagger")) == "common"
    assert resolve_rarity(get_item("long_bow")) == "uncommon"
    assert resolve_rarity(get_item("hawk_signet")) == "rare"
    assert resolve_rarity(get_item("runed_warhammer")) == "legendary"
    # legacy equip dict with registry id
    assert resolve_rarity({"name": "Steel Sword", "attack": 10, "id": "steel_sword"}) == "uncommon"
    # legacy dict without id falls back to a name lookup
    assert resolve_rarity({"name": "Plate Armor", "defense": 12}) == "rare"
    # unknown item / None -> common
    assert resolve_rarity({"name": "Mystery Club"}) == "common"
    assert resolve_rarity(None) == "common"


def test_item_helpers():
    assert item_name({"name": "Steel Sword"}) == "Steel Sword"
    assert item_name(get_item("dagger")) == "Dagger"
    assert item_stats_text({"attack": 10}) == "+10 ATK"
    assert item_stats_text({"defense": 7}) == "+7 DEF"
    assert item_stats_text({"attack": 2, "defense": 2}) == "+2 ATK, +2 DEF"
    assert item_stats_text(get_item("swift_boots")) == "+0.35 SPD"
    assert item_stats_text(None) == ""


# ------------------------------------------------------------------
# (2) Window contents: 5-item hero
# ------------------------------------------------------------------

def test_window_renders_equipment_and_backpack(pygame_headless, monkeypatch):
    panel = InventoryPanel(1920, 1080)
    panel.open(_hero_with_5_items())
    assert panel.visible
    texts = _render_and_spy_texts(panel, monkeypatch)

    # All 3 equip slots render the right names.
    assert "Steel Sword" in texts
    assert "Chain Mail" in texts
    assert "Hawk Signet" in texts
    assert "+10 ATK" in texts
    assert "+7 DEF" in texts
    assert "+2 ATK, +2 DEF" in texts

    # Backpack header + 2 filled + 3 empty slots.
    assert "Backpack 2/5" in texts
    assert "Dagger" in texts
    assert "Long Bow" in texts
    assert texts.count("—") == 3, "3 empty backpack slots must render as empty boxes"

    # Consumables row + title + footer hint.
    assert "Potions 1/5" in texts
    assert any("Sir Aldric" in t and "Inventory" in t for t in texts)
    assert any("auto-equip" in t for t in texts)


# ------------------------------------------------------------------
# (3) Empty-hero case
# ------------------------------------------------------------------

def test_window_renders_empty_hero(pygame_headless, monkeypatch):
    panel = InventoryPanel(1920, 1080)
    panel.open(_hero())
    texts = _render_and_spy_texts(panel, monkeypatch)

    assert "Backpack 0/5" in texts
    assert "Potions 0/5" in texts
    assert texts.count("Empty") == 3, "all 3 equip slot boxes must show the dimmed Empty label"
    assert texts.count("None") == 3, "all 3 equip slots must show a dimmed None name"
    assert texts.count("—") == 5, "all 5 backpack slots must render as empty boxes"


# ------------------------------------------------------------------
# (4) Open / close: X, outside click, ESC path, modal consumption
# ------------------------------------------------------------------

def test_close_button_and_outside_click_close(pygame_headless):
    panel = InventoryPanel(1920, 1080)
    panel.open(_hero_with_5_items())
    surface = pygame.Surface((1920, 1080), pygame.SRCALPHA)
    panel.render(surface)  # establishes close_rect + panel rect

    # Click inside the panel (not on X): consumed, stays open.
    rect = panel.modal.get_panel_rect()
    assert panel.handle_click(rect.center) is True
    assert panel.visible

    # Click the X: closes.
    assert panel.handle_click(panel.close_rect.center) is True
    assert not panel.visible
    assert panel.hero is None

    # Re-open, click outside the panel: closes (mirrors the quest dialog).
    panel.open(_hero_with_5_items())
    panel.render(surface)
    outside = (rect.x - 20, rect.y - 20)
    assert panel.handle_click(outside) is True
    assert not panel.visible


def test_esc_closes_inventory_first(pygame_headless):
    """ESC keyboard path: the inventory window closes before anything else."""
    from game.input.keyboard import handle_keydown

    hud = SimpleNamespace(inventory_panel=InventoryPanel(1920, 1080), _chat_panel=None)
    hud.inventory_panel.open(_hero_with_5_items())
    c = SimpleNamespace(hud=hud, _command_mode=False)
    ih = SimpleNamespace(commands=c)
    handle_keydown(ih, SimpleNamespace(key="esc", raw_event=None))
    assert not hud.inventory_panel.visible


# ------------------------------------------------------------------
# (5) Hotkey "I" toggles for the selected hero
# ------------------------------------------------------------------

def test_hotkey_i_is_free_of_build_hotkeys():
    from game.input_handler import BUILD_HOTKEY_TO_TYPE

    assert "i" not in BUILD_HOTKEY_TO_TYPE, "WK135 claims hotkey I; it must stay free"


def _keyboard_commands(hero) -> SimpleNamespace:
    hud = SimpleNamespace(inventory_panel=InventoryPanel(1920, 1080), _chat_panel=None)
    return SimpleNamespace(
        hud=hud,
        _command_mode=False,
        pause_menu=SimpleNamespace(visible=False),
        paused=False,
        selected_hero=hero,
    )


def test_hotkey_i_opens_and_closes(pygame_headless):
    from game.input.keyboard import handle_keydown

    hero = _hero_with_5_items()
    c = _keyboard_commands(hero)
    ih = SimpleNamespace(commands=c)
    event = SimpleNamespace(key="i", raw_event=None)

    handle_keydown(ih, event)
    assert c.hud.inventory_panel.visible
    assert c.hud.inventory_panel.hero is hero

    handle_keydown(ih, event)  # toggle off
    assert not c.hud.inventory_panel.visible


def test_hotkey_i_noop_without_hero(pygame_headless):
    from game.input.keyboard import handle_keydown

    c = _keyboard_commands(None)
    handle_keydown(SimpleNamespace(commands=c), SimpleNamespace(key="i", raw_event=None))
    assert not c.hud.inventory_panel.visible


# ------------------------------------------------------------------
# (6) Hero-panel Inventory button (Chat-button pattern)
# ------------------------------------------------------------------

def test_hero_panel_inventory_button_opens(pygame_headless):
    panel = HeroPanel(
        UITheme(),
        frame_inner=(70, 70, 90),
        frame_highlight=(110, 110, 140),
    )
    hero = _hero_with_5_items()
    surface = pygame.Surface((1280, 720), pygame.SRCALPHA)
    rect = pygame.Rect(8, 56, 246, 600)
    panel.render(surface, hero, rect, right_close_rect=None)

    assert panel._inventory_button_rect is not None
    assert panel._inventory_button_visible
    # Button sits below the Chat button (same column).
    assert panel._chat_button_rect is not None
    assert panel._inventory_button_rect.top >= panel._chat_button_rect.bottom

    action = panel.handle_click(panel._inventory_button_rect.center)
    assert isinstance(action, dict)
    assert action.get("type") == "open_inventory"
    assert action.get("hero") is hero

    # Chat button still returns its own action (unchanged).
    chat = panel.handle_click(panel._chat_button_rect.center)
    assert isinstance(chat, dict) and chat.get("type") == "start_conversation"


# ------------------------------------------------------------------
# (7) HUD wiring: modal click consumption + watch-card Bag button
# ------------------------------------------------------------------

def test_hud_click_consumed_while_window_open(pygame_headless):
    from game.ui.hud import HUD

    hud = HUD(1920, 1080)
    hero = _hero_with_5_items()
    hud.inventory_panel.open(hero)
    surface = pygame.Surface((1920, 1080), pygame.SRCALPHA)
    hud.inventory_panel.render(surface)

    rect = hud.inventory_panel.modal.get_panel_rect()
    assert hud.handle_click(rect.center, {}) == "inventory_click"
    assert hud.inventory_panel.visible
    # Outside click is also consumed by the modal (and closes it).
    assert hud.handle_click((rect.x - 30, rect.y - 30), {}) == "inventory_click"
    assert not hud.inventory_panel.visible


def test_hud_watch_card_bag_button_returns_open_inventory(pygame_headless):
    from game.ui.hud import HUD

    hud = HUD(1920, 1080)
    hero = _hero_with_5_items()
    hud._pin_slot.hero_id = "h1"
    hud._pin_slot.pinned_name = "Sir Aldric"
    hud._inventory_open_rect = pygame.Rect(100, 100, 34, 16)
    action = hud.handle_click((110, 108), {"heroes": [hero], "hero_profiles_by_id": {"h1": object()}})
    assert isinstance(action, dict)
    assert action.get("type") == "open_inventory"
    assert action.get("hero") is hero


def test_hud_watch_card_renders_bag_button(pygame_headless):
    """The pinned watch card draws Chat AND Bag buttons in the stats-row slack
    without growing the card (WATCH_CARD_* constants untouched)."""
    import game.ui.hud_watch_card as hud_watch_card
    from game.ui.hud import HUD

    assert hud_watch_card.WATCH_CARD_STATS_COMPACT_H == 58
    assert hud_watch_card.WATCH_CARD_STATS_H == 78
    assert hud_watch_card.WATCH_CARD_FULL_H_NO_CHAT == 236
    assert hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT == 446

    hud = HUD(1920, 1080)
    hud._pin_slot.hero_id = "h1"
    hud._pin_slot.pinned_name = "Sir Aldric"
    hud._watch_card_expanded = True
    hud._left_watch_rect = None
    prof = SimpleNamespace(
        vitals=SimpleNamespace(hp=60, max_hp=60),
        progression=SimpleNamespace(xp=0, xp_to_level=100),
        identity=SimpleNamespace(level=1),
        inventory=SimpleNamespace(weapon_name="Steel Sword", armor_name="Chain Mail"),
    )
    game_state = {"hero_profiles_by_id": {"h1": prof}}
    surface = pygame.Surface((1920, 1080))
    minimap_rect = pygame.Rect(8, 600, 246, 160)
    hud._render_watch_card_chrome(surface, minimap_rect, game_state)

    assert hud._chat_open_rect is not None, "Chat button must still render"
    assert hud._inventory_open_rect is not None, "Bag button must render next to Chat"
    card = hud._watch_card_rect
    assert card is not None
    assert card.contains(hud._inventory_open_rect), "Bag button must stay inside the card"
    assert hud._inventory_open_rect.left >= hud._chat_open_rect.right


# ------------------------------------------------------------------
# (8) Window stays within screen bounds at both target resolutions
# ------------------------------------------------------------------

@pytest.mark.parametrize("size", [(1024, 576), (1920, 1080)])
def test_window_within_screen_bounds(pygame_headless, size):
    panel = InventoryPanel(*size)
    panel.open(_hero_with_5_items())
    surface = pygame.Surface(size, pygame.SRCALPHA)
    panel.render(surface)
    rect = panel.modal.get_panel_rect()
    screen = pygame.Rect(0, 0, *size)
    assert screen.contains(rect), f"panel {rect} must fit inside {size}"
    assert panel.close_rect is not None and screen.contains(panel.close_rect)
