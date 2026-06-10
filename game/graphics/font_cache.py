"""
Lightweight pygame font cache.

Creating pygame.font.Font objects inside per-frame render loops is expensive and can
cause stutter/lag. This module provides lazy, global caches for fonts (by size) and
optionally for static text surfaces (by size/text/color).

Teardown safety (WK126 suite-crash fix): pygame.font.quit() / pygame.quit() free the
native SDL_ttf handles behind every pygame.font.Font that exists at that moment.
A Font cached here across a quit + re-init cycle is a dangling native pointer —
calling .render() on it is a hard access violation (0xC0000005) the interpreter
cannot catch. To make every caller safe regardless of init/quit ordering:

* an init-cycle generation counter (``_FONT_GENERATION``) is bumped — and all
  caches flushed — whenever pygame teardown runs (``pygame.quit`` and
  ``pygame.font.quit`` are wrapped once at import to do this);
* each cached Font records the generation it was created in; ``get_font`` returns
  a cached Font only if its generation matches (one int compare on the healthy hot
  path — this module is on the per-frame HUD path, FPS guardrails);
* on a miss/stale entry, the font module is (re-)initialised if needed and the
  entry rebuilt.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pygame

# Bumped every time pygame (or its font module) is torn down; cached Font objects
# from an older generation are dangling native handles and must never be used.
_FONT_GENERATION: int = 0

# size -> (generation_created_in, Font)
_FONT_CACHE: Dict[int, Tuple[int, pygame.font.Font]] = {}
_TEXT_CACHE: Dict[Tuple[int, str, Tuple[int, int, int]], pygame.Surface] = {}
_TEXT_SHADOW_CACHE: Dict[
    Tuple[int, str, Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int]],
    pygame.Surface,
] = {}
_TEXT_SHADOW_CACHE_MAX = 512


def _bump_font_generation() -> None:
    """Invalidate every cached font/text surface (pygame teardown is happening)."""
    global _FONT_GENERATION
    _FONT_GENERATION += 1
    _FONT_CACHE.clear()
    _TEXT_CACHE.clear()
    _TEXT_SHADOW_CACHE.clear()


def _install_quit_hooks() -> None:
    """Wrap pygame.quit / pygame.font.quit (once per process) so this module sees
    every teardown and can flush its caches before the native handles are freed.

    pygame.quit() tears down the font module at the C level WITHOUT routing
    through the Python ``pygame.font.quit`` attribute, so both entry points must
    be wrapped. Idempotent via a marker attribute on the pygame module.
    """
    if getattr(pygame, "_kingdom_font_cache_quit_hooked", False):
        return

    _orig_pygame_quit = pygame.quit
    _orig_font_quit = pygame.font.quit

    def _pygame_quit_flush_font_cache(*args, **kwargs):
        _bump_font_generation()
        return _orig_pygame_quit(*args, **kwargs)

    def _font_quit_flush_font_cache(*args, **kwargs):
        _bump_font_generation()
        return _orig_font_quit(*args, **kwargs)

    pygame.quit = _pygame_quit_flush_font_cache
    pygame.font.quit = _font_quit_flush_font_cache
    pygame._kingdom_font_cache_quit_hooked = True


_install_quit_hooks()


def get_font(size: int) -> pygame.font.Font:
    """Get (and cache) the default font at a given size.

    Safe to call in any pygame init state: a cached Font is returned only if it
    was created in the CURRENT pygame init generation (one int compare when
    healthy); otherwise the font module is (re-)initialised if necessary and the
    entry rebuilt — a Font surviving a pygame.quit()/font.quit() cycle is a
    dangling native handle and rendering with it is an uncatchable crash.
    """
    s = int(size)
    entry = _FONT_CACHE.get(s)
    if entry is not None and entry[0] == _FONT_GENERATION:
        return entry[1]
    if not pygame.font.get_init():
        pygame.font.init()
    font = pygame.font.Font(None, s)
    _FONT_CACHE[s] = (_FONT_GENERATION, font)
    return font


def render_text_cached(
    size: int,
    text: str,
    color: Tuple[int, int, int],
    antialias: bool = True,
) -> pygame.Surface:
    """
    Render and cache text surfaces for static labels/icons.

    Avoid using this for rapidly-changing text (e.g. timers) as that would grow the cache.
    """
    key = (int(size), str(text), (int(color[0]), int(color[1]), int(color[2])))
    surf = _TEXT_CACHE.get(key)
    if surf is None:
        surf = get_font(size).render(text, bool(antialias), color)
        _TEXT_CACHE[key] = surf
    return surf


def render_text_shadowed_cached(
    size: int,
    text: str,
    color: Tuple[int, int, int],
    *,
    shadow_color: Tuple[int, int, int] = (0, 0, 0),
    shadow_offset: Tuple[int, int] = (1, 1),
    antialias: bool = True,
) -> pygame.Surface:
    """
    Render a cached, shadowed text surface.

    This is intended for world-space labels where background contrast varies.
    Cache key includes the shadow styling so we avoid per-frame surface allocations.
    """
    key = (
        int(size),
        str(text),
        (int(color[0]), int(color[1]), int(color[2])),
        (int(shadow_color[0]), int(shadow_color[1]), int(shadow_color[2])),
        (int(shadow_offset[0]), int(shadow_offset[1])),
    )
    surf = _TEXT_SHADOW_CACHE.get(key)
    if surf is None:
        # Best-effort cache bound (avoid unbounded growth for frequently-changing numeric labels).
        if len(_TEXT_SHADOW_CACHE) >= _TEXT_SHADOW_CACHE_MAX:
            try:
                _TEXT_SHADOW_CACHE.pop(next(iter(_TEXT_SHADOW_CACHE)))
            except Exception:
                _TEXT_SHADOW_CACHE.clear()
        font = get_font(size)
        main = font.render(str(text), bool(antialias), color)
        shadow = font.render(str(text), bool(antialias), shadow_color)
        ox, oy = int(shadow_offset[0]), int(shadow_offset[1])
        pad_x = max(0, ox)
        pad_y = max(0, oy)
        w = int(main.get_width() + pad_x)
        h = int(main.get_height() + pad_y)
        surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
        if pad_x or pad_y:
            surf.blit(shadow, (pad_x, pad_y))
        else:
            # Offset (0,0): still render shadow first for slight darkening.
            surf.blit(shadow, (0, 0))
        surf.blit(main, (0, 0))
        _TEXT_SHADOW_CACHE[key] = surf
    return surf










