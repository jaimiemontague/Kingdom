"""WK100 Round B-17 seam + behavior test (Agent 11 / QA): the layout-orchestration
trio was moved VERBATIM from ``game/ui/hud.py`` into the existing
``game/ui/hud_left_layout.py`` (WK99's module) as module functions — the EIGHTH
bounded slice of the hud.py god-file and the THIRD/FINAL of the left-column/layout
cluster (after WK99 segments/split/drag + WK98 watch-card geometry):

The 3 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``layout_rects_for_screen(hud, w, h, *, show_right_panel, game_state=None)``
      (was ``HUD._layout_rects_for_screen`` — delegates core rects to
       ``HUDLayoutManager`` then overlays the left-column segment allocation;
       ``show_right_panel`` is KEYWORD-ONLY)
* ``compute_layout(hud, surface, game_state=None)``
      (was ``HUD._compute_layout`` — sets screen_w/h on the HUD then returns the
       9-rect tuple consumed by render())
* ``virtual_pointer_in_hud_chrome(hud, pos, surface, game_state)``
      (was ``HUD.virtual_pointer_in_hud_chrome`` — the PUBLIC pointer hit-test used
       by ``game/graphics/ursina_app.py`` to decide whether a screen coord lies over
       HUD chrome vs the world)

``HUD`` keeps 1-line delegating wrappers (same names + signatures — including the
PUBLIC, non-underscore ``virtual_pointer_in_hud_chrome`` that ursina_app's pointer
routing calls, and the keyword-only ``*, show_right_panel`` on
``_layout_rects_for_screen``) that forward to the module functions with the HUD
instance first, so every call site is UNCHANGED. ALL state + the ``HUDLayoutManager``
instance (``hud._layout_mgr``) STAY on HUD; the moved functions reach them via ``hud``.

This guards the refactor SEAM **and** the behavior (``_compute_layout`` drives EVERY
HUD rect placement every frame; the pointer hit-test is invisible so the steady-state
screenshots alone don't exercise it — the behavior test below proves both run through
the moved path):

* each moved function lives on ``hud_left_layout``, is callable, takes ``hud`` first,
  and ``layout_rects_for_screen``'s ``show_right_panel`` is keyword-only;
* each ``HUD`` wrapper DELEGATES to the matching ``hud_left_layout`` module function
  (proved by a real monkeypatch-of-the-module-fn spy — incl. the PUBLIC one);
* AST guard: ``hud_left_layout.py`` has NO module-top (runtime) import of
  ``game.ui.hud`` (a ``TYPE_CHECKING``-only ``from game.ui.hud import HUD`` is allowed)
  + a fresh interpreter imports both module orders without a cycle;
* a headless HUD with a selected+pinned hero drives ``_compute_layout`` /
  ``_layout_rects_for_screen`` to a 9-rect tuple and ``virtual_pointer_in_hud_chrome``
  to True (point inside the left panel when a hero is selected) and False (empty gs).
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when hud / pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import game.ui.hud_left_layout as hud_left_layout
from game.ui.hud import HUD


# The 3 functions WK100 moved into hud_left_layout.py.
MOVED_FUNCTIONS = (
    "layout_rects_for_screen",
    "compute_layout",
    "virtual_pointer_in_hud_chrome",
)

# HUD wrapper-name -> hud_left_layout module-function-name (the delegation contract).
# NOTE: virtual_pointer_in_hud_chrome's wrapper is PUBLIC (no leading underscore) —
# ursina_app.py:727 calls hud.virtual_pointer_in_hud_chrome(...) by that exact name.
WRAPPER_TO_FN = {
    "_layout_rects_for_screen": "layout_rects_for_screen",
    "_compute_layout": "compute_layout",
    "virtual_pointer_in_hud_chrome": "virtual_pointer_in_hud_chrome",
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 3 module fns (hud-first) on hud_left_layout, show_right_panel kwonly.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_left_layout(name: str) -> None:
    """The moved function is present on hud_left_layout and callable."""
    assert hasattr(hud_left_layout, name), f"{name} missing from hud_left_layout"
    assert callable(getattr(hud_left_layout, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    sig = inspect.signature(getattr(hud_left_layout, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", f"{name} first param is {params[0]!r}, expected 'hud'"


def test_layout_rects_for_screen_show_right_panel_is_keyword_only() -> None:
    """``show_right_panel`` must stay KEYWORD-ONLY on layout_rects_for_screen (callers pass
    it by keyword; a drift to positional would break the wrapper / call-site contract)."""
    sig = inspect.signature(hud_left_layout.layout_rects_for_screen)
    assert "show_right_panel" in sig.parameters, "show_right_panel param missing"
    assert (
        sig.parameters["show_right_panel"].kind == inspect.Parameter.KEYWORD_ONLY
    ), "show_right_panel must be KEYWORD_ONLY (defined after `*`)"


# ------------------------------------------------------------------
# (2) WRAPPERS DELEGATE: HUD defines the 3 wrappers and forwards to hud_left_layout.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name — including the PUBLIC virtual_pointer_in_hud_chrome."""
    assert hasattr(HUD, wrapper), f"HUD missing wrapper {wrapper}"
    assert callable(getattr(HUD, wrapper)), f"HUD.{wrapper} is not callable"


def _bare_hud() -> HUD:
    """A bare ``HUD`` instance with no ``__init__`` run.

    Constructing a real HUD pulls in a large pygame/UI stack; ``object.__new__`` gives us
    an instance whose bound wrapper method we can call without that construction. The
    wrapper doesn't touch any instance state itself — it just forwards ``self`` to the
    module function — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(HUD)


def test_layout_rects_for_screen_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch-delegation proof through ``HUD._layout_rects_for_screen``: replace
    ``hud_left_layout.layout_rects_for_screen`` with a sentinel spy, call the wrapper on a
    bare instance, assert the spy fired with the HUD forwarded as ``self`` (first arg), the
    keyword-only ``show_right_panel`` forwarded, and the wrapper returning the module result.
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, w, h_, *, show_right_panel, game_state=None):  # noqa: ANN001 - test spy
        calls.append((hh, w, h_, show_right_panel, game_state))
        return sentinel

    monkeypatch.setattr(hud_left_layout, "layout_rects_for_screen", spy)

    state_marker = object()
    result = h._layout_rects_for_screen(1920, 1080, show_right_panel=False, game_state=state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, w, h_, show_right_panel, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert w == 1920 and h_ == 1080, "w/h must be forwarded"
    assert show_right_panel is False, "keyword-only show_right_panel must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_compute_layout_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch-delegation proof through ``HUD._compute_layout`` (the render() entry point)."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, game_state=None):  # noqa: ANN001 - test spy
        calls.append((hh, surface, game_state))
        return sentinel

    monkeypatch.setattr(hud_left_layout, "compute_layout", spy)

    surface_marker = object()
    state_marker = object()
    result = h._compute_layout(surface_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_virtual_pointer_in_hud_chrome_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch-delegation proof through the PUBLIC ``HUD.virtual_pointer_in_hud_chrome``
    wrapper (ursina_app.py:727 routes pointer hit-tests through this EXACT name)."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, pos, surface, game_state):  # noqa: ANN001 - test spy
        calls.append((hh, pos, surface, game_state))
        return sentinel

    monkeypatch.setattr(hud_left_layout, "virtual_pointer_in_hud_chrome", spy)

    pos_marker = (12, 34)
    surface_marker = object()
    state_marker = object()
    result = h.virtual_pointer_in_hud_chrome(pos_marker, surface_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, pos, surface, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert pos is pos_marker, "pos must be forwarded"
    assert surface is surface_marker, "surface must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


# ------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD: hud_left_layout has no module-top runtime import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_left_layout_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_left_layout must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_left_layout). A ``TYPE_CHECKING``-only
    ``from game.ui.hud import HUD`` is allowed (not a runtime import), so we walk only
    module-level statements and skip the body of an ``if TYPE_CHECKING:`` block."""
    src_path = Path(hud_left_layout.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []

    def _is_hud(mod: str) -> bool:
        return mod == "game.ui.hud" or mod.endswith(".hud")

    for node in ast.iter_child_nodes(tree):  # module-top statements only
        # Permit imports that live inside `if TYPE_CHECKING:` — they are not runtime imports.
        if isinstance(node, ast.If):
            test = node.test
            is_type_checking = (
                isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
            ) or (
                isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
            )
            if is_type_checking:
                continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_hud(alias.name):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if _is_hud(node.module or ""):
                offenders.append(f"from {node.module} import ...")
    assert not offenders, (
        "hud_left_layout has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_left_layout", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_left_layout"),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a module-load
    cycle. Runs out-of-process so already-imported modules in this session cannot mask an
    import-order bug."""
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    code = (
        "import importlib;"
        f"importlib.import_module({first!r});"
        f"importlib.import_module({second!r});"
        "print('OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, (
        f"fresh import {first} -> {second} failed (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "OK" in proc.stdout, f"missing OK marker. STDOUT:\n{proc.stdout}"


# ------------------------------------------------------------------
# (4) BEHAVIOR: drive compute_layout / layout_rects_for_screen / pointer hit-test through
#     the moved wrappers on a headless HUD with a selected + pinned hero.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) — has the real layout state
    (``_layout_mgr`` / ``_pin_slot`` / ``screen_width`` / ``_left_split_handle_rects`` / …),
    so the moved functions can reach them via ``hud``."""
    pygame.init()
    return HUD(1920, 1080)


def _hero_selected_pinned_state() -> dict:
    """A game_state with a selected hero whose profile is pinned (mirror test_wk52_r10):
    selecting a hero makes the left panel a hit-region; pinning it (``_pin_slot.hero_id``)
    exercises the watch-card branches in virtual_pointer_in_hud_chrome."""
    return {
        "selected_hero": object(),
        "selected_peasant": None,
        "selected_building": None,
        "selected_enemy": None,
        "hero_profiles_by_id": {"p1": object()},
    }


def test_compute_layout_returns_nine_rects_and_sets_screen_dims(headless_hud: HUD) -> None:
    """``hud._compute_layout`` (-> hud_left_layout.compute_layout) returns the full 9-rect
    tuple of pygame.Rects, records the surface dims on the HUD, and places the top bar at
    y==0 and the bottom bar flush to the screen bottom — proving the layout math runs
    through the moved path WITHOUT raising."""
    hud = headless_hud
    hud._pin_slot.hero_id = "p1"
    gs = _hero_selected_pinned_state()
    surface = pygame.Surface((1920, 1080))

    rects = hud._compute_layout(surface, gs)  # must not raise

    assert len(rects) == 9, f"expected 9 rects, got {len(rects)}"
    assert all(isinstance(r, pygame.Rect) for r in rects), "all 9 entries must be pygame.Rect"
    top, bottom, left, right, minimap, command, speed, recall, memorial = rects
    assert hud.screen_width == 1920, f"screen_width == {hud.screen_width}, expected 1920"
    assert hud.screen_height == 1080, f"screen_height == {hud.screen_height}, expected 1080"
    assert top.y == 0, f"top bar y == {top.y}, expected 0"
    assert bottom.bottom == 1080, f"bottom bar bottom == {bottom.bottom}, expected 1080"


def test_layout_rects_for_screen_returns_nine_rects(headless_hud: HUD) -> None:
    """``hud._layout_rects_for_screen`` (-> hud_left_layout.layout_rects_for_screen) called
    directly with the keyword-only ``show_right_panel`` returns the same 9-rect tuple of
    pygame.Rects WITHOUT raising."""
    hud = headless_hud
    hud._pin_slot.hero_id = "p1"
    gs = _hero_selected_pinned_state()

    r2 = hud._layout_rects_for_screen(1920, 1080, show_right_panel=False, game_state=gs)

    assert len(r2) == 9, f"expected 9 rects, got {len(r2)}"
    assert all(isinstance(x, pygame.Rect) for x in r2), "all 9 entries must be pygame.Rect"


def test_virtual_pointer_in_hud_chrome_left_panel_hit_when_hero_selected(
    headless_hud: HUD,
) -> None:
    """A point just inside the left panel counts as HUD chrome when a hero is selected +
    pinned (the left rect is added as a hit-region). This drives the moved pointer hit-test
    through the watch-card branches (``_pin_slot.hero_id`` set) WITHOUT raising."""
    hud = headless_hud
    hud._pin_slot.hero_id = "p1"
    gs = _hero_selected_pinned_state()
    surface = pygame.Surface((1920, 1080))

    # Resolve the live left rect via the moved layout path.
    top, bottom, left, right, minimap, command, speed, recall, memorial = hud._compute_layout(
        surface, gs
    )

    inside = hud.virtual_pointer_in_hud_chrome((left.x + 4, left.y + 4), surface, gs)
    assert inside is True, "point inside the left panel must be HUD chrome when a hero is selected"


def test_virtual_pointer_in_hud_chrome_left_not_chrome_with_empty_state(
    headless_hud: HUD,
) -> None:
    """The complement (mirror test_wk52_r10_menu_scroll:96): with an EMPTY game_state and NO
    pinned hero, the left panel is not added as a hit-region, so a point at the left-panel
    origin is NOT HUD chrome -> ``virtual_pointer_in_hud_chrome`` returns False.

    NOTE on isolation: ``_pin_slot.hero_id`` is left as None here on purpose. The watch-card
    hit-region branch in ``virtual_pointer_in_hud_chrome`` keys off ``_pin_slot.hero_id``
    (NOT game_state), and a pinned hero's ``_left_watch_rect`` covers the whole left column —
    so pinning would (correctly, per the verbatim-moved logic) make the point HUD chrome
    regardless of game_state. To isolate the *selection-driven left-panel* behavior the plan
    asks for, we use the no-pin HUD; this is exactly what test_wk52_r10:96 does (it toggles
    a `selected_building`, never a pin)."""
    hud = headless_hud
    assert hud._pin_slot.hero_id is None, "fresh HUD must have no pinned hero for this case"
    gs = _hero_selected_pinned_state()
    surface = pygame.Surface((1920, 1080))

    # Resolve the live left rect via the moved layout path (selection present -> left exists).
    top, bottom, left, right, minimap, command, speed, recall, memorial = hud._compute_layout(
        surface, gs
    )

    outside = hud.virtual_pointer_in_hud_chrome((left.x + 4, left.y + 4), surface, {})
    assert outside is False, (
        "with an empty game_state (and no pin) the left panel is not a hit-region "
        "-> must NOT be HUD chrome"
    )
