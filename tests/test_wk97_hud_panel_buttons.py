"""WK97 Round B-14 seam + behavior test (Agent 11 / QA): the panel-chrome button
render cluster was moved VERBATIM from ``game/ui/hud.py`` into the new
``game/ui/hud_panel_buttons.py`` as module functions (the FIFTH bounded slice of the
hud.py god-file, after WK93 hud_radar, WK94 hud_toasts, WK95 hud_summaries,
WK96 hud_watch_card):

The 6 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``render_right_close_button(hud, surface, right_rect)``   (was ``HUD._render_right_close_button``)
* ``render_left_close_button(hud, surface, left_rect)``     (was ``HUD._render_left_close_button`` — lazy-inits ``hud._left_close_button``)
* ``render_pin_button(hud, surface, left_rect, game_state)``(was ``HUD._render_pin_button`` — WK51 pin toggle)
* ``trigger_recall_flash(hud)``                             (was ``HUD.trigger_recall_flash`` — WK52; called by ``game/ui/pin_alert_watcher.py:102``)
* ``render_memorial_button(hud, surface, memorial_rect, game_state)`` (was ``HUD._render_memorial_button``)
* ``render_recall_button(hud, surface, recall_rect, game_state)``     (was ``HUD._render_recall_button`` — WK51 bottom-bar recall)

This slice ALSO moves the ``COLOR_PIN_GOLD = (220, 180, 50)`` constant — the new module
now OWNS it (the pin renderer is its only consumer; verified no other use in game/tests/tools)
so there is NO re-export, and the constant was REMOVED from hud.py.

``HUD`` keeps 1-line delegating wrappers (same names + signatures, INCLUDING the
underscore-prefixed private names the render() call sites use AND the public
``trigger_recall_flash`` that the EXTERNAL ``game/ui/pin_alert_watcher.py`` calls) that
forward to the module functions with the HUD instance first, so all call sites are
UNCHANGED. All hit-rect/flash STATE (``right_close_rect``, ``left_close_rect``,
``pin_button_rect``, ``memorial_btn_rect``, ``recall_rect``, ``_recall_flash_end_ms``, the
``_recall_*`` overlays/caches, ``_pin_slot``, ``_button_*`` textures, ``_frame_*`` colors,
fonts, ``theme``) STAYS on the HUD; the moved functions reach it via the ``hud`` argument.

This guards the refactor SEAM **and** the button render path (the panel-chrome buttons only
draw when a panel is open / a hero is selected / pinned, so the steady-state before/after
captures alone do not exercise them — the behavior test below is what proves the buttons draw
through the moved path and that the hit-rects get set):

* each moved function lives on ``hud_panel_buttons``, is callable, takes ``hud`` first
  (``trigger_recall_flash`` takes ONLY ``hud``);
* ``hud_panel_buttons.COLOR_PIN_GOLD == (220, 180, 50)``;
* each ``HUD`` wrapper DELEGATES to the matching ``hud_panel_buttons`` module function (proved
  by a real monkeypatch-of-the-module-fn spy — INCLUDING ``trigger_recall_flash`` since the
  external ``pin_alert_watcher`` calls it — plus a render_* wrapper, AND a belt-and-suspenders
  AST/source check across all 6 wrappers);
* AST guard: ``hud_panel_buttons.py`` has NO module-top (runtime) import of ``game.ui.hud`` (a
  ``TYPE_CHECKING``-only import is allowed) + a fresh interpreter imports both orders;
* a headless HUD driven through the moved wrappers renders each button onto a real Surface
  without raising AND sets the matching hit-rect (``right_close_rect`` / ``left_close_rect`` /
  ``pin_button_rect`` / ``recall_rect`` / ``memorial_btn_rect``); the pin button clears its
  rect to ``None`` when no hero is selected; and ``trigger_recall_flash`` sets
  ``_recall_flash_end_ms > 0``.
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

import game.ui.hud_panel_buttons as hud_panel_buttons
from game.ui.hud import HUD


# The 6 functions WK97 moved into hud_panel_buttons.py.
MOVED_FUNCTIONS = (
    "render_right_close_button",
    "render_left_close_button",
    "render_pin_button",
    "trigger_recall_flash",
    "render_memorial_button",
    "render_recall_button",
)

# HUD wrapper-name -> hud_panel_buttons module-function-name (the delegation contract).
# NOTE: the render_* wrappers keep their leading-underscore private names because the
# render() call sites use those exact names; ``trigger_recall_flash`` keeps its PUBLIC
# name because game/ui/pin_alert_watcher.py:102 calls self._hud.trigger_recall_flash().
WRAPPER_TO_FN = {
    "_render_right_close_button": "render_right_close_button",
    "_render_left_close_button": "render_left_close_button",
    "_render_pin_button": "render_pin_button",
    "trigger_recall_flash": "trigger_recall_flash",
    "_render_memorial_button": "render_memorial_button",
    "_render_recall_button": "render_recall_button",
}

# COLOR_PIN_GOLD now lives on hud_panel_buttons.
EXPECTED_COLOR_PIN_GOLD = (220, 180, 50)


# ------------------------------------------------------------------
# (1) EXISTENCE: 6 module fns (hud-first) + COLOR_PIN_GOLD on hud_panel_buttons.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_panel_buttons(name: str) -> None:
    """The moved function is present on hud_panel_buttons and callable."""
    assert hasattr(hud_panel_buttons, name), f"{name} missing from hud_panel_buttons"
    assert callable(getattr(hud_panel_buttons, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    sig = inspect.signature(getattr(hud_panel_buttons, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", f"{name} first param is {params[0]!r}, expected 'hud'"


def test_trigger_recall_flash_takes_only_hud() -> None:
    """``trigger_recall_flash`` takes ONLY ``hud`` (no other params) — pins the signature
    the external pin_alert_watcher relies on (it calls it with zero extra args)."""
    sig = inspect.signature(hud_panel_buttons.trigger_recall_flash)
    params = list(sig.parameters)
    assert params == ["hud"], f"trigger_recall_flash params are {params!r}, expected ['hud']"


def test_color_pin_gold_lives_on_module_with_expected_value() -> None:
    """``COLOR_PIN_GOLD`` lives on hud_panel_buttons with the expected RGB tuple."""
    assert hasattr(hud_panel_buttons, "COLOR_PIN_GOLD"), "COLOR_PIN_GOLD missing from hud_panel_buttons"
    assert hud_panel_buttons.COLOR_PIN_GOLD == EXPECTED_COLOR_PIN_GOLD, (
        f"COLOR_PIN_GOLD == {hud_panel_buttons.COLOR_PIN_GOLD!r}, expected {EXPECTED_COLOR_PIN_GOLD!r}"
    )


def test_color_pin_gold_removed_from_hud() -> None:
    """``COLOR_PIN_GOLD`` was REMOVED from game.ui.hud (no re-export — it has no consumers
    other than the now-moved pin renderer)."""
    import game.ui.hud as hud_mod

    assert not hasattr(hud_mod, "COLOR_PIN_GOLD"), (
        "COLOR_PIN_GOLD must be removed from game.ui.hud (the move owns it; no re-export)"
    )


# ------------------------------------------------------------------
# (2) WRAPPERS DELEGATE: HUD defines the 6 wrappers and forwards to hud_panel_buttons.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (the render_* underscore ones + public
    ``trigger_recall_flash``)."""
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


def test_trigger_recall_flash_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof through the wrapper the EXTERNAL
    ``game/ui/pin_alert_watcher.py:102`` reaches via ``self._hud.trigger_recall_flash()``:
    replace ``hud_panel_buttons.trigger_recall_flash`` with a sentinel spy, call
    ``HUD.trigger_recall_flash`` on a bare instance, and assert the spy fired with the HUD
    forwarded as ``self`` (the only arg) and the wrapper returning the module fn's result.

    The wrapper imports ``hud_panel_buttons`` lazily inside its body (``from game.ui import
    hud_panel_buttons``); that binds the *module object* we monkeypatch here, so the patch
    is seen by the wrapper.
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh):  # noqa: ANN001 - test spy
        calls.append((hh,))
        return sentinel

    monkeypatch.setattr(hud_panel_buttons, "trigger_recall_flash", spy)

    result = h.trigger_recall_flash()

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    (hh,) = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the only arg"


def test_render_pin_button_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second real monkeypatch-delegation proof, through the ``_render_pin_button`` render_*
    wrapper (a render() call site at hud.py)."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, left_rect, game_state):  # noqa: ANN001 - test spy
        calls.append((hh, surface, left_rect, game_state))
        return sentinel

    monkeypatch.setattr(hud_panel_buttons, "render_pin_button", spy)

    surface_marker = object()
    rect_marker = object()
    state_marker = object()
    result = h._render_pin_button(surface_marker, rect_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, left_rect, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert left_rect is rect_marker, "left_rect must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_wrappers_reference_hud_panel_buttons_in_source() -> None:
    """Belt-and-suspenders: every wrapper body references the ``hud_panel_buttons`` module and
    calls the matching module function with ``self`` first. Pins the delegation across all 6
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
                # match hud_panel_buttons.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "hud_panel_buttons"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call hud_panel_buttons.<fn>(self, ...) in source: " f"{missing}"
    )


# ------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD: hud_panel_buttons has no module-top import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_panel_buttons_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_panel_buttons must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_panel_buttons). A ``TYPE_CHECKING``-only import is allowed and
    is NOT a runtime import, so we walk only module-level statements (skipping the body of an
    ``if TYPE_CHECKING:`` block) and flag only unconditional module-top imports."""
    src_path = Path(hud_panel_buttons.__file__)
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
        "hud_panel_buttons has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_panel_buttons", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_panel_buttons"),
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
# (4) BEHAVIOR: render each panel-chrome button through the moved wrapper on a headless HUD,
#     and assert the matching hit-rect / flash state got set.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) — has real hit-rect/flash state
    (``_pin_slot`` / ``_button_*`` textures / ``_frame_*`` colors / fonts / ``theme`` /
    ``memorial_card`` / ``_recall_*`` caches), so the moved functions can reach them via ``hud``."""
    pygame.init()
    return HUD(1920, 1080)


def test_render_right_close_button_sets_hit_rect(headless_hud: HUD) -> None:
    """The right-panel close X draws through the moved wrapper and sets ``right_close_rect``."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    hud._render_right_close_button(surface, pygame.Rect(1700, 40, 200, 400))  # must not raise
    assert hud.right_close_rect is not None, "right_close_rect should be set after a right-close render"


def test_render_left_close_button_sets_hit_rect(headless_hud: HUD) -> None:
    """The left-panel close X (lazy-inits ``_left_close_button``) draws through the moved
    wrapper and sets ``left_close_rect``."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    hud._render_left_close_button(surface, pygame.Rect(0, 40, 200, 400))  # must not raise
    assert hud.left_close_rect is not None, "left_close_rect should be set after a left-close render"


def test_render_pin_button_sets_rect_for_selected_hero(headless_hud: HUD) -> None:
    """With a selected hero, the WK51 pin toggle draws and sets ``pin_button_rect``."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    game_state = {"selected_hero": SimpleNamespace(hero_id="h1")}
    hud._render_pin_button(surface, pygame.Rect(0, 40, 200, 400), game_state)  # must not raise
    assert hud.pin_button_rect is not None, "pin_button_rect should be set when a hero is selected"


def test_render_pin_button_clears_rect_when_no_hero(headless_hud: HUD) -> None:
    """With no selected hero, the pin renderer early-outs and clears ``pin_button_rect`` to None."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))
    # Seed a stale rect so we prove the renderer resets it (not merely "stays None").
    hud.pin_button_rect = pygame.Rect(0, 0, 10, 10)
    hud._render_pin_button(surface, pygame.Rect(0, 40, 200, 400), {"selected_hero": None})
    assert hud.pin_button_rect is None, "pin_button_rect must be cleared to None when no hero is selected"


def test_render_recall_button_sets_hit_rect(headless_hud: HUD) -> None:
    """With a pinned (alive) hero + a matching profile, the WK51 bottom-bar recall button
    draws through the moved wrapper and sets ``recall_rect``. The hero is in
    ``hero_profiles_by_id`` so ``update_liveness`` sees it alive (no unpin), and the profile's
    identity.name drives the label."""
    hud = headless_hud
    hud._pin_slot.hero_id = "h1"
    surface = pygame.Surface((1920, 1080))
    game_state = {
        "hero_profiles_by_id": {"h1": SimpleNamespace(identity=SimpleNamespace(name="Nova"))}
    }
    hud._render_recall_button(surface, pygame.Rect(8, 1000, 180, 40), game_state)  # must not raise
    assert hud.recall_rect is not None, "recall_rect should be set for a pinned, alive hero"


def test_render_recall_button_clears_rect_when_not_pinned(headless_hud: HUD) -> None:
    """With no hero pinned (``_pin_slot.hero_id is None``), the recall renderer early-outs and
    clears ``recall_rect`` to None."""
    hud = headless_hud
    hud.recall_rect = pygame.Rect(0, 0, 10, 10)  # stale; must be reset
    surface = pygame.Surface((1920, 1080))
    hud._render_recall_button(surface, pygame.Rect(8, 1000, 180, 40), {})
    assert hud.recall_rect is None, "recall_rect must be cleared to None when no hero is pinned"


def test_render_memorial_button_sets_hit_rect(headless_hud: HUD) -> None:
    """With a pending memorial record and the memorial card hidden, the memorial opener draws
    through the moved wrapper and sets ``memorial_btn_rect``."""
    hud = headless_hud
    hud._pending_memorial = object()
    assert hud.memorial_card.visible is False, "memorial card must be hidden for the button to draw"
    surface = pygame.Surface((1920, 1080))
    hud._render_memorial_button(surface, pygame.Rect(8, 1000, 180, 40), {})  # must not raise
    assert hud.memorial_btn_rect is not None, "memorial_btn_rect should be set when a memorial is pending"


def test_render_memorial_button_clears_rect_when_no_pending(headless_hud: HUD) -> None:
    """With no pending memorial, the renderer early-outs and clears ``memorial_btn_rect``."""
    hud = headless_hud
    hud._pending_memorial = None
    hud.memorial_btn_rect = pygame.Rect(0, 0, 10, 10)  # stale; must be reset
    surface = pygame.Surface((1920, 1080))
    hud._render_memorial_button(surface, pygame.Rect(8, 1000, 180, 40), {})
    assert hud.memorial_btn_rect is None, "memorial_btn_rect must be cleared to None when nothing is pending"


def test_trigger_recall_flash_sets_flash_end(headless_hud: HUD) -> None:
    """``hud.trigger_recall_flash()`` (the public wrapper pin_alert_watcher calls) sets
    ``_recall_flash_end_ms`` to a positive value through the moved path."""
    hud = headless_hud
    hud.trigger_recall_flash()
    assert hud._recall_flash_end_ms > 0, "trigger_recall_flash should set _recall_flash_end_ms > 0"
