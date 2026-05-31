"""WK102 Round B-19 seam + behavior test (Agent 11 / QA): the status-message log was
moved VERBATIM from ``game/ui/hud.py`` into the new ``game/ui/hud_messages.py`` as module
functions (the tenth bounded slice of the hud.py god-file, after WK93-101 slices):

The 3 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``add_message(hud, text, color=COLOR_WHITE)``       (was ``HUD.add_message``)
* ``update_messages(hud)``                            (was ``HUD.update`` -- body is
  message-pruning; renamed for clarity at the module level)
* ``render_messages(hud, surface, left_rect=None)``   (was ``HUD.render_messages``)

``HUD`` keeps 1-line delegating wrappers (EXACT names ``add_message`` / ``update`` /
``render_messages``). Note the wrapper for the pruner keeps the generic name ``update``
because ``game/engine.py:819`` calls ``self.hud.update()`` EVERY FRAME; it forwards to the
module fn ``update_messages``. ``add_message`` is the PUBLIC, widest-blast-radius wrapper
(~56 callers / 17 files incl. a getattr reach in pin_alert_watcher.py) -- its name,
signature, and ``COLOR_WHITE`` default are load-bearing. ALL message STATE
(``hud.messages``, ``hud.message_duration``) and the fonts (``hud.font_small``) stay on the
HUD instance and are reached here via the ``hud`` argument; all call sites are UNCHANGED.

This guards the refactor SEAM **and** the message render/append/prune path (messages are
event-driven and auto-expire after 3000ms, so the before/after pygame captures prove only
that scene+chrome are unchanged -- the behavior test below is what proves the message path):

* each moved function lives on ``hud_messages``, is callable, and takes ``hud`` first
  (note the module fn is ``update_messages``, NOT ``update``);
* each ``HUD`` wrapper DELEGATES to the matching ``hud_messages`` module function (proved by
  a real monkeypatch-of-the-module-fn spy -- incl. ``update`` -> ``update_messages`` and the
  PUBLIC ``add_message``);
* AST guard: ``hud_messages.py`` has NO module-top (runtime) import of ``game.ui.hud`` -- a
  ``TYPE_CHECKING``-only ``from game.ui.hud import HUD`` is allowed and is NOT a runtime
  import, so we walk only module-level statements and skip the TYPE_CHECKING block;
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* a headless HUD driven through the moved append/FIFO-cap/prune/render path mutates state as
  expected and renders the message stack onto a real Surface without raising.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when hud / pygame is imported.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import game.ui.hud_messages as hud_messages
from config import COLOR_WHITE
from game.ui.hud import HUD


# The 3 functions WK102 moved into hud_messages.py (module-fn names).
MOVED_FUNCTIONS = (
    "add_message",
    "update_messages",
    "render_messages",
)

# HUD wrapper-name -> hud_messages module-function-name (the delegation contract).
# NOTE: the ``update`` wrapper keeps its generic name (engine.py:819 calls hud.update()
# every frame) but forwards to the module fn ``update_messages``.
WRAPPER_TO_FN = {
    "add_message": "add_message",
    "update": "update_messages",
    "render_messages": "render_messages",
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 3 module fns, each callable with ``hud`` as first param.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_messages(name: str) -> None:
    """The moved function is present on hud_messages and callable."""
    assert hasattr(hud_messages, name), f"{name} missing from hud_messages"
    assert callable(getattr(hud_messages, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    import inspect

    sig = inspect.signature(getattr(hud_messages, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", (
        f"{name} first param is {params[0]!r}, expected 'hud'"
    )


def test_module_update_fn_is_named_update_messages() -> None:
    """The module-level pruner is named ``update_messages`` (NOT ``update``); there is no
    bare ``update`` at module level in hud_messages."""
    assert hasattr(hud_messages, "update_messages")
    assert not hasattr(hud_messages, "update"), (
        "module fn must be named update_messages, not update"
    )


def test_add_message_default_color_is_color_white() -> None:
    """The PUBLIC add_message keeps its ``COLOR_WHITE`` default (load-bearing for ~56
    callers that rely on the single-arg form)."""
    import inspect

    sig = inspect.signature(hud_messages.add_message)
    default = sig.parameters["color"].default
    assert tuple(default) == tuple(COLOR_WHITE), (
        f"add_message color default is {default!r}, expected COLOR_WHITE {COLOR_WHITE!r}"
    )


# ------------------------------------------------------------------
# (2) WRAPPERS DELEGATE: HUD defines the 3 wrappers and forwards to hud_messages.
# ------------------------------------------------------------------

@pytest.mark.parametrize("wrapper", sorted(WRAPPER_TO_FN))
def test_hud_defines_wrapper(wrapper: str) -> None:
    """HUD still defines each wrapper name (add_message / update / render_messages)."""
    assert hasattr(HUD, wrapper), f"HUD missing wrapper {wrapper}"
    assert callable(getattr(HUD, wrapper)), f"HUD.{wrapper} is not callable"


def _bare_hud() -> HUD:
    """A bare ``HUD`` instance with no ``__init__`` run.

    Constructing a real HUD pulls in a large pygame/UI stack; ``object.__new__`` gives us
    an instance whose bound wrapper method we can call without that construction. The
    wrapper doesn't touch any instance state itself -- it just forwards ``self`` to the
    module function -- so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(HUD)


def test_update_wrapper_delegates_to_update_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real monkeypatch-delegation proof for the EVERY-FRAME path: replace
    ``hud_messages.update_messages`` with a sentinel spy, call ``HUD.update`` on a bare
    instance, and assert the spy fired with the HUD forwarded as ``self`` and the wrapper
    returning the module fn's result. (engine.py:819 calls self.hud.update() each frame.)
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh):  # noqa: ANN001 - test spy
        calls.append((hh,))
        return sentinel

    monkeypatch.setattr(hud_messages, "update_messages", spy)

    result = h.update()

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    (hh,) = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"


def test_add_message_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof through the PUBLIC, widest-blast-radius wrapper
    ``HUD.add_message`` -> ``hud_messages.add_message``."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, text, color):  # noqa: ANN001 - test spy
        calls.append((hh, text, color))
        return sentinel

    monkeypatch.setattr(hud_messages, "add_message", spy)

    result = h.add_message("hi", (1, 2, 3))

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, text, color = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert text == "hi"
    assert color == (1, 2, 3)


def test_render_messages_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof for ``HUD.render_messages`` ->
    ``hud_messages.render_messages`` (the internal render() caller path)."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, left_rect=None):  # noqa: ANN001 - test spy
        calls.append((hh, surface, left_rect))
        return sentinel

    monkeypatch.setattr(hud_messages, "render_messages", spy)

    surf_marker = object()
    result = h.render_messages(surf_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, _left = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surf_marker, "surface must be forwarded unchanged"


# ------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD: hud_messages has no module-top import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_messages_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_messages must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_messages). A ``TYPE_CHECKING``-only import is allowed and is
    NOT a runtime import, so we walk only module-level statements (skipping the body of an
    ``if TYPE_CHECKING:`` block) and flag only unconditional module-top imports."""
    src_path = Path(hud_messages.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []

    def _is_hud(mod: str) -> bool:
        return mod == "game.ui.hud" or mod.endswith(".hud")

    for node in ast.iter_child_nodes(tree):  # module-top statements only
        # Permit imports that live inside `if TYPE_CHECKING:` -- not runtime imports.
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
        "hud_messages has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_messages", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_messages"),
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
# (4) BEHAVIOR: drive messages through the moved path on a headless HUD.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) with message state initialised."""
    pygame.init()
    return HUD(1920, 1080)


def test_add_message_appends_with_text_and_color(headless_hud: HUD) -> None:
    """add_message (through the wrapper) appends a {text,color,time} dict."""
    hud = headless_hud
    hud.messages.clear()
    hud.add_message("hello", (200, 50, 50))
    assert len(hud.messages) == 1
    assert hud.messages[0]["text"] == "hello"
    assert tuple(hud.messages[0]["color"]) == (200, 50, 50)
    assert "time" in hud.messages[0]


def test_add_message_fifo_caps_at_five(headless_hud: HUD) -> None:
    """The moved path preserves the 5-message FIFO cap (overflow pops the oldest)."""
    hud = headless_hud
    hud.messages.clear()
    for i in range(7):  # > 5 total
        hud.add_message(f"msg{i}", (10, 20, 30))
    assert len(hud.messages) == 5, (
        f"message list should FIFO-cap at 5, got {len(hud.messages)}"
    )
    # The two oldest (msg0, msg1) should have been popped; msg2..msg6 remain in order.
    assert [m["text"] for m in hud.messages] == [f"msg{i}" for i in range(2, 7)]


def test_add_message_default_color_preserved(headless_hud: HUD) -> None:
    """Single-arg add_message defaults color to COLOR_WHITE (the 56-caller contract)."""
    hud = headless_hud
    hud.messages.clear()
    hud.add_message("def")
    assert tuple(hud.messages[0]["color"]) == tuple(COLOR_WHITE)


def test_update_prunes_stale_and_keeps_fresh(headless_hud: HUD) -> None:
    """update() (-> update_messages) prunes messages older than message_duration and keeps
    fresh ones. This is the every-frame engine.py:819 path."""
    hud = headless_hud
    hud.messages.clear()
    hud.add_message("old")
    # Backdate well beyond message_duration (3000ms).
    hud.messages[0]["time"] = pygame.time.get_ticks() - 5000
    hud.update()
    assert len(hud.messages) == 0, "stale message (>3000ms) must be pruned by update()"

    hud.add_message("fresh")
    hud.update()
    assert len(hud.messages) == 1, "fresh message must survive update()"
    assert hud.messages[0]["text"] == "fresh"


def test_render_messages_draws_pixels(headless_hud: HUD) -> None:
    """render_messages (through the wrapper) draws the message stack at top_bar_height+10,
    x>=10 -- proven by a non-black pixel in the expected band. Also exercises the left_rect
    x-offset path (must not raise)."""
    hud = headless_hud
    surf = pygame.Surface((1920, 1080))
    surf.fill((0, 0, 0))
    hud.messages.clear()
    hud.add_message("PIXELTEST", (255, 255, 255))
    hud.render_messages(surf)  # must not raise

    band_top = hud.top_bar_height + 10
    found = False
    for y in range(band_top, band_top + 18):
        for x in range(10, 400):
            if tuple(surf.get_at((x, y))[:3]) != (0, 0, 0):
                found = True
                break
        if found:
            break
    assert found, (
        "render_messages drew no non-black pixel in the message band "
        f"(y in [{band_top}, {band_top + 18}), x in [10, 400))"
    )

    # left_rect path (x-offset = left_rect.right + 10): must not raise.
    hud.render_messages(surf, pygame.Rect(0, 48, 224, 400))


def test_render_messages_ad_hoc_proof_png(headless_hud: HUD, tmp_path) -> None:
    """Ad-hoc render proof: save a Surface with 2 rendered messages to a PNG, re-load it,
    and confirm both colored lines are present (non-background pixels in two distinct rows).
    Written under pytest's tmp_path so no stray artifact is left in the repo."""
    hud = headless_hud
    surf = pygame.Surface((1920, 1080))
    surf.fill((0, 0, 0))
    hud.messages.clear()
    hud.add_message("WK102 test A", (100, 255, 100))
    hud.add_message("WK102 test B", (255, 180, 80))
    hud.render_messages(surf)

    out = tmp_path / "wk102_msg_render_qa.png"
    pygame.image.save(surf, str(out))
    assert out.exists() and out.stat().st_size > 0

    reloaded = pygame.image.load(str(out))
    band_top = hud.top_bar_height + 10

    def _row_has_ink(y: int) -> bool:
        return any(
            tuple(reloaded.get_at((x, y))[:3]) != (0, 0, 0)
            for x in range(10, 400)
        )

    # First line lives in the first 18px band; the second line one row down (+18).
    assert any(_row_has_ink(y) for y in range(band_top, band_top + 18)), (
        "first rendered message line missing from saved PNG"
    )
    assert any(_row_has_ink(y) for y in range(band_top + 18, band_top + 36)), (
        "second rendered message line missing from saved PNG"
    )
