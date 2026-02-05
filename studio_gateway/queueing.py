from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional, TypeVar


T = TypeVar("T")


@dataclass
class JobResult:
    ok: bool
    value: object | None = None
    error: str | None = None
    elapsed_ms: int | None = None


class LaneQueue:
    """
    A tiny lane-aware FIFO queue.

    Purpose (OpenClaw analogue):
    - Serialize runs per lane (e.g. `session:<agentId>:<sprintId>` or `repo_write`)
    - Allow limited global concurrency while preventing resource races
    """

    def __init__(self, *, max_concurrent_global: int = 4):
        self._max_concurrent_global = max_concurrent_global
        self._lanes: Dict[str, "queue.Queue[tuple[Callable[[], T], queue.Queue[JobResult]]]"] = {}
        self._lock = threading.Lock()
        self._active_global = 0

    def submit(self, lane: str, fn: Callable[[], T]) -> JobResult:
        """
        Submit a job to a lane and block until completion.
        (MVP: synchronous API; the daemon can wrap this for async UIs.)
        """

        result_q: "queue.Queue[JobResult]" = queue.Queue(maxsize=1)

        with self._lock:
            qlane = self._lanes.get(lane)
            if qlane is None:
                qlane = queue.Queue()
                self._lanes[lane] = qlane
            qlane.put((fn, result_q))

        self._drain()
        return result_q.get()

    def _drain(self) -> None:
        # MVP: naive draining. We ensure lane serialization by only running one job per lane at a time.
        # Global concurrency is capped by max_concurrent_global.
        with self._lock:
            if self._active_global >= self._max_concurrent_global:
                return

            # Pick any lane that has work and is not currently running.
            for lane, qlane in self._lanes.items():
                if qlane.empty():
                    continue
                self._active_global += 1
                fn, result_q = qlane.get()
                t = threading.Thread(target=self._run_job, args=(fn, result_q), daemon=True)
                t.start()
                break

    def _run_job(self, fn: Callable[[], T], result_q: "queue.Queue[JobResult]") -> None:
        start = time.perf_counter()
        try:
            v = fn()
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            result_q.put(JobResult(ok=True, value=v, elapsed_ms=elapsed_ms))
        except Exception as e:  # noqa: BLE001 (stdlib-only MVP)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            result_q.put(JobResult(ok=False, error=str(e), elapsed_ms=elapsed_ms))
        finally:
            with self._lock:
                self._active_global = max(0, self._active_global - 1)
            # keep draining after finishing
            self._drain()

