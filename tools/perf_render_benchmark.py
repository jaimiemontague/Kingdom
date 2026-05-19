"""
Rendering performance benchmark: FPS before and after /revealmap.

Boots the full Ursina game (no LLM), waits for terrain to settle, samples FPS
for a fixed window ("before"), programmatically triggers /revealmap, then
samples FPS for another fixed window ("after"). Finally, prints entity counts
and a PASS/FAIL verdict, then exits.

Usage (PowerShell, from project root):
    python tools/perf_render_benchmark.py
    python tools/perf_render_benchmark.py --csv perf_render.csv
    python tools/perf_render_benchmark.py --warmup 5 --measure 10

Output format (parsed by orchestrator agents — do not change):
    [perf-render] === BEFORE REVEAL ===
    [perf-render] samples=N avg_fps=XX.X min_fps=XX.X p10=XX.X p50=XX.X p90=XX.X
    [perf-render] === AFTER REVEAL ===
    [perf-render] samples=N avg_fps=XX.X min_fps=XX.X p10=XX.X p50=XX.X p90=XX.X
    [perf-render] === ENTITY COUNTS ===
    [perf-render] tracked_props=NNNN tree_entities=NNNN static_batches=NNNN
                  chunks=NNN enabled_props=NNNN enabled_outside_visible_chunks=NNN
                  visible_chunks=NNN
    [perf-render] === RESULT: PASS/FAIL (target: 45 FPS post-reveal, stretch: 55 FPS) ===
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
import time as pytime
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.chdir(str(PROJECT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Pygame backend stays headless even though Ursina opens a real GL window.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Ursina defaults `application.asset_folder` to dirname(sys.argv[0]) which is
# `tools/` when this script runs directly. Force the project root so Entity(model=...)
# and the Panda3D model path resolve glb/obj assets correctly (otherwise the cold-start
# spits ~13k "missing model" warnings and crawls through the model_path fallback).
import ursina.application as _ursina_application  # noqa: E402

_ursina_application.asset_folder = PROJECT_ROOT
_ursina_application.scenes_folder = PROJECT_ROOT / "scenes"
_ursina_application.scripts_folder = PROJECT_ROOT / "scripts"
_ursina_application.fonts_folder = PROJECT_ROOT / "fonts"
_ursina_application.textures_compressed_folder = PROJECT_ROOT / "textures_compressed"
_ursina_application.models_compressed_folder = PROJECT_ROOT / "models_compressed"
try:
    from panda3d.core import getModelPath as _get_model_path
    _get_model_path().append_path(str(PROJECT_ROOT.resolve()))
except Exception:
    pass

import pygame  # noqa: E402
pygame.init()


# Targets (post-fix). Below is "FAIL", at/above is "PASS"; stretch label only.
_TARGET_FPS = 45.0
_STRETCH_FPS = 55.0


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    # Nearest-rank percentile (sufficient for benchmark reporting).
    idx = max(0, min(n - 1, int(round(p * (n - 1)))))
    return float(sorted_values[idx])


def _summarize(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"samples": 0, "avg": 0.0, "min": 0.0, "p10": 0.0, "p50": 0.0, "p90": 0.0}
    s = sorted(samples)
    return {
        "samples": len(samples),
        "avg": float(statistics.mean(samples)),
        "min": float(min(samples)),
        "p10": _percentile(s, 0.10),
        "p50": _percentile(s, 0.50),
        "p90": _percentile(s, 0.90),
    }


def _do_reveal(viewer) -> None:
    """Reveal logic copied verbatim from game/engine.py:318-330 (/revealmap)."""
    from game.world import Visibility

    eng = viewer.engine
    world = eng.world
    world.fog_disabled = True
    for ty in range(world.height):
        for tx in range(world.width):
            world.visibility[ty][tx] = Visibility.VISIBLE
    world._currently_visible = []
    sim = getattr(eng, "sim", eng)
    sim._fog_revealers_snapshot = None
    eng._fog_revision = getattr(eng, "_fog_revision", 0) + 100
    for poi in getattr(sim, "pois", []):
        if not getattr(poi, "is_discovered", False):
            poi.is_discovered = True


def _print_stage_profile(viewer, *, samples_to_drop_warmup: int = 0) -> None:
    """WK58 W5 (Agent 10): if KINGDOM_URSINA_STAGE_PROFILE=1, print per-substage ms breakdown.

    Reads renderer._stage_ms_samples which is populated by the env-flag-gated
    instrumentation in ursina_renderer.update(). Skips the first ``samples_to_drop_warmup``
    frames to exclude one-time setup costs (the 'first frame after reveal' spike).
    """
    if os.environ.get("KINGDOM_URSINA_STAGE_PROFILE", "0") != "1":
        return
    renderer = getattr(viewer, "renderer", None)
    if renderer is None:
        return
    raw = getattr(renderer, "_stage_ms_samples", None)
    if not raw:
        return
    print("[perf-render] === STAGE PROFILE (renderer.update sub-stages, ms/frame) ===", flush=True)
    print("[perf-render] stage frames p50_ms p90_ms p99_ms max_ms mean_ms", flush=True)
    # Sort by p50_ms descending so the hot stages bubble to the top.
    rows = []
    for name in sorted(raw.keys()):
        vals = list(raw[name])
        # Drop a few warmup samples per stage to avoid one-time setup spikes.
        if samples_to_drop_warmup > 0 and len(vals) > samples_to_drop_warmup * 2:
            vals = vals[samples_to_drop_warmup:]
        if not vals:
            continue
        vs = sorted(vals)
        n = len(vs)
        p50 = vs[max(0, int(n * 0.50) - 1)]
        p90 = vs[max(0, int(n * 0.90) - 1)]
        p99 = vs[max(0, int(n * 0.99) - 1)]
        mx = vs[-1]
        mean = sum(vs) / n
        rows.append((p50, n, name, p90, p99, mx, mean))
    rows.sort(reverse=True)  # by p50 desc
    for p50, n, name, p90, p99, mx, mean in rows:
        print(
            "[perf-render-stage] {n:34s} frames={frames:4d} p50={p50:7.3f} p90={p90:7.3f} p99={p99:7.3f} max={mx:8.3f} mean={mn:7.3f}".format(
                n=name, frames=n, p50=p50, p90=p90, p99=p99, mx=mx, mn=mean,
            ),
            flush=True,
        )


def _collect_entity_counts(viewer) -> dict[str, int]:
    """Read tracked / enabled / chunk counts from the live renderer + terrain fog collab."""
    renderer = getattr(viewer, "renderer", None)
    if renderer is None:
        return {
            "tracked_props": 0,
            "tree_entities": 0,
            "static_batches": 0,
            "chunks": 0,
            "enabled_props": 0,
            "enabled_outside_visible_chunks": 0,
            "visible_chunks": 0,
        }

    terrain_fog = getattr(renderer, "_terrain_fog", None)
    tracked = getattr(renderer, "_visibility_gated_terrain", []) or []
    trees = getattr(renderer, "_tree_entities", {}) or {}

    chunks = getattr(terrain_fog, "_terrain_chunks", {}) if terrain_fog else {}
    visible_chunks = getattr(terrain_fog, "_visible_chunks", set()) if terrain_fog else set()

    # Build tile -> chunk lookup so we can count enabled props outside visible chunks.
    chunk_size = 16
    try:
        from game.graphics.ursina_terrain_fog_collab import TERRAIN_CHUNK_SIZE
        chunk_size = int(TERRAIN_CHUNK_SIZE)
    except Exception:
        pass

    enabled_props = 0
    enabled_outside = 0
    for entry in tracked:
        try:
            ent, tx, ty = entry
        except Exception:
            continue
        if bool(getattr(ent, "enabled", False)):
            enabled_props += 1
            chunk_key = (int(tx) // chunk_size, int(ty) // chunk_size)
            if chunk_key not in visible_chunks:
                enabled_outside += 1

    # Static batch counter is optional (Phase 3 adds it).
    static_batches = int(getattr(terrain_fog, "_static_terrain_batches", 0) or 0) if terrain_fog else 0

    return {
        "tracked_props": len(tracked),
        "tree_entities": len(trees),
        "static_batches": static_batches,
        "chunks": len(chunks),
        "enabled_props": int(enabled_props),
        "enabled_outside_visible_chunks": int(enabled_outside),
        "visible_chunks": len(visible_chunks),
    }


def _print_report(
    *,
    before: dict[str, float],
    after: dict[str, float],
    counts: dict[str, int],
) -> bool:
    """Print the labeled blocks. Returns True if after_avg >= target."""
    def _f1(v: float) -> str:
        return f"{float(v):.1f}"

    print("[perf-render] === BEFORE REVEAL ===", flush=True)
    print(
        "[perf-render] samples={samples} avg_fps={avg} min_fps={mn} p10={p10} p50={p50} p90={p90}".format(
            samples=int(before["samples"]),
            avg=_f1(before["avg"]),
            mn=_f1(before["min"]),
            p10=_f1(before["p10"]),
            p50=_f1(before["p50"]),
            p90=_f1(before["p90"]),
        ),
        flush=True,
    )
    print("[perf-render] === AFTER REVEAL ===", flush=True)
    print(
        "[perf-render] samples={samples} avg_fps={avg} min_fps={mn} p10={p10} p50={p50} p90={p90}".format(
            samples=int(after["samples"]),
            avg=_f1(after["avg"]),
            mn=_f1(after["min"]),
            p10=_f1(after["p10"]),
            p50=_f1(after["p50"]),
            p90=_f1(after["p90"]),
        ),
        flush=True,
    )
    print("[perf-render] === ENTITY COUNTS ===", flush=True)
    print(
        "[perf-render] tracked_props={tp} tree_entities={te} static_batches={sb} "
        "chunks={ch} enabled_props={ep} enabled_outside_visible_chunks={eo} visible_chunks={vc}".format(
            tp=counts["tracked_props"],
            te=counts["tree_entities"],
            sb=counts["static_batches"],
            ch=counts["chunks"],
            ep=counts["enabled_props"],
            eo=counts["enabled_outside_visible_chunks"],
            vc=counts["visible_chunks"],
        ),
        flush=True,
    )
    after_avg = float(after.get("avg", 0.0))
    verdict = "PASS" if after_avg >= _TARGET_FPS else "FAIL"
    print(
        "[perf-render] === RESULT: {v} (target: {t:.0f} FPS post-reveal, stretch: {s:.0f} FPS) ===".format(
            v=verdict, t=_TARGET_FPS, s=_STRETCH_FPS
        ),
        flush=True,
    )
    return after_avg >= _TARGET_FPS


def _append_csv(
    csv_path: Path,
    *,
    before: dict[str, float],
    after: dict[str, float],
    counts: dict[str, int],
) -> None:
    cols = [
        "timestamp",
        "before_avg",
        "before_min",
        "before_p50",
        "after_avg",
        "after_min",
        "after_p50",
        "tracked_props",
        "tree_entities",
        "static_batches",
        "enabled_props",
        "enabled_outside_visible_chunks",
        "visible_chunks",
    ]
    write_header = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(cols)
        w.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                round(float(before["avg"]), 3),
                round(float(before["min"]), 3),
                round(float(before["p50"]), 3),
                round(float(after["avg"]), 3),
                round(float(after["min"]), 3),
                round(float(after["p50"]), 3),
                counts["tracked_props"],
                counts["tree_entities"],
                counts["static_batches"],
                counts["enabled_props"],
                counts["enabled_outside_visible_chunks"],
                counts["visible_chunks"],
            ]
        )
    print(f"[perf-render] wrote {csv_path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Ursina rendering benchmark (FPS before/after /revealmap)")
    ap.add_argument(
        "--warmup",
        type=float,
        default=5.0,
        help="seconds to let terrain settle before sampling 'before' (default: 5)",
    )
    ap.add_argument(
        "--measure",
        type=float,
        default=8.0,
        help="seconds to sample each state, before and after reveal (default: 8)",
    )
    ap.add_argument(
        "--csv",
        type=str,
        default="",
        help="optional CSV file to append one summary row to",
    )
    ns = ap.parse_args()

    warmup_sec = max(0.5, float(ns.warmup))
    measure_sec = max(1.0, float(ns.measure))
    reveal_at = warmup_sec + measure_sec
    exit_at = reveal_at + measure_sec + 2.0  # +2s lets the reveal frame settle before quitting

    # Import after sys.path / chdir adjustments — UrsinaApp does its own pygame.init + Ursina().
    from ai.basic_ai import BasicAI
    from game.graphics.ursina_app import UrsinaApp

    def _make_ai() -> BasicAI:
        return BasicAI(llm_brain=None)

    print(
        f"[perf-render] boot UrsinaApp (warmup={warmup_sec}s, measure={measure_sec}s, "
        f"reveal_at={reveal_at}s, exit_at={exit_at}s)",
        flush=True,
    )
    viewer = UrsinaApp(ai_controller_factory=_make_ai)

    # Wire the AI brain event bus the same way main.py does, in case providers care.
    try:
        ai_ctrl = viewer.engine.ai_controller
        llm = getattr(ai_ctrl, "llm_brain", None)
        if llm is not None and hasattr(llm, "set_event_bus") and hasattr(viewer.engine, "event_bus"):
            llm.set_event_bus(viewer.engine.event_bus)
    except Exception:
        pass

    state: dict = {
        "phase": "warmup",          # warmup -> before -> after -> done
        "elapsed": 0.0,
        "before_samples": [],
        "after_samples": [],
        "reveal_triggered": False,
        "counts": None,
        "exit_initiated": False,
        "last_phase_announced": None,
        "tick_count": 0,
    }

    original_tick = viewer.engine.tick_simulation

    def hooked_tick(dt: float):
        result = original_tick(dt)
        try:
            d = float(dt or 0.0)
        except Exception:
            d = 0.0

        state["elapsed"] += d
        state["tick_count"] += 1

        # Instantaneous FPS for this frame.
        if d > 1e-9:
            inst_fps = 1.0 / d
        else:
            inst_fps = 0.0

        elapsed = state["elapsed"]

        if elapsed < warmup_sec:
            state["phase"] = "warmup"
        elif elapsed < reveal_at and inst_fps > 0.0:
            state["phase"] = "before"
            state["before_samples"].append(inst_fps)
        elif not state["reveal_triggered"] and elapsed >= reveal_at:
            state["reveal_triggered"] = True
            state["phase"] = "reveal"
            # WK58 W5 (Agent 10): snapshot the pre-reveal stage sample counts so we
            # can split before/after windows on the stage profile print at exit.
            try:
                renderer = getattr(viewer, "renderer", None)
                raw = getattr(renderer, "_stage_ms_samples", None) if renderer else None
                if raw is not None:
                    state["stage_counts_at_reveal"] = {k: len(v) for k, v in raw.items()}
            except Exception:
                pass
            try:
                _do_reveal(viewer)
                print(f"[perf-render] reveal triggered at elapsed={elapsed:.2f}s", flush=True)
            except Exception as exc:
                print(f"[perf-render] reveal FAILED: {exc}", flush=True)
        elif state["reveal_triggered"] and elapsed < (reveal_at + measure_sec) and inst_fps > 0.0:
            state["phase"] = "after"
            state["after_samples"].append(inst_fps)

        # Announce phase transitions so anyone tailing the log can see progress.
        if state["phase"] != state["last_phase_announced"] and state["phase"] in (
            "warmup", "before", "after"
        ):
            print(
                f"[perf-render] phase={state['phase']} elapsed={elapsed:.2f}s "
                f"tick_count={state['tick_count']} inst_fps={inst_fps:.1f}",
                flush=True,
            )
            state["last_phase_announced"] = state["phase"]

        if elapsed >= exit_at and not state["exit_initiated"]:
            state["exit_initiated"] = True
            state["counts"] = _collect_entity_counts(viewer)

            before = _summarize(state["before_samples"])
            after = _summarize(state["after_samples"])
            counts = state["counts"]

            _print_report(before=before, after=after, counts=counts)

            # WK58 W5 (Agent 10): per-stage profile print. Splits into before/after by
            # slicing samples at the reveal cutoff captured above. Off unless the
            # KINGDOM_URSINA_STAGE_PROFILE env var is set in the launching shell.
            try:
                renderer = getattr(viewer, "renderer", None)
                raw = getattr(renderer, "_stage_ms_samples", None) if renderer else None
                if raw and os.environ.get("KINGDOM_URSINA_STAGE_PROFILE", "0") == "1":
                    cut = state.get("stage_counts_at_reveal") or {}
                    print("[perf-render] === STAGE PROFILE (renderer.update sub-stages, ms/frame, BEFORE reveal) ===", flush=True)
                    # Build before/after sub-dicts so the same printer can render two tables.
                    class _Stub:
                        pass
                    stub = _Stub()
                    stub_renderer = _Stub()
                    stub_renderer._stage_ms_samples = {
                        k: list(v[:cut.get(k, 0)]) for k, v in raw.items()
                    }
                    stub.renderer = stub_renderer
                    _print_stage_profile(stub, samples_to_drop_warmup=2)

                    print("[perf-render] === STAGE PROFILE (renderer.update sub-stages, ms/frame, AFTER reveal) ===", flush=True)
                    stub2 = _Stub()
                    stub2_renderer = _Stub()
                    stub2_renderer._stage_ms_samples = {
                        k: list(v[cut.get(k, 0):]) for k, v in raw.items()
                    }
                    stub2.renderer = stub2_renderer
                    # Drop the first 3 post-reveal frames to skip the well-known initial spike
                    # (Wave 2 backlog: ~1.3 FPS first post-reveal frame from full-mask re-apply).
                    _print_stage_profile(stub2, samples_to_drop_warmup=3)
            except Exception as _exc:
                print(f"[perf-render] stage profile print FAILED: {_exc}", flush=True)

            if ns.csv:
                try:
                    _append_csv(Path(ns.csv), before=before, after=after, counts=counts)
                except Exception as exc:
                    print(f"[perf-render] CSV write FAILED: {exc}", flush=True)

            # Quit Ursina cleanly.
            try:
                from ursina import application
                application.quit()
            except Exception:
                # Last-resort exit so the process does not hang.
                pytime.sleep(0.05)
                os._exit(0)

        return result

    viewer.engine.tick_simulation = hooked_tick  # type: ignore[method-assign]

    # Drive the Ursina main loop. The hooked tick_simulation will eventually call
    # application.quit(), which makes viewer.run() return.
    viewer.run()

    # Defensive: if no after-samples (e.g. early crash), exit non-zero.
    if not state["after_samples"]:
        print("[perf-render] WARN: no after-samples collected (early exit or no frames).", flush=True)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
