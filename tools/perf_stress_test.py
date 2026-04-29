#!/usr/bin/env python3
"""
Measure UrsinaRenderer frame time at high unit counts (SimEngine + snapshot + update loop).

Examples (from repo root, PowerShell):
  python tools/perf_stress_test.py --units 200 --frames 300
  python tools/perf_stress_test.py --units 500 --frames 300
  python tools/perf_stress_test.py --units 1000 --frames 300
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Headless pygame (fonts/audio safe for CI) — Ursina/Panda still opens a GL context if available.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ursina defaults application.asset_folder to dirname(sys.argv[0]) → "tools/" when this file is run
# directly. Force the game project root so assets/models resolve like `python main.py`.
import ursina.application as ursina_application  # noqa: E402

ursina_application.asset_folder = PROJECT_ROOT
ursina_application.scenes_folder = PROJECT_ROOT / "scenes"
ursina_application.scripts_folder = PROJECT_ROOT / "scripts"
ursina_application.fonts_folder = PROJECT_ROOT / "fonts"
ursina_application.textures_compressed_folder = PROJECT_ROOT / "textures_compressed"
ursina_application.models_compressed_folder = PROJECT_ROOT / "models_compressed"
try:
    from panda3d.core import getModelPath

    getModelPath().append_path(str(PROJECT_ROOT.resolve()))
except Exception:
    pass

# ---------------------------------------------------------------------------
# Imports that require PROJECT_ROOT on sys.path
# ---------------------------------------------------------------------------
import pygame  # noqa: E402

import config  # noqa: E402
from config import TILE_SIZE, WINDOW_HEIGHT, WINDOW_WIDTH  # noqa: E402
from game.entities import Goblin, Hero, WarriorGuild  # noqa: E402
from game.graphics.ursina_renderer import UrsinaRenderer  # noqa: E402
from game.sim_engine import SimEngine  # noqa: E402
from game.world import TileType  # noqa: E402
from ursina import Entity, Ursina, scene, window  # noqa: E402
from ursina.shaders import lit_with_shadows_shader, unlit_shader  # noqa: E402


def _place_warrior_guild(sim: SimEngine) -> WarriorGuild:
    castle = next(b for b in sim.buildings if getattr(b, "building_type", None) == "castle")
    gx = int(castle.grid_x) - 4
    gy = int(castle.grid_y) + 2
    guild = WarriorGuild(gx, gy)
    sim.buildings.append(guild)
    w, h = guild.size
    for dy in range(int(h)):
        for dx in range(int(w)):
            sim.world.set_tile(gx + dx, gy + dy, int(TileType.PATH))
    return guild


def _spawn_heroes_and_enemies(sim: SimEngine, guild: WarriorGuild, total: int) -> tuple[int, int]:
    """Split ``total`` across heroes (warrior) and goblins; return (n_heroes, n_enemies)."""
    n_h = max(0, total // 2)
    n_e = max(0, total - n_h)
    # Warriors in a loose spiral around the guild (deterministic).
    for i in range(n_h):
        ang = float(i) * 2.399963229728653  # golden angle
        r = TILE_SIZE * (2.0 + (i % 60) * 0.35)
        hx = guild.center_x + r * math.cos(ang)
        hy = guild.center_y + r * math.sin(ang)
        h = Hero(hx, hy, hero_class="warrior")
        h.home_building = guild
        h.gold = 120
        sim.heroes.append(h)

    castle = next(b for b in sim.buildings if getattr(b, "building_type", None) == "castle")
    for i in range(n_e):
        ang = float(i) * 2.5132741228718345
        r = TILE_SIZE * (4.0 + (i % 80) * 0.4)
        ex = castle.center_x + r * math.cos(ang)
        ey = castle.center_y + r * math.sin(ang)
        sim.enemies.append(Goblin(ex, ey))

    return n_h, n_e


def _make_snapshot(sim: SimEngine):
    castle = next(b for b in sim.buildings if getattr(b, "building_type", None) == "castle")
    cx = float(castle.center_x) - float(WINDOW_WIDTH) * 0.5
    cy = float(castle.center_y) - float(WINDOW_HEIGHT) * 0.5
    return sim.build_snapshot(
        vfx_projectiles=(),
        screen_w=int(WINDOW_WIDTH),
        screen_h=int(WINDOW_HEIGHT),
        camera_x=cx,
        camera_y=cy,
        zoom=1.0,
        default_zoom=1.0,
        paused=False,
        running=True,
        pause_menu_visible=False,
    )


def _pct_index(n: int, p: float) -> int:
    if n <= 0:
        return 0
    return min(n - 1, max(0, int(math.floor(float(p) * float(n - 1)))))


def _one_percent_low_fps_ms(sorted_ms_asc: list[float]) -> tuple[float, float]:
    """
    Common game-benchmark convention: sort frame times ascending (fast..slow);
    take the slowest 1% slice and report mean ms and equivalent FPS for that slice.
    """
    n = len(sorted_ms_asc)
    if n == 0:
        return 0.0, 0.0
    k = max(1, int(math.ceil(n * 0.01)))
    worst = sorted_ms_asc[-k:]
    mean_ms = float(statistics.mean(worst))
    fps = (1000.0 / mean_ms) if mean_ms > 1e-9 else 0.0
    return mean_ms, fps


def _bootstrap_ursina() -> Ursina:
    pygame.init()
    pygame.display.init()
    pygame.display.set_mode((1, 1))

    _ursina_shadows = bool(getattr(config, "URSINA_DIRECTIONAL_SHADOWS", False))
    app = Ursina(
        title="Kingdom Sim - perf stress (non-interactive)",
        borderless=False,
        fullscreen=False,
        development_mode=False,
    )
    window.exit_button.visible = False
    window.fps_counter.enabled = False
    Entity.default_shader = lit_with_shadows_shader if _ursina_shadows else unlit_shader
    try:
        scene.clearFog()
    except Exception:
        pass
    try:
        from panda3d.core import LVecBase4f

        base = app
        base.setBackgroundColor(LVecBase4f(0.06, 0.07, 0.09, 1.0))
    except Exception:
        pass

    return app


def _write_json_record(
    *,
    record: dict,
    out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"schema_version": 1, "last_run": record, "history": []}
    if out_path.exists():
        try:
            prev = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict):
                hist = prev.get("history")
                hist = hist if isinstance(hist, list) else []
                old_last = prev.get("last_run")
                if isinstance(old_last, dict):
                    hist.append(old_last)
                payload["history"] = hist[-50:]
        except Exception:
            pass

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[perf_stress_test] wrote {out_path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ursina renderer stress (ms per renderer.update)")
    ap.add_argument("--units", type=int, default=200, help="Total units (heroes + enemies; half/half)")
    ap.add_argument("--frames", type=int, default=300, help="Measured frames after warmup")
    ap.add_argument("--warmup", type=int, default=30, help="Warmup frames (not counted in stats)")
    ap.add_argument(
        "--json-out",
        type=str,
        default=str(PROJECT_ROOT / "tools" / "perf_stress_baseline_wk47.json"),
        help="Output JSON path (default: tools/perf_stress_baseline_wk47.json)",
    )
    ns = ap.parse_args()

    total_units = max(0, int(ns.units))
    measure_frames = max(1, int(ns.frames))
    warmup_frames = max(0, int(ns.warmup))
    json_out = Path(ns.json_out)

    sim = SimEngine()
    sim.setup_initial_state()
    guild = _place_warrior_guild(sim)
    n_h, n_e = _spawn_heroes_and_enemies(sim, guild, total_units)

    print("[perf_stress_test] boot Ursina + UrsinaRenderer ...", flush=True)
    app = _bootstrap_ursina()
    renderer = UrsinaRenderer(sim.world)

    samples_ms: list[float] = []
    frame_idx = [0]
    total_frames = warmup_frames + measure_frames

    def _finalize_and_exit() -> None:
        if not samples_ms:
            print("[perf_stress_test] ERROR: no timed samples collected.", flush=True)
        s = sorted(samples_ms)
        avg_ms = float(statistics.mean(samples_ms))
        min_ms = float(min(samples_ms))
        max_ms = float(max(samples_ms))
        p99_ms = s[_pct_index(len(s), 0.99)] if s else 0.0
        one_pct_mean_ms, one_pct_low_fps = _one_percent_low_fps_ms(s)
        avg_fps = (1000.0 / avg_ms) if avg_ms > 1e-9 else 0.0

        print("", flush=True)
        print("perf_stress_test (UrsinaRenderer.update)")
        print("-" * 52)
        print(f"  units (heroes/enemies): {total_units}  ({n_h} / {n_e})")
        print(f"  warmup frames:          {warmup_frames}")
        print(f"  measured frames:        {measure_frames}")
        print(f"  avg frame time (ms):    {avg_ms:.3f}")
        print(f"  min / max (ms):         {min_ms:.3f} / {max_ms:.3f}")
        print(f"  avg FPS:                {avg_fps:.2f}")
        print(f"  1% low (worst 1% mean): {one_pct_low_fps:.2f} FPS  (~{one_pct_mean_ms:.3f} ms)")
        print(f"  99th pctile (ms):       {p99_ms:.3f}")
        print("-" * 52)
        print("", flush=True)

        record = {
            "schema_version": 1,
            "tool": "perf_stress_test",
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "units_total": total_units,
            "units_heroes": n_h,
            "units_enemies": n_e,
            "warmup_frames": warmup_frames,
            "measured_frames": measure_frames,
            "avg_frame_ms": round(avg_ms, 6),
            "min_frame_ms": round(min_ms, 6),
            "max_frame_ms": round(max_ms, 6),
            "avg_fps": round(avg_fps, 4),
            "one_percent_low_mean_ms": round(one_pct_mean_ms, 6),
            "one_percent_low_fps": round(one_pct_low_fps, 4),
            "p99_frame_ms": round(p99_ms, 6),
        }
        _write_json_record(record=record, out_path=json_out)

        try:
            pygame.quit()
        except Exception:
            pass
        from ursina import application

        application.quit()

    def perf_update() -> None:
        snapshot = _make_snapshot(sim)
        idx = frame_idx[0]
        t0 = time.perf_counter()
        renderer.update(snapshot)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if idx >= warmup_frames:
            samples_ms.append(dt_ms)
        frame_idx[0] = idx + 1
        if frame_idx[0] >= total_frames:
            _finalize_and_exit()

    import __main__

    __main__.update = perf_update
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
