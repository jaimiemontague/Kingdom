#!/usr/bin/env python3
"""
Run Ursina once, wait for terrain/HUD, save one PNG, then exit.

Uses ``KINGDOM_URSINA_AUTO_EXIT_SEC`` + ``KINGDOM_URSINA_AUTO_SCREENSHOT_PATH`` (see
``game/graphics/ursina_app.py``). Naming matches F12 via ``tools/ursina_screenshot``.

Examples::

    python tools/run_ursina_capture_once.py
    python tools/run_ursina_capture_once.py --seconds 8 --subdir wk32_nature --stem meadow_v2
    python tools/run_ursina_capture_once.py --no-screenshot
        # only auto-exit (debug)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Ursina one-shot PNG capture then exit.")
    ap.add_argument(
        "--seconds",
        type=float,
        default=6.0,
        help="Seconds after first frame before capture+exit (default: 6)",
    )
    ap.add_argument(
        "--subdir",
        type=str,
        default="wk32_nature",
        help="KINGDOM_SCREENSHOT_SUBDIR under docs/screenshots/ (default: wk32_nature)",
    )
    ap.add_argument(
        "--stem",
        type=str,
        default="",
        help="KINGDOM_SCREENSHOT_STEM filename prefix (default: ursina)",
    )
    ap.add_argument(
        "--no-llm",
        action="store_true",
        help="Pass --no-llm to main.py",
    )
    ap.add_argument(
        "--provider",
        type=str,
        default="",
        help="Optional LLM provider to pass through to main.py (for example: mock)",
    )
    ap.add_argument(
        "--no-screenshot",
        action="store_true",
        help="Only auto-exit (no PNG); for debugging startup",
    )
    ap.add_argument(
        "--fps-probe",
        action="store_true",
        help="Print Ursina FPS stats before auto-exit",
    )
    ap.add_argument(
        "--fps-warmup-sec",
        type=float,
        default=2.0,
        help="Seconds to skip before FPS sample collection (default: 2)",
    )
    ap.add_argument(
        "--hero-fps-probe-count",
        type=int,
        default=0,
        help="Spawn a warrior guild plus this many warriors before startup FPS probe",
    )
    ap.add_argument(
        "--disable-neutral-spawn",
        action="store_true",
        help="For hero FPS probes, prevent auto-spawned houses/farms from entering the measurement",
    )
    ns = ap.parse_args()

    env = os.environ.copy()
    env["KINGDOM_URSINA_AUTO_EXIT_SEC"] = str(ns.seconds)
    if ns.subdir:
        env["KINGDOM_SCREENSHOT_SUBDIR"] = ns.subdir
    if ns.stem:
        env["KINGDOM_SCREENSHOT_STEM"] = ns.stem
    if ns.fps_probe:
        env["KINGDOM_URSINA_FPS_PROBE"] = "1"
        env["KINGDOM_URSINA_FPS_PROBE_WARMUP_SEC"] = str(ns.fps_warmup_sec)
    if ns.hero_fps_probe_count:
        env["KINGDOM_URSINA_HERO_FPS_PROBE_COUNT"] = str(max(0, ns.hero_fps_probe_count))
    if ns.disable_neutral_spawn:
        env["KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN"] = "1"

    path: str | None = None
    if not ns.no_screenshot:
        sys.path.insert(0, str(PROJECT_ROOT))
        from tools.ursina_screenshot import next_auto_screenshot_path_for

        path = next_auto_screenshot_path_for(
            subdir=ns.subdir or None,
            stem=ns.stem or None,
        )
        env["KINGDOM_URSINA_AUTO_SCREENSHOT_PATH"] = path
        print(f"[capture-once] Will write: {path}", flush=True)
    else:
        print("[capture-once] Auto-exit only (no screenshot path)", flush=True)

    cmd = [sys.executable, str(PROJECT_ROOT / "main.py"), "--renderer", "ursina"]
    if ns.no_llm:
        cmd.append("--no-llm")
    elif ns.provider:
        cmd.extend(["--provider", ns.provider])

    print(f"[capture-once] Running: {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    if path and r.returncode == 0:
        print(f"[capture-once] Done. Open: {path}", flush=True)
    return int(r.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
