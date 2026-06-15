"""WK143 dragon audio cue wiring tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pytest

from game.audio import sfx_cache
from game.audio.audio_system import AudioSystem
from game.audio.contract import AUDIO_EVENT_MAP, SOUND_COOLDOWNS_MS
from game.world import Visibility


REPO_ROOT = Path(__file__).resolve().parents[1]
SFX_DIR = REPO_ROOT / "assets" / "audio" / "sfx"


def _make_audio() -> AudioSystem:
    audio = AudioSystem(enabled=False)
    audio._enemy_sounds = None
    return audio


def test_dragon_audio_contract_registers_and_materializes_cues():
    expected = {
        "boss_encounter_started": "dragon_roar",
        "boss_phase_changed": "dragon_phase",
        "boss_ability_telegraphed": "dragon_fire_telegraph",
        "boss_ability_resolved": "dragon_fire_impact",
    }

    manifest = json.loads((REPO_ROOT / "tools" / "assets_manifest.json").read_text(encoding="utf-8"))
    manifest_sfx = set(manifest.get("audio", {}).get("sfx", []))

    for event_type, sound_key in expected.items():
        assert AUDIO_EVENT_MAP[event_type] == sound_key
        assert SOUND_COOLDOWNS_MS[sound_key] > 0
        assert sound_key in manifest_sfx
        assert (SFX_DIR / f"{sound_key}.ogg").is_file()


def test_dragon_boss_events_route_to_dragon_only_cues(monkeypatch: pytest.MonkeyPatch):
    audio = _make_audio()
    played: list[tuple[str, float]] = []

    def _spy(audio_system, sound_key, volume=1.0):
        played.append((str(sound_key), float(volume)))

    monkeypatch.setattr(sfx_cache, "play_sfx", _spy)

    dragon_events = [
        {"type": "boss_encounter_started", "boss_type": "dragon", "position": (64.0, 64.0)},
        {"type": "boss_phase_changed", "boss_type": "dragon", "position": (64.0, 64.0)},
        {
            "type": "boss_ability_telegraphed",
            "boss_type": "dragon",
            "warning_event": "dragon_fire_telegraph",
            "position": (64.0, 64.0),
        },
        {
            "type": "boss_ability_resolved",
            "boss_type": "dragon",
            "impact_event": "dragon_fire_impact",
            "position": (64.0, 64.0),
        },
    ]

    for now_ms, event in enumerate(dragon_events, start=1):
        audio._emit_single_event(event, now_ms * 2500)

    assert [sound_key for sound_key, _ in played] == [
        "dragon_roar",
        "dragon_phase",
        "dragon_fire_telegraph",
        "dragon_fire_impact",
    ]

    played.clear()
    for now_ms, event in enumerate(dragon_events, start=1):
        muted_event = dict(event, boss_type="bandit_lord")
        audio._emit_single_event(muted_event, now_ms * 2500 + 20_000)
    assert played == []


def test_dragon_boss_audio_respects_position_visibility_gating(monkeypatch: pytest.MonkeyPatch):
    audio = _make_audio()
    played: list[str] = []

    def _spy(audio_system, sound_key, volume=1.0):
        played.append(str(sound_key))

    monkeypatch.setattr(sfx_cache, "play_sfx", _spy)

    world = SimpleNamespace(
        width=3,
        height=3,
        visibility=[[Visibility.VISIBLE for _ in range(3)] for _ in range(3)],
    )
    world.visibility[1][1] = Visibility.UNSEEN
    world.world_to_grid = lambda _x, _y: (1, 1)
    audio._world = world

    unseen_event = {
        "type": "boss_encounter_started",
        "boss_type": "dragon",
        "position": (48.0, 48.0),
    }
    audio._emit_single_event(unseen_event, 1_000)
    assert played == []

    world.visibility[1][1] = Visibility.VISIBLE
    audio._emit_single_event(unseen_event, 4_000)
    assert played == ["dragon_roar"]

