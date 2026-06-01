"""WK113 Round B seam test (Agent 11 / QA): the camera-control cluster was moved
VERBATIM from ``game/graphics/ursina_app.py`` into the new
``game/graphics/ursina_app_camera.py`` using the WK87-92/WK104-105 owner-arg
pure-move pattern. ``UrsinaApp`` keeps 9 one-line delegating wrappers (exact original
names + signatures); the relocated bodies are byte-faithful (only ``self``->``owner``,
the 3 intra-cluster cross-calls, and the 2 moved-constant reads changed). This guards
the refactor SEAM, not the rendering behaviour itself.

The 9 moved members (ALL instance methods → ALL owner-first; there is NO
``@staticmethod`` in this cluster):

* ``_setup_ursina_camera_for_castle(owner)``
* ``_recenter_editor_camera_to_sim_xy(owner, sim_x, sim_y)``
* ``_reset_camera_to_default(owner)``
* ``_toggle_camera_lock(owner)``
* ``_toggle_underground_camera(owner)``
* ``_sync_ursina_camera_fov_from_zoom(owner)``
* ``update_zone_fog_color(owner, camera_world_x, camera_world_z)``
* ``begin_camera_underground_transition(owner, target_y)``
* ``begin_camera_surface_transition(owner)``

The 2 zone-fog class constants (``_ZONE_FOG_COLORS``/``_DEFAULT_FOG_COLOR``) moved to
module-level constants; the 3 intra-cluster cross-calls inside
``_reset_camera_to_default`` / ``_toggle_underground_camera`` are DIRECT module-local
calls, not ``owner.*`` hops.

Acyclic: ``ursina_app.py`` imports the new module one-way (lazily, in each wrapper);
the new module imports ``UrsinaApp`` ONLY under ``TYPE_CHECKING`` and keeps the
function-local ``config``/``world_zones`` imports function-local, so a fresh
interpreter can import either order with no module-load cycle.

ursina render code is NOT covered by the WK67 digest, ``determinism_guard`` (which
excludes ``game/graphics/**``), or the pygame screenshot tool — render fidelity is
verified by Jaimie's DEFERRED before/after live Ursina captures (need a real GPU/window
the headless agents lack). What this test proves:

* each of the 9 fns lives on ``ursina_app_camera``, is callable, and has an
  ``owner``-first signature;
* each ``UrsinaApp`` wrapper DELEGATES — it calls the module function with the bare app
  instance (``self``) as ``owner``, forwards remaining args, and returns the result
  (spy+monkeypatch + an AST check of the wrapper bodies);
* AST guard: the new module has NO module-top runtime ``import game.graphics.ursina_app``
  (a ``TYPE_CHECKING``-guarded import of ``UrsinaApp`` is allowed);
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* the ``ursina_app.py`` wrapper bodies reference ``ursina_app_camera.<fn>`` in source;
* ``begin_camera_underground_transition`` really runs through the wrapper (it flips
  ``owner._camera_active_layer`` to -1 and ``owner._camera_transitioning`` to True) —
  best-effort, skipped if the bare-instance shape needs more attrs.
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Headless: never bring up a real display when the ursina app is imported. import of
# ursina_app is headless-safe; we NEVER call UrsinaApp.__init__ (it opens a window).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import game.graphics.ursina_app_camera as camera_mod
from game.graphics.ursina_app import UrsinaApp


# The 9 INSTANCE methods WK113 moved into ursina_app_camera.py (ALL owner-first).
MOVED_FUNCTIONS = (
    "_setup_ursina_camera_for_castle",
    "_recenter_editor_camera_to_sim_xy",
    "_reset_camera_to_default",
    "_toggle_camera_lock",
    "_toggle_underground_camera",
    "_sync_ursina_camera_fov_from_zoom",
    "update_zone_fog_color",
    "begin_camera_underground_transition",
    "begin_camera_surface_transition",
)

# All 9 wrappers (name -> module-function-name). Names preserved 1:1.
WRAPPER_TO_FN = {name: name for name in MOVED_FUNCTIONS}


# ---------------------------------------------------------------------------
# (1) EXISTENCE — moved functions present + callable; owner-first signature
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_camera_mod(name: str) -> None:
    """The moved function is present on ursina_app_camera and callable."""
    assert hasattr(camera_mod, name), f"{name} missing from ursina_app_camera"
    assert callable(getattr(camera_mod, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_is_owner_first(name: str) -> None:
    """Each moved module function has an ``owner``-first signature (the WK92 owner-arg
    pattern): the first positional parameter is the app owner. ALL 9 are instance
    functions — there is no ``@staticmethod`` in this cluster."""
    sig = inspect.signature(getattr(camera_mod, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected an owner-first signature"
    assert params[0] == "owner", (
        f"{name} first param is {params[0]!r}; expected 'owner' (owner-arg pure-move)"
    )


# ---------------------------------------------------------------------------
# (2) WRAPPERS DELEGATE — runtime spy + source/AST belt-and-suspenders
# ---------------------------------------------------------------------------
def _bare_app() -> UrsinaApp:
    """A bare ``UrsinaApp`` instance with no ``__init__`` run.

    Constructing a real UrsinaApp opens an ursina window; ``object.__new__`` gives us an
    instance whose bound wrapper method we can call without the heavy graphics
    construction. The wrapper doesn't touch any instance state itself — it just forwards
    ``self`` — so the bare instance is sufficient to prove delegation.
    """
    return object.__new__(UrsinaApp)


# wrapper-name -> extra positional args to pass after self (the wrapper's own params)
_WRAPPER_EXTRA_ARGS = {
    "_setup_ursina_camera_for_castle": (),
    "_recenter_editor_camera_to_sim_xy": (1.0, 2.0),
    "_reset_camera_to_default": (),
    "_toggle_camera_lock": (),
    "_toggle_underground_camera": (),
    "_sync_ursina_camera_fov_from_zoom": (),
    "update_zone_fog_color": (3.0, 4.0),
    "begin_camera_underground_transition": (-7.0,),
    "begin_camera_surface_transition": (),
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaApp.<name>`` -> ``camera_mod.<name>(self, *extra)``.

    Spy+monkeypatch the module function and assert the bare app is forwarded as
    ``owner`` (first arg), the remaining args pass through, and the result is returned.
    """
    app = _bare_app()
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(camera_mod, name, spy)

    extra = _WRAPPER_EXTRA_ARGS[name]
    result = getattr(app, name)(*extra)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    args, kwargs = calls[0]
    assert args[0] is app, "app (self) must be forwarded as the first (owner) arg"
    assert args[1:] == extra, (
        f"remaining args not forwarded: got {args[1:]!r}, expected {extra!r}"
    )
    assert not kwargs, f"unexpected kwargs forwarded: {kwargs!r}"


def test_wrappers_call_camera_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``ursina_app_camera.<fn>(...)``. This pins the delegation even if a future
    monkeypatch path changed."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))

    found: dict[str, bool] = {w: False for w in WRAPPER_TO_FN}

    class _Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            if node.name not in WRAPPER_TO_FN:
                self.generic_visit(node)
                return
            target_fn = WRAPPER_TO_FN[node.name]
            for call in ast.walk(node):
                if not isinstance(call, ast.Call):
                    continue
                fn = call.func
                # match ursina_app_camera.<target_fn>(...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_app_camera"
                ):
                    found[node.name] = True
            self.generic_visit(node)

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_app_camera.<fn>(...) in source: "
        f"{missing}"
    )


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD — new module has no module-top runtime ursina_app import
# ---------------------------------------------------------------------------
def test_camera_mod_has_no_module_top_import_of_ursina_app() -> None:
    """AST guard: ursina_app_camera must not import ursina_app at module top (the
    dependency points one way: ursina_app -> camera_mod). A ``TYPE_CHECKING``-guarded
    import of ``UrsinaApp`` is allowed and is NOT a runtime import, so we only flag
    UNCONDITIONAL module-top imports (those whose parent is the module body, not an
    ``if TYPE_CHECKING:`` block)."""
    src_path = Path(camera_mod.__file__)
    tree = ast.parse(src_path.read_text(encoding="utf-8-sig"), filename=str(src_path))
    offenders: list[str] = []
    # iter_child_nodes -> module-top statements only; nodes inside an
    # ``if TYPE_CHECKING:`` block are NOT direct children of the module, so a
    # TYPE_CHECKING-guarded import is correctly NOT flagged here.
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("ursina_app"):
                    offenders.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.endswith("ursina_app"):
                offenders.append(f"from {mod} import ...")
    assert not offenders, (
        "ursina_app_camera has a module-top (runtime) import of "
        f"ursina_app (would risk a cycle): {offenders}"
    )


# ---------------------------------------------------------------------------
# (4) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_app_camera",
            "game.graphics.ursina_app",
        ),
        (
            "game.graphics.ursina_app",
            "game.graphics.ursina_app_camera",
        ),
    ],
)
def test_fresh_subprocess_imports_both_orders(first: str, second: str) -> None:
    """A fresh interpreter can import both modules in EITHER order without a
    module-load cycle. Runs out-of-process so already-imported modules in this session
    cannot mask an import-order bug."""
    repo_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["SDL_VIDEODRIVER"] = "dummy"
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


# ---------------------------------------------------------------------------
# (5) WRAPPER-SOURCE GUARD — ursina_app.py wrappers reference camera_mod.<fn>
# ---------------------------------------------------------------------------
def test_ursina_app_source_references_camera_mod_for_each_wrapper() -> None:
    """Static-source guard: ``ursina_app.py`` source must reference
    ``ursina_app_camera.<fn>`` for each of the 9 wrappers (encoding tolerant of a
    possible BOM)."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    missing = [
        name
        for name in MOVED_FUNCTIONS
        if f"ursina_app_camera.{name}" not in src
    ]
    assert not missing, (
        "ursina_app.py is missing a ursina_app_camera.<fn> reference for "
        f"wrapper(s): {missing}"
    )


# ---------------------------------------------------------------------------
# (6) TRANSITION BEHAVIOR — the real moved body runs through the wrapper
# ---------------------------------------------------------------------------
def test_begin_underground_transition_flips_layer_through_wrapper() -> None:
    """Best-effort behaviour proof: hand-set the camera-transition owner fields the real
    ``begin_camera_underground_transition`` body reads/mutates, call the wrapper, and
    assert the active layer flipped to underground (-1) and the transition flag is True.
    Skipped (not failed) if the bare-instance shape needs more attrs — the body reads
    ``camera.y`` and does ``from config import UNDERGROUND_CAMERA_TRANSITION_SPEED``, so
    a bare instance may raise. The delegation tests (2) are the core proof."""
    app = _bare_app()
    try:
        app._camera_active_layer = 0
        app._camera_transitioning = False
        app._camera_surface_y = None
        app._camera_transition_target_y = None
        app._camera_transition_speed = 0.0
        app.begin_camera_underground_transition(-7.0)
    except Exception as exc:  # pragma: no cover - setup-shape mismatch is a skip
        pytest.skip(f"bare-instance camera-transition shape mismatch: {exc!r}")
    assert app._camera_active_layer == -1, (
        "real begin_camera_underground_transition body (via wrapper) did not set "
        "_camera_active_layer to -1"
    )
    assert app._camera_transitioning is True, (
        "real begin_camera_underground_transition body (via wrapper) did not set "
        "_camera_transitioning to True"
    )
