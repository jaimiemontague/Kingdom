"""Tests for wk62 HUD layout extraction and typed UI actions.

Verifies that:
- UIAction is frozen and constructible
- normalize_ui_action converts legacy str/dict/None returns
- HUDLayoutManager produces correct geometry for various screen sizes
- HUDLayout rectangles are internally consistent
- Constants re-exported through hud.py remain accessible (backward compat)
"""

from __future__ import annotations

import pygame
import pytest

pygame.init()


# ── UIAction tests ──────────────────────────────────────────────────


class TestUIAction:
    def test_basic_construction(self):
        from game.ui.ui_actions import UIAction

        a = UIAction("quit")
        assert a.kind == "quit"
        assert a.payload is None

    def test_with_payload(self):
        from game.ui.ui_actions import UIAction

        data = {"hero_id": "h1"}
        a = UIAction("select_hero", payload=data)
        assert a.kind == "select_hero"
        assert a.payload is data

    def test_frozen(self):
        from game.ui.ui_actions import UIAction

        a = UIAction("quit")
        with pytest.raises(AttributeError):
            a.kind = "other"

    def test_equality(self):
        from game.ui.ui_actions import UIAction

        assert UIAction("quit") == UIAction("quit")
        assert UIAction("quit") != UIAction("close")
        assert UIAction("a", 1) == UIAction("a", 1)


# ── normalize_ui_action tests ──────────────────────────────────────


class TestNormalizeUIAction:
    def test_none_returns_none(self):
        from game.ui.ui_actions import normalize_ui_action

        assert normalize_ui_action(None) is None

    def test_string_returns_action(self):
        from game.ui.ui_actions import UIAction, normalize_ui_action

        result = normalize_ui_action("quit")
        assert result == UIAction("quit")

    def test_dict_with_type_key(self):
        from game.ui.ui_actions import normalize_ui_action

        raw = {"type": "select_hero_at_world", "wx": 100.0, "wy": 200.0}
        result = normalize_ui_action(raw)
        assert result is not None
        assert result.kind == "select_hero_at_world"
        assert result.payload is raw

    def test_dict_with_action_key(self):
        from game.ui.ui_actions import normalize_ui_action

        raw = {"action": "build_menu_toggle"}
        result = normalize_ui_action(raw)
        assert result is not None
        assert result.kind == "build_menu_toggle"

    def test_dict_empty_returns_none(self):
        from game.ui.ui_actions import normalize_ui_action

        assert normalize_ui_action({}) is None

    def test_passthrough_uiaction(self):
        from game.ui.ui_actions import UIAction, normalize_ui_action

        original = UIAction("pin_hero")
        assert normalize_ui_action(original) is original

    def test_unrecognized_type_returns_none(self):
        from game.ui.ui_actions import normalize_ui_action

        assert normalize_ui_action(42) is None
        assert normalize_ui_action(3.14) is None
        assert normalize_ui_action([1, 2]) is None


# ── HUDLayout / HUDLayoutManager tests ────────────────────────────


class TestHUDLayoutManager:
    def test_default_1920x1080(self):
        from game.ui.hud_layout import HUDLayoutManager

        mgr = HUDLayoutManager()
        layout = mgr.compute(1920, 1080)

        assert layout.top_bar == pygame.Rect(0, 0, 1920, 48)
        assert layout.bottom_bar == pygame.Rect(0, 1080 - 96, 1920, 96)
        assert layout.minimap.x == 0
        assert layout.minimap.y == 1080 - 180
        assert layout.minimap.width == 224
        assert layout.minimap.height == 180
        assert layout.right_panel.width == 0  # retired WK52 R4
        assert layout.left_panel.width == 224
        assert layout.left_panel.y == 48
        assert layout.left_panel.height == layout.minimap.y - 48

    def test_small_screen(self):
        from game.ui.hud_layout import HUDLayoutManager

        mgr = HUDLayoutManager()
        layout = mgr.compute(800, 600)

        assert layout.top_bar.width == 800
        assert layout.bottom_bar.y == 600 - 96
        assert layout.minimap.y == 600 - 180
        assert layout.left_panel.height == max(0, layout.minimap.y - 48)

    def test_custom_theme_values(self):
        from game.ui.hud_layout import HUDLayoutManager

        mgr = HUDLayoutManager()
        layout = mgr.compute(1920, 1080, top_bar_h=60, bottom_bar_h=100)

        assert layout.top_bar.height == 60
        assert layout.bottom_bar.height == 100
        assert layout.bottom_bar.y == 1080 - 100

    def test_rects_do_not_overlap_vertically(self):
        """Top bar, left content area, and bottom bar should not overlap."""
        from game.ui.hud_layout import HUDLayoutManager

        mgr = HUDLayoutManager()
        layout = mgr.compute(1920, 1080)

        assert layout.top_bar.bottom <= layout.left_panel.top
        assert layout.left_panel.bottom <= layout.minimap.top or layout.left_panel.bottom <= layout.minimap.y
        assert layout.minimap.bottom <= layout.bottom_bar.bottom

    def test_recall_and_memorial_adjacent(self):
        from game.ui.hud_layout import HUDLayoutManager

        mgr = HUDLayoutManager()
        layout = mgr.compute(1920, 1080)

        # Recall starts right of minimap
        assert layout.recall_button.x > layout.minimap.right - 1
        # Memorial is right of recall
        assert layout.memorial_button.x >= layout.recall_button.right
        # Command bar is right of memorial
        assert layout.command_bar.x >= layout.memorial_button.right

    def test_speed_control_above_bottom_bar(self):
        from game.ui.hud_layout import HUDLayoutManager

        mgr = HUDLayoutManager()
        layout = mgr.compute(1920, 1080)

        assert layout.speed_control.bottom <= layout.bottom_bar.y + 4  # small gap tolerance


# ── Backward compatibility: constants still importable from hud ────


class TestBackwardCompatImports:
    def test_constants_from_hud(self):
        from game.ui.hud import LEFT_COL_W, RADAR_MINIMAP_H, RECALL_BTN_W, MEMORIAL_BTN_W

        assert LEFT_COL_W == 224
        assert RADAR_MINIMAP_H == 180
        assert RECALL_BTN_W == 180
        assert MEMORIAL_BTN_W == 90

    def test_constants_from_hud_layout(self):
        from game.ui.hud_layout import LEFT_COL_W, RADAR_MINIMAP_H, RECALL_BTN_W, MEMORIAL_BTN_W

        assert LEFT_COL_W == 224
        assert RADAR_MINIMAP_H == 180
        assert RECALL_BTN_W == 180
        assert MEMORIAL_BTN_W == 90

    def test_uiaction_importable_from_hud(self):
        """UIAction and normalize_ui_action are re-exported through hud for discoverability."""
        from game.ui.hud import UIAction, normalize_ui_action

        assert UIAction("test").kind == "test"
        assert normalize_ui_action("test") == UIAction("test")
