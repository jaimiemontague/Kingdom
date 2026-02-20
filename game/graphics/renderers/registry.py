"""Registry for all render-side renderer instances."""

from __future__ import annotations

import pygame

from .bounty_renderer import BountyRenderer
from .building_renderer import BuildingRenderer
from .enemy_renderer import EnemyRenderer
from .hero_renderer import HeroRenderer
from .worker_renderer import GuardRenderer, PeasantRenderer, TaxCollectorRenderer


class RendererRegistry:
    """Maps live entities to renderer instances (render-only state ownership)."""

    def __init__(self):
        self._hero_renderers: dict[int, HeroRenderer] = {}
        self._enemy_renderers: dict[int, EnemyRenderer] = {}
        self._peasant_renderers: dict[int, PeasantRenderer] = {}
        self._collector_renderers: dict[int, TaxCollectorRenderer] = {}
        self._guard_renderer = GuardRenderer()
        self._building_renderer = BuildingRenderer()
        self._bounty_renderer = BountyRenderer()

    @staticmethod
    def _key(entity: object) -> int:
        return id(entity)

    def _hero_renderer_for(self, hero: object) -> HeroRenderer:
        key = self._key(hero)
        renderer = self._hero_renderers.get(key)
        if renderer is None:
            renderer = HeroRenderer(hero_id=key, hero_class=str(getattr(hero, "hero_class", "warrior")))
            self._hero_renderers[key] = renderer
        return renderer

    def _enemy_renderer_for(self, enemy: object) -> EnemyRenderer:
        key = self._key(enemy)
        renderer = self._enemy_renderers.get(key)
        if renderer is None:
            renderer = EnemyRenderer(enemy_id=key, enemy_type=str(getattr(enemy, "enemy_type", "goblin")))
            self._enemy_renderers[key] = renderer
        return renderer

    def _peasant_renderer_for(self, peasant: object) -> PeasantRenderer:
        key = self._key(peasant)
        renderer = self._peasant_renderers.get(key)
        if renderer is None:
            renderer = PeasantRenderer(peasant_id=key)
            self._peasant_renderers[key] = renderer
        return renderer

    def _collector_renderer_for(self, collector: object) -> TaxCollectorRenderer:
        key = self._key(collector)
        renderer = self._collector_renderers.get(key)
        if renderer is None:
            renderer = TaxCollectorRenderer(collector_id=key)
            self._collector_renderers[key] = renderer
        return renderer

    def update_animations(
        self,
        dt: float,
        heroes: list[object],
        enemies: list[object],
        peasants: list[object],
        tax_collector: object | None,
        guards: list[object] | None = None,
    ) -> None:
        """Advance all animated renderers once per tick."""
        for hero in heroes:
            self._hero_renderer_for(hero).update_animation(getattr(hero, "render_state", hero), dt)
        for enemy in enemies:
            self._enemy_renderer_for(enemy).update_animation(getattr(enemy, "render_state", enemy), dt)
        for peasant in peasants:
            self._peasant_renderer_for(peasant).update_animation(getattr(peasant, "render_state", peasant), dt)
        if tax_collector is not None:
            self._collector_renderer_for(tax_collector).update_animation(
                getattr(tax_collector, "render_state", tax_collector),
                dt,
            )
        for guard in guards or []:
            if getattr(guard, "is_alive", True):
                self._guard_renderer.update_animation(getattr(guard, "render_state", guard), dt)

    def render_building(
        self,
        surface: pygame.Surface,
        building: object,
        camera_offset: tuple[float, float],
    ) -> None:
        self._building_renderer.render(surface, getattr(building, "render_state", building), camera_offset)

    def render_enemy(
        self,
        surface: pygame.Surface,
        enemy: object,
        camera_offset: tuple[float, float],
    ) -> None:
        self._enemy_renderer_for(enemy).render(surface, getattr(enemy, "render_state", enemy), camera_offset)

    def render_hero(
        self,
        surface: pygame.Surface,
        hero: object,
        camera_offset: tuple[float, float],
    ) -> None:
        self._hero_renderer_for(hero).render(surface, getattr(hero, "render_state", hero), camera_offset)

    def render_guard(
        self,
        surface: pygame.Surface,
        guard: object,
        camera_offset: tuple[float, float],
    ) -> None:
        self._guard_renderer.render(surface, getattr(guard, "render_state", guard), camera_offset)

    def render_peasant(
        self,
        surface: pygame.Surface,
        peasant: object,
        camera_offset: tuple[float, float],
    ) -> None:
        self._peasant_renderer_for(peasant).render(surface, getattr(peasant, "render_state", peasant), camera_offset)

    def render_tax_collector(
        self,
        surface: pygame.Surface,
        tax_collector: object,
        camera_offset: tuple[float, float],
    ) -> None:
        self._collector_renderer_for(tax_collector).render(
            surface,
            getattr(tax_collector, "render_state", tax_collector),
            camera_offset,
        )

    def render_bounties(
        self,
        surface: pygame.Surface,
        bounties: list[object],
        camera_offset: tuple[float, float],
    ) -> None:
        self._bounty_renderer.render_all(surface, bounties, camera_offset)

    def prune(
        self,
        heroes: list[object],
        enemies: list[object],
        peasants: list[object],
        tax_collector: object | None,
    ) -> None:
        """Drop renderer instances for entities no longer alive/referenced."""
        live_heroes = {self._key(hero) for hero in heroes}
        live_enemies = {self._key(enemy) for enemy in enemies}
        live_peasants = {self._key(peasant) for peasant in peasants}
        live_collectors = {self._key(tax_collector)} if tax_collector is not None else set()

        self._hero_renderers = {key: renderer for key, renderer in self._hero_renderers.items() if key in live_heroes}
        self._enemy_renderers = {key: renderer for key, renderer in self._enemy_renderers.items() if key in live_enemies}
        self._peasant_renderers = {
            key: renderer for key, renderer in self._peasant_renderers.items() if key in live_peasants
        }
        self._collector_renderers = {
            key: renderer for key, renderer in self._collector_renderers.items() if key in live_collectors
        }
