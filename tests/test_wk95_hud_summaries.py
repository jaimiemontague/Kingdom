"""WK95 Round B-12 seam + behavior test (Agent 11 / QA): the entity info-card render
cluster was moved VERBATIM from ``game/ui/hud.py`` into the new ``game/ui/hud_summaries.py``
as module functions (the third bounded slice of the hud.py god-file, after WK93's
hud_radar and WK94's hud_toasts):

The 4 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``peasant_action_label(hud, peasant)``                 (was ``HUD._peasant_action_label``)
* ``render_peasant_summary(hud, surface, peasant, left_rect)`` (was ``HUD._render_peasant_summary``, WK17)
* ``render_building_summary(hud, surface, building, rect)``    (was ``HUD._render_building_summary``)
* ``render_hero_focus_profile(hud, surface, rect, game_state)`` (was ``HUD._render_hero_focus_profile``, WK49)

``HUD`` keeps 1-line delegating wrappers (same names + signatures, INCLUDING the
underscore-prefixed private names that the render() call sites AND the external
``game/ui/micro_view_manager.py`` hero-focus ``hasattr``-caller use) that forward to the
module functions with the HUD instance as the first argument, so all call sites are
UNCHANGED. The shared helpers (``_draw_section_divider``, ``_right_panel_top_pad``) and all
state (``_frame_inner``/``_frame_highlight``/``_micro_view``/``_hero_panel``/``theme``) STAY
on the HUD; the moved functions reach them via the ``hud`` argument.

This guards the refactor SEAM **and** the summary render path (a summary only renders when
its entity kind is selected, so the steady-state before/after pygame captures prove only
that scene+chrome are unchanged — the behavior test below is what proves the summary path):

* each moved function lives on ``hud_summaries``, is callable, and takes ``hud`` first;
* each ``HUD`` wrapper DELEGATES to the matching ``hud_summaries`` module function (proved by
  a real monkeypatch-of-the-module-fn spy — including ``_render_hero_focus_profile`` since the
  external ``micro_view_manager`` module calls it via ``hasattr`` — AND a belt-and-suspenders
  AST/source check across all 4 wrappers);
* AST guard: ``hud_summaries.py`` has NO module-top (runtime) import of ``game.ui.hud`` — a
  ``TYPE_CHECKING``-only ``from game.ui.hud import HUD`` is allowed (it is not a runtime
  import), so we walk only module-level statements and skip the TYPE_CHECKING block;
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* a headless HUD driven through the moved peasant/building/hero-focus wrappers renders each
  summary onto a real Surface without raising (and the action label returns a str).
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

import game.ui.hud_summaries as hud_summaries
from game.ui.hud import HUD


# The 4 functions WK95 moved into hud_summaries.py.
MOVED_FUNCTIONS = (
    "peasant_action_label",
    "render_peasant_summary",
    "render_building_summary",
    "render_hero_focus_profile",
)

# HUD wrapper-name -> hud_summaries module-function-name (the delegation contract).
# NOTE: all 4 wrappers keep their leading-underscore private names because the render()
# call sites (hud.py 866/1528) and the EXTERNAL micro_view_manager.py hasattr-caller
# (:119/:126 -> _render_hero_focus_profile) use those exact names.
WRAPPER_TO_FN = {
    "_peasant_action_label": "peasant_action_label",
    "_render_peasant_summary": "render_peasant_summary",
    "_render_building_summary": "render_building_summary",
    "_render_hero_focus_profile": "render_hero_focus_profile",
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 4 module fns, each callable with ``hud`` as first param.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_summaries(name: str) -> None:
    """The moved function is present on hud_summaries and callable."""
    assert hasattr(hud_summaries, name), f"{name} missing from hud_summaries"
    assert callable(getattr(hud_summaries, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    sig = inspect.signature(getattr(hud_summaries, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", (
        f"{name} first param is {params[0]!r}, expected 'hud'"
    )


# ------------------------------------------------------------------
# (2) WRAPPERS DELEGATE: HUD defines the 4 wrappers and forwards to hud_summaries.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (incl. the leading-underscore private ones)."""
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


def test_render_hero_focus_profile_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof through the wrapper the EXTERNAL
    ``game/ui/micro_view_manager.py`` reaches via ``hasattr(hud, "_render_hero_focus_profile")``
    then ``hud._render_hero_focus_profile(...)``: replace ``hud_summaries.render_hero_focus_profile``
    with a sentinel spy, call ``HUD._render_hero_focus_profile`` on a bare instance, and assert
    the spy fired with the HUD forwarded as ``self`` (first arg), the remaining args forwarded
    in order, and the wrapper returning the module fn's result.

    The wrapper imports ``hud_summaries`` lazily inside its body (``from game.ui import
    hud_summaries``); that binds the *module object* we monkeypatch here, so the patch is
    seen by the wrapper.
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, rect, game_state):  # noqa: ANN001 - test spy
        calls.append((hh, surface, rect, game_state))
        return sentinel

    monkeypatch.setattr(hud_summaries, "render_hero_focus_profile", spy)

    surface_marker = object()
    rect_marker = object()
    state_marker = object()
    result = h._render_hero_focus_profile(surface_marker, rect_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, rect, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert rect is rect_marker, "rect must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_render_peasant_summary_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second real monkeypatch-delegation proof, through the ``_render_peasant_summary``
    wrapper (the render() call site at hud.py:1528)."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, peasant, left_rect):  # noqa: ANN001 - test spy
        calls.append((hh, surface, peasant, left_rect))
        return sentinel

    monkeypatch.setattr(hud_summaries, "render_peasant_summary", spy)

    surface_marker = object()
    peasant_marker = object()
    rect_marker = object()
    result = h._render_peasant_summary(surface_marker, peasant_marker, rect_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, peasant, left_rect = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert peasant is peasant_marker, "peasant must be forwarded"
    assert left_rect is rect_marker, "left_rect must be forwarded"


def test_wrappers_reference_hud_summaries_in_source() -> None:
    """Belt-and-suspenders: every wrapper body references the ``hud_summaries`` module and
    calls the matching module function with ``self`` first. Pins the delegation across all 4
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
                # match hud_summaries.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "hud_summaries"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call hud_summaries.<fn>(self, ...) in source: " f"{missing}"
    )


# ------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD: hud_summaries has no module-top import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_summaries_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_summaries must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_summaries). A ``TYPE_CHECKING``-only import is allowed and is
    NOT a runtime import, so we walk only module-level statements (skipping the body of an
    ``if TYPE_CHECKING:`` block) and flag only unconditional module-top imports."""
    src_path = Path(hud_summaries.__file__)
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
        "hud_summaries has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_summaries", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_summaries"),
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
# (4) BEHAVIOR: render each summary through the moved wrapper path on a headless HUD.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) — has real ``theme``/``_frame_*``/
    ``_micro_view``/``_hero_panel`` state, so the moved functions can reach them via ``hud``."""
    pygame.init()
    return HUD(1920, 1080)


def _mock_peasant() -> SimpleNamespace:
    """Duck-typed peasant the moved peasant renderers read (state .name, hp/max_hp, etc.)."""
    return SimpleNamespace(
        is_alive=True,
        state=SimpleNamespace(name="WORKING"),
        hp=5,
        max_hp=10,
        target_building=None,
        wood_inventory=None,
        required_wood=None,
    )


def _mock_building() -> SimpleNamespace:
    """Duck-typed building the moved building renderer reads (building_type, hp/max_hp)."""
    return SimpleNamespace(building_type="house", hp=80, max_hp=100)


def test_peasant_action_label_returns_str(headless_hud: HUD) -> None:
    """``hud._peasant_action_label`` (-> hud_summaries.peasant_action_label) returns a
    non-empty player-facing string for a WORKING peasant, through the moved path."""
    hud = headless_hud
    label = hud._peasant_action_label(_mock_peasant())
    assert isinstance(label, str), f"action label must be a str, got {type(label)!r}"
    assert label, "action label should be non-empty for a WORKING peasant"


def test_render_peasant_summary_no_raise(headless_hud: HUD) -> None:
    """Render the peasant info-card onto a real Surface through the moved wrapper — no raise."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    left_rect = pygame.Rect(0, 60, 320, 400)
    hud._render_peasant_summary(surface, _mock_peasant(), left_rect)  # must not raise


def test_render_building_summary_no_raise(headless_hud: HUD) -> None:
    """Render the building status card onto a real Surface through the moved wrapper — no raise."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    rect = pygame.Rect(1600, 60, 320, 400)
    hud._render_building_summary(surface, _mock_building(), rect)  # must not raise


def test_render_hero_focus_profile_no_hero_returns_clean(headless_hud: HUD) -> None:
    """With no selected hero and no micro-view quest hero, ``_render_hero_focus_profile``
    must return without raising (the early-out path). Proves the moved hero-focus seam end
    to end through the wrapper micro_view_manager reaches via hasattr."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    rect = pygame.Rect(1600, 60, 320, 400)
    # A real headless HUD has a real _micro_view whose quest_hero is None by default, so the
    # function falls through to its `if hero is None: return` early-out.
    game_state = {"selected_hero": None, "selected_hero_profile": None}
    hud._render_hero_focus_profile(surface, rect, game_state)  # must not raise


def test_render_hero_focus_profile_with_hero_no_raise(headless_hud: HUD) -> None:
    """Populated hero-focus path: a duck-typed hero (with a ``name``) + ``hero_profile=None``
    drives ``_hero_panel.render_focus_top``, which renders the 'Profile unavailable' line and
    returns. Renders onto a real Surface through the moved path — no raise."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    rect = pygame.Rect(1600, 60, 320, 400)
    hero = SimpleNamespace(name="Nova")
    game_state = {"selected_hero": hero, "selected_hero_profile": None}
    hud._render_hero_focus_profile(surface, rect, game_state)  # must not raise
