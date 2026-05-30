"""Billboard clip/frame helpers for units (WK41 mechanical split)."""

from __future__ import annotations

import time

from game.graphics.animation import AnimationClip
from game.graphics.worker_sprites import WorkerSpriteLibrary

import config

# WK67 Round A-2 (Wave 5): the sim advances one ``_sim_tick_counter`` per fixed
# sim tick (``GameEngine._FIXED_SIM_DT`` seconds). Under DETERMINISTIC_SIM/capture
# we derive the within-clip anim clock from that tick id instead of wall-clock, so
# a given sim tick ALWAYS selects the same frame index → byte-reproducible captures.
# Keep this in sync with ``GameEngine._FIXED_SIM_DT`` (20 Hz sim rate).
_SIM_TICK_SECONDS = 1.0 / 20.0


def anim_clock_seconds(frame_tick_id: int) -> float:
    """Return the monotonic clock (seconds) the unit anim FSM uses for elapsed math.

    Single source of truth for the tick basis, shared by both unit renderers
    (``UrsinaRenderer._compute_anim_frame`` and
    ``InstancedUnitRenderer._resolve_unit_anim_clip_frame``) so they animate from
    the IDENTICAL clock.

    - Normal play: wall-clock ``time.perf_counter()`` (live animation stays smooth;
      this is the EXACT value the renderers used before WK67 Wave 5).
    - DETERMINISTIC_SIM/capture: ``frame_tick_id * _SIM_TICK_SECONDS`` — a
      deterministic, monotonically increasing sim time. The same sim tick yields the
      same elapsed within every clip, so dynamic captures are byte-reproducible.
    """
    if config.DETERMINISTIC_SIM:
        return float(int(frame_tick_id)) * _SIM_TICK_SECONDS
    return time.perf_counter()


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


# WK68 R2 (Agent 09): DTO-driven base-clip selection. Mirrors the per-type live-entity
# helpers above (_hero_base_clip / _enemy_base_clip / _guard_base_clip /
# _peasant_base_clip / _tax_collector_base_clip) byte-for-byte, but reads the frozen
# UnitDTO (state_name / is_inside_building / is_alive) instead of a live entity. ``dto.kind``
# routes to the matching branch; the worker kinds split on dto.kind (peasant/guard/tax).
def base_clip_from_dto(dto) -> str:
    kind = getattr(dto, "kind", "")
    state_name = str(getattr(dto, "state_name", "") or "")
    if kind == "hero":
        if bool(getattr(dto, "is_inside_building", False)):
            return "inside"
        if state_name in ("MOVING", "RETREATING"):
            return "walk"
        return "idle"
    if kind == "enemy":
        return "walk" if state_name == "MOVING" else "idle"
    if kind == "guard":
        if state_name == "DEAD":
            return "dead"
        if state_name == "ATTACKING":
            return "attack"
        if state_name == "MOVING":
            return "walk"
        return "idle"
    if kind == "tax_collector":
        if state_name == "COLLECTING":
            return "collect"
        if state_name == "RETURNING":
            return "return"
        if state_name == "MOVING_TO_GUILD":
            return "walk"
        if state_name == "RESTING_AT_CASTLE":
            return "rest"
        return "idle"
    # peasant / peasant_builder
    if not bool(getattr(dto, "is_alive", True)):
        return "dead"
    if state_name == "DEAD":
        return "dead"
    if state_name == "WORKING":
        return "work"
    if state_name == "MOVING":
        return "walk"
    return "idle"


def facing_from_dto(r, dto) -> int:
    """WK68 R2 (Agent 09): facing (1=right, -1=left) from a frozen UnitDTO.

    Port of the former ``ursina_units_anim._unit_facing_direction`` (the live-entity
    facing helper, deleted in WK80 once this DTO path fully replaced it) but reads
    the DTO (``target_x``/``x``) and keeps the movement-tracking scratch in a
    renderer-owned dict keyed by the stable ``entity_id`` — NOT stamped onto the
    live entity (which the renderer no longer holds). Same precedence: combat
    target wins, else last-x movement delta, else last known facing.
    """
    eid = getattr(dto, "entity_id", None)
    cur_x = float(getattr(dto, "x", 0.0))
    # 1) Combat target: face toward target.x when meaningfully offset.
    target_x = getattr(dto, "target_x", None)
    if target_x is not None:
        dx = float(target_x) - cur_x
        if abs(dx) > 0.01:
            return 1 if dx >= 0 else -1
    # 2) Movement-based facing (renderer-owned scratch keyed by entity_id).
    st = r._unit_facing_state.get(eid)
    last_x = st.get("last_x") if st is not None else None
    if last_x is not None:
        dx = cur_x - last_x
        if abs(dx) > 0.01:
            new_facing = 1 if dx >= 0 else -1
            r._unit_facing_state[eid] = {"facing": new_facing, "last_x": cur_x}
            return new_facing
    # 3) No movement this frame: record current x, keep last known facing.
    prev_facing = st.get("facing", 1) if st is not None else 1
    r._unit_facing_state[eid] = {"facing": prev_facing, "last_x": cur_x}
    return prev_facing


def compute_anim_frame(r, obj_id, entity, unit_type: str, class_key: str, base_clip_fn=None) -> tuple:
    """Compute current animation clip name and frame index.

    The within-clip elapsed uses :func:`anim_clock_seconds` — wall-clock
    ``perf_counter`` in normal play, sim-tick-derived under DETERMINISTIC_SIM
    (WK67 Wave 5) so dynamic-scene captures are byte-reproducible.
    """
    # WK66 Move 1a: read the one-shot trigger + the sim's monotonic
    # anim_trigger_seq and play when the seq advances vs our renderer-owned
    # last-seen value, instead of clearing the trigger on the entity. The
    # renderer no longer writes _ursina_anim_trigger/_render_anim_trigger back.
    # WK68 R2 (Agent 09): ``entity`` is now a frozen UnitDTO. The DTO carries
    # ``anim_trigger``/``anim_trigger_seq`` (the live entity exposed
    # ``_render_anim_trigger``/``_ursina_anim_trigger``/``_anim_trigger_seq``);
    # read the DTO names first, falling back to the legacy entity attrs so any
    # non-DTO caller still works.
    trigger = (
        getattr(entity, "anim_trigger", None)
        or getattr(entity, "_ursina_anim_trigger", None)
        or getattr(entity, "_render_anim_trigger", None)
    )
    trigger_seq = int(
        getattr(entity, "anim_trigger_seq", None)
        if getattr(entity, "anim_trigger_seq", None) is not None
        else getattr(entity, "_anim_trigger_seq", 0) or 0
    )

    # WK68 R2 (Agent 09): base clip from the DTO (default path); legacy callers
    # may still pass a base_clip_fn that reads a live entity.
    base = base_clip_fn(entity) if base_clip_fn is not None else base_clip_from_dto(entity)
    st = r._unit_anim_state.get(obj_id)
    # WK67 Wave 5: under DETERMINISTIC_SIM/capture this is sim-tick-derived
    # (byte-reproducible); otherwise wall-clock perf_counter (live play unchanged).
    now = anim_clock_seconds(getattr(r, "_frame_tick_id", 0))
    last_seq = st.get("last_seq", -1) if st is not None else -1

    if trigger and trigger_seq != last_seq:
        tname = str(trigger)
        clips = r._get_cached_clips(unit_type, class_key)
        if tname in clips:
            r._unit_anim_state[obj_id] = {
                "clip": tname,
                "t0": now,
                "base": base,
                "oneshot": not clips[tname].loop,
                "last_seq": trigger_seq,
            }
            st = r._unit_anim_state[obj_id]
        elif st is not None:
            # Unknown clip name: still record the seq so we don't re-evaluate it.
            st["last_seq"] = trigger_seq

    if st is None:
        r._unit_anim_state[obj_id] = {
            "clip": base, "t0": now, "base": base, "oneshot": False,
            "last_seq": trigger_seq,
        }
        st = r._unit_anim_state[obj_id]
    else:
        st["base"] = base
        if st.get("oneshot"):
            clips = r._get_cached_clips(unit_type, class_key)
            oc = clips.get(st["clip"])
            if oc:
                elapsed_done = now - st["t0"]
                _i, finished = _frame_index_for_clip(oc, elapsed_done)
                if finished:
                    st["clip"] = base
                    st["t0"] = now
                    st["oneshot"] = False
        if not st.get("oneshot"):
            if st["clip"] != base:
                st["clip"] = base
                st["t0"] = now

    clip_name = st["clip"]
    clips = r._get_cached_clips(unit_type, class_key)
    clip = clips.get(clip_name)
    if clip is None:
        return base, 0
    elapsed = now - st["t0"]
    idx, _fin = _frame_index_for_clip(clip, elapsed)
    return clip_name, idx
