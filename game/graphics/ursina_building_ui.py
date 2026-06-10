"""Tax-overlay public API + building world-space UI (extracted WK87 from ursina_renderer).

This module owns the building-UI cluster that used to live at module level in
``game/graphics/ursina_renderer.py``: the hold-G tax-gold overlay public API
(``set_tax_gold_overlay_held``/``is_tax_gold_overlay_held``),
``building_tax_overlay_snapshot``, the overlay-Y helpers
(``_building_gold_overlay_y``/``_building_gold_overlay_world_y``),
``_sync_building_worldspace_ui``, ``_maybe_log_tax_overlay_debug``, and the
``_debug_tax_overlay``/``_tax_overlay_debug_last_print`` debug state.

WK87 is a PURE MOVE: the functions are byte-for-byte identical in logic and take
``ent``/``b``/``world``/``buildings`` params (no renderer-instance state), so they
relocate cleanly. ``ursina_renderer`` re-exports the public names for back-compat
and imports ``_sync_building_worldspace_ui``/``_maybe_log_tax_overlay_debug`` for
its building-sync call sites. Leaf deps only (ursina, config,
``ursina_unit_overlays``) — no module-top import of ``ursina_renderer`` (no cycle).
"""
from __future__ import annotations

import os

from ursina import Entity, Vec3, color, Text, scene

from game.graphics.ursina_unit_overlays import configure_ks_overlay as _configure_ks_overlay_impl


_debug_tax_overlay = os.environ.get("KINGDOM_DEBUG_TAX_OVERLAY", "").strip().lower() in ("1", "true", "yes")
_tax_overlay_debug_last_print: float = 0.0

# WK61-R4: polled from engine/input each frame; renderer also checks Ursina held_keys.
_tax_gold_overlay_held: bool = False


def set_tax_gold_overlay_held(held: bool) -> None:
    global _tax_gold_overlay_held
    _tax_gold_overlay_held = bool(held)


def is_tax_gold_overlay_held() -> bool:
    if _tax_gold_overlay_held:
        return True
    try:
        from ursina import held_keys
        return bool(held_keys.get("g", 0))
    except Exception:
        return False


def building_tax_overlay_snapshot(b, *, is_lair: bool) -> tuple[bool, int]:
    """Return (has_tax_field, amount) for hold-G building gold overlays (WK61-R6).

    WK68 R2 (Agent 09): now consumes the frozen BuildingDTO. The DTO carries
    ``has_tax_overlay`` (== the live ``has_tax_stash_data`` property) and
    ``stored_tax_gold``; for tax buildings the live ``get_overlay_tax_gold()`` returns
    exactly ``stored_tax_gold`` and base buildings have ``has_tax_stash_data=False``,
    so ``(has_tax_overlay, stored_tax_gold)`` reproduces the legacy method-based result
    byte-for-byte. A live entity (no ``has_tax_overlay`` attr) still takes the original
    method path below — fully backward compatible.
    """
    if is_lair or getattr(b, "is_poi", False):
        return False, 0
    # DTO path: the participation flag is present (live entities don't carry it).
    if hasattr(b, "has_tax_overlay"):
        if not getattr(b, "has_tax_overlay", False):
            return False, 0
        return True, int(getattr(b, "stored_tax_gold", 0) or 0)
    # Legacy live-entity path (method-based) — unchanged.
    if hasattr(b, "get_overlay_tax_gold"):
        if not getattr(b, "has_tax_stash_data", True):
            return False, 0
        gold = b.get_overlay_tax_gold()
        if gold is None:
            return False, 0
        return True, int(gold)
    if hasattr(b, "stored_tax_gold"):
        return True, int(getattr(b, "stored_tax_gold", 0) or 0)
    return False, 0


def _prefab_local_top_y(ent) -> float:
    """Estimate prefab roof height in parent-local Y for overlay placement."""
    cached = getattr(ent, "_ks_prefab_top_y", None)
    if cached is not None:
        return float(cached)
    max_y = 1.2
    for child in getattr(ent, "children", []) or []:
        try:
            py = float(getattr(child, "y", 0) or 0)
            sc = getattr(child, "scale", None)
            sy = float(getattr(sc, "y", 1) if sc is not None else 1)
            max_y = max(max_y, py + abs(sy) * 0.55)
        except Exception:
            continue
    ent._ks_prefab_top_y = max_y
    return max_y


def _building_gold_overlay_y(ent, *, hy: float = 1.0) -> float:
    """Readable local Y offset for taxable gold Text above prefab or billboard buildings."""
    if getattr(ent, "_ks_prefab_container", False) or getattr(ent, "_ks_building_mode", None) == "prefab":
        return _prefab_local_top_y(ent) + 0.50
    if getattr(ent, "_ks_billboard_configured", False):
        return max(float(hy) * 0.75, 0.9)
    return max(float(hy) * 0.55, 1.8)


def _building_gold_overlay_world_y(ent, *, terrain_y: float, hy: float = 1.0) -> float:
    """World-space Y for hold-G gold billboards: terrain + roof + clearance (WK61-R11 BUG-004).

    WK122-BUG-A1: clearance trimmed from +1.2 to +0.3 so the ``$N`` label hugs the
    roofline (``roof_local`` already encodes the roof-top estimate, incl. the +0.50
    prefab cap), instead of floating ~roof+1.7 above prefab buildings.
    """
    roof_local = _building_gold_overlay_y(ent, hy=hy)
    if getattr(ent, "_ks_prefab_container", False) or getattr(ent, "_ks_building_mode", None) == "prefab":
        return float(terrain_y) + roof_local + 0.3
    if getattr(ent, "_ks_billboard_configured", False):
        return float(terrain_y) + roof_local + 0.3
    return float(terrain_y) + roof_local + 0.3


def _configure_ks_overlay(ent) -> None:
    """Depth-off + on-top so labels/HP/gold overlays are not hidden by terrain or prefabs.

    WK62: delegates to ``ursina_unit_overlays.configure_ks_overlay``.
    """
    _configure_ks_overlay_impl(ent)


def _sync_building_worldspace_ui(
    b,
    bts: str,
    ent,
    is_lair: bool,
    *,
    wx: float = 0.0,
    wz: float = 0.0,
    terrain_y: float = 0.0,
    hy: float = 1.0,
) -> None:
    """R5 Phase 2 (Agent 03): Attach/update label, HP bar, and gold display
    as native Ursina child entities on a building entity.

    Skips POI buildings and lairs — only normal player-built buildings get labels.
    """
    # Skip POIs (discovery-gated) and lairs (enemy structures)
    if getattr(b, "is_poi", False) or is_lair:
        return

    # --- Building label --- (WK61-FEAT-001 / R4-BUG-001: no permanent prefab labels)
    label_ent = getattr(ent, "_ks_label", None)
    if label_ent is not None:
        label_ent.enabled = False
        if not getattr(ent, "_ks_label_removed", False):
            try:
                import ursina as _u
                _u.destroy(label_ent)
            except Exception:
                pass
            ent._ks_label_removed = True
            if hasattr(ent, "_ks_label"):
                delattr(ent, "_ks_label")

    # --- Building HP bar (show only when damaged) ---
    b_hp = int(getattr(b, 'hp', 0) or 0)
    b_max_hp = int(getattr(b, 'max_hp', 1) or 1)
    hp_bar_ent = getattr(ent, '_ks_hp_bar', None)
    if b_max_hp > 0 and b_hp > 0 and b_hp < b_max_hp:
        ratio = b_hp / b_max_hp
        if hp_bar_ent is None:
            hp_bar_ent = Entity(parent=ent, model='quad',
                color=color.green if ratio > 0.5 else color.red,
                scale=(1.0 * ratio, 0.05, 1), y=1.5, billboard=True, unlit=True)
            hp_bar_ent.set_depth_test(False)
            # Mythos S1 (`scene-entities-ignore`): renderer-managed — no update/input.
            from game.graphics.ursina_scene_ignore import mark_scene_ignore
            mark_scene_ignore(hp_bar_ent)
            ent._ks_hp_bar = hp_bar_ent
        else:
            hp_bar_ent.scale_x = ratio
            hp_bar_ent.color = color.green if ratio > 0.5 else color.red
            hp_bar_ent.enabled = True
    elif hp_bar_ent is not None:
        hp_bar_ent.enabled = False

    # --- Gold display (WK61-R10/R11: show $0 while G held; world-space billboard above roof) ---
    has_tax, stash = building_tax_overlay_snapshot(b, is_lair=is_lair)
    g_held = is_tax_gold_overlay_held()
    gold_ent = getattr(ent, "_ks_gold_label", None)
    overlay_world_y = _building_gold_overlay_world_y(ent, terrain_y=terrain_y, hy=hy)
    if has_tax and g_held:
        text = f"${stash}"
        label_color = (
            color.rgb(1.0, 0.8, 0.2) if stash > 0 else color.rgb(0.55, 0.55, 0.55)
        )
        if gold_ent is None:
            gold_ent = Text(
                text=text,
                parent=scene,
                origin=(0, 0),
                scale=12,
                color=label_color,
                billboard=True,
            )
            _configure_ks_overlay(gold_ent)
            ent._ks_gold_label = gold_ent
        else:
            if getattr(gold_ent, "parent", None) is not scene:
                gold_ent.parent = scene
            if gold_ent.text != text:
                gold_ent.text = text
            gold_ent.color = label_color
            gold_ent.enabled = True
            _configure_ks_overlay(gold_ent)
        gold_ent.world_position = Vec3(float(wx), overlay_world_y, float(wz))
    elif gold_ent is not None:
        gold_ent.enabled = False


def _maybe_log_tax_overlay_debug(buildings) -> None:
    """Optional once/sec debug when KINGDOM_DEBUG_TAX_OVERLAY=1 (WK61-R10)."""
    global _tax_overlay_debug_last_print
    if not _debug_tax_overlay:
        return
    import time

    now = time.time()
    if now - _tax_overlay_debug_last_print < 1.0:
        return
    _tax_overlay_debug_last_print = now
    g_held = is_tax_gold_overlay_held()
    tax_count = 0
    stash_sum = 0
    for b in buildings or ():
        # WK68 R2 (Agent 09): DTO-SAFE lair flag. The BuildingDTO carries a ``stash_gold``
        # int field on EVERY building, so a bare ``hasattr(b, "stash_gold")`` would be True
        # for all DTOs (mis-flagging tax buildings as lairs). Use ``has_stash_gold`` when
        # present (the DTO mirror), else the live ``hasattr``. Matches _building_is_lair.
        is_lair = bool(
            getattr(b, "is_lair", False)
            or getattr(b, "has_stash_gold", hasattr(b, "stash_gold"))
        )
        has_tax, stash = building_tax_overlay_snapshot(b, is_lair=is_lair)
        if has_tax:
            tax_count += 1
            stash_sum += int(stash)
    print(
        f"[KINGDOM_DEBUG_TAX_OVERLAY] g_held={g_held} "
        f"tax_buildings={tax_count} sum_stash={stash_sum}"
    )
