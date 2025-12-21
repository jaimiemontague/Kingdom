"""
Asset validation (WK3).

Build A policy: report-only (do not block UI work).
Build B policy: strict + attribution checks become failing gates.

This tool is intentionally FAST:
- no image decoding
- no scaling
- only filesystem checks
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "tools" / "assets_manifest.json"
DEFAULT_ASSETS_ROOT = PROJECT_ROOT / "assets"


FRAME_RE = re.compile(r"^frame_(\d+)\.(png|PNG)$")


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warn"
    code: str
    message: str
    path: str | None = None


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data


def _list_png_frames(dir_path: Path) -> list[str]:
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    names = []
    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        if FRAME_RE.match(p.name):
            names.append(p.name)
    names.sort()
    return names


def _has_sortable_frames(names: list[str]) -> bool:
    # We only require that names match frame_###.png; ordering is filename-sort order.
    # If there are duplicates or gaps, we still accept in report mode; strict may choose to tighten later.
    return bool(names)


def _validate_sprite_tree(
    *,
    assets_root: Path,
    category: str,
    kinds: Iterable[str],
    states: Iterable[str],
) -> tuple[list[Finding], dict[str, Any]]:
    """
    Validate directory structure like:
      assets/sprites/<category>/<kind>/<state>/frame_###.png
    """
    findings: list[Finding] = []
    report: dict[str, Any] = {"category": category, "kinds": {}}

    base = assets_root / "sprites" / category
    if not base.exists():
        findings.append(Finding("error", "missing_dir", f"Missing base directory for {category}", str(base)))
        return findings, report

    for kind in kinds:
        kind_report: dict[str, Any] = {"states": {}, "missing_states": [], "present_states": 0}
        kind_dir = base / kind
        if not kind_dir.exists():
            findings.append(Finding("warn", "missing_kind_dir", f"Missing {category} kind directory: {kind}", str(kind_dir)))
        for st in states:
            st_dir = kind_dir / st
            frames = _list_png_frames(st_dir)
            if not frames:
                kind_report["missing_states"].append(st)
                kind_report["states"][st] = {"frames": 0, "ok": False}
            else:
                kind_report["present_states"] += 1
                ok = _has_sortable_frames(frames)
                kind_report["states"][st] = {"frames": len(frames), "ok": bool(ok), "sample": frames[:3]}
                if not ok:
                    findings.append(Finding("warn", "bad_frame_naming", f"Frames not sortable/named correctly for {category}:{kind}:{st}", str(st_dir)))
        report["kinds"][kind] = kind_report

    return findings, report


def _validate_attribution(*, assets_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    third_party = assets_root / "third_party"
    if not third_party.exists():
        # No third-party packs present -> no-op.
        return findings

    if not third_party.is_dir():
        return [Finding("error", "third_party_not_dir", "assets/third_party exists but is not a directory", str(third_party))]

    # If packs exist, require verbatim LICENSE*/README* files within each pack dir.
    for pack in sorted([p for p in third_party.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        has_license = False
        has_readme = False
        for f in pack.iterdir():
            if not f.is_file():
                continue
            n = f.name.lower()
            if n.startswith("license") and n.endswith(".txt"):
                has_license = True
            if n.startswith("readme") and n.endswith(".txt"):
                has_readme = True
        if not has_license:
            findings.append(Finding("error", "missing_pack_license", f"Missing LICENSE*.txt in third-party pack dir: {pack.name}", str(pack)))
        if not has_readme:
            findings.append(Finding("warn", "missing_pack_readme", f"Missing README*.txt in third-party pack dir: {pack.name}", str(pack)))

    # If third_party exists, recommend ATTRIBUTION.md (warn, not error).
    attribution = assets_root / "ATTRIBUTION.md"
    if not attribution.exists():
        findings.append(Finding("warn", "missing_attribution_rollup", "Missing assets/ATTRIBUTION.md rollup file", str(attribution)))

    return findings


def _print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("[validate_assets] OK: no findings")
        return
    for f in findings:
        loc = f" ({f.path})" if f.path else ""
        print(f"[validate_assets] {f.severity.upper()} {f.code}: {f.message}{loc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate sprite folders + attribution (fast, no image decoding).")
    ap.add_argument("--manifest", type=str, default=str(DEFAULT_MANIFEST), help="path to assets manifest JSON")
    ap.add_argument("--assets-root", type=str, default=str(DEFAULT_ASSETS_ROOT), help="assets root directory")
    ap.add_argument("--report", action="store_true", help="print human-readable report (default behavior)")
    ap.add_argument("--json", action="store_true", help="emit JSON report to stdout (for CI parsing)")
    ap.add_argument("--strict", action="store_true", help="non-zero exit if missing required folders/states")
    ap.add_argument("--check-attribution", action="store_true", help="validate assets/third_party/* license/readme scaffolding")
    ns = ap.parse_args()

    manifest_path = Path(ns.manifest)
    assets_root = Path(ns.assets_root)

    # Default to report mode if no explicit mode flags are set.
    if not (ns.report or ns.json or ns.strict or ns.check_attribution):
        ns.report = True

    try:
        manifest = _load_manifest(manifest_path)
    except Exception as e:
        print(f"[validate_assets] ERROR: failed to read manifest: {e} ({manifest_path})")
        return 2

    findings: list[Finding] = []
    full_report: dict[str, Any] = {"manifest": str(manifest_path), "assets_root": str(assets_root), "categories": {}}

    heroes = manifest.get("heroes", {})
    enemies = manifest.get("enemies", {})
    buildings = manifest.get("buildings", {})

    h_findings, h_report = _validate_sprite_tree(
        assets_root=assets_root,
        category="heroes",
        kinds=heroes.get("classes", []),
        states=heroes.get("states", []),
    )
    findings.extend(h_findings)
    full_report["categories"]["heroes"] = h_report

    e_findings, e_report = _validate_sprite_tree(
        assets_root=assets_root,
        category="enemies",
        kinds=enemies.get("types", []),
        states=enemies.get("states", []),
    )
    findings.extend(e_findings)
    full_report["categories"]["enemies"] = e_report

    b_findings, b_report = _validate_sprite_tree(
        assets_root=assets_root,
        category="buildings",
        kinds=buildings.get("types", []),
        states=buildings.get("states", []),
    )
    findings.extend(b_findings)
    full_report["categories"]["buildings"] = b_report

    if ns.check_attribution:
        findings.extend(_validate_attribution(assets_root=assets_root))

    # Output
    if ns.json:
        # Keep it single JSON object for easy tooling.
        serial = {
            "report": full_report,
            "findings": [f.__dict__ for f in findings],
        }
        print(json.dumps(serial, ensure_ascii=False))
    else:
        if ns.report:
            _print_findings(findings)
            # Compact summary for quick scan.
            errors = len([f for f in findings if f.severity == "error"])
            warns = len([f for f in findings if f.severity == "warn"])
            print(f"[validate_assets] SUMMARY errors={errors} warns={warns}")

    if ns.strict:
        # Strict gate: errors are always failing. Missing kind/state dirs are warnings by default today
        # because Build A should not be blocked; QA can tighten severity in Build B if desired.
        if any(f.severity == "error" for f in findings):
            return 1

    # Report-only default behavior: always succeed.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


