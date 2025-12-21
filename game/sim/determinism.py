"""
Determinism helpers.

Goals:
- Provide a single seeded RNG for gameplay state (spawns, procedural world, etc.)
- Provide stable sub-streams derived from a base seed (avoid hidden coupling between systems)

Non-goals:
- Cryptographic security
- Perfect cross-language reproducibility (this is Python's Mersenne Twister)
"""

from __future__ import annotations

import random
import zlib
from typing import Optional

_BASE_SEED: int = 1
_GLOBAL_RNG: random.Random = random.Random(_BASE_SEED)


def set_sim_seed(seed: int) -> None:
    """Set the base seed used for deterministic simulation RNG."""
    global _BASE_SEED, _GLOBAL_RNG
    _BASE_SEED = int(seed) & 0xFFFFFFFF
    _GLOBAL_RNG = random.Random(_BASE_SEED)


def _derive_seed(tag: str) -> int:
    # Use stable hashing (NEVER Python's built-in hash(), which is randomized per process).
    crc = zlib.crc32(tag.encode("utf-8")) & 0xFFFFFFFF
    return (_BASE_SEED ^ crc) & 0xFFFFFFFF


def get_rng(tag: Optional[str] = None) -> random.Random:
    """
    Get the global gameplay RNG, or a deterministic sub-RNG for a specific system.

    - If `tag` is None: returns the shared global RNG (sequence depends on call order).
    - If `tag` is provided: returns an independent RNG stream derived from the base seed.
    """
    if tag is None:
        return _GLOBAL_RNG
    return random.Random(_derive_seed(str(tag)))


