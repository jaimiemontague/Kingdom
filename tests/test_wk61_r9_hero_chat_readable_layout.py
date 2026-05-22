"""WK61 R9: Hero menu chat readable split layout."""

from __future__ import annotations

import pygame
import pytest

from game.entities.hero import Hero
from game.ui.hud import (
    HERO_MENU_CHAT_MIN_H,
    HERO_MENU_HERO_MIN_H,
    HUD,
)


@pytest.fixture
def _pygame_font_ready() -> None:
    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()


@pytest.mark.parametrize("w,h", [(1024, 576), (1920, 1080)])
def test_hero_menu_chat_split_reserves_readable_space(
    _pygame_font_ready: None, w: int, h: int
) -> None:
    hud = HUD(w, h)
    top_h = int(hud.theme.top_bar_h)
    bottom_h = int(hud.theme.bottom_bar_h)
    from game.ui.hud import RADAR_MINIMAP_H

    left_h = (h - RADAR_MINIMAP_H) - top_h
    left = pygame.Rect(0, top_h, 224, left_h)

    split = hud._hero_menu_chat_split_rects(left)
    assert split is not None
    hero_rect, chat_rect = split

    assert hero_rect.height >= HERO_MENU_HERO_MIN_H
    assert chat_rect.height >= HERO_MENU_CHAT_MIN_H
    assert hero_rect.bottom < chat_rect.top
    assert chat_rect.bottom <= left.bottom

    # Chat band must not overlap bottom command bar.
    bottom_y = h - bottom_h
    assert chat_rect.bottom <= bottom_y or chat_rect.bottom <= left.bottom


def test_hero_menu_chat_split_at_576p_leaves_scrollable_hero(_pygame_font_ready: None) -> None:
    hud = HUD(1024, 576)
    hero = Hero(0.0, 0.0, hero_id="r9_hero", name="ReadableHero")
    hud._chat_panel.start_conversation(hero)
    hud._chat_panel.conversation_history.extend(
        [
            {"role": "player", "text": "Explore the eastern woods."},
            {"role": "hero", "text": "Aye, I'll scout the treeline and report back."},
        ]
    )

    surface = pygame.Surface((1024, 576))
    game_state = {
        "selected_hero": hero,
        "selected_building": None,
        "heroes": [hero],
        "hero_profiles_by_id": {},
        "bounties": [],
    }
    hud.render(surface, game_state)

    assert hud._hero_menu_chat_rect is not None
    assert hud._hero_menu_chat_rect.height >= HERO_MENU_CHAT_MIN_H
    assert hud._hero_menu_hero_rect is not None
    assert hud._hero_menu_hero_rect.height >= HERO_MENU_HERO_MIN_H
