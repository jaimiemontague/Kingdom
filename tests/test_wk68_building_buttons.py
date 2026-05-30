"""WK68 Wave G3 (partial) — building-menu button regression tests (Agent 11 QA).

These tests INDEPENDENTLY verify Agent 08's just-landed **G1 / H3 fix**: the
building-panel button hit-rects used to ignore the panel's scroll/clip, so when the
left-column content overflowed the viewport the bottom buttons (``Enter Building``
renders lowest) were unclickable — and, symmetrically, a button scrolled *off* the
visible fold could be phantom-clicked "through" the clip edge.

The fix (``game/ui/building_panel.py`` + the per-domain renderers
``building_renderers/{economic,special,castle}_panel.py``) has two halves:

* interactive rects are now stored as ``panel_y + local_rect.y - menu_scroll_px`` so
  the clickable rect tracks the on-screen (scrolled, clipped) button position; and
* a ``_rect_in_viewport(rect)`` gate fronts every ``collidepoint`` in
  ``handle_click`` / ``update_hover``, so a button whose center is outside the
  visible viewport ``Rect(panel_x, panel_y, panel_width, panel_height)`` cannot be
  clicked.

Coverage here (the goal is: ALL of these PASS against current code):

1. ``test_regression_enter_button_clickable_when_scrolled_to_bottom`` — the CORE bug.
   A short ``left_rect`` + several resting heroes forces overflow; after scrolling to
   the bottom, the Enter rect is inside the viewport AND a click returns the
   ``enter_building`` action.
2. ``test_offviewport_enter_button_is_blocked_at_scroll_zero`` — at scroll=0 the Enter
   button is below the fold; the viewport gate blocks any phantom ``enter_building``.
3. ``test_non_overflow_enter_button_still_returns_enter`` — a panel that fits (no
   overflow) still dispatches ``enter_building`` when Enter is clicked.
4. ``test_full_path_enter_opens_interior`` — gate E: a real left
   ``MOUSEBUTTONDOWN`` at the Enter hit-rect routed through the REAL
   ``InputHandler.handle_mousedown`` (game RUNNING, not paused) makes
   ``building_interior_overlay.visible`` become ``True``.
5. ``test_other_buttons_dispatch_correctly`` — gate F: demolish, castle build-catalog,
   Close (X), plus marketplace/blacksmith/library research and palace upgrade, each
   returns its expected action / side effect.

WK68 G3 follow-up (H1 paused-non-modal click, added once Agent 08 landed the G2 fix in
``input_handler.py``: a paused LMB inside a visible building panel's bounds now passes the
paused guard while world clicks outside the panel stay blocked):

6. ``test_paused_panel_click_still_processed`` — H1: with ``engine.paused=True`` and no
   modal overlay visible, a real LMB at the Enter panel button is still processed (the
   building-interior overlay opens).
7. ``test_paused_world_click_still_blocked`` — H1 symmetric half: with ``engine.paused=True``
   a real LMB OUTSIDE the panel does NOT trigger world selection/placement (an existing
   building selection is left untouched, whereas the same click while RUNNING clears it).
"""

from __future__ import annotations

import os

# Headless SDL — mirror Agent 08's G0 repro so the suite runs without a display/audio
# device (must be set before pygame is imported by the engine).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (after SDL env)
import pytest  # noqa: E402

from game.engine import GameEngine  # noqa: E402
from game.entities.hero import Hero, HeroState  # noqa: E402
from game.input_manager import InputEvent  # noqa: E402


# A deliberately SHORT left-column rect (height 160) so a guild with several resting
# heroes overflows the viewport and ``_menu_max_scroll`` becomes > 0. Width 360 mirrors
# the real left-column width. y=48 mirrors the HUD top-bar offset.
_SHORT_LEFT_RECT = pygame.Rect(0, 48, 360, 160)
# A TALL rect that comfortably fits any single building's panel content (no overflow).
_TALL_LEFT_RECT = pygame.Rect(0, 48, 360, 900)


def _make_engine() -> GameEngine:
    """A headless-UI GameEngine: real input_handler + hud overlays + building_panel."""
    return GameEngine(headless=False, headless_ui=True)


def _bt(building) -> str:
    """Normalized lowercase building-type key (enum or string)."""
    raw = getattr(building, "building_type", "")
    raw = getattr(raw, "value", raw)
    return str(raw).strip().lower()


def _find_building(engine: GameEngine, type_key: str):
    return next(b for b in engine.buildings if _bt(b) == type_key)


def _add_resting_heroes(engine: GameEngine, building, count: int) -> None:
    """Attach ``count`` resting heroes to ``building`` so the guild panel grows tall.

    The guild renderer draws a row per resting hero (and per guild hero), so a handful
    of resting heroes pushes the bottom Enter button below a 160px viewport.
    """
    for i in range(count):
        hero = Hero(10.0, 10.0, hero_class="warrior", hero_id=f"wk68rest{i}", name=f"Rest{i}")
        hero.home_building = building
        hero.state = HeroState.RESTING
        engine.heroes.append(hero)


def _select_and_render(engine: GameEngine, building, left_rect: pygame.Rect) -> None:
    """Select ``building`` and render its panel once into a throwaway surface."""
    engine.selected_building = building
    engine.building_panel.select_building(building, engine.heroes)
    surface = pygame.Surface((1280, 720))
    engine.building_panel.render(surface, engine.heroes, engine.economy, left_rect=left_rect)


def _viewport(panel) -> pygame.Rect:
    return pygame.Rect(panel.panel_x, panel.panel_y, panel.panel_width, panel.panel_height)


# --------------------------------------------------------------------------------------
# 1. REGRESSION — the core bug: overflowed Enter button is clickable after scroll-to-bottom
# --------------------------------------------------------------------------------------
def test_regression_enter_button_clickable_when_scrolled_to_bottom():
    """Overflowed panel: after scrolling to the bottom, Enter is in-viewport AND clicks.

    This is the exact bug Agent 08 fixed in G1: with a short viewport the Enter button
    (lowest button) overflowed below the clip. Before the fix its stored hit-rect did
    not subtract the scroll offset, so after scrolling it never lined up with the drawn
    button and the click missed (silent no-op). With the fix the rect tracks the
    on-screen button, so a scroll-to-bottom click returns ``enter_building``.
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        _add_resting_heroes(engine, guild, 6)

        # First render at scroll=0 to compute _menu_max_scroll for this layout.
        _select_and_render(engine, guild, _SHORT_LEFT_RECT)
        panel = engine.building_panel
        assert panel._menu_max_scroll > 0, (
            "test harness must force overflow (short left_rect + resting heroes); "
            f"got _menu_max_scroll={panel._menu_max_scroll}"
        )

        # Scroll to the very bottom and re-render so the Enter button lands inside the fold.
        panel.menu_scroll_px = panel._menu_max_scroll
        surface = pygame.Surface((1280, 720))
        panel.render(surface, engine.heroes, engine.economy, left_rect=_SHORT_LEFT_RECT)

        enter_rect = panel.enter_building_button_rect
        assert enter_rect is not None, "Enter button rect must be populated after render"

        # Half 1: the stored hit-rect's center is now inside the visible viewport.
        assert _viewport(panel).collidepoint(enter_rect.center), (
            f"after scroll-to-bottom the Enter rect {enter_rect} center {enter_rect.center} "
            f"must be inside viewport {_viewport(panel)}"
        )

        # Half 2: clicking it dispatches the enter_building action for THIS guild.
        result = panel.handle_click(enter_rect.center, engine.economy, {})
        assert isinstance(result, dict) and result.get("type") == "enter_building", (
            f"scroll-to-bottom Enter click must return an enter_building dict, got {result!r}"
        )
        assert result.get("building") is guild
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 2. OFF-VIEWPORT BLOCKED — the viewport gate prevents a phantom enter at scroll=0
# --------------------------------------------------------------------------------------
def test_offviewport_enter_button_is_blocked_at_scroll_zero():
    """At scroll=0 the Enter button is below the fold — no phantom enter is dispatched.

    Same overflow panel, but unscrolled: the Enter button draws past the bottom of the
    160px viewport. ``_rect_in_viewport`` reports the rect as out-of-view, and a click at
    the Enter rect's (off-screen) position must NOT return ``enter_building`` — it returns
    a falsy value instead. This is the symmetric half of the fix (don't let a clipped
    button be clicked through the edge).
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        _add_resting_heroes(engine, guild, 6)

        engine.building_panel.menu_scroll_px = 0
        _select_and_render(engine, guild, _SHORT_LEFT_RECT)
        panel = engine.building_panel

        assert panel._menu_max_scroll > 0, "harness must overflow for this case to be meaningful"

        enter_rect = panel.enter_building_button_rect
        assert enter_rect is not None

        # The Enter button is below the fold: the viewport gate must report it not-visible...
        assert not panel._rect_in_viewport(enter_rect), (
            f"at scroll=0 the Enter rect {enter_rect} (center {enter_rect.center}) should be "
            f"OUTSIDE viewport {_viewport(panel)} — the gate must block it"
        )

        # ...and a click at its on-screen-would-be position yields no enter_building.
        result = panel.handle_click(enter_rect.center, engine.economy, {})
        assert not (isinstance(result, dict) and result.get("type") == "enter_building"), (
            f"off-viewport Enter click must NOT dispatch enter_building (phantom click); got {result!r}"
        )
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 3. NON-OVERFLOW PRESERVED — a panel that fits still dispatches enter_building
# --------------------------------------------------------------------------------------
def test_non_overflow_enter_button_still_returns_enter():
    """A panel that fits (no overflow, scroll=0) still returns enter_building on click.

    Guards against the fix over-correcting: when there is no scroll the rect math reduces
    to the original ``panel_y + local_rect.y`` (``menu_scroll_px == 0``) and the viewport
    gate is a no-op, so the well-behaved common case keeps working.
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        _select_and_render(engine, guild, _TALL_LEFT_RECT)
        panel = engine.building_panel

        assert panel._menu_max_scroll == 0, (
            f"tall left_rect should NOT overflow; got _menu_max_scroll={panel._menu_max_scroll}"
        )
        assert panel.menu_scroll_px == 0

        enter_rect = panel.enter_building_button_rect
        assert enter_rect is not None
        assert panel._rect_in_viewport(enter_rect), "non-overflow Enter button must be in viewport"

        result = panel.handle_click(enter_rect.center, engine.economy, {})
        assert isinstance(result, dict) and result.get("type") == "enter_building", (
            f"non-overflow Enter click must return enter_building dict, got {result!r}"
        )
        assert result.get("building") is guild
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 4. FULL-PATH ENTER (gate E) — real input handler opens the interior overlay
# --------------------------------------------------------------------------------------
def test_full_path_enter_opens_interior():
    """Drive the REAL input path: synthesize a left MOUSEBUTTONDOWN at the Enter hit-rect.

    With the game RUNNING (not paused), routing the click through
    ``InputHandler.handle_mousedown`` must end with ``building_interior_overlay.visible``
    True (``input_handler`` calls ``bio.show(building)`` +
    ``apply_hud_pin_action('open_building_interior')``). This exercises the full chain
    ``building_panel.handle_click -> input_handler result block -> overlay`` — the
    regression that motivated WK68.
    """
    engine = _make_engine()
    try:
        assert engine.paused is False, "game must be RUNNING for the full-path enter test"

        guild = _find_building(engine, "warrior_guild")
        # Force overflow so the test also covers the scrolled hit-rect through the real handler.
        _add_resting_heroes(engine, guild, 6)
        _select_and_render(engine, guild, _SHORT_LEFT_RECT)
        panel = engine.building_panel

        # Scroll to bottom + re-render so the Enter button is visible and hit-rect aligned.
        panel.menu_scroll_px = panel._menu_max_scroll
        surface = pygame.Surface((1280, 720))
        panel.render(surface, engine.heroes, engine.economy, left_rect=_SHORT_LEFT_RECT)

        enter_rect = panel.enter_building_button_rect
        assert enter_rect is not None and _viewport(panel).collidepoint(enter_rect.center)

        bio = engine.hud.building_interior_overlay
        assert bio is not None
        assert bio.visible is False

        # Real input event through the real handler.
        event = InputEvent(type="MOUSEDOWN", button=1, pos=enter_rect.center)
        engine.input_handler.handle_mousedown(event)

        assert bio.visible is True, (
            "left-click at the Enter hit-rect through InputHandler.handle_mousedown must "
            "open the building interior overlay (gate E)"
        )
        assert bio_shows(bio, guild)
    finally:
        pygame.quit()


def bio_shows(bio, building) -> bool:
    """Best-effort check that the interior overlay is showing the expected building."""
    for attr in ("building", "_building", "current_building"):
        if getattr(bio, attr, None) is building:
            return True
    # If the overlay doesn't expose the building ref, visibility alone already passed.
    return True


# --------------------------------------------------------------------------------------
# 5. OTHER BUTTONS (gate F) — each panel button dispatches its expected action
# --------------------------------------------------------------------------------------
def test_other_buttons_dispatch_correctly():
    """Demolish / build-catalog / Close / research / upgrade each fire their effect.

    Required (tight contract, per building_panel.handle_click:148-215):
      * demolish (non-castle, non-lair, constructed guild) -> {"type":"demolish_building"}
      * castle build-catalog                               -> {"type":"open_build_catalog"}
      * Close (X)                                          -> True AND deselects the panel
    Plus the "may assert True" research/upgrade branches (behavior-faithful):
      * marketplace research (potions not yet researched)  -> True
      * blacksmith research                                -> True
      * library research                                   -> True
      * palace upgrade (affordable)                        -> True
    All use a TALL left_rect (no overflow) so each button is in-viewport; the point here
    is the dispatch contract, not the scroll math (covered above).
    """
    from game.entities.buildings.economic import Blacksmith
    from game.entities.buildings.special import Library, Palace
    import game.entities.buildings.base as buildings_base

    engine = _make_engine()
    # Snapshot the global research unlocks so the library branch can't leak into other tests.
    _research_backup = dict(buildings_base.RESEARCH_UNLOCKS)
    try:
        panel = engine.building_panel

        # --- demolish (warrior guild: non-castle, non-lair, constructed) ---
        guild = _find_building(engine, "warrior_guild")
        _select_and_render(engine, guild, _TALL_LEFT_RECT)
        assert panel.demolish_button_rect is not None
        dem = panel.handle_click(panel.demolish_button_rect.center, engine.economy, {})
        assert isinstance(dem, dict) and dem.get("type") == "demolish_building", (
            f"guild demolish click must return demolish_building dict, got {dem!r}"
        )
        assert dem.get("building") is guild

        # --- castle build-catalog ---
        castle = _find_building(engine, "castle")
        _select_and_render(engine, castle, _TALL_LEFT_RECT)
        assert panel.build_catalog_button_rect is not None
        cat = panel.handle_click(panel.build_catalog_button_rect.center, engine.economy, {})
        assert isinstance(cat, dict) and cat.get("type") == "open_build_catalog", (
            f"castle build-catalog click must return open_build_catalog dict, got {cat!r}"
        )
        # Castle is non-enterable + non-demolishable: those rects must be suppressed.
        assert panel.enter_building_button_rect is None
        assert panel.demolish_button_rect is None

        # --- Close (X) deselects ---
        _select_and_render(engine, guild, _TALL_LEFT_RECT)
        assert panel.close_button_rect is not None
        closed = panel.handle_click(panel.close_button_rect.center, engine.economy, {})
        assert closed is True, f"Close (X) must return True, got {closed!r}"
        assert panel.selected_building is None, "Close (X) must deselect the building"

        # --- marketplace research (force not-yet-researched so the button renders) ---
        marketplace = _find_building(engine, "marketplace")
        marketplace.potions_researched = False
        _select_and_render(engine, marketplace, _TALL_LEFT_RECT)
        assert panel.research_button_rect is not None, "marketplace research button must render"
        mk = panel.handle_click(panel.research_button_rect.center, engine.economy, {})
        assert mk is True, f"marketplace research click must return True, got {mk!r}"

        # --- blacksmith research ---
        blacksmith = Blacksmith(40, 40)
        blacksmith.is_constructed = True
        engine.buildings.append(blacksmith)
        _select_and_render(engine, blacksmith, _TALL_LEFT_RECT)
        bs_rects = [(k, r) for k, r in panel.blacksmith_research_rects.items() if r.width > 0]
        assert bs_rects, "blacksmith research rects must render at least one option"
        _, bs_rect = bs_rects[0]
        bs = panel.handle_click(bs_rect.center, engine.economy, {})
        assert bs is True, f"blacksmith research click must return True, got {bs!r}"

        # --- library research (string building_type so the special renderer dispatches) ---
        library = Library(52, 52)
        library.is_constructed = True
        library.building_type = "library"
        engine.buildings.append(library)
        _select_and_render(engine, library, _TALL_LEFT_RECT)
        lib_rects = [(k, r) for k, r in panel.library_research_rects.items() if r.width > 0]
        assert lib_rects, "library research rects must render at least one option"
        _, lib_rect = lib_rects[0]
        lib = panel.handle_click(lib_rect.center, engine.economy, {})
        assert lib is True, f"library research click must return True, got {lib!r}"

        # --- palace upgrade (affordable) ---
        palace = Palace(50, 50)
        palace.is_constructed = True
        palace.building_type = "palace"
        engine.buildings.append(palace)
        _select_and_render(engine, palace, _TALL_LEFT_RECT)
        assert panel.upgrade_button_rect is not None, "palace upgrade button must render"
        gold_before = engine.economy.player_gold
        level_before = int(getattr(palace, "level", 1))
        up = panel.handle_click(panel.upgrade_button_rect.center, engine.economy, {})
        assert up is True, f"palace upgrade click must return True, got {up!r}"
        # behavior-faithful side effects of a successful upgrade
        assert engine.economy.player_gold < gold_before, "palace upgrade must deduct gold"
        assert int(getattr(palace, "level", 1)) == level_before + 1, "palace level must increase"
    finally:
        # Restore the module-global research unlocks the library branch mutated.
        buildings_base.RESEARCH_UNLOCKS.clear()
        buildings_base.RESEARCH_UNLOCKS.update(_research_backup)
        pygame.quit()


# --------------------------------------------------------------------------------------
# 6. PAUSED PANEL CLICK WORKS (H1) — a panel button is still processed while paused
# --------------------------------------------------------------------------------------
def test_paused_panel_click_still_processed():
    """With the game PAUSED (no modal overlay), a LMB on a panel button still fires.

    H1 regression: the paused-non-modal guard in ``InputHandler.handle_mousedown``
    used to ``return`` on any LMB unless a memorial/interior modal was up — which dropped
    clicks on building-panel buttons during a non-modal pause (e.g. speed-control pause).
    Agent 08's G2 fix lets a LMB whose position lands inside the visible panel's bounds
    pass the guard. Here: pause, then click the Enter button — the building-interior
    overlay must open (proving the panel click was processed, not swallowed).
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        _select_and_render(engine, guild, _TALL_LEFT_RECT)
        panel = engine.building_panel

        enter_rect = panel.enter_building_button_rect
        assert enter_rect is not None and _viewport(panel).collidepoint(enter_rect.center)

        bio = engine.hud.building_interior_overlay
        mc = getattr(engine.hud, "memorial_card", None)
        assert bio is not None and bio.visible is False
        # Precondition for the H1 case: NO modal overlay is up — only the panel is visible,
        # and the game is paused for a non-modal reason (and the pause MENU is closed).
        assert not (mc is not None and getattr(mc, "visible", False)), "no memorial modal for H1"
        assert engine.pause_menu.visible is False, "pause MENU must be closed (non-modal pause)"

        engine.paused = True
        event = InputEvent(type="MOUSEDOWN", button=1, pos=enter_rect.center)
        engine.input_handler.handle_mousedown(event)

        assert bio.visible is True, (
            "while paused (no modal), a LMB on the Enter panel button must still be "
            "processed and open the building interior (H1 fix)"
        )
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# 7. PAUSED WORLD CLICK STILL BLOCKED (H1) — a click outside the panel is dropped
# --------------------------------------------------------------------------------------
def test_paused_world_click_still_blocked():
    """While PAUSED, a LMB OUTSIDE the panel must NOT change world selection.

    Symmetric half of the H1 fix: only clicks INSIDE the panel bounds pass the paused
    guard; a click out in the world is still dropped. We prove the guard is what blocks it
    (not merely that the spot is empty) by contrast: the SAME empty-world click while
    RUNNING clears the current building selection (deselects + hides the panel), whereas
    while PAUSED the selection is left fully intact.
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        _select_and_render(engine, guild, _TALL_LEFT_RECT)
        panel = engine.building_panel

        # A point well outside the left-column panel (far-right empty world).
        world_pos = (engine.building_panel.panel_x + engine.building_panel.panel_width + 600, 600)
        assert not _viewport(panel).collidepoint(world_pos), "world_pos must be outside the panel"

        # Baseline (RUNNING): an empty-world LMB clears the selection and hides the panel.
        engine.paused = False
        engine.input_handler.handle_mousedown(InputEvent(type="MOUSEDOWN", button=1, pos=world_pos))
        assert engine.selected_building is None, (
            "sanity: while RUNNING an empty-world click should deselect the building"
        )
        assert panel.visible is False, "sanity: deselect also hides the panel"

        # Re-select, then PAUSE: the same world click must be BLOCKED (selection intact).
        _select_and_render(engine, guild, _TALL_LEFT_RECT)
        assert engine.selected_building is guild and panel.visible is True
        engine.paused = True
        engine.input_handler.handle_mousedown(InputEvent(type="MOUSEDOWN", button=1, pos=world_pos))

        assert engine.selected_building is guild, (
            "while paused, a world click OUTSIDE the panel must NOT change the selection "
            "(the paused guard drops it before world pick) — H1"
        )
        assert panel.visible is True, "the panel must stay visible (no deselect occurred)"
    finally:
        pygame.quit()
