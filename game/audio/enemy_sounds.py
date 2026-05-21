"""
Enemy-type-specific audio subsystem (WK61-FEAT-002).

Maps each enemy type to distinct attack, death, and ambient sounds.
Manages ambient sound cooldowns per enemy and caps simultaneous enemy sounds.

Non-authoritative: never affects simulation state. All sound playback
fails silently if files are missing or mixer is unavailable.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING, Dict, Optional

import pygame

from game.paths import ASSETS_DIR

if TYPE_CHECKING:
    from game.audio.audio_system import AudioSystem

# ---------------------------------------------------------------------------
# Enemy type -> sound keys mapping
# All files live flat in assets/audio/sfx/ as <enemy_type>_<action>.ogg
# ---------------------------------------------------------------------------
ENEMY_SOUND_MAP: Dict[str, Dict[str, str]] = {
    "goblin": {
        "attack": "goblin_attack",
        "death": "goblin_death",
        "ambient": "goblin_ambient",
    },
    "wolf": {
        "attack": "wolf_attack",
        "death": "wolf_death",
        "ambient": "wolf_ambient",
    },
    "skeleton": {
        "attack": "skeleton_attack",
        "death": "skeleton_death",
        "ambient": "skeleton_ambient",
    },
    "skeleton_archer": {
        "attack": "skeleton_attack",   # shares skeleton attack sound
        "death": "skeleton_death",     # shares skeleton death sound
        "ambient": "skeleton_ambient", # shares skeleton ambient sound
    },
    "spider": {
        "attack": "spider_attack",
        "death": "spider_death",
        "ambient": "spider_ambient",
    },
    "bandit": {
        "attack": "bandit_attack",
        "death": "bandit_death",
        "ambient": "bandit_ambient",
    },
    "bandit_lord": {
        "attack": "bandit_attack",   # shares bandit attack sound
        "death": "bandit_death",     # shares bandit death sound
        "ambient": "bandit_ambient", # shares bandit ambient sound
    },
}

# Per-sound volume levels (mixed at combat tier: 0.7-0.85)
ENEMY_SOUND_VOLUMES: Dict[str, float] = {
    "attack": 0.80,
    "death": 0.75,
    "ambient": 0.35,  # low volume to avoid cacophony
}

# Ambient cooldown range (seconds) -- randomized per enemy instance
AMBIENT_COOLDOWN_MIN_S = 5.0
AMBIENT_COOLDOWN_MAX_S = 15.0

# Maximum simultaneous enemy sounds playing at once (prevents wall of noise)
MAX_SIMULTANEOUS_ENEMY_SOUNDS = 4

# Distance-based volume parameters (world pixel units)
# At MAX_AUDIBLE_DISTANCE, sound is fully muted.
# At 0 distance, sound is at full configured volume.
MAX_AUDIBLE_DISTANCE_PX = 1200.0  # ~37 tiles at 32px/tile


class EnemySoundManager:
    """
    Manages per-enemy-type sound playback with distance attenuation,
    ambient cooldowns, and a cap on simultaneous sounds.
    """

    def __init__(self, audio_system: "AudioSystem"):
        self._audio = audio_system
        self._sound_cache: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self._ambient_cooldowns: Dict[int, float] = {}  # enemy_id -> next_ambient_time_ms
        self._active_channels: list[pygame.mixer.Channel] = []
        self._enabled = audio_system.enabled
        if self._enabled:
            self._load_enemy_sounds()

    def _load_enemy_sounds(self) -> None:
        """Pre-load all enemy sound files from assets/audio/sfx/."""
        sfx_dir = ASSETS_DIR / "audio" / "sfx"
        if not sfx_dir.exists():
            return

        # Collect unique sound keys
        all_keys: set[str] = set()
        for sounds in ENEMY_SOUND_MAP.values():
            all_keys.update(sounds.values())

        for sound_key in all_keys:
            ogg_file = sfx_dir / f"{sound_key}.ogg"
            wav_file = sfx_dir / f"{sound_key}.wav"
            sound_file = None
            if ogg_file.exists():
                sound_file = ogg_file
            elif wav_file.exists():
                sound_file = wav_file

            if sound_file:
                try:
                    self._sound_cache[sound_key] = pygame.mixer.Sound(str(sound_file))
                except Exception:
                    self._sound_cache[sound_key] = None
            else:
                self._sound_cache[sound_key] = None

    def _cleanup_finished_channels(self) -> None:
        """Remove channels that have finished playing."""
        self._active_channels = [
            ch for ch in self._active_channels
            if ch is not None and ch.get_busy()
        ]

    def _count_active(self) -> int:
        """Count currently playing enemy sound channels."""
        self._cleanup_finished_channels()
        return len(self._active_channels)

    def _distance_volume(
        self, enemy_x: float, enemy_y: float,
        camera_x: float, camera_y: float
    ) -> float:
        """
        Scale volume by distance from camera center.
        Returns 0.0 (silent) to 1.0 (full) based on distance.
        """
        dx = enemy_x - camera_x
        dy = enemy_y - camera_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist >= MAX_AUDIBLE_DISTANCE_PX:
            return 0.0
        return max(0.0, 1.0 - (dist / MAX_AUDIBLE_DISTANCE_PX))

    def _play_enemy_sound(
        self, sound_key: str, action: str,
        enemy_x: float, enemy_y: float,
        camera_x: float, camera_y: float
    ) -> None:
        """
        Play an enemy sound with distance attenuation and simultaneous cap.
        """
        if not self._enabled:
            return

        sound = self._sound_cache.get(sound_key)
        if sound is None:
            return

        # Check simultaneous cap
        if self._count_active() >= MAX_SIMULTANEOUS_ENEMY_SOUNDS:
            return

        # Distance-based volume
        dist_factor = self._distance_volume(
            enemy_x, enemy_y, camera_x, camera_y
        )
        if dist_factor <= 0.01:
            return  # too far away to hear

        base_vol = ENEMY_SOUND_VOLUMES.get(action, 0.7)
        master = self._audio._master_volume
        sfx = self._audio._sfx_volume
        final_volume = base_vol * dist_factor * master * sfx
        final_volume = max(0.0, min(1.0, final_volume))

        try:
            sound.set_volume(final_volume)
            channel = sound.play()
            if channel is not None:
                self._active_channels.append(channel)
        except Exception:
            pass

    def on_enemy_attack(
        self, enemy_type: str,
        enemy_x: float, enemy_y: float,
        camera_x: float, camera_y: float
    ) -> None:
        """
        Play attack sound for the given enemy type.
        Called when a hero attacks an enemy or an enemy attacks a target.
        """
        et = (enemy_type or "").lower().strip()
        sounds = ENEMY_SOUND_MAP.get(et)
        if not sounds:
            return
        sound_key = sounds.get("attack")
        if sound_key:
            self._play_enemy_sound(
                sound_key, "attack",
                enemy_x, enemy_y, camera_x, camera_y
            )

    def on_enemy_death(
        self, enemy_type: str,
        enemy_x: float, enemy_y: float,
        camera_x: float, camera_y: float
    ) -> None:
        """
        Play death sound for the given enemy type.
        Called when an enemy is killed.
        """
        et = (enemy_type or "").lower().strip()
        sounds = ENEMY_SOUND_MAP.get(et)
        if not sounds:
            return
        sound_key = sounds.get("death")
        if sound_key:
            self._play_enemy_sound(
                sound_key, "death",
                enemy_x, enemy_y, camera_x, camera_y
            )

    def update_ambient(
        self,
        enemies: list,
        now_ms: float,
        camera_x: float,
        camera_y: float
    ) -> None:
        """
        Tick ambient sounds for living enemies. Each enemy has an individual
        random cooldown (5-15 seconds) to avoid a wall of noise.
        Called once per frame from the audio system update.

        Args:
            enemies: list of enemy objects (must have .x, .y, .enemy_type, .is_alive)
            now_ms: current sim time in milliseconds
            camera_x: camera world X
            camera_y: camera world Y
        """
        if not self._enabled:
            return

        for enemy in enemies:
            if not getattr(enemy, "is_alive", True):
                continue

            eid = id(enemy)
            et = getattr(enemy, "enemy_type", "")
            if isinstance(et, str):
                et = et.lower().strip()
            else:
                et = str(getattr(et, "value", et)).lower().strip()

            sounds = ENEMY_SOUND_MAP.get(et)
            if not sounds or "ambient" not in sounds:
                continue

            # Check individual cooldown
            next_time = self._ambient_cooldowns.get(eid, 0.0)
            if now_ms < next_time:
                continue

            # Set next cooldown (randomized)
            cooldown_s = random.uniform(AMBIENT_COOLDOWN_MIN_S, AMBIENT_COOLDOWN_MAX_S)
            self._ambient_cooldowns[eid] = now_ms + (cooldown_s * 1000.0)

            sound_key = sounds["ambient"]
            self._play_enemy_sound(
                sound_key, "ambient",
                getattr(enemy, "x", 0.0),
                getattr(enemy, "y", 0.0),
                camera_x, camera_y,
            )

    def cleanup_dead_cooldowns(self, alive_enemy_ids: set[int]) -> None:
        """Remove cooldown entries for enemies that no longer exist."""
        stale = [eid for eid in self._ambient_cooldowns if eid not in alive_enemy_ids]
        for eid in stale:
            del self._ambient_cooldowns[eid]
