"""
Mixer / volume control (WK79 extraction from audio_system.py).

Pure-move: functions take the owning AudioSystem as `audio` (self.->audio.);
behavior byte-identical to the prior AudioSystem methods.

WK7/V1.3: Volume control API (UI-only, non-authoritative). `_apply_ambient_volume`
lives here because it is the shared volume-scaling helper used by the master/music
setters (and by ambient playback).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.audio.audio_system import AudioSystem


def _apply_ambient_volume(audio: "AudioSystem"):
    """Apply master/music volume to ambient if playing."""
    if audio._ambient_sound is None or audio._ambient_channel is None:
        return
    try:
        final_volume = audio._ambient_base_volume * audio._master_volume * audio._music_volume
        audio._ambient_sound.set_volume(max(0.0, min(1.0, final_volume)))
    except Exception:
        # Failed to update; no-op (audio should never crash sim)
        pass


def set_master_volume(audio: "AudioSystem", volume_0_to_1: float):
    """
    Set master volume (affects all SFX and ambient).

    WK7: This is the API surface for ESC menu → Audio page.
    Volume is UI-only state and never affects simulation.

    Args:
        volume_0_to_1: Master volume from 0.0 (mute) to 1.0 (full volume)
                       UI should convert 0-100% slider to 0.0-1.0 range
    """
    # Clamp to valid range
    audio._master_volume = max(0.0, min(1.0, float(volume_0_to_1)))

    # Update ambient volume if playing
    _apply_ambient_volume(audio)


def get_master_volume(audio: "AudioSystem") -> float:
    """
    Get current master volume.

    WK7: This is the API surface for ESC menu → Audio page.

    Returns:
        Master volume from 0.0 (mute) to 1.0 (full volume)
        UI should convert to 0-100% for display
    """
    return audio._master_volume


def set_music_volume(audio: "AudioSystem", volume_0_to_1: float):
    """
    Set music/ambient volume (affects ambient only).

    Args:
        volume_0_to_1: Music volume from 0.0 (mute) to 1.0 (full volume)
                       UI should convert 0-100% slider to 0.0-1.0 range
    """
    audio._music_volume = max(0.0, min(1.0, float(volume_0_to_1)))
    _apply_ambient_volume(audio)


def get_music_volume(audio: "AudioSystem") -> float:
    """Get current music/ambient volume."""
    return audio._music_volume


def set_sfx_volume(audio: "AudioSystem", volume_0_to_1: float):
    """
    Set SFX volume (affects SFX only).

    Args:
        volume_0_to_1: SFX volume from 0.0 (mute) to 1.0 (full volume)
                       UI should convert 0-100% slider to 0.0-1.0 range
    """
    audio._sfx_volume = max(0.0, min(1.0, float(volume_0_to_1)))


def get_sfx_volume(audio: "AudioSystem") -> float:
    """Get current SFX volume."""
    return audio._sfx_volume
