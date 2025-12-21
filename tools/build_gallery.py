"""
Build a lightweight local HTML gallery to compare our captured screenshots to reference images.

Usage (acceptance):
  python tools/build_gallery.py --shots docs/screenshots/test_run --refs .cursor/plans/art_examples --out docs/art/compare_gallery.html
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMG_EXTS


def _rel(from_dir: Path, to_path: Path) -> str:
    try:
        return os.path.relpath(str(to_path), start=str(from_dir))
    except Exception:
        return str(to_path)


def _load_manifest(shots_dir: Path) -> dict[str, Any]:
    m = shots_dir / "manifest.json"
    return json.loads(m.read_text(encoding="utf-8"))


def _find_run_dirs(shots_path: Path) -> list[Path]:
    """
    Accept either:
    - a single run dir containing manifest.json
    - a parent dir containing multiple run dirs, each with manifest.json
    """
    shots_path = shots_path.resolve()
    if (shots_path / "manifest.json").exists():
        return [shots_path]

    run_dirs: list[Path] = []
    if shots_path.exists() and shots_path.is_dir():
        # First, check immediate children (common layout: shots_root/<run>/manifest.json).
        for child in sorted(shots_path.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and (child / "manifest.json").exists():
                run_dirs.append(child)
        # Also allow nested layouts (tools may choose shots_root/scenario_seed3/<run>/... later).
        if not run_dirs:
            for m in sorted(shots_path.rglob("manifest.json"), key=lambda p: str(p).lower()):
                rd = m.parent
                if rd.is_dir():
                    run_dirs.append(rd)
    # De-dupe while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for rd in run_dirs:
        k = str(rd.resolve())
        if k in seen:
            continue
        seen.add(k)
        unique.append(rd)
    return unique


def _resolve_output_path(run_dir: Path, output: dict[str, Any]) -> Path:
    """
    Support both legacy and v1.1 manifests:
    - v1.0 wrote absolute `path`
    - v1.1 writes `relpath` relative to run_dir
    """
    if output.get("relpath"):
        return run_dir / str(output["relpath"])
    p = str(output.get("path", "") or "")
    if p:
        pp = Path(p)
        if pp.is_absolute():
            return pp
        return run_dir / pp
    return run_dir / str(output.get("filename", ""))


def _scan_refs(refs_dir: Path) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    if not refs_dir.exists():
        return refs
    for p in sorted(refs_dir.rglob("*")):
        if _is_image(p):
            refs.append({"name": p.name, "path": str(p)})
    return refs


def _html_escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a local compare gallery (HTML).")
    ap.add_argument("--shots", type=str, required=True, help="shots run directory (contains manifest.json)")
    ap.add_argument("--refs", type=str, required=True, help="reference images directory")
    ap.add_argument("--out", type=str, required=True, help="output HTML path (e.g., docs/art/compare_gallery.html)")
    ns = ap.parse_args()

    shots_dir = Path(ns.shots)
    refs_dir = Path(ns.refs)
    out_path = Path(ns.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    run_dirs = _find_run_dirs(shots_dir)
    if not run_dirs:
        raise SystemExit(f"No run directories found at: {shots_dir}")

    runs: list[dict[str, Any]] = []
    for rd in run_dirs:
        manifest = _load_manifest(rd)
        outputs = list(manifest.get("outputs", []))
        runs.append({"dir": str(rd), "manifest": manifest, "outputs": outputs})
    refs = _scan_refs(refs_dir)

    out_dir = out_path.parent
    shots_rel_dir = out_dir

    # Precompute relative paths for the HTML.
    our_runs = []
    for r in runs:
        manifest = r["manifest"]
        outputs = r["outputs"]
        rd = Path(r["dir"])
        items = []
        for o in outputs:
            p = _resolve_output_path(rd, o)
            items.append(
                {
                    "label": str(o.get("label", o.get("filename", ""))),
                    "filename": str(o.get("filename", "")),
                    "img": _rel(shots_rel_dir, p),
                    "sha256": str(o.get("sha256", "")),
                }
            )
        our_runs.append(
            {
                "scenario": str(manifest.get("run", {}).get("scenario", "")),
                "seed": int(manifest.get("run", {}).get("seed", 0) or 0),
                "run_dir": str(manifest.get("run", {}).get("run_dir", Path(r["dir"]).name)),
                "dir": str(rd),
                "items": items,
            }
        )

    ref_items = [{"name": r["name"], "img": _rel(shots_rel_dir, Path(r["path"]))} for r in refs]

    if len(our_runs) == 1:
        title = f"Compare Gallery — scenario={our_runs[0]['scenario']} seed={our_runs[0]['seed']}"
    else:
        title = f"Compare Gallery — {len(our_runs)} run(s)"

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_html_escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 16px; color: #111; }}
    h1 {{ font-size: 18px; margin: 0 0 12px 0; }}
    .meta {{ font-size: 12px; color: #444; margin-bottom: 16px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .section {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; }}
    .items {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }}
    .card {{ border: 1px solid #eee; border-radius: 8px; padding: 8px; }}
    .label {{ font-size: 12px; margin-bottom: 6px; }}
    img {{ width: 100%; height: auto; image-rendering: pixelated; background: #000; }}
    .small {{ font-size: 11px; color: #666; word-break: break-all; }}
  </style>
</head>
<body>
  <h1>{_html_escape(title)}</h1>
  <div class="meta">
    Shots: <code>{_html_escape(str(shots_dir))}</code><br/>
    Refs: <code>{_html_escape(str(refs_dir))}</code>
  </div>
  <div class="grid">
    <div class="section">
      <h2>Our runs</h2>
      {''.join([f'''
      <h3 style="margin: 10px 0 6px 0; font-size: 14px;">{_html_escape(run.get("run_dir",""))} — scenario={_html_escape(run["scenario"])} seed={run["seed"]}</h3>
      <div class="items">
        {''.join([f'''
        <div class="card">
          <div class="label">{_html_escape(i["label"])}</div>
          <a href="{_html_escape(i["img"])}" target="_blank" rel="noreferrer">
            <img src="{_html_escape(i["img"])}" alt="{_html_escape(i["filename"])}"/>
          </a>
          <div class="small">sha256: {_html_escape(i["sha256"])}</div>
        </div>''' for i in run["items"]])}
      </div>
      ''' for run in our_runs])}
    </div>
    <div class="section">
      <h2>References (.cursor/plans/art_examples)</h2>
      <div class="items">
        {''.join([f'''
        <div class="card">
          <div class="label">{_html_escape(r["name"])}</div>
          <a href="{_html_escape(r["img"])}" target="_blank" rel="noreferrer">
            <img src="{_html_escape(r["img"])}" alt="{_html_escape(r["name"])}"/>
          </a>
        </div>''' for r in ref_items])}
      </div>
    </div>
  </div>
</body>
</html>
"""

    out_path.write_text(html, encoding="utf-8")
    # Optional JSON sidecar for future tooling.
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps({"title": title, "runs": our_runs, "refs": ref_items}, indent=2),
        encoding="utf-8",
    )

    print(f"[gallery] Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


