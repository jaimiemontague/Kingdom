# Changelog

## Prototype v1.3.7 — Hero Chat with Broken LLMs

- UX: **Hero chat** — click a hero in a building interior to open a chat panel; type messages and press Enter; hero responds via LLM (when provider is available).
- UX: **Chat panel** — word-wrapped messages, auto-scroll, "Thinking..." indicator, End Conversation button; LLM provider default now reads from `.env` (e.g. `LLM_PROVIDER=openai`).
- Fix: OpenAI provider updated for `gpt-5-nano` (max_completion_tokens, no custom temperature); conversation worker returns fallback text on errors.
- Fix: Chat keystrokes no longer leak to game hotkeys; chat input handled before pause/menu checks.
- **Known issue:** LLM conversation calls can still fail or stop responding after a few attempts. Once these are stable, we'll be ready to officially bump to v1.4.

## Prototype v1.3.6 — Interiors Update

- UX: **Enter Building** — select any enterable building (Inn, guilds, Marketplace, Blacksmith, temples) and click "Enter Building" to view its interior in the right panel.
- UX: **Building interiors** — procedural interior scenes for Inn (bar, tables, fireplace), Marketplace (shelves, counter), and Warrior Guild (training dummies, sparring ring); other enterable buildings use a generic interior.
- UX: **Interior panel** — right panel shows background, furniture, NPC (bartender/merchant/guildmaster), and hero occupants in real time; Exit button, ESC, or clicking the map returns to overview.
- UX: **Auto-slow on enter** — game slows to 0.25x when entering a building; speed restores on exit.
- Fix: Right panel now opens automatically when entering a building (no need to click a hero first).
- Fix: Building panel scrolls when content is tall (e.g. Warrior Guild) so "Enter Building" is always visible.
- Fix: Inn "get a drink" gold no longer crashes (gold_earned_from_drinks property setter added).

## Prototype v1.3.5 — Time and Speed Update

- UX: **5-tier speed control** — Pause, Super Slow, Slow, Normal, and Fast (bottom-right bar). Game starts at Normal (0.5x); Fast matches previous speed.
- UX: **Hotkeys** — `[` / `]` step speed slower/faster; backtick (`` ` ``) toggles pause.
- Buildings: **Universal occupancy** — all buildings track heroes inside; building panels show "Heroes inside: N/max" for guilds, Inn, Marketplace, Blacksmith.
- Foundation: EventBus events when heroes enter or exit buildings (for future interior view and LLM chat).

## Prototype v1.3.4 — Refactor Bug Fixes Update

- Fix: **ESC** no longer crashes when opening the pause menu (missing button texture).
- UX: **Command bar** Build, Hire, and Bounty buttons are now clickable (same behavior as hotkeys).
- UX: **Fullscreen/borderless** — click near the top of the screen to switch to windowed mode.
- AI: Heroes **prefer fighting nearby monsters** over going to the Inn; rest/drink only when no enemies nearby or when critically low HP.

## Prototype v1.3.3 — The Inn & AI Behavior Update

- Combat: Heroes inside buildings are now **fully untargetable** by enemies — covers resting, shopping, and all future inside-building states.
- Combat: Enemies no longer **prioritize buildings with heroes inside**, preventing the flush-and-kill pattern.
- Buildings: Heroes now **spend realistic time inside** buildings — buying potions takes 8-12 seconds, armor 16-22 seconds, with randomized durations per task.
- Buildings: Purchases happen **when the hero exits**, not on entry — creating a natural in-and-out feel.
- Inn: Heroes can now **rest at Inns** with faster healing (1 HP/sec vs guild 1 HP/2sec) and will choose a closer Inn over their home guild.
- Inn: Heroes occasionally **"get a drink"** at the Inn when idle, full health, and have spare gold — flavor behavior that makes the world feel alive.
- Inn: Panel now shows **heroes inside**, recovery rate, and gold earned from drinks.
- LLM: OpenAI model is now **configurable** via `OPENAI_MODEL` env var (default: `gpt-5-nano`); added `.env.example` for setup.

## Prototype v1.3.2 — The AI Refactor Update

- AI: **Hero AI decomposed** into 7 focused behavior modules — bounty pursuit, defense, journey, stuck recovery, exploration, shopping, and LLM bridge.
- AI: `basic_ai.py` slimmed from **1,580 to 363 lines** as a coordinator; behavior logic lives in `ai/behaviors/`.
- Quality: **20 new AI behavior tests** (bounty scoring, defense triggers, shopping, stuck recovery, exploration) — total test suite now at **68 tests**.
- Fix: **Marketplace panel** now correctly displays potion research and purchase options.

## Prototype v1.3.1 — The Refactor Update

- Architecture: **Engine decomposed** — InputHandler, DisplayManager, BuildingFactory, CleanupManager extracted from the monolithic engine.
- Architecture: **EventBus** centralizes all event routing (combat, audio, VFX) — replaces manual try/except routing blocks.
- Architecture: **GameSystem Protocol** formalizes system interfaces — all 6 core systems conform.
- Entities: **Building package** — 25+ building classes split into domain modules (guilds, temples, defensive, economic, special) with `HiringBuilding` mixin eliminating duplicate code.
- Entities: **Sim/render separation** — all entity rendering moved to dedicated renderer classes; entity files are now pure simulation logic with no pygame dependency.
- UI: **HUD decomposed** into focused sub-components (hero panel, command bar, top bar) with reusable **Button**, **HPBar**, and **TextLabel** widgets.
- UI: **Building panel** decomposed into per-domain panel renderers via registry pattern.
- Config: All tuning constants grouped into **frozen dataclasses** with backward-compatible aliases.
- Types: **BuildingType**, **HeroClass**, **EnemyType**, **BountyType** enums replace bare strings (backward-compatible via `str` inheritance).
- Quality: **pytest unit test suite** (29 tests) covering combat, economy, bounty, buffs, and spawner systems.

## Prototype v1.3.0 — The Basics Are In Update

- AI: Heroes **buy potions more often** and **use potions before fleeing** (less early retreat).
- UI: ESC menu buttons have **consistent label alignment**.
- Audio: Separate volume controls: **Master**, **Music (ambient)**, and **SFX** (3 sliders).
- Pause: World camera/zoom **does not scroll** while paused / ESC menu open.
- Blacksmith: **Research weapon/armor upgrades**, then heroes can **purchase upgrades** (counts as a purchase for Journey triggers).
- UX: Demolish is **player-owned buildings only** (not monster lairs).

## Prototype v1.2.9 — UI-v2 Update

- UI: Full-screen **(exclusive)**, **borderless fullscreen-windowed**, and **windowed** modes (Graphics menu) with safer resizing behavior.
- UI: ESC now opens a centered **pause/settings** menu (Graphics/Audio/Controls).
- UI: Castle → **Build buildings** opens a centered build catalog with icons/tiles and click-to-place.
- UI: Major visual uplift — cohesive CC0 UI skin (9-slice panels/buttons/icons), tighter spacing, and Tab-toggleable right panel.

## Prototype v1.2.8 — The Audio Update (Hotfix)

- Fix: Bounty flags now render **on top of black fog** (UNSEEN), so they’re visible even in solid-black fog-of-war.

## Prototype v1.2.7 — The Audio Update

- Audio: Added **ambient loop** + expanded SFX coverage (building place/destroy, bounty place/claim, melee hit, enemy death, lair cleared).
- Audio rule (feel): **You can only hear world sounds for actions that are visible on screen** (inside camera viewport **and** `Visibility.VISIBLE`).
- Build UX: Clicking **Build** now opens a **clickable building list** (click-to-select behaves like hotkeys and enables mouse placement).
- Fog-of-war: Bounties can appear in **black fog**, and Rangers will pursue those bounties even if far away/unrevealed.
- Rangers: Baseline AI is more prone to **exploring black fog**, and Rangers earn a small amount of **XP for revealing new tiles**.

## Prototype v1.2.6 — The Ranged Update

- Combat readability: **visible ranged projectiles** for ranged attackers (heroes/enemies/towers), tuned for readability (slower + larger pixels).
- Rangers: **attack from range** (no more running into melee range first) and **bow-shot cue** in attack frames.
- Buildings: **auto-demolish at 0 HP** (except castle = game over) + **player demolish button** (instant, no refund).
- Destruction: demolished/destroyed buildings leave **rubble/debris** behind (visual-only, deterministic).
- Workers: **Peasants and Tax Collectors render as pixel sprites** (no glyphs).
- Tooling: Visual Snapshot System scenarios updated/added (including `ranged_projectiles` and `building_debris`) and strict asset validation stays green.

## Prototype v1.2.5

- New enemy: **Skeleton Archer** (`skeleton_archer`) — ranged-only instant-hit attacks with kiting behavior.
- Spawns from **Skeleton Crypt** (deterministic 80/20 mix) and is now **guaranteed in Wave 1** near the castle for easy testing.
- Pipeline: strict asset validation and Visual Snapshot System enemy catalog cover the new enemy type.

## Prototype v1.2.4

- WK3 UI polish + UX manageability: 1080p borderless default, Quit button, and closeable panels (X).
- Visual Snapshot System: deterministic screenshot capture + comparison gallery to drive look/feel iteration.
- Pixel-art pass: improved CC0 placeholder sprites for buildings/enemies (native tile-multiple sizes for buildings) while keeping fallbacks safe.
- Perf/determinism guardrails: tooling gates remain green (`qa_smoke --quick`, strict asset + attribution validator).

## Prototype v1.2.3

- Hero AI polish: reduced rapid target/goal oscillation (“spaz loops”) via commitment windows/hysteresis.
- Combat correctness: heroes **cannot apply damage while inside buildings** (hard-gated).
- Stuck recovery: deterministic detection + recovery attempts (repath/nudge/reset) to reduce “frozen in the wild” cases.
- QA gate: `python tools/qa_smoke.py --quick` includes deterministic `hero_stuck_repro` and passes (determinism guard first).
- Debuggability: debug UI exposes stuck snapshot + attack-block reason (debug-only, cache-friendly).

## Prototype v1.2.1

- Hero UI: show **Intent** and **Last decision** (action + short reason + age) in **mock** and **--no-llm** modes.
- Bounty UI: show **responders count** and deterministic **attractiveness** tier (low/med/high).
- Early-session clarity: improved bounty placement discoverability (help + tip).
- Determinism guardrails: `qa_smoke --quick` includes a determinism guard and passes (no wall-clock time in sim logic; no global RNG in sim).

## Prototype v1.2.0

- Pixel-art render pipeline improvements: nearest-neighbor scaling + reduced camera shimmer.
- Procedural pixel sprites for tiles, enemies, and buildings (with fallbacks when no assets exist).
- Combat VFX particles for hits/kills to improve readability.
- Fog-of-war visibility system and overlay rendering.
- Added neutral building system (auto-spawned map structures) and supporting systems.

## Prototype v1.1.0

- Heroes have unique stable IDs (prevents synchronized/clumped behavior from name collisions).
- Enemies retarget attackers when hit while attacking buildings.
- Added Peasants that spawn from the castle, build newly placed buildings, and repair structures (castle repair is top priority).
- Newly placed buildings deploy at 1 HP and are non-targetable until construction begins; unusable until fully built.
- Hero UI panels display potion counts; heroes can buy and carry potions when researched.
- Wave pacing tuned (warmup before first wave + larger, less frequent waves).






