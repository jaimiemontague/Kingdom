from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitRunner:
    repo_root: Path

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, cwd=str(self.repo_root), text=True, capture_output=True)

    def is_clean(self) -> bool:
        cp = self._run(["git", "status", "--porcelain"])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
        return cp.stdout.strip() == ""

    def current_branch(self) -> str:
        cp = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
        return cp.stdout.strip()

    def checkout_new_branch(self, branch: str, *, base: str = "main") -> None:
        cp = self._run(["git", "checkout", base])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
        cp = self._run(["git", "checkout", "-b", branch])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())

    def add_all(self) -> None:
        cp = self._run(["git", "add", "."])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())

    def commit(self, message: str) -> None:
        cp = self._run(["git", "commit", "-m", message])
        if cp.returncode != 0:
            # If nothing to commit, treat as ok for MVP.
            if "nothing to commit" in (cp.stdout + cp.stderr).lower():
                return
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())

    def merge_to_main_and_push(self, branch: str) -> None:
        cp = self._run(["git", "checkout", "main"])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
        cp = self._run(["git", "merge", "--no-ff", branch])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
        cp = self._run(["git", "push"])
        if cp.returncode != 0:
            raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())

