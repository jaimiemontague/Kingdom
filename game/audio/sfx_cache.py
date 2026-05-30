"""
SFX cache + loader + playback (WK79 extraction from audio_system.py).

Pure-move: functions take the owning AudioSystem as `audio` (self.->audio.);
behavior byte-identical to the prior AudioSystem methods.
`_assets_dir` was a @staticmethod and is now a plain module function.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from game.paths import ASSETS_DIR
from game.audio.contract import AUDIO_EVENT_MAP

if TYPE_CHECKING:
    from game.audio.audio_system import AudioSystem


def _assets_dir():
    """Get assets directory path."""
    return ASSETS_DIR / "audio"


def _load_sfx(audio: "AudioSystem"):
    """Preload all SFX files from assets/audio/sfx/ (flat structure, supports .wav and .ogg).

    TODO (Audio Agent): Add assets/audio/sfx/poi_discovered.ogg — a brief discovery chime
    (short rising arpeggio or crystal chime, ~0.5s, for POI discovery notifications).
    """
    if not audio.enabled:
        return

    sfx_dir = _assets_dir() / "sfx"
    if not sfx_dir.exists():
        # No audio assets yet; continue with no-op behavior
        return

    # Load sounds from flat paths (sfx/building_place.wav or .ogg, etc.)
    # Include extra SFX keys not triggered by events (e.g. wk14 building_under_attack_rumble)
    all_keys = set(AUDIO_EVENT_MAP.values())
    for sound_key in all_keys:
        # Try .wav first, then .ogg
        wav_file = sfx_dir / f"{sound_key}.wav"
        ogg_file = sfx_dir / f"{sound_key}.ogg"

        sound_file = None
        if wav_file.exists():
            sound_file = wav_file
        elif ogg_file.exists():
            sound_file = ogg_file

        if sound_file:
            try:
                audio._sfx_cache[sound_key] = pygame.mixer.Sound(str(sound_file))
            except Exception:
                audio._sfx_cache[sound_key] = None
        else:
            audio._sfx_cache[sound_key] = None


def play_sfx(audio: "AudioSystem", sound_key: str, volume: float = 1.0):
    """
    Play a one-shot sound effect.

    WK7: Master volume is applied automatically (master_volume * volume).
    Volume changes are post-processing and do not affect simulation state.

    Args:
        sound_key: Sound key (e.g., "building_place", "bow_release")
        volume: Per-sound volume 0.0 to 1.0 (will be multiplied by master volume)
    """
    if not audio.enabled:
        return

    sound = audio._sfx_cache.get(sound_key)
    if sound is None:
        # Sound not loaded or missing; no-op
        return

    try:
        # WK7: Apply master volume (multiplies per-sound volume)
        final_volume = float(volume) * audio._master_volume * audio._sfx_volume
        sound.set_volume(max(0.0, min(1.0, final_volume)))  # Clamp to 0.0-1.0
        sound.play()
    except Exception:
        # Playback failed; no-op (audio should never crash sim)
        pass
