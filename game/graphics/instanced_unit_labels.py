"""Pooled zoom-LOD name/gold labels for the instanced unit path (Mythos S4+S6).

``label-zoom-lod-pooled``: instanced units have no per-unit Entity to parent a
``Text`` label to, and creating/destroying Texts per frame is the documented
spawn-hitch mechanism (Ursina ``Text.__init__`` costs 5-21 ms). Instead, a
FIXED, BOUNDED pool of ``Text`` entities is created lazily (never destroyed,
never grown past the cap — C1-leak compliant: ``scene.entities`` stays stable)
and re-assigned each frame to the nearest on-screen instanced units via cheap
``.text`` mutation (~0.13 ms) + ``world_position`` writes.

Zoom LOD (owner-authorized): labels exist ONLY when the camera zoom ratio
(``frame.zoom / frame.default_zoom``) is closer than the threshold — at the
gate scenario's fully-zoomed-out view (ZOOM_MIN=0.3) labels are culled (they
are physically illegible there anyway; HP bars stay — they render in the
instanced HP-bar pass regardless of zoom). Hysteresis prevents threshold
flicker. The SELECTED hero's labels bypass the LOD (candidate spec).

Label content/placement byte-matches the legacy per-Entity overlays
(``ursina_unit_overlays`` / ``ursina_unit_sync``): name labels (hero name,
enemy/worker type title, "Guard", "Tax Collector"), the hero gold ``$N(+T)``
label, and the tax-collector carried-gold ``$N`` label. Legacy labels are
children of a scaled billboarded parent, so world scale = label_scale *
parent_scale_y and the local +y offset rides the camera-up axis — both are
reproduced here. The dead rest-"Zzz" label is NOT reproduced (it never showed
in legacy either — see the WK68 note in ursina_unit_sync.py).

Env knobs:

* ``KINGDOM_LABEL_ZOOM_CULL``     — "0" disables the LOD cull (labels at every
                                    zoom, still pooled/bounded). Default on.
* ``KINGDOM_LABEL_ZOOM_LOD_ON``   — zoom ratio at/above which labels turn ON
                                    (default 0.8).
* ``KINGDOM_LABEL_ZOOM_LOD_OFF``  — zoom ratio below which labels turn OFF
                                    (default 0.7; clamped <= ON for hysteresis).
* ``KINGDOM_INSTANCED_LABEL_POOL``— pool cap in Text nodes (default 64).
"""
from __future__ import annotations

import os
from typing import Sequence

from ursina import Text, Vec3, color, scene

from game.graphics.ursina_unit_overlays import configure_ks_overlay
from game.graphics.visual_specs import (
    ENEMY_SPEC,
    GUARD_SPEC,
    HERO_SPEC,
    PEASANT_SPEC,
    TAX_COLLECTOR_SPEC,
    UnitVisualSpec,
)

_SPEC_BY_KIND: dict[str, UnitVisualSpec] = {
    "hero": HERO_SPEC,
    "enemy": ENEMY_SPEC,
    "peasant": PEASANT_SPEC,
    "guard": GUARD_SPEC,
    "tax_collector": TAX_COLLECTOR_SPEC,
}

# Legacy gold-label tint (ursina_unit_overlays.sync_hero_gold_label /
# ursina_unit_sync tax-collector gold).
_GOLD_COLOR = color.rgb(1.0, 0.8, 0.2)
_WHITE = color.white

# Legacy tax-collector carried-gold label constants (hardcoded at
# ursina_unit_sync.py sync_snapshot_tax_collector — not in the spec).
_TC_GOLD_Y = 0.35
_TC_GOLD_SCALE = 10.0


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name, "")
        return float(raw) if raw.strip() else float(default)
    except Exception:
        return float(default)


class InstancedUnitLabelPool:
    """Bounded, reusable pool of world-space ``Text`` labels for instanced units."""

    def __init__(self, max_labels: int | None = None) -> None:
        if max_labels is None:
            try:
                max_labels = int(os.environ.get("KINGDOM_INSTANCED_LABEL_POOL", "64"))
            except Exception:
                max_labels = 64
        self._max = max(1, int(max_labels))
        raw_cull = os.environ.get("KINGDOM_LABEL_ZOOM_CULL", "1")
        self._cull_enabled = str(raw_cull).strip().lower() not in ("0", "false", "no", "off")
        self._lod_on = _env_float("KINGDOM_LABEL_ZOOM_LOD_ON", 0.8)
        self._lod_off = min(_env_float("KINGDOM_LABEL_ZOOM_LOD_OFF", 0.7), self._lod_on)
        # Hysteresis state: start culled — the first sync() flips it on when the
        # camera is close enough (boot zoom 1.0 >= 0.8 -> on; gate 0.3 stays off).
        self._lod_visible = False
        # key (entity_id, slot) -> Text currently showing that label.
        self._assigned: dict[tuple[str, str], Text] = {}
        # Returned-to-pool Texts (disabled, ready for reuse).
        self._free: list[Text] = []
        self._created_total = 0
        self._overflow_logged = False

    # ------------------------------------------------------------------
    # Introspection (tests / debug)
    # ------------------------------------------------------------------
    @property
    def pool_entity_count(self) -> int:
        """Total Text nodes ever created (== live pool size; never shrinks)."""
        return self._created_total

    @property
    def active_label_count(self) -> int:
        """Labels currently assigned/enabled this frame."""
        return len(self._assigned)

    @property
    def lod_visible(self) -> bool:
        return self._lod_visible

    # ------------------------------------------------------------------
    # LOD
    # ------------------------------------------------------------------
    def _labels_visible(self, zoom_ratio: float) -> bool:
        if not self._cull_enabled:
            return True
        if self._lod_visible:
            if zoom_ratio < self._lod_off:
                self._lod_visible = False
        else:
            if zoom_ratio >= self._lod_on:
                self._lod_visible = True
        return self._lod_visible

    # ------------------------------------------------------------------
    # Pool plumbing
    # ------------------------------------------------------------------
    def _create_label(self):
        if self._created_total >= self._max:
            if not self._overflow_logged:
                self._overflow_logged = True
                try:
                    print(
                        f"[mythos] label pool cap ({self._max}) reached — "
                        "farthest unit labels skipped (KINGDOM_INSTANCED_LABEL_POOL to raise)",
                        flush=True,
                    )
                except Exception:
                    pass
            return None
        lbl = Text(text=" ", parent=scene, origin=(0, 0), billboard=True)
        # Same overlay contract as legacy labels: always_on_top + depth off +
        # bin fixed,110 (WK124) + mark_scene_ignore (skipped by ursina's walk).
        configure_ks_overlay(lbl)
        self._created_total += 1
        return lbl

    # ------------------------------------------------------------------
    # Per-frame sync
    # ------------------------------------------------------------------
    def sync(
        self,
        sources: Sequence,
        *,
        zoom_ratio: float = 1.0,
        selected_id: str | None = None,
    ) -> None:
        """Assign pooled labels to instanced units for this frame.

        ``sources``: ``InstancedUnitRenderer.label_sources`` — (kind, dto,
        blended world pos) tuples, already frustum-filtered. ``zoom_ratio``:
        ``frame.zoom / frame.default_zoom``. ``selected_id``: stable id of the
        selected hero — its labels bypass the zoom LOD.
        """
        visible = self._labels_visible(float(zoom_ratio))

        if visible:
            ordered = list(sources)
            # Nearest-to-camera first so the bounded pool spends its budget on
            # the most readable units; the selected hero always sorts first.
            cam_pos = None
            try:
                from ursina import camera

                wp = camera.world_position
                cam_pos = (float(wp.x), float(wp.y), float(wp.z))
            except Exception:
                cam_pos = None

            def _rank(src) -> tuple:
                kind, dto, pos = src
                is_sel = 0 if (selected_id is not None and dto.entity_id == selected_id) else 1
                if cam_pos is None:
                    return (is_sel, 0.0)
                dx = pos[0] - cam_pos[0]
                dy = pos[1] - cam_pos[1]
                dz = pos[2] - cam_pos[2]
                return (is_sel, dx * dx + dy * dy + dz * dz)

            ordered.sort(key=_rank)
        elif selected_id is not None:
            ordered = [s for s in sources if s[1].entity_id == selected_id]
        else:
            ordered = []

        # Build the desired label set (capped at the pool size), preserving the
        # nearest-first order. Each entry: key -> (text, color, scale, pos, y_off).
        desired: dict[tuple[str, str], tuple] = {}
        budget = self._max
        for kind, dto, pos in ordered:
            if len(desired) >= budget:
                break
            spec = _SPEC_BY_KIND.get(kind)
            if spec is None:
                continue
            eid = dto.entity_id
            name_text = self._name_text(kind, dto)
            if name_text:
                desired[(eid, "name")] = (
                    name_text,
                    _WHITE,
                    float(spec.label_scale) * spec.scale_y,
                    pos,
                    float(spec.label_y) * spec.scale_y,
                )
            if len(desired) >= budget:
                break
            if kind == "hero":
                gold = int(getattr(dto, "gold", 0) or 0)
                taxed = int(getattr(dto, "taxed_gold", 0) or 0)
                if gold + taxed > 0:
                    gold_text = f"${gold}(+{taxed})" if taxed > 0 else f"${gold}"
                    desired[(eid, "gold")] = (
                        gold_text,
                        _GOLD_COLOR,
                        float(spec.gold_label_scale or 10) * spec.scale_y,
                        pos,
                        float(spec.gold_label_y or -0.35) * spec.scale_y,
                    )
            elif kind == "tax_collector":
                carried = int(getattr(dto, "carried_gold", 0) or 0)
                if carried > 0:
                    desired[(eid, "gold")] = (
                        f"${carried}",
                        _GOLD_COLOR,
                        _TC_GOLD_SCALE * spec.scale_y,
                        pos,
                        _TC_GOLD_Y * spec.scale_y,
                    )

        # Release labels whose key is no longer desired (disable ONCE, gated on
        # the real _enabled attr — no per-frame unstash storms).
        for key in [k for k in self._assigned if k not in desired]:
            lbl = self._assigned.pop(key)
            if getattr(lbl, "_enabled", True):
                lbl.enabled = False
            self._free.append(lbl)

        if not desired:
            return

        # Legacy labels are children of a BILLBOARDED parent, so their local +y
        # offset rides the camera-up axis — reproduce with the camera up vector.
        try:
            from ursina import camera

            up = camera.up
            up = (float(up.x), float(up.y), float(up.z))
        except Exception:
            up = (0.0, 1.0, 0.0)

        for key, (txt, clr, scl, pos, y_off) in desired.items():
            lbl = self._assigned.get(key)
            if lbl is None:
                lbl = self._free.pop() if self._free else self._create_label()
                if lbl is None:
                    continue  # pool exhausted — farthest labels skipped
                self._assigned[key] = lbl
            if not getattr(lbl, "_enabled", True):
                lbl.enabled = True
            if lbl.text != txt:
                lbl.text = txt
            if getattr(lbl, "_ks_pool_color", None) != clr:
                lbl.color = clr
                lbl._ks_pool_color = clr
            if getattr(lbl, "_ks_pool_scale", None) != scl:
                lbl.scale = scl
                lbl._ks_pool_scale = scl
            lbl.world_position = Vec3(
                pos[0] + up[0] * y_off,
                pos[1] + up[1] * y_off,
                pos[2] + up[2] * y_off,
            )

    @staticmethod
    def _name_text(kind: str, dto) -> str:
        """Legacy name-label text per unit kind (ursina_unit_sync parity)."""
        if kind == "hero":
            return str(getattr(dto, "name", "") or "")
        if kind == "enemy":
            return str(getattr(dto, "enemy_type", "enemy") or "enemy").replace("_", " ").title()
        if kind == "peasant":
            return str(
                getattr(dto, "render_worker_type", "peasant") or "peasant"
            ).replace("_", " ").title()
        if kind == "guard":
            return "Guard"
        if kind == "tax_collector":
            return "Tax Collector"
        return ""

    def destroy(self) -> None:
        import ursina as _u

        for lbl in list(self._assigned.values()) + list(self._free):
            try:
                _u.destroy(lbl)
            except Exception:
                pass
        self._assigned.clear()
        self._free.clear()
        self._created_total = 0
