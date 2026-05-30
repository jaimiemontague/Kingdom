"""
WK20 — Ursina input debug telemetry (Agent 12 / Tools).

WK67 Round A-2 (L9): the telemetry helpers moved verbatim into
``game.graphics.ursina_input_debug`` (sever the ``game/graphics -> tools`` runtime
import). This module is now a thin **re-export** so any existing tools consumer keeps
importing these symbols from ``tools.ursina_input_debug`` unchanged. ``tools`` ->
``game`` is the allowed (non-circular) import direction.

Activated when environment variable KINGDOM_URSINA_DEBUG_INPUT=1.
Emits a single WK20_INPUT line per left-mouse-button press (rising edge).
Telemetry only; does not touch simulation state.
"""

from __future__ import annotations

from game.graphics.ursina_input_debug import (  # noqa: F401
    ENV_KEY,
    is_ursina_debug_input_enabled,
    maybe_print_wk20_input_on_lmb,
    print_wk20_input_line,
)
