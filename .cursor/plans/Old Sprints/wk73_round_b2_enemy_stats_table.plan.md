# WK73 Sprint Plan — Round B-2b: enemy.py ENEMY_STATS table

**Author:** Agent 01 (PM) · **Date:** 2026-05-30 · **Goal:** all tests pass; the 7 near-identical enemy stat-block subclasses collapse into one `ENEMY_STATS` table applied by `Enemy.__init__`; behavior byte-identical (digest `b73961…` unchanged).
**Predecessors:** WK68-72. **Roadmap:** Round B-2 (god-file / redundancy reduction), entities-units area (pairs with the WK71 hero split).

## 0. TL;DR
`game/entities/enemy.py` (623 LOC) has 8 `Enemy` subclasses. **SkeletonArcher** is the one real behavioral subclass (kiting `update`) — it STAYS. The other 7 (Goblin, Wolf, Skeleton, Spider, Bandit, BanditLord, DemonOverlord) are pure stat blocks that copy-paste the same `__init__` shape. WK73 lifts their stats into a single `ENEMY_STATS: dict[str, EnemyStats]` table that `Enemy.__init__` applies by `enemy_type`, and reduces each of the 7 subclasses to a **1-line shim** (so every `Goblin(x,y)` construction site in lair.py/spawner.py keeps working unchanged). Headless, digest-guarded (the 300-tick digest is combat-heavy), no screenshots. Digest `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded` MUST stay byte-identical. PM writes no code.

## 1. Scope
**IN:**
- Add `@dataclass(frozen=True) EnemyStats` + `ENEMY_STATS: dict[str, EnemyStats]` (in enemy.py or a new `game/entities/enemy_stats.py`) capturing EVERY per-type attribute the 7 stat subclasses currently set (read each subclass `__init__` verbatim: hp/max_hp, attack_power, speed/move_speed, color, size, xp/gold reward, attack range, attack cooldown, vision, any flags — capture ALL of them).
- Make `Enemy.__init__(x, y, enemy_type="goblin")` read `ENEMY_STATS.get(enemy_type, <default>)` and apply the stats AFTER the current base init (so the values end up identical to what the subclass set). Preserve the exact current default behavior for an unknown type.
- Reduce the 7 stat subclasses to 1-line shims: `class Goblin(Enemy):` with `def __init__(self, x, y): super().__init__(x, y, "goblin")` (and likewise wolf/skeleton/spider/bandit/bandit_lord/demon_overlord with their exact type keys). Keep the class NAMES (lair.py + spawner.py construct by name).
- **SkeletonArcher STAYS AS-IS** (it has behavioral `update`/kiting) — only fold its STAT lines into the table if they're pure stats AND it still passes its type; do NOT touch its behavioral methods. If risky, leave SkeletonArcher entirely untouched.
- Optionally move `register_attacker`/`attackers` up to the `Enemy` base if that de-dups cleanly (audit) — only if behavior-identical; else skip.

**OUT:** `make_enemy()` factory + changing construction sites (keep the subclass shims so call sites are unchanged — lower risk); the `EnemyType` enum revival; combat.py changes; any stat rebalance.

## 2. Pattern
```python
@dataclass(frozen=True)
class EnemyStats:
    hp: int; attack_power: int; speed: float; color: tuple; size: int
    xp_reward: int; gold_reward: int; attack_range: float; attack_cooldown_ms: int
    # ... EVERY field the subclasses set — add fields to cover them all

ENEMY_STATS = { "goblin": EnemyStats(...), "wolf": EnemyStats(...), ... }  # exact current values

class Enemy:
    def __init__(self, x, y, enemy_type="goblin"):
        # ... existing base init ...
        s = ENEMY_STATS.get(enemy_type)
        if s is not None:
            self.max_hp = s.hp; self.hp = s.hp; self.attack_power = s.attack_power; ...  # apply ALL
        # else: keep the current default-type behavior

class Goblin(Enemy):
    def __init__(self, x, y): super().__init__(x, y, "goblin")
```
The stat values in the table must EXACTLY equal what each subclass set today. The digest is the guard.

## 3. Definition of Done
- **A.** `pytest` all pass (baseline **667 passed / 4 skipped / 0 failed**).
- **B.** `determinism_guard.py` clean.
- **C.** WK67 digest byte-identical = `b73961340cd681e5c5d04d2735fe7e302fc23167433d7f566905597d8d148ded`.
- **D.** `qa_smoke.py --quick` green.
- **E.** `ENEMY_STATS` exists; the 7 stat subclasses are ≤ a few lines each (no per-subclass stat duplication remains); SkeletonArcher behavior intact; all construction sites (lair.py, spawner.py) unchanged and working.
- **F.** Logs updated; PM hub close.

## 4. Waves
- **W1 (Agent 05):** build the table + refactor `Enemy.__init__` + shim the 7 subclasses. Verify digest + suite.
- **W2 (Agent 11):** stat-parity test (for each enemy type, constructing it yields the SAME attributes as the pre-WK73 subclass — embed expected stats captured from git HEAD) + full DoD gate.
- Agent 06 consult (combat semantics if digest drifts).

## 5. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Table misses an attribute a subclass set → stat differs | Med | read EACH subclass __init__ verbatim; W2 stat-parity test vs git-HEAD values; digest guards combat |
| Apply-order: base init overwrites a stat or vice-versa | Med | apply table AFTER base init exactly where the subclass did; digest catches drift |
| SkeletonArcher behavioral coupling | Low-Med | leave its update/kiting untouched; only its pure stats (optional) |
| Digest drift | Low | verify after the refactor; if it drifts, a stat value/order is wrong |

## 6. Success
The 7 enemy stat subclasses become 1-line shims over a single `ENEMY_STATS` table, enemies spawn/fight identically — proven by 667+ green tests, clean determinism guard, unchanged `b73961…` digest, and the stat-parity test.

## 7. Kickoff
Roster: 05 (refactor W1), 11 (parity + DoD W2), 06 (consult). Order: 05 W1 → PM gate (digest+suite) → 11 W2 → commit+push. Reminders: onboard via `.cursor/rules`; `claude-opus-4-8`; behavior-preserving, digest unchanged; NO screenshots; own log; DO NOT COMMIT.
Follow-ups: hud/ursina_renderer/engine/input_handler/ursina_app splits; Move 9; world.py split; config package; clusters 3/4/5; AI router (Round D); zombie purge (21-file deletion — needs its own careful sprint); dead `_unit_facing_direction` removal.
