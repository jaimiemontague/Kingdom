"""WK99 Round B-16 seam + behavior test (Agent 11 / QA): the left-column split cluster
was moved VERBATIM from ``game/ui/hud.py`` into the new ``game/ui/hud_left_layout.py`` as
module functions (the SEVENTH bounded slice of the hud.py god-file, after WK93 hud_radar,
WK94 hud_toasts, WK95 hud_summaries, WK96 hud_watch_card, WK97 hud_panel_buttons,
WK98 watch-card geometry).

The 7 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``left_column_segments_open(hud, game_state)``         (was ``HUD._left_column_segments_open``)
* ``normalized_left_split_fracs(hud, main_open, watch_open)`` (was ``HUD._normalized_left_split_fracs``)
* ``layout_left_column_segments(hud, top_h, minimap, game_state)`` (was ``HUD._layout_left_column_segments``)
* ``render_left_split_handles(hud, surface)``            (was ``HUD._render_left_split_handles``)
* ``handle_sidebar_split_pointer_down(hud, pos, game_state)`` (was ``HUD.handle_sidebar_split_pointer_down`` -- PUBLIC)
* ``handle_sidebar_split_pointer_move(hud, pos, game_state)`` (was ``HUD.handle_sidebar_split_pointer_move`` -- PUBLIC)
* ``handle_sidebar_split_pointer_up(hud)``               (was ``HUD.handle_sidebar_split_pointer_up`` -- PUBLIC)

This slice ALSO relocates the 5 ``LEFT_SPLIT_*`` layout constants from hud.py into
``hud_layout.py`` (the authoritative layout-constants module; same WK98 pattern as
``HERO_LEFT_MIN_H``); hud.py RE-IMPORTS + RE-EXPORTS them so ``from game.ui.hud import
LEFT_SPLIT_*`` keeps resolving for ``tests/test_wk61_r10_sidebar_layout.py`` (imports
``LEFT_SPLIT_HANDLE_H``) and ``tests/test_wk61_r11_sidebar_main_solo_handle.py`` (imports
``LEFT_SPLIT_HANDLE_HIT_H`` + ``LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO``) AND so hud.py's
``__init__`` split-frac defaults still resolve the bare names.

``HUD`` keeps 1-line lazy-delegating wrappers (EXACT names + signatures, INCLUDING the 3
PUBLIC ``handle_sidebar_split_pointer_*`` the input layer (ursina_app/mouse/input_handler)
reaches via hasattr/getattr) that forward to the module functions with the HUD instance
first, so all call sites are UNCHANGED. All ``_left_*`` drag/layout STATE stays on HUD; the
moved functions reach it via the ``hud`` argument.

This guards the refactor SEAM **and** the left-column layout + drag-resize behavior:

* (1) EXISTENCE -- each moved function lives on ``hud_left_layout``, is callable, takes ``hud`` first;
* (2) CONSTANT RELOCATION -- the 5 ``LEFT_SPLIT_*`` constants are importable from BOTH
      ``game.ui.hud_layout`` AND ``game.ui.hud`` (re-export) with the literal values; hud_layout
      source defines all 5 at column 0; hud.py source no longer has its own column-0 def;
* (3) WRAPPERS DELEGATE -- each HUD wrapper forwards to the matching module fn (monkeypatch
      spy each, call the wrapper, assert fired -- incl. all 3 public handle_sidebar_split_pointer_*);
* (4) AST NO-CYCLE GUARD -- ``hud_left_layout.py`` has NO module-top (runtime) import of
      ``game.ui.hud`` (a ``TYPE_CHECKING`` ``from game.ui.hud import HUD`` is permitted) + a fresh
      interpreter imports both orders without a cycle;
* (5) BEHAVIOR -- a headless HUD with a selection + a pinned hero (both segments open) lays
      out the left column via the moved wrapper (sets _left_main_rect/_left_watch_rect/
      _left_split_handle_rects), drives a full pointer down/move/up drag through the 3 public
      wrappers, and renders the split handles -- all without raising.
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

import game.ui.hud_layout as hud_layout
import game.ui.hud_left_layout as hud_left_layout
from game.ui.hud import HUD, RADAR_MINIMAP_H, RADAR_MINIMAP_W


# The 7 functions WK99 moved into hud_left_layout.py.
MOVED_FUNCTIONS = (
    "left_column_segments_open",
    "normalized_left_split_fracs",
    "layout_left_column_segments",
    "render_left_split_handles",
    "handle_sidebar_split_pointer_down",
    "handle_sidebar_split_pointer_move",
    "handle_sidebar_split_pointer_up",
)

# HUD wrapper-name -> hud_left_layout module-function-name (the delegation contract).
# The 4 layout/render wrappers keep their leading-underscore private names; the 3
# handle_sidebar_split_pointer_* are PUBLIC (no underscore) because the input layer
# (ursina_app/mouse/input_handler) reaches them via hasattr/getattr by exact name.
WRAPPER_TO_FN = {
    "_left_column_segments_open": "left_column_segments_open",
    "_normalized_left_split_fracs": "normalized_left_split_fracs",
    "_layout_left_column_segments": "layout_left_column_segments",
    "_render_left_split_handles": "render_left_split_handles",
    "handle_sidebar_split_pointer_down": "handle_sidebar_split_pointer_down",
    "handle_sidebar_split_pointer_move": "handle_sidebar_split_pointer_move",
    "handle_sidebar_split_pointer_up": "handle_sidebar_split_pointer_up",
}

# The 3 PUBLIC wrappers the input layer calls by exact name via hasattr/getattr.
PUBLIC_HANDLE_WRAPPERS = (
    "handle_sidebar_split_pointer_down",
    "handle_sidebar_split_pointer_move",
    "handle_sidebar_split_pointer_up",
)

# The 5 LEFT_SPLIT_* constants WK99 relocated into hud_layout.py, with expected values.
EXPECTED_CONSTANTS = {
    "LEFT_SPLIT_HANDLE_H": 4,
    "LEFT_SPLIT_HANDLE_HIT_H": 8,
    "LEFT_SPLIT_DEFAULT_FRAC_MAIN": 0.55,
    "LEFT_SPLIT_DEFAULT_FRAC_WATCH": 0.45,
    "LEFT_SPLIT_DEFAULT_FRAC_MAIN_SOLO": 0.72,
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 7 module fns on hud_left_layout, each callable + hud-first.
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


# ------------------------------------------------------------------
# (2) CONSTANT RELOCATION: the 5 LEFT_SPLIT_* live in hud_layout, re-exported by hud.
# ------------------------------------------------------------------

@pytest.mark.parametrize("const_name,expected", sorted(EXPECTED_CONSTANTS.items()))
def test_constant_lives_on_hud_layout_with_expected_value(const_name: str, expected) -> None:
    """The 5 LEFT_SPLIT_* constants live on hud_layout with the expected literal values."""
    assert hasattr(hud_layout, const_name), f"{const_name} missing from hud_layout"
    actual = getattr(hud_layout, const_name)
    assert actual == expected, f"hud_layout.{const_name} == {actual!r}, expected {expected!r}"


@pytest.mark.parametrize("const_name,expected", sorted(EXPECTED_CONSTANTS.items()))
def test_constant_reexported_from_hud_with_expected_value(const_name: str, expected) -> None:
    """`from game.ui.hud import <LEFT_SPLIT_*>` resolves with the expected value (re-export);
    this is what tests/test_wk61_r10 + test_wk61_r11 depend on, plus hud.py's __init__ defaults."""
    import game.ui.hud as hud_mod

    assert hasattr(hud_mod, const_name), (
        f"game.ui.hud is missing re-exported constant {const_name}"
    )
    via_hud = getattr(hud_mod, const_name)
    via_layout = getattr(hud_layout, const_name)
    assert via_hud == expected, f"hud.{const_name} == {via_hud!r}, expected {expected!r}"
    assert via_hud == via_layout, (
        f"hud.{const_name} ({via_hud!r}) != hud_layout.{const_name} ({via_layout!r})"
    )


def test_hud_layout_source_defines_all_five_at_column_zero() -> None:
    """Read hud_layout.py source: assert it defines all 5 LEFT_SPLIT_* at column 0
    (a real top-level assignment, not just a re-import)."""
    src_path = Path(hud_layout.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    defined: set[str] = set()
    for node in ast.iter_child_nodes(tree):  # module-top statements only (column 0)
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for tgt in targets:
            if isinstance(tgt, ast.Name) and tgt.id in EXPECTED_CONSTANTS:
                defined.add(tgt.id)
    missing = sorted(set(EXPECTED_CONSTANTS) - defined)
    assert not missing, f"hud_layout.py does not define these at column 0: {missing}"


def test_hud_source_has_no_column_zero_left_split_assignment() -> None:
    """Read hud.py source: assert NO column-0 ``LEFT_SPLIT_*=`` assignment remains (only the
    import line / indented __init__ usage). The constants were relocated to hud_layout."""
    src_path = Path(sys.modules[HUD.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):  # module-top statements only (column 0)
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for tgt in targets:
            if isinstance(tgt, ast.Name) and tgt.id.startswith("LEFT_SPLIT_"):
                offenders.append(tgt.id)
    assert not offenders, (
        f"hud.py still defines LEFT_SPLIT_* at column 0 (should be relocated to hud_layout): "
        f"{offenders}"
    )


# ------------------------------------------------------------------
# (3) WRAPPERS DELEGATE: HUD defines the 7 wrappers and forwards to hud_left_layout.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (incl. the 3 public handle_sidebar_split_pointer_*)."""
    assert hasattr(HUD, wrapper), f"HUD missing wrapper {wrapper}"
    assert callable(getattr(HUD, wrapper)), f"HUD.{wrapper} is not callable"


def _bare_hud() -> HUD:
    """A bare ``HUD`` instance with no ``__init__`` run.

    Constructing a real HUD pulls in a large pygame/UI stack; ``object.__new__`` gives us an
    instance whose bound wrapper method we can call without that construction. The wrapper
    doesn't touch instance state itself -- it just forwards ``self`` to the module function --
    so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(HUD)


@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_wrapper_delegates_to_module_function(
    wrapper: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real monkeypatch-delegation proof for EACH of the 7 wrappers (incl. all 3 public
    handle_sidebar_split_pointer_*): replace the matching ``hud_left_layout.<fn>`` with a
    sentinel spy, call the wrapper on a bare instance with marker args, and assert the spy fired
    exactly once with the HUD forwarded as the first arg, the remaining args forwarded in order,
    and the wrapper returning the module fn's result.

    Each wrapper imports ``hud_left_layout`` lazily inside its body (``from game.ui import
    hud_left_layout``); that binds the *module object* we monkeypatch here, so the patch is seen.
    """
    target_fn = WRAPPER_TO_FN[wrapper]
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(hud_left_layout, target_fn, spy)

    # Build positional markers sized to the wrapper's own signature (minus self).
    wrapper_sig = inspect.signature(getattr(HUD, wrapper))
    n_extra = len(wrapper_sig.parameters) - 1  # drop 'self'
    markers = [object() for _ in range(n_extra)]

    result = getattr(h, wrapper)(*markers)

    assert result is sentinel, f"{wrapper} must return the module function's result"
    assert len(calls) == 1, f"{wrapper} must call hud_left_layout.{target_fn} exactly once"
    args, kwargs = calls[0]
    assert args and args[0] is h, f"{wrapper} must forward the HUD (self) as the first arg"
    assert list(args[1:]) == markers, (
        f"{wrapper} must forward the remaining args in order to {target_fn}"
    )


# ------------------------------------------------------------------
# (4) AST NO-CYCLE GUARD: hud_left_layout has no module-top runtime import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_left_layout_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_left_layout must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_left_layout). A ``TYPE_CHECKING``-only ``from game.ui.hud import
    HUD`` is allowed (it is not a runtime import), so we walk only module-level statements,
    skipping the body of an ``if TYPE_CHECKING:`` block, and flag only unconditional imports."""
    src_path = Path(hud_left_layout.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []

    def _is_hud(mod: str) -> bool:
        return mod == "game.ui.hud" or mod.endswith(".hud")

    for node in ast.iter_child_nodes(tree):  # module-top statements only
        # Permit imports inside `if TYPE_CHECKING:` -- they are not runtime imports.
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
    """A fresh interpreter can import both modules in EITHER order without a module-load cycle.
    Runs out-of-process so already-imported modules in this session cannot mask an order bug."""
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
# (5) BEHAVIOR: lay out the left column + drive a full drag + render handles, headless.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) -- has the real ``_left_*`` drag/layout
    state + the split-frac defaults, so the moved functions can reach them via ``hud``."""
    pygame.init()
    return HUD(1920, 1080)


def test_layout_drag_and_render_through_moved_path(headless_hud: HUD) -> None:
    """End-to-end through the moved cluster (mirrors test_wk61_r10's both-segments-open setup):
    with a selection (main open) AND a pinned hero (watch open), the moved layout wrapper
    allocates the main + watch rects and stashes the handle rects; a full pointer down/move/up
    drag through the 3 PUBLIC wrappers resizes the split; and the handle-render wrapper draws
    onto a real Surface -- all WITHOUT raising."""
    hud = headless_hud
    # Watch open: pin a hero.
    hud._pin_slot.hero_id = "p1"
    hud._pin_slot.pinned_name = "Pinned"
    hud._watch_card_expanded = True
    # Main open: a non-None selection.
    gs = {"selected_hero": object()}

    minimap = pygame.Rect(0, 1080 - int(RADAR_MINIMAP_H), int(RADAR_MINIMAP_W), int(RADAR_MINIMAP_H))
    top_h = 48

    # --- layout -------------------------------------------------------------
    left, main, watch = hud._layout_left_column_segments(top_h, minimap, gs)  # must not raise
    assert isinstance(main, pygame.Rect), "main panel rect must be a pygame.Rect"
    assert isinstance(watch, pygame.Rect), "watch card rect must be a pygame.Rect"
    assert isinstance(left, pygame.Rect)
    assert hud._left_main_rect is not None, "_left_main_rect must be set after layout"
    assert hud._left_watch_rect is not None, "_left_watch_rect must be set after layout"
    assert len(hud._left_split_handle_rects) > 0, "layout must stash at least one handle rect"
    # Flush-left at x=0, full left-column column width, non-overlapping (main above watch).
    assert main.x == 0 and watch.x == 0, "left column must be flush-left at x=0"
    assert main.bottom <= watch.top + 1, "main panel must sit above the watch card (no overlap)"

    # --- drag (down -> move -> up) through the 3 PUBLIC wrappers ------------
    handle = hud._left_split_handle_rects.get("main_bottom") or next(
        iter(hud._left_split_handle_rects.values())
    )
    assert hud.handle_sidebar_split_pointer_down(handle.center, gs) is True
    assert (
        hud.handle_sidebar_split_pointer_move((handle.centerx, handle.centery + 40), gs) is True
    )
    assert hud.handle_sidebar_split_pointer_up() is True

    # --- render the handles -------------------------------------------------
    surface = pygame.Surface((1920, 1080))
    assert hud._render_left_split_handles(surface) is None  # must not raise
