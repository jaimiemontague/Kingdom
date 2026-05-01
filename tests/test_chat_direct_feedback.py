"""WK50 Phase 2B: chat overlay hints for direct prompt outcomes (pure logic, no HUD render)."""

import os

# Headless pygame for Font module used by imports in game.ui chain.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.font.init()

from game.ui.chat_panel import format_direct_prompt_hint


def test_plain_chat_hint_suppressed():
    """No-tool friendly reply should stay text-only."""
    assert (
        format_direct_prompt_hint(
            {
                "tool_action": None,
                "obey_defy": "Obey",
                "refusal_reason": "",
                "safety_assessment": "unknown",
                "interpreted_intent": "no_action_chat_only",
            }
        )
        is None
    )


def test_accept_order_with_tool_action():
    h = format_direct_prompt_hint(
        {
            "tool_action": "move_to",
            "obey_defy": "Obey",
            "refusal_reason": "",
            "safety_assessment": "safe",
            "interpreted_intent": "return_home",
            "physical_committed": True,
        }
    )
    assert h == "Order applied"


def test_redirect_when_validator_prefers_safer_physical_action():
    h = format_direct_prompt_hint(
        {
            "tool_action": "use_potion",
            "obey_defy": "Obey",
            "refusal_reason": "",
            "safety_assessment": "critical_redirect",
            "interpreted_intent": "seek_healing",
            "physical_committed": True,
        }
    )
    assert "Redirected" in h


def test_tool_claimed_but_not_committed():
    h = format_direct_prompt_hint(
        {
            "tool_action": "move_to",
            "obey_defy": "Obey",
            "refusal_reason": "",
            "safety_assessment": "safe",
            "interpreted_intent": "return_home",
            "physical_committed": False,
        }
    )
    assert h == "Not applied — no action committed"


def test_not_carried_out_mvp_combat():
    h = format_direct_prompt_hint(
        {
            "tool_action": None,
            "obey_defy": "Defy",
            "refusal_reason": "mvp_combat_deferred",
            "safety_assessment": "deferred",
            "interpreted_intent": "no_action_chat_only",
        }
    )
    assert h is not None
    assert h.startswith("Refused")
    assert "attack" in h


def test_not_carried_out_via_reason_without_explicit_defy():
    h = format_direct_prompt_hint(
        {
            "tool_action": None,
            "obey_defy": "Obey",
            "refusal_reason": "no_gold",
            "safety_assessment": "impossible",
            "interpreted_intent": "no_action_chat_only",
        }
    )
    assert h is not None
    assert "gold" in h.lower()

