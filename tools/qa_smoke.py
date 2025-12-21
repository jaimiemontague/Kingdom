"""
QA smoke runner (headless).

Wraps tools/observe_sync.py into a few standard profiles so QA/regressions can be run
as a single command that returns a useful exit code.

Examples:
  python tools/qa_smoke.py --quick
  python tools/qa_smoke.py --seconds 30 --heroes 20 --seed 3
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OBSERVE = PROJECT_ROOT / "tools" / "observe_sync.py"
DETERMINISM_GUARD = PROJECT_ROOT / "tools" / "determinism_guard.py"


def _run_determinism_guard(*, title: str) -> int:
    if not DETERMINISM_GUARD.exists():
        print(f"\n[qa_smoke] === {title} ===")
        print(f"[qa_smoke] WARN: missing {DETERMINISM_GUARD}; skipping determinism guard")
        return 0

    cmd = [sys.executable, str(DETERMINISM_GUARD)]
    print(f"\n[qa_smoke] === {title} ===")
    print("[qa_smoke] cmd:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    print(f"[qa_smoke] exit_code={completed.returncode}")
    return int(completed.returncode)


def _run_profile(args_list: list[str], *, title: str) -> int:
    env = os.environ.copy()
    # Extra safety for headless environments (Windows + CI runners).
    env.setdefault("SDL_VIDEODRIVER", "dummy")
    env.setdefault("SDL_AUDIODRIVER", "dummy")

    cmd = [sys.executable, str(OBSERVE), *args_list]
    print(f"\n[qa_smoke] === {title} ===")
    print("[qa_smoke] cmd:", " ".join(cmd))
    completed = subprocess.run(cmd, env=env, cwd=str(PROJECT_ROOT))
    print(f"[qa_smoke] exit_code={completed.returncode}")
    return int(completed.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run headless QA smoke profiles")
    ap.add_argument("--seconds", type=float, default=12.0, help="simulation duration per profile")
    ap.add_argument("--heroes", type=int, default=10, help="number of warrior heroes (base)")
    ap.add_argument("--seed", type=int, default=3, help="rng seed")
    ap.add_argument("--realtime", action="store_true", help="advance pygame clock similarly to realtime")
    ap.add_argument("--quick", action="store_true", help="run a small set of standard smoke profiles")
    ap.add_argument("--llm", action="store_true", help="include mock-LLM path (single profile mode only)")
    ap.add_argument("--no-enemies", action="store_true", help="disable enemies (single profile mode only)")
    ap.add_argument("--bounty", action="store_true", help="add an explore bounty (single profile mode only)")
    ap.add_argument("--log-every", type=int, default=180, help="log cadence in ticks (single profile mode only)")
    ns = ap.parse_args()

    if not OBSERVE.exists():
        print(f"[qa_smoke] ERROR: missing {OBSERVE}")
        return 2

    if ns.quick:
        profiles: list[tuple[str, list[str]]] = []
        base = [
            "--seconds",
            str(ns.seconds),
            "--heroes",
            str(ns.heroes),
            "--seed",
            str(ns.seed),
            "--log-every",
            "240",
            "--qa",
        ]
        if ns.realtime:
            base.append("--realtime")

        # Include bounties so QA can assert at least one responder.
        profiles.append(("base (enemies, construction, combat, bounty)", [*base, "--bounty"]))
        profiles.append(("bounty scenario preset (responders/claim)", [*base, "--no-enemies", "--scenario", "intent_bounty"]))
        profiles.append(("no-enemies (economy/shopping isolation)", [*base, "--no-enemies"]))
        profiles.append(("mock-LLM enabled (decision plumbing)", [*base, "--llm", "--realtime", "--bounty"]))

        rc = 0
        # Determinism is a release gate: fail fast if someone reintroduced wall-clock/RNG into sim logic.
        rc = _run_determinism_guard(title="determinism_guard (static)")
        if rc != 0:
            print("\n[qa_smoke] DONE:", f"FAIL (rc={rc})")
            return rc

        for title, a in profiles:
            prc = _run_profile(a, title=title)
            if prc != 0:
                rc = prc
                break

        print("\n[qa_smoke] DONE:", "PASS" if rc == 0 else f"FAIL (rc={rc})")
        return rc

    # Single-profile mode (fully configurable)
    args_list = [
        "--seconds",
        str(ns.seconds),
        "--heroes",
        str(ns.heroes),
        "--seed",
        str(ns.seed),
        "--log-every",
        str(ns.log_every),
    ]
    if ns.realtime:
        args_list.append("--realtime")
    if ns.no_enemies:
        args_list.append("--no-enemies")
    if ns.bounty:
        args_list.append("--bounty")
    if ns.llm:
        args_list.append("--llm")

    rc = _run_profile(args_list, title="custom")
    print("\n[qa_smoke] DONE:", "PASS" if rc == 0 else f"FAIL (rc={rc})")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())


