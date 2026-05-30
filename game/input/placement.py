"""Building placement selection — mechanical extraction of InputHandler.

WK77 Round B-2e: ``select_building_for_placement`` moved verbatim from
``game/input_handler.py`` (WK69/WK75/WK76 pure-move pattern). Takes the live
``InputHandler`` as ``ih``; the body is the original method body with ``self.``
rewritten to ``ih.``. ``game/input_handler.py`` keeps a 1-line delegating wrapper.
Behavior is byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from game.input_handler import InputHandler


def select_building_for_placement(ih: "InputHandler", building_type: str) -> bool:
    """
    Unified method for selecting a building for placement.
    Called by both hotkeys and panel clicks.
    Returns True if selection succeeded, False otherwise.
    """
    c = ih.commands

    # Check affordability
    if not c.economy.can_afford_building(building_type):
        c.hud.add_message("Not enough gold!", (255, 100, 100))
        return False

    # Check prerequisites. Empty list = no prerequisite (e.g. temple).
    from config import BUILDING_PREREQUISITES
    if building_type in BUILDING_PREREQUISITES:
        required = BUILDING_PREREQUISITES[building_type]
        if required:
            has_prereq = False
            for building in c.buildings:
                if building.building_type in required and getattr(building, "is_constructed", False):
                    has_prereq = True
                    break
            if not has_prereq:
                req_names = ", ".join(b.replace("_", " ").title() for b in required)
                c.hud.add_message(f"Requires: {req_names}", (255, 200, 100))
                return False

    # Check constraints (mutually exclusive)
    from config import BUILDING_CONSTRAINTS
    if building_type in BUILDING_CONSTRAINTS:
        excluded = BUILDING_CONSTRAINTS[building_type]
        for building in c.buildings:
            if building.building_type in excluded:
                excl_name = building.building_type.replace("_", " ").title()
                c.hud.add_message(f"Cannot build: {excl_name} exists", (255, 200, 100))
                return False

    # All checks passed - select building
    c.building_menu.select_building(building_type)
    # Close panel if open
    if c.building_list_panel.visible:
        c.building_list_panel.close()
    return True
