"""WK61 R4 UI regressions — Agent 08 (taxable gold display, hero Chat button)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame
import pytest

from config import COLOR_GOLD, COLOR_WHITE
from game.entities.buildings.economic import Blacksmith, Marketplace
from game.entities.hero import Hero
from game.ui.building_renderers.economic_panel import EconomicPanelRenderer
from game.ui.hero_panel import HeroPanel
from game.ui.hud import HUD
from game.ui.pin_slot import PinSlot
from game.ui.theme import UITheme


@pytest.fixture
def _pygame_font_ready() -> None:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.font.init()
    try:
        yield
    finally:
        pygame.font.quit()


def test_hero_panel_chat_button_returns_start_conversation(_pygame_font_ready: None) -> None:
    theme = UITheme()
    panel = HeroPanel(theme, frame_inner=(80, 80, 100), frame_highlight=(107, 107, 132))
    hero = Hero(0.0, 0.0, hero_id="chat_test", name="ChatTest")
    panel._current_hero = hero
    panel._chat_button_visible = True
    panel._chat_button_rect = pygame.Rect(10, 200, 180, 26)

    action = panel.handle_click((100, 213))

    assert action == {"type": "start_conversation", "hero": hero}


def test_start_conversation_does_not_pin_unpinned_hero(_pygame_font_ready: None) -> None:
    from game.input_handler import InputHandler

    hud = MagicMock()
    hud._pin_slot = PinSlot()
    hud._watch_card_expanded = False
    hud._chat_visible = False

    chat_panel = MagicMock()
    hud._chat_panel = chat_panel

    hero = Hero(0.0, 0.0, hero_id="unpinned", name="Unpinned")
    commands = MagicMock()
    commands.hud = hud
    commands.pause_menu.visible = False
    commands.paused = False
    commands.running = True
    commands.building_panel.deselect = MagicMock()
    commands.get_game_state.return_value = {}
    commands.selected_hero = None
    commands.selected_building = None

    handler = InputHandler(commands)
    event = SimpleNamespace(
        button=1,
        pos=(50, 50),
        raw_event=None,
    )

    hud.handle_click.return_value = {"type": "start_conversation", "hero": hero}

    handler.handle_mousedown(event)

    assert hud._pin_slot.hero_id is None
    chat_panel.start_conversation.assert_called_once_with(hero)
    assert hud._chat_visible is False
    assert commands.selected_hero is hero


def test_economic_panel_taxable_gold_positive_uses_gold_color(_pygame_font_ready: None) -> None:
    renderer = EconomicPanelRenderer()
    marketplace = Marketplace(0, 0)
    marketplace.stored_tax_gold = 42

    panel = SimpleNamespace(
        font_normal=pygame.font.Font(None, 24),
        font_small=pygame.font.Font(None, 18),
    )
    surface = pygame.Surface((300, 120))

    y = renderer._render_taxable_gold(panel, surface, marketplace, 10)

    assert y == 35
    gold_pixels = [
        surface.get_at((x, y_row))[:3]
        for x in range(10, 180, 4)
        for y_row in range(10, 28, 2)
    ]
    assert COLOR_GOLD in gold_pixels


def test_economic_panel_taxable_gold_zero_is_white_not_grey_stale(_pygame_font_ready: None) -> None:
    renderer = EconomicPanelRenderer()
    blacksmith = Blacksmith(0, 0)
    blacksmith.stored_tax_gold = 0

    panel = SimpleNamespace(
        font_normal=pygame.font.Font(None, 24),
        font_small=pygame.font.Font(None, 18),
    )
    surface = pygame.Surface((320, 120))

    renderer._render_taxable_gold(panel, surface, blacksmith, 10)

    white_pixels = [
        surface.get_at((x, y_row))[:3]
        for x in range(10, 180, 4)
        for y_row in range(10, 24, 2)
    ]
    assert COLOR_WHITE in white_pixels
    hint_pixels = [
        surface.get_at((x, y_row))[:3]
        for x in range(10, 280, 4)
        for y_row in range(30, 50, 2)
    ]
    assert (150, 150, 150) in hint_pixels


def test_hud_renders_hero_menu_chat_split_without_pin(_pygame_font_ready: None) -> None:
    hud = HUD(1024, 576)
    hero = Hero(0.0, 0.0, hero_id="popup_hero", name="PopupHero")
    hud._chat_panel.start_conversation(hero)
    left = pygame.Rect(0, 48, 224, 348)

    game_state = {
        "selected_hero": hero,
        "selected_building": None,
        "heroes": [hero],
        "hero_profiles_by_id": {},
    }

    assert hud._should_render_hero_menu_chat_popup(game_state) is True
    split = hud._hero_menu_chat_split_rects(left)
    assert split is not None
    hero_rect, chat_rect = split
    assert hero_rect.height >= 120
    assert chat_rect.height >= 152
    assert hero_rect.bottom + 4 <= chat_rect.top
    assert chat_rect.bottom <= left.bottom
    assert chat_rect.width > 0
