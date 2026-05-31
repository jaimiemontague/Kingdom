"""Canonical AI action/intent vocabulary (WK110 consolidation of scattered string contracts).

Single source of truth for the LLM tool-action names, the direct-prompt intent names,
and the place-type groupings that were previously duplicated across prompt_templates.py,
direct_prompt_validator.py, prompt_packs.py, decision_moments.py and arrival_handlers.py.

LEAF MODULE: imports ONLY stdlib. Must NOT import from ai.* or game.* (kept upstream of
the whole ai package to avoid import cycles). Downstream modules derive their existing
public collections (VALID_ACTIONS, TOOL_ACTIONS, SUPPORTED_DIRECT_INTENTS, ...) from these
enums and re-export them under the SAME names with BYTE-IDENTICAL values, so the WK67 AI
decision digest stays byte-identical and no caller/test moves.

``str, Enum`` is deliberate: ``ToolAction.MOVE_TO == "move_to"`` and
``ToolAction.MOVE_TO.value == "move_to"`` are both True, so every existing string
membership/equality check behaves identically.
"""
from __future__ import annotations

from enum import Enum


class ToolAction(str, Enum):
    """Canonical LLM tool-action names.

    Values are byte-identical to the current ``ai.prompt_templates.TOOL_ACTIONS`` members.
    ``ai.prompt_templates.VALID_ACTIONS`` has the SAME membership (a set of these seven
    strings), so both legacy collections are reproduced from this enum.
    """

    LEAVE_BUILDING = "leave_building"
    MOVE_TO = "move_to"
    FIGHT = "fight"
    RETREAT = "retreat"
    BUY_ITEM = "buy_item"
    USE_POTION = "use_potion"
    EXPLORE = "explore"


class DirectIntent(str, Enum):
    """Canonical direct-prompt (player chat) intent names.

    Values are byte-identical to the current
    ``ai.direct_prompt_validator.SUPPORTED_DIRECT_INTENTS`` members.
    """

    STATUS_REPORT = "status_report"
    RETURN_HOME = "return_home"
    SEEK_HEALING = "seek_healing"
    GO_TO_KNOWN_PLACE = "go_to_known_place"
    BUY_POTIONS = "buy_potions"
    EXPLORE_DIRECTION = "explore_direction"
    REST_UNTIL_HEALED = "rest_until_healed"
    NO_ACTION_CHAT_ONLY = "no_action_chat_only"


# Combat intents the model might emit that are deferred (not supported) in the MVP.
# Values copied verbatim from ``direct_prompt_validator.DEFERRED_COMBAT_INTENTS``.
DEFERRED_COMBAT_INTENTS = frozenset(
    {
        "attack_known_lair",
        "attack_nearest_enemy",
        "attack_lair",
        "attack_enemy",
    }
)

# Place-type groupings (values copied verbatim from the current frozensets/dicts in
# ``direct_prompt_validator.py``). The validator aliases these to its existing private
# names (``_PLAYER_HOME_TYPES`` / ``_PLACE_TYPE_TO_MOVE_TARGET``) so its read-sites are
# unchanged.
PLACE_TYPE_TO_MOVE_TARGET = {
    "castle": "castle",
    "inn": "inn",
    "marketplace": "marketplace",
    "blacksmith": "blacksmith",
}

PLAYER_HOME_TYPES = frozenset(
    {
        "warrior_guild",
        "ranger_guild",
        "rogue_guild",
        "wizard_guild",
        "temple",
    }
)
