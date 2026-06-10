"""WK129 BUG 1 — audio regression after the Mythos perf sprint (76e055e..c8ac350).

ROOT CAUSE (the only audio-behavior change in the whole sprint range — the
Mythos suspects were all exonerated by end-to-end probes, see the sprint
report): WK125's pause-frozen sim clock silently rebased the AudioSystem's
cooldown clock. Pre-sprint, shipped (non-deterministic) play published
``set_sim_now_ms(None)`` every tick, so ``AudioSystem.on_event``'s
``now_ms()`` fell back to ``pygame.time.get_ticks()`` (REAL wall clock).
Post-WK125, ``now_ms()`` is the pause-frozen sim accumulator:

* whenever the sim clock is frozen/stalled (menu pause, speed-0 pause, any
  sim freeze), ``now - last_play`` stays < cooldown forever, so every sound
  key plays at most ONCE and then ALL audio is muted;
* at NORMAL speed (multiplier 0.5) every audio cooldown silently doubled.

FIX: ``AudioSystem.on_event`` and ``ambient.update_enemy_ambient`` stamp
cooldowns from ``pygame.time.get_ticks()`` again (audio is non-authoritative
presentation; it never feeds the sim or the WK67 digest).

This module also pins the per-frame audio DISPATCH path under the DEFAULT
env (Mythos scene-ignore ON, instancing ON): engine tick -> _finalize_update
-> _flush_event_bus -> EventBus -> AudioSystem.on_event -> sfx playback, with
the mixer spied (no sound device needed), plus the scene-ignore guard
invariant that protects any future per-frame driver entity from pruning.
"""
from __future__ import annotations

import os

import pytest

# Headless SDL drivers BEFORE pygame/engine import. The DEFAULT Mythos env is
# preserved: KINGDOM_SCENE_IGNORE / KINGDOM_URSINA_INSTANCING stay unset.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game.audio import sfx_cache  # noqa: E402
from game.audio.audio_system import AudioSystem  # noqa: E402


@pytest.fixture()
def play_spy(monkeypatch):
    """Spy the mixer-level playback seam (sfx_cache.play_sfx) — no device needed."""
    calls: list[str] = []

    def _spy(audio, sound_key, volume=1.0):
        calls.append(str(sound_key))

    monkeypatch.setattr(sfx_cache, "play_sfx", _spy)
    return calls


def _engine_ursina_flags():
    """Build a GameEngine with the exact flags UrsinaApp uses (audio ACTIVE)."""
    pygame.init()
    from game.engine import GameEngine

    eng = GameEngine(headless=False, headless_ui=True)
    eng._ursina_viewer = False  # avoid ursina imports in tick_simulation
    return eng


# ---------------------------------------------------------------------------
# 1. Per-frame dispatch path reached under the DEFAULT env.
# ---------------------------------------------------------------------------
def test_per_frame_audio_path_reached_under_default_env(play_spy):
    from game.graphics.ursina_scene_ignore import scene_ignore_enabled

    # The default env: Mythos scene-ignore pruning ON (the prime suspect) —
    # the audio path must still be reached with it enabled.
    assert scene_ignore_enabled() is True

    eng = _engine_ursina_flags()
    try:
        assert eng.audio_system is not None and eng.audio_system.enabled

        # Audio must be subscribed on the engine event bus ('*' wildcard).
        subs = getattr(eng.event_bus, "_subscribers", [])
        assert any(
            t == "*" and getattr(cb, "__self__", None) is eng.audio_system
            for t, cb in subs
        ), "AudioSystem.on_event is not subscribed on the engine EventBus"

        on_event_hits = []
        orig_on_event = eng.audio_system.on_event
        eng.audio_system.on_event = lambda ev: (on_event_hits.append(ev.get("type")), orig_on_event(ev))[1]
        # Re-point the bus subscription at the wrapped method.
        eng.event_bus._subscribers = [
            (t, (eng.audio_system.on_event if (t == "*" and getattr(cb, "__self__", None) is eng.audio_system) else cb))
            for t, cb in subs
        ]

        # Emit a mapped world event at the castle (explored ground) + a UI event,
        # then run the per-frame loop exactly like the Ursina app does.
        castle = next(
            b for b in eng.buildings if getattr(b, "building_type", None) == "castle"
        )
        for _ in range(40):  # advance sim time past every cooldown first
            eng.tick_simulation(0.05)
        eng.event_bus.emit(
            {"type": "building_placed", "x": float(castle.center_x), "y": float(castle.center_y)}
        )
        eng.event_bus.emit({"type": "ui_click"})
        for _ in range(10):
            eng.tick_simulation(0.05)

        assert "building_placed" in on_event_hits, "on_event never reached for a world event"
        assert "ui_click" in on_event_hits, "on_event never reached for a UI event"
        assert "building_place" in play_spy, "world SFX never reached the mixer seam"
        assert "ui_click" in play_spy, "UI SFX never reached the mixer seam"
    finally:
        eng.running = False


# ---------------------------------------------------------------------------
# 2. THE regression: a frozen sim clock must NOT mute audio (wall-clock
#    cooldowns — pre-sprint shipped behavior). FAILS pre-fix, PASSES post-fix.
# ---------------------------------------------------------------------------
def test_frozen_sim_clock_does_not_mute_audio(play_spy, monkeypatch):
    from game.sim import timebase

    audio = AudioSystem(enabled=True)
    if not audio.enabled:
        pytest.skip("mixer unavailable even with dummy driver")

    # Freeze the sim clock (what pause / speed-0 / any sim stall does).
    timebase.set_sim_now_ms(123_456)
    try:
        # Control the wall clock so the test is deterministic.
        t = {"ms": 50_000}
        monkeypatch.setattr(pygame.time, "get_ticks", lambda: t["ms"])

        audio.on_event({"type": "ui_click"})
        assert play_spy == ["ui_click"], "first click must play"

        # 500ms of REAL time passes; the sim clock stays frozen.
        t["ms"] += 500
        audio.on_event({"type": "ui_click"})
        assert play_spy == ["ui_click", "ui_click"], (
            "audio muted while the sim clock is frozen — cooldowns are stamped "
            "from the pause-frozen sim clock instead of the wall clock "
            "(WK125 regression: ALL audio dies after one play per key)"
        )
    finally:
        timebase.set_sim_now_ms(None)


def test_enemy_ambient_scheduler_runs_on_wall_clock(monkeypatch):
    """update_enemy_ambient must schedule from get_ticks(), not the sim clock."""
    from types import SimpleNamespace

    from game.audio import ambient
    from game.sim import timebase

    audio = AudioSystem(enabled=False)  # no mixer needed; we spy the manager
    audio.enabled = True  # re-enable the gate (no pygame state touched below)

    seen = []

    class _MgrSpy:
        def update_ambient(self, enemies, now, cam_x, cam_y):
            seen.append(float(now))

        def cleanup_dead_cooldowns(self, alive):
            pass

    audio._enemy_sounds = _MgrSpy()

    timebase.set_sim_now_ms(777)  # frozen sim clock
    try:
        monkeypatch.setattr(pygame.time, "get_ticks", lambda: 42_000)
        enemy = SimpleNamespace(x=0.0, y=0.0, enemy_type="goblin", is_alive=True)
        audio.update_enemy_ambient([enemy])
        assert seen == [42_000.0], (
            f"enemy ambient scheduled from {seen} — expected the wall clock "
            "(42000), not the frozen sim clock (777)"
        )
    finally:
        timebase.set_sim_now_ms(None)


# ---------------------------------------------------------------------------
# 3. Scene-ignore guard invariant: the pruning can never flag an entity that
#    drives per-frame work (the audio-driver-exemption contract for S1).
# ---------------------------------------------------------------------------
def test_scene_ignore_never_flags_update_driving_entities():
    from game.graphics.ursina_scene_ignore import mark_scene_ignore

    class _Driver:
        ignore = False

        def update(self):  # a per-frame driver (e.g. anything audio-driving)
            pass

    class _InputSink:
        ignore = False

        def input(self, key):
            pass

    class _Plain:
        ignore = False
        update = None
        input = None
        on_click = None
        scripts = ()

    d, i, p = _Driver(), _InputSink(), _Plain()
    mark_scene_ignore(d)
    mark_scene_ignore(i)
    mark_scene_ignore(p)
    assert d.ignore is False, "S1 pruning flagged an update-driving entity"
    assert i.ignore is False, "S1 pruning flagged an input-driving entity"
    assert p.ignore is True, "S1 pruning must still flag plain render-only entities"
