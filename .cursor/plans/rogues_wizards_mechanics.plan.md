## Majesty mechanics being adapted

- **Guild-based recruitment**: classes come from specific buildings (Rogue Guild, Wizard Guild).
- **Autonomous behavior**: classes show distinct preferences without direct control.
- **Incentive-driven play**: classes respond differently to bounties (Rogues are very reward-driven; Wizards are cautious but effective at range).

## Scope decisions (defaults for this prototype)

- **No palace level gating** (Majesty has it): guilds are immediately buildable like existing buildings.
- **No “Extort” ability** (Majesty Rogue Guild feature): out of scope for now; keep economy stable.
- **Wizard “spells” simplified**: a lightweight periodic bonus damage mechanic (mana + spell cooldown) instead of a full spellbook/research system.

## Implementation steps

1) **Plan + wiring**

- Add this plan file only (no code changes yet).

2) **Config + controls**

- Add `rogue_guild`, `wizard_guild` to:
- `BUILDING_COSTS`, `BUILDING_SIZES`, `BUILDING_COLORS`
- Add hotkeys:
- `4` Rogue Guild
- `5` Wizard Guild
- Update HUD and `main.py` printed controls.

3) **Buildings**

- Add `RogueGuild(Building)` and `WizardGuild(Building)` mirroring `WarriorGuild`/`RangerGuild`:
- `stored_tax_gold`, `collect_taxes`, `hire_hero`, render label
- Export via `game/entities/__init__.py`.
- Building panel: treat them as guilds (reuse existing guild renderer).

4) **Hiring**

- Extend `GameEngine.try_hire_hero()` to accept selected guild types:
- `warrior_guild` -> `warrior`
- `ranger_guild` -> `ranger`
- `rogue_guild` -> `rogue`
- `wizard_guild` -> `wizard`

5) **Heroes**

- Add class tuning in `Hero`:
- **Rogue**: very fast, lowish HP/defense, decent damage; prefers melee weapons.
- **Wizard**: fragile, slower, long range; has mana and a spell cooldown for bonus damage.
- Add `Hero.compute_attack_damage(target)` so CombatSystem can optionally use class specials.

6) **AI**

- Extend bounty pursuit scoring:
- Rogue strongest bounty bias (and slightly longer acceptable distance than Warrior).
- Wizard moderate bounty bias.
- Extend spacing/cowardice:
- Wizard maintains bigger minimum distance; retreats earlier if pressured.
- Rogue disengages earlier at low HP; can kite slightly.
- Extend shopping preference:
- Rogue prefers melee/daggers.
- Wizard prefers magic staves.

7) **Marketplace items**

- Add dagger progression + staff progression with `style` tags (`melee`, `magic`).

8) **Observer validation**

- Extend `tools/observe_sync.py` with `--rogues` / `--wizards` spawn flags and place their guild buildings.
- Run a short headless sim to confirm no crashes and classes spawn and behave distinctively.

## Files expected to change

- `config.py`
- `main.py`
- `game/ui/hud.py`
- `game/ui/building_panel.py`
- `game/engine.py`
- `game/entities/building.py`
- `game/entities/__init__.py`
- `game/entities/hero.py`
- `ai/basic_ai.py`
- `game/systems/combat.py`
- `tools/observe_sync.py`