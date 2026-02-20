"""
WK17 memory leak profile: run game for 5 minutes (--no-llm) and compare tracemalloc snapshots.

Usage:
  python tools/memory_profile.py [--duration 300] [--out report.md]

Must set SDL_VIDEODRIVER=dummy (and SDL_AUDIODRIVER=dummy) before importing pygame.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from pathlib import Path

# Headless so we can run 5 min without a window
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import tracemalloc  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run_game_for_seconds(engine, duration_sec: float) -> None:
    """Run engine.run() in this thread; caller will set engine.running = False after duration_sec."""
    try:
        engine.run()
    except Exception as e:
        print(f"[memory_profile] Game thread error: {e}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Profile game memory over a timed --no-llm run")
    ap.add_argument("--duration", type=float, default=300.0, help="Run duration in seconds (default 300)")
    ap.add_argument("--out", type=str, default="", help="Write report to this path (default: stdout + docs/memory_leak_wk17.md)")
    ns = ap.parse_args()

    duration = max(60.0, ns.duration)
    out_path = Path(ns.out) if ns.out else PROJECT_ROOT / "docs" / "memory_leak_wk17.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[memory_profile] Starting tracemalloc and game (--no-llm) for {duration:.0f}s...")
    tracemalloc.start(25)

    # Import after env so pygame uses dummy drivers
    from game.engine import GameEngine  # noqa: E402
    from ai.basic_ai import BasicAI  # noqa: E402

    game = GameEngine(early_nudge_mode=None)
    game.ai_controller = BasicAI(llm_brain=None)

    snapshot_start = tracemalloc.take_snapshot()
    thread = threading.Thread(target=run_game_for_seconds, args=(game, duration))
    thread.start()

    time.sleep(duration)
    game.running = False
    thread.join(timeout=10.0)
    if thread.is_alive():
        print("[memory_profile] WARNING: Game thread did not exit within 10s", file=sys.stderr)

    snapshot_end = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Compare: what grew the most
    top_stats = snapshot_end.compare_to(snapshot_start, "lineno")
    lines = []
    lines.append("# WK17 Memory Leak Profile Report")
    lines.append("")
    lines.append(f"Run: {duration:.0f}s headless, --no-llm. Tracemalloc comparison (end vs start).")
    lines.append("")
    lines.append("## Top 40 allocations by size increase (traceback)")
    lines.append("")
    for i, stat in enumerate(top_stats[:40], 1):
        lines.append(f"{i}. **{stat.size_diff / 1024:.1f} KiB** ({stat.count_diff} blocks)")
        for line in stat.traceback.format():
            lines.append(f"   {line}")
        lines.append("")

    # Also by count (many small allocations)
    by_count = sorted(
        [s for s in top_stats if s.count_diff > 0],
        key=lambda s: -s.count_diff,
    )
    lines.append("## Top 20 by block count increase")
    lines.append("")
    for i, stat in enumerate(by_count[:20], 1):
        lines.append(f"{i}. **+{stat.count_diff} blocks**, +{stat.size_diff / 1024:.1f} KiB — {stat.traceback.format()[0].strip()}")
    lines.append("")

    report = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[memory_profile] Report written to {out_path}")

    # Print short summary to stdout
    total_diff = sum(s.size_diff for s in top_stats if s.size_diff > 0)
    print(f"[memory_profile] Total allocated size increase: {total_diff / (1024*1024):.2f} MiB")
    print("[memory_profile] Top 5 by size:")
    for stat in top_stats[:5]:
        print(f"  +{stat.size_diff/1024:.0f} KiB  {stat.traceback.format()[0].strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
