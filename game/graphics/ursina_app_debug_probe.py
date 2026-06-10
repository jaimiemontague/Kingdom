"""Env-gated debug-layout + FPS-probe + auto-screenshot scaffolding, extracted from game/graphics/ursina_app.py (WK105 slice).

All 8 members are dead-by-default (gated behind KINGDOM_URSINA_* env flags / the auto-exit path).
The 7 instance methods take owner=UrsinaApp first (self.->owner.); _save_window_screenshot_sync is a
plain module function (was a @staticmethod). UrsinaApp keeps 1-line delegating wrappers (exact names).
Acyclic: ursina_app.py imports this module one-way (lazily, in the wrappers); this module imports
UrsinaApp ONLY under TYPE_CHECKING and keeps all heavy (ursina/panda3d/game.entities) imports
function-local.
"""
from __future__ import annotations

import os
import time as pytime
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from game.graphics.ursina_app import UrsinaApp


def _add_wk30_debug_prefab_layout(owner) -> None:
    """WK30 debug: place one of each prefab-backed building near the castle.

    Used by Agent 03 + Jaimie for prefab-fit iteration. Places castle + warrior /
    ranger / rogue / wizard guilds + inn + a house fully constructed in a row east of the
    castle so a single default-framed screenshot shows every prefab against the tile
    grid. Uses ``engine.building_factory`` so any future building-subclass wiring
    (occupancy, researchers, etc.) is consistent with the player-placed path.
    """
    engine = owner.engine
    castle = next(
        (
            b
            for b in engine.buildings
            if getattr(b, "building_type", None) == "castle"
        ),
        None,
    )
    if castle is None:
        print("[wk30-debug-layout] no castle in engine; skipping prefab row")
        return

    factory = getattr(engine, "building_factory", None)
    if factory is None:
        print("[wk30-debug-layout] engine.building_factory missing; skipping")
        return

    # Anchor the row 2 tiles east of the castle's east edge, aligned with its north row.
    base_x = int(castle.grid_x) + int(castle.size[0]) + 2
    base_y = int(castle.grid_y)

    # (building_type, dx) — dx chosen to leave one tile of gap between footprints
    # (2x2 guilds at +0/+3/+6/+9, 3x2 inn at +12, 1x1 house at +16). House is not in BuildingFactory
    # (it's spawned by peasants, not the build menu), so build it via the base class.
    layout = [
        ("warrior_guild", 0),
        ("ranger_guild", 3),
        ("rogue_guild", 6),
        ("wizard_guild", 9),
        ("inn", 12),
        ("house", 16),
    ]
    only = os.environ.get("KINGDOM_URSINA_PREFAB_TEST_LAYOUT_ONLY", "").strip().lower()
    if only:
        layout = [(bts, dx) for (bts, dx) in layout if bts == only]
    from game.entities.buildings.base import Building
    from game.entities.buildings.types import BuildingType

    for bts, dx in layout:
        try:
            if bts == "house":
                b = Building(base_x + dx, base_y, BuildingType.HOUSE)
            else:
                b = factory.create(bts, base_x + dx, base_y)
            if b is None:
                print(f"[wk30-debug-layout] factory returned None for {bts}")
                continue
            if hasattr(b, "is_constructed"):
                b.is_constructed = True
            if hasattr(b, "construction_started"):
                b.construction_started = True
            engine.buildings.append(b)
            if hasattr(b, "set_event_bus") and getattr(engine, "event_bus", None):
                b.set_event_bus(engine.event_bus)
        except Exception as exc:
            print(f"[wk30-debug-layout] skipped {bts}: {exc}")

    # Reveal the entire map so fog-of-war does not hide the test row.
    try:
        from game.world import Visibility

        world = engine.world
        for ty in range(int(world.height)):
            for tx in range(int(world.width)):
                world.visibility[ty][tx] = Visibility.VISIBLE
        engine._fog_revision = int(getattr(engine, "_fog_revision", 0)) + 1
    except Exception as exc:
        print(f"[wk30-debug-layout] fog reveal failed: {exc}")


def _install_worker_scale_comparison_shot(owner) -> None:
    """Place one warrior + one peasant beside the castle for Ursina scale QA (see tools/run_worker_scale_ursina_shot.py)."""
    from config import TILE_SIZE

    from game.entities.hero import Hero
    from game.entities.peasant import Peasant

    eng = owner.engine
    castle = next((b for b in eng.buildings if getattr(b, "building_type", "") == "castle"), None)
    if castle is None:
        print("[worker-scale-shot] no castle; skipping")
        return
    cx = float(getattr(castle, "center_x", 0.0))
    cy = float(getattr(castle, "center_y", 0.0))
    wx = cx + TILE_SIZE * 2.5
    wy = cy
    px = wx + TILE_SIZE * 1.0
    py = wy
    # Isolate one warrior vs one peasant (default match spawns many heroes + tax collector).
    eng.heroes.clear()
    eng.heroes.append(Hero(wx, wy, hero_class="warrior"))
    eng.peasants.clear()
    eng.peasants.append(Peasant(px, py))
    eng.tax_collector = None
    eng.enemies.clear()
    eng.guards.clear()
    setattr(eng.sim, "_worker_scale_shot_hold", True)
    if hasattr(eng, "screenshot_hide_ui"):
        eng.screenshot_hide_ui = True
    try:
        z = float(getattr(eng, "zoom", 1.0) or 1.0)
        eng.zoom = max(z, 2.25)
    except Exception:
        pass


def _add_hero_fps_probe_layout(owner, hero_count: int) -> None:
    """WK32 r5 debug: deterministic warrior guild + N warriors for renderer FPS probes."""
    engine = owner.engine
    castle = next(
        (
            b
            for b in engine.buildings
            if getattr(b, "building_type", None) == "castle"
        ),
        None,
    )
    if castle is None:
        print("[hero-fps-probe] no castle in engine; skipping scenario")
        return

    try:
        from game.entities import WarriorGuild
        from game.entities.hero import Hero

        guild = WarriorGuild(int(castle.grid_x) - 4, int(castle.grid_y) + 2)
        guild.is_constructed = True
        guild.construction_started = True
        if hasattr(guild, "set_event_bus"):
            guild.set_event_bus(engine.event_bus)
        engine.buildings.append(guild)
        if os.environ.get("KINGDOM_URSINA_DISABLE_NEUTRAL_SPAWN", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            neutral = getattr(engine, "neutral_building_system", None)
            if neutral is not None:
                neutral.spawn_interval_sec = 999999.0

        for idx in range(max(0, int(hero_count))):
            hero = Hero(
                guild.center_x + config.TILE_SIZE + (idx % 3) * 10,
                guild.center_y + (idx // 3) * 10,
                hero_class="warrior",
            )
            hero.home_building = guild
            engine.heroes.append(hero)

        # Keep the probe view deterministic without revealing the whole map; full-map
        # visibility would benchmark terrain draw count instead of hero-spawn cost.
        try:
            from game.world import Visibility

            world = engine.world
            cx = int(getattr(castle, "grid_x", 0))
            cy = int(getattr(castle, "grid_y", 0))
            radius = 14
            for ty in range(max(0, cy - radius), min(int(world.height), cy + radius + 1)):
                for tx in range(max(0, cx - radius), min(int(world.width), cx + radius + 1)):
                    world.visibility[ty][tx] = Visibility.VISIBLE
            engine._fog_revision = int(getattr(engine, "_fog_revision", 0)) + 1
        except Exception:
            pass

        print(f"[hero-fps-probe] spawned warrior_guild heroes={len(engine.heroes)}")
    except Exception as exc:
        print(f"[hero-fps-probe] setup failed: {exc}")


def _record_fps_probe_sample(owner, dt: float) -> None:
    if not owner._fps_probe_enabled:
        return
    owner._fps_probe_elapsed += float(dt or 0.0)
    if owner._fps_probe_elapsed < owner._fps_probe_warmup_sec:
        return
    if dt > 1e-9:
        owner._fps_probe_samples.append(1.0 / float(dt))
        # Mythos S0 (`gate-measurement-harness`): also bucket the sample into the
        # optional wall-clock acceptance window (KINGDOM_URSINA_FPS_WINDOW_SEC, parsed
        # once in UrsinaApp.__init__). Dead unless that env is set.
        win = getattr(owner, "_fps_probe_window_sec", None)
        if win is not None and win[0] <= owner._fps_probe_elapsed <= win[1]:
            samples = getattr(owner, "_fps_probe_window_samples", None)
            if samples is not None:
                samples.append(1.0 / float(dt))


def _record_fps_probe_stage_ms(owner, name: str, started_at: float) -> None:
    if not owner._fps_probe_enabled or owner._fps_probe_elapsed < owner._fps_probe_warmup_sec:
        return
    owner._fps_probe_stage_samples.setdefault(name, []).append((pytime.perf_counter() - started_at) * 1000.0)


def _print_fps_probe_summary(owner) -> None:
    if not owner._fps_probe_enabled:
        return
    samples = list(owner._fps_probe_samples)
    if not samples:
        print("[fps-probe] no samples collected")
        return
    samples.sort()
    avg = sum(samples) / len(samples)
    p10 = samples[max(0, int(len(samples) * 0.10) - 1)]
    p50 = samples[max(0, int(len(samples) * 0.50) - 1)]
    p90 = samples[max(0, int(len(samples) * 0.90) - 1)]
    print(
        "[fps-probe] "
        f"heroes={len(getattr(owner.engine, 'heroes', []))} "
        f"frames={len(samples)} "
        f"avg_fps={avg:.1f} "
        f"min_fps={samples[0]:.1f} "
        f"p10_fps={p10:.1f} "
        f"p50_fps={p50:.1f} "
        f"p90_fps={p90:.1f} "
        f"max_fps={samples[-1]:.1f}"
    )
    for name, values in sorted(owner._fps_probe_stage_samples.items()):
        vals = sorted(values)
        if not vals:
            continue
        avg_ms = sum(vals) / len(vals)
        p90_ms = vals[max(0, int(len(vals) * 0.90) - 1)]
        print(
            "[fps-probe-stage] "
            f"{name} frames={len(vals)} avg_ms={avg_ms:.3f} "
            f"p90_ms={p90_ms:.3f} max_ms={vals[-1]:.3f}"
        )
    # Mythos S0 (`gate-measurement-harness`): single greppable acceptance-window verdict
    # line — fps percentiles computed ONLY from frames whose probe-elapsed time fell
    # inside KINGDOM_URSINA_FPS_WINDOW_SEC="<lo>:<hi>". Same percentile index style as
    # the whole-run [fps-probe] line above.
    win = getattr(owner, "_fps_probe_window_sec", None)
    if win is not None:
        wvals = sorted(getattr(owner, "_fps_probe_window_samples", None) or [])
        if not wvals:
            print(f"[fps-probe-window {win[0]:g}:{win[1]:g}] no samples in window")
        else:
            wavg = sum(wvals) / len(wvals)
            wp10 = wvals[max(0, int(len(wvals) * 0.10) - 1)]
            wp50 = wvals[max(0, int(len(wvals) * 0.50) - 1)]
            print(
                f"[fps-probe-window {win[0]:g}:{win[1]:g}] "
                f"frames={len(wvals)} avg_fps={wavg:.1f} "
                f"p10_fps={wp10:.1f} p50_fps={wp50:.1f} min_fps={wvals[0]:.1f}"
            )


def _maybe_auto_screenshot_then_quit(owner) -> None:
    """WK30 debug: save one screenshot (if a path was requested) and quit Ursina.

    Uses the **synchronous** ``base.win.getScreenshot()`` + ``PNMImage.write()`` path
    rather than ``base.screenshot(...)`` which queues the write for a later frame
    (the async queue never drains before ``application.quit()`` exits the process).
    """
    try:
        from ursina import application

        base = getattr(application, "base", None)
        if base is not None:
            try:
                base.graphicsEngine.renderFrame()
                base.graphicsEngine.renderFrame()
            except Exception:
                pass
        _print_fps_probe_summary(owner)
        if owner._auto_screenshot_path and base is not None:
            out_path = os.path.abspath(owner._auto_screenshot_path)
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            ok = _save_window_screenshot_sync(base, out_path)
            if ok and os.path.isfile(out_path):
                print(f"[auto-screenshot] Saved: {out_path}")
            else:
                print(f"[auto-screenshot] Failed to write: {out_path}")
        try:
            application.quit()
        except Exception:
            import sys

            sys.exit(0)
    except Exception as exc:
        print(f"[auto-exit] Aborted: {exc}")


def _save_window_screenshot_sync(base, out_path: str) -> bool:
    """Grab the main GraphicsWindow framebuffer into a PNMImage and write it now.

    Unlike ``base.screenshot()`` this does not schedule a future write — the image
    bytes are pulled synchronously and written in the same call. Works from a
    shutdown path where we are about to ``application.quit()``.
    """
    try:
        from panda3d.core import Filename, PNMImage

        tex = base.win.getScreenshot()
        if tex is None:
            print("[auto-screenshot] getScreenshot returned None")
            return False
        img = PNMImage()
        if not tex.store(img):
            print("[auto-screenshot] Texture.store failed")
            return False
        fn = Filename.fromOsSpecific(out_path)
        return bool(img.write(fn))
    except Exception as exc:
        print(f"[auto-screenshot] Sync capture failed: {exc}")
        return False
