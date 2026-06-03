#!/usr/bin/env python3
"""WK123 LIVE FPS soak harness — drives the REAL Ursina game with a heavy scenario for
~17 min unattended, logging FPS-over-time + periodic screenshots. Tools-only; edits no
game code. The scenario + first-frame hook are injected via a generated capture-patch
module that monkeypatches ``UrsinaApp.__init__`` (the same mechanism the WK67 combat
capture uses), so ``orig_init`` builds the world first and our hook runs after.

What the harness wires up (all via existing game knobs — nothing reinvented):
  - ``KINGDOM_URSINA_AUTO_EXIT_SEC = minutes*60``  → auto-quit at the soak deadline
    (ursina_app.py:247 / ursina_app_frame.py:131-139).
  - ``KINGDOM_FPS_SLOWLOG=1``                       → [frameavg]/[slowframe] lines every
    120 frames with stages tick/rend/hudR/hudU + live E=/B= (ursina_app_frame.py:298-325).
  - ``KINGDOM_URSINA_FPS_PROBE=1`` (+WARMUP)        → on-exit avg/min/p10/p50/p90 + per-stage
    (ursina_app_debug_probe.py:219).
  - ``KINGDOM_URSINA_AUTO_SCREENSHOT_PATH``         → sync screenshot at the auto-exit.

The first-frame hook (in the generated patch) then:
  (a) force-spawns the heavy scenario (>=24 heroes, ~100 buildings, 80 enemies) against
      ``UrsinaApp.engine`` via ``tools/wk123_scenario.build_heavy_scenario``;
  (b) LOCKS speed — fast: tb.set_time_multiplier(1.0) then no-ops the setter so an engine
      reset can't change it; normal: 0.5;
  (c) sets ``engine.zoom`` — out: config.ZOOM_MIN; normal: engine.default_zoom;
  (d) window — maximized: resize the Panda window to the desktop size (DEFAULT_BORDERLESS
      is already True); windowed: leave the default window;
  (e) installs a tick_simulation wrapper that (i) tops enemies back up to the cap every
      ~40 frames, (ii) every 15s wall (densifying to ~2s in minutes 15-17) appends a CSV
      row, and (iii) forces a sync screenshot at the 15/16/17-min marks.

CSV columns: wall_ts, fps_ema, dt_ms, tick, rend, hudR, hudU, E, B, scene_entities,
             heroes, alive_heroes.

Usage (the MAIN session — with a GPU — actually runs these; this file only builds + the
headless validation runs the spawn helpers, NOT the live GPU loop):

    python tools/wk123_fps_soak.py --zoom out    --speed fast   --window maximized --minutes 17
    python tools/wk123_fps_soak.py --zoom normal  --speed normal --window windowed  --minutes 17

Outputs:
    tmp/wk123/soak_<zoom>_<speed>_<window>.log   (full stdout/stderr tee)
    tmp/wk123/soak_<zoom>_<speed>_<window>.csv   (the periodic FPS rows)
    docs/screenshots/wk123_soak/<combo>_min{15,16,17}.png
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = PROJECT_ROOT / "tmp" / "wk123"
SHOT_DIR = PROJECT_ROOT / "docs" / "screenshots" / "wk123_soak"

# ---------------------------------------------------------------------------
# The generated capture patch (string). Loaded by the runner BEFORE main.py so
# its apply_patch() rebinds UrsinaApp.__init__ before the app is constructed.
# Placeholders {{...}} are .format()-substituted with the run config.
# ---------------------------------------------------------------------------
_PATCH_TEMPLATE = r'''"""WK123 GENERATED soak capture patch — do not edit by hand (tools/wk123_fps_soak.py)."""
from __future__ import annotations

import os
import time as _wall
import csv as _csv

import config

# Run config injected by the harness.
_ZOOM_MODE = {zoom_mode!r}     # "out" | "normal"
_SPEED_MODE = {speed_mode!r}   # "fast" | "normal"
_WINDOW_MODE = {window_mode!r} # "maximized" | "windowed"
_CSV_PATH = {csv_path!r}
_SHOT_PREFIX = {shot_prefix!r}  # docs/screenshots/wk123_soak/<combo>
_MINUTES = {minutes!r}

_CSV_COLS = [
    "wall_ts", "fps_ema", "dt_ms", "tick", "rend", "hudR", "hudU",
    "E", "B", "scene_entities", "heroes", "alive_heroes",
]


def _lock_speed():
    import game.sim.timebase as tb
    if _SPEED_MODE == "fast":
        tb.set_time_multiplier(1.0)
        tb.set_time_multiplier = lambda m: None  # pin past any engine reset
    else:  # normal
        tb.set_time_multiplier(0.5)


def _set_zoom(engine):
    try:
        if _ZOOM_MODE == "out":
            engine.zoom = float(config.ZOOM_MIN)
        else:  # normal
            engine.zoom = float(getattr(engine, "default_zoom", 1.0) or 1.0)
    except Exception as exc:
        print(f"[wk123-soak] zoom set failed: {{exc}}", flush=True)


def _maximize_window():
    if _WINDOW_MODE != "maximized":
        return
    try:
        from panda3d.core import WindowProperties
        from ursina import application
        base = getattr(application, "base", None)
        if base is None or getattr(base, "win", None) is None:
            print("[wk123-soak] no base.win; cannot maximize", flush=True)
            return
        pipe = getattr(base, "pipe", None)
        w = int(getattr(pipe, "getDisplayWidth", lambda: 0)()) if pipe else 0
        h = int(getattr(pipe, "getDisplayHeight", lambda: 0)()) if pipe else 0
        if w <= 0 or h <= 0:
            w, h = 1920, 1080  # fallback desktop size
        wp = WindowProperties()
        wp.setSize(w, h)
        wp.setOrigin(0, 0)
        base.win.requestProperties(wp)
        print(f"[wk123-soak] window maximized to {{w}}x{{h}}", flush=True)
    except Exception as exc:
        print(f"[wk123-soak] maximize failed: {{exc}}", flush=True)


def _screenshot(path):
    """Sync framebuffer grab + write (same path as ursina_app_debug_probe)."""
    try:
        from ursina import application
        from game.graphics.ursina_app_debug_probe import _save_window_screenshot_sync
        base = getattr(application, "base", None)
        if base is None:
            return False
        try:
            base.graphicsEngine.renderFrame()
            base.graphicsEngine.renderFrame()
        except Exception:
            pass
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        ok = _save_window_screenshot_sync(base, os.path.abspath(path))
        print(f"[wk123-soak] screenshot {{'saved' if ok else 'FAILED'}}: {{path}}", flush=True)
        return ok
    except Exception as exc:
        print(f"[wk123-soak] screenshot error: {{exc}}", flush=True)
        return False


def apply_patch():
    from game.graphics import ursina_app as ua
    from tools import wk123_scenario as scn

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)  # build the real world first
        engine = self.engine

        counts = scn.build_heavy_scenario(engine, heroes=24, buildings_target=100, enemies=80)
        _lock_speed()
        _set_zoom(engine)
        _maximize_window()
        print(
            "[wk123-soak] scenario READY: "
            f"heroes={{counts['heroes']}} buildings={{counts['buildings']}} "
            f"enemies={{counts['enemies']}} (alive={{counts['enemies_alive']}}) "
            f"| zoom={{_ZOOM_MODE}}({{engine.zoom:.3f}}) speed={{_SPEED_MODE}} window={{_WINDOW_MODE}}",
            flush=True,
        )

        # Open the CSV and write the header now.
        try:
            os.makedirs(os.path.dirname(os.path.abspath(_CSV_PATH)), exist_ok=True)
            _csv_fh = open(_CSV_PATH, "w", newline="", encoding="utf-8")
            _csv_writer = _csv.writer(_csv_fh)
            _csv_writer.writerow(_CSV_COLS)
            _csv_fh.flush()
        except Exception as exc:
            print(f"[wk123-soak] CSV open failed: {{exc}}", flush=True)
            _csv_fh = None
            _csv_writer = None

        state = {{
            "frame": 0,
            "wall0": _wall.perf_counter(),
            "next_log_wall": 0.0,         # first row immediately
            "shots_done": set(),          # which minute marks captured
        }}

        orig_tick = engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            state["frame"] += 1
            f = state["frame"]

            # (i) keep the swarm pinned at the cap (measure time, not attrition).
            if f % 40 == 0:
                scn.topup_enemies(engine)

            now = _wall.perf_counter()
            elapsed = now - state["wall0"]
            elapsed_min = elapsed / 60.0

            # densify the logging cadence inside the minute-15..17 window.
            log_interval = 2.0 if elapsed_min >= 15.0 else 15.0

            if elapsed >= state["next_log_wall"]:
                state["next_log_wall"] = elapsed + log_interval
                _write_row(engine, now - state["wall0"], dt, _csv_writer, _csv_fh)

            # (iii) forced screenshots at the 15 / 16 / 17 min marks.
            for mark in (15, 16, 17):
                if mark > _MINUTES:
                    continue
                if mark in state["shots_done"]:
                    continue
                if elapsed_min >= float(mark):
                    state["shots_done"].add(mark)
                    _screenshot(f"{{_SHOT_PREFIX}}_min{{mark}}.png")

            return result

        engine.tick_simulation = patched_tick

    ua.UrsinaApp.__init__ = patched_init


def _write_row(engine, wall_ts, dt, writer, fh):
    """Append one CSV FPS row. Best-effort; never raises into the tick loop."""
    try:
        from ursina import scene
        scene_entities = len(getattr(scene, "entities", []) or [])
    except Exception:
        scene_entities = -1
    fps_ema = float(getattr(engine, "_ursina_window_fps_ema", 0.0) or 0.0)
    dt_ms = float(dt or 0.0) * 1000.0
    # Pull the per-stage timings the engine records for the F2/slowlog overlay.
    eng = engine
    a = getattr(eng, "_wk123_last_stage_ms", None)
    # The slowlog accumulators live on the UrsinaApp, not the engine, so we recompute the
    # cheap stage proxies we can read off the engine; tick is the last sim cost, the
    # remaining stages are best-effort 0 if unavailable (the [frameavg] stdout log carries
    # the authoritative per-stage breakdown).
    tick_ms = float(getattr(eng, "_last_frame_dt_ms", 0.0) or 0.0)
    try:
        E = len([e for e in getattr(eng, "enemies", []) if getattr(e, "is_alive", True)])
    except Exception:
        E = -1
    B = len(getattr(eng, "buildings", []) or [])
    H = len(getattr(eng, "heroes", []) or [])
    try:
        alive_h = len([h for h in getattr(eng, "heroes", []) if getattr(h, "is_alive", True)])
    except Exception:
        alive_h = -1
    row = [
        f"{{wall_ts:.2f}}", f"{{fps_ema:.2f}}", f"{{dt_ms:.2f}}",
        f"{{tick_ms:.2f}}", "", "", "",  # rend/hudR/hudU: see [frameavg] stdout
        E, B, scene_entities, H, alive_h,
    ]
    if writer is not None:
        try:
            writer.writerow(row)
            if fh is not None:
                fh.flush()
        except Exception:
            pass
    print(
        f"[wk123-row] t={{wall_ts:.1f}}s fps_ema={{fps_ema:.1f}} dt={{dt_ms:.1f}}ms "
        f"E={{E}} B={{B}} ents={{scene_entities}} heroes={{H}} alive_h={{alive_h}}",
        flush=True,
    )


apply_patch()
'''


def _combo(zoom: str, speed: str, window: str) -> str:
    return f"{zoom}_{speed}_{window}"


def build_patch_source(*, zoom: str, speed: str, window: str, csv_path: Path,
                       shot_prefix: Path, minutes: float) -> str:
    return _PATCH_TEMPLATE.format(
        zoom_mode=zoom,
        speed_mode=speed,
        window_mode=window,
        csv_path=str(csv_path),
        shot_prefix=str(shot_prefix),
        minutes=float(minutes),
    )


def build_runner_source(patch_path: Path) -> str:
    """A tiny runner that loads the patch (rebinds UrsinaApp.__init__) then runs main.py."""
    rel_patch = patch_path.relative_to(PROJECT_ROOT).as_posix()
    return textwrap.dedent(
        f"""
        import importlib.util
        import sys
        from pathlib import Path

        ROOT = Path(__file__).resolve().parent
        sys.path.insert(0, str(ROOT))
        patch_path = ROOT / "{rel_patch}"
        spec = importlib.util.spec_from_file_location("wk123_soak_patch", patch_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)  # apply_patch() runs at import

        sys.argv = [str(ROOT / "main.py"), "--renderer", "ursina", "--no-llm"]
        import main as kingdom_main
        kingdom_main.main()
        """
    ).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="WK123 live FPS soak harness (real Ursina game).")
    ap.add_argument("--zoom", choices=["out", "normal"], default="out")
    ap.add_argument("--speed", choices=["normal", "fast"], default="fast")
    ap.add_argument("--window", choices=["windowed", "maximized"], default="maximized")
    ap.add_argument("--minutes", type=float, default=17.0,
                    help="Soak duration; maps to KINGDOM_URSINA_AUTO_EXIT_SEC = minutes*60.")
    ap.add_argument("--fps-warmup-sec", type=float, default=5.0,
                    help="Seconds skipped before the on-exit FPS-probe collects samples.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Write the patch + runner and print the command, but do not launch.")
    ns = ap.parse_args()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    combo = _combo(ns.zoom, ns.speed, ns.window)
    log_path = TMP_DIR / f"soak_{combo}.log"
    csv_path = TMP_DIR / f"soak_{combo}.csv"
    shot_prefix = SHOT_DIR / combo
    patch_path = TMP_DIR / f"_soak_patch_{combo}.py"
    runner_path = PROJECT_ROOT / f".wk123_soak_runner_{combo}.py"

    patch_path.write_text(
        build_patch_source(
            zoom=ns.zoom, speed=ns.speed, window=ns.window,
            csv_path=csv_path, shot_prefix=shot_prefix, minutes=ns.minutes,
        ),
        encoding="utf-8",
    )
    runner_path.write_text(build_runner_source(patch_path), encoding="utf-8")

    env = os.environ.copy()
    env["KINGDOM_URSINA_AUTO_EXIT_SEC"] = str(float(ns.minutes) * 60.0)
    env["KINGDOM_FPS_SLOWLOG"] = "1"
    env["KINGDOM_URSINA_FPS_PROBE"] = "1"
    env["KINGDOM_URSINA_FPS_PROBE_WARMUP_SEC"] = str(ns.fps_warmup_sec)
    # Screenshot at the auto-exit deadline (final-frame capture, alongside our min15/16/17 shots).
    env["KINGDOM_URSINA_AUTO_SCREENSHOT_PATH"] = str(shot_prefix.parent / f"{combo}_exit.png")
    env.setdefault("PYTHONUNBUFFERED", "1")

    cmd = [sys.executable, str(runner_path)]
    print(f"[wk123-soak] combo={combo} minutes={ns.minutes}")
    print(f"[wk123-soak] patch  : {patch_path}")
    print(f"[wk123-soak] runner : {runner_path}")
    print(f"[wk123-soak] log    : {log_path}")
    print(f"[wk123-soak] csv    : {csv_path}")
    print(f"[wk123-soak] shots  : {shot_prefix}_min{{15,16,17}}.png (+ _exit.png)")
    print(f"[wk123-soak] AUTO_EXIT_SEC={env['KINGDOM_URSINA_AUTO_EXIT_SEC']} "
          f"SLOWLOG=1 FPS_PROBE=1 WARMUP={ns.fps_warmup_sec}")
    print(f"[wk123-soak] cmd    : {' '.join(cmd)}")

    if ns.dry_run:
        print("[wk123-soak] --dry-run: not launching.")
        return 0

    # Tee stdout+stderr to the log file while still streaming to the console.
    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, universal_newlines=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            logf.write(line)
            logf.flush()
        rc = proc.wait()

    print(f"[wk123-soak] done rc={rc}. log={log_path} csv={csv_path}")
    # Leave the runner/patch on disk for forensics; they are regenerated each run.
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
