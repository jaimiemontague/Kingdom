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

# WK6: Canonical event name → sound file path mapping
# This is the contract that Agent 14 and Agent 12 must align with.
# Uses nested paths: sfx/build/place.wav, sfx/bounty/placed.wav, etc.
AUDIO_EVENT_MAP = {
    # Building events
    "building_placed": "sfx/build/place",
    "building_destroyed": "sfx/build/destroyed",
    
    # Bounty events
    "bounty_placed": "sfx/bounty/placed",
    
    # Combat events (ranged projectiles - handled specially in emit_from_events)
    # "ranged_projectile" is handled dynamically based on projectile_kind/source
    
    # UI events (optional)
    "ui_click": "sfx/ui/click",
}

# Sound cooldowns (milliseconds) to prevent spam
# Agent 14 will provide final values; these are Build A defaults
SOUND_COOLDOWNS_MS = {
    "sfx/build/place": 200,
    "sfx/build/destroyed": 500,
    "sfx/bounty/placed": 200,
    "sfx/weapons/ranger_shot": 150,
    "sfx/weapons/skeleton_archer_shot": 150,
    "sfx/ui/click": 100,
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
        """Preload all SFX files from assets/audio/sfx/ (nested structure)."""
        if not self.enabled:
            return
        
        sfx_dir = self._assets_dir() / "sfx"
        if not sfx_dir.exists():
            # No audio assets yet; continue with no-op behavior
            return
        
        # Load sounds from nested paths (sfx/build/place.wav, etc.)
        for event_name, sound_path in AUDIO_EVENT_MAP.items():
            # sound_path is like "sfx/build/place" (without extension)
            sound_file = self._assets_dir() / f"{sound_path}.wav"
            if sound_file.exists():
                try:
                    self._sfx_cache[sound_path] = pygame.mixer.Sound(str(sound_file))
                except Exception:
                    # File exists but failed to load; continue without this sound
                    self._sfx_cache[sound_path] = None
            else:
                # File missing; cache None (will be no-op on play)
                self._sfx_cache[sound_path] = None
        
        # Also preload weapon sounds (ranger_shot, skeleton_archer_shot)
        weapons_dir = sfx_dir / "weapons"
        if weapons_dir.exists():
            for weapon_file in ["ranger_shot.wav", "skeleton_archer_shot.wav"]:
                sound_path = f"sfx/weapons/{weapon_file[:-4]}"  # Remove .wav
                sound_file = weapons_dir / weapon_file
                if sound_file.exists():
                    try:
                        self._sfx_cache[sound_path] = pygame.mixer.Sound(str(sound_file))
                    except Exception:
                        self._sfx_cache[sound_path] = None
                else:
                    self._sfx_cache[sound_path] = None
    
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
            
            # Special handling for ranged_projectile (determine weapon sound)
            if event_type == "ranged_projectile":
                projectile_kind = event.get("projectile_kind", "arrow")
                # For Build A: use ranger_shot for arrows, skeleton_archer_shot if explicitly marked
                # Default to ranger_shot for arrows (Ranger, SkeletonArcher both use arrows)
                # Future: could inspect event source or projectile_kind to differentiate
                if projectile_kind == "arrow":
                    # Try to determine source from context (if available)
                    # For now, default to ranger_shot (can be refined in Build B)
                    sound_path = "sfx/weapons/ranger_shot"
                elif projectile_kind == "bolt":
                    # Ballista uses bolts; for Build A, use ranger_shot as fallback
                    sound_path = "sfx/weapons/ranger_shot"
                else:
                    sound_path = "sfx/weapons/ranger_shot"  # Default fallback
            else:
                # Map event type to sound path
                sound_path = AUDIO_EVENT_MAP.get(event_type)
                if not sound_path:
                    continue
            
            # Check cooldown
            cooldown_ms = SOUND_COOLDOWNS_MS.get(sound_path, 0)
            last_play = self._cooldowns.get(sound_path, 0.0)
            if (now_ms - last_play) < cooldown_ms:
                continue  # Still on cooldown
            
            # Play sound
            self.play_sfx(sound_path, volume=1.0)
            self._cooldowns[sound_path] = now_ms
    
    def play_sfx(self, sound_path: str, volume: float = 1.0):
        """
        Play a one-shot sound effect.
        
        Args:
            sound_path: Sound path (e.g., "sfx/build/place", "sfx/weapons/ranger_shot")
            volume: Volume 0.0 to 1.0
        """
        if not self.enabled:
            return
        
        sound = self._sfx_cache.get(sound_path)
        if sound is None:
            # Sound not loaded or missing; no-op
            return
        
        try:
            sound.set_volume(float(volume))
            sound.play()
        except Exception:
            # Playback failed; no-op (audio should never crash sim)
            pass
    
    def set_ambient(self, track_name: str = "day_loop", volume: float = 0.4):
        """
        Play/loop an ambient track.
        
        Args:
            track_name: Track filename (without extension), default "day_loop" for Build A
            volume: Volume 0.0 to 1.0, default 0.4 for Build A (cozy/peaceful tone)
        """
        if not self.enabled:
            return
        
        # Stop current ambient if playing
        self.stop_ambient()
        
        ambient_dir = self._assets_dir() / "ambient"
        track_file = ambient_dir / f"{track_name}.ogg"
        if not track_file.exists():
            # Try .wav as fallback
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

