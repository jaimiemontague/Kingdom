"""WK67 Round A-2 (Move 6): HeroCommand — AI proposes, the sim applies.

This closes the L3b write-side boundary leak where ``ai/behaviors/shopping.py``
mutated ``economy`` / ``hero`` directly across the AI boundary (it called
``hero.buy_item`` and ``economy.hero_purchase`` itself). After Move 6 the AI only
*proposes* a :class:`HeroPurchaseCommand` to a sim-owned :class:`CommandSink`; the
sim is the ONLY place that mutates hero/economy state.

Design rules (see ``.cursor/plans/wk67_round_a2_ai_boundary.plan.md`` "Critical
Design Rules" 3 & 4):

* No AI code may hold or mutate a live sim service. The write now happens inside
  :func:`apply_hero_command`, which the sim owns.
* The command applies **SYNCHRONOUSLY when proposed**, in the same tick and the
  same order as the code it replaces. The shopping loop reads ``hero.gold``
  between purchases (priority potion → extra potion → weapon → armor), so a
  deferred/batched applier would change the multi-item gold gating. The sink
  therefore applies immediately and returns whether the purchase succeeded, so
  the next priority branch sees the updated gold — byte-identical to the
  original inline ``do_shopping`` behaviour.

The applier mirrors the ORIGINAL ``do_shopping`` effect EXACTLY:

    if hero.buy_item(item):
        economy.hero_purchase(hero.name, item["name"], item["price"])

(``hero.buy_item`` is called WITHOUT ``shop_building`` — exactly as
``do_shopping`` did; the shop-tax deposit path inside ``buy_item`` resolves the
shop on its own.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class HeroPurchaseCommand:
    """A proposal that hero ``hero_id`` purchases shop ``item``.

    ``item`` is the shop item dict ``do_shopping`` already passes to
    ``hero.buy_item`` (carries ``name`` / ``price`` / ``type`` and, for
    weapons/armor, ``attack`` / ``defense``). Kept as a dict to mirror the
    current ``buy_item`` contract exactly.
    """

    hero_id: str
    item: dict


class CommandSink(Protocol):
    """Sink the AI proposes hero commands to. ``propose`` returns ``True`` iff the
    command was applied successfully (the shopping loop branches on this to gate
    subsequent purchases)."""

    def propose(self, command: object) -> bool: ...


def apply_hero_command(sim: Any, command: object) -> bool:
    """The ONLY place hero purchases mutate state.

    Resolves the hero by id, runs ``hero.buy_item`` and (on success) logs the
    purchase through ``sim.economy.hero_purchase`` — mirroring ``do_shopping``'s
    original effect EXACTLY (restores economy logging on the live AI path that
    Move 5 transitionally dropped). Returns ``True`` iff the purchase succeeded.
    """
    if isinstance(command, HeroPurchaseCommand):
        hero = sim.find_hero_by_id(command.hero_id)
        if hero is None:
            return False
        if hero.buy_item(command.item):
            sim.economy.hero_purchase(
                hero.name, command.item["name"], command.item["price"]
            )
            return True
    return False


class SimCommandSink:
    """Synchronous, sim-owned :class:`CommandSink`.

    Applies the proposed command NOW (in the proposing tick) and returns success.
    Synchronous application is mandatory (Critical Rule 4): the shopping loop
    reads ``hero.gold`` between purchases, so the mutation must land before the
    next priority branch's affordability check.
    """

    __slots__ = ("_sim",)

    def __init__(self, sim: Any):
        self._sim = sim

    def propose(self, command: object) -> bool:
        return apply_hero_command(self._sim, command)
