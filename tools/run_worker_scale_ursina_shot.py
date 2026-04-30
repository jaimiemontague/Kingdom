#!/usr/bin/env python3
"""
One Ursina launch: warrior + peasant beside castle, auto-screenshot, exit.

Uses ``KINGDOM_URSINA_WORKER_SCALE_SHOT`` (see ``game/graphics/ursina_app.py``) plus the same
auto-exit / screenshot env contract as ``tools/run_ursina_capture_once.py``.

From repo root (PowerShell):

  python tools/run_worker_scale_ursina_shot.py

Output path is printed; compare peasant vs warrior silhouette height on screen.
Tune ``URSINA_WORKER_BILLBOARD_BASE`` / ``KINGDOM_URSINA_WORKER_SCALE`` in config or env if needed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Ursina screenshot: warrior + peasant scale check.")
    ap.add_argument("--seconds", type=float, default=5.0, help="Seconds before capture+exit")
    ap.add_argument("--subdir", type=str, default="worker_scale_check", help="Under docs/screenshots/")
    ap.add_argument("--stem", type=str, default="peasant_vs_warrior", help="PNG filename prefix")
    ns = ap.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))
    from tools.ursina_screenshot import next_auto_screenshot_path_for

    path = next_auto_screenshot_path_for(subdir=ns.subdir or None, stem=ns.stem or None)
    env = os.environ.copy()
    env["KINGDOM_URSINA_WORKER_SCALE_SHOT"] = "1"
    env["KINGDOM_URSINA_AUTO_EXIT_SEC"] = str(ns.seconds)
    env["KINGDOM_URSINA_AUTO_SCREENSHOT_PATH"] = str(path)
    env["KINGDOM_SCREENSHOT_SUBDIR"] = ns.subdir
    env["KINGDOM_SCREENSHOT_STEM"] = ns.stem

    cmd = [sys.executable, str(PROJECT_ROOT / "main.py"), "--renderer", "ursina", "--no-llm"]
    print(f"[worker-scale-shot] Will write: {path}", flush=True)
    print(f"[worker-scale-shot] Running: {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    if r.returncode == 0:
        print(f"[worker-scale-shot] Done. Open: {path}", flush=True)
    return int(r.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
