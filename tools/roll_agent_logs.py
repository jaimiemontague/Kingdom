"""
Roll Cursor agent logs to reduce context bloat.

Keeps the last N sprints in each rolling log under:
  .cursor/plans/agent_logs/agent_*.json

Moves older sprints verbatim into per-log archives under:
  .cursor/plans/agent_logs/archive/agent_*.archive.json

Also writes a small index file:
  .cursor/plans/agent_logs/AGENT_LOG_INDEX.md

This tool is intentionally conservative:
  - Only processes logs that match the schema (top-level: schema_version, agent, sprints).
  - Skips any non-conforming JSON (e.g., JSONL-style *_AUTO.json).
  - Creates timestamped backups before modifying any file.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / ".cursor" / "plans" / "agent_logs"
ARCHIVE_DIR = LOG_DIR / "archive"
INDEX_PATH = LOG_DIR / "AGENT_LOG_INDEX.md"


def _utc_stamp() -> str:
    # Use timezone-aware UTC timestamp (py 3.13+).
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    # Keep stable, readable formatting. Do not sort keys: sprint key order matters.
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _is_schema_log(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if "schema_version" not in obj or "agent" not in obj or "sprints" not in obj:
        return False
    if not isinstance(obj.get("agent"), dict):
        return False
    if not isinstance(obj.get("sprints"), dict):
        return False
    return True


def _agent_id(obj: Dict[str, Any]) -> str:
    agent = obj.get("agent") or {}
    return str(agent.get("id", "unknown"))


def _backup_file(path: Path) -> Path:
    stamp = _utc_stamp()
    backup_path = path.with_name(f"{path.name}.bak_{stamp}")
    backup_path.write_bytes(path.read_bytes())
    return backup_path


def _archive_path_for(rolling_path: Path) -> Path:
    # Preserve basename; add .archive.json suffix.
    name = rolling_path.name
    if name.endswith(".json"):
        name = name[: -len(".json")]
    return ARCHIVE_DIR / f"{name}.archive.json"


def _list_candidate_logs() -> List[Path]:
    # Only top-level agent_*.json in LOG_DIR (exclude archive dir).
    candidates = sorted(LOG_DIR.glob("agent_*.json"))
    return [p for p in candidates if p.is_file()]


def _read_log_if_schema(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        obj = _load_json(path)
    except Exception as e:
        return None, f"failed_to_parse_json: {e}"
    if not _is_schema_log(obj):
        return None, "not_schema_log"
    return obj, None


def _roll_one(
    rolling_path: Path,
    keep: int,
    dry_run: bool,
    ensure_archive: bool,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "rolling_path": str(rolling_path),
        "status": "skipped",
        "reason": None,
        "agent_id": None,
        "sprints_total": None,
        "sprints_kept": None,
        "sprints_archived": [],
        "archive_path": None,
        "backups": [],
    }

    rolling_obj, err = _read_log_if_schema(rolling_path)
    if rolling_obj is None:
        result["status"] = "skipped"
        result["reason"] = err
        return result

    agent_id = _agent_id(rolling_obj)
    result["agent_id"] = agent_id

    sprints: Dict[str, Any] = rolling_obj["sprints"]
    sprint_keys = list(sprints.keys())
    result["sprints_total"] = len(sprint_keys)

    archive_path = _archive_path_for(rolling_path)
    result["archive_path"] = str(archive_path)

    if keep < 1:
        result["status"] = "skipped"
        result["reason"] = "invalid_keep_lt_1"
        return result

    if len(sprint_keys) <= keep:
        result["sprints_kept"] = len(sprint_keys)
        # Failsafe: ensure archive stub exists even if we don't need to roll.
        if ensure_archive and not archive_path.exists():
            result["status"] = "would_create_archive_stub" if dry_run else "created_archive_stub"
            if dry_run:
                return result

            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            archive_obj = {
                "schema_version": rolling_obj.get("schema_version", "2.0"),
                "agent": rolling_obj.get("agent", {"id": agent_id, "name": "unknown"}),
                "notes": [
                    "Archive file created by tools/roll_agent_logs.py.",
                    "Contains older sprints moved verbatim from the rolling log to reduce context bloat.",
                    "This file may be empty until the rolling log exceeds the keep window.",
                    "This file is append-only: do not rewrite old rounds.",
                ],
                "sprints": {},
            }
            _write_json(archive_path, archive_obj)
            return result

        result["status"] = "skipped"
        result["reason"] = "no_roll_needed"
        return result

    to_archive = sprint_keys[: len(sprint_keys) - keep]
    to_keep = sprint_keys[len(sprint_keys) - keep :]
    result["sprints_kept"] = len(to_keep)
    result["sprints_archived"] = to_archive

    # Load or create archive object.
    archive_obj: Dict[str, Any]
    if archive_path.exists():
        archive_obj_raw = _load_json(archive_path)
        if not _is_schema_log(archive_obj_raw):
            result["status"] = "skipped"
            result["reason"] = "archive_exists_but_not_schema_log"
            return result
        if _agent_id(archive_obj_raw) != agent_id:
            result["status"] = "skipped"
            result["reason"] = "archive_agent_id_mismatch"
            return result
        archive_obj = archive_obj_raw
        if "sprints" not in archive_obj or not isinstance(archive_obj["sprints"], dict):
            archive_obj["sprints"] = {}
    else:
        archive_obj = {
            "schema_version": rolling_obj.get("schema_version", "2.0"),
            "agent": rolling_obj.get("agent", {"id": agent_id, "name": "unknown"}),
            "notes": [
                "Archive file created by tools/roll_agent_logs.py.",
                "Contains older sprints moved verbatim from the rolling log to reduce context bloat.",
                "This file is append-only: do not rewrite old rounds.",
            ],
            "sprints": {},
        }

    # Determine which keys are actually new to archive (idempotency).
    archive_sprints: Dict[str, Any] = archive_obj["sprints"]
    already_present = [k for k in to_archive if k in archive_sprints]
    if already_present:
        # If archive already has these sprints, we don't want to overwrite them silently.
        # This can happen if the tool was run before and the rolling file still contains them (manual edits).
        # In that case, refuse to proceed unless dry-run; user can resolve by removing duplicates from rolling.
        result["status"] = "skipped"
        result["reason"] = f"archive_already_contains_sprints: {already_present[:5]}{'...' if len(already_present) > 5 else ''}"
        return result

    result["status"] = "would_roll" if dry_run else "rolled"

    if dry_run:
        return result

    # Ensure archive directory exists.
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Backups before writing.
    result["backups"].append(str(_backup_file(rolling_path)))
    if archive_path.exists():
        result["backups"].append(str(_backup_file(archive_path)))

    # Move sprints (copy then delete).
    for k in to_archive:
        archive_sprints[k] = sprints[k]
    for k in to_archive:
        del sprints[k]

    # Write updated files.
    _write_json(archive_path, archive_obj)
    _write_json(rolling_path, rolling_obj)
    return result


def _summarize_sprint(sprint_obj: Any) -> str:
    # Best-effort extraction of 1-2 bullets from common fields; keep it very short.
    if not isinstance(sprint_obj, dict):
        return ""
    rounds = sprint_obj.get("rounds")
    if not isinstance(rounds, dict) or not rounds:
        return ""
    # Take the last round (in insertion order).
    last_round_key = list(rounds.keys())[-1]
    last_round = rounds.get(last_round_key) or {}
    # Common locations:
    # - response.summary_bullets (list[str])
    # - what_i_changed (list[str])
    resp = last_round.get("response")
    if isinstance(resp, dict):
        bullets = resp.get("summary_bullets")
        if isinstance(bullets, list) and bullets:
            return "; ".join(str(b) for b in bullets[:2])
    wic = last_round.get("what_i_changed")
    if isinstance(wic, list) and wic:
        return "; ".join(str(b) for b in wic[:2])
    # PM hub has pm_status_summary.wk*_focus etc, but avoid digging deep.
    return ""


def _collect_index_rows() -> List[str]:
    rows: List[str] = []

    # Rolling logs.
    rolling_paths = _list_candidate_logs()
    for rp in sorted(rolling_paths, key=lambda p: p.name.lower()):
        rolling_obj, err = _read_log_if_schema(rp)
        if rolling_obj is None:
            continue
        agent = rolling_obj.get("agent") or {}
        agent_label = f'{agent.get("id","??")} — {agent.get("name","unknown")}'
        rows.append(f"### {agent_label}")
        rows.append("")
        rows.append(f"- **Rolling**: `{rp.as_posix()}`")

        ap = _archive_path_for(rp)
        rows.append(f"- **Archive**: `{ap.as_posix()}`{' (missing)' if not ap.exists() else ''}")
        rows.append("")

        rolling_sprints = list((rolling_obj.get("sprints") or {}).keys())
        if rolling_sprints:
            rows.append("**Rolling sprints (most recent kept):**")
            for k in rolling_sprints:
                summ = _summarize_sprint(rolling_obj["sprints"].get(k))
                if summ:
                    rows.append(f"- `{k}` — {summ}")
                else:
                    rows.append(f"- `{k}`")
        else:
            rows.append("**Rolling sprints:** (none)")

        # Archive sprints list (names only, no summaries to keep tiny).
        if ap.exists():
            try:
                arch_obj = _load_json(ap)
            except Exception:
                arch_obj = None
            if _is_schema_log(arch_obj):
                arch_sprints = list((arch_obj.get("sprints") or {}).keys())
                rows.append("")
                rows.append(f"**Archived sprints:** {len(arch_sprints)}")
                if arch_sprints:
                    # Keep list compact: show first 5 and last 5.
                    if len(arch_sprints) <= 12:
                        for k in arch_sprints:
                            rows.append(f"- `{k}`")
                    else:
                        for k in arch_sprints[:5]:
                            rows.append(f"- `{k}`")
                        rows.append("- `…`")
                        for k in arch_sprints[-5:]:
                            rows.append(f"- `{k}`")
        rows.append("")

    return rows


def _write_index() -> None:
    lines: List[str] = []
    lines.append("# Agent Log Index")
    lines.append("")
    lines.append("This file is generated by `python tools/roll_agent_logs.py`.")
    lines.append("It lists which sprints live in rolling logs vs archives, so you can look up history without loading large JSON files into context.")
    lines.append("")
    lines.append(f"- Log dir: `{LOG_DIR.as_posix()}`")
    lines.append(f"- Archive dir: `{ARCHIVE_DIR.as_posix()}`")
    lines.append("")
    lines.extend(_collect_index_rows())
    INDEX_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Roll agent logs into archives to reduce context bloat.")
    parser.add_argument("--keep", type=int, default=7, help="Number of most-recent sprints to keep in rolling logs (default: 7).")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change but do not write files.")
    parser.add_argument("--only", type=str, default=None, help="Only process a single rolling log filename (e.g. agent_01_ExecutiveProducer_PM.json).")
    parser.set_defaults(ensure_archives=True)
    parser.add_argument(
        "--no-ensure-archives",
        action="store_false",
        dest="ensure_archives",
        help="Disable creating empty archive stubs for schema logs that don't yet need rolling.",
    )
    parser.add_argument("--write-index", action="store_true", help="Write AGENT_LOG_INDEX.md after processing.")
    args = parser.parse_args(argv)

    rolling_paths = _list_candidate_logs()
    if args.only:
        rolling_paths = [p for p in rolling_paths if p.name == args.only]
        if not rolling_paths:
            print(f"ERROR: --only '{args.only}' did not match any file under {LOG_DIR}")
            return 2

    results: List[Dict[str, Any]] = []
    for p in rolling_paths:
        res = _roll_one(p, keep=args.keep, dry_run=args.dry_run, ensure_archive=args.ensure_archives)
        results.append(res)

    # Report.
    rolled = [r for r in results if r["status"] in ("rolled", "would_roll", "created_archive_stub", "would_create_archive_stub")]
    skipped = [r for r in results if r["status"] == "skipped"]
    print(f"keep={args.keep} dry_run={args.dry_run}")
    print(f"processed={len(results)} rolled={len(rolled)} skipped={len(skipped)}")
    for r in results:
        status = r["status"]
        base = os.path.basename(r["rolling_path"])
        if status in ("rolled", "would_roll"):
            print(f"- {status}: {base} (archived={len(r['sprints_archived'])}, kept={r['sprints_kept']})")
        elif status in ("created_archive_stub", "would_create_archive_stub"):
            print(f"- {status}: {base} (kept={r['sprints_kept']})")
        else:
            print(f"- skipped: {base} ({r.get('reason')})")

    if args.write_index and not args.dry_run:
        _write_index()
        print(f"wrote_index: {INDEX_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

