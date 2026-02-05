from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .events import EventBus, EventSink
from .models import EventKind, SprintState, SprintStatus, utc_now_iso
from .policy import default_contract, total_budget_minutes, validate_contract
from .orchestrator import default_orchestrator
from .state_store import StateStore
from .config import load_or_create_config
from .daemon import serve


def _repo_root() -> Path:
    # repo-local invocation assumption; stable for Cursor and CLI usage
    return Path(__file__).resolve().parents[1]


def cmd_status(args: argparse.Namespace) -> int:
    repo = _repo_root()
    store = StateStore.default(repo_root=repo)
    store.load()
    paths = store.paths

    out = {
        "studio_gateway_version": __version__,
        "repo_root": str(repo),
        "store_root": str(paths.root),
        "sprints": sorted(store.list_sprints().keys()),
        "events_path": str(paths.events_jsonl),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_events(args: argparse.Namespace) -> int:
    repo = _repo_root()
    store = StateStore.default(repo_root=repo)
    store.load()
    bus = EventBus(sink=EventSink(store.paths.events_jsonl))
    events = bus.recent(max_lines=int(args.tail))
    payload = [e.__dict__ for e in events]
    print(json.dumps(payload, indent=2))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    repo = _repo_root()
    store = StateStore.default(repo_root=repo)
    store.load()
    store.paths.root.mkdir(parents=True, exist_ok=True)
    store.paths.artifacts_root.mkdir(parents=True, exist_ok=True)

    bus = EventBus(sink=EventSink(store.paths.events_jsonl))
    bus.emit(EventKind.NOTE, "studio_gateway initialized", data={"version": __version__})
    store.save()

    contract = default_contract()
    validate_contract(contract)
    min_budget = total_budget_minutes(contract, use_max=False)
    max_budget = total_budget_minutes(contract, use_max=True)
    print(f"[studio_gateway] initialized at {store.paths.root}")
    print(f"[studio_gateway] default sprint loop budget: {min_budget}-{max_budget} minutes (R0..R5)")
    return 0


def cmd_sprint_create(args: argparse.Namespace) -> int:
    repo = _repo_root()
    store = StateStore.default(repo_root=repo)
    store.load()

    sprint_id = args.sprint_id
    if store.get_sprint(sprint_id) is not None:
        print(f"[studio_gateway] ERROR: sprint already exists: {sprint_id}", file=sys.stderr)
        return 2

    s = SprintState(
        sprint_id=sprint_id,
        title=args.title or sprint_id,
        created_ts=utc_now_iso(),
        status=SprintStatus.CREATED,
        artifacts_dir=str((store.paths.artifacts_root / sprint_id).resolve()),
        meta={"created_by": "cli"},
    )
    store.upsert_sprint(s)
    store.save()

    bus = EventBus(sink=EventSink(store.paths.events_jsonl))
    bus.emit(EventKind.SPRINT_CREATED, f"sprint created: {sprint_id}", sprint_id=sprint_id)
    print(f"[studio_gateway] created sprint {sprint_id}")
    return 0


def cmd_sprint_run(args: argparse.Namespace) -> int:
    repo = _repo_root()
    orch = default_orchestrator(repo_root=repo)
    orch.run_to_completion(args.sprint_id)
    print(f"[studio_gateway] sprint run finished: {args.sprint_id}")
    return 0


def cmd_sprint_step(args: argparse.Namespace) -> int:
    repo = _repo_root()
    orch = default_orchestrator(repo_root=repo)
    orch.step(args.sprint_id)
    print(f"[studio_gateway] sprint stepped: {args.sprint_id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="studio_gateway", description="AI Studio autonomous sprint runner")
    ap.add_argument("--version", action="store_true", help="print version and exit")
    sp = ap.add_subparsers(dest="cmd")

    p_init = sp.add_parser("init", help="initialize .studio_gateway state store")
    p_init.set_defaults(func=cmd_init)

    p_status = sp.add_parser("status", help="print gateway status")
    p_status.set_defaults(func=cmd_status)

    p_events = sp.add_parser("events", help="print recent events (json)")
    p_events.add_argument("--tail", default="200", help="max events to show")
    p_events.set_defaults(func=cmd_events)

    p_serve = sp.add_parser("serve", help="run local web UI server (daemon)")
    p_serve.add_argument("--host", default="127.0.0.1", help="bind host (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=18790, help="bind port (default: 18790)")
    p_serve.set_defaults(
        func=lambda ns: (serve(repo_root=_repo_root(), host=str(ns.host), port=int(ns.port)) or 0)  # blocks
    )

    p_sprint = sp.add_parser("sprint", help="sprint operations")
    sps = p_sprint.add_subparsers(dest="sprint_cmd")

    p_create = sps.add_parser("create", help="create a new sprint record")
    p_create.add_argument("sprint_id", help="unique sprint id (e.g., wk8_memory_leak_hotfix)")
    p_create.add_argument("--title", default=None, help="human title")
    p_create.set_defaults(func=cmd_sprint_create)

    p_step = sps.add_parser("step", help="advance the sprint by one round (MVP)")
    p_step.add_argument("sprint_id", help="sprint id")
    p_step.set_defaults(func=cmd_sprint_step)

    p_run = sps.add_parser("run", help="run the sprint to completion (MVP)")
    p_run.add_argument("sprint_id", help="sprint id")
    p_run.set_defaults(func=cmd_sprint_run)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    ns = ap.parse_args(argv)
    if ns.version:
        print(__version__)
        return 0
    if not hasattr(ns, "func"):
        ap.print_help()
        return 2
    return int(ns.func(ns))

