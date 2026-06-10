"""Mythos S1 (`scene-entities-ignore`): take renderer-managed entities out of
Ursina's per-frame update/input walks.

Ursina's ``_update`` task iterates ALL ``scene.entities`` every frame (removal
membership test + ``.enabled`` property + ``has_disabled_ancestor`` parent-chain
walk + ``hasattr(update)`` + scripts loop, site-packages/ursina/main.py:196-220)
and re-runs the same walk for EVERY input event including held-key repeats
(main.py:286-317). Measured on this box: 1.3-5.3 ms/frame at the ~536-entity gate
scene, dropping to 0.09 ms with ``ignore=True`` — and the cost scales linearly
with entity count (a wall for the hundreds-of-enemies goal).

Kingdom's renderer-managed entities (unit billboards, overlay HP bars / name /
gold / Zzz labels, 3D buildings + prefab piece children, bounty/rubble props, the
fog quad, the HUD overlay quad, the terrain root, the status text) define no
``update()`` / ``input()`` / ``on_click`` and carry no scripts — they are driven
exclusively by the renderer's explicit per-frame sync calls, so the walk is pure
waste for them. Setting ``entity.ignore = True`` removes them from both walks
(main.py:199 / :287) while leaving everything else intact:

* rendering / ``enabled`` show-hide (ignore only affects the Python walks),
* ``animate_*`` tweens (ursina Sequences run from ``application.sequences``,
  main.py:189-190 — independent of the entity walk),
* analytic picking (game/graphics/ursina_pick.py — no colliders involved).

NOT flagged: ``EditorCamera`` and ursina's own window UI (``window.fps_counter``,
``window.exit_button``) — those DO consume update/input.

Env gate: ``KINGDOM_SCENE_IGNORE`` — default ON; set ``=0`` to restore stock
behavior (the fallback hatch, since this leans on Ursina internals).

Safety guard: :func:`mark_scene_ignore` refuses to flag an entity that defines
``update`` / ``input`` / ``on_click`` or carries ``scripts`` — such an entity
needs the walk. (Today no renderer-managed entity does; the guard protects
future additions per the candidate's "dev assert" requirement.)
"""
from __future__ import annotations

import os


def scene_ignore_enabled() -> bool:
    """True unless ``KINGDOM_SCENE_IGNORE=0`` (default ON)."""
    return os.environ.get("KINGDOM_SCENE_IGNORE", "1").strip() != "0"


def mark_scene_ignore(ent) -> None:
    """Set ``ent.ignore = True`` (skip Ursina's per-frame update/input walks) when safe.

    No-op when the env gate is off, *ent* is None, or *ent* defines update/input/
    on_click or has scripts (it would stop receiving them — never flag those).
    Never raises into a render path.
    """
    if ent is None or not scene_ignore_enabled():
        return
    try:
        if getattr(ent, "update", None) is not None:
            return
        if getattr(ent, "input", None) is not None:
            return
        if getattr(ent, "on_click", None) is not None:
            return
        if getattr(ent, "scripts", None):
            return
        ent.ignore = True
    except Exception:
        pass
