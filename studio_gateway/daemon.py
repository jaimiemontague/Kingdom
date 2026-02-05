from __future__ import annotations

import json
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import __version__
from .config import GatewayConfig, load_or_create_config, save_config
from .events import EventBus, EventSink
from .models import EventKind, SprintState, SprintStatus, utc_now_iso
from .orchestrator import OrchestratorConfig, default_orchestrator
from .policy import default_contract
from .state_store import StateStore


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")


class StudioGatewayApp:
    """
    Long-lived app container shared by HTTP handlers.
    """

    def __init__(self, *, repo_root: Path):
        self.repo_root = repo_root
        self.store = StateStore.default(repo_root=repo_root)
        self.store.load()
        self.bus = EventBus(sink=EventSink(self.store.paths.events_jsonl))
        self.cfg: GatewayConfig = load_or_create_config(repo_root=repo_root)

        self._job_lock = threading.Lock()
        self._current_job: Optional[threading.Thread] = None
        self._current_job_name: Optional[str] = None

    def reload_config(self) -> None:
        self.cfg = load_or_create_config(repo_root=self.repo_root)

    def update_config(self, patch: Dict[str, Any]) -> GatewayConfig:
        cfg = GatewayConfig.from_dict({**self.cfg.to_dict(), **patch})
        # Keep token stable unless explicitly changed.
        if not cfg.auth_token:
            cfg.auth_token = self.cfg.auth_token
        save_config(repo_root=self.repo_root, cfg=cfg)
        self.cfg = cfg
        return cfg

    def orchestrator(self):
        contract = default_contract()
        ocfg = OrchestratorConfig(
            repo_root=self.repo_root,
            contract=contract,
            max_concurrent_global=int(self.cfg.max_concurrent_global),
            enable_auto_merge=bool(self.cfg.enable_auto_merge),
            automation_paused=bool(self.cfg.automation_paused),
        )
        return default_orchestrator(repo_root=self.repo_root, cfg_override=ocfg)

    def start_job(self, name: str, target) -> bool:
        with self._job_lock:
            if self._current_job and self._current_job.is_alive():
                return False
            t = threading.Thread(target=target, name=name, daemon=True)
            self._current_job = t
            self._current_job_name = name
            t.start()
            return True

    def job_status(self) -> Dict[str, Any]:
        with self._job_lock:
            running = bool(self._current_job and self._current_job.is_alive())
            return {"running": running, "name": self._current_job_name if running else None}


class Handler(BaseHTTPRequestHandler):
    server_version = "StudioGatewayHTTP/0.1"

    def _app(self) -> StudioGatewayApp:
        return self.server.app  # type: ignore[attr-defined]

    def _require_auth(self) -> bool:
        app = self._app()
        token = app.cfg.auth_token
        if not token:
            return True
        got = self.headers.get("X-Studio-Gateway-Token") or ""
        return got == token

    def _send(self, code: int, body: bytes, *, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, obj: Any) -> None:
        self._send(code, _json_bytes(obj))

    def _send_text(self, code: int, text: str, *, content_type: str = "text/plain; charset=utf-8") -> None:
        self._send(code, (text + "\n").encode("utf-8"), content_type=content_type)

    def _parse_json_body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return dict(json.loads(raw.decode("utf-8")))
        except Exception:
            return {}

    def _route(self) -> Tuple[str, Dict[str, str]]:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = urllib.parse.parse_qs(parsed.query)
        params = {k: v[-1] for k, v in q.items() if v}
        return path, params

    def do_GET(self) -> None:  # noqa: N802
        path, params = self._route()
        app = self._app()

        if path == "/health":
            return self._send_json(200, {"ok": True, "version": __version__})

        if path == "/":
            html = (Path(__file__).resolve().parent / "web" / "index.html").read_text(encoding="utf-8")
            return self._send(200, html.encode("utf-8"), content_type="text/html; charset=utf-8")

        if path.startswith("/static/"):
            fp = Path(__file__).resolve().parent / "web" / path.removeprefix("/static/")
            if not fp.exists() or not fp.is_file():
                return self._send_text(404, "not found")
            ctype = "text/plain; charset=utf-8"
            if fp.suffix == ".js":
                ctype = "text/javascript; charset=utf-8"
            elif fp.suffix == ".css":
                ctype = "text/css; charset=utf-8"
            elif fp.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            data = fp.read_bytes()
            return self._send(200, data, content_type=ctype)

        # API
        if path == "/api/status":
            app.store.load()
            return self._send_json(
                200,
                {
                    "version": __version__,
                    "repo_root": str(app.repo_root),
                    "job": app.job_status(),
                    "sprints": sorted(app.store.list_sprints().keys()),
                },
            )

        if path == "/api/config":
            if not self._require_auth():
                return self._send_json(401, {"error": "unauthorized"})
            return self._send_json(200, app.cfg.to_dict())

        if path == "/api/events":
            app.store.load()
            tail = int(params.get("tail", "200"))
            sprint_id = params.get("sprint_id")
            events = app.bus.recent(max_lines=tail)
            out = []
            for e in events:
                if sprint_id and e.sprint_id != sprint_id:
                    continue
                out.append(e.__dict__)
            return self._send_json(200, out)

        if path == "/api/sprints":
            app.store.load()
            sprints = {sid: s.title for sid, s in app.store.list_sprints().items()}
            return self._send_json(200, {"sprints": sprints})

        if path.startswith("/api/sprints/"):
            app.store.load()
            sid = path.split("/", 3)[3]
            s = app.store.get_sprint(sid)
            if s is None:
                return self._send_json(404, {"error": "not found"})
            from .models import to_jsonable

            return self._send_json(200, to_jsonable(s))

        if path.startswith("/api/artifacts/"):
            # GET /api/artifacts/<sprint_id>/<relpath>
            parts = path.split("/", 4)
            if len(parts) < 4:
                return self._send_json(400, {"error": "bad path"})
            sprint_id = parts[3]
            rel = parts[4] if len(parts) >= 5 else ""
            root = app.store.paths.artifacts_root / sprint_id
            target = (root / rel).resolve()
            if not str(target).startswith(str(root.resolve())):
                return self._send_json(400, {"error": "path traversal blocked"})
            if not target.exists() or not target.is_file():
                return self._send_json(404, {"error": "not found"})
            return self._send(200, target.read_bytes(), content_type="text/plain; charset=utf-8")

        return self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path, _params = self._route()
        app = self._app()

        if path.startswith("/api/") and not self._require_auth():
            return self._send_json(401, {"error": "unauthorized"})

        if path == "/api/config":
            patch = self._parse_json_body()
            cfg = app.update_config(patch)
            return self._send_json(200, cfg.to_dict())

        if path == "/api/sprints":
            body = self._parse_json_body()
            sprint_id = str(body.get("sprint_id") or "").strip()
            title = str(body.get("title") or sprint_id).strip()
            if not sprint_id:
                return self._send_json(400, {"error": "missing sprint_id"})
            app.store.load()
            if app.store.get_sprint(sprint_id) is not None:
                return self._send_json(409, {"error": "sprint exists"})
            s = SprintState(
                sprint_id=sprint_id,
                title=title,
                created_ts=utc_now_iso(),
                status=SprintStatus.CREATED,
                artifacts_dir=str((app.store.paths.artifacts_root / sprint_id).resolve()),
                meta={"created_by": "ui"},
            )
            app.store.upsert_sprint(s)
            app.store.save()
            app.bus.emit(EventKind.SPRINT_CREATED, f"sprint created: {sprint_id}", sprint_id=sprint_id)
            return self._send_json(201, {"ok": True, "sprint_id": sprint_id})

        if path.endswith("/run") and path.startswith("/api/sprints/"):
            sid = path.split("/")[3]

            def _run():
                orch = app.orchestrator()
                orch.run_to_completion(sid)

            ok = app.start_job(f"run:{sid}", _run)
            return self._send_json(202 if ok else 409, {"ok": ok})

        if path.endswith("/step") and path.startswith("/api/sprints/"):
            sid = path.split("/")[3]

            def _step():
                orch = app.orchestrator()
                orch.step(sid)

            ok = app.start_job(f"step:{sid}", _step)
            return self._send_json(202 if ok else 409, {"ok": ok})

        if path.endswith("/cancel") and path.startswith("/api/sprints/"):
            sid = path.split("/")[3]
            app.store.load()
            s = app.store.get_sprint(sid)
            if s is None:
                return self._send_json(404, {"error": "not found"})
            s.status = SprintStatus.CANCELLED
            s.last_error = "cancelled_by_user"
            app.store.upsert_sprint(s)
            app.store.save()
            app.bus.emit(EventKind.NOTE, "sprint cancelled", sprint_id=sid)
            return self._send_json(200, {"ok": True})

        return self._send_json(404, {"error": "not found"})


def serve(*, repo_root: Path, host: str, port: int) -> None:
    app = StudioGatewayApp(repo_root=repo_root)
    srv = ThreadingHTTPServer((host, int(port)), Handler)
    srv.app = app  # type: ignore[attr-defined]
    app.bus.emit(EventKind.NOTE, "studio_gateway daemon started", data={"host": host, "port": int(port)})
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        app.bus.emit(EventKind.NOTE, "studio_gateway daemon stopped")

