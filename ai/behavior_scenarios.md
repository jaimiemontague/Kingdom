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







