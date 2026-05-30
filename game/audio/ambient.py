"""
Ambient playback (WK79 extraction from audio_system.py).

Pure-move: functions take the owning AudioSystem as `audio` (self.->audio.);
behavior byte-identical to the prior AudioSystem methods.
"""
from __future__ import annotations

from typing import List, TYPE_CHECKING

import pygame

from game.audio import sfx_cache, mixer_volume

if TYPE_CHECKING:
    from game.audio.audio_system import AudioSystem


# wk14: Interior ambient (per-building-type loops when player is in interior view)
_INTERIOR_AMBIENT_MAP = {
    "inn": "ambient_inn",
    "marketplace": "ambient_marketplace",
    "warrior_guild": "ambient_warrior_guild",
    "ranger_guild": "ambient_interior_default",
    "rogue_guild": "ambient_interior_default",
    "wizard_guild": "ambient_interior_default",
    "blacksmith": "ambient_blacksmith",
    "temple_agrela": "ambient_temple",
    "temple_dauros": "ambient_temple",
    "temple_fervus": "ambient_temple",
    "temple_krypta": "ambient_temple",
    "temple_krolm": "ambient_temple",
    "temple_helia": "ambient_temple",
    "temple_lunord": "ambient_temple",
}


def set_ambient(audio: "AudioSystem", track_name: str = "ambient_loop", volume: float = 0.4):
    """
    Play/loop an ambient track.

    WK7: Master volume is applied automatically (master_volume * volume).
    Volume changes are post-processing and do not affect simulation state.

    Args:
        track_name: Track filename (without extension), default "ambient_loop" for Build A
        volume: Per-track volume 0.0 to 1.0, default 0.4 for Build A (will be multiplied by master volume)
    """
    if not audio.enabled:
        return

    # Stop current ambient if playing
    stop_ambient(audio)

    ambient_dir = sfx_cache._assets_dir() / "ambient"
    # Try .ogg first, then .wav
    track_file = ambient_dir / f"{track_name}.ogg"
    if not track_file.exists():
        track_file = ambient_dir / f"{track_name}.wav"

    if not track_file.exists():
        return

    try:
        audio._ambient_sound = pygame.mixer.Sound(str(track_file))
        # Store base ambient volume (before master/music scaling)
        audio._ambient_base_volume = float(volume)
        # Loop ambient (loops=-1 means infinite loop)
        audio._ambient_channel = audio._ambient_sound.play(loops=-1)
        # Apply master/music scaling after channel is created
        mixer_volume._apply_ambient_volume(audio)
    except Exception:
        # Failed to load/play; no-op
        audio._ambient_sound = None
        audio._ambient_channel = None
        audio._ambient_base_volume = 0.4  # Reset to default


def stop_ambient(audio: "AudioSystem"):
    """Stop ambient playback."""
    if not audio.enabled:
        return

    if audio._ambient_channel:
        try:
            audio._ambient_channel.stop()
        except Exception:
            pass
    audio._ambient_channel = None
    audio._ambient_sound = None


def start_interior_ambient(audio: "AudioSystem", building_type: str) -> None:
    """
    Start interior ambient loop for the given building type (wk14).
    If the track file does not exist, fails silently (non-authoritative).
    """
    if not audio.enabled:
        return
    bt = (building_type or "").lower().strip()
    track_name = _INTERIOR_AMBIENT_MAP.get(bt, "ambient_interior_default")
    set_ambient(audio, track_name, volume=0.35)


def stop_interior_ambient(audio: "AudioSystem") -> None:
    """
    Restore outdoor ambient loop after exiting interior view (wk14).
    """
    if not audio.enabled:
        return
    set_ambient(audio, "ambient_loop", volume=0.4)


def update_enemy_ambient(audio: "AudioSystem", enemies: List) -> None:
    """
    Tick ambient sounds for living enemies. Called once per frame.

    Each enemy type plays a distinct ambient sound on a random cooldown
    (5-15s per enemy) to avoid cacophony. Distance-based volume
    attenuation and a simultaneous sound cap (4) are applied.

    Non-authoritative: safe to skip or call with an empty list.

    Args:
        enemies: list of enemy objects (with .x, .y, .enemy_type, .is_alive attrs)
    """
    if not audio.enabled or audio._enemy_sounds is None:
        return
    if not enemies:
        return

    try:
        from game.sim.timebase import now_ms as sim_now_ms
        now = float(sim_now_ms())
        audio._enemy_sounds.update_ambient(
            enemies, now,
            audio._camera_x, audio._camera_y,
        )
        # Periodically clean up cooldowns for dead/despawned enemies
        alive_ids = {id(e) for e in enemies if getattr(e, "is_alive", True)}
        audio._enemy_sounds.cleanup_dead_cooldowns(alive_ids)
    except Exception:
        pass  # Non-authoritative: never crash sim
