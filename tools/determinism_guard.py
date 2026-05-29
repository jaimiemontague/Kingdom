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


def _display_path(p: Path) -> str:
    """Human-readable path for reporting.

    Prefer a repo-relative path, but fall back to the absolute string when the
    path lives outside ``PROJECT_ROOT`` (``relative_to`` raises ``ValueError``).
    This is load-bearing: callers run ``determinism_guard --paths <file>`` with
    paths that may be outside the repo, and the old ``file.relative_to(...)``
    crashed those runs.
    """
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


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


# Modules whose aliases we care about when normalizing attribute chains.
# (We only rewrite the *root* of a chain through a module alias, plus direct
# `from X import name` bindings for these modules.)
_TRACKED_MODULES = {"pygame", "time", "datetime", "random"}


def _build_alias_map(tree: ast.AST) -> dict[str, tuple[str, ...]]:
    """
    Build a map from a locally-bound name to the canonical attribute prefix it
    refers to, so aliased imports are matched like their canonical form.

    Examples (name -> canonical prefix tuple):
      ``import time as t``                  -> {"t": ("time",)}
      ``import datetime as dt``             -> {"dt": ("datetime",)}
      ``from random import random``         -> {"random": ("random", "random")}
      ``from random import random as rnd``  -> {"rnd": ("random", "random")}
      ``from time import time as now``      -> {"now": ("time", "time")}
      ``from datetime import datetime``     -> {"datetime": ("datetime", "datetime")}

    Only tracked modules (``pygame``/``time``/``datetime``/``random``) are mapped;
    everything else is ignored so unrelated aliases don't create false positives.
    """
    aliases: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # `import time as t` / `import datetime.foo as d`
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in _TRACKED_MODULES:
                    continue
                bound = alias.asname or alias.name
                # `import datetime as d` -> d == datetime; submodule imports
                # bind the dotted name only when unaliased, which we skip.
                if alias.asname:
                    aliases[alias.asname] = tuple(alias.name.split("."))
                elif "." not in alias.name:
                    aliases[bound] = (alias.name,)
        elif isinstance(node, ast.ImportFrom):
            # `from random import random [as rnd]`
            if node.level and node.level > 0:
                continue  # relative import; not a tracked stdlib module
            module = node.module or ""
            root = module.split(".")[0]
            if root not in _TRACKED_MODULES:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                aliases[bound] = (*module.split("."), alias.name)
    return aliases


def _normalize_chain(
    chain: list[str], aliases: dict[str, tuple[str, ...]]
) -> list[str]:
    """Rewrite the root of an attribute chain through the alias map.

    ``["t", "time"]`` with ``{"t": ("time",)}`` -> ``["time", "time"]``.
    ``["rnd"]``       with ``{"rnd": ("random", "random")}`` -> ``["random", "random"]``.
    """
    if not chain:
        return chain
    mapped = aliases.get(chain[0])
    if mapped is None:
        return chain
    return [*mapped, *chain[1:]]


def _violation(kind: str, file: Path, node: ast.AST, detail: str) -> dict:
    return {
        "kind": kind,
        "file": _display_path(file),
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
                "file": _display_path(file_path),
                "line": int(getattr(e, "lineno", 0) or 0),
                "col": int(getattr(e, "offset", 0) or 0),
                "detail": f"SyntaxError: {e}",
            }
        ]

    findings: list[dict] = []
    aliases = _build_alias_map(tree)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        raw_chain = _attr_chain(node.func)
        if not raw_chain:
            continue
        chain = _normalize_chain(raw_chain, aliases)

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

    # Resolve input roots to absolute so paths outside the repo (and relative
    # paths) are handled consistently; reporting falls back to the raw string
    # for anything outside PROJECT_ROOT (see _display_path).
    if ns.paths:
        roots = [Path(p).resolve() for p in ns.paths]
    else:
        roots = list(DEFAULT_SCAN_DIRS)
    exclude_dirs = list(DEFAULT_EXCLUDE_DIRS)

    files = _iter_py_files(roots, exclude_dirs=exclude_dirs)
    all_findings: list[dict] = []
    for f in files:
        all_findings.extend(scan_file(f))

    # A parse error is NOT a determinism violation: a malformed/partial file
    # should not produce the same FAIL/exit-1 as a real wall-clock/RNG use.
    parse_errors = [v for v in all_findings if v.get("kind") == "parse_error"]
    violations = [v for v in all_findings if v.get("kind") != "parse_error"]

    if ns.json:
        print(
            json.dumps(
                {"violations": violations, "parse_errors": parse_errors},
                indent=2,
            )
        )
    else:
        if parse_errors:
            print(
                f"[determinism_guard] WARN: {len(parse_errors)} file(s) could not be parsed (not counted as violations)"
            )
            for v in parse_errors:
                print(f"- {v['file']}:{v['line']}:{v['col']} [parse_error] {v['detail']}")
        if not violations:
            print("[determinism_guard] PASS: no violations found")
        else:
            print(f"[determinism_guard] FAIL: {len(violations)} violation(s)")
            for v in violations:
                print(f"- {v['file']}:{v['line']}:{v['col']} [{v['kind']}] {v['detail']}")

    # Exit non-zero only for real determinism violations.
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())







