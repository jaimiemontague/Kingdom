"""Toast notifications for the HUD (WK94 slice of hud.py).

Extracted VERBATIM from game/ui/hud.py (WK94 Round B-11): the toast subsystem —
the wave-event toast (``on_wave_incoming`` / ``on_wave_cleared`` / ``render_wave_toast``,
WK60) and the POI discovery/interaction toast cluster (``notify_poi_discovered`` /
``check_poi_discoveries`` / ``ensure_poi_interaction_subscription`` / ``on_poi_interaction``
/ ``on_boss_spawned_toast`` / ``render_poi_toasts``, WK55/WK58/WK59). All toast STATE
(``_poi_toasts``, ``_wave_toast_*``, etc.) lives on the HUD instance and is accessed here
via the ``hud`` argument. HUD keeps 1-line delegating wrappers (same names + signatures,
including the leading-underscore private names that engine.py EventBus subscriptions and
render() call) so the call sites are unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from game.ui.hud import HUD


# ------------------------------------------------------------------
# WK60: Wave event toast API (consumed by engine EventBus subscription)
# ------------------------------------------------------------------

def on_wave_incoming(hud: "HUD", event: dict) -> None:
    """Handle 'wave_incoming' EventBus event — show a prominent countdown toast."""
    name = event.get("name", "Unknown Wave")
    seconds = int(event.get("seconds", 10))
    hud._wave_toast_text = f"INCOMING: {name}!"
    hud._wave_toast_color = (255, 100, 100)
    hud._wave_toast_start_ms = pygame.time.get_ticks()
    hud._wave_toast_duration_ms = (seconds + 2) * 1000  # show for countdown duration + 2s
    hud._wave_toast_countdown_end_ms = pygame.time.get_ticks() + seconds * 1000


def on_wave_cleared(hud: "HUD", event: dict) -> None:
    """Handle 'wave_cleared' EventBus event — show a reward toast."""
    name = event.get("name", "Wave")
    reward = int(event.get("reward", 0))
    hud._wave_toast_text = f"Wave Cleared! +{reward} Gold"
    hud._wave_toast_color = (255, 215, 0)
    hud._wave_toast_start_ms = pygame.time.get_ticks()
    hud._wave_toast_duration_ms = 4000
    hud._wave_toast_countdown_end_ms = 0  # no countdown for cleared


def render_wave_toast(hud: "HUD", surface: pygame.Surface) -> None:
    """Render the wave event toast banner (centered, top-center area)."""
    if hud._wave_toast_text is None:
        return
    now = pygame.time.get_ticks()
    elapsed = now - hud._wave_toast_start_ms
    if elapsed > hud._wave_toast_duration_ms:
        hud._wave_toast_text = None
        return

    # Build display text with optional countdown
    display_text = hud._wave_toast_text
    if hud._wave_toast_countdown_end_ms > 0:
        remaining_sec = max(0, (hud._wave_toast_countdown_end_ms - now) / 1000.0)
        if remaining_sec > 0:
            display_text = f"{hud._wave_toast_text} ({int(remaining_sec)}s)"

    # Fade in/out
    alpha = 255
    fade_ms = 400
    if elapsed < fade_ms:
        alpha = int(255 * elapsed / fade_ms)
    elif elapsed > hud._wave_toast_duration_ms - fade_ms:
        alpha = int(255 * (hud._wave_toast_duration_ms - elapsed) / fade_ms)
    alpha = max(0, min(255, alpha))

    text_surf = hud._wave_toast_font.render(display_text, True, hud._wave_toast_color)
    tw, th = text_surf.get_size()
    pad_x, pad_y = 20, 8
    banner_w = tw + pad_x * 2
    banner_h = th + pad_y * 2

    # Position: top-center, below top bar
    bx = (surface.get_width() - banner_w) // 2
    by = hud.top_bar_height + 8

    bg = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
    bg.fill((20, 20, 40, min(200, alpha)))
    pygame.draw.rect(bg, (*hud._wave_toast_color, min(180, alpha)), (0, 0, banner_w, banner_h), 2)
    surface.blit(bg, (bx, by))

    text_surf.set_alpha(alpha)
    surface.blit(text_surf, (bx + pad_x, by + pad_y))


def notify_poi_discovered(hud: "HUD", poi_name: str, interaction_type: str = "") -> None:
    """Queue a POI discovery toast notification."""
    msg = f"Discovered: {poi_name}"
    hud._poi_toasts.append((msg, float(hud._POI_TOAST_DURATION_MS), interaction_type))
    if len(hud._poi_toasts) > 3:
        hud._poi_toasts.pop(0)


def check_poi_discoveries(hud: "HUD", game_state: dict) -> None:
    """Scan buildings for newly discovered POIs and fire toasts."""
    buildings = game_state.get("buildings", [])
    for b in buildings:
        if not getattr(b, "is_poi", False):
            continue
        if not getattr(b, "is_discovered", False):
            continue
        poi_def = getattr(b, "poi_def", None)
        if poi_def is None:
            continue
        b_id = id(b)
        if b_id in hud._poi_toast_ids:
            continue
        hud._poi_toast_ids.add(b_id)
        name = getattr(poi_def, "display_name", None) or "Unknown POI"
        itype = getattr(poi_def, "interaction_type", "") or ""
        hud.notify_poi_discovered(str(name), interaction_type=str(itype))
        # Play discovery chime via engine audio system
        engine = game_state.get("engine")
        if engine is not None:
            audio = getattr(engine, "audio_system", None)
            if audio is not None:
                audio.play_sfx("poi_discovered")


# ------------------------------------------------------------------
# POI interaction toasts (WK59)
# ------------------------------------------------------------------

def ensure_poi_interaction_subscription(hud: "HUD", game_state: dict) -> None:
    """Lazily subscribe to poi_interaction / boss_spawned events on first render."""
    if hud._poi_interaction_subscribed:
        return
    sim = game_state.get("sim")
    if sim is None:
        return
    bus = getattr(sim, "event_bus", None)
    if bus is None:
        return
    bus.subscribe("poi_interaction", hud._on_poi_interaction)
    bus.subscribe("boss_spawned", hud._on_boss_spawned_toast)
    hud._poi_interaction_subscribed = True


def on_poi_interaction(hud: "HUD", event: dict) -> None:
    """EventBus callback: format and queue a toast for a POI interaction."""
    itype = event.get("interaction_type", "")
    hero_name = event.get("hero_name", "A hero")
    poi_name = event.get("poi_name", "a place of interest")

    if itype == "shrine":
        buff = event.get("buff_attack", 0)
        msg = f"{hero_name} prayed at {poi_name}. HP restored! ATK +{buff}"
    elif itype == "loot":
        gold = event.get("gold", 0)
        msg = f"{hero_name} found treasure at {poi_name}! +{gold} gold"
    elif itype == "combat":
        msg = f"Enemies emerge from {poi_name}!"
    elif itype == "knowledge":
        revealed = event.get("revealed_poi_name")
        suffix = "A hidden location is revealed!" if revealed else "The fog parts..."
        msg = f"{hero_name} reads ancient text at {poi_name}. {suffix}"
    elif itype == "npc":
        msg = f"A figure beckons from {poi_name}..."
    elif itype == "dungeon":
        msg = f"{hero_name} peers into {poi_name}..."
    else:
        return  # Unknown interaction type, skip toast

    hud._poi_toasts.append((msg, float(hud._POI_TOAST_DURATION_MS), itype))
    if len(hud._poi_toasts) > 3:
        hud._poi_toasts.pop(0)


def on_boss_spawned_toast(hud: "HUD", event: dict) -> None:
    """EventBus callback: format and queue a toast for a boss spawn."""
    poi_name = event.get("poi_name", "a place of interest")
    msg = f"A powerful foe appears at {poi_name}!"
    hud._poi_toasts.append((msg, float(hud._POI_TOAST_DURATION_MS), "boss"))
    if len(hud._poi_toasts) > 3:
        hud._poi_toasts.pop(0)


def render_poi_toasts(hud: "HUD", surface: pygame.Surface) -> None:
    """Render and tick POI discovery toast notifications (WK55 polish)."""
    if not hud._poi_toasts:
        return

    now_ms = pygame.time.get_ticks()
    dt_ms = float(now_ms - hud._poi_last_tick_ms)
    hud._poi_last_tick_ms = now_ms

    screen_w = surface.get_width()
    y_offset = hud.top_bar_height + 16

    # POI type -> dot color (matches minimap palette)
    _type_colors = {
        "shrine": (100, 180, 255),
        "loot": (255, 215, 0),
        "combat": (220, 120, 30),
        "knowledge": (180, 100, 255),
        "npc": (100, 200, 100),
        "dungeon": (160, 40, 40),
        "boss": (255, 50, 50),
    }

    duration = float(hud._POI_TOAST_DURATION_MS)
    fade_ms = hud._POI_TOAST_FADE_MS

    remaining: list[tuple[str, float, str]] = []
    for msg, time_left_ms, itype in hud._poi_toasts:
        time_left_ms -= dt_ms
        if time_left_ms <= 0:
            continue
        remaining.append((msg, time_left_ms, itype))

        # Compute alpha: fade-in during first fade_ms, fade-out during last fade_ms
        elapsed_ms = duration - time_left_ms
        if elapsed_ms < fade_ms:
            # Fade in
            alpha = max(0, min(255, int(elapsed_ms * 255 / fade_ms)))
        elif time_left_ms < fade_ms:
            # Fade out
            alpha = max(0, min(255, int(time_left_ms * 255 / fade_ms)))
        else:
            alpha = 255

        text_surf = hud._poi_toast_font.render(msg, True, (255, 255, 220))
        tw, th = text_surf.get_size()
        dot_radius = 5
        dot_padding = dot_radius * 2 + 8  # space for colored dot on left
        bg_w = tw + dot_padding + 20
        bg_h = th + 14
        bg_x = (screen_w - bg_w) // 2

        # Draw background pill
        bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
        bg.fill((20, 20, 40, min(210, alpha)))
        # Rounded-corner border highlight
        pygame.draw.rect(bg, (80, 80, 120, min(140, alpha)), bg.get_rect(), 1, border_radius=4)
        surface.blit(bg, (bg_x, y_offset))

        # Draw colored type dot
        dot_color = _type_colors.get(itype, (180, 180, 180))
        dot_x = bg_x + dot_radius + 8
        dot_y = y_offset + bg_h // 2
        dot_surf = pygame.Surface((dot_radius * 2 + 2, dot_radius * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(dot_surf, (*dot_color, alpha), (dot_radius + 1, dot_radius + 1), dot_radius)
        surface.blit(dot_surf, (dot_x - dot_radius - 1, dot_y - dot_radius - 1))

        # Draw text
        text_surf.set_alpha(alpha)
        surface.blit(text_surf, (bg_x + dot_padding + 6, y_offset + 7))

        y_offset += bg_h + 6

    hud._poi_toasts = remaining
