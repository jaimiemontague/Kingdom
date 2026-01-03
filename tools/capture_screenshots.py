"""
Deterministic screenshot runner (Visual Snapshot System).

Outputs:
- <out>/manifest.json
- <out>/*.png

Constraints:
- Deterministic: uses sim seed and sim ticks; avoids wall-clock for sim time.
- Headless-capable: can run with SDL dummy video driver.
- No LLM usage.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import hashlib
from pathlib import Path


# Headless-friendly defaults (safe on Windows + CI).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from game.engine import GameEngine  # noqa: E402
from game.sim.determinism import set_sim_seed  # noqa: E402
from game.sim.timebase import set_sim_now_ms  # noqa: E402
from ai.basic_ai import BasicAI  # noqa: E402

from tools.screenshot_scenarios import get_scenario, Shot  # noqa: E402


SIZE_RE = re.compile(r"^(\d+)x(\d+)$", re.IGNORECASE)


def _parse_size(s: str) -> tuple[int, int]:
    m = SIZE_RE.match(str(s).strip())
    if not m:
        raise ValueError("size must be like 1920x1080")
    return int(m.group(1)), int(m.group(2))


def _set_camera_center(engine: GameEngine, world_x: float, world_y: float) -> None:
    win_w = int(getattr(engine, "window_width", engine.screen.get_width()))
    win_h = int(getattr(engine, "window_height", engine.screen.get_height()))
    z = float(getattr(engine, "zoom", 1.0) or 1.0)
    view_w = win_w / max(1e-6, z)
    view_h = win_h / max(1e-6, z)
    engine.camera_x = float(world_x) - view_w / 2.0
    engine.camera_y = float(world_y) - view_h / 2.0
    if hasattr(engine, "clamp_camera"):
        engine.clamp_camera()


def _configure_engine_surface(engine: GameEngine, width: int, height: int) -> None:
    # For deterministic screenshots we prefer a known surface size (even if game defaults differ).
    flags = 0
    screen = pygame.display.set_mode((int(width), int(height)), flags)
    engine.screen = screen
    engine.window_width = int(width)
    engine.window_height = int(height)
    # Recreate cached surfaces sized to window.
    engine._scaled_surface = pygame.Surface((int(width), int(height)))
    engine._pause_overlay = pygame.Surface((int(width), int(height)), pygame.SRCALPHA)
    engine._pause_overlay.fill((0, 0, 0, 128))
    # Reset view surface so it gets resized on demand.
    engine._view_surface = None
    engine._view_surface_size = (0, 0)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic screenshot capture runner")
    ap.add_argument("--scenario", type=str, required=True, help="scenario name (e.g., building_catalog)")
    ap.add_argument("--seed", type=int, default=3, help="deterministic seed")
    ap.add_argument("--out", type=str, required=True, help="output directory (e.g., docs/screenshots/test_run/)")
    ap.add_argument("--size", type=str, default="1920x1080", help="capture size like 1920x1080")
    ap.add_argument("--ticks", type=int, default=120, help="ticks to advance (paused) before each capture (sim-time only)")
    ap.add_argument("--dt", type=float, default=1.0 / 60.0, help="dt seconds per tick (sim-time)")
    ns = ap.parse_args()

    out_dir = (PROJECT_ROOT / ns.out).resolve() if not Path(ns.out).is_absolute() else Path(ns.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_dir_name = out_dir.name

    width, height = _parse_size(ns.size)

    # Deterministic RNG seed (for hero names, world-gen substreams, etc).
    set_sim_seed(int(ns.seed))

    pygame.init()
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_mode((1, 1))

    # Build engine + disable LLM.
    engine = GameEngine()
    engine.ai_controller = BasicAI(llm_brain=None)

    # Use stable capture surface size.
    _configure_engine_surface(engine, width, height)

    # Keep simulation deterministic: drive sim-time via ticks; avoid wall-clock.
    set_sim_now_ms(0)

    # Build scenario shots (this mutates engine state).
    shots: list[Shot] = get_scenario(engine, str(ns.scenario), seed=int(ns.seed))

    outputs = []
    for idx, shot in enumerate(shots):
        # Advance sim time deterministically so timers/animations/VFX can settle.
        #
        # IMPORTANT: We must NOT rely on engine.paused updates here, because `GameEngine.update()`
        # early-returns when paused. That would prevent scenarios like `ranged_projectiles` from
        # ever emitting VFX. We still drive sim time deterministically via set_sim_now_ms(...).
        was_paused = bool(getattr(engine, "paused", False))
        engine.paused = False
        for t in range(int(ns.ticks) + int(getattr(shot, "ticks", 0))):
            set_sim_now_ms(int((t * float(ns.dt)) * 1000.0))
            try:
                engine.update(float(ns.dt))
            except Exception:
                # Update should not be required for screenshotting; don't crash capture on non-critical issues.
                pass
        # Restore pause state (best-effort) so we don't leak state across shots.
        engine.paused = was_paused
        engine.zoom = float(getattr(shot, "zoom", 1.0) or 1.0)
        _set_camera_center(engine, float(shot.center_x), float(shot.center_y))

        # Reset per-shot UI/selection state to avoid cross-shot contamination.
        # Scenarios can override via Shot.apply().
        # For captures, hide UI by default (world-space visuals like VFX/debris are the focus).
        try:
            engine.screenshot_hide_ui = True
        except Exception:
            pass
        try:
            engine.selected_hero = None
        except Exception:
            pass
        try:
            engine.selected_building = None
        except Exception:
            pass
        try:
            if hasattr(engine, "debug_panel"):
                engine.debug_panel.visible = False
        except Exception:
            pass

        # Apply any per-shot state mutations (selection/UI toggles/etc).
        apply_fn = getattr(shot, "apply", None)
        if callable(apply_fn):
            try:
                apply_fn(engine)
            except Exception:
                pass

        # Render once and save.
        engine.render()
        filename = str(getattr(shot, "filename"))
        path = out_dir / filename
        pygame.image.save(engine.screen, str(path))

        outputs.append(
            {
                "index": idx,
                "filename": filename,
                # Keep the manifest stable across machines: never embed absolute paths.
                # Consumers should resolve this relative to the run directory.
                "relpath": filename,
                "label": str(getattr(shot, "label", filename)),
                "scenario": str(ns.scenario),
                "seed": int(ns.seed),
                "size": {"w": int(width), "h": int(height)},
                "camera": {"center_x": float(shot.center_x), "center_y": float(shot.center_y), "zoom": float(engine.zoom)},
                "sha256": _sha256_file(path),
                "meta": {} if getattr(shot, "meta", None) is None else dict(getattr(shot, "meta")),
            }
        )

    manifest = {
        "schema_version": "1.1",
        "run": {
            "scenario": str(ns.scenario),
            "seed": int(ns.seed),
            "run_dir": str(run_dir_name),
            "size": {"w": int(width), "h": int(height)},
            "ticks_per_shot": int(ns.ticks),
            "dt": float(ns.dt),
        },
        "outputs": outputs,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[capture] Wrote {len(outputs)} PNG(s) to {out_dir}")
    print(f"[capture] manifest={out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


