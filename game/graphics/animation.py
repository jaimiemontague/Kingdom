from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pygame


@dataclass(frozen=True)
class AnimationClip:
    frames: List[pygame.Surface]
    frame_time_sec: float = 0.1
    loop: bool = True

    def __post_init__(self):
        if not self.frames:
            raise ValueError("AnimationClip requires at least one frame")
        if self.frame_time_sec <= 0:
            raise ValueError("frame_time_sec must be > 0")


class AnimationPlayer:
    """
    Simple time-based animation player.

    - Call play(name) to switch clips
    - Call update(dt) once per tick
    - Call frame() to get current Surface
    """

    def __init__(self, clips: Dict[str, AnimationClip], initial: str):
        if initial not in clips:
            raise KeyError(f"Initial clip '{initial}' not in clips")
        self._clips = clips
        self._current_name = initial
        self._t = 0.0
        self._idx = 0
        self._finished = False

    @property
    def current(self) -> str:
        return self._current_name

    @property
    def finished(self) -> bool:
        return self._finished

    def play(self, name: str, restart: bool = False):
        if name not in self._clips:
            return
        if (not restart) and name == self._current_name:
            return
        self._current_name = name
        self._t = 0.0
        self._idx = 0
        self._finished = False

    def update(self, dt: float):
        clip = self._clips[self._current_name]
        if self._finished:
            return

        self._t += float(dt)
        while self._t >= clip.frame_time_sec and not self._finished:
            self._t -= clip.frame_time_sec
            self._idx += 1
            if self._idx >= len(clip.frames):
                if clip.loop:
                    self._idx = 0
                else:
                    self._idx = len(clip.frames) - 1
                    self._finished = True

    def frame(self) -> pygame.Surface:
        clip = self._clips[self._current_name]
        return clip.frames[self._idx]


def load_png_frames(folder: str | Path, scale_to: Optional[tuple[int, int]] = None) -> List[pygame.Surface]:
    """
    Load all PNGs in a folder, sorted by filename.
    Returns [] if folder doesn't exist or contains no pngs.
    """
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        return []

    files = sorted([f for f in p.iterdir() if f.is_file() and f.suffix.lower() == ".png"])
    frames: List[pygame.Surface] = []
    for f in files:
        img = pygame.image.load(str(f)).convert_alpha()
        if scale_to is not None:
            img = pygame.transform.smoothscale(img, scale_to)
        frames.append(img)
    return frames





