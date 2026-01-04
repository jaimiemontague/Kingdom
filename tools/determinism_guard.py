"""
Determinism guard (static check).

Purpose:
- Prevent accidental reintroduction of nondeterministic dependencies into simulation logic
  (future multiplayer enablement + replays + reproducible QA).

What we flag (in simulation code):
- Wall-clock-ish time: pygame.time.get_ticks(), time.time(), time.monotonic(), datetime.now(), etc.
- Unseeded / global RNG: random.random/randint/choice/shuffle/...
- Python's hash() (process-randomized by default)

We intentionally DO NOT scan:
- game/ui/** (UI can use wall-clock time)
- game/graphics/** (render/VFX can be nondeterministic)
- game/sim/** (this contains the deterministic wrappers)
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


DEFAULT_SCAN_DIRS = [
    PROJECT_ROOT / "game" / "entities",
    PROJECT_ROOT / "game" / "systems",
    PROJECT_ROOT / "ai",
]

DEFAULT_EXCLUDE_DIRS = [
    PROJECT_ROOT / "game" / "ui",
    PROJECT_ROOT / "game" / "graphics",
    PROJECT_ROOT / "game" / "sim",
]


_RANDOM_ATTRS = {
    "random",
    "randint",
    "uniform",
    "choice",
    "shuffle",
    "seed",
    "randrange",
}

_TIME_ATTRS_FORBIDDEN = {
    "time",
    "monotonic",
}

_DATETIME_ATTRS_FORBIDDEN = {
    "now",
    "utcnow",
}


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _iter_py_files(roots: Iterable[Path], *, exclude_dirs: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".py":
            out.append(root)
            continue
        for p in root.rglob("*.py"):
            if any(_is_under(p, ex) for ex in exclude_dirs):
                continue
            out.append(p)
    return sorted(set(out))


def _attr_chain(node: ast.AST) -> list[str] | None:
    """
    For Attribute chains, return list like ["pygame", "time", "get_ticks"].
    For Names, return ["name"].
    """
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        base = _attr_chain(node.value)
        if base is None:
            return None
        return [*base, node.attr]
    return None


def _violation(kind: str, file: Path, node: ast.AST, detail: str) -> dict:
    return {
        "kind": kind,
        "file": str(file.relative_to(PROJECT_ROOT)),
        "line": int(getattr(node, "lineno", 0) or 0),
        "col": int(getattr(node, "col_offset", 0) or 0),
        "detail": detail,
    }


def scan_file(file_path: Path) -> list[dict]:
    try:
        src = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = file_path.read_text(encoding="utf-8", errors="replace")

    try:
        tree = ast.parse(src, filename=str(file_path))
    except SyntaxError as e:
        return [
            {
                "kind": "parse_error",
                "file": str(file_path.relative_to(PROJECT_ROOT)),
                "line": int(getattr(e, "lineno", 0) or 0),
                "col": int(getattr(e, "offset", 0) or 0),
                "detail": f"SyntaxError: {e}",
            }
        ]

    findings: list[dict] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        chain = _attr_chain(node.func)
        if not chain:
            continue

        # pygame.time.get_ticks()
        if chain == ["pygame", "time", "get_ticks"]:
            findings.append(
                _violation(
                    "wall_clock_time",
                    file_path,
                    node,
                    "Use game.sim.timebase.now_ms() (sim time) instead of pygame.time.get_ticks() in simulation logic.",
                )
            )
            continue

        # time.time() / time.monotonic()
        if len(chain) == 2 and chain[0] == "time" and chain[1] in _TIME_ATTRS_FORBIDDEN:
            findings.append(
                _violation(
                    "wall_clock_time",
                    file_path,
                    node,
                    f"Use sim time (game.sim.timebase.now_ms) or dt accumulation; avoid time.{chain[1]}() in simulation logic.",
                )
            )
            continue

        # datetime.datetime.now()/utcnow() or datetime.now()/utcnow()
        if chain[-1] in _DATETIME_ATTRS_FORBIDDEN and ("datetime" in chain):
            findings.append(
                _violation(
                    "wall_clock_time",
                    file_path,
                    node,
                    "Avoid datetime.now()/utcnow() in simulation logic; use sim time.",
                )
            )
            continue

        # random.<...>()
        if len(chain) == 2 and chain[0] == "random" and chain[1] in _RANDOM_ATTRS:
            findings.append(
                _violation(
                    "global_rng",
                    file_path,
                    node,
                    "Use game.sim.determinism.get_rng(...) (seeded) instead of random.* in simulation logic.",
                )
            )
            continue

        # hash(...)
        if chain == ["hash"]:
            findings.append(
                _violation(
                    "unstable_hash",
                    file_path,
                    node,
                    "Avoid Python hash() for deterministic behavior; use a stable hash (e.g. zlib.crc32) or explicit IDs.",
                )
            )
            continue

    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="Static determinism guard (simulation code)")
    ap.add_argument(
        "--paths",
        nargs="*",
        default=[],
        help="Optional paths to scan (files or dirs). Default scans game/entities, game/systems, ai.",
    )
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    ns = ap.parse_args()

    roots = [Path(p) for p in ns.paths] if ns.paths else list(DEFAULT_SCAN_DIRS)
    exclude_dirs = list(DEFAULT_EXCLUDE_DIRS)

    files = _iter_py_files(roots, exclude_dirs=exclude_dirs)
    all_findings: list[dict] = []
    for f in files:
        all_findings.extend(scan_file(f))

    if ns.json:
        print(json.dumps({"findings": all_findings}, indent=2))
    else:
        if not all_findings:
            print("[determinism_guard] PASS: no violations found")
        else:
            print(f"[determinism_guard] FAIL: {len(all_findings)} violation(s)")
            for v in all_findings:
                print(f"- {v['file']}:{v['line']}:{v['col']} [{v['kind']}] {v['detail']}")

    return 0 if not all_findings else 1


if __name__ == "__main__":
    raise SystemExit(main())







