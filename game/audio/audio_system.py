"""
Event-driven audio system (non-authoritative, pure consumer).

WK6: AudioSystem consumes events from simulation and plays sounds.
Never affects simulation state; safe to disable or fail.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Tuple
import pygame

# WK6: Canonical event name → sound key mapping (flat contract)
# This is the contract that Agent 14 and Agent 12 must align with.
# Uses flat keys: building_place, building_destroy, bounty_place, bow_release, ui_click
# Files are located at: assets/audio/sfx/{sound_key}.wav or .ogg
AUDIO_EVENT_MAP = {
    # Building events
    "building_placed": "building_place",
    "building_destroyed": "building_destroy",
    
    # Bounty events
    "bounty_placed": "bounty_place",
    
    # Combat events (ranged projectiles)
    "ranged_projectile": "bow_release",  # Default for all ranged projectiles
    
    # UI events (optional)
    "ui_click": "ui_click",
}

# Sound cooldowns (milliseconds) to prevent spam
# Agent 14 will provide final values; these are Build A defaults
SOUND_COOLDOWNS_MS = {
    "building_place": 200,
    "building_destroy": 500,
    "bounty_place": 200,
    "bow_release": 150,
    "ui_click": 100,
}


class AudioSystem:
    """
    Lightweight, non-authoritative audio system.
    
    Consumes events and plays sounds. Never affects simulation state.
    Safe to disable or fail gracefully.
    """
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._sfx_cache: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self._cooldowns: Dict[str, float] = {}  # sound_key -> last_play_time_ms
        self._ambient_channel: Optional[pygame.mixer.Channel] = None
        self._ambient_sound: Optional[pygame.mixer.Sound] = None
        
        if not self.enabled:
            return
        
        # Initialize pygame.mixer safely
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        except Exception:
            # Mixer init failed; disable audio
            self.enabled = False
            return
        
        # Preload SFX from assets/audio/sfx/
        self._load_sfx()
    
    def _load_sfx(self):
        """Preload all SFX files from assets/audio/sfx/ (flat structure, supports .wav and .ogg)."""
        if not self.enabled:
            return
        
        sfx_dir = self._assets_dir() / "sfx"
        if not sfx_dir.exists():
            # No audio assets yet; continue with no-op behavior
            return
        
        # Load sounds from flat paths (sfx/building_place.wav or .ogg, etc.)
        for event_name, sound_key in AUDIO_EVENT_MAP.items():
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
                    self._sfx_cache[sound_key] = pygame.mixer.Sound(str(sound_file))
                except Exception:
                    # File exists but failed to load; continue without this sound
                    self._sfx_cache[sound_key] = None
            else:
                # File missing; cache None (will be no-op on play)
                self._sfx_cache[sound_key] = None
    
    @staticmethod
    def _assets_dir() -> Path:
        """Get assets directory path."""
        return Path(__file__).resolve().parents[2] / "assets" / "audio"
    
    def emit_from_events(self, events: list[dict]):
        """
        Consume events and trigger sounds.
        
        Non-blocking: never crashes simulation.
        Respects cooldowns to prevent spam.
        """
        if not self.enabled:
            return
        
        if not events:
            return
        
        from game.sim.timebase import now_ms as sim_now_ms
        now_ms = float(sim_now_ms())
        
        for event in events:
            event_type = event.get("type")
            if not event_type:
                continue
            
            # Map event type to sound key (flat contract)
            sound_key = AUDIO_EVENT_MAP.get(event_type)
            if not sound_key:
                continue
            
            # Check cooldown
            cooldown_ms = SOUND_COOLDOWNS_MS.get(sound_key, 0)
            last_play = self._cooldowns.get(sound_key, 0.0)
            if (now_ms - last_play) < cooldown_ms:
                continue  # Still on cooldown
            
            # Play sound
            self.play_sfx(sound_key, volume=1.0)
            self._cooldowns[sound_key] = now_ms
    
    def play_sfx(self, sound_key: str, volume: float = 1.0):
        """
        Play a one-shot sound effect.
        
        Args:
            sound_key: Sound key (e.g., "building_place", "bow_release")
            volume: Volume 0.0 to 1.0
        """
        if not self.enabled:
            return
        
        sound = self._sfx_cache.get(sound_key)
        if sound is None:
            # Sound not loaded or missing; no-op
            return
        
        try:
            sound.set_volume(float(volume))
            sound.play()
        except Exception:
            # Playback failed; no-op (audio should never crash sim)
            pass
    
    def set_ambient(self, track_name: str = "ambient_loop", volume: float = 0.4):
        """
        Play/loop an ambient track.
        
        Args:
            track_name: Track filename (without extension), default "ambient_loop" for Build A
            volume: Volume 0.0 to 1.0, default 0.4 for Build A (cozy/peaceful tone)
        """
        if not self.enabled:
            return
        
        # Stop current ambient if playing
        self.stop_ambient()
        
        ambient_dir = self._assets_dir() / "ambient"
        # Try .ogg first, then .wav
        track_file = ambient_dir / f"{track_name}.ogg"
        if not track_file.exists():
            track_file = ambient_dir / f"{track_name}.wav"
        
        if not track_file.exists():
            return
        
        try:
            self._ambient_sound = pygame.mixer.Sound(str(track_file))
            self._ambient_sound.set_volume(float(volume))
            # Loop ambient (loops=-1 means infinite loop)
            self._ambient_channel = self._ambient_sound.play(loops=-1)
        except Exception:
            # Failed to load/play; no-op
            self._ambient_sound = None
            self._ambient_channel = None
    
    def stop_ambient(self):
        """Stop ambient playback."""
        if not self.enabled:
            return
        
        if self._ambient_channel:
            try:
                self._ambient_channel.stop()
            except Exception:
                pass
        self._ambient_channel = None
        self._ambient_sound = None

