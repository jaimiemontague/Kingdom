# Behavior Evaluation Scenarios (LLM-Assisted Heroes)

These scenarios are meant to be **reproducible**, **short**, and easy to validate by observing the hero’s chosen `action`.

## Scenario 1: Critical health with potion (combat)

- **Setup**: Hero is `FIGHTING`, `health_percent < 25%`, `potions >= 1`, enemy within 2 tiles.
- **Expected**:
  - Prefer `use_potion` (over `retreat`) unless already at safety and still threatened.
- **Notes**: Validates the most important survival rule.

## Scenario 2: Critical health without potion (combat)

- **Setup**: Hero is `FIGHTING`, `health_percent < 25%`, `potions == 0`.
- **Expected**:
  - `retreat` with target `castle` or `marketplace`.

## Scenario 3: Low health in combat (not critical)

- **Setup**: Hero is `FIGHTING`, `25% <= health_percent < 50%`, enemy present.
- **Expected**:
  - `use_potion` if available; otherwise `retreat` is acceptable depending on “near safety”.

## Scenario 4: Shopping opportunity

- **Setup**: Hero has `gold >= 30`, marketplace within ~6 tiles, shop contains a potion the hero can afford.
- **Expected**:
  - `buy_item` targeting a potion when low on potions / low health.

## Scenario 5: Stable output contract (schema robustness)

- **Setup**: Force provider to return malformed outputs (extra text, missing fields, invalid action).
- **Expected**:
  - Parser rejects unknown actions and falls back deterministically via `get_fallback_decision`.

## Scenario 6: Ashwing hunt prep

- **Setup**: Active `Ashwing's Hoard` chain, dragon revealed, hero healthy with supplies, boss telegraph visible in the structured context.
- **Expected**:
  - Prompt context keeps the dragon facts structured: chain phase, boss identity, boss phase, telegraph, and the current preparation target.
  - A prepared hero can continue the hunt.

## Scenario 7: Ashwing hunt resupply

- **Setup**: Active `Ashwing's Hoard` chain, hero is healthy but has no potions, and the structured context exposes the hunt facts.
- **Expected**:
  - The deterministic policy may choose `prepare_supplies` before pressing on.
  - The model must not invent a dragon weakness or claim the hoard is already claimed.

## Scenario 8: Ashwing hunt retreat

- **Setup**: Active `Ashwing's Hoard` chain, hero is wounded and has no potions.
- **Expected**:
  - Survival gates force `retreat_to_heal`.
  - Rescue/revenge memories remain separate structured facts and are not overwritten by the dragon hunt context.







