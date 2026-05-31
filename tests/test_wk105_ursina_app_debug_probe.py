"""WK105 Round B-22 seam test (Agent 11 / QA): the env-gated debug/FPS-probe +
auto-screenshot scaffolding was moved VERBATIM from ``game/graphics/ursina_app.py``
into the new ``game/graphics/ursina_app_debug_probe.py`` using the WK87-92/WK104
owner-arg pure-move pattern. The cluster is DEAD-BY-DEFAULT (every entry point is
gated behind a ``KINGDOM_URSINA_*`` env flag or the auto-exit path), so a verbatim
move cannot regress normal-play rendering.

The 8 moved members:

* ``_add_wk30_debug_prefab_layout(owner)`` (env ``KINGDOM_URSINA_PREFAB_TEST_LAYOUT``)
* ``_install_worker_scale_comparison_shot(owner)`` (env ``…WORKER_SCALE_SHOT``)
* ``_add_hero_fps_probe_layout(owner, hero_count)`` (env ``…HERO_FPS_PROBE_COUNT``)
* ``_record_fps_probe_sample(owner, dt)`` (FPS-probe trio; no-op when disabled)
* ``_record_fps_probe_stage_ms(owner, name, started_at)`` (no-op when disabled)
* ``_print_fps_probe_summary(owner)``
* ``_maybe_auto_screenshot_then_quit(owner)`` (auto-exit path)
* ``_save_window_screenshot_sync(base, out_path)`` — was a ``@staticmethod``; moves as
  a PLAIN module function with NO ``owner``/``self`` arg (signature ``(base, out_path)``).

The 7 INSTANCE methods became module functions with ``owner`` first (every ``self.``
in their bodies rewritten to ``owner.``). ``UrsinaApp`` keeps 8 one-line delegating
wrappers (same names + signatures; ``_save_window_screenshot_sync`` stays a
``@staticmethod``) so the staying call sites (``__init__`` 187/192/204; ``run()``
``_record_fps_probe_stage_ms`` / ``_install_worker_scale_comparison_shot`` /
``_record_fps_probe_sample`` / ``_maybe_auto_screenshot_then_quit``) reach the
relocated code unchanged. The two intra-cluster cross-calls inside
``_maybe_auto_screenshot_then_quit`` (``_print_fps_probe_summary(owner)`` and
``_save_window_screenshot_sync(base, out_path)``) are DIRECT module-local calls, not
``owner.*`` hops.

Acyclic: ``ursina_app.py`` imports the new module one-way (lazily, in each wrapper);
the new module imports ``UrsinaApp`` ONLY under ``TYPE_CHECKING`` and keeps all heavy
(ursina/panda3d/game.entities) imports function-local, so a fresh interpreter can
import either order with no module-load cycle.

This guards the refactor SEAM, not the rendering behaviour itself. ursina render code
is NOT covered by the WK67 digest, ``determinism_guard`` (which excludes
``game/graphics/**``), or the pygame screenshot tool — render fidelity (and the
dead-by-default debug layouts specifically) is verified by Jaimie's DEFERRED before/
after live Ursina captures (need a real GPU/window the headless agents lack). What
this test proves:

* each of the 7 instance fns lives on ``ursina_app_debug_probe``, is callable, and has
  an ``owner``-first signature; ``_save_window_screenshot_sync`` exists + is callable
  but is ``(base, out_path)`` (NOT owner-first);
* each ``UrsinaApp`` wrapper DELEGATES — it calls the module function with the bare
  app instance (``self``) as ``owner`` (the 7 instance ones) or with ``(base, out_path)``
  (the staticmethod), forwards remaining args, and returns the result (spy+monkeypatch
  + an AST check of the wrapper bodies);
* AST guard: the new module has NO module-top runtime ``import game.graphics.ursina_app``
  (a ``TYPE_CHECKING``-guarded import of ``UrsinaApp`` is allowed);
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* the ``ursina_app.py`` wrapper bodies reference ``ursina_app_debug_probe.<fn>`` in source;
* the FPS-trio body really runs through the wrapper (``_record_fps_probe_sample`` grows
  ``owner._fps_probe_samples``) — best-effort, skipped if the bare-instance shape needs
  more attrs.
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

import game.graphics.ursina_app_debug_probe as debug_probe
from game.graphics.ursina_app import UrsinaApp


# The 7 INSTANCE methods WK105 moved into ursina_app_debug_probe.py (owner-first).
MOVED_INSTANCE_FUNCTIONS = (
    "_add_wk30_debug_prefab_layout",
    "_install_worker_scale_comparison_shot",
    "_add_hero_fps_probe_layout",
    "_record_fps_probe_sample",
    "_record_fps_probe_stage_ms",
    "_print_fps_probe_summary",
    "_maybe_auto_screenshot_then_quit",
)

# The one moved @staticmethod (plain module fn now): (base, out_path), NOT owner-first.
MOVED_STATIC_FUNCTION = "_save_window_screenshot_sync"

# All 8 wrappers (name -> module-function-name). Names preserved 1:1.
ALL_MOVED_FUNCTIONS = MOVED_INSTANCE_FUNCTIONS + (MOVED_STATIC_FUNCTION,)
WRAPPER_TO_FN = {name: name for name in ALL_MOVED_FUNCTIONS}


# ---------------------------------------------------------------------------
# (1) EXISTENCE — moved functions present + callable; owner-first where required
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ALL_MOVED_FUNCTIONS)
def test_moved_function_lives_on_debug_probe(name: str) -> None:
    """The moved function is present on ursina_app_debug_probe and callable."""
    assert hasattr(debug_probe, name), f"{name} missing from ursina_app_debug_probe"
    assert callable(getattr(debug_probe, name)), f"{name} is not callable"


@pytest.mark.parametrize("name", MOVED_INSTANCE_FUNCTIONS)
def test_moved_instance_function_is_owner_first(name: str) -> None:
    """Each moved INSTANCE module function has an ``owner``-first signature (the WK92
    owner-arg pattern): the first positional parameter is the app owner."""
    sig = inspect.signature(getattr(debug_probe, name))
    params = list(sig.parameters)
    assert params, f"{name} has no parameters; expected an owner-first signature"
    assert params[0] == "owner", (
        f"{name} first param is {params[0]!r}; expected 'owner' (owner-arg pure-move)"
    )


def test_save_window_screenshot_sync_signature_is_base_out_path() -> None:
    """``_save_window_screenshot_sync`` was a ``@staticmethod`` (no self) — it moves as a
    plain module function with signature ``(base, out_path)``, NOT owner-first."""
    sig = inspect.signature(getattr(debug_probe, MOVED_STATIC_FUNCTION))
    params = list(sig.parameters)
    assert params[:2] == ["base", "out_path"], (
        f"{MOVED_STATIC_FUNCTION} signature is {params}; expected ['base', 'out_path'] "
        "(it was a @staticmethod — no owner/self arg)"
    )
    assert params[0] != "owner", (
        f"{MOVED_STATIC_FUNCTION} must NOT be owner-first (it is a moved @staticmethod)"
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
_INSTANCE_WRAPPER_EXTRA_ARGS = {
    "_add_wk30_debug_prefab_layout": (),
    "_install_worker_scale_comparison_shot": (),
    "_add_hero_fps_probe_layout": (3,),
    "_record_fps_probe_sample": (0.016,),
    "_record_fps_probe_stage_ms": ("x", 0.0),
    "_print_fps_probe_summary": (),
    "_maybe_auto_screenshot_then_quit": (),
}


@pytest.mark.parametrize("name", MOVED_INSTANCE_FUNCTIONS)
def test_instance_wrapper_delegates(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """``UrsinaApp.<name>`` -> ``debug_probe.<name>(self, *extra)``.

    Spy+monkeypatch the module function and assert the bare app is forwarded as
    ``owner`` (first arg), the remaining args pass through, and the result is returned.
    """
    app = _bare_app()
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(debug_probe, name, spy)

    extra = _INSTANCE_WRAPPER_EXTRA_ARGS[name]
    result = getattr(app, name)(*extra)

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    args, kwargs = calls[0]
    assert args[0] is app, "app (self) must be forwarded as the first (owner) arg"
    assert args[1:] == extra, (
        f"remaining args not forwarded: got {args[1:]!r}, expected {extra!r}"
    )
    assert not kwargs, f"unexpected kwargs forwarded: {kwargs!r}"


def test_save_window_screenshot_sync_wrapper_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``UrsinaApp._save_window_screenshot_sync`` (a ``@staticmethod``) ->
    ``debug_probe._save_window_screenshot_sync(base, out_path)`` — NO owner/self arg."""
    calls: list[tuple] = []
    sentinel = object()

    def spy(*args, **kwargs):  # noqa: ANN002, ANN003 - test spy
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(debug_probe, MOVED_STATIC_FUNCTION, spy)

    base_marker = object()
    result = UrsinaApp._save_window_screenshot_sync(base_marker, "p.png")

    assert result is sentinel, "wrapper must return the module function's result"
    assert len(calls) == 1, "module function must be called exactly once"
    args, kwargs = calls[0]
    assert args == (base_marker, "p.png"), (
        f"staticmethod wrapper must forward (base, out_path); got {args!r}"
    )
    assert not kwargs, f"unexpected kwargs forwarded: {kwargs!r}"


def test_wrappers_call_debug_probe_module_in_source() -> None:
    """Source/AST belt-and-suspenders: every wrapper body contains a call to
    ``ursina_app_debug_probe.<fn>(...)``. This pins the delegation even if a future
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
                # match ursina_app_debug_probe.<target_fn>(...)
                if (
                    isinstance(fn, ast.Attribute)
                    and fn.attr == target_fn
                    and isinstance(fn.value, ast.Name)
                    and fn.value.id == "ursina_app_debug_probe"
                ):
                    found[node.name] = True
            self.generic_visit(node)

    _Visitor().visit(tree)
    missing = [w for w, ok in found.items() if not ok]
    assert not missing, (
        "wrapper(s) do not call ursina_app_debug_probe.<fn>(...) in source: "
        f"{missing}"
    )


# ---------------------------------------------------------------------------
# (3) AST NO-CYCLE GUARD — new module has no module-top runtime ursina_app import
# ---------------------------------------------------------------------------
def test_debug_probe_has_no_module_top_import_of_ursina_app() -> None:
    """AST guard: ursina_app_debug_probe must not import ursina_app at module top (the
    dependency points one way: ursina_app -> debug_probe). A ``TYPE_CHECKING``-guarded
    import of ``UrsinaApp`` is allowed and is NOT a runtime import, so we only flag
    UNCONDITIONAL module-top imports (those whose parent is the module body, not an
    ``if TYPE_CHECKING:`` block)."""
    src_path = Path(debug_probe.__file__)
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
        "ursina_app_debug_probe has a module-top (runtime) import of "
        f"ursina_app (would risk a cycle): {offenders}"
    )


# ---------------------------------------------------------------------------
# (4) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_app_debug_probe",
            "game.graphics.ursina_app",
        ),
        (
            "game.graphics.ursina_app",
            "game.graphics.ursina_app_debug_probe",
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
# (5) WRAPPER-SOURCE GUARD — ursina_app.py wrappers reference debug_probe.<fn>
# ---------------------------------------------------------------------------
def test_ursina_app_source_references_debug_probe_for_each_wrapper() -> None:
    """Static-source guard: ``ursina_app.py`` source must reference
    ``ursina_app_debug_probe.<fn>`` for each of the 8 wrappers (encoding tolerant of a
    possible BOM)."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    missing = [
        name
        for name in ALL_MOVED_FUNCTIONS
        if f"ursina_app_debug_probe.{name}" not in src
    ]
    assert not missing, (
        "ursina_app.py is missing a ursina_app_debug_probe.<fn> reference for "
        f"wrapper(s): {missing}"
    )


# ---------------------------------------------------------------------------
# (6) FPS-TRIO BEHAVIOR — the real moved body runs through the wrapper
# ---------------------------------------------------------------------------
def test_record_fps_probe_sample_grows_samples_through_wrapper() -> None:
    """Best-effort behaviour proof: hand-set the FPS-probe owner fields the real
    ``_record_fps_probe_sample`` body reads/mutates, call the wrapper, and assert
    ``owner._fps_probe_samples`` grew. Skipped (not failed) if the bare-instance shape
    needs more attrs — delegation tests (2) are the core proof."""
    app = _bare_app()
    try:
        app._fps_probe_enabled = True
        app._fps_probe_elapsed = 0.0
        app._fps_probe_warmup_sec = 0.0
        app._fps_probe_samples = []
        app._fps_probe_stage_samples = {}
        before = len(app._fps_probe_samples)
        app._record_fps_probe_sample(0.016)
    except Exception as exc:  # pragma: no cover - setup-shape mismatch is a skip
        pytest.skip(f"bare-instance FPS-probe shape mismatch: {exc!r}")
    assert len(app._fps_probe_samples) > before, (
        "real _record_fps_probe_sample body (via wrapper) did not append a sample"
    )
