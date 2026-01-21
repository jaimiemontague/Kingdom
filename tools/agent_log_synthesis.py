"""
Agent log synthesis helper.

Reads per-agent JSON logs under .cursor/plans/agent_logs and prints a compact
summary of blockers, risks, dependencies, and next actions for PM triage.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = PROJECT_ROOT / ".cursor" / "plans" / "agent_logs"


@dataclass(frozen=True)
class RoundInfo:
    sprint_id: str
    round_id: str
    sent_at: datetime | None
    received_at: datetime | None
    round_obj: dict[str, Any]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_agent_files(log_dir: Path) -> Iterable[Path]:
    if not log_dir.exists():
        return []
    files = [p for p in log_dir.glob("agent_*.json") if p.is_file()]
    files.sort()
    return files


def _collect_rounds(sprints: dict[str, Any]) -> list[RoundInfo]:
    rounds: list[RoundInfo] = []
    for sprint_id, sprint_obj in sprints.items():
        rounds_obj = sprint_obj.get("rounds", {}) if isinstance(sprint_obj, dict) else {}
        for round_id, round_obj in rounds_obj.items():
            if not isinstance(round_obj, dict):
                continue
            round_meta = round_obj.get("round_meta", {})
            response = round_obj.get("response", {})
            rounds.append(
                RoundInfo(
                    sprint_id=str(sprint_id),
                    round_id=str(round_id),
                    sent_at=_parse_dt(round_meta.get("sent_at_local")),
                    received_at=_parse_dt(response.get("received_at_local")),
                    round_obj=round_obj,
                )
            )
    return rounds


def _latest_round(rounds: list[RoundInfo]) -> RoundInfo | None:
    if not rounds:
        return None

    def key(r: RoundInfo) -> tuple[int, datetime, str, str]:
        ts = r.received_at or r.sent_at
        if ts is None:
            return (0, datetime.min, r.sprint_id, r.round_id)
        return (1, ts, r.sprint_id, r.round_id)

    return max(rounds, key=key)


def _select_round(
    rounds: list[RoundInfo],
    *,
    sprint: str | None,
    round_id: str | None,
) -> RoundInfo | None:
    if sprint:
        rounds = [r for r in rounds if r.sprint_id == sprint]
    if round_id:
        rounds = [r for r in rounds if r.round_id == round_id]
    return _latest_round(rounds)


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None:
        return []
    return [str(value)]


def _format_agent_block(label: str, items: list[str]) -> list[str]:
    if not items:
        return [f"{label}: none"]
    joined = "; ".join(items)
    return [f"{label}: {joined}"]


def _format_agent_summary(agent: dict[str, Any], selection: RoundInfo | None) -> list[str]:
    agent_id = str(agent.get("id", "?"))
    agent_name = str(agent.get("name", "unknown"))
    if selection is None:
        return [f"{agent_id}. {agent_name}: no rounds found"]

    resp = selection.round_obj.get("response", {})
    status = resp.get("status", "unknown")
    questions = _as_list(resp.get("questions_back_to_pm"))
    risks = _as_list(resp.get("risks"))
    deps = _as_list(resp.get("dependencies"))
    next_actions = _as_list(resp.get("recommended_next_actions"))
    summary = _as_list(resp.get("summary_bullets"))

    lines = [
        f"{agent_id}. {agent_name} — {selection.sprint_id}/{selection.round_id} (status={status})",
    ]
    if summary:
        lines.append(f"  summary: {'; '.join(summary)}")
    lines.extend(f"  {s}" for s in _format_agent_block("questions", questions))
    lines.extend(f"  {s}" for s in _format_agent_block("risks", risks))
    lines.extend(f"  {s}" for s in _format_agent_block("dependencies", deps))
    if next_actions:
        lines.append(f"  next_actions: {'; '.join(next_actions)}")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize agent logs for PM synthesis")
    ap.add_argument("--logs-dir", type=Path, default=DEFAULT_LOG_DIR, help="agent logs directory")
    ap.add_argument("--sprint", type=str, default=None, help="filter to sprint id")
    ap.add_argument("--round", dest="round_id", type=str, default=None, help="filter to round id")
    ap.add_argument("--json", action="store_true", help="emit JSON summary")
    ns = ap.parse_args()

    log_dir: Path = ns.logs_dir
    files = _iter_agent_files(log_dir)
    if not files:
        print(f"[agent_synthesis] ERROR: no agent logs found in {log_dir}")
        return 2

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    summary: dict[str, Any] = {
        "generated_at": generated_at,
        "filters": {"sprint": ns.sprint, "round": ns.round_id},
        "agents": [],
        "aggregate": {"questions": [], "risks": [], "dependencies": []},
    }

    lines: list[str] = []
    lines.append("[agent_synthesis] AI Studio agent summary")
    lines.append(f"[agent_synthesis] logs_dir={log_dir}")
    if ns.sprint or ns.round_id:
        lines.append(f"[agent_synthesis] filters: sprint={ns.sprint} round={ns.round_id}")

    for path in files:
        try:
            data = _load_json(path)
        except Exception as exc:
            lines.append(f"[agent_synthesis] WARN: failed to read {path.name}: {exc}")
            continue

        agent = data.get("agent", {})
        sprints = data.get("sprints", {}) if isinstance(data, dict) else {}
        rounds = _collect_rounds(sprints)
        selection = _select_round(rounds, sprint=ns.sprint, round_id=ns.round_id)

        resp = selection.round_obj.get("response", {}) if selection else {}
        questions = _as_list(resp.get("questions_back_to_pm"))
        risks = _as_list(resp.get("risks"))
        deps = _as_list(resp.get("dependencies"))

        summary["aggregate"]["questions"].extend(
            [{"agent": agent.get("name"), "item": q} for q in questions]
        )
        summary["aggregate"]["risks"].extend(
            [{"agent": agent.get("name"), "item": r} for r in risks]
        )
        summary["aggregate"]["dependencies"].extend(
            [{"agent": agent.get("name"), "item": d} for d in deps]
        )

        summary["agents"].append(
            {
                "agent_id": agent.get("id"),
                "agent_name": agent.get("name"),
                "sprint_id": selection.sprint_id if selection else None,
                "round_id": selection.round_id if selection else None,
                "status": resp.get("status"),
                "questions": questions,
                "risks": risks,
                "dependencies": deps,
                "summary_bullets": _as_list(resp.get("summary_bullets")),
                "recommended_next_actions": _as_list(resp.get("recommended_next_actions")),
            }
        )

        lines.extend(_format_agent_summary(agent, selection))

    if ns.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n".join(lines))
        agg_q = summary["aggregate"]["questions"]
        agg_r = summary["aggregate"]["risks"]
        agg_d = summary["aggregate"]["dependencies"]
        print("\n[agent_synthesis] aggregate")
        print(f"  questions: {len(agg_q)}")
        print(f"  risks: {len(agg_r)}")
        print(f"  dependencies: {len(agg_d)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
