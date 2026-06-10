"""WK96 Round B-13 seam + behavior test (Agent 11 / QA): the pinned-hero watch-card
render cluster was moved VERBATIM from ``game/ui/hud.py`` into the new
``game/ui/hud_watch_card.py`` as module functions (the FOURTH bounded slice of the
hud.py god-file, after WK93 hud_radar, WK94 hud_toasts, WK95 hud_summaries):

The 3 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``render_hero_watch_card_infocard(hud, surface, minimap_rect, game_state)``
      (was ``HUD._render_hero_watch_card_infocard`` — the WK52 card: header, optional
       map slot + HP/XP/Lvl stats rows + bars + Chat button + chat band)
* ``render_card_slot(hud, surface, minimap_rect, game_state)``
      (was ``HUD._render_card_slot`` — resets the per-frame watch-card rects then renders
       the hero card when a hero is pinned)
* ``render_watch_card_chrome(hud, surface, minimap_rect, game_state)``
      (was ``HUD._render_watch_card_chrome`` — the render() entry point at hud.py)

This slice ALSO moves the ``WATCH_CARD_*`` layout constants — the new module now OWNS
them (the renderer reads ``WATCH_CARD_HEADER_H``), and hud.py RE-IMPORTS + RE-EXPORTS
them so ``from game.ui.hud import WATCH_CARD_*`` keeps resolving for
``tests/test_wk52_watch_card.py`` AND for the watch-card layout helpers that STAY on HUD
(``_effective_watch_card_h`` / ``_watch_card_body_split`` / ``_watch_chat_band_rect`` …).

``HUD`` keeps 1-line delegating wrappers (same names + signatures, INCLUDING the
underscore-prefixed private names the render() call site uses) that forward to the module
functions with the HUD instance first, so all call sites are UNCHANGED. All watch-card
STATE (``_pin_slot`` / ``_info_card`` / ``_chat_panel`` / the ``_watch_*`` caches /
``_button_*`` / fonts) STAYS on HUD; the moved functions reach it via the ``hud`` argument.

This guards the refactor SEAM **and** the watch-card render path (the card only draws when
a hero is pinned, so the steady-state before/after captures alone do not exercise it — the
behavior test below is what proves the card draws through the moved path):

* each moved function lives on ``hud_watch_card``, is callable, takes ``hud`` first;
* the 8 ``WATCH_CARD_*`` constants live on ``hud_watch_card`` with the expected int values;
* each ``HUD`` wrapper DELEGATES to the matching ``hud_watch_card`` module function (proved
  by a real monkeypatch-of-the-module-fn spy for two of them + an AST/source check across all 3);
* RE-EXPORT integrity: ``from game.ui.hud import WATCH_CARD_*`` resolves AND each name ``is``
  the same object as ``hud_watch_card.<same name>`` (this is what test_wk52 depends on);
* AST guard: ``hud_watch_card.py`` has NO module-top (runtime) import of ``game.ui.hud`` (a
  ``TYPE_CHECKING``-only import is allowed) + a fresh interpreter imports both orders;
* a headless HUD with a pinned hero + duck-typed profile renders the card through the moved
  wrapper without raising (and sets ``_watch_card_rect``), and the ``hero_id is None``
  early-out returns cleanly with ``_watch_card_rect`` reset to ``None``.
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Headless: never bring up a real display when hud / pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import game.ui.hud_watch_card as hud_watch_card
from game.ui.hud import HUD


# The 3 functions WK96 moved into hud_watch_card.py.
MOVED_FUNCTIONS = (
    "render_hero_watch_card_infocard",
    "render_card_slot",
    "render_watch_card_chrome",
)

# HUD wrapper-name -> hud_watch_card module-function-name (the delegation contract).
# NOTE: all 3 wrappers keep their leading-underscore private names because the render()
# call site (hud.py:1377 -> self._render_watch_card_chrome(...)) uses those exact names.
WRAPPER_TO_FN = {
    "_render_hero_watch_card_infocard": "render_hero_watch_card_infocard",
    "_render_card_slot": "render_card_slot",
    "_render_watch_card_chrome": "render_watch_card_chrome",
}

# The 8 WATCH_CARD_* layout constants the new module now OWNS, with expected int values.
WATCH_CARD_HEADER_H = 18
WATCH_CARD_MAP_H = 160
WATCH_CARD_STATS_H = 78
WATCH_CARD_STATS_COMPACT_H = 58
WATCH_CARD_CHAT_H = 190  # WK130: 150 -> 190
WATCH_CARD_FULL_H_WITH_CHAT = (
    WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_H + WATCH_CARD_CHAT_H
)  # 446
WATCH_CARD_FULL_H_NO_CHAT = (
    WATCH_CARD_HEADER_H + WATCH_CARD_MAP_H + WATCH_CARD_STATS_COMPACT_H
)  # 236
WATCH_CARD_FULL_H = WATCH_CARD_FULL_H_WITH_CHAT  # 446

EXPECTED_CONSTANTS = {
    "WATCH_CARD_HEADER_H": WATCH_CARD_HEADER_H,
    "WATCH_CARD_MAP_H": WATCH_CARD_MAP_H,
    "WATCH_CARD_STATS_H": WATCH_CARD_STATS_H,
    "WATCH_CARD_STATS_COMPACT_H": WATCH_CARD_STATS_COMPACT_H,
    "WATCH_CARD_CHAT_H": WATCH_CARD_CHAT_H,
    "WATCH_CARD_FULL_H_WITH_CHAT": WATCH_CARD_FULL_H_WITH_CHAT,
    "WATCH_CARD_FULL_H_NO_CHAT": WATCH_CARD_FULL_H_NO_CHAT,
    "WATCH_CARD_FULL_H": WATCH_CARD_FULL_H,
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 3 module fns (hud-first) + 8 WATCH_CARD_* constants on hud_watch_card.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_watch_card(name: str) -> None:
    """The moved function is present on hud_watch_card and callable."""
    assert hasattr(hud_watch_card, name), f"{name} missing from hud_watch_card"
    assert callable(getattr(hud_watch_card, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    sig = inspect.signature(getattr(hud_watch_card, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", f"{name} first param is {params[0]!r}, expected 'hud'"


@pytest.mark.parametrize("const_name,expected", sorted(EXPECTED_CONSTANTS.items()))
def test_watch_card_constants_live_on_module_with_expected_value(
    const_name: str, expected: int
) -> None:
    """The 8 WATCH_CARD_* constants live on hud_watch_card with the expected int values."""
    assert hasattr(hud_watch_card, const_name), f"{const_name} missing from hud_watch_card"
    actual = getattr(hud_watch_card, const_name)
    assert isinstance(actual, int), f"{const_name} should be int, got {type(actual)!r}"
    assert actual == expected, f"{const_name} == {actual}, expected {expected}"


def test_watch_card_derived_sums_are_internally_consistent() -> None:
    """The 3 derived heights equal their component sums (pins the arithmetic, not just literals)."""
    assert (
        hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT
        == hud_watch_card.WATCH_CARD_HEADER_H
        + hud_watch_card.WATCH_CARD_MAP_H
        + hud_watch_card.WATCH_CARD_STATS_H
        + hud_watch_card.WATCH_CARD_CHAT_H
    )
    assert hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT == 446  # WK130: was 406
    assert (
        hud_watch_card.WATCH_CARD_FULL_H_NO_CHAT
        == hud_watch_card.WATCH_CARD_HEADER_H
        + hud_watch_card.WATCH_CARD_MAP_H
        + hud_watch_card.WATCH_CARD_STATS_COMPACT_H
    )
    assert hud_watch_card.WATCH_CARD_FULL_H_NO_CHAT == 236
    assert hud_watch_card.WATCH_CARD_FULL_H == hud_watch_card.WATCH_CARD_FULL_H_WITH_CHAT
    assert hud_watch_card.WATCH_CARD_FULL_H == 446  # WK130: was 406


# ------------------------------------------------------------------
# (2) WRAPPERS DELEGATE: HUD defines the 3 wrappers and forwards to hud_watch_card.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (the leading-underscore private ones)."""
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


def test_render_watch_card_chrome_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof through the render() entry-point wrapper
    (``HUD._render_watch_card_chrome``, called at hud.py:1377): replace
    ``hud_watch_card.render_watch_card_chrome`` with a sentinel spy, call the wrapper on a bare
    instance, and assert the spy fired with the HUD forwarded as ``self`` (first arg), the
    remaining args forwarded in order, and the wrapper returning the module fn's result.

    The wrapper imports ``hud_watch_card`` lazily inside its body (``from game.ui import
    hud_watch_card``); that binds the *module object* we monkeypatch here, so the patch is seen.
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, minimap_rect, game_state):  # noqa: ANN001 - test spy
        calls.append((hh, surface, minimap_rect, game_state))
        return sentinel

    monkeypatch.setattr(hud_watch_card, "render_watch_card_chrome", spy)

    surface_marker = object()
    minimap_marker = object()
    state_marker = object()
    result = h._render_watch_card_chrome(surface_marker, minimap_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, minimap_rect, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert minimap_rect is minimap_marker, "minimap_rect must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_render_card_slot_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second real monkeypatch-delegation proof, through the ``_render_card_slot`` wrapper."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, minimap_rect, game_state):  # noqa: ANN001 - test spy
        calls.append((hh, surface, minimap_rect, game_state))
        return sentinel

    monkeypatch.setattr(hud_watch_card, "render_card_slot", spy)

    surface_marker = object()
    minimap_marker = object()
    state_marker = object()
    result = h._render_card_slot(surface_marker, minimap_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, minimap_rect, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert minimap_rect is minimap_marker, "minimap_rect must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_wrappers_reference_hud_watch_card_in_source() -> None:
    """Belt-and-suspenders: every wrapper body references the ``hud_watch_card`` module and
    calls the matching module function with ``self`` first. Pins the delegation across all 3
    wrappers even where we only monkeypatch-prove two of them above."""
    src_path = Path(sys.modules[HUD.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))

    found: dict[str, bool] = {w: False for w in WRAPPER_TO_FN}

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name not in WRAPPER_TO_FN:
                return
            target_fn = WRAPPER_TO_FN[node.name]
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func
                # match hud_watch_card.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "hud_watch_card"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call hud_watch_card.<fn>(self, ...) in source: " f"{missing}"
    )


# ------------------------------------------------------------------
# (3) RE-EXPORT INTEGRITY: from game.ui.hud import WATCH_CARD_* still resolves AND is the
#     SAME object as hud_watch_card.<name> (this is what test_wk52_watch_card.py depends on).
# ------------------------------------------------------------------

@pytest.mark.parametrize("const_name,expected", sorted(EXPECTED_CONSTANTS.items()))
def test_constant_reexported_from_hud_and_same_object(const_name: str, expected: int) -> None:
    """`from game.ui.hud import <WATCH_CARD_*>` resolves, has the expected value, AND is the
    identical object as hud_watch_card.<name> (proves the re-export, not a divergent copy)."""
    import game.ui.hud as hud_mod

    assert hasattr(hud_mod, const_name), (
        f"game.ui.hud is missing re-exported constant {const_name}"
    )
    via_hud = getattr(hud_mod, const_name)
    via_module = getattr(hud_watch_card, const_name)
    assert via_hud == expected, f"hud.{const_name} == {via_hud}, expected {expected}"
    assert via_hud is via_module, (
        f"hud.{const_name} is not the SAME object as hud_watch_card.{const_name} "
        "(re-export must alias the owner, not a copy)"
    )


def test_test_wk52_style_from_import_resolves() -> None:
    """Exactly the import that tests/test_wk52_watch_card.py performs must still resolve."""
    from game.ui.hud import (  # noqa: F401 - import is the assertion
        WATCH_CARD_CHAT_H,
        WATCH_CARD_FULL_H,
        WATCH_CARD_FULL_H_NO_CHAT,
        WATCH_CARD_FULL_H_WITH_CHAT,
        WATCH_CARD_HEADER_H,
        WATCH_CARD_MAP_H,
        WATCH_CARD_STATS_COMPACT_H,
        WATCH_CARD_STATS_H,
    )

    assert WATCH_CARD_HEADER_H == 18
    assert WATCH_CARD_FULL_H == 446  # WK130: was 406


# ------------------------------------------------------------------
# (4) AST NO-CYCLE GUARD: hud_watch_card has no module-top runtime import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_watch_card_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_watch_card must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_watch_card). A ``TYPE_CHECKING``-only import is allowed and is
    NOT a runtime import, so we walk only module-level statements (skipping the body of an
    ``if TYPE_CHECKING:`` block) and flag only unconditional module-top imports."""
    src_path = Path(hud_watch_card.__file__)
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
        "hud_watch_card has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_watch_card", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_watch_card"),
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
# (5) BEHAVIOR: render the pinned-hero watch card through the moved wrapper on a headless HUD.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) — has real watch-card state
    (``_pin_slot`` / ``_info_card`` / ``_chat_panel`` / ``_watch_*`` caches / ``_button_*`` /
    fonts) + the layout helpers, so the moved functions can reach them via ``hud``."""
    pygame.init()
    return HUD(1920, 1080)


def _pinned_hero_profile() -> SimpleNamespace:
    """Duck-typed hero profile the watch-card renderer reads: vitals(hp/max_hp),
    progression(xp/xp_to_level), identity(level)."""
    return SimpleNamespace(
        vitals=SimpleNamespace(hp=30, max_hp=50),
        progression=SimpleNamespace(xp=20, xp_to_level=100),
        identity=SimpleNamespace(level=3),
    )


def test_render_watch_card_chrome_draws_card_for_pinned_hero(headless_hud: HUD) -> None:
    """The real pixel guard: with a pinned hero + a duck-typed profile and the card expanded,
    ``hud._render_watch_card_chrome`` (-> hud_watch_card.render_watch_card_chrome -> render_card_slot
    -> render_hero_watch_card_infocard) renders onto a real Surface WITHOUT raising and sets
    ``hud._watch_card_rect`` (proves the card actually drew through the moved path)."""
    hud = headless_hud
    hud._pin_slot.hero_id = "h1"
    hud._pin_slot.pinned_name = "Nova"
    profile = _pinned_hero_profile()
    game_state = {"hero_profiles_by_id": {"h1": profile}}
    hud._watch_card_expanded = True
    # Use the minimap-relative layout path (a fresh HUD already has _left_watch_rect=None,
    # which routes render_hero_watch_card_infocard through _effective_watch_card_h(sh) — no raise).
    hud._left_watch_rect = None

    surface = pygame.Surface((1920, 1080))
    minimap_rect = pygame.Rect(8, 600, 180, 160)

    hud._render_watch_card_chrome(surface, minimap_rect, game_state)  # must not raise

    assert hud._watch_card_rect is not None, (
        "the watch card did not draw — _watch_card_rect should be set after a pinned-hero render"
    )
    # The card slot recorded that it rendered a hero (not a building/empty slot).
    assert hud._card_slot_kind == "hero"


def test_render_watch_card_chrome_early_out_when_no_pinned_hero(headless_hud: HUD) -> None:
    """The early-out path: with ``_pin_slot.hero_id is None``, ``_render_watch_card_chrome``
    must return without raising and leave ``_watch_card_rect`` reset to ``None`` (render_card_slot
    resets the per-frame rects then short-circuits before drawing the hero card)."""
    hud = headless_hud
    # First seed a stale rect so we prove the slot resets it (not merely "stays None").
    hud._watch_card_rect = pygame.Rect(0, 0, 10, 10)
    hud._pin_slot.hero_id = None
    hud._watch_card_expanded = True
    hud._left_watch_rect = None

    surface = pygame.Surface((1920, 1080))
    minimap_rect = pygame.Rect(8, 600, 180, 160)

    hud._render_watch_card_chrome(surface, minimap_rect, game_state={})  # must not raise

    assert hud._watch_card_rect is None, (
        "with no pinned hero the watch card must not draw — _watch_card_rect should be None"
    )
    assert hud._card_slot_kind is None
