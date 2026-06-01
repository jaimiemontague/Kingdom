"""WK116 Round B seam test (Agent 11 / QA): the input/pointer cluster was moved
VERBATIM from ``game/graphics/ursina_app.py`` into the new
``game/graphics/ursina_app_input.py`` using the WK105/WK113 owner-arg pure-move
pattern. ``UrsinaApp`` keeps 9 one-line delegating wrappers (exact original names +
signatures); the relocated bodies are byte-faithful (only ``self``->``owner`` and the
intra-cluster cross-calls changed). This guards the refactor SEAM, not the input
behaviour itself.

The 9 moved members (ALL instance methods → ALL owner-first; there is NO
``@staticmethod`` in this cluster):

* ``_is_chat_active(owner)``
* ``_install_ursina_input_hook(owner)``
* ``_pixel_hits_opaque_ui(owner, px, py)``
* ``_engine_screen_pos_for_pointer(owner)``
* ``_sidebar_split_drag_active(owner)``
* ``_virtual_screen_pos(owner)``
* ``_pointer_event_pos(owner)``
* ``_queue_pointer_motion_event(owner)``
* ``_handle_ursina_input(owner, key)``

The intra-cluster cross-calls inside the moved bodies are DIRECT module-local calls
(e.g. ``_pixel_hits_opaque_ui(owner, px, py)``), not ``owner.*`` hops; the cross-cluster
camera calls (``owner._reset_camera_to_default`` etc., which live in
``ursina_app_camera`` and stay as wrappers on ``UrsinaApp``) remain ``owner.*`` hops.

Acyclic: ``ursina_app.py`` imports the new module one-way (lazily, in each wrapper);
the new module imports ``UrsinaApp`` ONLY under ``TYPE_CHECKING`` and keeps the
function-local ``__main__`` / ``ursina.application`` / ``os`` imports function-local, so
a fresh interpreter can import either order with no module-load cycle.

ursina render/input code is NOT covered by the WK67 digest, ``determinism_guard`` (which
excludes ``game/graphics/**``), or the pygame screenshot tool — input fidelity is
verified by Jaimie's DEFERRED before/after live Ursina captures (need a real GPU/window
the headless agents lack). What this test proves:

* each of the 9 fns lives on ``ursina_app_input``, is callable, and has an
  ``owner``-first signature;
* each ``UrsinaApp`` wrapper DELEGATES — it calls the module function with the bare app
  instance (``self``) as ``owner``, forwards remaining args, and returns the result
  (spy+monkeypatch + an AST check of the wrapper bodies);
* AST guard: the new module has NO module-top runtime ``import game.graphics.ursina_app``
  (a ``TYPE_CHECKING``-guarded import of ``UrsinaApp`` is allowed);
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* the ``ursina_app.py`` wrapper bodies reference ``ursina_app_input.<fn>`` in source;
* ``_sidebar_split_drag_active`` really runs through the wrapper (it reads
  ``owner.engine.hud._left_split_drag_kind`` and returns a bool) — best-effort, skipped
  if the bare-instance shape needs more attrs. The delegation tests (2) are the core
  proof.
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

# Headless: never bring up a real display when the ursina app is imported. import of
# ursina_app is headless-safe; we NEVER call UrsinaApp.__init__ (it opens a window).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import game.graphics.ursina_app_input as input_mod
from game.graphics.ursina_app import UrsinaApp


# The 9 INSTANCE methods WK116 moved into ursina_app_input.py (ALL owner-first).
MOVED_FUNCTIONS = (
    "_is_chat_active",
    "_install_ursina_input_hook",
    "_pixel_hits_opaque_ui",
    "_engine_screen_pos_for_pointer",
    "_sidebar_split_drag_active",
    "_virtual_screen_pos",
    "_pointer_event_pos",
    "_queue_pointer_motion_event",
    "_handle_ursina_input",
)

# All 9 wrappers (name -> module-function-name). Names preserved 1:1.
WRAPPER_TO_FN = {name: name for name in MOVED_FUNCTIONS}


# ---------------------------------------------------------------------------
# (1) EXISTENCE — moved functions present + callable; owner-first signature
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_lives_on_input_mod(name: str) -> None:
    """The moved function is present on ursina_app_input and callable."""
    assert hasattr(input_mod, name), f"{name} missing from ursina_app_input"
    assert callable(getattr(input_mod, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_moved_function_is_owner_first(name: str) -> None:
    """Each moved module function has an ``owner``-first signature (the WK92 owner-arg
    pattern): the first positional parameter is the app owner. ALL 9 are instance
    functions — there is no ``@staticmethod`` in this cluster."""
    sig = inspect.signature(getattr(input_mod, name))
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
    "_is_chat_active": (),
    "_install_ursina_input_hook": (),
    "_pixel_hits_opaque_ui": (10, 10),
    "_engine_screen_pos_for_pointer": (),
    "_sidebar_split_drag_active": (),
    "_virtual_screen_pos": (),
    "_pointer_event_pos": (),
    "_queue_pointer_motion_event": (),
    "_handle_ursina_input": ("escape",),
}


@pytest.mark.parametrize("name", MOVED_FUNCTIONS)
def test_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaApp.<name>`` -> ``input_mod.<name>(self, *extra)``.

    Spy+monkeypatch the module function and assert the bare app is forwarded as
    ``owner`` (first arg), the remaining args pass through, and the result is returned.
    """
    app = _bare_app()
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(input_mod, name, spy)

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


def test_wrappers_call_input_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``ursina_app_input.<fn>(...)``. This pins the delegation even if a future
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
                # match ursina_app_input.<target_fn>(...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_app_input"
                ):
                    found[node.name] = True
            self.generic_visit(node)

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_app_input.<fn>(...) in source: "
        f"{missing}"
    )


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD — new module has no module-top runtime ursina_app import
# ---------------------------------------------------------------------------
def test_input_mod_has_no_module_top_import_of_ursina_app() -> None:
    """AST guard: ursina_app_input must not import ursina_app at module top (the
    dependency points one way: ursina_app -> input_mod). A ``TYPE_CHECKING``-guarded
    import of ``UrsinaApp`` is allowed and is NOT a runtime import, so we only flag
    UNCONDITIONAL module-top imports (those whose parent is the module body, not an
    ``if TYPE_CHECKING:`` block)."""
    src_path = Path(input_mod.__file__)
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
        "ursina_app_input has a module-top (runtime) import of "
        f"ursina_app (would risk a cycle): {offenders}"
    )


# ---------------------------------------------------------------------------
# (4) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_app_input",
            "game.graphics.ursina_app",
        ),
        (
            "game.graphics.ursina_app",
            "game.graphics.ursina_app_input",
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
# (5) WRAPPER-SOURCE GUARD — ursina_app.py wrappers reference input_mod.<fn>
# ---------------------------------------------------------------------------
def test_ursina_app_source_references_input_mod_for_each_wrapper() -> None:
    """Static-source guard: ``ursina_app.py`` source must reference
    ``ursina_app_input.<fn>`` for each of the 9 wrappers (encoding tolerant of a
    possible BOM)."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    missing = [
        name
        for name in MOVED_FUNCTIONS
        if f"ursina_app_input.{name}" not in src
    ]
    assert not missing, (
        "ursina_app.py is missing a ursina_app_input.<fn> reference for "
        f"wrapper(s): {missing}"
    )


# ---------------------------------------------------------------------------
# (6) SIDEBAR-SPLIT-DRAG BEHAVIOR — the real moved body runs through the wrapper
# ---------------------------------------------------------------------------
def test_sidebar_split_drag_active_returns_bool_through_wrapper() -> None:
    """Best-effort behaviour proof: hand-set the engine/hud owner fields the real
    ``_sidebar_split_drag_active`` body reads, call the wrapper, and assert it returns a
    bool (False when no split-drag is in progress). The body reads
    ``owner.engine.hud._left_split_drag_kind``; with that ``None`` it must return False.
    Skipped (not failed) if the bare-instance shape needs more attrs — the delegation
    tests (2) are the core proof."""
    app = _bare_app()
    try:
        app.engine = types.SimpleNamespace(
            hud=types.SimpleNamespace(_left_split_drag_kind=None)
        )
        result = app._sidebar_split_drag_active()
    except Exception as exc:  # pragma: no cover - setup-shape mismatch is a skip
        pytest.skip(f"bare-instance sidebar-split-drag shape mismatch: {exc!r}")
    assert isinstance(result, bool), (
        "real _sidebar_split_drag_active body (via wrapper) did not return a bool"
    )
    assert result is False, (
        "real _sidebar_split_drag_active body (via wrapper) should be False when "
        "_left_split_drag_kind is None"
    )
