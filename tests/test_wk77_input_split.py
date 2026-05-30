"""WK77 Round B-2e seam tests — InputHandler split into the ``game/input/`` package.

WK77 moved ``InputHandler.handle_mousedown`` / ``handle_mousemove`` /
``handle_keydown`` / ``select_building_for_placement`` verbatim into
``game/input/{mouse,keyboard,placement}.py`` as module functions taking the live
``InputHandler`` as ``ih`` (WK69/WK75/WK76 pure-move pattern). ``game/input_handler.py``
keeps 1-line delegating wrappers of the same names.

This file is the WAVE-2 (Agent 11 / QA) seam test. It does NOT re-test input behavior
(that is covered byte-identically by the WK68 button/paused tests +
``test_input_handler_gamecommands`` + the full suite). It proves the *seam*:

1. the four package functions exist and are callable on the expected modules;
2. each ``InputHandler`` wrapper DELEGATES to its module function, passing the live
   ``InputHandler`` as the first positional arg and forwarding the call args/return;
3. an AST/import guard: ``game/input/mouse.py`` + ``game/input/keyboard.py`` do NOT
   import ``game.input_handler`` at module load time (TYPE_CHECKING-only) — i.e. no
   module-level import cycle. (keyboard.py legitimately lazy-imports the single-source
   ``BUILD_HOTKEY_TO_TYPE`` *inside* ``handle_keydown`` — a function-body import, which
   cannot create a cycle and is the documented WK70 pattern.)
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

# Headless SDL — InputHandler / the input package pull in pygame transitively.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from game import input as input_pkg  # noqa: E402  (after SDL env)
from game.input import keyboard, mouse, placement  # noqa: E402
from game.input_handler import InputHandler  # noqa: E402


# Repo root = two levels up from this test file (tests/ -> repo root).
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_ih() -> InputHandler:
    """Build a real InputHandler over a minimal command surface.

    Mirrors tests/test_input_handler_gamecommands.py: ``InputHandler.__init__`` only
    stores ``commands`` and the five typed protocol aliases, so a bare SimpleNamespace
    is sufficient — the delegation tests monkeypatch the module function, so its body
    (which would touch the richer command surface) never runs.
    """
    return InputHandler(SimpleNamespace())


# ---------------------------------------------------------------------------
# 1. The package functions exist and are callable on the expected modules.
# ---------------------------------------------------------------------------

def test_package_exposes_input_subpackage():
    assert input_pkg.__name__ == "game.input"


@pytest.mark.parametrize(
    "module, fn_name",
    [
        (mouse, "handle_mousedown"),
        (mouse, "handle_mousemove"),
        (keyboard, "handle_keydown"),
        (placement, "select_building_for_placement"),
    ],
)
def test_module_function_exists_and_callable(module, fn_name):
    fn = getattr(module, fn_name, None)
    assert fn is not None, f"{module.__name__}.{fn_name} missing"
    assert callable(fn), f"{module.__name__}.{fn_name} is not callable"


# ---------------------------------------------------------------------------
# 2. Each InputHandler wrapper delegates to its module function, forwarding
#    (ih, *args) and returning the module function's result.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "module, fn_name, wrapper_name, extra_args",
    [
        (mouse, "handle_mousedown", "handle_mousedown", ("EVENT_MD",)),
        (mouse, "handle_mousemove", "handle_mousemove", ("EVENT_MM",)),
        (keyboard, "handle_keydown", "handle_keydown", ("EVENT_KD",)),
        (
            placement,
            "select_building_for_placement",
            "select_building_for_placement",
            ("warrior_guild",),
        ),
    ],
)
def test_wrapper_delegates_to_module_function(
    monkeypatch, module, fn_name, wrapper_name, extra_args
):
    ih = _make_ih()
    calls = []
    sentinel = object()

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(module, fn_name, spy)

    wrapper = getattr(ih, wrapper_name)
    result = wrapper(*extra_args)

    # Wrapper returned exactly what the module function returned.
    assert result is sentinel, f"{wrapper_name} did not forward the return value"

    # Module function fired exactly once.
    assert len(calls) == 1, f"{module.__name__}.{fn_name} fired {len(calls)} times (want 1)"

    args, kwargs = calls[0]
    # First positional arg is the live InputHandler instance.
    assert args[0] is ih, f"{wrapper_name} did not pass the InputHandler as first arg"
    # Remaining args forwarded verbatim.
    assert args[1:] == extra_args, (
        f"{wrapper_name} forwarded {args[1:]!r}, expected {extra_args!r}"
    )
    assert kwargs == {}, f"{wrapper_name} forwarded unexpected kwargs {kwargs!r}"


# ---------------------------------------------------------------------------
# 3. AST/import guard: no module-level import of game.input_handler (no cycle).
# ---------------------------------------------------------------------------

def _module_level_imports_of(path: Path, target: str):
    """Return module-top-level (non-TYPE_CHECKING) imports that reference ``target``.

    Walks only the module body's direct children (and the bodies of any top-level
    ``if`` blocks whose test is NOT ``TYPE_CHECKING``). Imports nested inside function
    or class bodies are *runtime-lazy* and cannot create an import cycle, so they are
    intentionally excluded.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []

    def _scan(import_node):
        if isinstance(import_node, ast.Import):
            for alias in import_node.names:
                if alias.name == target or alias.name.startswith(target + "."):
                    found.append(ast.dump(import_node))
        elif isinstance(import_node, ast.ImportFrom):
            mod = import_node.module or ""
            if mod == target or mod.startswith(target + "."):
                found.append(ast.dump(import_node))

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _scan(node)
        elif isinstance(node, ast.If):
            test = node.test
            is_type_checking = isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
            if is_type_checking:
                continue  # TYPE_CHECKING-only imports are allowed (never executed)
            for sub in node.body + node.orelse:
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    _scan(sub)

    return found


@pytest.mark.parametrize("rel_path", ["game/input/mouse.py", "game/input/keyboard.py"])
def test_no_module_level_input_handler_import(rel_path):
    path = _REPO_ROOT / rel_path
    assert path.exists(), f"{rel_path} missing"
    offending = _module_level_imports_of(path, "game.input_handler")
    assert not offending, (
        f"{rel_path} imports game.input_handler at module load time (import-cycle risk); "
        f"the InputHandler import must be TYPE_CHECKING-only. Offending: {offending}"
    )


def test_type_checking_import_present_in_mouse_and_keyboard():
    """Sanity: the InputHandler import IS present, but only under TYPE_CHECKING."""
    for rel_path in ("game/input/mouse.py", "game/input/keyboard.py"):
        path = _REPO_ROOT / rel_path
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        tc_imports = []
        for node in tree.body:
            if isinstance(node, ast.If):
                test = node.test
                if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
                    for sub in node.body:
                        if isinstance(sub, ast.ImportFrom) and sub.module == "game.input_handler":
                            tc_imports.append([a.name for a in sub.names])
        assert ["InputHandler"] in tc_imports, (
            f"{rel_path} should TYPE_CHECKING-import InputHandler"
        )
