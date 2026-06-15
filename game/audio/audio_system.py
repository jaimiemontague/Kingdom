"""
Event-driven audio system (non-authoritative, pure consumer).

WK6: AudioSystem consumes events from simulation and plays sounds.
Never affects simulation state; safe to disable or fail.

WK6 Mid-Sprint: Visibility-gated audio - only plays SFX if event is on-screen and in explored area.
WK61: Enemy-type-specific sounds (attack, death, ambient) via EnemySoundManager.
WK79: God-file split into the game/audio/ package (contract / sfx_cache / ambient /
mixer_volume). AudioSystem is now a thin facade: it keeps the event-dispatch core
(__init__, on_event, _emit_single_event, set_listener_view, _is_audible_world_event)
and a 1-line delegating wrapper for every moved method so call sites are unchanged.
"""
from __future__ import annotations

from typing import Dict, List, Optional
import pygame

from game.audio.contract import AUDIO_EVENT_MAP, SOUND_COOLDOWNS_MS


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
        self._music_volume: float = 0.0  # Ambient/music slider (multiplies master)
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

        # WK61: Enemy-type-specific sound manager
        self._enemy_sounds: Optional["EnemySoundManager"] = None
        try:
            from game.audio.enemy_sounds import EnemySoundManager
            self._enemy_sounds = EnemySoundManager(self)
        except Exception:
            pass  # Graceful degradation if enemy sounds module fails

    # --- SFX cache / loader / playback (game/audio/sfx_cache.py) ---------------

    def _load_sfx(self):
        from game.audio import sfx_cache
        return sfx_cache._load_sfx(self)

    @staticmethod
    def _assets_dir():
        from game.audio import sfx_cache
        return sfx_cache._assets_dir()

    def play_sfx(self, sound_key: str, volume: float = 1.0):
        from game.audio import sfx_cache
        return sfx_cache.play_sfx(self, sound_key, volume)

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
        Check if a world event should be audible based on fog-of-war exploration state.

        Only mutes events on truly unexplored (UNSEEN) tiles. Explored or visible
        tiles always play. UI events are always audible.

        The viewport check was removed because in Ursina (3D) mode the engine's 2D
        camera_x/y diverges from the actual 3D camera, causing false rejections.
        """
        event_type = event.get("type", "")

        if event_type.startswith("ui_"):
            return True

        if self._world is None:
            return True

        world_x = event.get("x")
        world_y = event.get("y")

        if world_x is None or world_y is None:
            world_x = event.get("from_x")
            world_y = event.get("from_y")

        if world_x is None or world_y is None:
            world_x = event.get("to_x")
            world_y = event.get("to_y")

        if world_x is None or world_y is None:
            position = event.get("position")
            if isinstance(position, (tuple, list)) and len(position) >= 2:
                world_x, world_y = position[0], position[1]

        if world_x is None or world_y is None:
            return True

        try:
            from game.world import Visibility
            if hasattr(self._world, "world_to_grid") and hasattr(self._world, "visibility"):
                grid_x, grid_y = self._world.world_to_grid(float(world_x), float(world_y))
                if 0 <= grid_x < self._world.width and 0 <= grid_y < self._world.height:
                    if self._world.visibility[grid_y][grid_x] == Visibility.UNSEEN:
                        return False
        except Exception:
            pass

        return True

    def on_event(self, event: dict):
        """
        EventBus subscriber callback for single event dispatch.

        WK129 audio-regression fix: cooldowns are stamped from the REAL wall
        clock (``pygame.time.get_ticks()``), the clock this system shipped on
        pre-WK125 (non-deterministic play published ``set_sim_now_ms(None)``,
        so ``now_ms()`` fell back to ``get_ticks()``). WK125 silently rebased
        ``now_ms()`` onto the pause-frozen sim clock, which broke audio:

        * a frozen/stalled sim clock (menu pause, speed-0 pause, any sim
          freeze) makes ``now - last_play`` permanently < cooldown, so every
          sound key plays at most ONCE and then ALL audio is muted;
        * at NORMAL speed (multiplier 0.5) every cooldown silently doubled.

        Audio is non-authoritative presentation (never feeds the sim or the
        WK67 digest), so real-time cooldowns are the correct timebase.
        """
        if not self.enabled:
            return
        self._emit_single_event(event, float(pygame.time.get_ticks()))

    def _emit_single_event(self, event: dict, now_ms: float):
        if not event:
            return

        event_type = event.get("type")
        if not event_type:
            return

        # Map event type to sound key (flat contract)
        sound_key = AUDIO_EVENT_MAP.get(event_type)
        if not sound_key:
            return

        boss_type = str(event.get("boss_type", "") or "").lower().strip()
        if event_type in {
            "boss_encounter_started",
            "boss_phase_changed",
            "boss_ability_telegraphed",
            "boss_ability_resolved",
        } and boss_type != "dragon":
            return

        # WK6 Mid-Sprint: Check visibility gating (viewport + fog-of-war)
        if not self._is_audible_world_event(event):
            return  # Event is off-screen or not visible - skip sound

        # Check cooldown
        cooldown_ms = SOUND_COOLDOWNS_MS.get(sound_key, 0)
        last_play = self._cooldowns.get(sound_key, 0.0)
        if (now_ms - last_play) < cooldown_ms:
            return  # Still on cooldown

        # Play sound
        self.play_sfx(sound_key, volume=1.0)
        self._cooldowns[sound_key] = now_ms

        # WK61: Dispatch enemy-type-specific sounds for combat events
        if self._enemy_sounds is not None:
            try:
                ex = float(event.get("x", 0.0) or 0.0)
                ey = float(event.get("y", 0.0) or 0.0)
                cam_x = self._camera_x
                cam_y = self._camera_y
                if event_type == "hero_attack":
                    enemy_type = event.get("target", "")
                    if enemy_type:
                        self._enemy_sounds.on_enemy_attack(
                            enemy_type, ex, ey, cam_x, cam_y
                        )
                elif event_type == "enemy_killed":
                    enemy_type = event.get("enemy", "")
                    if enemy_type:
                        self._enemy_sounds.on_enemy_death(
                            enemy_type, ex, ey, cam_x, cam_y
                        )
            except Exception:
                pass  # Never crash sim for audio

    # --- Ambient playback (game/audio/ambient.py) -----------------------------

    def set_ambient(self, track_name: str = "ambient_loop", volume: float = 0.4):
        from game.audio import ambient
        return ambient.set_ambient(self, track_name, volume)

    def stop_ambient(self):
        from game.audio import ambient
        return ambient.stop_ambient(self)

    def start_interior_ambient(self, building_type: str) -> None:
        from game.audio import ambient
        return ambient.start_interior_ambient(self, building_type)

    def stop_interior_ambient(self) -> None:
        from game.audio import ambient
        return ambient.stop_interior_ambient(self)

    def update_enemy_ambient(self, enemies: List) -> None:
        from game.audio import ambient
        return ambient.update_enemy_ambient(self, enemies)

    # --- Mixer / volume control (game/audio/mixer_volume.py) -------------------

    def _apply_ambient_volume(self):
        from game.audio import mixer_volume
        return mixer_volume._apply_ambient_volume(self)

    def set_master_volume(self, volume_0_to_1: float):
        from game.audio import mixer_volume
        return mixer_volume.set_master_volume(self, volume_0_to_1)

    def get_master_volume(self) -> float:
        from game.audio import mixer_volume
        return mixer_volume.get_master_volume(self)

    def set_music_volume(self, volume_0_to_1: float):
        from game.audio import mixer_volume
        return mixer_volume.set_music_volume(self, volume_0_to_1)

    def get_music_volume(self) -> float:
        from game.audio import mixer_volume
        return mixer_volume.get_music_volume(self)

    def set_sfx_volume(self, volume_0_to_1: float):
        from game.audio import mixer_volume
        return mixer_volume.set_sfx_volume(self, volume_0_to_1)

    def get_sfx_volume(self) -> float:
        from game.audio import mixer_volume
        return mixer_volume.get_sfx_volume(self)
