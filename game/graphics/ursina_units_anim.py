"""Billboard clip/frame helpers for units (WK41 mechanical split)."""

from __future__ import annotations

from game.graphics.animation import AnimationClip
from game.graphics.worker_sprites import WorkerSpriteLibrary

import config


def _frame_index_for_clip(clip: AnimationClip, elapsed: float) -> tuple[int, bool]:
    """Match ``AnimationPlayer`` timing: non-looping finishes after n frame-times."""
    n = len(clip.frames)
    ft = clip.frame_time_sec
    if n == 0:
        return 0, True
    if ft <= 0:
        return 0, False
    if clip.loop:
        cycle = n * ft
        if cycle <= 0:
            return 0, False
        t = elapsed % cycle
        idx = int(t / ft) % n
        return idx, False
    steps = int(elapsed / ft)
    if steps >= n:
        return n - 1, True
    return steps, False


def _hero_base_clip(hero) -> str:
    if bool(getattr(hero, "is_inside_building", False)):
        return "inside"
    state = getattr(hero, "state", None)
    state_name = str(getattr(state, "name", state))
    if state_name in ("MOVING", "RETREATING"):
        return "walk"
    return "idle"


def _enemy_base_clip(enemy) -> str:
    state = getattr(enemy, "state", None)
    state_name = str(getattr(state, "name", state))
    return "walk" if state_name == "MOVING" else "idle"


def _guard_base_clip(guard) -> str:
    """Locomotion clip for guards; must match WorkerRenderer guard mapping (game/graphics/renderers/worker_renderer.py)."""
    state = getattr(guard, "state", None)
    state_name = str(getattr(state, "name", state))
    if state_name == "DEAD":
        return "dead"
    if state_name == "ATTACKING":
        return "attack"
    if state_name == "MOVING":
        return "walk"
    return "idle"


def _peasant_base_clip(peasant) -> str:
    """Locomotion clip for peasants / builder peasants; must match WorkerRenderer peasant branch."""
    if not getattr(peasant, "is_alive", True):
        return "dead"
    state = getattr(peasant, "state", None)
    state_name = str(getattr(state, "name", state))
    if state_name == "DEAD":
        return "dead"
    if state_name == "WORKING":
        return "work"
    if state_name == "MOVING":
        return "walk"
    return "idle"


def _tax_collector_base_clip(tc) -> str:
    """Locomotion clip for tax collector; must match WorkerRenderer tax_collector branch."""
    state = getattr(tc, "state", None)
    state_name = str(getattr(state, "name", state))
    if state_name == "COLLECTING":
        return "collect"
    if state_name == "RETURNING":
        return "return"
    if state_name == "MOVING_TO_GUILD":
        return "walk"
    if state_name == "RESTING_AT_CASTLE":
        return "rest"
    return "idle"


def _worker_idle_surface(worker_type: str):
    wt = str(worker_type or "peasant").lower()
    sz = int(getattr(config, "UNIT_SPRITE_PIXELS", 32))
    clips = WorkerSpriteLibrary.clips_for(wt, size=sz)
    return clips["idle"].frames[0]
