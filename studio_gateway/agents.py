from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Protocol


@dataclass(frozen=True)
class ToolPolicy:
    """
    Tool allow/deny at a coarse level.

    This is a control-plane guardrail. The actual enforcement lives where tools are run
    (subprocess wrappers, file mutators, git, etc.).
    """

    allow: tuple[str, ...] = ("read", "exec", "git", "write", "edit")
    deny: tuple[str, ...] = ()

    def is_allowed(self, tool_name: str) -> bool:
        if tool_name in self.deny:
            return False
        if self.allow and tool_name not in self.allow:
            return False
        return True


@dataclass
class AgentProfile:
    agent_id: str
    label: str
    workspace_dir: Path
    state_dir: Path
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)


class LLMProvider(Protocol):
    def complete(self, *, system: str, prompt: str) -> str: ...


class MockProvider:
    """
    Deterministic stand-in for real LLM calls.

    This makes the gateway runnable without keys while keeping the orchestration
    pipeline testable.
    """

    def complete(self, *, system: str, prompt: str) -> str:
        # Keep it short and structured enough to parse in future iterations.
        return (
            "Status: ACK (mock)\n"
            "Deliverables:\n"
            "- No-op (mock provider)\n"
            "Questions:\n"
            "- None\n"
            "Next actions:\n"
            "- Replace MockProvider with a real provider config\n"
        )


def build_default_agent_profiles(*, repo_root: Path) -> Dict[str, AgentProfile]:
    """
    MVP isolation model:
    - per-agent scratch workspace under .studio_gateway/workspaces/<agentId>
    - per-agent state under .studio_gateway/agents/<agentId>
    """

    root = repo_root / ".studio_gateway"
    profiles: Dict[str, AgentProfile] = {}

    # Match your studio naming conventions.
    for n in range(1, 15):
        aid = f"agent_{n:02d}"
        profiles[aid] = AgentProfile(
            agent_id=aid,
            label=aid,
            workspace_dir=root / "workspaces" / aid,
            state_dir=root / "agents" / aid,
            tool_policy=ToolPolicy(),
        )

    # A few sensible restrictive defaults for safety (can be tuned later).
    # Example: Marketing should not edit code.
    profiles["agent_13"].tool_policy = ToolPolicy(allow=("read",), deny=("write", "edit", "git", "exec"))

    return profiles


def provider_from_env() -> LLMProvider:
    """
    Future hook point:
    - wire to OpenAI/Anthropic/Gemini via env/config.

    For now: always return MockProvider so the system is runnable.
    """

    _ = os.environ.get("STUDIO_GATEWAY_LLM", "mock").lower()
    return MockProvider()

