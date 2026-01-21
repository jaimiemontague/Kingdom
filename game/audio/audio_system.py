"""
Event-driven audio system (non-authoritative, pure consumer).

WK6: AudioSystem consumes events from simulation and plays sounds.
Never affects simulation state; safe to disable or fail.

WK6 Mid-Sprint: Visibility-gated audio - only plays SFX if event is on-screen and Visibility.VISIBLE.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Tuple
import pygame

# WK6: Canonical event name → sound key mapping (flat contract)
# WK6 Mid-Sprint: Expanded to cover more real-world actions
# This is the contract that Agent 14 and Agent 12 must align with.
# Uses flat keys: building_place, building_destroy, bounty_place, bow_release, ui_click, etc.
# Files are located at: assets/audio/sfx/{sound_key}.wav or .ogg
AUDIO_EVENT_MAP = {
    # Building events
    "building_placed": "building_place",
    "building_destroyed": "building_destroy",
    
    # Combat events
    "hero_attack": "melee_hit",
    "ranged_projectile": "bow_release",
    "enemy_killed": "enemy_death",
    "lair_cleared": "lair_cleared",
    
    # Bounty events
    "bounty_placed": "bounty_place",
    "bounty_claimed": "bounty_claimed",
    
    # Economy/Shop events
    "hero_hired": "hero_hired",
    "purchase_made": "purchase",
    
    # UI events (optional, not visibility-gated)
    "ui_click": "ui_click",
    "ui_confirm": "ui_confirm",
    "ui_error": "ui_error",
}

# Sound cooldowns (milliseconds) to prevent spam
# Agent 14 will provide final values; these are Build A defaults
SOUND_COOLDOWNS_MS = {
    "building_place": 200,
    "building_destroy": 500,
    "bounty_place": 200,
    "bounty_claimed": 300,
    "bow_release": 150,
    "melee_hit": 100,
    "enemy_death": 200,
    "lair_cleared": 500,
    "hero_hired": 300,
    "purchase": 150,
    "ui_click": 100,
    "ui_confirm": 150,
    "ui_error": 200,
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
        self._ambient_base_volume: float = 0.4  # Base ambient volume (before master/music scaling)
        
        # WK7/V1.3: Volume controls (UI-only, non-authoritative)
        # Range: 0.0 to 1.0 (0.0 = mute, 1.0 = full volume)
        # Default: 0.8 (80% per PM decision)
        self._master_volume: float = 0.8
        self._music_volume: float = 1.0  # Ambient/music slider (multiplies master)
        self._sfx_volume: float = 1.0    # SFX slider (multiplies master)
        
        # WK6 Mid-Sprint: Viewport and world context for visibility gating
        self._camera_x: float = 0.0
        self._camera_y: float = 0.0
        self._zoom: float = 1.0
        self._window_width: int = 1920
        self._window_height: int = 1080
        self._world: Optional[object] = None  # World instance for visibility checks
        
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
    
    def set_listener_view(self, camera_x: float, camera_y: float, zoom: float, window_width: int, window_height: int, world: Optional[object] = None):
        """
        Update viewport context for visibility gating.
        
        Called each frame from engine to provide camera and world state.
        
        Args:
            camera_x: Camera world X position
            camera_y: Camera world Y position
            zoom: Current zoom level
            window_width: Window width in pixels
            window_height: Window height in pixels
            world: World instance for visibility checks (optional)
        """
        self._camera_x = float(camera_x)
        self._camera_y = float(camera_y)
        self._zoom = float(zoom) if zoom else 1.0
        self._window_width = int(window_width)
        self._window_height = int(window_height)
        self._world = world
    
    def _is_audible_world_event(self, event: dict) -> bool:
        """
        Check if a world event should be audible (on-screen + Visibility.VISIBLE).
        
        UI events (ui_click, etc.) are always audible (not gated by visibility).
        
        Args:
            event: Event dictionary
            
        Returns:
            True if event should produce sound, False otherwise
        """
        event_type = event.get("type", "")
        
        # UI events are always audible (not gated by world visibility)
        if event_type.startswith("ui_"):
            return True
        
        # Extract world position from event
        # Try x,y first, then from_x/from_y, then to_x/to_y
        world_x = event.get("x")
        world_y = event.get("y")
        
        if world_x is None or world_y is None:
            # Try from_x/from_y (for projectiles, use source position)
            world_x = event.get("from_x")
            world_y = event.get("from_y")
        
        if world_x is None or world_y is None:
            # Try to_x/to_y (for projectiles, use target position)
            world_x = event.get("to_x")
            world_y = event.get("to_y")
        
        if world_x is None or world_y is None:
            # No position found - default to audible (better to play than miss)
            return True
        
        world_x = float(world_x)
        world_y = float(world_y)
        
        # Check viewport: is position within camera view?
        view_w = max(1, int(self._window_width / self._zoom))
        view_h = max(1, int(self._window_height / self._zoom))
        
        # World position relative to camera
        rel_x = world_x - self._camera_x
        rel_y = world_y - self._camera_y
        
        # Check if within viewport bounds (with small margin for edge cases)
        margin = 50  # pixels margin for sounds near edge
        if rel_x < -margin or rel_x > view_w + margin:
            return False
        if rel_y < -margin or rel_y > view_h + margin:
            return False
        
        # Check fog-of-war visibility (if world is available)
        if self._world is not None:
            try:
                from game.world import Visibility
                if hasattr(self._world, "world_to_grid") and hasattr(self._world, "visibility"):
                    grid_x, grid_y = self._world.world_to_grid(world_x, world_y)
                    if 0 <= grid_x < self._world.width and 0 <= grid_y < self._world.height:
                        if self._world.visibility[grid_y][grid_x] != Visibility.VISIBLE:
                            return False
            except Exception:
                # If visibility check fails, default to audible (better to play than miss)
                pass
        
        return True
    
    def emit_from_events(self, events: list[dict]):
        """
        Consume events and trigger sounds.
        
        Non-blocking: never crashes simulation.
        Respects cooldowns to prevent spam.
        WK6 Mid-Sprint: Only plays world SFX if event is on-screen and Visibility.VISIBLE.
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
            
            # WK6 Mid-Sprint: Check visibility gating (viewport + fog-of-war)
            if not self._is_audible_world_event(event):
                continue  # Event is off-screen or not visible - skip sound
            
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
        
        WK7: Master volume is applied automatically (master_volume * volume).
        Volume changes are post-processing and do not affect simulation state.
        
        Args:
            sound_key: Sound key (e.g., "building_place", "bow_release")
            volume: Per-sound volume 0.0 to 1.0 (will be multiplied by master volume)
        """
        if not self.enabled:
            return
        
        sound = self._sfx_cache.get(sound_key)
        if sound is None:
            # Sound not loaded or missing; no-op
            return
        
        try:
            # WK7: Apply master volume (multiplies per-sound volume)
            final_volume = float(volume) * self._master_volume * self._sfx_volume
            sound.set_volume(max(0.0, min(1.0, final_volume)))  # Clamp to 0.0-1.0
            sound.play()
        except Exception:
            # Playback failed; no-op (audio should never crash sim)
            pass
    
    def set_ambient(self, track_name: str = "ambient_loop", volume: float = 0.4):
        """
        Play/loop an ambient track.
        
        WK7: Master volume is applied automatically (master_volume * volume).
        Volume changes are post-processing and do not affect simulation state.
        
        Args:
            track_name: Track filename (without extension), default "ambient_loop" for Build A
            volume: Per-track volume 0.0 to 1.0, default 0.4 for Build A (will be multiplied by master volume)
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
            # Store base ambient volume (before master/music scaling)
            self._ambient_base_volume = float(volume)
            # Loop ambient (loops=-1 means infinite loop)
            self._ambient_channel = self._ambient_sound.play(loops=-1)
            # Apply master/music scaling after channel is created
            self._apply_ambient_volume()
        except Exception:
            # Failed to load/play; no-op
            self._ambient_sound = None
            self._ambient_channel = None
            self._ambient_base_volume = 0.4  # Reset to default
    
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
    
    def _apply_ambient_volume(self):
        """Apply master/music volume to ambient if playing."""
        if self._ambient_sound is None or self._ambient_channel is None:
            return
        try:
            final_volume = self._ambient_base_volume * self._master_volume * self._music_volume
            self._ambient_sound.set_volume(max(0.0, min(1.0, final_volume)))
        except Exception:
            # Failed to update; no-op (audio should never crash sim)
            pass

    # WK7/V1.3: Volume control API (UI-only, non-authoritative)
    
    def set_master_volume(self, volume_0_to_1: float):
        """
        Set master volume (affects all SFX and ambient).
        
        WK7: This is the API surface for ESC menu → Audio page.
        Volume is UI-only state and never affects simulation.
        
        Args:
            volume_0_to_1: Master volume from 0.0 (mute) to 1.0 (full volume)
                           UI should convert 0-100% slider to 0.0-1.0 range
        """
        # Clamp to valid range
        self._master_volume = max(0.0, min(1.0, float(volume_0_to_1)))
        
        # Update ambient volume if playing
        self._apply_ambient_volume()
    
    def get_master_volume(self) -> float:
        """
        Get current master volume.
        
        WK7: This is the API surface for ESC menu → Audio page.
        
        Returns:
            Master volume from 0.0 (mute) to 1.0 (full volume)
            UI should convert to 0-100% for display
        """
        return self._master_volume

    def set_music_volume(self, volume_0_to_1: float):
        """
        Set music/ambient volume (affects ambient only).

        Args:
            volume_0_to_1: Music volume from 0.0 (mute) to 1.0 (full volume)
                           UI should convert 0-100% slider to 0.0-1.0 range
        """
        self._music_volume = max(0.0, min(1.0, float(volume_0_to_1)))
        self._apply_ambient_volume()

    def get_music_volume(self) -> float:
        """Get current music/ambient volume."""
        return self._music_volume

    def set_sfx_volume(self, volume_0_to_1: float):
        """
        Set SFX volume (affects SFX only).

        Args:
            volume_0_to_1: SFX volume from 0.0 (mute) to 1.0 (full volume)
                           UI should convert 0-100% slider to 0.0-1.0 range
        """
        self._sfx_volume = max(0.0, min(1.0, float(volume_0_to_1)))

    def get_sfx_volume(self) -> float:
        """Get current SFX volume."""
        return self._sfx_volume

