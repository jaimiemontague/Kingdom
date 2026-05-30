"""WK87 Round B-4 seam test (Agent 11 / QA): the tax-overlay + building world-space
UI cluster moved VERBATIM from ``game/graphics/ursina_renderer.py`` into
``game/graphics/ursina_building_ui.py`` and the public names are RE-EXPORTED from
ursina_renderer for back-compat.

This guards the refactor seam (not the rendering behaviour, which is covered by the
WK61 tests + before/after screenshots):

* the 8 moved functions live on ``ursina_building_ui`` and are callable;
* ``set_tax_gold_overlay_held``/``is_tax_gold_overlay_held`` remain importable from
  ``ursina_renderer`` and are the SAME objects (proves a true re-export, not a copy);
* the tax-overlay held flag round-trips through the public API;
* ``ursina_building_ui`` has NO module-top import of ``ursina_renderer`` (AST guard)
  and a fresh interpreter can import both modules in EITHER order (no module-load
  cycle).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

import game.graphics.ursina_building_ui as building_ui
import game.graphics.ursina_renderer as renderer


# The full set of module functions WK87 moved into ursina_building_ui.py.
MOVED_FUNCTIONS = (
    "set_tax_gold_overlay_held",
    "is_tax_gold_overlay_held",
    "building_tax_overlay_snapshot",
    "_prefab_local_top_y",
    "_building_gold_overlay_y",
    "_building_gold_overlay_world_y",
    "_sync_building_worldspace_ui",
    "_maybe_log_tax_overlay_debug",
)

# The public names ursina_renderer re-exports for back-compat (ursina_app + engine
# lifecycle call set_tax_gold_overlay_held).
REEXPORTED_PUBLIC = (
    "set_tax_gold_overlay_held",
    "is_tax_gold_overlay_held",
)


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_building_ui(name: str) -> None:
    """Every moved function is present on ursina_building_ui and callable."""
    assert hasattr(building_ui, name), f"{name} missing from ursina_building_ui"
    assert callable(getattr(building_ui, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", REEXPORTED_PUBLIC)
def test_public_name_reexported_from_renderer_same_object(name: str) -> None:
    """The public tax-overlay API is still importable from ursina_renderer AND is the
    SAME object as ursina_building_ui's — a true re-export, not a divergent copy."""
    assert hasattr(renderer, name), f"{name} not re-exported from ursina_renderer"
    assert getattr(renderer, name) is getattr(building_ui, name), (
        f"{name} re-export is not the same object as ursina_building_ui's "
        "(re-export must alias, not copy)"
    )


def test_building_tax_overlay_snapshot_reexported_from_renderer_same_object() -> None:
    """building_tax_overlay_snapshot is consumed via ursina_renderer by WK61 tests —
    it too must be the same object after the move."""
    assert (
        renderer.building_tax_overlay_snapshot
        is building_ui.building_tax_overlay_snapshot
    )


def test_set_get_tax_overlay_held_round_trips() -> None:
    """The hold-G overlay flag round-trips through the public API (set True -> is True;
    set False -> is False). Restored to its original value afterward."""
    original = building_ui.is_tax_gold_overlay_held()
    try:
        building_ui.set_tax_gold_overlay_held(True)
        assert building_ui.is_tax_gold_overlay_held() is True
        # The re-exported name drives the SAME module state.
        renderer.set_tax_gold_overlay_held(False)
        assert renderer.is_tax_gold_overlay_held() is False
        assert building_ui.is_tax_gold_overlay_held() is False
    finally:
        building_ui.set_tax_gold_overlay_held(bool(original))
    assert building_ui.is_tax_gold_overlay_held() == bool(original)


def test_building_ui_has_no_module_top_import_of_renderer() -> None:
    """AST guard: ursina_building_ui must not import ursina_renderer at module top
    (the dependency points one way: renderer -> building_ui). Any lazy/function-local
    import is fine and not flagged here."""
    src_path = Path(building_ui.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8"), filename=str(src_path))
    offenders: list[str] = []
    for node in ast.iter_child_nodes(tree):  # module-top statements only
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "game.graphics.ursina_renderer" or alias.name.endswith(
                    "ursina_renderer"
                ):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_renderer"):
                offenders.append(f"from {mod} import ...")
    assert not offenders, (
        "ursina_building_ui has a module-top import of ursina_renderer "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.graphics.ursina_building_ui", "game.graphics.ursina_renderer"),
        ("game.graphics.ursina_renderer", "game.graphics.ursina_building_ui"),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a module-load
    cycle. Runs out-of-process so the already-imported modules in this session cannot
    mask an import-order bug."""
    repo_root = Path(__file__).resolve().parents[1]
    code = (
        f"import importlib;"
        f"importlib.import_module({first!r});"
        f"importlib.import_module({second!r});"
        f"print('OK')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"fresh import {first} -> {second} failed (rc={proc.returncode}).\n"
        f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    )
    assert "OK" in proc.stdout, f"missing OK marker. STDOUT:\n{proc.stdout}"
