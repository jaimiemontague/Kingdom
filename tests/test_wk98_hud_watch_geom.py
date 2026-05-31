"""WK98 Round B-15 seam + behavior test (Agent 11 / QA): the 5 pinned-hero
watch-card GEOMETRY helpers were moved VERBATIM from ``game/ui/hud.py`` into the
EXISTING ``game/ui/hud_watch_card.py`` as module functions (the SIXTH bounded
slice of the hud.py god-file, after WK93 hud_radar, WK94 hud_toasts, WK95
hud_summaries, WK96 hud_watch_card render, WK97 hud_panel_buttons). This slice
COMPLETES hud_watch_card.py's render+geometry+constants cohesion.

The 5 moved module functions (each takes the HUD instance, ``hud``, FIRST):

* ``effective_card_full_h(hud)``            (was ``HUD.effective_card_full_h`` — PUBLIC)
* ``desired_watch_card_expanded_h(hud)``    (was ``HUD._desired_watch_card_expanded_h``)
* ``effective_watch_card_h(hud, screen_h)`` (was ``HUD._effective_watch_card_h``)
* ``watch_card_body_split(hud, ch)``        (was ``HUD._watch_card_body_split``)
* ``watch_chat_band_rect(hud, cx, cy, cw, ch, map_h, stats_h, chat_h, profiles,
   hero_id, painted_stats_bottom_override=None)`` (was ``HUD._watch_chat_band_rect``)

This slice ALSO relocates the left-column layout constant ``HERO_LEFT_MIN_H`` OUT
of hud.py and INTO the authoritative ``game/ui/hud_layout.py`` (next to
``LEFT_COL_W`` / ``RADAR_MINIMAP_H``). hud.py RE-IMPORTS it from hud_layout (and
hud_watch_card.py imports it from hud_layout too) so BOTH
``from game.ui.hud_layout import HERO_LEFT_MIN_H`` AND
``from game.ui.hud import HERO_LEFT_MIN_H`` keep resolving (the WK96
constant-ownership pattern; the 3 wk52/wk61 tests are the live guard).

``HUD`` keeps 1-line delegating wrappers (same names + signatures, INCLUDING the
underscore-prefixed private names + the PUBLIC ``effective_card_full_h``) that
forward to the module functions with the HUD instance first, so all call sites
are UNCHANGED. All watch-card STATE (``_pin_slot`` / ``_watch_card_expanded`` /
``_chat_visible`` / ``_left_watch_rect`` / fonts / theme) STAYS on HUD; the moved
functions reach it via the ``hud`` argument.

This guards the refactor SEAM **and** the geometry behavior:

* each of the 5 module fns lives on ``hud_watch_card``, callable, takes ``hud`` first;
* ``HERO_LEFT_MIN_H == 80`` is defined in hud_layout.py AND re-exported by hud (and
  hud.py defines no own ``HERO_LEFT_MIN_H = ...`` at column 0);
* each ``HUD`` wrapper DELEGATES to the matching ``hud_watch_card`` fn (proved by a
  real monkeypatch-of-the-module-fn sentinel spy, incl. the public wrapper);
* AST guard: ``hud_watch_card.py`` has NO module-top (runtime) import of
  ``game.ui.hud`` (a ``TYPE_CHECKING``-only import is allowed) + a fresh interpreter
  imports both orders;
* a headless HUD with a pinned hero drives all 5 helpers through the wrappers and
  produces sane heights / body-split / chat-band rect without raising.
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

import game.ui.hud_watch_card as hud_watch_card
from game.ui.hud import (
    HUD,
    LEFT_COL_W,
    WATCH_CARD_FULL_H_NO_CHAT,
    WATCH_CARD_FULL_H_WITH_CHAT,
    WATCH_CARD_HEADER_H,
)


# The 5 geometry functions WK98 moved into hud_watch_card.py (hud-first signature).
MOVED_FUNCTIONS = (
    "effective_card_full_h",
    "desired_watch_card_expanded_h",
    "effective_watch_card_h",
    "watch_card_body_split",
    "watch_chat_band_rect",
)

# HUD wrapper-name -> hud_watch_card module-function-name (the delegation contract).
# NOTE: ``effective_card_full_h`` is the ONE PUBLIC wrapper (no leading underscore);
# test_wk52_watch_card.py calls ``hud.effective_card_full_h()`` so the exact public
# name must be preserved.
WRAPPER_TO_FN = {
    "effective_card_full_h": "effective_card_full_h",
    "_desired_watch_card_expanded_h": "desired_watch_card_expanded_h",
    "_effective_watch_card_h": "effective_watch_card_h",
    "_watch_card_body_split": "watch_card_body_split",
    "_watch_chat_band_rect": "watch_chat_band_rect",
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 5 module fns on hud_watch_card, hud-first signature.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_watch_card(name: str) -> None:
    """The moved geometry function is present on hud_watch_card and callable."""
    assert hasattr(hud_watch_card, name), f"{name} missing from hud_watch_card"
    assert callable(getattr(hud_watch_card, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    sig = inspect.signature(getattr(hud_watch_card, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", f"{name} first param is {params[0]!r}, expected 'hud'"


# ------------------------------------------------------------------
# (2) CONSTANT RELOCATION: HERO_LEFT_MIN_H lives in hud_layout (== 80), re-exported
#     by hud (== 80), defined THERE (not at column 0 in hud.py).
# ------------------------------------------------------------------

def test_hero_left_min_h_importable_from_hud_layout() -> None:
    """`from game.ui.hud_layout import HERO_LEFT_MIN_H` resolves and equals 80."""
    from game.ui.hud_layout import HERO_LEFT_MIN_H

    assert HERO_LEFT_MIN_H == 80


def test_hero_left_min_h_reexported_from_hud() -> None:
    """The re-export is preserved: `from game.ui.hud import HERO_LEFT_MIN_H` == 80
    (the 3 wk52/wk61 tests import it from game.ui.hud)."""
    from game.ui.hud import HERO_LEFT_MIN_H

    assert HERO_LEFT_MIN_H == 80


def test_hero_left_min_h_same_object_across_modules() -> None:
    """Belt-and-suspenders: the hud name aliases the hud_layout owner (not a copy)."""
    import game.ui.hud as hud_mod
    import game.ui.hud_layout as hud_layout

    assert hud_mod.HERO_LEFT_MIN_H is hud_layout.HERO_LEFT_MIN_H == 80


def test_hero_left_min_h_defined_in_hud_layout_source() -> None:
    """hud_layout.py source contains a top-level ``HERO_LEFT_MIN_H = 80`` assignment
    (the constant is DEFINED there, not merely imported)."""
    import game.ui.hud_layout as hud_layout

    src = Path(hud_layout.__file__).read_text(encoding="utf-8")
    assert re.search(r"(?m)^HERO_LEFT_MIN_H\s*=\s*80\b", src), (
        "hud_layout.py is missing a top-level `HERO_LEFT_MIN_H = 80` definition"
    )


def test_hud_source_has_no_own_hero_left_min_h_definition() -> None:
    """hud.py must NOT define its own ``HERO_LEFT_MIN_H = ...`` at column 0 — only the
    import line (the definition was relocated to hud_layout in WK98). We check that no
    column-0 line matches ``^HERO_LEFT_MIN_H\\s*=`` (the import is indented inside the
    ``from game.ui.hud_layout import (...)`` block, so it never matches)."""
    import game.ui.hud as hud_mod

    src = Path(hud_mod.__file__).read_text(encoding="utf-8")
    offenders = [
        ln
        for ln in src.splitlines()
        if re.match(r"^HERO_LEFT_MIN_H\s*=", ln)
    ]
    assert not offenders, (
        "hud.py still defines its own HERO_LEFT_MIN_H at column 0 "
        f"(should be relocated to hud_layout + re-imported): {offenders}"
    )


# ------------------------------------------------------------------
# (3) WRAPPERS DELEGATE: HUD defines the 5 wrappers and forwards to hud_watch_card.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (incl. the PUBLIC effective_card_full_h)."""
    assert hasattr(HUD, wrapper), f"HUD missing wrapper {wrapper}"
    assert callable(getattr(HUD, wrapper)), f"HUD.{wrapper} is not callable"


def _bare_hud() -> HUD:
    """A bare ``HUD`` instance with no ``__init__`` run.

    Constructing a real HUD pulls in a large pygame/UI stack; ``object.__new__`` gives us
    an instance whose bound wrapper method we can call without that construction. The
    wrapper doesn't touch any instance state itself — it just forwards ``self`` (and any
    extra args) to the module function — so the bare instance is sufficient to prove
    delegation when the module fn is monkeypatched to a sentinel spy.
    """
    return object.__new__(HUD)


# Extra positional args each wrapper passes through (beyond the HUD ``self``), chosen so
# the wrapper's def-line arity is satisfied. Values are opaque markers — the spy records
# them but the real geometry never runs.
_WRAPPER_EXTRA_ARGS = {
    "effective_card_full_h": (),
    "_desired_watch_card_expanded_h": (),
    "_effective_watch_card_h": (1080,),
    "_watch_card_body_split": (200,),
    "_watch_chat_band_rect": (0, 0, LEFT_COL_W, 200, 160, 78, 150, {}, "p1"),
}


@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_wrapper_delegates_to_module_fn(wrapper: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof for ALL 5 wrappers (incl. the PUBLIC
    ``effective_card_full_h``): replace the matching ``hud_watch_card.<fn>`` with a
    sentinel spy, call the HUD wrapper on a bare instance, and assert the spy fired
    exactly once with the HUD forwarded as ``self`` (first arg) and the wrapper returning
    the module fn's result.

    The wrapper imports ``hud_watch_card`` lazily inside its body (``from game.ui import
    hud_watch_card``); that binds the *module object* we monkeypatch here, so the patch
    is seen."""
    target_fn = WRAPPER_TO_FN[wrapper]
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(hud_watch_card, target_fn, spy)

    extra = _WRAPPER_EXTRA_ARGS[wrapper]
    result = getattr(h, wrapper)(*extra)

    assert result is sentinel, f"{wrapper} must return the module function's result"
    assert len(calls) == 1, f"{target_fn} must be called exactly once"
    args, _kwargs = calls[0]
    assert args, f"{wrapper} must forward at least the HUD instance"
    assert args[0] is h, f"{wrapper} must forward HUD (self) as the first arg"


def test_public_effective_card_full_h_wrapper_is_public() -> None:
    """``effective_card_full_h`` is the ONE public wrapper (test_wk52 calls
    ``hud.effective_card_full_h()`` — no underscore)."""
    assert hasattr(HUD, "effective_card_full_h")
    assert not hasattr(HUD, "_effective_card_full_h"), (
        "the wrapper must be PUBLIC (effective_card_full_h), not underscore-prefixed"
    )


# ------------------------------------------------------------------
# (4) AST NO-CYCLE GUARD: hud_watch_card has no module-top runtime import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_watch_card_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_watch_card must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_watch_card). A ``TYPE_CHECKING``-only import is allowed and
    is NOT a runtime import, so we walk only module-level statements (skipping the body of
    an ``if TYPE_CHECKING:`` block) and flag only unconditional module-top imports."""
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
# (5) BEHAVIOR: drive all 5 geometry helpers through the wrappers on a headless HUD.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) — has real watch-card state
    (``_pin_slot`` / ``_watch_card_expanded`` / ``_chat_visible`` / ``_left_watch_rect`` /
    fonts / theme), so the moved geometry functions can reach them via ``hud``."""
    pygame.init()
    hud = HUD(1920, 1080)
    hud._pin_slot.hero_id = "p1"
    hud._watch_card_expanded = True
    hud._chat_visible = True
    return hud


def test_effective_watch_card_h_positive_int(headless_hud: HUD) -> None:
    """``hud._effective_watch_card_h(1080)`` returns a positive int >= header height."""
    ch = headless_hud._effective_watch_card_h(1080)
    assert isinstance(ch, int)
    assert ch > 0
    assert ch >= WATCH_CARD_HEADER_H


def test_watch_card_body_split_sums_within_card(headless_hud: HUD) -> None:
    """``hud._watch_card_body_split(ch)`` returns a 3-tuple of non-negative ints whose
    sum does not exceed the card height."""
    ch = headless_hud._effective_watch_card_h(1080)
    mh, sh, cuh = headless_hud._watch_card_body_split(ch)
    assert all(isinstance(v, int) and v >= 0 for v in (mh, sh, cuh))
    assert mh + sh + cuh <= ch


def test_effective_card_full_h_tracks_chat_visibility(headless_hud: HUD) -> None:
    """The PUBLIC ``hud.effective_card_full_h()`` returns the with-chat full height when
    chat is visible and the no-chat height when it is hidden."""
    hud = headless_hud
    assert hud._chat_visible is True
    assert hud.effective_card_full_h() == WATCH_CARD_FULL_H_WITH_CHAT

    hud._chat_visible = False
    assert hud.effective_card_full_h() == WATCH_CARD_FULL_H_NO_CHAT

    hud._chat_visible = True  # restore


def test_desired_watch_card_expanded_h_int(headless_hud: HUD) -> None:
    """``hud._desired_watch_card_expanded_h()`` returns an int."""
    assert isinstance(headless_hud._desired_watch_card_expanded_h(), int)


def test_watch_chat_band_rect_returns_rect_or_none(headless_hud: HUD) -> None:
    """``hud._watch_chat_band_rect(...)`` returns a pygame.Rect or None without raising."""
    hud = headless_hud
    ch = hud._effective_watch_card_h(1080)
    mh, sh, cuh = hud._watch_card_body_split(ch)
    r = hud._watch_chat_band_rect(0, 0, LEFT_COL_W, ch, mh, sh, cuh, {}, "p1")
    assert r is None or isinstance(r, pygame.Rect)
