"""Mechanical extraction of HP/name/gold/rest label sync from UrsinaRenderer.

WK62 Wave 2 (Agent 09 Task B): moves overlay creation, update, and facing
logic out of the monolithic ``ursina_renderer.py`` into a focused helper.

No label behaviour has been changed -- this is a pure code-motion refactor.
The renderer calls these helpers instead of having the logic inline.
"""
from __future__ import annotations

from ursina import Entity, Text, color, scene, Vec3

from game.graphics.visual_specs import UnitVisualSpec


# -----------------------------------------------------------------------
# Low-level overlay utilities (previously module-level in ursina_renderer)
# -----------------------------------------------------------------------

def configure_ks_overlay(ent) -> None:
    """Depth-off + on-top so labels/HP/gold overlays are not hidden by terrain or prefabs.

    WK122-BUG-A2: ``always_on_top`` + ``render_queue`` alone did NOT reliably force the
    Text onto a top render bin, so taller/nearer buildings drawn later still occluded the
    ``$N`` tax labels. We now also disable depth *write* and assign a genuine high-sort
    Panda3D ``"fixed"`` bin (sort 60), so the entity draws after all opaque world geometry
    regardless of draw order. ``set_depth_test``/``set_depth_write``/``set_bin`` are exposed
    on the Ursina Entity via its Panda3D NodePath base. Shared by HP bars + name labels;
    they were already depth-off + on-top, so the extra bin only reinforces their layering.
    """
    if ent is None or getattr(ent, "_ks_overlay_cfg", False):
        return
    ent.billboard = True
    try:
        ent.set_depth_test(False)
    except Exception:
        pass
    try:
        ent.set_depth_write(False)
    except Exception:
        pass
    try:
        # Genuine top render bin: draw after all opaque world geometry (buildings/terrain/trees).
        ent.set_bin("fixed", 60)
    except Exception:
        pass
    try:
        ent.always_on_top = True
    except Exception:
        pass
    try:
        ent.render_queue = 2
    except Exception:
        pass
    try:
        if getattr(ent, "z", 0) >= 0:
            ent.z = -0.02
    except Exception:
        pass
    ent._ks_overlay_cfg = True


def sync_ks_facing_overlay(child, facing: float) -> None:
    """Keep overlay readable when the parent billboard uses negative scale_x for facing."""
    if child is None:
        return
    sx = getattr(child, "scale_x", None)
    if sx is None:
        sc = getattr(child, "scale", None)
        sx = getattr(sc, "x", 12) if sc is not None else 12
    child.scale_x = abs(float(sx or 12))
    child.rotation_y = 180 if float(facing) < 0 else 0


# -----------------------------------------------------------------------
# Overlay teardown (WK123 C1 leak fix)
# -----------------------------------------------------------------------

# Every ``_ks_*`` attr that holds a child Entity/Text overlay node attached to a
# unit/building billboard. ``ursina.destroy(parent)`` does NOT cascade to regular
# ``.children`` (Ursina's destroy.py has the child-recursion commented out), so on
# removal these orphan into ``scene.entities`` forever unless freed explicitly.
# Sources: ursina_unit_overlays (_ks_hp_bg/_ks_hp_fg/_ks_name_label/_ks_gold_label/
# _ks_rest_label), ursina_unit_sync (_ks_tc_gold), ursina_building_ui
# (_ks_hp_bar/_ks_label, plus _ks_gold_label which is parent=SCENE — so it is NOT
# in ent.children and MUST be caught by this named-attr loop, not the child sweep).
_OVERLAY_CHILD_ATTRS = (
    "_ks_hp_bg",
    "_ks_hp_fg",
    "_ks_name_label",
    "_ks_gold_label",
    "_ks_rest_label",
    "_ks_tc_gold",
    "_ks_hp_bar",
    "_ks_label",
)


def free_entity_overlays(ent) -> None:
    """Destroy every overlay child Entity/Text attached to *ent* and clear its attrs.

    Called on the removal path BEFORE ``ursina.destroy(ent)`` so the unit/building's
    detached overlay nodes do not orphan into ``scene.entities`` (WK123 C1 leak). The
    unit/building itself is destroyed by the caller; this only frees its overlays.

    Belt-and-suspenders: after the named-attr sweep, also destroys any remaining
    ``children`` / ``loose_children`` so an overlay not covered by a named attr is
    still freed. Robust to already-destroyed entities / missing attrs.
    """
    if ent is None:
        return
    import ursina as _u

    for attr in _OVERLAY_CHILD_ATTRS:
        child = getattr(ent, attr, None)
        if child is not None:
            try:
                _u.destroy(child)
            except Exception:
                pass
            try:
                setattr(ent, attr, None)
            except Exception:
                pass

    for child in (
        list(getattr(ent, "children", []) or [])
        + list(getattr(ent, "loose_children", []) or [])
    ):
        try:
            _u.destroy(child)
        except Exception:
            pass


# -----------------------------------------------------------------------
# Name label
# -----------------------------------------------------------------------

def ensure_ks_name_label(
    ent,
    attr: str,
    text: str,
    *,
    y: float = 0.55,
    scale: float = 10,
    label_color=None,
) -> None:
    """Create or update a ``Text`` child for a unit name / type label."""
    if not text:
        lab = getattr(ent, attr, None)
        if lab is not None:
            lab.enabled = False
        return
    lab = getattr(ent, attr, None)
    tint = label_color or color.white
    if lab is None:
        lab = Text(
            text=text,
            parent=ent,
            origin=(0, 0),
            scale=scale,
            color=tint,
            billboard=True,
            y=y,
        )
        configure_ks_overlay(lab)
        setattr(ent, attr, lab)
    else:
        if lab.text != text:
            lab.text = text
        lab.enabled = True
        configure_ks_overlay(lab)


# -----------------------------------------------------------------------
# HP bar (two-quad: background + coloured foreground)
# -----------------------------------------------------------------------

def sync_hp_bar(ent, hp: int, max_hp: int, spec: UnitVisualSpec) -> None:
    """Create or update the HP bar child quads on *ent* using *spec* dimensions.

    Skips units whose ``spec.hp_bar_w`` is zero (e.g. tax collectors with no HP
    bar).  Uses the ``_ks_last_hp_key`` dirty-gate so Panda3D transforms are
    only touched when HP actually changes (WK58 W6 perf fix).
    """
    if spec.hp_bar_w <= 0:
        return

    hp_bg = getattr(ent, "_ks_hp_bg", None)
    hp_fg = getattr(ent, "_ks_hp_fg", None)
    hp_key = (hp, max_hp)

    bw = spec.hp_bar_w
    bh = spec.hp_bar_h
    by = spec.hp_bar_y

    if max_hp > 0 and hp > 0:
        ratio = hp / max_hp
        bar_color = color.green if ratio > 0.5 else color.red

        if hp_bg is None:
            hp_bg = Entity(
                parent=ent, model="quad", color=color.rgb(0.25, 0.25, 0.25),
                scale=(bw, bh, 1), position=(0, by, -0.01),
                billboard=True, unlit=True,
            )
            configure_ks_overlay(hp_bg)
            ent._ks_hp_bg = hp_bg

        if hp_fg is None:
            hp_fg = Entity(
                parent=ent, model="quad", color=bar_color,
                scale=(bw * ratio, bh, 1),
                position=(-(bw * (1 - ratio) / 2), by, -0.02),
                billboard=True, unlit=True,
            )
            configure_ks_overlay(hp_fg)
            ent._ks_hp_fg = hp_fg
            ent._ks_last_hp_key = hp_key
        elif getattr(ent, "_ks_last_hp_key", None) != hp_key:
            hp_fg.scale_x = bw * ratio
            hp_fg.x = -(bw * (1 - ratio) / 2)
            hp_fg.color = bar_color
            ent._ks_last_hp_key = hp_key

        hp_bg.enabled = True
        hp_fg.enabled = True
        configure_ks_overlay(hp_bg)
        configure_ks_overlay(hp_fg)
    else:
        if hp_bg is not None:
            hp_bg.enabled = False
        if hp_fg is not None:
            hp_fg.enabled = False


# -----------------------------------------------------------------------
# Hero gold display
# -----------------------------------------------------------------------

def sync_hero_gold_label(ent, gold: int, taxed_gold: int) -> None:
    """Show ``$N`` (or ``$N(+T)``) below the hero billboard."""
    total = gold + taxed_gold
    gold_ent = getattr(ent, "_ks_gold_label", None)
    if total > 0:
        gold_text = f"${gold}(+{taxed_gold})" if taxed_gold > 0 else f"${gold}"
        if gold_ent is None:
            gold_ent = Text(
                text=gold_text, parent=ent, origin=(0, 0), scale=10,
                color=color.rgb(1.0, 0.8, 0.2), billboard=True, y=-0.35,
            )
            configure_ks_overlay(gold_ent)
            ent._ks_gold_label = gold_ent
        else:
            if gold_ent.text != gold_text:
                gold_ent.text = gold_text
            gold_ent.enabled = True
            configure_ks_overlay(gold_ent)
    elif gold_ent is not None:
        gold_ent.enabled = False


# -----------------------------------------------------------------------
# Hero rest indicator
# -----------------------------------------------------------------------

def sync_hero_rest_label(ent, is_resting: bool) -> None:
    """Show / hide the ``Zzz`` label when a hero is resting."""
    rest_ent = getattr(ent, "_ks_rest_label", None)
    if is_resting:
        if rest_ent is None:
            rest_ent = Text(
                text="Zzz", parent=ent, origin=(0, 0), scale=12,
                color=color.rgb(0.7, 0.85, 1.0), billboard=True, y=0.72, x=0.3,
            )
            configure_ks_overlay(rest_ent)
            ent._ks_rest_label = rest_ent
        else:
            rest_ent.enabled = True
            configure_ks_overlay(rest_ent)
    elif rest_ent is not None:
        rest_ent.enabled = False


# -----------------------------------------------------------------------
# Batch facing fix for all overlay children
# -----------------------------------------------------------------------

_HERO_OVERLAY_ATTRS = ("_ks_name_label", "_ks_gold_label", "_ks_rest_label",
                       "_ks_hp_bg", "_ks_hp_fg")
_SIMPLE_OVERLAY_ATTRS = ("_ks_name_label", "_ks_hp_bg", "_ks_hp_fg")


def sync_hero_overlays_facing(ent, facing: float) -> None:
    """Un-mirror all hero overlay children when the parent faces left."""
    for attr in _HERO_OVERLAY_ATTRS:
        sync_ks_facing_overlay(getattr(ent, attr, None), facing)


def sync_unit_overlays_facing(ent, facing: float) -> None:
    """Un-mirror name + HP overlay children when the parent faces left."""
    for attr in _SIMPLE_OVERLAY_ATTRS:
        sync_ks_facing_overlay(getattr(ent, attr, None), facing)
