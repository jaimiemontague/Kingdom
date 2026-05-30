"""WK68 Wave G3 (gate G) — Hire-Hero button regression tests (Agent 11 QA).

These tests INDEPENDENTLY verify Agent 08's just-landed **G2** work: a ``Hire Hero $100``
button on the 5 hirable buildings (the four guilds + a temple), wired so a click routes
through the REAL input path and recruits a hero.

Contract under test (read from ``game/ui/building_panel.py`` +
``game/input_handler.py`` + ``game/engine.try_hire_hero``):

* ``BuildingPanel._render_hire_hero_button`` only draws the button when the building's
  normalized type is in ``_HIRABLE_TYPES = {warrior_guild, ranger_guild, rogue_guild,
  wizard_guild, temple}`` AND ``building.is_constructed``. It stores a live
  ``hire_hero_button_rect`` (scroll-aware, like Enter/Demolish) ONLY when the button is
  ENABLED — i.e. ``building.can_hire()`` (``heroes_hired < max_heroes``) AND
  ``economy.player_gold >= HERO_HIRE_COST`` (100). When disabled or non-hirable,
  ``hire_hero_button_rect is None`` (no hit-rect → unclickable).
* ``handle_click`` at the (enabled) hire rect returns ``{"type":"hire_hero","building":b}``.
* ``InputHandler.handle_mousedown`` consumes that dict: sets ``selected_building`` to the
  guild then calls ``try_hire_hero()`` which deducts 100 gold, bumps ``heroes_hired``,
  spawns a ``Hero`` into ``engine.heroes`` (warrior_guild→warrior, temple→cleric), and
  emits a ``hero_hired`` event.

Goal: ALL of these PASS against current code.

  a. ``test_hire_success_through_real_input_path`` — gate G core: a real left
     ``MOUSEBUTTONDOWN`` at the hire hit-rect (game RUNNING) deducts 100 gold, +1
     ``heroes_hired``, +1 ``len(heroes)``, emits ``hero_hired``, new hero's home is the guild.
  b. ``test_cap_disabled_no_hire_rect_and_no_hire`` — guild at cap renders
     ``hire_hero_button_rect is None`` and a click there does not hire.
  c. ``test_broke_disabled_no_hire_rect_and_no_hire`` — gold < 100 → rect None; no hire.
  d. ``test_temple_is_hirable_and_hires_a_cleric`` — a constructed temple shows the hire
     button and hiring it adds a cleric.
  e. ``test_non_hirable_building_renders_no_hire_button`` — a marketplace (not hirable)
     renders NO hire button (``hire_hero_button_rect is None``).
"""

from __future__ import annotations

import os

# Headless SDL — mirror the G1 repro so the suite runs without a display/audio device
# (must be set before pygame is imported by the engine).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (after SDL env)

from config import HERO_HIRE_COST  # noqa: E402
from game.engine import GameEngine  # noqa: E402
from game.entities.buildings.temples import Temple  # noqa: E402
from game.input_manager import InputEvent  # noqa: E402

# A TALL left-column rect so a single building's panel fits with no overflow — every
# button (incl. the hire button, which renders lowest) is in-viewport. Width 360 / y=48
# mirror the real left-column width and the HUD top-bar offset.
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


def _select_and_render(engine: GameEngine, building, left_rect: pygame.Rect = _TALL_LEFT_RECT) -> None:
    """Select ``building`` and render its panel once into a throwaway surface."""
    engine.selected_building = building
    engine.building_panel.select_building(building, engine.heroes)
    surface = pygame.Surface((1280, 720))
    engine.building_panel.render(surface, engine.heroes, engine.economy, left_rect=left_rect)


def _viewport(panel) -> pygame.Rect:
    return pygame.Rect(panel.panel_x, panel.panel_y, panel.panel_width, panel.panel_height)


def _add_constructed_temple(engine: GameEngine) -> Temple:
    """Append a fully constructed Temple (no temple exists at game start) and return it."""
    temple = Temple(60, 60)
    temple.is_constructed = True
    engine.buildings.append(temple)
    return temple


# --------------------------------------------------------------------------------------
# a. HIRE SUCCESS via the REAL input path (gate G core)
# --------------------------------------------------------------------------------------
def test_hire_success_through_real_input_path():
    """Real left MOUSEBUTTONDOWN at the hire hit-rect recruits a hero from the guild.

    Game RUNNING (not paused). Routing the click through
    ``InputHandler.handle_mousedown`` must: deduct ``HERO_HIRE_COST`` (100) gold, bump the
    guild's ``heroes_hired`` by 1, append exactly one ``Hero`` to ``engine.heroes`` whose
    home is the guild, and emit a ``hero_hired`` event. This exercises the full chain
    ``building_panel.handle_click → input_handler hire_hero block → engine.try_hire_hero``.
    """
    engine = _make_engine()
    try:
        assert engine.paused is False, "game must be RUNNING for the hire full-path test"

        guild = _find_building(engine, "warrior_guild")
        assert getattr(guild, "is_constructed", True) is True
        assert guild.can_hire() and guild.heroes_hired < guild.max_heroes, (
            "warrior_guild must start under its hero cap"
        )
        assert engine.economy.player_gold >= HERO_HIRE_COST, "need >= 100 gold to hire"

        # Capture hero_hired via a real subscriber (flush dispatches the queued event).
        captured: list[dict] = []
        engine.event_bus.subscribe("hero_hired", lambda ev: captured.append(ev))

        _select_and_render(engine, guild)
        panel = engine.building_panel
        hire_rect = panel.hire_hero_button_rect
        assert hire_rect is not None, "enabled hire button must store a live hit-rect"
        assert _viewport(panel).collidepoint(hire_rect.center), (
            f"hire rect {hire_rect} center must be inside viewport {_viewport(panel)}"
        )

        gold_before = engine.economy.player_gold
        heroes_before = len(engine.heroes)
        hired_before = int(guild.heroes_hired)

        engine.input_handler.handle_mousedown(
            InputEvent(type="MOUSEDOWN", button=1, pos=hire_rect.center)
        )
        engine.event_bus.flush()

        assert engine.economy.player_gold == gold_before - HERO_HIRE_COST, (
            f"hire must deduct {HERO_HIRE_COST} gold; "
            f"{gold_before} → {engine.economy.player_gold}"
        )
        assert guild.heroes_hired == hired_before + 1, "guild.heroes_hired must increase by 1"
        assert len(engine.heroes) == heroes_before + 1, "exactly one hero must be spawned"

        new_hero = engine.heroes[-1]
        assert new_hero.home_building is guild, "new hero's home_building must be the guild"
        assert len(captured) == 1, (
            f"exactly one hero_hired event must fire; got {len(captured)}"
        )
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# b. CAP-DISABLED — guild at cap: no hit-rect, click does not hire
# --------------------------------------------------------------------------------------
def test_cap_disabled_no_hire_rect_and_no_hire():
    """A guild at its hero cap renders the hire button DISABLED (no hit-rect).

    ``can_hire()`` returns False when ``heroes_hired >= max_heroes``, so the renderer
    stores ``hire_hero_button_rect is None``. With no live hit-rect the button is
    unclickable; routing a click through the panel must not return ``hire_hero`` and
    a real input click must not spawn a hero or deduct gold.
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        guild.heroes_hired = guild.max_heroes  # at cap
        assert not guild.can_hire()
        assert engine.economy.player_gold >= HERO_HIRE_COST, "gold must be fine so ONLY cap disables"

        _select_and_render(engine, guild)
        panel = engine.building_panel
        assert panel.hire_hero_button_rect is None, (
            "guild at cap must render NO live hire hit-rect (button disabled)"
        )

        # A click at the would-be button area must NOT dispatch a hire_hero action.
        gold_before = engine.economy.player_gold
        heroes_before = len(engine.heroes)
        hired_before = int(guild.heroes_hired)
        # The enabled hire rect (when present) is the panel-width button near the bottom;
        # probe a point inside the panel bounds — there is no hire rect so nothing fires.
        probe = (panel.panel_x + panel.panel_width // 2, panel.panel_y + panel.panel_height - 30)
        result = panel.handle_click(probe, engine.economy, {})
        assert not (isinstance(result, dict) and result.get("type") == "hire_hero"), (
            f"capped guild must never dispatch hire_hero; got {result!r}"
        )
        assert engine.economy.player_gold == gold_before, "no gold may be spent"
        assert len(engine.heroes) == heroes_before, "no hero may be spawned"
        assert guild.heroes_hired == hired_before, "heroes_hired must stay at cap"
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# c. BROKE-DISABLED — gold < 100: no hit-rect, click does not hire
# --------------------------------------------------------------------------------------
def test_broke_disabled_no_hire_rect_and_no_hire():
    """When ``player_gold < HERO_HIRE_COST`` the hire button is DISABLED (no hit-rect).

    Same as the cap case but the disabling reason is affordability. The guild is under
    cap so ``can_hire()`` is True — only the gold gate trips. ``hire_hero_button_rect``
    must be None and no hire may occur.
    """
    engine = _make_engine()
    try:
        guild = _find_building(engine, "warrior_guild")
        assert guild.can_hire(), "guild must be under cap so ONLY low gold disables"
        engine.economy.player_gold = HERO_HIRE_COST - 1  # one short
        assert engine.economy.player_gold < HERO_HIRE_COST

        _select_and_render(engine, guild)
        panel = engine.building_panel
        assert panel.hire_hero_button_rect is None, (
            "guild with gold < HERO_HIRE_COST must render NO live hire hit-rect"
        )

        gold_before = engine.economy.player_gold
        heroes_before = len(engine.heroes)
        hired_before = int(guild.heroes_hired)
        probe = (panel.panel_x + panel.panel_width // 2, panel.panel_y + panel.panel_height - 30)
        result = panel.handle_click(probe, engine.economy, {})
        assert not (isinstance(result, dict) and result.get("type") == "hire_hero"), (
            f"broke guild must never dispatch hire_hero; got {result!r}"
        )
        assert engine.economy.player_gold == gold_before, "no gold may be spent"
        assert len(engine.heroes) == heroes_before, "no hero may be spawned"
        assert guild.heroes_hired == hired_before, "heroes_hired must be unchanged"
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# d. TEMPLE hirable — constructed temple shows hire button, hiring adds a cleric
# --------------------------------------------------------------------------------------
def test_temple_is_hirable_and_hires_a_cleric():
    """A constructed temple is in ``_HIRABLE_TYPES`` and hiring it recruits a Cleric.

    ``engine.try_hire_hero`` maps ``temple → HeroClass.CLERIC``. A real input click at the
    temple's hire hit-rect must spawn one hero whose ``hero_class`` is ``cleric`` and whose
    home is the temple, deducting 100 gold and bumping ``heroes_hired``.
    """
    engine = _make_engine()
    try:
        temple = _add_constructed_temple(engine)
        assert _bt(temple) == "temple"
        assert temple.can_hire() and engine.economy.player_gold >= HERO_HIRE_COST

        _select_and_render(engine, temple)
        panel = engine.building_panel
        hire_rect = panel.hire_hero_button_rect
        assert hire_rect is not None, "constructed temple must render an enabled hire button"
        assert _viewport(panel).collidepoint(hire_rect.center)

        gold_before = engine.economy.player_gold
        heroes_before = len(engine.heroes)
        hired_before = int(temple.heroes_hired)

        engine.input_handler.handle_mousedown(
            InputEvent(type="MOUSEDOWN", button=1, pos=hire_rect.center)
        )

        assert engine.economy.player_gold == gold_before - HERO_HIRE_COST
        assert temple.heroes_hired == hired_before + 1
        assert len(engine.heroes) == heroes_before + 1, "temple hire must spawn one hero"

        new_hero = engine.heroes[-1]
        assert new_hero.home_building is temple
        new_class = str(getattr(new_hero, "hero_class", "")).strip().lower()
        assert new_class == "cleric", f"temple must hire a cleric, got {new_class!r}"
    finally:
        pygame.quit()


# --------------------------------------------------------------------------------------
# e. NON-HIRABLE — marketplace renders no hire button
# --------------------------------------------------------------------------------------
def test_non_hirable_building_renders_no_hire_button():
    """A marketplace (not in ``_HIRABLE_TYPES``) renders NO hire button.

    The renderer early-returns with ``hire_hero_button_rect is None`` for any building
    whose type is not a guild/temple — so even a wealthy player viewing a marketplace
    sees no hire button and a panel click never dispatches ``hire_hero``.
    """
    engine = _make_engine()
    try:
        marketplace = _find_building(engine, "marketplace")
        assert _bt(marketplace) not in {
            "warrior_guild",
            "ranger_guild",
            "rogue_guild",
            "wizard_guild",
            "temple",
        }
        assert engine.economy.player_gold >= HERO_HIRE_COST, "gold is ample; type is what gates it"

        _select_and_render(engine, marketplace)
        panel = engine.building_panel
        assert panel.hire_hero_button_rect is None, (
            "a non-hirable building (marketplace) must render NO hire hit-rect"
        )
    finally:
        pygame.quit()
