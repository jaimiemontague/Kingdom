"""Temple panel renderer.

Temples share the same panel layout as guild-type hiring buildings.
"""

from __future__ import annotations

from .guild_panel import GuildPanelRenderer


class TemplePanelRenderer(GuildPanelRenderer):
    """Temple renderer currently reuses guild presentation."""

