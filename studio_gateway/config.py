from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class GatewayConfig:
    """
    Studio Gateway runtime configuration.

    Stored at `.studio_gateway/config.json` (gitignored).
    """

    # Security / access
    auth_token: str
    bind_host: str = "127.0.0.1"
    port: int = 18790

    # Automation behavior
    enable_auto_merge: bool = False
    automation_paused: bool = False

    # Concurrency
    max_concurrent_global: int = 4

    # Gates (ids only in MVP; contract currently defines the command)
    gate_profile: str = "quick"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "auth_token": self.auth_token,
            "bind_host": self.bind_host,
            "port": self.port,
            "enable_auto_merge": self.enable_auto_merge,
            "automation_paused": self.automation_paused,
            "max_concurrent_global": self.max_concurrent_global,
            "gate_profile": self.gate_profile,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GatewayConfig":
        return cls(
            auth_token=str(d.get("auth_token") or ""),
            bind_host=str(d.get("bind_host") or "127.0.0.1"),
            port=int(d.get("port") or 18790),
            enable_auto_merge=bool(d.get("enable_auto_merge", False)),
            automation_paused=bool(d.get("automation_paused", False)),
            max_concurrent_global=int(d.get("max_concurrent_global") or 4),
            gate_profile=str(d.get("gate_profile") or "quick"),
        )


def config_path(*, repo_root: Path) -> Path:
    return repo_root / ".studio_gateway" / "config.json"


def load_or_create_config(*, repo_root: Path) -> GatewayConfig:
    p = config_path(repo_root=repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        cfg = GatewayConfig.from_dict(d)
        # If token missing, generate once.
        if not cfg.auth_token:
            cfg.auth_token = secrets.token_urlsafe(24)
            save_config(repo_root=repo_root, cfg=cfg)
        return cfg

    cfg = GatewayConfig(auth_token=secrets.token_urlsafe(24))
    save_config(repo_root=repo_root, cfg=cfg)
    return cfg


def save_config(*, repo_root: Path, cfg: GatewayConfig) -> None:
    p = config_path(repo_root=repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

