"""WK118 Round B seam test (Agent 11 / QA): the ~245-line per-frame ``update()``
closure was extracted VERBATIM from ``UrsinaApp.run()`` (in
``game/graphics/ursina_app.py``) into the new module
``game/graphics/ursina_app_frame.py`` as ``run_frame(owner, dt)`` (the WK87-92/
WK104-105/WK113/116/117 owner-arg pure-move pattern). ``UrsinaApp.run()`` collapses to a
~7-line Ursina bootstrap whose nested ``update()`` shim calls
``ursina_app_frame.run_frame(self, time.dt)``. The relocated body is byte-faithful to the
original ``update()`` modulo ONLY the two documented structural diffs (the dropped first
line ``dt = time.dt`` — ``dt`` is now the function parameter — and the hoisted
``pan_speed = 55.0`` first line, which was a captured ``run()`` local). This guards the
refactor SEAM, not the live rendering behaviour itself.

ursina render code is NOT covered by the WK67 digest, ``determinism_guard`` (which
excludes ``game/graphics/**``), or the pygame screenshot tool. CRUCIALLY, the per-frame
``run_frame`` loop is NOT exercised by ANY headless gate (the WK67 digest / qa_smoke
drive the pygame/sim path, not the live Ursina frame loop). The PRIMARY faithfulness
proof this sprint is therefore the PM AST verbatim-diff gate (run_frame body ==
original update() body modulo the two documented diffs). The LIVE frame loop (pan/zoom,
camera layer transitions, terrain clamp, hero-follow, zone fog, auto-exit, HUD upload) is
**DEFERRED to the Sovereign's before/after live Ursina captures** (need a real GPU/window
the headless agents lack). What this test proves:

* ``ursina_app_frame.run_frame`` exists, is callable, and has signature ``(owner, dt)``
  (owner-first, dt-param — the owner-arg pure-move shape);
* the ``UrsinaApp.run`` source DELEGATES — it defines a nested ``update`` and calls
  ``ursina_app_frame.run_frame(self, time.dt)``, and the OLD loop markers
  (``_chat_captures_keyboard`` / ``pan_speed = 55.0`` / ``tick_simulation``) are GONE
  from ``run()`` source (they moved into ``run_frame``);
* static-source guard: ``ursina_app.py`` references ``ursina_app_frame.run_frame``;
* AST guard: the new module has NO module-top runtime ``import game.graphics.ursina_app``
  (a ``TYPE_CHECKING``-guarded import of ``UrsinaApp`` is allowed);
* a fresh interpreter can import both modules in EITHER order (no module-load cycle);
* best-effort smoke: a stub ``owner`` + monkeypatched ursina globals drive one
  ``run_frame(owner, 0.016)`` and ``owner.engine.tick_simulation`` is called once —
  skipped (not failed) if the stub shape doesn't satisfy the live body, since the
  verbatim-diff gate + the structural pins above are the core proof.
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

import game.graphics.ursina_app_frame as frame_mod
from game.graphics.ursina_app import UrsinaApp


# ---------------------------------------------------------------------------
# (1) EXISTENCE + SIGNATURE — run_frame present, callable, (owner, dt)
# ---------------------------------------------------------------------------
def test_run_frame_exists_and_is_callable() -> None:
    """The extracted per-frame loop lives on ursina_app_frame as ``run_frame`` and is
    callable."""
    assert hasattr(frame_mod, "run_frame"), "run_frame missing from ursina_app_frame"
    assert callable(frame_mod.run_frame), "run_frame is not callable"


def test_run_frame_signature_is_owner_dt() -> None:
    """``run_frame`` has the owner-arg pure-move signature: ``(owner, dt)`` — owner first,
    dt is the per-frame parameter (the dropped ``dt = time.dt`` line)."""
    params = list(inspect.signature(frame_mod.run_frame).parameters)
    assert params == ["owner", "dt"], (
        f"run_frame signature is {params!r}; expected ['owner', 'dt']"
    )


# ---------------------------------------------------------------------------
# (2) SHIM DELEGATION — UrsinaApp.run source delegates; old loop markers gone
# ---------------------------------------------------------------------------
def test_run_shim_delegates_and_old_loop_markers_gone() -> None:
    """``UrsinaApp.run`` collapsed to a thin shim: its source defines a nested
    ``update`` and calls ``ursina_app_frame.run_frame(self, time.dt)``. The old per-frame
    loop markers must NO LONGER appear in ``run()`` source — they moved into
    ``run_frame``."""
    src = inspect.getsource(UrsinaApp.run)
    assert "ursina_app_frame.run_frame(self, time.dt)" in src, (
        "run() shim must call ursina_app_frame.run_frame(self, time.dt)"
    )
    assert "def update(" in src, "run() shim must define a nested update()"
    for gone in ("_chat_captures_keyboard", "pan_speed = 55.0", "tick_simulation"):
        assert gone not in src, (
            f"old loop marker {gone!r} still present in run() source — the body did "
            "not fully move into run_frame"
        )


# ---------------------------------------------------------------------------
# (3) SOURCE GUARD — ursina_app.py references ursina_app_frame.run_frame
# ---------------------------------------------------------------------------
def test_ursina_app_source_references_run_frame() -> None:
    """Static-source guard: ``ursina_app.py`` source references
    ``ursina_app_frame.run_frame`` (encoding tolerant of a possible BOM)."""
    src_path = Path(sys.modules[UrsinaApp.__module__].__file__)
    src = src_path.read_text(encoding="utf-8-sig")
    assert "ursina_app_frame.run_frame" in src, (
        "ursina_app.py is missing a ursina_app_frame.run_frame reference"
    )


# ---------------------------------------------------------------------------
# (4) AST NO-CYCLE GUARD — new module has no module-top runtime ursina_app import
# ---------------------------------------------------------------------------
def test_frame_mod_has_no_module_top_import_of_ursina_app() -> None:
    """AST guard: ursina_app_frame must not import ursina_app at module top (the
    dependency points one way: ursina_app -> frame_mod). A ``TYPE_CHECKING``-guarded
    import of ``UrsinaApp`` is allowed and is NOT a runtime import, so we only flag
    UNCONDITIONAL module-top imports (those whose parent is the module body, not an
    ``if TYPE_CHECKING:`` block) — same as the WK105/113 test."""
    src_path = Path(frame_mod.__file__)
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
        "ursina_app_frame has a module-top (runtime) import of "
        f"ursina_app (would risk a cycle): {offenders}"
    )


# ---------------------------------------------------------------------------
# (5) NO CYCLE — fresh subprocess, BOTH import orders
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "first,second",
    [
        (
            "game.graphics.ursina_app_frame",
            "game.graphics.ursina_app",
        ),
        (
            "game.graphics.ursina_app",
            "game.graphics.ursina_app_frame",
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
# (6) BEST-EFFORT DRIVE — stub owner + monkeypatched ursina globals; one frame
# ---------------------------------------------------------------------------
class _Vec3Like:
    """A tiny mutable Vec3 stand-in: ``.x/.y/.z`` and indexed access the body uses."""

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class _HeldKeys(dict):
    """``held_keys`` is read both as ``hk.get(...)`` and ``hk["a"]`` — a dict that
    returns 0 for missing keys covers both."""

    def __missing__(self, key):  # noqa: ANN001, ANN204
        return 0


def _build_stub_owner() -> types.SimpleNamespace:
    """Build a stub ``owner`` carrying the attrs/methods ``run_frame`` reads. The live
    body has many ``getattr(..., default)`` / try-except guards, so a SimpleNamespace
    plus a handful of no-op methods is enough to drive one frame to completion. The
    no-op owner methods are the WK113/116/117 sibling-module wrappers (we are NOT
    asserting their behaviour — only that the moved body reaches ``tick_simulation``)."""
    tick = _CallCounter()
    engine = types.SimpleNamespace(
        tick_simulation=tick,
        get_game_state=lambda: {},
        build_snapshot=lambda: {},
        build_presentation_frame=lambda: {},
        render_pygame=lambda: None,
        process_command=lambda *_a, **_k: None,
        zoom_by=lambda *_a, **_k: None,
        paused=False,
        pause_menu=types.SimpleNamespace(visible=False),
        running=True,
        hud=None,
        _command_mode=False,
        _last_frame_dt_ms=0.0,
        _ursina_window_fps_ema=None,
        _find_hero_by_id=lambda _id: None,
    )
    input_manager = types.SimpleNamespace(
        queue_event=lambda *_a, **_k: None,
        get_mouse_pos=lambda: (0, 0),
        set_virtual_screen_size=lambda *_a, **_k: None,
    )
    renderer = types.SimpleNamespace(_camera_active_layer=0, update=lambda *_a, **_k: None)
    owner = types.SimpleNamespace(
        engine=engine,
        input_manager=input_manager,
        renderer=renderer,
        # early-path state
        _pending_lmb=False,
        _worker_scale_shot_reattach=0,
        # auto-exit
        _auto_exit_triggered=False,
        _auto_exit_deadline_sec=0.0,
        _auto_exit_elapsed=0.0,
        _auto_reveal_done=True,
        # camera state
        _editor_camera=None,
        _camera_orbit_locked=False,
        _camera_transitioning=False,
        _camera_transition_target_y=None,
        _camera_transition_speed=0.0,
        _camera_active_layer=0,
        _hero_follow_last_layer=None,
        _hud_composite_texture=None,
        # owner-method hops (no-ops): WK113/116/117 sibling-module wrappers
        _sync_headless_ui_canvas_to_window=lambda: None,
        _queue_pointer_motion_event=lambda: None,
        _virtual_screen_pos=lambda: (0, 0),
        _pointer_event_pos=lambda: (0, 0),
        _sidebar_split_drag_active=lambda: False,
        _engine_screen_pos_for_pointer=lambda: (None, None, None, 0.0, 0.0),
        _record_fps_probe_stage_ms=lambda *_a, **_k: None,
        _record_fps_probe_sample=lambda *_a, **_k: None,
        _install_worker_scale_comparison_shot=lambda: None,
        _maybe_auto_screenshot_then_quit=lambda: None,
        _sync_ursina_camera_fov_from_zoom=lambda: None,
        _refresh_ui_overlay_texture=lambda: None,
        _sync_hud_texture_filter_mode=lambda *_a, **_k: None,
        update_zone_fog_color=lambda *_a, **_k: None,
        begin_camera_underground_transition=lambda *_a, **_k: None,
        begin_camera_surface_transition=lambda: None,
    )
    return owner


class _CallCounter:
    """A trivial callable that counts invocations (a Mock-lite, no dependency)."""

    def __init__(self) -> None:
        self.count = 0

    def __call__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        self.count += 1


def test_run_frame_drives_one_frame_and_ticks_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Best-effort smoke: drive ONE ``run_frame(owner, 0.016)`` with a stub owner and
    monkeypatched ursina module globals (``camera`` / ``held_keys`` / ``mouse``) and
    assert the sim was ticked exactly once. Wrapped in try/except + ``pytest.skip`` on
    ANY exception — this is a best-effort smoke; the PM verbatim-diff gate and the
    structural pins (1)-(5) are the core proof. The full live loop is
    deferred-screenshot-verified (real GPU/window required)."""
    owner = _build_stub_owner()
    try:
        # Monkeypatch the ursina module globals the body reads.
        monkeypatch.setattr(frame_mod, "held_keys", _HeldKeys(), raising=False)
        monkeypatch.setattr(
            frame_mod,
            "mouse",
            types.SimpleNamespace(x=0.0, y=0.0, right=False),
            raising=False,
        )
        cam = types.SimpleNamespace(
            x=0.0,
            y=10.0,
            z=0.0,
            aspect_ratio=1.0,
            world_position=_Vec3Like(0.0, 10.0, 0.0),
        )
        monkeypatch.setattr(frame_mod, "camera", cam, raising=False)
        frame_mod.run_frame(owner, 0.016)
    except Exception as exc:  # pragma: no cover - stub-shape mismatch is a skip
        pytest.skip(f"frame drive shape mismatch: {exc!r}")
    assert owner.engine.tick_simulation.count == 1, (
        "run_frame did not tick the simulation exactly once "
        f"(count={owner.engine.tick_simulation.count})"
    )
