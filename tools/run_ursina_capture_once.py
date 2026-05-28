#!/usr/bin/env python3
"""
Run Ursina once, wait for terrain/HUD, save one PNG, then exit.

Uses ``KINGDOM_URSINA_AUTO_EXIT_SEC`` + ``KINGDOM_URSINA_AUTO_SCREENSHOT_PATH`` (see
``game/graphics/ursina_app.py``). Naming matches F12 via ``tools/ursina_screenshot``.

Examples::

    python tools/run_ursina_capture_once.py
    python tools/run_ursina_capture_once.py --seconds 8 --subdir wk32_nature --stem meadow_v2
    python tools/run_ursina_capture_once.py --scenario wk61_hold_g_tax_overlay --ticks 5400 --out docs/screenshots/wk61_r10_hold_g
    python tools/run_ursina_capture_once.py --no-screenshot
        # only auto-exit (debug)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_RUNNER = PROJECT_ROOT / ".ursina_capture_runner.py"


def _out_to_subdir(out: str) -> str:
    raw = out.replace("\\", "/").strip("/")
    prefix = "docs/screenshots/"
    if raw.startswith(prefix):
        return raw[len(prefix) :].strip("/")
    return raw


def _run_with_capture_patch(
    *,
    patch_path: Path,
    env: dict[str, str],
    no_llm: bool,
    provider: str,
) -> subprocess.CompletedProcess[str]:
    rel_patch = patch_path.relative_to(PROJECT_ROOT).as_posix()
    provider_literal = repr(str(provider or ""))
    runner_src = textwrap.dedent(
        f"""
        import importlib.util
        import sys
        from pathlib import Path

        ROOT = Path(__file__).resolve().parent
        sys.path.insert(0, str(ROOT))
        patch_path = ROOT / "{rel_patch}"
        spec = importlib.util.spec_from_file_location("wk61_capture_patch", patch_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        sys.argv = [str(ROOT / "main.py"), "--renderer", "ursina"]
        if {no_llm!r}:
            sys.argv.append("--no-llm")
        elif {provider_literal}:
            sys.argv.extend(["--provider", {provider_literal}])
        import main as kingdom_main

        kingdom_main.main()
        """
    ).strip()
    CAPTURE_RUNNER.write_text(runner_src, encoding="utf-8")
    try:
        cmd = [sys.executable, str(CAPTURE_RUNNER)]
        print(f"[capture-once] Running patched runner: {' '.join(cmd)}", flush=True)
        return subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    finally:
        CAPTURE_RUNNER.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ursina one-shot PNG capture then exit.")
    ap.add_argument(
        "--seconds",
        type=float,
        default=None,
        help="Seconds after first frame before capture+exit (default: 6, or ticks/60 when --scenario set)",
    )
    ap.add_argument(
        "--scenario",
        type=str,
        default="",
        help="Named Ursina capture scenario from tools/screenshot_scenarios.py",
    )
    ap.add_argument(
        "--ticks",
        type=int,
        default=None,
        help="Sim ticks for scenario timing (converted to seconds at 60 Hz when --seconds omitted)",
    )
    ap.add_argument(
        "--out",
        type=str,
        default="",
        help="Output directory or subdir under docs/screenshots/ (e.g. docs/screenshots/wk61_r10_hold_g)",
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
    ap.add_argument(
        "--reveal-map",
        action="store_true",
        help="Auto-trigger /revealmap once on first frame (sets KINGDOM_URSINA_REVEAL_ON_START=1)",
    )
    ns = ap.parse_args()

    scenario_cfg: dict[str, object] | None = None
    patch_path: Path | None = None
    if ns.scenario:
        sys.path.insert(0, str(PROJECT_ROOT))
        from tools.screenshot_scenarios import get_ursina_capture_scenario

        scenario_cfg = get_ursina_capture_scenario(ns.scenario)
        patch_rel = str(scenario_cfg.get("patch_path", "") or "").strip()
        if patch_rel:
            patch_path = PROJECT_ROOT / patch_rel

    ticks = ns.ticks
    if ticks is None and scenario_cfg is not None:
        ticks = int(scenario_cfg.get("default_ticks") or 0) or None

    seconds = ns.seconds
    if seconds is None:
        if ticks is not None:
            seconds = float(ticks) / 60.0
        else:
            seconds = 6.0

    subdir = ns.subdir
    if ns.out.strip():
        subdir = _out_to_subdir(ns.out.strip())
    elif scenario_cfg is not None:
        subdir = str(scenario_cfg.get("default_out_subdir") or subdir)

    stem = ns.stem
    if not stem and scenario_cfg is not None:
        stem = str(scenario_cfg.get("stem") or "")

    no_llm = bool(ns.no_llm or scenario_cfg is not None)

    env = os.environ.copy()
    env["KINGDOM_URSINA_AUTO_EXIT_SEC"] = str(seconds)
    if subdir:
        env["KINGDOM_SCREENSHOT_SUBDIR"] = subdir
    if stem:
        env["KINGDOM_SCREENSHOT_STEM"] = stem
    if ns.fps_probe:
        env["KINGDOM_URSINA_FPS_PROBE"] = "1"
        env["KINGDOM_URSINA_FPS_PROBE_WARMUP_SEC"] = str(ns.fps_warmup_sec)
    if ns.hero_fps_probe_count:
        env["KINGDOM_URSINA_HERO_FPS_PROBE_COUNT"] = str(max(0, ns.hero_fps_probe_count))
    if ns.disable_neutral_spawn:
        env["KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN"] = "1"
    if ns.reveal_map:
        env["KINGDOM_URSINA_REVEAL_ON_START"] = "1"
    if scenario_cfg is not None:
        for key, value in dict(scenario_cfg.get("env") or {}).items():
            env[str(key)] = str(value)

    path: str | None = None
    if not ns.no_screenshot:
        sys.path.insert(0, str(PROJECT_ROOT))
        from tools.ursina_screenshot import next_auto_screenshot_path_for

        path = next_auto_screenshot_path_for(
            subdir=subdir or None,
            stem=stem or None,
        )
        env["KINGDOM_URSINA_AUTO_SCREENSHOT_PATH"] = path
        print(f"[capture-once] Will write: {path}", flush=True)
    else:
        print("[capture-once] Auto-exit only (no screenshot path)", flush=True)

    if patch_path is not None:
        if not patch_path.is_file():
            print(f"[capture-once] Missing capture patch: {patch_path}", flush=True)
            return 1
        r = _run_with_capture_patch(
            patch_path=patch_path,
            env=env,
            no_llm=no_llm,
            provider=str(ns.provider or ""),
        )
    else:
        cmd = [sys.executable, str(PROJECT_ROOT / "main.py"), "--renderer", "ursina"]
        if no_llm:
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
