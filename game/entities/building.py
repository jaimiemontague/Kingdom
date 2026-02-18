"""
Backward-compatible building import shim.

This module intentionally re-exports all public building symbols from
`game.entities.buildings` so external imports do not need to change.
"""

from game.entities.buildings import *  # noqa: F401,F403
