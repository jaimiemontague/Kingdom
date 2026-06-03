"""Presentation-owned selection state. Stores entity IDs, not live object references.

The sim never reads or writes this. GameEngine owns the instance and populates
get_game_state() / build_snapshot() from it. InputHandler writes to it through
GameCommands (or directly after Wave 2).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class SelectionState:
    """Tracks which entity the player has selected.

    Selection is mutually exclusive across entity types:
    setting one clears the others. The exception is that
    selected_building_id can coexist with selected_hero_id
    (the HUD shows building in right panel and hero in left).
    """

    selected_hero_id: Optional[str] = None
    selected_building_id: Optional[str] = None
    selected_enemy_id: Optional[str] = None
    selected_peasant_id: Optional[str] = None
    # WK122: the left "hero" panel slot can also hold a Guard or the TaxCollector.
    # kind disambiguates which sim collection the id resolves against.
    # Values: 'hero' | 'guard' | 'tax_collector' (None when nothing selected).
    selected_hero_kind: Optional[str] = None

    def select_hero(self, hero_id: Optional[str], kind: str = "hero") -> None:
        """Select a hero (or guard / tax_collector). Clears enemy and peasant selection.

        ``kind`` records which sim collection ``hero_id`` resolves against. For the
        tax_collector (a singleton with no id) pass ``hero_id=None, kind='tax_collector'``.
        """
        self.selected_hero_id = hero_id
        self.selected_hero_kind = kind
        self.selected_enemy_id = None
        self.selected_peasant_id = None

    def select_building(self, building_id: str) -> None:
        """Select a building. Clears enemy and peasant selection."""
        self.selected_building_id = building_id
        self.selected_enemy_id = None
        self.selected_peasant_id = None

    def select_enemy(self, enemy_id: str) -> None:
        """Select an enemy. Clears hero and peasant selection."""
        self.selected_hero_id = None
        self.selected_enemy_id = enemy_id
        self.selected_peasant_id = None

    def select_peasant(self, peasant_id: str) -> None:
        """Select a peasant. Clears hero and enemy selection."""
        self.selected_hero_id = None
        self.selected_peasant_id = peasant_id
        self.selected_enemy_id = None

    def clear_hero(self) -> None:
        self.selected_hero_id = None
        self.selected_hero_kind = None

    def clear_building(self) -> None:
        self.selected_building_id = None

    def clear_enemy(self) -> None:
        self.selected_enemy_id = None

    def clear_peasant(self) -> None:
        self.selected_peasant_id = None

    def clear_all(self) -> None:
        self.selected_hero_id = None
        self.selected_hero_kind = None
        self.selected_building_id = None
        self.selected_enemy_id = None
        self.selected_peasant_id = None

    def on_entity_destroyed(self, entity_id: str) -> None:
        """Clear selection if the destroyed entity was selected."""
        if self.selected_hero_id == entity_id:
            self.selected_hero_id = None
            self.selected_hero_kind = None
        if self.selected_building_id == entity_id:
            self.selected_building_id = None
        if self.selected_enemy_id == entity_id:
            self.selected_enemy_id = None
        if self.selected_peasant_id == entity_id:
            self.selected_peasant_id = None
