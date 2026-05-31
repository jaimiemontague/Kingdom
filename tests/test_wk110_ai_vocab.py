"""WK110 Round B characterization seam test for ai/vocab.py.

WK110 consolidated the scattered AI tool-action / direct-intent vocabulary into a
new stdlib-only LEAF module ``ai/vocab.py`` (``ToolAction(str, Enum)`` +
``DirectIntent(str, Enum)`` + place-grouping frozensets/dict). The existing modules
``ai/prompt_templates.py`` and ``ai/direct_prompt_validator.py`` now DERIVE their public
collections from the enums and RE-EXPORT the legacy names with BYTE-IDENTICAL values
and types.

This test is the regression net for that refactor. It PINS the exact pre-WK110 literal
values (copied verbatim from ``git show HEAD:`` of the source modules at the time of the
refactor) and asserts the CURRENT module attributes equal them in BOTH membership AND
type. It also locks the str-Enum behavior, the enum<->collection consistency, the
re-export presence the existing suite relies on, and the LEAF invariant (ai/vocab.py
imports ONLY stdlib).

These pins guarantee zero drift: the WK67 AI-decision digest stays byte-identical
because every membership/equality check on these strings behaves identically.
"""

from __future__ import annotations

import ast
import os

import ai.direct_prompt_validator as dpv
from ai.direct_prompt_validator import (  # noqa: F401  (re-export presence check)
    DEFERRED_COMBAT_INTENTS,
    SUPPORTED_DIRECT_INTENTS,
)
from ai.prompt_templates import TOOL_ACTIONS, VALID_ACTIONS
from ai.vocab import DirectIntent, ToolAction

# ---------------------------------------------------------------------------
# PINNED pre-WK110 literal values (the characterization net). Do NOT "fix" these
# to match new code -- they encode the original contract. If a value here must
# change, the WK67 digest is almost certainly affected: stop and re-verify.
# ---------------------------------------------------------------------------
PINNED_VALID_ACTIONS = {
    "fight",
    "retreat",
    "buy_item",
    "use_potion",
    "explore",
    "leave_building",
    "move_to",
}
PINNED_TOOL_ACTIONS = {
    "leave_building",
    "move_to",
    "fight",
    "retreat",
    "buy_item",
    "use_potion",
    "explore",
}
PINNED_SUPPORTED_DIRECT_INTENTS = {
    "status_report",
    "return_home",
    "seek_healing",
    "go_to_known_place",
    "buy_potions",
    "explore_direction",
    "rest_until_healed",
    "no_action_chat_only",
}
PINNED_DEFERRED_COMBAT_INTENTS = {
    "attack_known_lair",
    "attack_nearest_enemy",
    "attack_lair",
    "attack_enemy",
}
PINNED_PLACE_TYPE_TO_MOVE_TARGET = {
    "castle": "castle",
    "inn": "inn",
    "marketplace": "marketplace",
    "blacksmith": "blacksmith",
}
PINNED_PLAYER_HOME_TYPES = {
    "warrior_guild",
    "ranger_guild",
    "rogue_guild",
    "wizard_guild",
    "temple",
}


# ---------------------------------------------------------------------------
# 1. str-Enum behavior
# ---------------------------------------------------------------------------
def test_toolaction_is_str_enum():
    assert issubclass(ToolAction, str)
    # equal to the bare string AND .value is the bare string (string-enum contract)
    assert ToolAction.MOVE_TO == "move_to"
    assert ToolAction.MOVE_TO.value == "move_to"
    assert isinstance(ToolAction.FIGHT, str)


def test_directintent_is_str_enum():
    assert issubclass(DirectIntent, str)
    assert DirectIntent.STATUS_REPORT == "status_report"
    assert DirectIntent.STATUS_REPORT.value == "status_report"
    assert isinstance(DirectIntent.RETURN_HOME, str)


# ---------------------------------------------------------------------------
# 2. byte-identical-value characterization (membership AND type)
# ---------------------------------------------------------------------------
def test_valid_actions_byte_identical():
    assert type(VALID_ACTIONS) is set
    assert set(VALID_ACTIONS) == PINNED_VALID_ACTIONS


def test_tool_actions_byte_identical():
    assert type(TOOL_ACTIONS) is set
    assert set(TOOL_ACTIONS) == PINNED_TOOL_ACTIONS


def test_supported_direct_intents_byte_identical():
    assert type(dpv.SUPPORTED_DIRECT_INTENTS) is frozenset
    assert set(dpv.SUPPORTED_DIRECT_INTENTS) == PINNED_SUPPORTED_DIRECT_INTENTS


def test_deferred_combat_intents_byte_identical():
    assert type(dpv.DEFERRED_COMBAT_INTENTS) is frozenset
    assert set(dpv.DEFERRED_COMBAT_INTENTS) == PINNED_DEFERRED_COMBAT_INTENTS


def test_place_type_to_move_target_byte_identical():
    assert type(dpv._PLACE_TYPE_TO_MOVE_TARGET) is dict
    assert dict(dpv._PLACE_TYPE_TO_MOVE_TARGET) == PINNED_PLACE_TYPE_TO_MOVE_TARGET


def test_player_home_types_byte_identical():
    assert type(dpv._PLAYER_HOME_TYPES) is frozenset
    assert set(dpv._PLAYER_HOME_TYPES) == PINNED_PLAYER_HOME_TYPES


# ---------------------------------------------------------------------------
# 3. re-export presence (the by-name imports the existing suite relies on)
# ---------------------------------------------------------------------------
def test_reexports_resolve_by_name():
    # These imports happen at module top-level above; this asserts they bound real
    # objects (so the existing suite's `from ... import NAME` still resolves).
    assert VALID_ACTIONS is not None
    assert TOOL_ACTIONS is not None
    assert SUPPORTED_DIRECT_INTENTS is not None
    assert DEFERRED_COMBAT_INTENTS is not None
    # and they are still reachable as module attributes on the original modules
    import ai.prompt_templates as pt

    assert hasattr(pt, "VALID_ACTIONS")
    assert hasattr(pt, "TOOL_ACTIONS")
    assert hasattr(dpv, "SUPPORTED_DIRECT_INTENTS")
    assert hasattr(dpv, "DEFERRED_COMBAT_INTENTS")
    assert hasattr(dpv, "_PLACE_TYPE_TO_MOVE_TARGET")
    assert hasattr(dpv, "_PLAYER_HOME_TYPES")


# ---------------------------------------------------------------------------
# 4. enum <-> collection consistency
# ---------------------------------------------------------------------------
def test_every_toolaction_value_in_tool_actions():
    for member in ToolAction:
        assert member.value in TOOL_ACTIONS
    assert {a.value for a in ToolAction} == set(TOOL_ACTIONS)


def test_every_directintent_value_in_supported():
    for member in DirectIntent:
        assert member.value in dpv.SUPPORTED_DIRECT_INTENTS
    assert {i.value for i in DirectIntent} == set(dpv.SUPPORTED_DIRECT_INTENTS)


# ---------------------------------------------------------------------------
# 5. LEAF guard (AST): ai/vocab.py imports ONLY stdlib (no ai.* / game.*)
# ---------------------------------------------------------------------------
_ALLOWED_IMPORT_ROOTS = {"__future__", "enum"}


def _vocab_source_path() -> str:
    # ai/vocab.py lives next to the ai package; resolve relative to this test file.
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    return os.path.join(repo_root, "ai", "vocab.py")


def test_vocab_is_a_stdlib_only_leaf():
    path = _vocab_source_path()
    assert os.path.isfile(path), f"ai/vocab.py not found at {path}"
    with open(path, encoding="utf-8-sig") as fh:
        tree = ast.parse(fh.read(), filename=path)

    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for `from . import x`; treat as relative -> reject
            root = (node.module or "").split(".")[0]
            imported_roots.add(root)

    # No ai.* / game.* imports anywhere in the leaf module.
    offenders = {r for r in imported_roots if r.startswith("ai") or r.startswith("game")}
    assert not offenders, f"ai/vocab.py is not a leaf -- forbidden imports: {sorted(offenders)}"

    # And only stdlib roots we explicitly allow appear.
    unexpected = imported_roots - _ALLOWED_IMPORT_ROOTS - {""}
    assert not unexpected, f"ai/vocab.py imports unexpected modules: {sorted(unexpected)}"
