"""WK93 Round B-10 seam test (Agent 11 / QA): the radar-minimap cluster was moved
VERBATIM from ``game/ui/hud.py`` into the new ``game/ui/hud_radar.py`` as module
functions (the first bounded slice of the 2477-LOC hud.py god-file):

* ``world_to_radar(wx, wy, inner, world_w, world_h)`` (was the module fn at
  ``hud.py:59``) — re-exported from ``game.ui.hud`` for existing importers
  (``tests/test_wk52_watch_card.py: from game.ui.hud import world_to_radar``).
* ``ensure_radar_terrain_surface(hud, inner, world)``
  (was ``HUD._ensure_radar_terrain_surface``) — cached terrain underlay; reads/writes
  ``hud._radar_terrain_cache_key`` / ``hud._radar_terrain_surface`` (cache state STAYS
  on the HUD).
* ``render_radar_minimap(hud, surface, minimap_rect, game_state)``
  (was ``HUD._render_radar_minimap``) — entity/POI dot overlay.

``HUD`` keeps 1-line delegating wrappers (same names + signatures) that forward to the
module functions with the HUD instance as the first argument, so the ``HUD.render``
call site is UNCHANGED.

This guards the refactor SEAM, not the rendering behaviour itself (that is covered by
the WK67 digest pin + the before/after pygame ``ui_panels`` / ``base_overview``
screenshots, which Agent 11 confirmed visually: the ``ui_panels_hero`` before/after PNGs
are byte-identical, the terrain underlay + static enemy dots in the minimap crop are
pixel-identical, and the only difference is the central hero/building dot cluster band —
which Agent 08 proved is run-to-run sim non-determinism, NOT a regression):

* each moved function lives on ``hud_radar`` and is callable;
* each ``HUD`` wrapper DELEGATES — it calls the module function with the HUD instance
  (``self``) as the first arg, forwards the remaining args, and returns its result
  (proved by spy+monkeypatch of the module functions, and pinned by an AST check of the
  wrapper bodies that they call ``hud_radar.<fn>(self, ...)``);
* ``game.ui.hud.world_to_radar IS game.ui.hud_radar.world_to_radar`` (re-export identity);
* AST guard: ``hud_radar.py`` has NO module-top import of ``game.ui.hud`` (the dependency
  points one way: hud -> hud_radar). A ``TYPE_CHECKING``-only import is allowed and is NOT
  a runtime import, so we only flag unconditional module-top imports;
* a fresh interpreter can import both modules in EITHER order (no module-load cycle).
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

import game.ui.hud_radar as hud_radar
import game.ui.hud as hud_mod
from game.ui.hud import HUD


# The three functions WK93 moved into hud_radar.py.
MOVED_FUNCTIONS = (
    "world_to_radar",
    "ensure_radar_terrain_surface",
    "render_radar_minimap",
)

# wrapper-name -> module-function-name (the delegation contract).
WRAPPER_TO_FN = {
    "_ensure_radar_terrain_surface": "ensure_radar_terrain_surface",
    "_render_radar_minimap": "render_radar_minimap",
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_radar(name: str) -> None:
    """The moved function is present on hud_radar and callable."""
    assert hasattr(hud_radar, name), f"{name} missing from hud_radar"
    assert callable(getattr(hud_radar, name)), f"{name} is not callable"


def _bare_hud() -> HUD:
    """A bare ``HUD`` instance with no ``__init__`` run.

    Constructing a real HUD pulls in a large pygame/UI stack; ``object.__new__`` gives us
    an instance whose bound wrapper method we can call without that construction. The
    wrapper doesn't touch any instance state itself — it just forwards ``self`` to the
    module function — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(HUD)


def test_ensure_terrain_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``HUD._ensure_radar_terrain_surface`` ->
    ``hud_radar.ensure_radar_terrain_surface(self, inner, world)``.

    Spy+monkeypatch the module function and assert the HUD is forwarded as ``self``, the
    remaining args pass through in order, and the wrapper returns the module result."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, inner, world):  # noqa: ANN001 - test spy
        calls.append((hh, inner, world))
        return sentinel

    monkeypatch.setattr(hud_radar, "ensure_radar_terrain_surface", spy)

    inner_marker = object()
    world_marker = object()
    result = h._ensure_radar_terrain_surface(inner_marker, world_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, inner, world = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert inner is inner_marker, "inner must be forwarded"
    assert world is world_marker, "world must be forwarded"


def test_render_minimap_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """``HUD._render_radar_minimap`` ->
    ``hud_radar.render_radar_minimap(self, surface, minimap_rect, game_state)``.

    Spy+monkeypatch the module function and assert the HUD is forwarded as ``self``, the
    remaining args pass through in order, and the wrapper returns the module result."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, surface, minimap_rect, game_state):  # noqa: ANN001 - test spy
        calls.append((hh, surface, minimap_rect, game_state))
        return sentinel

    monkeypatch.setattr(hud_radar, "render_radar_minimap", spy)

    surface_marker = object()
    rect_marker = object()
    state_marker = object()
    result = h._render_radar_minimap(surface_marker, rect_marker, state_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, surface, minimap_rect, game_state = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert surface is surface_marker, "surface must be forwarded"
    assert minimap_rect is rect_marker, "minimap_rect must be forwarded"
    assert game_state is state_marker, "game_state must be forwarded"


def test_wrappers_call_hud_radar_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``hud_radar.<fn>(self, ...)`` with ``self`` as the first argument. This pins the
    delegation even if a future monkeypatch path changed."""
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
                # match hud_radar.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "hud_radar"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call hud_radar.<fn>(self, ...) in source: " f"{missing}"
    )


def test_world_to_radar_reexport_identity() -> None:
    """``game.ui.hud.world_to_radar`` IS ``game.ui.hud_radar.world_to_radar`` — the
    re-export is the same function object (so existing importers of
    ``from game.ui.hud import world_to_radar`` get the moved fn, not a copy)."""
    assert hasattr(hud_mod, "world_to_radar"), "hud must re-export world_to_radar"
    assert hud_mod.world_to_radar is hud_radar.world_to_radar, (
        "hud.world_to_radar must be the SAME object as hud_radar.world_to_radar "
        "(re-export, not a re-definition)"
    )


def test_hud_radar_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_radar must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_radar). A ``TYPE_CHECKING``-only import is allowed and is
    NOT a runtime import, so we only flag unconditional module-top imports."""
    src_path = Path(hud_radar.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):  # module-top statements only
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "game.ui.hud" or alias.name.endswith(".hud"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "game.ui.hud" or mod.endswith(".hud"):
                offenders.append(f"from {mod} import ...")
    assert not offenders, (
        "hud_radar has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_radar", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_radar"),
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
