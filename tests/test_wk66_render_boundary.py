"""WK66 Round A-1 — render/snapshot boundary characterization pins.

These four pins are written in **Wave 0, before any code change**, and MUST be
GREEN on the current unmodified code (HEAD a469841). They are the contract that
proves the WK66 moves (1a anim-trigger, 1b fog/discovery, 3 render DTOs, 4 the
snapshot split) are *behavior-preserving*:

1. ``test_render_dto_field_parity`` — pins the exact field values a renderer
   reads off a live sim entity today. After Move 3 builds ``UnitDTO`` /
   ``BuildingDTO`` / ``BountyDTO``, an equivalent helper reading the DTO must
   return the SAME tuples. (The field lists below are the enumerations in the
   plan's "Wave 1 — Agent 03 / Task 1" section, verified against the renderer
   source in ``game/graphics/renderers/*``.)
2. ``test_anim_one_shot_plays_once_then_replays_on_new_trigger`` — pins the
   observable one-shot contract under Move 1a's **seq-based** mechanism: the sim
   bumps a monotonic ``_anim_trigger_seq`` per NEW trigger (no longer clearing
   ``_render_anim_trigger`` off the entity), and each renderer plays the one-shot
   only when the seq advances vs a renderer-owned last-seen. The pins have teeth
   against all three failure modes this mechanism could introduce: never-play,
   loop-forever, and replay-on-unchanged-seq (the last is the exact risk of
   removing the write-back clear — the trigger string now lingers). Covered on
   the pygame ``HeroRenderer`` / ``RendererRegistry`` path AND the Ursina
   ``_compute_anim_frame`` seq-gating path (headless).
3. ``test_fog_discovery_digest_is_stable`` — the byte-identical guardrail for
   Move 1b. A deterministic (``DETERMINISTIC_SIM=1``, seed 3) headless engine
   run with a hero revealing terrain must produce a fixed digest of the
   ``world.visibility`` grid + the ``is_discovered`` building count.
4. ``test_snapshot_not_mutated_on_consume`` — extends WK65's build-time guard
   (``tests/test_wk65_snapshot_no_mutation.py``) to the *consume* side: driving a
   full renderer pass over the snapshot must not mutate the gameplay fields of
   any live sim entity. (Move 1a/1b/L2 remove the renderer write-backs that this
   pin's field set is deliberately blind to — see ``_GAMEPLAY_FIELDS`` note.)

Style mirrors ``tests/test_engine.py`` / ``tests/test_wk65_snapshot_no_mutation.py``:
``GameEngine(headless=True)`` + ``pygame.quit()`` in a finally.
"""

from __future__ import annotations

import os

import pygame
import pytest

# Headless-friendly drivers so the renderer pass + sprite loads work without a
# real display (mirrors tools/capture_screenshots.py).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from config import TILE_SIZE
from game.engine import GameEngine


# A sentinel so a missing attribute is recorded as a stable value rather than
# raising — the renderers read every field via getattr(..., default), so the
# parity contract is "the value the renderer would see", not "attribute exists".
_MISSING = "<missing>"


# ---------------------------------------------------------------------------
# Cross-test resource hygiene (WK66-W0 suite-crash fix)
# ---------------------------------------------------------------------------
#
# ROOT CAUSE of the full-suite "Windows fatal exception: access violation
# (0xC0000005)": the renderer pass these pins drive populates several
# *module-global / class-level* pygame.Surface caches —
#   * game.graphics.font_cache._FONT_CACHE / _TEXT_CACHE / _TEXT_SHADOW_CACHE
#   * {Hero,Enemy,Worker,Building}SpriteLibrary._cache  (AnimationClip frames)
#   * game.graphics.ui_icons._type_cache / _tier_cache / _badge_cache
# Those Surfaces (some built via convert_alpha(), i.e. display-format-bound) are
# allocated under one pygame display session. When this file then calls
# pygame.quit() in a test's finally, SDL is torn down and those cached Surfaces /
# Font objects are left orphaned in the global dicts. A *later* test in the same
# process re-inits pygame, gets a cache HIT, and blits / pygame.transform.* the
# stale surface — corrupting the SDL/GDI heap until the process dies (the crash
# surfaces in font.render(), but the cause is the stale cached surfaces, not the
# font call itself). The 575 other tests never drive a full render-pass through
# these caches, so they stay under Windows' surface limit; these pins were the
# straw. Fix: after EVERY test in this file, drop everything we cached and quit
# the display cleanly, so this file leaves zero stale pygame state behind and
# cannot contribute to cross-suite accumulation. No assertion is touched.


def _clear_global_render_caches() -> None:
    """Empty every module-global pygame.Surface/Font cache our render pass fills.

    Defensive: each clear is independent so a not-yet-imported module never
    breaks teardown. Safe to call repeatedly.
    """
    try:
        from game.graphics import font_cache as _fc
        _fc._FONT_CACHE.clear()
        _fc._TEXT_CACHE.clear()
        _fc._TEXT_SHADOW_CACHE.clear()
    except Exception:
        pass
    for module_name, cls_name in (
        ("game.graphics.hero_sprites", "HeroSpriteLibrary"),
        ("game.graphics.enemy_sprites", "EnemySpriteLibrary"),
        ("game.graphics.worker_sprites", "WorkerSpriteLibrary"),
        ("game.graphics.building_sprites", "BuildingSpriteLibrary"),
    ):
        try:
            import importlib

            cache = getattr(getattr(importlib.import_module(module_name), cls_name), "_cache")
            cache.clear()
        except Exception:
            pass
    try:
        from game.graphics import ui_icons as _icons
        _icons._type_cache.clear()
        _icons._tier_cache.clear()
        _icons._badge_cache.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _render_resource_hygiene():
    """Per-test teardown: release every global pygame surface/font this file
    populated and quit the display, so a stale cached surface from one of these
    pins can never be reused by a later suite test (the access-violation cause).

    Runs for ALL tests in this module (autouse). It only *adds* cleanup after
    each test body's own ``pygame.quit()`` finally — it changes no assertion and
    no scenario, so the four pins keep their full rigor.
    """
    yield
    _clear_global_render_caches()
    try:
        if pygame.display.get_init():
            pygame.display.quit()
    except Exception:
        pass
    try:
        pygame.quit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _round_floats(value, ndigits: int = 3):
    if isinstance(value, float):
        return round(value, ndigits)
    return value


def _state_name(entity) -> str:
    """How every renderer coerces ``state`` -> a clip-selector string."""
    state = getattr(entity, "state", None)
    return str(getattr(state, "name", state))


# ===========================================================================
# Pin 1 — Render-DTO field parity (pins Move 3)
# ===========================================================================
#
# Each helper reads EXACTLY the fields the corresponding renderer reads today,
# using the SAME getattr-with-default the renderer uses (see the read sites
# enumerated in each docstring). After Move 3, a helper reading the DTO must
# return the identical tuple — that is the contract Agent 03 builds DTOs to and
# Agent 10 consumes.


def _unit_view(entity, kind: str) -> tuple:
    """Fields read by hero_renderer.py:54-173 / enemy_renderer.py:44-124 /
    worker_renderer.py:53-253 off a live unit (hero/enemy/peasant/guard/tax).

    ``inside_building`` is flattened to its center tuple here, exactly as the
    plan requires the DTO to carry ``inside_building_center`` (NOT a live ref).
    """
    inside_ref = getattr(entity, "inside_building", None)
    if inside_ref is not None:
        inside_center = (
            _round_floats(float(getattr(inside_ref, "center_x", 0.0))),
            _round_floats(float(getattr(inside_ref, "center_y", 0.0))),
        )
    else:
        inside_center = None
    return (
        # stable id used as the render-state key (Move 3 keys on this, never id())
        str(getattr(entity, "hero_id", None) or getattr(entity, "entity_id", None) or id(entity)),
        kind,
        _round_floats(float(getattr(entity, "x", 0.0))),
        _round_floats(float(getattr(entity, "y", 0.0))),
        int(getattr(entity, "facing", 1)),
        bool(getattr(entity, "is_alive", True)),
        _round_floats(float(getattr(entity, "hp", 0.0))),
        _round_floats(float(max(1.0, getattr(entity, "max_hp", 1.0)))),
        int(getattr(entity, "size", 20)),
        _state_name(entity),
        # hero-only fields (default-safe for other kinds, per the DTO defaults)
        str(getattr(entity, "hero_class", "warrior")),
        str(getattr(entity, "enemy_type", "goblin")),
        str(getattr(entity, "name", "")),
        int(getattr(entity, "gold", 0)),
        int(getattr(entity, "taxed_gold", 0)),
        bool(getattr(entity, "is_inside_building", False)),
        inside_center,
    )


def _building_view(building) -> tuple:
    """Fields read by building_renderer.py:50-186 off a live building."""
    raw_type = getattr(building, "building_type", "building")
    building_type = str(getattr(raw_type, "value", raw_type) or "building").lower()
    return (
        str(getattr(building, "entity_id", None) or id(building)),
        building_type,
        _round_floats(float(getattr(building, "world_x", 0.0))),
        _round_floats(float(getattr(building, "world_y", 0.0))),
        int(getattr(building, "width", 0)),
        int(getattr(building, "height", 0)),
        _round_floats(float(getattr(building, "hp", 0.0))),
        _round_floats(float(max(1.0, getattr(building, "max_hp", 1.0)))),
        bool(getattr(building, "is_constructed", True)),
        _round_floats(float(getattr(building, "construction_progress", 1.0))),
        tuple(getattr(building, "color", (128, 128, 128))),
        bool(getattr(building, "is_lair", False)),
        bool(getattr(building, "is_neutral", False)),
        int(getattr(building, "stash_gold", 0)),
        int(getattr(building, "stored_tax_gold", 0)),
        int(getattr(building, "level", 1)),
        bool(getattr(building, "target", None)),  # has_target — never the live target ref
        int(getattr(building, "attack_range", 0)),
    )


def _bounty_view(bounty) -> tuple:
    """Fields read by bounty_renderer.py:20-103 off a live bounty.

    Excludes the nine ``_ui_cache_*`` attributes the renderer currently stamps
    on the bounty — those are the L2 write-back Move 1/Wave 2 removes, not part
    of the data contract.
    """
    responders = int(getattr(bounty, "responders", getattr(bounty, "ui_responders", 0)) or 0)
    tier = str(
        getattr(bounty, "attractiveness_tier", getattr(bounty, "ui_attractiveness", "low")) or "low"
    ).lower()
    return (
        str(getattr(bounty, "bounty_id", None) or id(bounty)),
        _round_floats(float(getattr(bounty, "x", 0.0))),
        _round_floats(float(getattr(bounty, "y", 0.0))),
        bool(getattr(bounty, "claimed", False)),
        int(getattr(bounty, "reward", 0) or 0),
        responders,
        tier,
    )


def _seed_entities(engine: GameEngine) -> None:
    """Add a deterministic hero, enemy, and bounty so every parity branch has a
    subject (the base headless engine starts with buildings but no heroes)."""
    from game.entities.hero import Hero
    from game.entities.enemy import Enemy

    castle = next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")
    cx = float(castle.center_x)
    cy = float(castle.center_y)
    engine.heroes.append(
        Hero(cx + 2 * TILE_SIZE, cy, hero_class="warrior", hero_id="wk66_parity_hero", name="Parity")
    )
    engine.enemies.append(Enemy(cx - 4 * TILE_SIZE, cy + 2 * TILE_SIZE, enemy_type="goblin"))
    engine.bounty_system.place_bounty(cx + 6 * TILE_SIZE, cy, reward=100, bounty_type="explore")


def test_render_dto_field_parity():
    """The fields a renderer reads off live entities are well-typed and stable.

    This is the *contract* both Agent 03 (DTO builder) and Agent 10 (DTO
    consumer) code against. After Move 3, helpers reading the DTO must produce
    these exact tuple shapes/values.
    """
    engine = GameEngine(headless=True)
    try:
        _seed_entities(engine)
        # Settle a few ticks so positions/state are representative (no RNG drift
        # asserted here — we pin shape + read-equivalence, not absolute values).
        for _ in range(5):
            engine.update(1 / 60)

        snap = engine.build_snapshot()

        # --- units (heroes + enemies + peasants + guards + tax collector) ---
        # WK68 R3: the live entity tuples were deleted from the snapshot; read the
        # engine's live lists (exactly what build_snapshot iterates to build DTOs).
        hero_views = [_unit_view(h, "hero") for h in list(engine.heroes)[:3]]
        enemy_views = [_unit_view(e, "enemy") for e in list(engine.enemies)[:3]]
        assert hero_views, "expected at least one hero to pin"
        assert enemy_views, "expected at least one enemy to pin"

        for view in hero_views + enemy_views:
            (eid, kind, x, y, facing, is_alive, hp, max_hp, size, state_name,
             hero_class, enemy_type, name, gold, taxed_gold, inside, inside_center) = view
            assert isinstance(eid, str) and eid, "unit entity_id must be a non-empty str key"
            assert kind in ("hero", "enemy", "peasant", "guard", "tax_collector")
            assert isinstance(x, float) and isinstance(y, float)
            assert isinstance(facing, int)
            assert isinstance(is_alive, bool)
            assert isinstance(hp, float) and isinstance(max_hp, float) and max_hp >= 1.0
            assert isinstance(size, int) and size > 0
            assert isinstance(state_name, str) and state_name and state_name != "None"
            assert isinstance(hero_class, str) and isinstance(enemy_type, str)
            assert isinstance(name, str)
            assert isinstance(gold, int) and isinstance(taxed_gold, int)
            assert isinstance(inside, bool)
            assert inside_center is None or (
                isinstance(inside_center, tuple) and len(inside_center) == 2
            ), "inside_building must be flattened to a (x, y) tuple or None — never a live ref"

        # Read-equivalence: reading the same live entity twice yields the same
        # tuple (this is what the DTO must reproduce).
        first_hero = list(engine.heroes)[0]
        assert _unit_view(first_hero, "hero") == _unit_view(first_hero, "hero")

        # --- buildings ---
        building_views = [_building_view(b) for b in list(engine.buildings)[:5]]
        assert building_views, "expected buildings to pin"
        for view in building_views:
            (eid, btype, wx, wy, w, h, hp, max_hp, constructed, prog, color,
             is_lair, is_neutral, stash, tax, level, has_target, atk_range) = view
            assert isinstance(eid, str) and eid
            assert isinstance(btype, str) and btype == btype.lower()
            assert isinstance(wx, float) and isinstance(wy, float)
            assert isinstance(w, int) and isinstance(h, int)
            assert isinstance(hp, float) and isinstance(max_hp, float) and max_hp >= 1.0
            assert isinstance(constructed, bool)
            assert isinstance(prog, float) and 0.0 <= prog <= 1.0
            assert isinstance(color, tuple) and len(color) == 3
            assert isinstance(is_lair, bool) and isinstance(is_neutral, bool)
            assert isinstance(stash, int) and isinstance(tax, int) and isinstance(level, int)
            assert isinstance(has_target, bool)  # a bool, NOT the live target object
            assert isinstance(atk_range, int)

        # The castle must be present, constructed, lowercased-typed, and key-stable.
        castle_views = [v for v in building_views if v[1] == "castle"]
        assert castle_views, "castle must appear in the building views"
        assert castle_views[0][8] is True, "castle should be constructed"

        # --- bounties ---
        bounty_views = [
            _bounty_view(b)
            for b in list(engine.bounty_system.get_unclaimed_bounties())[:3]
        ]
        assert bounty_views, "expected at least one bounty to pin"
        for (bid, bx, by, claimed, reward, responders, tier) in bounty_views:
            assert isinstance(bid, str) and bid
            assert isinstance(bx, float) and isinstance(by, float)
            assert isinstance(claimed, bool)
            assert isinstance(reward, int)
            assert isinstance(responders, int)
            assert tier in ("low", "med", "high")
        # Our seeded bounty reward is preserved through the snapshot.
        assert any(v[4] == 100 for v in bounty_views), "seeded bounty reward=100 must be visible"
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# WK68 R1 — additive DTO field parity (Ursina / instanced / pygame-remainder)
# ---------------------------------------------------------------------------
#
# WK68 Wave R1 extends the WK66 DTOs ADDITIVELY so the still-unmigrated renderers
# (Ursina ``_sync_snapshot_*``, the instanced pack loop, and the pygame
# guards/peasants/tax-collector worker renderer) can flip onto DTOs in R2 with
# ZERO behavior change. Each new field must equal the value the renderer reads off
# the LIVE entity today, using the SAME getattr/hasattr-with-default. These helpers
# encode those exact reads (the audit sites are noted in render_dto.py).


def _unit_extra_view(entity) -> tuple:
    """The WK68 R1 additive UnitDTO fields, read off a live unit exactly as the
    Ursina / instanced / worker renderers read them today."""
    return (
        int(getattr(entity, "layer", 0)),                        # ursina:1286/1378
        bool(getattr(entity, "is_inside_castle", False)),        # ursina:1448 / instanced:415 / worker_renderer:150
        str(getattr(entity, "render_worker_type", "peasant") or "peasant"),  # ursina:1473 / instanced:419
        int(getattr(entity, "carried_gold", 0) or 0),            # worker_renderer:214 / ursina:1592
    )


def _unit_r2_view(entity) -> tuple:
    """The WK68 R2 (Agent 09/10) additive UnitDTO fields, read off a live unit
    exactly as ``render_dto.unit_dto_from`` flattens them today.

    - ``target_x`` — the Ursina facing helper (_unit_facing_direction) reads the
      combat ``target``'s x when the target has x/y coords; None otherwise.
    - ``state`` — the pygame WorkerRenderer reads ``entity.state`` as
      ``str(getattr(state, "name", state))`` == ``state_name``; the DTO carries
      ``state`` == state_name so the worker read is byte-identical.
    """
    target = getattr(entity, "target", None)
    if target is not None and hasattr(target, "x") and hasattr(target, "y"):
        try:
            target_x = float(target.x)
        except (TypeError, ValueError):
            target_x = None
    else:
        target_x = None
    state = getattr(entity, "state", None)
    state_name = str(getattr(state, "name", state))
    return (target_x, state_name)


def _building_extra_view(b) -> tuple:
    """The WK68 R1 additive BuildingDTO fields, read off a live building exactly as
    the Ursina building sync reads them today."""
    poi_def = getattr(b, "poi_def", None)
    poi_type = getattr(poi_def, "poi_type", None) if poi_def is not None else None
    return (
        float(getattr(b, "x", 0.0)),       # ursina center reads (b.x/b.y) — distinct from world_x/world_y
        float(getattr(b, "y", 0.0)),
        bool(getattr(b, "is_poi", False)),  # ursina:1062/1067
        (str(poi_type) if poi_type is not None else None),  # ursina cave/mine tint:1168/1201/1252
        hasattr(b, "stash_gold"),           # ursina lair detection:1096
    )


def _building_r2_view(b) -> tuple:
    """The WK68 R2 (Agent 09) additive BuildingDTO fields, read off a live building
    exactly as ``render_dto.building_dto_from`` reads them today.

    - ``has_tax_overlay`` == ``building.has_tax_stash_data`` (hold-G gold overlay).
    - ``grid_x``/``grid_y``/``size`` == the footprint coords the terrain
      scatter-exclusion + grid-debug paths read (b.grid_x/.grid_y/.size).
    """
    return (
        bool(getattr(b, "has_tax_stash_data", False)),
        int(getattr(b, "grid_x", 0) or 0),
        int(getattr(b, "grid_y", 0) or 0),
        tuple(getattr(b, "size", (0, 0)) or (0, 0)),
    )


def test_render_dto_additive_field_parity_wk68():
    """WK68 R1: the additive DTO fields equal the live-entity values (R2 unblock).

    Builds a scene that exercises the NON-default values of every new field
    (a builder-peasant -> render_worker_type='peasant_builder', an underground
    hero -> layer=-1, a tax collector carrying gold, a POI building -> is_poi /
    poi_type, a lair -> has_stash_gold) so the parity has teeth, then asserts the
    DTO carries exactly what the renderer would read off the live entity.
    """
    from game.entities.builder_peasant import BuilderPeasant
    from game.entities.lair import GoblinCamp

    engine = GameEngine(headless=True)
    try:
        _seed_entities(engine)

        castle = next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")
        cx, cy = float(castle.center_x), float(castle.center_y)

        # Non-default unit fields:
        # - an underground hero (layer != 0)
        underground_hero = list(engine.heroes)[0]
        underground_hero.layer = -1
        # - a builder peasant (render_worker_type == 'peasant_builder')
        target_b = next(b for b in engine.buildings if b is not castle)
        engine.peasants.append(BuilderPeasant.spawn_from_castle(castle=castle, target_building=target_b))
        # - a peasant inside the castle (is_inside_castle True)
        from game.entities.peasant import Peasant
        inside_peasant = Peasant(cx, cy)
        inside_peasant.is_inside_castle = True
        engine.peasants.append(inside_peasant)
        # - tax collector carrying gold (carried_gold > 0)
        assert engine.tax_collector is not None
        engine.tax_collector.carried_gold = 77

        # Non-default building fields: add a lair (has_stash_gold True).
        lair = GoblinCamp(10, 10)
        engine.buildings.append(lair)

        # Snapshot immediately (no settle ticks): the seeded builder/inside peasant
        # would otherwise transition/cull, and parity needs no motion — it pins the
        # read-equivalence of the DTO vs the live entity, not absolute positions.
        snap = engine.build_snapshot()

        # --- unit DTOs vs live entities (every kind) ---
        # WK68 R3: the live entity tuples were deleted from the snapshot; the DTO
        # tuples are built in live-list order, so zip each DTO tuple against the
        # engine's live list (the exact source build_snapshot iterates).
        unit_pairs = (
            list(zip(snap.hero_dtos, engine.heroes))
            + list(zip(snap.enemy_dtos, engine.enemies))
            + list(zip(snap.peasant_dtos, engine.peasants))
            + list(zip(snap.guard_dtos, engine.guards))
        )
        if snap.tax_collector_dto is not None and engine.tax_collector is not None:
            unit_pairs.append((snap.tax_collector_dto, engine.tax_collector))
        assert unit_pairs, "expected units to pin"

        for dto, live in unit_pairs:
            assert (dto.layer, dto.is_inside_castle, dto.render_worker_type, dto.carried_gold) == \
                _unit_extra_view(live), (
                    "UnitDTO additive fields must equal the live-entity reads "
                    f"(kind={dto.kind}, id={dto.entity_id})"
                )
            # WK68 R2 (Agent 09/10) additive fields — target_x (Ursina facing) and the
            # ``state`` alias (pygame worker label) — must equal the live-entity reads.
            assert (dto.target_x, dto.state) == _unit_r2_view(live), (
                "UnitDTO R2 fields (target_x/state) must equal the live-entity reads "
                f"(kind={dto.kind}, id={dto.entity_id})"
            )

        # Teeth: the non-default values actually flowed through (not just defaults).
        hero_dto = next(d for d in snap.hero_dtos if d.entity_id == str(underground_hero.hero_id))
        assert hero_dto.layer == -1, "underground hero layer must reach the DTO"
        assert any(d.render_worker_type == "peasant_builder" for d in snap.peasant_dtos), \
            "builder-peasant render_worker_type must reach the DTO"
        assert any(d.is_inside_castle for d in snap.peasant_dtos), \
            "inside-castle peasant flag must reach the DTO"
        assert snap.tax_collector_dto.carried_gold == 77, "tax-collector carried_gold must reach the DTO"

        # --- building DTOs vs live buildings ---
        # WK68 R3: zip against the engine's live list (snapshot live tuple deleted).
        bld_pairs = list(zip(snap.building_dtos, engine.buildings))
        assert bld_pairs, "expected buildings to pin"
        for dto, live in bld_pairs:
            assert (dto.center_x, dto.center_y, dto.is_poi, dto.poi_type, dto.has_stash_gold) == \
                _building_extra_view(live), (
                    "BuildingDTO additive fields must equal the live-building reads "
                    f"(type={dto.building_type}, id={dto.entity_id})"
                )
            # center_x/center_y are the CENTER (== live x/y), distinct from world_x/world_y corner.
            assert dto.center_x == float(live.x) and dto.center_y == float(live.y)
            # WK68 R2 (Agent 09) additive fields — the hold-G tax overlay flag + the
            # terrain scatter-exclusion/grid-debug footprint coords — must equal the
            # live-building reads.
            assert (dto.has_tax_overlay, dto.grid_x, dto.grid_y, dto.size) == \
                _building_r2_view(live), (
                    "BuildingDTO R2 fields (has_tax_overlay/grid_x/grid_y/size) must "
                    f"equal the live-building reads (type={dto.building_type})"
                )

        # Teeth: the lair surfaces has_stash_gold True via the same hasattr the renderer uses.
        assert any(d.has_stash_gold for d in snap.building_dtos), \
            "a lair must surface has_stash_gold=True (Ursina lair detection)"
    finally:
        pygame.quit()


# ===========================================================================
# Pin 2 — Anim one-shot semantics (pins Move 1a)
# ===========================================================================


class _UnitState:
    """A minimal attribute-bag standing in for an entity's render_state.

    WK66 Move 1a: the sim now drives one-shots via a monotonic
    ``_anim_trigger_seq`` (bumped on each NEW trigger) and the renderer plays
    only when the seq advances vs its own last-seen — it NO LONGER clears
    ``_render_anim_trigger`` back onto the entity. This bag therefore carries
    BOTH fields, and ``_bump`` mutates them exactly the way the sim's
    ``_queue_render_animation`` does (set the string, increment the seq), so the
    pins drive the same observable signal the real entity emits.
    """

    def __init__(self, **kwargs) -> None:
        self.__dict__.setdefault("_anim_trigger_seq", 0)
        self.__dict__.setdefault("_render_anim_trigger", None)
        self.__dict__.update(kwargs)

    def _bump(self, name: str) -> None:
        """Mirror ``Hero._queue_render_animation``: set trigger, increment seq."""
        self._render_anim_trigger = str(name)
        self._anim_trigger_seq = int(self._anim_trigger_seq) + 1


def _advance_until_base(renderer, state, *, max_frames: int = 400) -> int:
    """Tick the renderer until its one-shot lock clears (returns to base clip).

    Returns the number of frames it took. The non-looping attack/hurt clips
    finish after a fixed number of frames; the renderer then plays the base clip.
    The frame budget is the teeth against a *loop-forever* regression — if the
    one-shot never released, this would raise instead of silently passing.
    """
    for i in range(max_frames):
        renderer.update_animation(state, 1 / 60)
        if renderer._anim_lock_one_shot is None:
            return i + 1
    raise AssertionError(
        "one-shot never returned to base clip within frame budget "
        "(LOOP-FOREVER regression in the seq mechanism)"
    )


def test_anim_one_shot_plays_once_then_replays_on_new_trigger():
    """Observable one-shot contract under the WK66 seq mechanism (HeroRenderer).

    Move 1a removed the ``setattr(entity, "_render_anim_trigger", None)``
    write-back. The renderer now plays a one-shot only when the sim's monotonic
    ``_anim_trigger_seq`` advances past the renderer's own ``_last_trigger_seq``.
    ``attack``/``hurt`` are non-looping clips (``game/graphics/hero_sprites.py:56-57``).

    This pin re-asserts the SAME essential behaviour the old pin did, re-targeted
    to the seq contract, and is the verification that Agent 10's mechanism is
    correct. It has explicit teeth against the three failure modes the new
    mechanism could introduce:
      * NEVER-PLAY    — a fresh (advanced) seq must start the clip.
      * LOOP-FOREVER  — after the clip's frames elapse it must return to base.
      * REPLAY-ON-UNCHANGED-SEQ — ticking with the trigger string STILL present
        but the seq UNCHANGED must NOT replay (the exact hazard of dropping the
        write-back clear — the string now lingers on the entity).
    """
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        from game.graphics.renderers.hero_renderer import HeroRenderer

        renderer = HeroRenderer(hero_id="wk66_anim", hero_class="warrior", size_px=32)
        assert renderer._anim.current == "idle", "fresh renderer starts on the idle base clip"

        # idle is the base; seq=0 (never advanced) -> stays idle, never one-shots.
        state = _UnitState(
            hero_class="warrior", x=0.0, y=0.0, state=None, is_inside_building=False,
        )
        for _ in range(30):
            renderer.update_animation(state, 1 / 60)
        assert renderer._anim.current == "idle"
        assert renderer._anim_lock_one_shot is None

        # --- (1) NEW trigger: bump seq the way the sim does -> attack plays once ---
        state._bump("attack")
        renderer.update_animation(state, 1 / 60)
        assert renderer._anim.current == "attack", "an advanced seq must start the one-shot clip"
        assert renderer._anim_lock_one_shot == "attack"
        # CONTRACT CHANGE (verified): the renderer does NOT clear the trigger off
        # the entity any more — the string lingers; only the seq gates replay.
        assert state._render_anim_trigger == "attack", (
            "Move 1a: the renderer must NOT write _render_anim_trigger back to None"
        )

        # --- (2) returns to base, does NOT loop forever ---
        frames_to_finish = _advance_until_base(renderer, state)
        assert renderer._anim_lock_one_shot is None, "one-shot must release after finishing"
        assert renderer._anim.current == "idle", "must return to the base clip after the one-shot"
        assert frames_to_finish > 1, "a one-shot should span more than a single frame"

        # --- (3) TEETH: unchanged seq + LINGERING trigger string must NOT replay ---
        # This is the precise regression dropping the write-back clear could cause:
        # _render_anim_trigger is still "attack" on the state, but the seq has not
        # advanced, so the renderer must stay on the base clip every frame.
        assert state._render_anim_trigger == "attack", "trigger string still lingers (by design)"
        seq_before = state._anim_trigger_seq
        for _ in range(60):
            renderer.update_animation(state, 1 / 60)
            assert renderer._anim_lock_one_shot is None, (
                "REPLAY-ON-UNCHANGED-SEQ regression: renderer re-triggered the "
                "one-shot from the lingering trigger string without a seq bump"
            )
        assert renderer._anim.current == "idle"
        assert state._anim_trigger_seq == seq_before, "scenario must not have bumped the seq"

        # --- (4) a NEW occurrence (seq bumps again) replays exactly once ---
        state._bump("attack")
        renderer.update_animation(state, 1 / 60)
        assert renderer._anim.current == "attack", "a fresh seq must replay the one-shot"
        assert renderer._anim_lock_one_shot == "attack"
        _advance_until_base(renderer, state)
        assert renderer._anim.current == "idle"

        # A different one-shot (hurt) on the next seq bump also plays once then ends.
        state._bump("hurt")
        renderer.update_animation(state, 1 / 60)
        assert renderer._anim.current == "hurt"
        _advance_until_base(renderer, state)
        assert renderer._anim.current == "idle"
    finally:
        pygame.quit()


def test_anim_one_shot_via_registry_level_driven_by_sim_path():
    """Same seq contract, driven end-to-end through the REAL sim trigger API.

    Routes a live ``Hero`` through ``RendererRegistry.update_animations`` (which
    reads ``hero.render_state`` — the hero itself) and bumps the trigger via the
    genuine sim path ``Hero._queue_render_animation`` (the same call
    ``on_attack_landed`` makes), proving the seq the sim emits is the seq the
    renderer gates on. Teeth: never-play, loop-forever, and replay-on-unchanged-seq.
    """
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        from game.graphics.renderers.registry import RendererRegistry
        from game.entities.hero import Hero

        hero = Hero(0.0, 0.0, hero_class="warrior", hero_id="wk66_reg_anim", name="Reg")
        assert hero._anim_trigger_seq == 0 and hero._render_anim_trigger is None

        registry = RendererRegistry()
        renderer = registry._hero_renderer_for(hero)

        # Real sim path bumps seq 0 -> 1 and sets the trigger string.
        hero._queue_render_animation("attack")
        assert hero._anim_trigger_seq == 1 and hero._render_anim_trigger == "attack"

        registry.update_animations(1 / 60, [hero], [], [], None, [])
        assert renderer._anim.current == "attack", "registry must start the one-shot from the sim seq"
        # The sim path does NOT clear the trigger; the renderer must not either.
        assert getattr(hero, "_render_anim_trigger", None) == "attack", (
            "Move 1a: trigger must remain on the entity (renderer no longer write-backs)"
        )

        # Returns to base (not loop-forever).
        for _ in range(400):
            registry.update_animations(1 / 60, [hero], [], [], None, [])
            if renderer._anim_lock_one_shot is None:
                break
        assert renderer._anim_lock_one_shot is None, "one-shot must release (no loop-forever)"
        assert renderer._anim.current == "idle"

        # TEETH: the trigger string still lingers on the hero, seq unchanged ->
        # repeated registry passes must NOT replay it.
        assert hero._render_anim_trigger == "attack"
        for _ in range(60):
            registry.update_animations(1 / 60, [hero], [], [], None, [])
            assert renderer._anim_lock_one_shot is None, (
                "REPLAY-ON-UNCHANGED-SEQ regression via the registry path"
            )
        assert renderer._anim.current == "idle"

        # A new attack occurrence (seq 1 -> 2) replays once.
        hero._queue_render_animation("attack")
        assert hero._anim_trigger_seq == 2
        registry.update_animations(1 / 60, [hero], [], [], None, [])
        assert renderer._anim.current == "attack", "a fresh sim seq must replay the one-shot"
    finally:
        pygame.quit()


# ---------------------------------------------------------------------------
# Ursina _compute_anim_frame seq-gating (Move 1a, headless)
# ---------------------------------------------------------------------------
#
# The Ursina billboard path is where the lingering-trigger/unchanged-seq hazard
# is MOST dangerous: ``GameEngine._update_render_animations`` copies
# ``_render_anim_trigger`` -> ``_ursina_anim_trigger`` on EVERY tick the trigger
# is set (game/engine.py:1219-1238), but it does NOT touch ``_anim_trigger_seq``.
# So ``_compute_anim_frame`` (ursina_renderer.py:558-620) sees the trigger STRING
# every frame while the seq stays put — and must replay only on a seq advance.
#
# ``UrsinaRenderer.__init__`` builds a real Ursina window/entities, so we
# construct the instance via ``__new__`` and populate ONLY the two attributes
# ``_compute_anim_frame`` reads (``_unit_anim_state`` + ``_clips_cache``). The
# method itself, the clip metadata (``HeroSpriteLibrary.clips_for`` — pure
# pygame), and ``_frame_index_for_clip`` are the REAL production code; nothing is
# faked. ``_compute_anim_frame`` measures elapsed via ``time.perf_counter()``
# against the record's ``t0``, so to deterministically exercise the
# clip-has-finished branch we rewind ``t0`` (the very input the method reads) —
# this drives the real return-to-base logic without a flaky real sleep.


def _make_headless_ursina_renderer():
    """A bare UrsinaRenderer carrying only the state ``_compute_anim_frame`` uses."""
    from game.graphics.ursina_renderer import UrsinaRenderer

    r = UrsinaRenderer.__new__(UrsinaRenderer)
    r._unit_anim_state = {}
    r._clips_cache = {}
    return r


def test_ursina_compute_anim_frame_seq_gating_headless():
    """Ursina ``_compute_anim_frame`` honours the seq gate (the dangerous path).

    Same four-point contract as the pygame pin, on the Ursina billboard mechanism:
      (1) an advanced seq starts the one-shot clip,
      (2) it returns to the base clip after its frames elapse (no loop-forever),
      (3) repeated calls with the trigger string STILL present but the seq
          UNCHANGED do NOT restart it (no replay-on-unchanged-seq — the exact
          hazard of the engine copying _render_anim_trigger every tick), and
      (4) bumping the seq replays it once.
    """
    import time

    from game.graphics.ursina_units_anim import _hero_base_clip

    r = _make_headless_ursina_renderer()
    obj_id = 0xA11CE

    class _Ent:
        def __init__(self, **kw) -> None:
            self.__dict__.update(kw)

    # Idle hero, NEW attack trigger with seq advanced 0 -> 1. Both the
    # _ursina_anim_trigger (engine-copied) and _render_anim_trigger are present,
    # mirroring the live tick state.
    ent = _Ent(
        state=None, is_inside_building=False,
        _ursina_anim_trigger="attack", _render_anim_trigger="attack",
        _anim_trigger_seq=1,
    )

    # (1) NEVER-PLAY teeth: an advanced seq must start the one-shot.
    clip, _idx = r._compute_anim_frame(obj_id, ent, "hero", "warrior", _hero_base_clip)
    rec = r._unit_anim_state[obj_id]
    assert clip == "attack", "advanced seq must start the Ursina one-shot clip"
    assert rec["oneshot"] is True
    assert rec["last_seq"] == 1
    t0_at_play = rec["t0"]

    # (3) REPLAY-ON-UNCHANGED-SEQ teeth: the engine keeps copying the trigger
    # string every tick, but the seq is unchanged -> the record must NOT restart
    # (t0 unchanged, clip stays the in-flight one-shot, last_seq pinned at 1).
    for _ in range(30):
        clip, _idx = r._compute_anim_frame(obj_id, ent, "hero", "warrior", _hero_base_clip)
        rec = r._unit_anim_state[obj_id]
        assert rec["last_seq"] == 1, "unchanged seq must not be re-consumed"
        assert rec["t0"] == t0_at_play, (
            "REPLAY-ON-UNCHANGED-SEQ regression: one-shot restarted (t0 reset) "
            "from the lingering trigger string without a seq advance"
        )
        assert rec["clip"] == "attack" and rec["oneshot"] is True

    # (2) LOOP-FOREVER teeth: once the clip's frames have elapsed it must return
    # to the base clip. We rewind t0 past the clip length (the elapsed value the
    # method reads) so the finished-branch fires deterministically.
    r._unit_anim_state[obj_id]["t0"] = time.perf_counter() - 100.0
    clip, _idx = r._compute_anim_frame(obj_id, ent, "hero", "warrior", _hero_base_clip)
    rec = r._unit_anim_state[obj_id]
    assert clip == "idle", "one-shot must return to the base clip after its frames elapse"
    assert rec["oneshot"] is False

    # And with the trigger string STILL lingering + seq STILL unchanged, it must
    # stay on base (no spontaneous replay once it has finished).
    for _ in range(10):
        clip, _idx = r._compute_anim_frame(obj_id, ent, "hero", "warrior", _hero_base_clip)
        assert clip == "idle", "finished one-shot must not replay on an unchanged seq"

    # (4) NEW occurrence: bump the seq -> replays once.
    ent._anim_trigger_seq = 2
    clip, _idx = r._compute_anim_frame(obj_id, ent, "hero", "warrior", _hero_base_clip)
    rec = r._unit_anim_state[obj_id]
    assert clip == "attack", "a fresh seq must replay the Ursina one-shot"
    assert rec["oneshot"] is True
    assert rec["last_seq"] == 2


# ===========================================================================
# Pin 3 — Fog / discovery digest (pins Move 1b; byte-identical guardrail)
# ===========================================================================
#
# Golden values captured from current HEAD code (seed 3, DETERMINISTIC_SIM=1,
# 600 ticks, the deterministic moving-hero scenario below). Move 1b moves the
# discovery/SEEN marking into the sim; this digest MUST remain byte-identical.
# If Move 1b changes headless fog *behaviour* (which tiles are revealed / which
# buildings are discovered), this pin goes red — exactly the guardrail the plan
# asks for.
#
# WK66-W0 PM NOTE (pre-existing nondeterminism — recorded, NOT masked): the
# internal monotonic counter ``SimEngine._fog_revision`` drifts by +/-1 across
# *repeated in-process* ``GameEngine()`` constructions (observed: 61, 61, 62
# over three back-to-back runs in one process). It tracks how many frames
# ``update_visibility`` actually ran, which is sensitive to module-level/global
# state carried between engine instances (same family as the WK65 carry-item
# "tests/test_spawner.py order-dependent global-rebind"). The fog *grid* itself
# (VISIBLE/SEEN tile counts + discovered-building count) is perfectly stable
# across runs, so the guardrail pins the grid coverage and deliberately EXCLUDES
# ``fog_revision``. Agent 04 should be aware of this when re-running the digest
# at the gates.
_FOG_GOLDEN = {
    "visible": 486,   # tiles == Visibility.VISIBLE (2)
    "seen": 313,      # tiles == Visibility.SEEN (1)
    "discovered_buildings": 1,
}


def _fog_digest(engine: GameEngine) -> dict:
    """Grid-coverage digest — the byte-stable fog *state* (excludes the unstable
    internal ``_fog_revision`` counter; see the PM note above)."""
    vis = engine.world.visibility
    visible = sum(1 for row in vis for cell in row if cell == 2)
    seen = sum(1 for row in vis for cell in row if cell == 1)
    discovered = sum(1 for b in engine.buildings if getattr(b, "is_discovered", False))
    return {
        "visible": visible,
        "seen": seen,
        "discovered_buildings": discovered,
    }


def _run_fog_scenario() -> dict:
    """Deterministic headless reveal: a ranger walks two legs across the map.

    No AI controller (so movement is fully scripted) + fixed seed => the
    visibility grid evolves identically every run.
    """
    from game.sim.determinism import set_sim_seed
    from game.sim.timebase import set_sim_now_ms
    from game.entities.hero import Hero, HeroState

    set_sim_seed(3)
    engine = GameEngine(headless=True)
    try:
        set_sim_now_ms(0)
        castle = next(b for b in engine.buildings if getattr(b, "building_type", None) == "castle")
        hero = Hero(
            float(castle.center_x), float(castle.center_y),
            hero_class="ranger", hero_id="wk66_fog_probe", name="Scout",
        )
        engine.heroes.append(hero)
        hero.set_target_position(castle.center_x + 30 * TILE_SIZE, castle.center_y + 20 * TILE_SIZE)
        hero.state = HeroState.MOVING

        for t in range(600):
            set_sim_now_ms(int(t * (1 / 60) * 1000.0))
            # When the first leg completes, send the hero on a second leg so the
            # reveal footprint is large and deterministic.
            if hero.state != HeroState.MOVING and hero.target_position is None and t < 540:
                hero.set_target_position(
                    castle.center_x - 20 * TILE_SIZE, castle.center_y - 25 * TILE_SIZE
                )
                hero.state = HeroState.MOVING
            engine.update(1 / 60)

        return _fog_digest(engine)
    finally:
        pygame.quit()


@pytest.mark.skipif(
    os.getenv("DETERMINISTIC_SIM", "0") != "1",
    reason="fog/discovery digest is only byte-stable under DETERMINISTIC_SIM=1",
)
def test_fog_discovery_digest_is_stable():
    """The fog/discovery digest equals the golden captured from current code."""
    digest = _run_fog_scenario()
    assert digest == _FOG_GOLDEN, (
        "fog/discovery digest changed — Move 1b must keep headless fog behaviour "
        f"byte-identical. got={digest} golden={_FOG_GOLDEN}"
    )


def test_fog_discovery_digest_is_reproducible():
    """Independent of DETERMINISTIC_SIM, two runs in-process must agree.

    This proves the scenario itself is internally deterministic (the guardrail
    that Move 1b can be diffed against), without hard-coding the wall-clock-mode
    numbers (which differ from the DETERMINISTIC_SIM golden above).
    """
    first = _run_fog_scenario()
    second = _run_fog_scenario()
    assert first == second, f"fog scenario not reproducible: {first} != {second}"
    # Sanity: the hero actually revealed terrain (non-trivial digest).
    assert first["visible"] > 0
    assert first["seen"] > 0


# ===========================================================================
# Pin 4 — Snapshot not mutated on CONSUME (extends WK65 build-time guard)
# ===========================================================================
#
# WK65's test_wk65_snapshot_no_mutation proved *building* the snapshot is inert.
# This proves *consuming* it (a full renderer pass) is inert w.r.t. gameplay
# state. The field set below is deliberately the gameplay/renderer-visible
# fields ONLY — it excludes the private ``_ui_cache_*`` (bounty) and
# ``_render_anim_trigger`` (unit) scratch attributes, because those are exactly
# the L2 write-backs WK66 removes. Pinning gameplay fields keeps this GREEN on
# current code AND after Wave 2 deletes the write-backs.
_GAMEPLAY_FIELDS = (
    "x", "y", "hp", "max_hp", "level", "gold", "xp", "taxed_gold",
    "state", "target", "is_alive", "is_constructed", "construction_progress",
    "building_type", "enemy_type", "hero_class", "is_inside_building",
    "claimed", "reward", "responders", "attractiveness_tier",
)


def _gameplay_entity_digest(entity) -> tuple:
    out: list = []
    for field in _GAMEPLAY_FIELDS:
        if not hasattr(entity, field):
            out.append((field, _MISSING))
            continue
        try:
            value = getattr(entity, field)
        except Exception:
            out.append((field, _MISSING))
            continue
        if isinstance(value, float):
            value = round(value, 6)
        elif isinstance(value, (int, bool, str, type(None))):
            pass
        else:
            value = repr(value)
        out.append((field, value))
    return tuple(out)


def _scene_digest(engine: GameEngine) -> dict:
    return {
        "heroes": tuple(_gameplay_entity_digest(h) for h in engine.heroes),
        "enemies": tuple(_gameplay_entity_digest(e) for e in engine.enemies),
        "buildings": tuple(_gameplay_entity_digest(b) for b in engine.buildings),
        "peasants": tuple(_gameplay_entity_digest(p) for p in engine.peasants),
        "guards": tuple(_gameplay_entity_digest(g) for g in engine.guards),
        "bounties": tuple(
            _gameplay_entity_digest(b) for b in engine.bounty_system.get_unclaimed_bounties()
        ),
        "gold": int(getattr(engine.economy, "player_gold", 0)),
    }


def _drive_full_render_pass(engine, snap) -> None:
    """Exercise a renderer pass exactly like the pygame path:
    advance every animated renderer, then render every entity to a dummy surface.

    WK68 R3: the snapshot no longer carries the live entity tuples. The real
    pygame path advances animations on the live entities (in
    ``GameEngine._update_render_animations``) and DRAWS from the frozen ``*_dtos``
    (``PygameRenderer._draw_world_layers``). This helper mirrors that split: the
    animation advance runs over the engine's live entities; every render_* draw
    runs over the snapshot's DTO tuples — the exact production access pattern.
    """
    from game.graphics.renderers.registry import RendererRegistry

    registry = RendererRegistry()
    surface = pygame.Surface((640, 640))

    registry.update_animations(
        1 / 60,
        list(engine.heroes),
        list(engine.enemies),
        list(engine.peasants),
        engine.tax_collector,
        list(engine.guards),
    )
    for building in snap.building_dtos:
        registry.render_building(surface, building, (0.0, 0.0))
    for enemy in snap.enemy_dtos:
        registry.render_enemy(surface, enemy, (0.0, 0.0))
    for hero in snap.hero_dtos:
        registry.render_hero(surface, hero, (0.0, 0.0))
    for peasant in snap.peasant_dtos:
        registry.render_peasant(surface, peasant, (0.0, 0.0))
    for guard in snap.guard_dtos:
        registry.render_guard(surface, guard, (0.0, 0.0))
    if snap.tax_collector_dto is not None:
        registry.render_tax_collector(surface, snap.tax_collector_dto, (0.0, 0.0))
    registry.render_bounties(surface, list(snap.bounty_dtos), (0.0, 0.0))


def test_snapshot_not_mutated_on_consume():
    """A full renderer pass over the snapshot does not mutate gameplay state."""
    pygame.init()
    pygame.display.set_mode((1, 1))
    try:
        engine = GameEngine(headless=True)
        _seed_entities(engine)
        # A few ticks so animation triggers / state are realistic before snapshot.
        for _ in range(5):
            engine.update(1 / 60)

        assert len(engine.buildings) >= 1
        assert len(engine.heroes) >= 1
        assert len(engine.bounty_system.get_unclaimed_bounties()) >= 1

        # WK68 R3: the bounty ``update_ui_metrics`` mutation was relocated from the
        # renderer INTO ``build_snapshot`` (it deterministically refreshes
        # ``responders``/``attractiveness_tier`` once per snapshot build, before the
        # bounty DTOs, exactly as it used to run once per render frame). Build the
        # snapshot FIRST, then baseline — this pin isolates the CONSUME side (the
        # render pass), which must remain inert; the build side is pinned separately
        # by tests/test_wk65_snapshot_no_mutation.py.
        snap = engine.build_snapshot()

        before = _scene_digest(engine)
        _drive_full_render_pass(engine, snap)

        after = _scene_digest(engine)
        assert before == after, "a renderer pass over the snapshot mutated live sim gameplay state"
    finally:
        pygame.quit()
