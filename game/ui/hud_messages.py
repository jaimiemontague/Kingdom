"""HUD status-message log, extracted from game.ui.hud (WK102).

Append/expire/draw the short status messages (e.g. combat-kill notices) shown at
the top of the screen. add_message FIFO-caps at 5; update() prunes entries older
than hud.message_duration (3000ms); render_messages draws the stack at
top_bar_height+10. All message STATE (hud.messages, hud.message_duration) and the
fonts (hud.font_small) live on the HUD instance and are reached here via the ``hud``
argument; HUD keeps 1-line delegating wrappers (exact names: add_message, update,
render_messages -- update() is called every frame by engine.py). Acyclic: hud.py
imports this module lazily inside the wrappers; this module imports only pygame +
config.COLOR_WHITE (config does NOT import game.ui) + game.ui.widgets (leaf module,
no hud import) + HUD under TYPE_CHECKING.

Mythos S3 (hud-compose-trims): render_messages re-ran ``font.render`` for every
visible message EVERY frame; it now reuses the bounded global text-surface cache
(``TextLabel.get_surface``, game/ui/widgets.py) keyed (font, text, color) — same
pixels, ~zero per-frame cost while the message list is unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from config import COLOR_WHITE
from game.ui.widgets import TextLabel

if TYPE_CHECKING:
    from game.ui.hud import HUD


def add_message(hud: "HUD", text: str, color: tuple[int, int, int] = COLOR_WHITE) -> None:
    hud.messages.append({"text": text, "color": color, "time": pygame.time.get_ticks()})
    if len(hud.messages) > 5:
        hud.messages.pop(0)


def update_messages(hud: "HUD") -> None:
    current_time = pygame.time.get_ticks()
    hud.messages = [msg for msg in hud.messages if current_time - msg["time"] < hud.message_duration]


def render_messages(hud: "HUD", surface: pygame.Surface, left_rect: pygame.Rect | None = None) -> None:
    y_offset = hud.top_bar_height + 10
    x_offset = 10
    if left_rect and left_rect.width > 0:
        x_offset = left_rect.right + 10
    for msg in hud.messages:
        color = msg["color"]
        if isinstance(color, (tuple, list)) and len(color) == 3:
            # Cached path (mythos hud-compose-trims): identical to font.render —
            # TextLabel.get_surface calls the same render on first miss.
            text = TextLabel.get_surface(hud.font_small, msg["text"], color)
        else:
            # Exotic color objects (alpha, pygame.Color) keep the direct render.
            text = hud.font_small.render(msg["text"], True, color)
        surface.blit(text, (x_offset, y_offset))
        y_offset += 18
