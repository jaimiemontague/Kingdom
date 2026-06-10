#!/usr/bin/env python3
"""Mythos Lag Fix LIVE FPS soak harness — fork of ``tools/wk123_fps_soak.py`` (which stays
untouched). Drives the REAL Ursina game with the heavy scenario for ~20.5 min unattended,
logging FPS-over-time + a screenshot BURST across the minute-15..20 acceptance window.
Tools-only; edits no game code. The scenario + first-frame hook are injected via a
generated capture-patch module that monkeypatches ``UrsinaApp.__init__`` (the proven
wk123/WK67 mechanism), so ``orig_init`` builds the world first and our hook runs after.

Env knobs wired up (same as wk123 — nothing reinvented):
  - ``KINGDOM_URSINA_AUTO_EXIT_SEC = minutes*60``  -> auto-quit at the soak deadline.
  - ``KINGDOM_FPS_SLOWLOG=1``                       -> [frameavg]/[slowframe] stage lines.
  - ``KINGDOM_URSINA_FPS_PROBE=1`` (+WARMUP)        -> on-exit avg/min/p10/p50/p90 + the
    per-frame stage samples we read for the CSV (see below).
  - ``KINGDOM_URSINA_AUTO_SCREENSHOT_PATH``         -> sync screenshot at the auto-exit.

Differences from wk123 (the Mythos spec):
  1. Default ``--minutes 20.5`` with an acceptance window minute 15->20
     (``--window-start 15 --window-end 20``). CSV rows every 15s outside the window,
     every 2s inside it.
  2. Screenshot BURST across the window: one shot every ``--shot-interval-sec``
     (default 3.0) -> ~100 shots/run, written to
     ``docs/screenshots/mythos_soak/<combo>/shot_mMM_SS.png`` (MM = elapsed minute,
     SS = second within that minute). Capture is the CHEAP single-readback path —
     the body of ``ursina_app_debug_probe._save_window_screenshot_sync``
     (``base.win.getScreenshot()`` -> ``PNMImage`` -> ``write``) — WITHOUT the two
     forced ``graphicsEngine.renderFrame()`` calls that helper's callers add, so each
     shot costs one GPU readback + one PNG encode, not two extra rendered frames.
     The CSV row written right after each capture carries ``shot=1`` so analysis can
     discount capture frames.
  3. Per-stage CSV columns FILLED (wk123 left rend/hudR/hudU blank): tick/rend/hudR/hudU
     come from the freshest per-frame samples the ``KINGDOM_URSINA_FPS_PROBE``
     instrumentation appends to ``UrsinaApp._fps_probe_stage_samples`` (stage names
     ``tick_simulation`` / ``ursina_renderer`` / ``pygame_hud_render`` /
     ``hud_texture_upload`` — recorded in ``ursina_app_frame.run_frame``). Before the
     probe warmup elapses we fall back to the ``KINGDOM_FPS_SLOWLOG`` rolling
     accumulators (``UrsinaApp._slowlog_accum`` keys tick/rend/hudr/hudu averaged over
     ``_slowlog_frames % 120`` frames since the last reset). All reads are best-effort
     ``getattr`` with 0.0 defaults — never raises into the tick loop. Values are from
     the LAST COMPLETED frame (our tick wrapper runs before this frame's rend/hud
     stages execute).
  4. End-of-run ``[mythos-verdict]`` block: the harness parses its own CSV after the
     subprocess exits and prints window row count, shots taken, window avg/p50/p10/min
     fps_ema, the hard gate PASS/FAIL (EVERY window row fps_ema > 30) and a softer
     p10>30 summary. Informational only — the process exit code stays the game's rc.
  5. ``--spawn-hitch-test`` (off by default): after a 60s warmup, force-spawn ONE
     warrior every 20s (the ``wk123_scenario`` guild + ``_spawn_warriors`` path that
     ``topup_heroes`` uses) and log
       ``[hitch] t=..s spawn#N maxdt_before=..ms maxdt_after=..ms``
     from the max per-frame dt in the +/-2s halo around each spawn; rows go to
     ``tmp/mythos/hitch_<combo>.csv`` (spawn_ts, max_dt_pre_ms, max_dt_post_ms,
     frames_over_80ms_post). NOTE: in this mode the periodic HERO top-up is disabled
     (the enemy top-up stays) so the controlled 20s spawns are the only hero-spawn
     source — otherwise the every-40-frames re-pin churn would pollute the +/-2s halos.
     A spawn within the final 2s of the run may be dropped (its post-halo never closes).
  6. Outputs under ``tmp/mythos/`` (logs + CSVs + generated patch) and
     ``docs/screenshots/mythos_soak/`` (shots). Runner: ``.mythos_soak_runner_<combo>.py``
     at the repo root (same pattern as wk123).
  7. ``--label <suffix>`` is appended to every output filename (CSV/log/patch/runner/
     shot dir) so repeat runs don't clobber, e.g. ``soak_out_fast_windowed_r2.csv``.

CSV columns: wall_ts, fps_ema, dt_ms, tick, rend, hudR, hudU, E, B, scene_entities,
             heroes, alive_heroes, shot.

Usage (the MAIN session — with a GPU — actually runs these; this file only builds, and
the headless validation only checks the generated artifacts, NOT the live GPU loop):

    # Gate combos (20.5 min each, window 15->20):
    python tools/mythos_fps_soak.py --zoom out --speed fast --window windowed
    python tools/mythos_fps_soak.py --zoom out --speed fast --window maximized

    # 2.5-min smoke (shrunken window, sparse shots):
    python tools/mythos_fps_soak.py --zoom out --speed fast --window windowed \
        --minutes 2.5 --window-start 1 --window-end 2.5 --shot-interval-sec 30 --label smoke

    # Spawn-hitch micro-lag test (60s warmup then +1 hero every 20s):
    python tools/mythos_fps_soak.py --zoom out --speed fast --window windowed \
        --spawn-hitch-test --minutes 6 --window-start 5 --window-end 6 \
        --shot-interval-sec 30 --label hitch

Outputs:
    tmp/mythos/soak_<combo>[<label>].log / .csv
    tmp/mythos/hitch_<combo>[<label>].csv            (only with --spawn-hitch-test)
    docs/screenshots/mythos_soak/<combo>[<label>]/shot_mMM_SS.png (+ exit.png)
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TMP_DIR = PROJECT_ROOT / "tmp" / "mythos"
SHOT_ROOT = PROJECT_ROOT / "docs" / "screenshots" / "mythos_soak"

FPS_GATE = 30.0  # the hard gate: every acceptance-window row must have fps_ema > 30

# ---------------------------------------------------------------------------
# The generated capture patch (string). Loaded by the runner BEFORE main.py so
# its apply_patch() rebinds UrsinaApp.__init__ before the app is constructed.
# Placeholders {...} are .format()-substituted with the run config; every literal
# brace is doubled ({{ }}). Validation (c) ast-parses the generated output.
# ---------------------------------------------------------------------------
_PATCH_TEMPLATE = r'''"""MYTHOS GENERATED soak capture patch — do not edit by hand (tools/mythos_fps_soak.py)."""
from __future__ import annotations

import os
import time as _wall
import csv as _csv

import config

# Run config injected by the harness.
_ZOOM_MODE = {zoom_mode!r}      # "out" | "normal"
_SPEED_MODE = {speed_mode!r}    # "fast" | "normal"
_WINDOW_MODE = {window_mode!r}  # "maximized" | "windowed"
_CSV_PATH = {csv_path!r}
_SHOT_DIR = {shot_dir!r}        # docs/screenshots/mythos_soak/<combo>[<label>]
_MINUTES = {minutes!r}
_HEROES = {heroes!r}            # warriors to force-spawn (Sovereign spec: 20+)
_BUILDINGS = {buildings!r}      # building-count target (Sovereign spec: 20+)
_ENEMIES = {enemies!r}          # enemies to ring-spawn (Sovereign spec: 75+)
_WIN_START_S = {window_start_s!r}   # acceptance window start (seconds)
_WIN_END_S = {window_end_s!r}       # acceptance window end (seconds)
_SHOT_EVERY_S = {shot_interval_s!r} # screenshot cadence inside the window
_HITCH = {hitch!r}              # spawn-hitch capture mode on/off
_HITCH_CSV_PATH = {hitch_csv_path!r}

_HITCH_WARMUP_S = 60.0     # no controlled spawns before this
_HITCH_EVERY_S = 20.0      # one forced hero spawn per this interval
_HITCH_HALO_S = 2.0        # max-dt window measured on each side of a spawn
_HITCH_OVER_MS = 80.0      # "frames_over_80ms_post" threshold

_CSV_COLS = [
    "wall_ts", "fps_ema", "dt_ms", "tick", "rend", "hudR", "hudU",
    "E", "B", "scene_entities", "heroes", "alive_heroes", "shot",
]
_HITCH_COLS = ["spawn_ts", "max_dt_pre_ms", "max_dt_post_ms", "frames_over_80ms_post"]


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
        print(f"[mythos-soak] zoom set failed: {{exc}}", flush=True)


def _maximize_window():
    if _WINDOW_MODE != "maximized":
        return
    try:
        from panda3d.core import WindowProperties
        from ursina import application
        base = getattr(application, "base", None)
        if base is None or getattr(base, "win", None) is None:
            print("[mythos-soak] no base.win; cannot maximize", flush=True)
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
        print(f"[mythos-soak] window maximized to {{w}}x{{h}}", flush=True)
    except Exception as exc:
        print(f"[mythos-soak] maximize failed: {{exc}}", flush=True)


def _screenshot(path):
    """CHEAP current-framebuffer grab: one GPU readback + one PNG write.

    This is the body of ``ursina_app_debug_probe._save_window_screenshot_sync``
    (base.win.getScreenshot() -> PNMImage -> write) WITHOUT the two forced
    ``graphicsEngine.renderFrame()`` calls its callers add — we are mid-burst on a
    live frame loop, so the framebuffer already holds the most recent frame and
    forcing two re-renders per shot would double-charge every capture.
    """
    try:
        from ursina import application
        from panda3d.core import Filename, PNMImage
        base = getattr(application, "base", None)
        if base is None or getattr(base, "win", None) is None:
            return False
        tex = base.win.getScreenshot()
        if tex is None:
            print("[mythos-soak] getScreenshot returned None", flush=True)
            return False
        img = PNMImage()
        if not tex.store(img):
            print("[mythos-soak] Texture.store failed", flush=True)
            return False
        out_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        return bool(img.write(Filename.fromOsSpecific(out_path)))
    except Exception as exc:
        print(f"[mythos-soak] screenshot error: {{exc}}", flush=True)
        return False


def _stage_ms(app):
    """Freshest per-frame tick/rend/hudR/hudU stage ms, best-effort off the app object.

    Primary: the last per-frame samples KINGDOM_URSINA_FPS_PROBE instrumentation appends
    to ``app._fps_probe_stage_samples`` (see ursina_app_frame.run_frame ->
    _record_fps_probe_stage_ms). These are last-COMPLETED-frame values: our tick wrapper
    runs before this frame's rend/hud stages execute, so all four stay consistent.
    Fallback (probe warmup not yet elapsed): the KINGDOM_FPS_SLOWLOG rolling accumulators
    (``app._slowlog_accum``) averaged over the frames since their last 120-frame reset.
    Never raises; missing values default to 0.0.
    """
    out = {{"tick": 0.0, "rend": 0.0, "hudR": 0.0, "hudU": 0.0}}
    try:
        samples = getattr(app, "_fps_probe_stage_samples", None) or {{}}
        names = {{
            "tick": "tick_simulation",
            "rend": "ursina_renderer",
            "hudR": "pygame_hud_render",
            "hudU": "hud_texture_upload",
        }}
        got_any = False
        for key, name in names.items():
            lst = samples.get(name) or []
            if lst:
                out[key] = float(lst[-1])
                got_any = True
        if got_any:
            return out
    except Exception:
        pass
    try:
        acc = getattr(app, "_slowlog_accum", None) or {{}}
        n = int(getattr(app, "_slowlog_frames", 0) or 0) % 120
        if n > 0 and acc:
            out["tick"] = float(acc.get("tick", 0.0)) / n
            out["rend"] = float(acc.get("rend", 0.0)) / n
            out["hudR"] = float(acc.get("hudr", 0.0)) / n
            out["hudU"] = float(acc.get("hudu", 0.0)) / n
    except Exception:
        pass
    return out


def _write_row(app, engine, wall_ts, dt, writer, fh, shot_flag):
    """Append one CSV FPS row. Best-effort; never raises into the tick loop."""
    try:
        from ursina import scene
        scene_entities = len(getattr(scene, "entities", []) or [])
    except Exception:
        scene_entities = -1
    fps_ema = float(getattr(engine, "_ursina_window_fps_ema", 0.0) or 0.0)
    dt_ms = float(dt or 0.0) * 1000.0
    stages = _stage_ms(app)
    try:
        E = len([e for e in getattr(engine, "enemies", []) if getattr(e, "is_alive", True)])
    except Exception:
        E = -1
    B = len(getattr(engine, "buildings", []) or [])
    H = len(getattr(engine, "heroes", []) or [])
    try:
        alive_h = len([h for h in getattr(engine, "heroes", []) if getattr(h, "is_alive", True)])
    except Exception:
        alive_h = -1
    row = [
        f"{{wall_ts:.2f}}", f"{{fps_ema:.2f}}", f"{{dt_ms:.2f}}",
        f"{{stages['tick']:.2f}}", f"{{stages['rend']:.2f}}",
        f"{{stages['hudR']:.2f}}", f"{{stages['hudU']:.2f}}",
        E, B, scene_entities, H, alive_h, 1 if shot_flag else 0,
    ]
    if writer is not None:
        try:
            writer.writerow(row)
            if fh is not None:
                fh.flush()
        except Exception:
            pass
    print(
        f"[mythos-row] t={{wall_ts:.1f}}s fps_ema={{fps_ema:.1f}} dt={{dt_ms:.1f}}ms "
        f"tick={{stages['tick']:.1f}} rend={{stages['rend']:.1f}} "
        f"hudR={{stages['hudR']:.1f}} hudU={{stages['hudU']:.1f}} "
        f"E={{E}} B={{B}} ents={{scene_entities}} heroes={{H}} alive_h={{alive_h}} "
        f"shot={{1 if shot_flag else 0}}",
        flush=True,
    )


def apply_patch():
    from game.graphics import ursina_app as ua
    from tools import wk123_scenario as scn

    orig_init = ua.UrsinaApp.__init__

    def patched_init(self, ai_controller_factory):
        orig_init(self, ai_controller_factory)  # build the real world first
        app = self
        engine = self.engine

        counts = scn.build_heavy_scenario(
            engine, heroes=_HEROES, buildings_target=_BUILDINGS, enemies=_ENEMIES
        )
        _lock_speed()
        _set_zoom(engine)
        _maximize_window()
        print(
            "[mythos-soak] scenario READY: "
            f"heroes={{counts['heroes']}} buildings={{counts['buildings']}} "
            f"enemies={{counts['enemies']}} (alive={{counts['enemies_alive']}}) "
            f"| zoom={{_ZOOM_MODE}}({{engine.zoom:.3f}}) speed={{_SPEED_MODE}} "
            f"window={{_WINDOW_MODE}} hitch={{_HITCH}}",
            flush=True,
        )

        # Open the soak CSV and write the header now.
        try:
            os.makedirs(os.path.dirname(os.path.abspath(_CSV_PATH)), exist_ok=True)
            _csv_fh = open(_CSV_PATH, "w", newline="", encoding="utf-8")
            _csv_writer = _csv.writer(_csv_fh)
            _csv_writer.writerow(_CSV_COLS)
            _csv_fh.flush()
        except Exception as exc:
            print(f"[mythos-soak] CSV open failed: {{exc}}", flush=True)
            _csv_fh = None
            _csv_writer = None

        # Hitch CSV (only in --spawn-hitch-test mode).
        _hitch_fh = None
        _hitch_writer = None
        if _HITCH:
            try:
                os.makedirs(os.path.dirname(os.path.abspath(_HITCH_CSV_PATH)), exist_ok=True)
                _hitch_fh = open(_HITCH_CSV_PATH, "w", newline="", encoding="utf-8")
                _hitch_writer = _csv.writer(_hitch_fh)
                _hitch_writer.writerow(_HITCH_COLS)
                _hitch_fh.flush()
            except Exception as exc:
                print(f"[mythos-soak] hitch CSV open failed: {{exc}}", flush=True)
                _hitch_fh = None
                _hitch_writer = None

        state = {{
            "frame": 0,
            "wall0": _wall.perf_counter(),
            "next_log_wall": 0.0,            # first row immediately
            "next_shot_wall": float(_WIN_START_S),
            "shots_taken": 0,
            "pending_shot": False,           # set on capture, consumed by the next CSV row
            "dtbuf": [],                     # (elapsed_s, dt_ms) ring for the hitch halos
            "next_spawn_wall": _HITCH_WARMUP_S,
            "spawn_n": 0,
            "pending_spawns": [],            # open hitch events awaiting their post-halo
        }}

        orig_tick = engine.tick_simulation

        def patched_tick(dt):
            result = orig_tick(dt)
            state["frame"] += 1
            f = state["frame"]

            now = _wall.perf_counter()
            elapsed = now - state["wall0"]
            dt_ms = float(dt or 0.0) * 1000.0

            # Rolling per-frame dt buffer for the spawn-hitch +/-2s halos.
            if _HITCH:
                buf = state["dtbuf"]
                buf.append((elapsed, dt_ms))
                cutoff = elapsed - (_HITCH_HALO_S + 0.5)
                while buf and buf[0][0] < cutoff:
                    buf.pop(0)

            # Keep the swarm pinned (measure time, not attrition). In hitch mode the
            # periodic HERO top-up is disabled so the controlled 20s spawns are the
            # only hero-spawn source (re-pin churn would pollute the halos).
            if f % 40 == 0:
                scn.topup_enemies(engine)
                if not _HITCH:
                    scn.topup_heroes(engine, target=_HEROES)

            # Spawn-hitch mode: one forced warrior every 20s after the 60s warmup.
            if _HITCH and elapsed >= state["next_spawn_wall"]:
                state["next_spawn_wall"] += _HITCH_EVERY_S
                state["spawn_n"] += 1
                try:
                    guild = scn._get_or_make_guild(engine)
                    scn._spawn_warriors(engine, guild, 1, start_index=len(engine.heroes))
                except Exception as exc:
                    print(f"[mythos-soak] hitch spawn failed: {{exc}}", flush=True)
                pre = [d for (t, d) in state["dtbuf"] if elapsed - _HITCH_HALO_S <= t < elapsed]
                state["pending_spawns"].append({{
                    "n": state["spawn_n"],
                    "t": elapsed,
                    "pre_max": max(pre) if pre else 0.0,
                    "post": [],
                }})

            # Collect post-halo frames + finalize closed hitch events.
            if _HITCH and state["pending_spawns"]:
                done = []
                for ev in state["pending_spawns"]:
                    if elapsed <= ev["t"] + _HITCH_HALO_S:
                        ev["post"].append(dt_ms)
                    else:
                        done.append(ev)
                for ev in done:
                    state["pending_spawns"].remove(ev)
                    post_max = max(ev["post"]) if ev["post"] else 0.0
                    over = len([d for d in ev["post"] if d > _HITCH_OVER_MS])
                    print(
                        f"[hitch] t={{ev['t']:.1f}}s spawn#{{ev['n']}} "
                        f"maxdt_before={{ev['pre_max']:.1f}}ms maxdt_after={{post_max:.1f}}ms "
                        f"frames_over_{{int(_HITCH_OVER_MS)}}ms_post={{over}}",
                        flush=True,
                    )
                    if _hitch_writer is not None:
                        try:
                            _hitch_writer.writerow([
                                f"{{ev['t']:.2f}}", f"{{ev['pre_max']:.2f}}",
                                f"{{post_max:.2f}}", over,
                            ])
                            if _hitch_fh is not None:
                                _hitch_fh.flush()
                        except Exception:
                            pass

            # Screenshot burst across the acceptance window.
            in_window = _WIN_START_S <= elapsed <= _WIN_END_S
            if in_window and elapsed >= state["next_shot_wall"]:
                state["next_shot_wall"] += float(_SHOT_EVERY_S)
                if state["next_shot_wall"] <= elapsed:  # never burst-catch-up after a stall
                    state["next_shot_wall"] = elapsed + float(_SHOT_EVERY_S)
                mm = int(elapsed // 60)
                ss = int(elapsed % 60)
                shot_path = os.path.join(_SHOT_DIR, "shot_m%02d_%02d.png" % (mm, ss))
                ok = _screenshot(shot_path)
                if ok:
                    state["shots_taken"] += 1
                    state["pending_shot"] = True
                print(
                    f"[mythos-shot] #{{state['shots_taken']}} t={{elapsed:.1f}}s "
                    f"{{'saved' if ok else 'FAILED'}}: {{shot_path}}",
                    flush=True,
                )

            # CSV cadence: 15s outside the window, 2s inside it.
            log_interval = 2.0 if in_window else 15.0
            if elapsed >= state["next_log_wall"]:
                state["next_log_wall"] = elapsed + log_interval
                shot_flag = state["pending_shot"]
                state["pending_shot"] = False
                _write_row(app, engine, elapsed, dt, _csv_writer, _csv_fh, shot_flag)

            return result

        engine.tick_simulation = patched_tick

    ua.UrsinaApp.__init__ = patched_init


apply_patch()
'''


def _combo(zoom: str, speed: str, window: str) -> str:
    return f"{zoom}_{speed}_{window}"


def _norm_label(label: str) -> str:
    """Normalize --label into a `_suffix` filename fragment ('' when unset)."""
    label = (label or "").strip().strip("_")
    return f"_{label}" if label else ""


def build_patch_source(*, zoom: str, speed: str, window: str, csv_path: Path,
                       shot_dir: Path, minutes: float, heroes: int, buildings: int,
                       enemies: int, window_start_min: float, window_end_min: float,
                       shot_interval_sec: float, hitch: bool, hitch_csv_path: Path) -> str:
    return _PATCH_TEMPLATE.format(
        zoom_mode=zoom,
        speed_mode=speed,
        window_mode=window,
        csv_path=str(csv_path),
        shot_dir=str(shot_dir),
        minutes=float(minutes),
        heroes=int(heroes),
        buildings=int(buildings),
        enemies=int(enemies),
        window_start_s=float(window_start_min) * 60.0,
        window_end_s=float(window_end_min) * 60.0,
        shot_interval_s=float(shot_interval_sec),
        hitch=bool(hitch),
        hitch_csv_path=str(hitch_csv_path),
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
        spec = importlib.util.spec_from_file_location("mythos_soak_patch", patch_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)  # apply_patch() runs at import

        sys.argv = [str(ROOT / "main.py"), "--renderer", "ursina", "--no-llm"]
        import main as kingdom_main
        kingdom_main.main()
        """
    ).strip()


# ---------------------------------------------------------------------------
# End-of-run verdict (parses the CSV the patch wrote).
# ---------------------------------------------------------------------------

def _pctl(sorted_vals: list[float], frac: float) -> float:
    """Same index style as the in-game fps-probe summary (ursina_app_debug_probe)."""
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * frac) - 1))
    return sorted_vals[idx]


def compute_verdict(csv_path: Path | str, window_start_min: float,
                    window_end_min: float, gate_fps: float = FPS_GATE) -> dict:
    """Parse the soak CSV and compute the acceptance-window verdict.

    Returns a dict: window_rows, shots_flagged, avg, p50, p10, min, gate_pass
    (EVERY window row fps_ema > gate_fps), soft_pass (p10 > gate_fps).
    Empty/missing window data -> rows=0 and both verdicts False.
    """
    lo = float(window_start_min) * 60.0
    hi = float(window_end_min) * 60.0
    fps_vals: list[float] = []
    shots = 0
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            try:
                t = float(rec.get("wall_ts", ""))
                fps = float(rec.get("fps_ema", ""))
            except (TypeError, ValueError):
                continue
            if lo <= t <= hi:
                fps_vals.append(fps)
                if str(rec.get("shot", "0")).strip() == "1":
                    shots += 1
    fps_sorted = sorted(fps_vals)
    n = len(fps_sorted)
    return {
        "window_rows": n,
        "shots_flagged": shots,
        "avg": (sum(fps_sorted) / n) if n else 0.0,
        "p50": _pctl(fps_sorted, 0.50),
        "p10": _pctl(fps_sorted, 0.10),
        "min": fps_sorted[0] if n else 0.0,
        "gate_pass": bool(n) and all(v > gate_fps for v in fps_sorted),
        "soft_pass": bool(n) and _pctl(fps_sorted, 0.10) > gate_fps,
    }


def print_verdict(csv_path: Path, window_start_min: float, window_end_min: float,
                  shot_dir: Path | None = None) -> dict | None:
    """Print the [mythos-verdict] block. Informational only — never raises."""
    try:
        v = compute_verdict(csv_path, window_start_min, window_end_min)
    except Exception as exc:
        print(f"[mythos-verdict] FAILED to parse {csv_path}: {exc}")
        return None
    shots_on_disk = None
    if shot_dir is not None:
        try:
            shots_on_disk = len(list(Path(shot_dir).glob("shot_m*.png")))
        except Exception:
            shots_on_disk = None
    print(f"[mythos-verdict] csv={csv_path} window={window_start_min:g}..{window_end_min:g}min")
    print(f"[mythos-verdict] window_rows={v['window_rows']} shots_flagged={v['shots_flagged']}"
          + (f" shots_on_disk={shots_on_disk}" if shots_on_disk is not None else ""))
    if v["window_rows"] == 0:
        print("[mythos-verdict] NO window rows - gate cannot be evaluated: FAIL (no-data)")
        return v
    print(f"[mythos-verdict] window fps_ema: avg={v['avg']:.1f} p50={v['p50']:.1f} "
          f"p10={v['p10']:.1f} min={v['min']:.1f}")
    print(f"[mythos-verdict] gate (ALL window rows fps_ema>{FPS_GATE:g}): "
          f"{'PASS' if v['gate_pass'] else 'FAIL'}")
    print(f"[mythos-verdict] soft (p10>{FPS_GATE:g}): "
          f"{'PASS' if v['soft_pass'] else 'FAIL'}")
    return v


def print_hitch_summary(hitch_csv: Path) -> None:
    """Print a one-line summary of the hitch CSV. Informational only — never raises."""
    try:
        if not Path(hitch_csv).is_file():
            print(f"[mythos-hitch-summary] no hitch CSV at {hitch_csv}")
            return
        post = []
        over_spawns = 0
        with open(hitch_csv, newline="", encoding="utf-8") as fh:
            for rec in csv.DictReader(fh):
                try:
                    post.append(float(rec.get("max_dt_post_ms", "")))
                    if int(float(rec.get("frames_over_80ms_post", "0"))) > 0:
                        over_spawns += 1
                except (TypeError, ValueError):
                    continue
        worst = max(post) if post else 0.0
        print(f"[mythos-hitch-summary] spawns={len(post)} worst_post_dt={worst:.1f}ms "
              f"spawns_with_frames_over_80ms={over_spawns} csv={hitch_csv}")
    except Exception as exc:
        print(f"[mythos-hitch-summary] FAILED to parse {hitch_csv}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mythos live FPS soak harness (real Ursina game; fork of wk123).")
    ap.add_argument("--zoom", choices=["out", "normal"], default="out")
    ap.add_argument("--speed", choices=["normal", "fast"], default="fast")
    ap.add_argument("--window", choices=["windowed", "maximized"], default="maximized")
    ap.add_argument("--minutes", type=float, default=20.5,
                    help="Soak duration; maps to KINGDOM_URSINA_AUTO_EXIT_SEC = minutes*60.")
    ap.add_argument("--window-start", type=float, default=15.0,
                    help="Acceptance-window start (minutes): 2s CSV rows + shot burst begin.")
    ap.add_argument("--window-end", type=float, default=20.0,
                    help="Acceptance-window end (minutes).")
    ap.add_argument("--shot-interval-sec", type=float, default=3.0,
                    help="Screenshot cadence inside the acceptance window (~100 shots at 3s).")
    ap.add_argument("--heroes", type=int, default=24,
                    help="Warriors to force-spawn (Sovereign spec: 20+; default 24).")
    ap.add_argument("--buildings", type=int, default=24,
                    help="Building-count target (Sovereign spec: 20+; default 24).")
    ap.add_argument("--enemies", type=int, default=80,
                    help="Enemies to ring-spawn (Sovereign spec: 75+; default 80).")
    ap.add_argument("--fps-warmup-sec", type=float, default=5.0,
                    help="Seconds skipped before the FPS-probe collects samples.")
    ap.add_argument("--spawn-hitch-test", action="store_true",
                    help="Hitch mode: 60s warmup then force-spawn 1 hero every 20s; "
                         "log [hitch] max-dt halos + write tmp/mythos/hitch_<combo>.csv. "
                         "Disables the periodic hero top-up (enemy top-up stays).")
    ap.add_argument("--label", default="",
                    help="Suffix appended to output filenames so repeat runs don't "
                         "clobber (e.g. --label r2 -> soak_out_fast_windowed_r2.csv).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Write the patch + runner and print the command, but do not launch.")
    ns = ap.parse_args()

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    SHOT_ROOT.mkdir(parents=True, exist_ok=True)

    combo = _combo(ns.zoom, ns.speed, ns.window)
    tag = combo + _norm_label(ns.label)
    log_path = TMP_DIR / f"soak_{tag}.log"
    csv_path = TMP_DIR / f"soak_{tag}.csv"
    hitch_csv_path = TMP_DIR / f"hitch_{tag}.csv"
    shot_dir = SHOT_ROOT / tag
    patch_path = TMP_DIR / f"_soak_patch_{tag}.py"
    runner_path = PROJECT_ROOT / f".mythos_soak_runner_{tag}.py"

    patch_path.write_text(
        build_patch_source(
            zoom=ns.zoom, speed=ns.speed, window=ns.window,
            csv_path=csv_path, shot_dir=shot_dir, minutes=ns.minutes,
            heroes=ns.heroes, buildings=ns.buildings, enemies=ns.enemies,
            window_start_min=ns.window_start, window_end_min=ns.window_end,
            shot_interval_sec=ns.shot_interval_sec,
            hitch=ns.spawn_hitch_test, hitch_csv_path=hitch_csv_path,
        ),
        encoding="utf-8",
    )
    runner_path.write_text(build_runner_source(patch_path), encoding="utf-8")

    env = os.environ.copy()
    env["KINGDOM_URSINA_AUTO_EXIT_SEC"] = str(float(ns.minutes) * 60.0)
    env["KINGDOM_FPS_SLOWLOG"] = "1"
    env["KINGDOM_URSINA_FPS_PROBE"] = "1"
    env["KINGDOM_URSINA_FPS_PROBE_WARMUP_SEC"] = str(ns.fps_warmup_sec)
    # Final-frame capture at the auto-exit deadline, next to the burst shots.
    env["KINGDOM_URSINA_AUTO_SCREENSHOT_PATH"] = str(shot_dir / "exit.png")
    env.setdefault("PYTHONUNBUFFERED", "1")

    cmd = [sys.executable, str(runner_path)]
    print(f"[mythos-soak] combo={combo} label={ns.label or '-'} minutes={ns.minutes} "
          f"window={ns.window_start}..{ns.window_end}min shot_every={ns.shot_interval_sec}s "
          f"heroes={ns.heroes} buildings={ns.buildings} enemies={ns.enemies} "
          f"hitch={ns.spawn_hitch_test}")
    print(f"[mythos-soak] patch  : {patch_path}")
    print(f"[mythos-soak] runner : {runner_path}")
    print(f"[mythos-soak] log    : {log_path}")
    print(f"[mythos-soak] csv    : {csv_path}")
    if ns.spawn_hitch_test:
        print(f"[mythos-soak] hitch  : {hitch_csv_path}")
    print(f"[mythos-soak] shots  : {shot_dir}\\shot_mMM_SS.png (+ exit.png)")
    print(f"[mythos-soak] AUTO_EXIT_SEC={env['KINGDOM_URSINA_AUTO_EXIT_SEC']} "
          f"SLOWLOG=1 FPS_PROBE=1 WARMUP={ns.fps_warmup_sec}")
    print(f"[mythos-soak] cmd    : {' '.join(cmd)}")

    if ns.dry_run:
        print("[mythos-soak] --dry-run: not launching.")
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

    print(f"[mythos-soak] done rc={rc}. log={log_path} csv={csv_path}")
    # Informational verdict (never changes rc).
    if csv_path.is_file():
        print_verdict(csv_path, ns.window_start, ns.window_end, shot_dir=shot_dir)
    else:
        print(f"[mythos-verdict] no CSV written at {csv_path} (run died before frame 1?)")
    if ns.spawn_hitch_test:
        print_hitch_summary(hitch_csv_path)
    # Leave the runner/patch on disk for forensics; they are regenerated each run.
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
