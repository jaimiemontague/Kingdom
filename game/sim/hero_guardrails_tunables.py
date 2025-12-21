"""
WK2 Hero AI guardrails — locked tunables.

Purpose:
- Provide a single, cycle-free place for AI/QA/Tools to import the *same* thresholds.
- Keep units explicit and determinism-friendly (no wall-clock; values are plain numbers).

These values are locked by PM for WK2 Build A:
see PM hub: agent_01 ExecutiveProducer_PM → wk2-hero-polish-ai-sprites / wk2_r1 / pm_decisions.acceptance_thresholds_locked
"""

from __future__ import annotations

# -----------------------------
# Stuck detection / recovery
# -----------------------------

# If a hero intends to move but has moved less than this many tiles over the window,
# they are considered "not making progress" (paired with STUCK_TIME_S).
STUCK_DISPLACEMENT_TILES_THRESHOLD: float = 0.25

# Time window (seconds, simulation time) before declaring a hero stuck.
STUCK_TIME_S: float = 2.0

# Max deterministic recovery attempts per target/goal before falling back (e.g., reset goal/patrol).
UNSTUCK_MAX_ATTEMPTS_PER_TARGET: int = 3

# Minimum delay between recovery attempts (seconds, simulation time).
UNSTUCK_BACKOFF_S: float = 0.5


# -----------------------------
# Anti-oscillation
# -----------------------------

# Minimum time (seconds, simulation time) to "commit" to a target before retargeting.
TARGET_COMMIT_WINDOW_S: float = 1.5

# Minimum time (seconds, simulation time) to "commit" to a bounty before switching (unless invalid).
BOUNTY_COMMIT_WINDOW_S: float = 2.5


# -----------------------------
# Override rules (documentation)
# -----------------------------

# NOTE (policy, not code):
# Commitment windows should be overridden immediately for:
# - target died/invalid
# - bounty removed/claimed
# - target unreachable


