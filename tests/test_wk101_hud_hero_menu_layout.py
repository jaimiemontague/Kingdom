"""WK101 Round B-18 seam + behavior test (Agent 11 / QA): the hero-menu-chat-popup
layout cluster was moved VERBATIM from ``game/ui/hud.py`` into the existing
``game/ui/hud_left_layout.py`` as module functions (the NINTH bounded slice of the
hud.py god-file), and the 4 ``HERO_MENU_*`` layout constants were relocated from
hud.py into ``game/ui/hud_layout.py`` (hud re-imports + re-exports them).

The 3 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``should_render_hero_menu_chat_popup(hud, game_state)``
      (was ``HUD._should_render_hero_menu_chat_popup`` — show an in-column chat band when a
       hero is selected with an active chat that is NOT the pinned watch-card chat)
* ``hero_menu_chat_desired_h(hud, left_h)``
      (was ``HUD._hero_menu_chat_desired_h`` — the chat band's reserved height)
* ``hero_menu_chat_split_rects(hud, left)``
      (was ``HUD._hero_menu_chat_split_rects`` — split the left column into a shrunk hero
       sheet + a readable chat band; it only RETURNS rects, never assigns state)

The 4 ``HERO_MENU_*`` constants now live in ``hud_layout.py`` and are re-imported by hud.py
so ``from game.ui.hud import HERO_MENU_CHAT_MIN_H`` / ``HERO_MENU_HERO_MIN_H`` keep resolving
for ``tests/test_wk61_r9_hero_chat_readable_layout.py:9-11``.

``HUD`` keeps 1-line delegating wrappers (same private names + signatures the call sites use)
that forward to the module functions with the HUD instance first, so all call sites are
UNCHANGED. ``_uses_pinned_watch_card_chat`` STAYS on HUD; the ``_hero_menu_chat_rect`` /
``_hero_menu_hero_rect`` STATE ASSIGNMENTS stay in ``render()`` — the moved split function
must NOT assign them. The dead ``WATCH_MINIMAP_SIZE`` const stays untouched in hud.py.

This guards the refactor SEAM **and** the in-column split behavior.
"""
from __future__ import annotations

import ast
import inspect
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when hud / pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import game.ui.hud_left_layout as hud_left_layout
import game.ui.hud_layout as hud_layout
from game.ui.hud import HUD


# The 3 functions WK101 moved into hud_left_layout.py.
MOVED_FUNCTIONS = (
    "should_render_hero_menu_chat_popup",
    "hero_menu_chat_desired_h",
    "hero_menu_chat_split_rects",
)

# HUD wrapper-name -> hud_left_layout module-function-name (the delegation contract).
# All 3 wrappers keep their leading-underscore private names because the render() and
# layout call sites use those exact names.
WRAPPER_TO_FN = {
    "_should_render_hero_menu_chat_popup": "should_render_hero_menu_chat_popup",
    "_hero_menu_chat_desired_h": "hero_menu_chat_desired_h",
    "_hero_menu_chat_split_rects": "hero_menu_chat_split_rects",
}

# The 4 HERO_MENU_* layout constants relocated to hud_layout.py, with expected int values.
EXPECTED_CONSTANTS = {
    "HERO_MENU_CHAT_GAP": 4,
    "HERO_MENU_CHAT_MIN_H": 152,
    "HERO_MENU_CHAT_PREFERRED_H": 220,
    "HERO_MENU_HERO_MIN_H": 120,
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 3 module fns on hud_left_layout, each hud-first.
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
# (2) CONSTANT RELOCATION: 4 HERO_MENU_* live (col-0) on hud_layout, re-exported by hud,
#     removed from hud.py's own defs; WATCH_MINIMAP_SIZE untouched in hud.py.
# ------------------------------------------------------------------

@pytest.mark.parametrize("const_name,expected", sorted(EXPECTED_CONSTANTS.items()))
def test_constant_importable_from_both_modules(const_name: str, expected: int) -> None:
    """Each HERO_MENU_* constant is importable from BOTH hud_layout AND hud (re-export),
    with the expected int value."""
    import game.ui.hud as hud_mod

    assert hasattr(hud_layout, const_name), f"hud_layout missing {const_name}"
    assert hasattr(hud_mod, const_name), f"game.ui.hud missing re-exported {const_name}"
    via_layout = getattr(hud_layout, const_name)
    via_hud = getattr(hud_mod, const_name)
    assert via_layout == expected, f"hud_layout.{const_name} == {via_layout}, expected {expected}"
    assert via_hud == expected, f"hud.{const_name} == {via_hud}, expected {expected}"
    assert via_hud is via_layout, (
        f"hud.{const_name} is not the SAME object as hud_layout.{const_name} "
        "(re-export must alias the owner, not a copy)"
    )


def test_test_wk61_r9_style_from_import_resolves() -> None:
    """Exactly the import that tests/test_wk61_r9_hero_chat_readable_layout.py performs
    (``from game.ui.hud import HERO_MENU_CHAT_MIN_H, HERO_MENU_HERO_MIN_H``) must resolve."""
    from game.ui.hud import (  # noqa: F401 - import is the assertion
        HERO_MENU_CHAT_MIN_H,
        HERO_MENU_HERO_MIN_H,
    )

    assert HERO_MENU_CHAT_MIN_H == 152
    assert HERO_MENU_HERO_MIN_H == 120


@pytest.mark.parametrize("const_name", sorted(EXPECTED_CONSTANTS))
def test_constant_defined_at_column_zero_in_hud_layout(const_name: str) -> None:
    """Read hud_layout.py source: each HERO_MENU_* is defined at column 0 (the owner)."""
    src = Path(hud_layout.__file__).read_text(encoding="utf-8")
    pattern = re.compile(rf"^{const_name}\s*=", re.MULTILINE)
    assert pattern.search(src), (
        f"{const_name} not defined at column 0 in hud_layout.py (expected the owner def)"
    )


def test_hud_py_has_no_column_zero_hero_menu_def() -> None:
    """Read hud.py source: NO column-0 ``HERO_MENU_*=`` assignment (only the import)."""
    src = Path(sys.modules[HUD.__module__].__file__).read_text(encoding="utf-8")
    offenders = re.findall(r"^HERO_MENU_\w+\s*=", src, re.MULTILINE)
    assert not offenders, (
        f"hud.py still defines HERO_MENU_* at column 0 (should be re-imported only): {offenders}"
    )


def test_watch_minimap_size_still_defined_in_hud_py() -> None:
    """The dead ``WATCH_MINIMAP_SIZE`` const is left untouched at column 0 in hud.py."""
    src = Path(sys.modules[HUD.__module__].__file__).read_text(encoding="utf-8")
    assert re.search(r"^WATCH_MINIMAP_SIZE\s*=", src, re.MULTILINE), (
        "WATCH_MINIMAP_SIZE should remain defined (untouched dead const) in hud.py"
    )


# ------------------------------------------------------------------
# (3) WRAPPERS DELEGATE: HUD defines the 3 wrappers and forwards to hud_left_layout.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (the leading-underscore private ones)."""
    assert hasattr(HUD, wrapper), f"HUD missing wrapper {wrapper}"
    assert callable(getattr(HUD, wrapper)), f"HUD.{wrapper} is not callable"


def _bare_hud() -> HUD:
    """A bare ``HUD`` instance with no ``__init__`` run.

    The wrapper doesn't touch any instance state itself — it just forwards ``self`` to the
    module function — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(HUD)


@pytest.mark.parametrize("wrapper,fn_name", sorted(WRAPPER_TO_FN.items()))
def test_wrapper_delegates_to_module_fn(
    wrapper: str, fn_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real monkeypatch-delegation proof: replace ``hud_left_layout.<fn>`` with a sentinel
    spy, call the matching HUD wrapper on a bare instance, and assert the spy fired with the
    HUD forwarded as ``self`` (first arg) + the remaining arg forwarded, returning the spy's
    result. The wrapper imports ``hud_left_layout`` lazily, binding the module object we patch.
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, arg):  # noqa: ANN001 - test spy (all 3 fns take exactly (hud, one_arg))
        calls.append((hh, arg))
        return sentinel

    monkeypatch.setattr(hud_left_layout, fn_name, spy)

    arg_marker = object()
    result = getattr(h, wrapper)(arg_marker)

    assert result is sentinel, f"{wrapper} must return the module function's result"
    assert len(calls) == 1, f"{fn_name} must be called exactly once"
    hh, arg = calls[0]
    assert hh is h, f"{wrapper} must forward HUD (self) as the first arg"
    assert arg is arg_marker, f"{wrapper} must forward its argument"


# ------------------------------------------------------------------
# (4) AST NO-CYCLE GUARD: hud_left_layout has no module-top runtime import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_left_layout_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_left_layout must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_left_layout). A ``TYPE_CHECKING``-only import (``from
    game.ui.hud import HUD``) is allowed and is NOT a runtime import, so we walk only
    module-level statements (skipping the body of an ``if TYPE_CHECKING:`` block)."""
    src_path = Path(hud_left_layout.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []

    def _is_hud(mod: str) -> bool:
        return mod == "game.ui.hud" or mod.endswith(".hud")

    for node in ast.iter_child_nodes(tree):  # module-top statements only
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
# (5) BEHAVIOR: exercise the 3 functions through the HUD wrappers on a headless HUD.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) — has real chat/state, so the moved
    functions can reach them via ``hud``."""
    pygame.init()
    return HUD(1920, 1080)


def test_should_render_hero_menu_chat_popup_false_for_empty_state(headless_hud: HUD) -> None:
    """With an empty game_state (no selected_hero / no active chat) the popup predicate
    returns False without raising."""
    hud = headless_hud
    assert hud._should_render_hero_menu_chat_popup({}) is False


def test_hero_menu_chat_desired_h_int_and_zero_floor(headless_hud: HUD) -> None:
    """desired_h returns an int for a positive height, and 0 for a non-positive height."""
    hud = headless_hud
    h = hud._hero_menu_chat_desired_h(600)
    assert isinstance(h, int)
    assert hud._hero_menu_chat_desired_h(0) == 0


def test_hero_menu_chat_split_rects_shape_and_minimums(headless_hud: HUD) -> None:
    """split_rects returns None or a (hero_rect, chat_rect) pair of pygame.Rects; when it
    returns a pair, each rect honours its minimum height (mirror test_wk61_r9)."""
    from game.ui.hud import HERO_MENU_CHAT_MIN_H, HERO_MENU_HERO_MIN_H

    hud = headless_hud
    r = hud._hero_menu_chat_split_rects(pygame.Rect(0, 48, 224, 700))
    assert r is None or (
        len(r) == 2 and all(isinstance(x, pygame.Rect) for x in r)
    )
    if r is not None:
        hero_rect, chat_rect = r
        assert hero_rect.height >= HERO_MENU_HERO_MIN_H
        assert chat_rect.height >= HERO_MENU_CHAT_MIN_H


def test_split_rects_does_not_mutate_render_state(headless_hud: HUD) -> None:
    """A bare ``_hero_menu_chat_split_rects`` call only RETURNS rects — it must NOT assign
    the ``_hero_menu_chat_rect`` / ``_hero_menu_hero_rect`` state (that happens only in
    render(); downstream readers + wk61_r9 height asserts depend on render() doing it)."""
    hud = headless_hud
    before_chat = getattr(hud, "_hero_menu_chat_rect", None)
    before_hero = getattr(hud, "_hero_menu_hero_rect", None)

    hud._hero_menu_chat_split_rects(pygame.Rect(0, 48, 224, 700))

    assert getattr(hud, "_hero_menu_chat_rect", None) is before_chat, (
        "split_rects must not mutate _hero_menu_chat_rect (assignment belongs to render())"
    )
    assert getattr(hud, "_hero_menu_hero_rect", None) is before_hero, (
        "split_rects must not mutate _hero_menu_hero_rect (assignment belongs to render())"
    )
