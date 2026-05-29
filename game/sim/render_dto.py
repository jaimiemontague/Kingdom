"""WK66 Round A-1: frozen value-type DTOs for the render boundary.

Renderers consume these instead of live sim entities so they cannot mutate sim
state. Scalars/tuples only — NEVER a live object reference (the one trap is
``Hero.inside_building``, a live building ref, which is flattened to
``inside_building_center``).

The field lists and the getattr defaults below are taken verbatim from what the
renderers read today (verified against ``game/graphics/renderers/*`` and pinned
by ``tests/test_wk66_render_boundary.py::test_render_dto_field_parity``):

- ``UnitDTO``      -> hero_renderer.py:54-173 / enemy_renderer.py:44-124 /
                      worker_renderer.py:53-253
- ``BuildingDTO``  -> building_renderer.py:50-186 (+ ursina lair/POI gating)
- ``BountyDTO``    -> bounty_renderer.py:20-103

Wave 1 is ADDITIVE: ``build_snapshot`` populates these alongside the existing
live entity tuples. Wave 2 flips the renderers to read them; Wave 3 removes the
live tuples.
"""

from __future__ import annotations

from dataclasses import dataclass


def _stable_entity_id(entity: object) -> str:
    """Transitional stable key (WK63 contract).

    ``id(entity)`` is only a fallback for fixtures that lack a real id — every
    live hero/enemy/building/bounty has a stable id by this point.
    """
    return str(
        getattr(entity, "hero_id", None)
        or getattr(entity, "entity_id", None)
        or id(entity)
    )


@dataclass(frozen=True)
class UnitDTO:
    """Hero / enemy / peasant / guard / tax-collector — a shared unit shape."""

    entity_id: str            # stable id (hero_id/entity_id); the render-state key
    kind: str                 # "hero" | "enemy" | "peasant" | "guard" | "tax_collector"
    x: float
    y: float
    facing: int               # default 1
    is_alive: bool
    hp: float
    max_hp: float             # always >= 1.0
    size: int
    state_name: str           # str(getattr(state, "name", state))
    # One-shot animation trigger (read-only). Wave 2 plays the clip when
    # ``anim_trigger_seq`` increases instead of clearing the trigger on the entity.
    anim_trigger: str | None
    anim_trigger_seq: int     # sim-owned monotonic counter; +1 each new trigger
    # hero-only (default-safe for other kinds):
    hero_class: str = "warrior"
    enemy_type: str = "goblin"
    name: str = ""
    gold: int = 0
    taxed_gold: int = 0
    is_inside_building: bool = False
    inside_building_center: tuple[float, float] | None = None  # FLATTENED — never a live ref


@dataclass(frozen=True)
class BuildingDTO:
    entity_id: str
    building_type: str        # already lowercased/normalized
    world_x: float
    world_y: float
    width: int
    height: int
    hp: float
    max_hp: float             # always >= 1.0
    is_constructed: bool
    construction_progress: float   # 0.0 .. 1.0
    color: tuple[int, int, int]
    is_lair: bool
    is_neutral: bool
    stash_gold: int
    stored_tax_gold: int
    level: int
    has_target: bool          # bool(getattr(building, "target", None)) — NOT the live target
    attack_range: int
    is_discovered: bool        # POI discovery flag (sim-owned; render reads only)
    tile_visible: bool         # building's tile is currently VISIBLE (sim fog grid)


@dataclass(frozen=True)
class BountyDTO:
    bounty_id: str
    x: float
    y: float
    claimed: bool
    reward: int
    responders: int
    attractiveness_tier: str  # "low" | "med" | "high"


# ---------------------------------------------------------------------------
# Builders — read EXACTLY the fields the renderers read, with the SAME defaults.
# ---------------------------------------------------------------------------

def unit_dto_from(entity: object, kind: str) -> UnitDTO:
    """Build a ``UnitDTO`` from a live hero/enemy/peasant/guard/tax-collector.

    Mirrors the getattr defaults in hero/enemy/worker renderers so a renderer
    reading the DTO sees identical values to reading the live entity.
    """
    inside_ref = getattr(entity, "inside_building", None)
    if inside_ref is not None:
        inside_center: tuple[float, float] | None = (
            float(getattr(inside_ref, "center_x", 0.0)),
            float(getattr(inside_ref, "center_y", 0.0)),
        )
    else:
        inside_center = None

    state = getattr(entity, "state", None)
    state_name = str(getattr(state, "name", state))

    return UnitDTO(
        entity_id=_stable_entity_id(entity),
        kind=kind,
        x=float(getattr(entity, "x", 0.0)),
        y=float(getattr(entity, "y", 0.0)),
        facing=int(getattr(entity, "facing", 1)),
        is_alive=bool(getattr(entity, "is_alive", True)),
        hp=float(getattr(entity, "hp", 0.0)),
        max_hp=float(max(1.0, getattr(entity, "max_hp", 1.0))),
        size=int(getattr(entity, "size", 20)),
        state_name=state_name,
        anim_trigger=getattr(entity, "_render_anim_trigger", None),
        anim_trigger_seq=int(getattr(entity, "_anim_trigger_seq", 0)),
        hero_class=str(getattr(entity, "hero_class", "warrior")),
        enemy_type=str(getattr(entity, "enemy_type", "goblin")),
        name=str(getattr(entity, "name", "")),
        gold=int(getattr(entity, "gold", 0)),
        taxed_gold=int(getattr(entity, "taxed_gold", 0)),
        is_inside_building=bool(getattr(entity, "is_inside_building", False)),
        inside_building_center=inside_center,
    )


def building_dto_from(b: object, *, tile_visible: bool = False) -> BuildingDTO:
    """Build a ``BuildingDTO`` from a live building.

    ``tile_visible`` is computed by the sim (``build_snapshot``) from the fog
    grid; the renderer no longer needs to consult ``world.visibility`` for the
    fields carried here.
    """
    raw_type = getattr(b, "building_type", "building")
    building_type = str(getattr(raw_type, "value", raw_type) or "building").lower()
    return BuildingDTO(
        entity_id=str(getattr(b, "entity_id", None) or id(b)),
        building_type=building_type,
        world_x=float(getattr(b, "world_x", 0.0)),
        world_y=float(getattr(b, "world_y", 0.0)),
        width=int(getattr(b, "width", 0)),
        height=int(getattr(b, "height", 0)),
        hp=float(getattr(b, "hp", 0.0)),
        max_hp=float(max(1.0, getattr(b, "max_hp", 1.0))),
        is_constructed=bool(getattr(b, "is_constructed", True)),
        construction_progress=float(getattr(b, "construction_progress", 1.0)),
        color=tuple(getattr(b, "color", (128, 128, 128))),
        is_lair=bool(getattr(b, "is_lair", False)),
        is_neutral=bool(getattr(b, "is_neutral", False)),
        stash_gold=int(getattr(b, "stash_gold", 0)),
        stored_tax_gold=int(getattr(b, "stored_tax_gold", 0)),
        level=int(getattr(b, "level", 1)),
        has_target=bool(getattr(b, "target", None)),
        attack_range=int(getattr(b, "attack_range", 0)),
        is_discovered=bool(getattr(b, "is_discovered", False)),
        tile_visible=bool(tile_visible),
    )


def bounty_dto_from(b: object) -> BountyDTO:
    """Build a ``BountyDTO`` from a live bounty (excludes the ``_ui_cache_*`` scratch)."""
    responders = int(getattr(b, "responders", getattr(b, "ui_responders", 0)) or 0)
    tier = str(
        getattr(b, "attractiveness_tier", getattr(b, "ui_attractiveness", "low")) or "low"
    ).lower()
    return BountyDTO(
        bounty_id=str(getattr(b, "bounty_id", None) or id(b)),
        x=float(getattr(b, "x", 0.0)),
        y=float(getattr(b, "y", 0.0)),
        claimed=bool(getattr(b, "claimed", False)),
        reward=int(getattr(b, "reward", 0) or 0),
        responders=responders,
        attractiveness_tier=tier,
    )
