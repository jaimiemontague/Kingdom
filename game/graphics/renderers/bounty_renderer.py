"""Bounty rendering moved from game.systems.bounty."""

from __future__ import annotations

import pygame

from game.graphics.font_cache import get_font


class BountyRenderer:
    """Render-only bounty marker rendering."""

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
        cached_reward = getattr(bounty, "_ui_cache_reward_value", None)
        cached_surf = getattr(bounty, "_ui_cache_reward_surf", None)
        cached_rect = getattr(bounty, "_ui_cache_reward_rect", None)
        if cached_reward != reward_val or cached_surf is None:
            setattr(bounty, "_ui_cache_reward_value", reward_val)
            cached_surf = font.render(f"${reward_val}", True, (255, 255, 255))
            cached_rect = cached_surf.get_rect(center=(0, 0))
            setattr(bounty, "_ui_cache_reward_surf", cached_surf)
            setattr(bounty, "_ui_cache_reward_rect", cached_rect)

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
            getattr(bounty, "_ui_cache_meta_key", None) != meta_key
            or getattr(bounty, "_ui_cache_r_surf", None) is None
            or getattr(bounty, "_ui_cache_a_surf", None) is None
        ):
            setattr(bounty, "_ui_cache_meta_key", meta_key)
            r_surf = meta_font.render(f"R:{responders}", True, (255, 255, 255))
            setattr(bounty, "_ui_cache_r_surf", r_surf)
            setattr(bounty, "_ui_cache_r_w", int(r_surf.get_width()))
            setattr(bounty, "_ui_cache_a_surf", meta_font.render(tier_label, True, tier_color))

        r_surf = getattr(bounty, "_ui_cache_r_surf", None)
        a_surf = getattr(bounty, "_ui_cache_a_surf", None)
        r_w = int(getattr(bounty, "_ui_cache_r_w", 0) or 0)

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
        for bounty in bounties:
            self.render_bounty(surface, bounty, camera_offset)
