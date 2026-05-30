"""WK85 Round D-5 driver test — exploration.handle_idle decomposed into ordered steps.

WK85 decomposed the 128-LOC ``handle_idle`` god-function in
``ai/behaviors/exploration.py`` into 8 ordered, named ``_idle_*(ai, hero, view) ->
bool`` step functions. ``handle_idle`` is now a thin driver that iterates the
module-level ``_IDLE_STEPS`` tuple IN ORDER and returns as soon as a step returns
True (the original early-return points); a step returning False falls through to
the next. The terminal ``_idle_patrol_zone`` always returns False (the original
no-``return`` final block).

This is the WAVE-2 (Agent 11 / QA) driver pin. It does NOT re-test the idle
*behavior* — that is covered byte-identically by the full suite and the WK67
300-tick AI-decision digest (``b73961…``), which hashes exactly these idle
decisions and is a PERFECT guard against any reorder/short-circuit drift. This
file proves the *driver seam*:

1. ``exploration.handle_idle`` exists, is callable, and keeps its
   ``(ai, hero, view)`` signature.
2. All 8 ``_idle_*`` step functions exist + are callable.
3. ``exploration._IDLE_STEPS`` is a tuple/list of EXACTLY those 8 functions in
   the documented order.
4. DRIVER SHORT-CIRCUIT pin: patch ``_IDLE_STEPS`` with spies so that a chosen
   step returns True — assert the driver stops there (earlier steps ran once,
   that step ran once, LATER steps did NOT run).
5. DRIVER FALL-THROUGH pin: patch ``_IDLE_STEPS`` so ALL steps return False —
   assert every step ran exactly once, in order, and ``handle_idle`` returns
   ``None``.

The fakes are minimal ``SimpleNamespace`` stand-ins: the driver only calls
``as_ai_view(view)`` (a pass-through for any non-dict) and then iterates the
patched ``_IDLE_STEPS``, so no real ai/hero/world is needed.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from ai.behaviors import exploration


# The 8 ordered step names, in the order WK85 documents them (and the order the
# driver must run them). The tuple in exploration._IDLE_STEPS must match.
_STEP_NAMES = (
    "_idle_clear_dangling_bounty",
    "_idle_take_bounty",
    "_idle_seek_meal",
    "_idle_shopping",
    "_idle_engage_nearby_enemy",
    "_idle_get_drink",
    "_idle_visit_poi",
    "_idle_patrol_zone",
)


def _fake_avh():
    """A minimal (ai, hero, view) triple — the driver only forwards these.

    ``view`` is a SimpleNamespace (not a dict) so ``as_ai_view`` passes it through
    unchanged; ``ai``/``hero`` are opaque sentinels the spies just record.
    """
    ai = SimpleNamespace(name="ai")
    hero = SimpleNamespace(name="hero")
    view = SimpleNamespace(name="view")
    return ai, hero, view


# ---------------------------------------------------------------------------
# 1. handle_idle exists, is callable, keeps its (ai, hero, view) signature.
# ---------------------------------------------------------------------------

def test_handle_idle_exists_and_callable_with_signature():
    assert exploration.__name__ == "ai.behaviors.exploration"
    fn = getattr(exploration, "handle_idle", None)
    assert fn is not None, "ai.behaviors.exploration.handle_idle missing"
    assert callable(fn), "ai.behaviors.exploration.handle_idle is not callable"

    params = list(inspect.signature(fn).parameters)
    assert params == ["ai", "hero", "view"], (
        f"handle_idle signature drifted from (ai, hero, view): {params}"
    )


# ---------------------------------------------------------------------------
# 2. All 8 _idle_* step functions exist + are callable, each (ai, hero, view).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", _STEP_NAMES)
def test_idle_step_exists_and_callable(name):
    fn = getattr(exploration, name, None)
    assert fn is not None, f"ai.behaviors.exploration.{name} missing"
    assert callable(fn), f"ai.behaviors.exploration.{name} is not callable"
    params = list(inspect.signature(fn).parameters)
    assert params == ["ai", "hero", "view"], (
        f"{name} signature drifted from (ai, hero, view): {params}"
    )


# ---------------------------------------------------------------------------
# 3. _IDLE_STEPS is a tuple/list of EXACTLY those 8 functions in order.
# ---------------------------------------------------------------------------

def test_idle_steps_is_the_eight_in_order():
    steps = getattr(exploration, "_IDLE_STEPS", None)
    assert steps is not None, "ai.behaviors.exploration._IDLE_STEPS missing"
    assert isinstance(steps, (tuple, list)), (
        f"_IDLE_STEPS must be a tuple/list, got {type(steps).__name__}"
    )
    assert len(steps) == 8, f"_IDLE_STEPS must hold exactly 8 steps, got {len(steps)}"

    # Each entry must be the SAME function object as the documented module-level
    # step, in the documented order.
    expected = tuple(getattr(exploration, n) for n in _STEP_NAMES)
    assert tuple(steps) == expected, (
        "_IDLE_STEPS is not the documented 8 step functions in order.\n"
        f"got names:      {[getattr(s, '__name__', repr(s)) for s in steps]}\n"
        f"expected names: {list(_STEP_NAMES)}"
    )


# ---------------------------------------------------------------------------
# Spy harness: build N spies, each recording its call order onto a shared list,
# returning a configurable bool. Patch _IDLE_STEPS with them so the driver runs
# the spies (handle_idle iterates the tuple object, so replacing it is the seam).
# ---------------------------------------------------------------------------

def _make_spies(return_flags, call_log, captured):
    """One spy per flag; records (index, ai, hero, view) and returns the flag."""
    spies = []
    for i, flag in enumerate(return_flags):
        def spy(ai, hero, view, _i=i, _flag=flag):
            call_log.append(_i)
            captured.append((_i, ai, hero, view))
            return _flag
        spies.append(spy)
    return tuple(spies)


# ---------------------------------------------------------------------------
# 4. DRIVER SHORT-CIRCUIT: a step returns True -> driver stops there; earlier
#    steps ran (in order), that step ran, LATER steps did NOT run.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("true_at", [0, 1, 3, 4, 6, 7])
def test_driver_short_circuits_on_first_true(monkeypatch, true_at):
    call_log: list[int] = []
    captured: list = []
    flags = [i == true_at for i in range(8)]  # exactly one True, at true_at
    spies = _make_spies(flags, call_log, captured)
    monkeypatch.setattr(exploration, "_IDLE_STEPS", spies)

    ai, hero, view = _fake_avh()
    result = exploration.handle_idle(ai, hero, view)

    # Driver returns None (handle_idle -> None on short-circuit).
    assert result is None, f"handle_idle returned {result!r}, expected None"

    # Ran steps 0..true_at inclusive, IN ORDER, and stopped — no later steps.
    assert call_log == list(range(true_at + 1)), (
        f"short-circuit at step {true_at}: ran {call_log}, "
        f"expected {list(range(true_at + 1))} (later steps must NOT run)"
    )

    # The (ai, hero, view) forwarded to each invoked spy is the SAME triple.
    for idx, got_ai, got_hero, got_view in captured:
        assert got_ai is ai, f"step {idx} got a different ai"
        assert got_hero is hero, f"step {idx} got a different hero"
        assert got_view is view, f"step {idx} got a different view"


# ---------------------------------------------------------------------------
# 5. DRIVER FALL-THROUGH: ALL steps return False -> every step runs once, in
#    order, and handle_idle returns None (the original terminal fall-through).
# ---------------------------------------------------------------------------

def test_driver_falls_through_when_all_false(monkeypatch):
    call_log: list[int] = []
    captured: list = []
    flags = [False] * 8
    spies = _make_spies(flags, call_log, captured)
    monkeypatch.setattr(exploration, "_IDLE_STEPS", spies)

    ai, hero, view = _fake_avh()
    result = exploration.handle_idle(ai, hero, view)

    assert result is None, f"handle_idle returned {result!r}, expected None"

    # Every step ran EXACTLY once, in declared order 0..7.
    assert call_log == list(range(8)), (
        f"fall-through: ran {call_log}, expected every step once in order [0..7]"
    )
    assert len(captured) == 8, f"expected 8 spy invocations, got {len(captured)}"


# ---------------------------------------------------------------------------
# Sanity: the LAST real step (_idle_patrol_zone) is the terminal fall-through —
# it is positioned last in _IDLE_STEPS. (The behavior that it always returns
# False is covered byte-identically by the WK67 digest; here we just pin its
# position so the driver's "no step returned True" path matches the original
# final no-return block.)
# ---------------------------------------------------------------------------

def test_patrol_zone_is_the_terminal_step():
    steps = exploration._IDLE_STEPS
    assert steps[-1] is exploration._idle_patrol_zone, (
        "_idle_patrol_zone must be the LAST step (the terminal fall-through that "
        f"mirrors the original final no-return block); got {steps[-1].__name__!r}"
    )
