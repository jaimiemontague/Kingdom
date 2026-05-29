"""Bounty rendering moved from game.systems.bounty."""

from __future__ import annotations

import pygame

from game.graphics.font_cache import get_font


class BountyRenderer:
    """Render-only bounty marker rendering.

    WK66 L2: the rendered text surfaces are cached in a renderer-owned dict keyed
    by ``bounty_id`` (was nine ``_ui_cache_*`` attributes stamped on the live
    ``Bounty`` — a render-to-sim write-back). The renderer no longer mutates the
    bounty object.
    """

    def __init__(self) -> None:
        # bounty_id -> {"reward_val", "reward_surf", "reward_rect",
        #               "meta_key", "r_surf", "r_w", "a_surf"}
        self._cache: dict[str, dict] = {}

    def render_bounty(
        self,
        surface: pygame.Surface,
        bounty: object,
        camera_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """Render a single bounty flag."""
        if bool(getattr(bounty, "claimed", False)):
            return

        cam_x, cam_y = camera_offset
        screen_x = float(getattr(bounty, "x", 0.0)) - float(cam_x)
        screen_y = float(getattr(bounty, "y", 0.0)) - float(cam_y)

        bid = str(getattr(bounty, "bounty_id", None) or id(bounty))
        entry = self._cache.get(bid)
        if entry is None:
            entry = {}
            self._cache[bid] = entry

        pygame.draw.line(
            surface,
            (80, 50, 25),
            (screen_x, screen_y),
            (screen_x, screen_y - 30),
            5,
        )
        pygame.draw.line(
            surface,
            (139, 90, 43),
            (screen_x, screen_y),
            (screen_x, screen_y - 30),
            3,
        )

        flag_points = [
            (screen_x, screen_y - 30),
            (screen_x + 20, screen_y - 25),
            (screen_x, screen_y - 20),
        ]
        pygame.draw.polygon(surface, (100, 80, 0), flag_points)
        pygame.draw.polygon(surface, (255, 215, 0), flag_points)

        font = get_font(16)
        reward_val = int(getattr(bounty, "reward", 0) or 0)
        cached_surf = entry.get("reward_surf")
        cached_rect = entry.get("reward_rect")
        if entry.get("reward_val") != reward_val or cached_surf is None:
            entry["reward_val"] = reward_val
            cached_surf = font.render(f"${reward_val}", True, (255, 255, 255))
            cached_rect = cached_surf.get_rect(center=(0, 0))
            entry["reward_surf"] = cached_surf
            entry["reward_rect"] = cached_rect

        if cached_surf is not None and cached_rect is not None:
            rect = cached_rect.copy()
            rect.center = (screen_x + 10, screen_y - 35)
            surface.blit(cached_surf, rect)

        responders = int(getattr(bounty, "responders", getattr(bounty, "ui_responders", 0)) or 0)
        tier = str(
            getattr(
                bounty,
                "attractiveness_tier",
                getattr(bounty, "ui_attractiveness", "low"),
            )
            or "low"
        ).lower()
        tier_label = {"low": "Low", "med": "Med", "high": "High"}.get(tier, "Low")
        tier_color = {
            "low": (150, 150, 150),
            "med": (240, 210, 90),
            "high": (110, 230, 140),
        }.get(tier, (150, 150, 150))

        meta_font = get_font(14)
        meta_key = (responders, tier)
        if (
            entry.get("meta_key") != meta_key
            or entry.get("r_surf") is None
            or entry.get("a_surf") is None
        ):
            entry["meta_key"] = meta_key
            r_surf = meta_font.render(f"R:{responders}", True, (255, 255, 255))
            entry["r_surf"] = r_surf
            entry["r_w"] = int(r_surf.get_width())
            entry["a_surf"] = meta_font.render(tier_label, True, tier_color)

        r_surf = entry.get("r_surf")
        a_surf = entry.get("a_surf")
        r_w = int(entry.get("r_w", 0) or 0)

        if r_surf is not None:
            surface.blit(r_surf, (screen_x + 24, screen_y - 18))
        if a_surf is not None:
            surface.blit(a_surf, (screen_x + 24 + r_w + 6, screen_y - 18))

    def render_all(
        self,
        surface: pygame.Surface,
        bounties: list[object],
        camera_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """Render all active bounties."""
        active_ids: set[str] = set()
        for bounty in bounties:
            active_ids.add(str(getattr(bounty, "bounty_id", None) or id(bounty)))
            self.render_bounty(surface, bounty, camera_offset)
        # Drop cached surfaces for bounties that are gone (claimed/expired).
        stale = set(self._cache.keys()) - active_ids
        for bid in stale:
            self._cache.pop(bid, None)
