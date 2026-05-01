"""Lightweight helpers for WK49 HeroPanel profile UI."""

from game.ui.hero_panel import intent_label_from_slug, truncate_panel_line


def test_truncate_panel_line():
    short = truncate_panel_line("hello", max_chars=10)
    assert short == "hello"
    long = truncate_panel_line("0123456789abcdef", max_chars=8)
    assert long.endswith("\u2026")


def test_intent_mapping():
    assert intent_label_from_slug("idle") == "Idle"
    assert intent_label_from_slug("pursuing_bounty") == "Pursuing bounty"
    assert intent_label_from_slug("custom_future_intent") == "Custom Future Intent"
