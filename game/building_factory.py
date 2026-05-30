"""
Building factory for runtime placement.

WK70 W2: ``BUILDING_REGISTRY`` is DERIVED from the single-source ``BUILDING_DEFS``
(game/content/buildings.py) instead of being a hand-written dict. It maps every key
that has a constructor class and is neither a POI (POIs route via ``POI_DEFINITIONS``
below) nor castle/house/farm (intentionally absent — those are placed via other paths).
The class is resolved through the import-cycle-safe lazy ``building_class_for`` accessor,
so this module imports NO entity classes at load time (config -> buildings -> entities ->
config would cycle). The result is byte-identical to the pre-WK70 27-key registry
(guarded by tests/test_wk70_building_registry.py).
"""
from game.content.buildings import BUILDING_DEFS, building_class_for

# WK54: POI type registration
try:
    from game.entities.poi import PointOfInterest, POI_DEFINITIONS
except Exception:
    PointOfInterest = None  # type: ignore[assignment, misc]
    POI_DEFINITIONS = {}  # type: ignore[assignment]


def _build_registry() -> dict[str, type]:
    """Derive the 27 placement-class mappings from BUILDING_DEFS (see module docstring)."""
    registry: dict[str, type] = {}
    for key, d in BUILDING_DEFS.items():
        if d.is_poi or key in ("castle", "house", "farm"):
            continue
        cls = building_class_for(key)
        if cls is None:
            continue
        registry[key] = cls
    return registry


class BuildingFactory:
    """Create building instances from placement type keys."""

    BUILDING_REGISTRY = _build_registry()

    def create(self, building_type: str, grid_x: int, grid_y: int):
        """Return a placed building instance, or None for unknown type."""
        # WK54: Check POI types first (different constructor than regular buildings)
        if POI_DEFINITIONS and str(building_type) in POI_DEFINITIONS:
            return PointOfInterest(grid_x, grid_y, POI_DEFINITIONS[str(building_type)])
        cls = self.BUILDING_REGISTRY.get(str(building_type))
        if cls is None:
            return None
        return cls(grid_x, grid_y)
