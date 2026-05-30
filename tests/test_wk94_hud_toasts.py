"""WK94 Round B-11 seam + behavior test (Agent 11 / QA): the toast subsystem was moved
VERBATIM from ``game/ui/hud.py`` into the new ``game/ui/hud_toasts.py`` as module
functions (the second bounded slice of the hud.py god-file, after WK93's hud_radar):

The 9 moved module functions (each takes the HUD instance, ``hud``, as the FIRST arg):

* ``on_wave_incoming(hud, event)``                  (was ``HUD.on_wave_incoming``, WK60)
* ``on_wave_cleared(hud, event)``                   (was ``HUD.on_wave_cleared``, WK60)
* ``render_wave_toast(hud, surface)``               (was ``HUD._render_wave_toast``, WK60)
* ``notify_poi_discovered(hud, poi_name, itype)``   (was ``HUD.notify_poi_discovered``, WK55)
* ``check_poi_discoveries(hud, game_state)``         (was ``HUD._check_poi_discoveries``, WK55)
* ``ensure_poi_interaction_subscription(hud, gs)``   (was ``HUD._ensure_poi_interaction_subscription``, WK59)
* ``on_poi_interaction(hud, event)``                (was ``HUD._on_poi_interaction``, WK59)
* ``on_boss_spawned_toast(hud, event)``             (was ``HUD._on_boss_spawned_toast``, WK59)
* ``render_poi_toasts(hud, surface)``               (was ``HUD._render_poi_toasts``, WK55)

``HUD`` keeps 1-line delegating wrappers (same names + signatures, INCLUDING the
leading-underscore private names that the engine.py EventBus subscriptions and HUD.render
call) that forward to the module functions with the HUD instance as the first argument, so
all call sites are UNCHANGED. ALL toast STATE stays on the HUD (``__init__`` lines 333-351).

This guards the refactor SEAM **and** the toast render path (toasts are event-driven and
do NOT appear in a steady-state screenshot, so the before/after pygame captures prove only
that scene+chrome are unchanged — the behavior test below is what proves the toast path):

* each moved function lives on ``hud_toasts``, is callable, and takes ``hud`` first;
* each ``HUD`` wrapper DELEGATES to the matching ``hud_toasts`` module function (proved by a
  real monkeypatch-of-the-module-fn spy AND a belt-and-suspenders AST/source check);
* AST guard: ``hud_toasts.py`` has NO module-top (runtime) import of ``game.ui.hud`` — a
  ``TYPE_CHECKING``-only ``from game.ui.hud import HUD`` is allowed (it is not a runtime
  import), so we walk only module-level statements and skip the TYPE_CHECKING block;
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* a headless HUD driven through the moved wave + POI toast path mutates state as expected
  and renders both toast banners onto a real Surface without raising.
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

import game.ui.hud_toasts as hud_toasts
from game.ui.hud import HUD


# The 9 functions WK94 moved into hud_toasts.py.
MOVED_FUNCTIONS = (
    "on_wave_incoming",
    "on_wave_cleared",
    "render_wave_toast",
    "notify_poi_discovered",
    "check_poi_discoveries",
    "ensure_poi_interaction_subscription",
    "on_poi_interaction",
    "on_boss_spawned_toast",
    "render_poi_toasts",
)

# HUD wrapper-name -> hud_toasts module-function-name (the delegation contract).
# NOTE: several wrappers keep their leading-underscore private names because the engine
# EventBus subscriptions and HUD.render() call sites use those exact names.
WRAPPER_TO_FN = {
    "on_wave_incoming": "on_wave_incoming",
    "on_wave_cleared": "on_wave_cleared",
    "_render_wave_toast": "render_wave_toast",
    "notify_poi_discovered": "notify_poi_discovered",
    "_check_poi_discoveries": "check_poi_discoveries",
    "_ensure_poi_interaction_subscription": "ensure_poi_interaction_subscription",
    "_on_poi_interaction": "on_poi_interaction",
    "_on_boss_spawned_toast": "on_boss_spawned_toast",
    "_render_poi_toasts": "render_poi_toasts",
}


# ------------------------------------------------------------------
# (1) EXISTENCE: 9 module fns, each callable with ``hud`` as first param.
# ------------------------------------------------------------------

@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_hud_toasts(name: str) -> None:
    """The moved function is present on hud_toasts and callable."""
    assert hasattr(hud_toasts, name), f"{name} missing from hud_toasts"
    assert callable(getattr(hud_toasts, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_takes_hud_first(name: str) -> None:
    """Each moved module function takes the HUD instance as its FIRST parameter."""
    import inspect

    sig = inspect.signature(getattr(hud_toasts, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected 'hud' first"
    assert params[0] == "hud", (
        f"{name} first param is {params[0]!r}, expected 'hud'"
    )


# ------------------------------------------------------------------
# (2) WRAPPERS DELEGATE: HUD defines the 9 wrappers and forwards to hud_toasts.
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


def test_on_wave_incoming_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real monkeypatch-delegation proof: replace ``hud_toasts.on_wave_incoming`` with a
    sentinel spy, call ``HUD.on_wave_incoming`` on a bare instance, and assert the spy
    fired with the HUD forwarded as ``self`` (first arg), the event forwarded, and the
    wrapper returning the module fn's result.

    The wrapper imports ``hud_toasts`` lazily inside its body (``from game.ui import
    hud_toasts``); that binds the *module object* we monkeypatch here, so the patch is
    seen by the wrapper.
    """
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, event):  # noqa: ANN001 - test spy
        calls.append((hh, event))
        return sentinel

    monkeypatch.setattr(hud_toasts, "on_wave_incoming", spy)

    event_marker = {"name": "Sentinel Wave", "seconds": 3}
    result = h.on_wave_incoming(event_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, event = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert event is event_marker, "event must be forwarded unchanged"


def test_on_poi_interaction_wrapper_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Second real monkeypatch-delegation proof, through a leading-underscore private
    wrapper (``HUD._on_poi_interaction`` — the EventBus-registered bound-method path)."""
    h = _bare_hud()
    calls: list[tuple] = []
    sentinel = object()

    def spy(hh, event):  # noqa: ANN001 - test spy
        calls.append((hh, event))
        return sentinel

    monkeypatch.setattr(hud_toasts, "on_poi_interaction", spy)

    event_marker = {"interaction_type": "loot", "gold": 7}
    result = h._on_poi_interaction(event_marker)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    hh, event = calls[0]
    assert hh is h, "HUD (self) must be forwarded as the first arg"
    assert event is event_marker, "event must be forwarded unchanged"


def test_wrappers_reference_hud_toasts_in_source() -> None:
    """Belt-and-suspenders: every wrapper body references the ``hud_toasts`` module and
    calls the matching module function. Pins the delegation across all 9 wrappers even
    where we only monkeypatch-prove two of them above."""
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
                # match hud_toasts.<target_fn>(self, ...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "hud_toasts"
                    and call.args
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == "self"
                ):
                    found[node.name] = True

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call hud_toasts.<fn>(self, ...) in source: " f"{missing}"
    )


# ------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD: hud_toasts has no module-top import of game.ui.hud.
# ------------------------------------------------------------------

def test_hud_toasts_has_no_module_top_import_of_hud() -> None:
    """AST guard: hud_toasts must not import game.ui.hud at module top (the dependency
    points one way: hud -> hud_toasts). A ``TYPE_CHECKING``-only import is allowed and is
    NOT a runtime import, so we walk only module-level statements (skipping the body of an
    ``if TYPE_CHECKING:`` block) and flag only unconditional module-top imports."""
    src_path = Path(hud_toasts.__file__)
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
        "hud_toasts has a module-top (runtime) import of game.ui.hud "
        f"(would risk a cycle): {offenders}"
    )


@pytest.mark.parametrize(
    "first,second",
    [
        ("game.ui.hud_toasts", "game.ui.hud"),
        ("game.ui.hud", "game.ui.hud_toasts"),
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
# (4) BEHAVIOR: drive toasts through the moved path on a headless HUD.
# ------------------------------------------------------------------

@pytest.fixture
def headless_hud() -> HUD:
    """A real headless HUD (SDL dummy video driver) with toast state initialised."""
    pygame.init()
    return HUD(1920, 1080)


def test_wave_toast_path_through_wrappers(headless_hud: HUD) -> None:
    """Drive the wave-event toast through the moved path: incoming -> render -> cleared."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))

    hud.on_wave_incoming({"name": "Test Wave", "seconds": 5})
    assert hud._wave_toast_text is not None, "wave incoming must set the toast text"
    assert "Test Wave" in hud._wave_toast_text
    hud._render_wave_toast(surface)  # must not raise

    hud.on_wave_cleared({"name": "Test", "reward": 100})
    assert hud._wave_toast_text is not None
    assert "Cleared" in hud._wave_toast_text, (
        f"cleared toast text should contain 'Cleared', got {hud._wave_toast_text!r}"
    )
    hud._render_wave_toast(surface)  # must not raise


def test_poi_toast_path_through_wrappers(headless_hud: HUD) -> None:
    """Drive the POI toast cluster through the moved path: interaction, boss, discovery.

    The steady-state POI list caps at 3 (a pop occurs on overflow), so we assert presence
    by content rather than relying on exact lengths where the cap could interfere."""
    hud = headless_hud
    surface = pygame.Surface((1920, 1080))

    # POI interaction (loot) -> a toast is queued.
    n0 = len(hud._poi_toasts)
    hud._on_poi_interaction(
        {
            "interaction_type": "loot",
            "hero_name": "Bob",
            "poi_name": "Cave",
            "gold": 50,
        }
    )
    assert len(hud._poi_toasts) == n0 + 1, "loot interaction must queue one toast"
    assert any("Cave" in t[0] and "50" in t[0] for t in hud._poi_toasts), (
        "loot toast should mention the POI name and gold amount"
    )
    hud._render_poi_toasts(surface)  # must not raise

    # Boss spawn -> a boss toast naming the POI.
    hud._on_boss_spawned_toast({"poi_name": "Lair"})
    assert any("Lair" in t[0] for t in hud._poi_toasts), (
        "boss-spawned toast should mention the POI name"
    )

    # Public discovery API -> a 'Discovered' toast.
    hud.notify_poi_discovered("Shrine", "shrine")
    assert any("Discovered" in t[0] and "Shrine" in t[0] for t in hud._poi_toasts), (
        "notify_poi_discovered should queue a 'Discovered: <name>' toast"
    )
    hud._render_poi_toasts(surface)  # must not raise


def test_poi_toast_list_caps_at_three(headless_hud: HUD) -> None:
    """The moved path preserves the 3-toast cap (overflow pops the oldest)."""
    hud = headless_hud
    for i in range(6):
        hud._on_poi_interaction(
            {"interaction_type": "loot", "poi_name": f"Cave{i}", "gold": i}
        )
    assert len(hud._poi_toasts) == 3, (
        f"POI toast list should cap at 3, got {len(hud._poi_toasts)}"
    )
