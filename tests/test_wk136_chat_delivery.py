"""WK136 — Sovereign bug: "talking to heroes just hangs, I never get a response".

Two independent root causes, both covered here:

1. DELIVERY BUG (engine loop): ``_poll_conversation_response()`` lived only at the
   END of ``lifecycle.update()`` — the per-sim-tick body. When the game is paused
   (``engine.paused`` set by the building-interior / memorial overlays, or the
   PAUSE speed tier => time multiplier 0.0) ZERO sim ticks drain, so the poll
   never ran and the worker's finished response sat in
   ``llm.conversation_responses`` forever. The keyboard path deliberately lets the
   player chat while paused (game/input/keyboard.py "chat works even at low speed
   tiers"), so this was reachable in normal play. Fix: the conversation pump now
   also runs once per RENDER frame in ``lifecycle.tick_simulation`` (the method
   both the pygame run() loop and the Ursina run_frame() drive every frame),
   independent of pause state.

2. gpt-5-family provider support (ai/providers/openai_provider.py): reasoning
   models need reasoning_effort="minimal" and a completion budget big enough
   that reasoning tokens don't eat the whole thing (>=1500), plus a
   CONVERSATION_TIMEOUT (30s) decoupled from the snappy autonomous LLM_TIMEOUT
   (5s) so the player can actually get a real answer.

These tests drive the REAL engine loop headlessly: GameEngine(headless_ui=True)
+ engine.tick_simulation(dt) — exactly what ursina_app_frame.run_frame calls.
"""

from __future__ import annotations

import json
import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (after SDL env)
import pytest

import config
from ai.basic_ai import BasicAI
from ai.llm_brain import LLMBrain
from game.engine import GameEngine
from game.entities.hero import Hero
from game.sim.timebase import set_time_multiplier


# ---------------------------------------------------------------------------
# Stub providers (mirror tests/test_wk134_llm_e2e.py patterns)
# ---------------------------------------------------------------------------


class _ChatStubProvider:
    """Returns a fixed chat-only JSON reply through the REAL parse/validate path."""

    REPLY = "The roads are quiet, Sovereign. I stand ready."

    def __init__(self):
        self.calls: list[float] = []  # timeout values seen

    @property
    def name(self) -> str:
        return "stub"

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
        self.calls.append(timeout)
        return json.dumps(
            {
                "spoken_response": self.REPLY,
                "interpreted_intent": "no_action_chat_only",
                "tool_action": None,
            }
        )


class _SlowProvider:
    """Honors the ``timeout`` argument like a real HTTP client: raises when the
    simulated latency exceeds it (the OpenAI SDK raises APITimeoutError)."""

    def __init__(self, latency_s: float = 0.3):
        self.latency_s = latency_s
        self.calls: list[float] = []

    @property
    def name(self) -> str:
        return "slow-stub"

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
        self.calls.append(timeout)
        if self.latency_s > timeout:
            time.sleep(timeout)
            raise RuntimeError(f"Request timed out after {timeout}s")
        time.sleep(self.latency_s)
        return json.dumps(
            {
                "spoken_response": "Made it under the wire.",
                "interpreted_intent": "no_action_chat_only",
                "tool_action": None,
            }
        )


class _EmptyProvider:
    """Returns an empty completion — the gpt-5 'reasoning ate the whole token
    budget' failure shape (finish_reason=length, content='')."""

    @property
    def name(self) -> str:
        return "empty-stub"

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, timeout: float = 5.0) -> str:
        return ""


# ---------------------------------------------------------------------------
# Engine harness — the same update path UrsinaApp.run_frame drives each frame
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = GameEngine(headless=False, headless_ui=True)
    brain = LLMBrain(provider_name="mock")
    eng.ai_controller = BasicAI(llm_brain=brain)
    hero = Hero(500.0, 500.0, "warrior", hero_id="wk136_hero", name="Aldric")
    eng.heroes.append(hero)
    try:
        yield eng, brain, hero
    finally:
        try:
            brain.stop()
        finally:
            set_time_multiplier(config.DEFAULT_SPEED_TIER)
            eng.paused = False
            pygame.quit()


def _hero_replies(chat_panel) -> list[dict]:
    return [e for e in chat_panel.conversation_history if e.get("role") == "hero"]


def _pump_frames_until_reply(eng, chat_panel, *, max_frames: int = 240, dt: float = 1 / 60):
    """Drive engine.tick_simulation exactly like ursina_app_frame.run_frame does."""
    for _ in range(max_frames):
        eng.tick_simulation(dt)
        time.sleep(0.01)  # let the LLM worker thread run
        replies = _hero_replies(chat_panel)
        if replies:
            return replies
    return _hero_replies(chat_panel)


def _send_chat(eng, brain, hero, text: str, provider) -> object:
    brain.provider = provider
    chat_panel = eng.hud._chat_panel
    chat_panel.start_conversation(hero)
    eng._last_conversation_request_ms = -10_000_000  # bypass send cooldown
    eng.send_player_message(hero, text)
    assert chat_panel.waiting_for_response is True, "request did not queue"
    return chat_panel


# ---------------------------------------------------------------------------
# 1. Delivery through the real frame loop
# ---------------------------------------------------------------------------


def test_chat_response_delivered_while_running(engine):
    """Baseline: unpaused engine loop delivers the response to the ChatPanel."""
    eng, brain, hero = engine
    chat_panel = _send_chat(eng, brain, hero, "how goes the patrol?", _ChatStubProvider())
    replies = _pump_frames_until_reply(eng, chat_panel)
    assert replies, "no hero reply delivered through the running frame loop"
    assert _ChatStubProvider.REPLY in replies[-1]["text"]
    assert chat_panel.waiting_for_response is False


def test_chat_response_delivered_while_engine_paused(engine):
    """THE WK136 BUG: engine.paused=True (building interior / memorial overlay)
    must not silence the chat forever. Failed before the fix — the poll only ran
    inside sim ticks, and a paused engine drains zero ticks."""
    eng, brain, hero = engine
    eng.paused = True
    chat_panel = _send_chat(eng, brain, hero, "report, while we are paused", _ChatStubProvider())
    replies = _pump_frames_until_reply(eng, chat_panel)
    assert replies, (
        "chat response never delivered while engine.paused — "
        "_poll_conversation_response is not pumped per render frame"
    )
    assert _ChatStubProvider.REPLY in replies[-1]["text"]
    assert chat_panel.waiting_for_response is False


def test_chat_response_delivered_at_pause_speed_tier(engine):
    """THE WK136 BUG (variant): PAUSE speed tier (time multiplier 0.0) — the
    speed bar's leftmost tier — also drained zero ticks. Chat input is
    deliberately allowed at this tier (keyboard.py), so delivery must work."""
    eng, brain, hero = engine
    set_time_multiplier(0.0)
    chat_panel = _send_chat(eng, brain, hero, "report, at pause tier", _ChatStubProvider())
    replies = _pump_frames_until_reply(eng, chat_panel)
    assert replies, (
        "chat response never delivered at speed-tier pause (multiplier 0.0)"
    )
    assert _ChatStubProvider.REPLY in replies[-1]["text"]


def test_chat_timeout_fallback_still_delivers_canned_line(engine):
    """Force a 0.1s conversation timeout: the provider times out, and the canned
    fallback line must still land in the ChatPanel (never dead silence)."""
    eng, brain, hero = engine
    provider = _SlowProvider(latency_s=0.3)

    import ai.llm_brain as llm_brain_mod

    orig = llm_brain_mod.CONVERSATION_TIMEOUT
    llm_brain_mod.CONVERSATION_TIMEOUT = 0.1
    try:
        chat_panel = _send_chat(eng, brain, hero, "are you there?", provider)
        replies = _pump_frames_until_reply(eng, chat_panel, max_frames=300)
    finally:
        llm_brain_mod.CONVERSATION_TIMEOUT = orig
    assert provider.calls and provider.calls[0] == 0.1, "conversation timeout not forwarded"
    assert replies, "timeout fallback line never delivered to the ChatPanel"
    assert "loss for words" in replies[-1]["text"]
    assert chat_panel.waiting_for_response is False


def test_empty_completion_yields_thinking_fallback(engine):
    """Empty content (gpt-5 reasoning swallowing the token budget) maps to the
    'I am thinking, Sovereign...' canned line — delivered, not silent."""
    eng, brain, hero = engine
    chat_panel = _send_chat(eng, brain, hero, "speak up", _EmptyProvider())
    replies = _pump_frames_until_reply(eng, chat_panel)
    assert replies
    assert "thinking" in replies[-1]["text"].lower()


def test_pending_indicator_lifecycle(engine):
    """ChatPanel pending affordance: waiting_for_response True after send (the
    HUD renders the '<name> is thinking...' line off this flag), False after
    delivery."""
    eng, brain, hero = engine
    chat_panel = _send_chat(eng, brain, hero, "thinking indicator?", _ChatStubProvider())
    assert chat_panel.waiting_for_response is True
    replies = _pump_frames_until_reply(eng, chat_panel)
    assert replies
    assert chat_panel.waiting_for_response is False


# ---------------------------------------------------------------------------
# 2. Timeout split: snappy autonomous decisions, patient conversations
# ---------------------------------------------------------------------------


def test_timeout_constants_split():
    assert config.LLM_TIMEOUT == 5.0, "autonomous decisions must stay snappy"
    assert config.CONVERSATION_TIMEOUT >= 30.0, (
        "conversations need reasoning-model headroom (gpt-5 family)"
    )


def test_conversation_path_uses_conversation_timeout(engine):
    eng, brain, hero = engine
    provider = _ChatStubProvider()
    chat_panel = _send_chat(eng, brain, hero, "timeout check", provider)
    replies = _pump_frames_until_reply(eng, chat_panel)
    assert replies
    assert provider.calls and provider.calls[0] == config.CONVERSATION_TIMEOUT


# ---------------------------------------------------------------------------
# 3. gpt-5 family support in OpenAIProvider
# ---------------------------------------------------------------------------


class _FakeCompletions:
    def __init__(self, reject_params: set[str] | None = None, content: str = "ok"):
        self.reject_params = reject_params or set()
        self.content = content
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(dict(kwargs))
        for p in self.reject_params:
            if p in kwargs:
                raise RuntimeError(f"unsupported_parameter: {p!r} is not supported")
        from types import SimpleNamespace

        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def _provider_with_fake_client(model: str, fake: _FakeCompletions):
    from types import SimpleNamespace

    from ai.providers.openai_provider import OpenAIProvider

    p = OpenAIProvider(model=model)
    p.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return p


def test_gpt5_request_shape_minimal_effort_and_big_completion_budget():
    fake = _FakeCompletions()
    p = _provider_with_fake_client("gpt-5-nano", fake)
    out = p.complete("sys", "user", timeout=30.0)
    assert out == "ok"
    call = fake.calls[0]
    assert call["model"] == "gpt-5-nano"
    assert call["reasoning_effort"] == "minimal"
    assert call["max_completion_tokens"] >= 1500, "reasoning tokens count against the budget"
    assert "max_tokens" not in call
    assert "temperature" not in call, "gpt-5 rejects non-default temperature"
    assert call["timeout"] == 30.0


def test_gpt5_falls_back_to_low_effort_when_minimal_rejected():
    class _RejectMinimal(_FakeCompletions):
        def create(self, **kwargs):
            self.calls.append(dict(kwargs))
            if kwargs.get("reasoning_effort") == "minimal":
                raise RuntimeError("invalid value for 'reasoning_effort': 'minimal' is not supported")
            from types import SimpleNamespace

            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="low-ok"))]
            )

    fake = _RejectMinimal()
    p = _provider_with_fake_client("gpt-5-nano", fake)
    assert p.complete("sys", "user", timeout=30.0) == "low-ok"
    efforts = [c.get("reasoning_effort") for c in fake.calls]
    assert efforts[0] == "minimal" and "low" in efforts[1:]


def test_gpt5_drops_reasoning_effort_when_param_unsupported():
    fake = _FakeCompletions(reject_params={"reasoning_effort"})
    p = _provider_with_fake_client("gpt-5-mini", fake)
    assert p.complete("sys", "user") == "ok"
    last = fake.calls[-1]
    assert "reasoning_effort" not in last
    assert last.get("max_completion_tokens", 0) >= 1500


def test_non_gpt5_request_shape_unchanged():
    fake = _FakeCompletions()
    p = _provider_with_fake_client("gpt-4o-mini", fake)
    assert p.complete("sys", "user") == "ok"
    call = fake.calls[0]
    assert "reasoning_effort" not in call
    assert call.get("max_completion_tokens") == 600
    assert "temperature" not in call


def test_non_gpt5_max_tokens_legacy_fallback_kept():
    fake = _FakeCompletions(reject_params={"max_completion_tokens"})
    p = _provider_with_fake_client("gpt-4o-mini", fake)
    assert p.complete("sys", "user") == "ok"
    assert "max_tokens" in fake.calls[-1]
