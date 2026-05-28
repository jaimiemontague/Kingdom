"""Shared visual spec registry for unit rendering constants.

WK62 Wave 2 (Agent 09): centralises scale, HP-bar, label, and picking
constants that were previously duplicated across ``ursina_renderer.py``,
``instanced_unit_renderer.py``, and ``ursina_pick.py``.

The dataclass is **frozen** and deterministic -- it never inspects live engine
state.  Consumer code calls ``unit_visual_spec(kind, class_or_type)`` once at
startup or per-entity creation and caches the result.

All numeric values are transcribed verbatim from the existing renderer code so
that behaviour is byte-identical before and after this extraction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import config

# ---------------------------------------------------------------------------
# Base scale factor shared by all unit billboards.  Mirrors the expression
# used in ``ursina_renderer.py`` and ``instanced_unit_renderer.py``.
# ---------------------------------------------------------------------------
_US: float = float(
    getattr(config, "UNIT_SPRITE_PIXELS", config.TILE_SIZE)
) / float(config.TILE_SIZE)

_WB: float = float(getattr(config, "URSINA_WORKER_BILLBOARD_BASE", 0.42))
_WYM: float = float(getattr(config, "URSINA_WORKER_BILLBOARD_Y_SCALE_MUL", 0.55))


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class UnitVisualSpec:
    """Read-only visual constants for one unit kind."""

    kind: str
    """Logical unit kind: hero, enemy, peasant, guard, tax_collector."""

    atlas_key: str
    """Atlas category key used by ``UnitAtlasBuilder``: hero, enemy, or worker."""

    scale_x: float
    """Billboard X scale (world units)."""

    scale_y: float
    """Billboard Y scale (world units)."""

    hp_bar_w: float
    """HP bar total width (parent-local units)."""

    hp_bar_h: float
    """HP bar height (parent-local units)."""

    hp_bar_y: float
    """HP bar Y offset from entity origin (parent-local)."""

    label_y: float
    """Name label Y offset from entity origin (parent-local)."""

    label_scale: float
    """Name label ``Text.scale`` (Ursina text scale units)."""

    pick_radius_px: float
    """Screen-space pick radius in virtual pixels (for ``ursina_pick``)."""

    gold_label_y: Optional[float] = None
    """Gold display Y offset (parent-local).  ``None`` means no gold label."""

    gold_label_scale: Optional[float] = None
    """Gold display ``Text.scale``.  ``None`` means no gold label."""

    rest_label_y: Optional[float] = None
    """Rest indicator Y offset.  ``None`` means unit type has no rest label."""

    rest_label_x: Optional[float] = None
    """Rest indicator X offset.  ``None`` means unit type has no rest label."""

    rest_label_scale: Optional[float] = None
    """Rest indicator ``Text.scale``."""


# ---------------------------------------------------------------------------
# Canonical specs -- values transcribed from ursina_renderer.py / pick.py
# ---------------------------------------------------------------------------

# Hero billboard: UNIT_BILLBOARD_SCALE = 0.62 * _US (square)
_HERO_S = 0.62 * _US

HERO_SPEC = UnitVisualSpec(
    kind="hero",
    atlas_key="hero",
    scale_x=_HERO_S,
    scale_y=_HERO_S,
    hp_bar_w=0.8,
    hp_bar_h=0.04,
    hp_bar_y=0.42,
    label_y=0.58,
    label_scale=10,
    pick_radius_px=42.0,
    gold_label_y=-0.35,
    gold_label_scale=10,
    rest_label_y=0.72,
    rest_label_x=0.3,
    rest_label_scale=12,
)

# Enemy billboard: ENEMY_SCALE = 0.5 * _US (square)
_ENEMY_S = 0.5 * _US

ENEMY_SPEC = UnitVisualSpec(
    kind="enemy",
    atlas_key="enemy",
    scale_x=_ENEMY_S,
    scale_y=_ENEMY_S,
    hp_bar_w=0.6,
    hp_bar_h=0.03,
    hp_bar_y=0.38,
    label_y=0.52,
    label_scale=8,
    pick_radius_px=42.0,
)

# Peasant billboard: PEASANT_SCALE_XZ / PEASANT_SCALE_Y (squashed)
_PEASANT_SX = _WB * _US
_PEASANT_SY = _PEASANT_SX * _WYM

PEASANT_SPEC = UnitVisualSpec(
    kind="peasant",
    atlas_key="worker",
    scale_x=_PEASANT_SX,
    scale_y=_PEASANT_SY,
    hp_bar_w=0.5,
    hp_bar_h=0.03,
    hp_bar_y=0.34,
    label_y=0.48,
    label_scale=8,
    pick_radius_px=42.0,
)

# Guard billboard: GUARD_SCALE_XZ / GUARD_SCALE_Y
_GUARD_SX = 0.5 * _US
_GUARD_SY = 0.7 * _US

GUARD_SPEC = UnitVisualSpec(
    kind="guard",
    atlas_key="worker",
    scale_x=_GUARD_SX,
    scale_y=_GUARD_SY,
    hp_bar_w=0.7,
    hp_bar_h=0.03,
    hp_bar_y=0.40,
    label_y=0.50,
    label_scale=8,
    pick_radius_px=42.0,
)

# Tax collector: same billboard size as peasant, no HP bar
TAX_COLLECTOR_SPEC = UnitVisualSpec(
    kind="tax_collector",
    atlas_key="worker",
    scale_x=_PEASANT_SX,
    scale_y=_PEASANT_SY,
    hp_bar_w=0.0,
    hp_bar_h=0.0,
    hp_bar_y=0.0,
    label_y=0.50,
    label_scale=8,
    pick_radius_px=42.0,
)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------
_SPEC_BY_KIND: dict[str, UnitVisualSpec] = {
    "hero": HERO_SPEC,
    "enemy": ENEMY_SPEC,
    "peasant": PEASANT_SPEC,
    "guard": GUARD_SPEC,
    "tax_collector": TAX_COLLECTOR_SPEC,
}

# Alias so ``worker`` also resolves to peasant (atlas_key convention).
_SPEC_BY_KIND["worker"] = PEASANT_SPEC


def unit_visual_spec(kind: str, class_or_type: str = "") -> UnitVisualSpec:
    """Return the canonical visual spec for *kind* (hero/enemy/peasant/guard/tax_collector).

    *class_or_type* is reserved for future per-class overrides (e.g. wizard
    might get a different label colour) but currently unused -- all heroes
    share the same spec.

    Falls back to ``HERO_SPEC`` for unknown kinds so callers never get ``None``.
    """
    return _SPEC_BY_KIND.get(kind.lower(), HERO_SPEC)
