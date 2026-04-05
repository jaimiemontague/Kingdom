# Changelog

## Prototype v1.4.6 — Ursina Input Bridge

### WK20 Sprint: Input Routing and Playability
- **Pygame UI Input Routing**: Mapped Ursina's center-origin cursor coords directly into our virtual 1080p Pygame screen space, allowing interactive elements (buttons, ESC menu, panels) to work directly inside the true 3D viewer.
- **3D Floor Raycasting**: Clicking the transparent "world" now accurately raycasts from the 3D perspective camera down to the `y=0` floor plane, yielding stable tile selections for simulating placing/selecting entities.
- **Camera Initialization**: Modified default 3D camera to frame the Castle and surrounding map, getting rid of the initial "zoomed-in single cube" issue.
- **Telemetry / Debug UI**: Implemented specific input debugging behind `KINGDOM_URSINA_DEBUG_INPUT=1` env arg to help verify Ursina raycast and input translations.

## Prototype v1.4.5 — Ursina 3D Viewer (Phase 2.1v2)

### Engine Decoupling (Phase 1)
- **InputManager abstraction**: Created a generic `InputManager` interface (`game/input_manager.py`) and `PygameInputManager` implementation, removing all direct `pygame.event` / `pygame.key` / `pygame.mouse` calls from the core engine.
- **Simulation/render split**: `GameEngine.run()` decomposed into `tick_simulation(dt)` and `render_pygame()`, allowing external loops (Ursina, headless) to drive the simulation independently.
- **Headless mode**: `GameEngine(headless=True)` skips all Pygame display, UI, audio, VFX, and sprite initialization while keeping the full simulation core (world, economy, combat, spawner, buildings, heroes).
- **`get_game_state()` API**: New method returns a snapshot dict of all simulation entities for external renderers.
- **`_NullStub` pattern**: Headless UI stubs silently absorb all method calls and attribute access, eliminating ~20 potential `AttributeError` crashes in the simulation path.

### Ursina 3D Viewer MVP (Phase 2)
- **`--renderer ursina` flag**: `main.py` now accepts `--renderer ursina` to launch the Ursina 3D viewer instead of the Pygame renderer.
- **Ursina MVP viewer**: View-only 3D diorama showing the simulation as colored primitives — castle (gold), lairs (brown), enemies (red), heroes (blue circles), peasants (orange), guards (yellow).
- **Tile-unit coordinate system**: Game pixel coordinates divided by `TILE_SIZE` (32) for proper Ursina orthographic scaling.
- **Panda3D background**: Green map background via native `setBackgroundColor()` API.
- **Camera controls**: WASD to pan, Q/E to zoom in/out.
- **Status overlay**: Real-time HUD showing Gold, Heroes, Enemies, and Buildings count.

### Tech Debt Fixed
- **16 eager `getattr` fallbacks**: Replaced all `getattr(self, "window_width", self.screen.get_width())` patterns with `self.window_width` — Python evaluates defaults eagerly, causing crashes when `self.screen` is `None`.
- **`RendererRegistry` guarded**: Set to `None` in headless mode to prevent sprite loading (`pygame.image.load().convert_alpha()`) without a display.

### New Files
- `game/input_manager.py` — Abstract InputManager interface + InputEvent dataclass
- `game/pygame_input_manager.py` — Pygame implementation of InputManager
- `game/ursina_input_manager.py` — Ursina implementation of InputManager
- `game/graphics/ursina_renderer.py` — Simulation-to-Ursina entity translator
- `game/graphics/ursina_app.py` — Ursina application wrapper
- `tools/run_headless_sim.py` — Headless simulation test harness

---

## Prototype v1.4.4 — Playtest Fixes & Hero Agency

### Hero Interaction & Chat
- **Hero Focus Mode**: Clicking any hero now opens a split right panel with a hero-centric minimap (top half) and the chat panel (bottom half), regardless of whether the hero is in a building or in the wild.
- **Chat History Persistence**: Conversation history is now stored per-hero. Clicking away and reselecting a hero picks up the chat where you left off.
- **LLM Physical Agency**: Heroes now respond to chat commands with JSON containing both a `spoken_response` and a `tool_action`. When the LLM says they'll leave a building or move somewhere, they actually do it.

### UI & UX Fixes
- **Activity text overlap fix**: HUD messages in the top-left no longer render behind the hero detail panel; they dynamically offset when the left panel is visible.
- **ESC key fix**: Pressing ESC now correctly exits Hero Focus mode first, then opens the pause menu on the next press (previously got trapped).
- **Minimap performance**: Cached the Surface allocation in `_render_hero_minimap` to eliminate per-frame memory churn that caused random lag spikes.
- **UI rendering restored**: Fixed a regression where the entire HUD disappeared due to a missing `if` guard in the render loop.

### AI & Shopping
- **Blacksmith AI fix**: Refactored `find_blacksmith_with_upgrades` → `find_blacksmith` so heroes can target any constructed blacksmith for base item purchases, not just those with researched upgrades.

---

## Prototype v1.4.3 — The LLM-AI Merger Update

### WK18 Sprint: LLM-AI Merger, Physicality, & Dev Tools
- **Hero Context Injection**: Heroes are now explicitly self-aware of their physical reality (HP, Gold, Potions, Stats, Location) through the new `hero_stat_block` injected directly into their conversational prompt.
- **Physical Soft-Collisions**: Heroes physically push each other apart (`_apply_hero_separation`) rather than clumping synchronously onto the exact same pixel coordinates.
- **The Inn Economy**: Heroes now pay a fractional loiter fee (0.5 gold/sec) to rest at the Inn and are forcefully ejected when their wallet reaches 0, returning them to the work pool.
- **Dynamic F4 Dev Tools**: Toggle the `F4` developer overlay to view real-time AI/LLM requests, responses, and errors in a fully resizable, scrolling, word-wrapped matrix log window.
- **Dev Tools Performance**: Cached the text-wrapping array in the F4 DevOverlay, completely eliminating game thread stutter when the AI makes an API request.
- **Lair Pixel Art**: Generated fully textured and distinct CC0 placeholder pixel art for the 5 hostile lairs (Goblin Camp, Wolf Den, Skeleton Crypt, Spider Nest, and Bandit Camp).

## Prototype v1.4.2 — Playability Quality Reached

### WK17 Sprint: Quality, Logic, & Immersion
- **Hero Conviction System**: Added hysteresis to hero AI behavior to prevent immediate task churning and ensure commitment to intents like shopping or errands.
- **Clickable Peasants**: Peasants can now be selected, revealing a UI info panel detailing their current action and HP.
- **Dynamic Fog of War**: Auto-spawned player structures (farms, houses, etc.) and active guards now inherently push back the fog of war, ensuring visibility over your domain.
- **Performance & Stability**: Fixed a memory leak by caching UI overlay fonts and instituting a bounded FIFO cache for the A* pathfinding system.

## Prototype v1.4.1 — UI UX Improvements and NPC Upgrades

### UI & Menu Polish

- **Pause menu button alignment:** Resume and Quit buttons now use a transparent icon placeholder when `icon_play.png`/`icon_quit.png` are missing, ensuring all 5 menu buttons align perfectly.
- **Slimmer left panel:** Hero detail panel reduced from 320px to 224px (30% slimmer) for more map visibility.
- **Right panel auto-hide:** Right panel now fully disappears when no building or entity is selected.
- **Animated research progress bar:** Marketplace, Blacksmith, and Library research shows a filling progress bar instead of a static grey bar; backed by `sim_now_ms()` for deterministic rendering.

### NPC & Interaction Upgrades

- **Tax collector clickability:** Tax collectors are now selectable on the map; clicking one opens a dedicated left panel showing Status, Carried Gold, and Total Collected.
- **Guard panel:** Clicking a guard now opens a left panel with Post, State, HP bar, and ATK stats.
- **Global hero selection:** Clicking a hero inside a building interior or clicking a hero's name/portrait in the chat panel opens their detail panel on the left.

### Economy & Pacing

- **Monster gold +50%:** Spider gold 5→8, Bandit gold 12→18 for faster mid-game income.
- **Tax rate:** Normalized to 25%.
- **Starting gold +40%:** Increased from 1500 to 2100.
- **Monster density:** Lair count 2→4, goblin spawn interval 5000→3500ms, max alive enemies 20→32.

### AI & Defense

- **Castle urgent defense:** Heroes pop out of buildings and abandon tasks to defend the castle when it's under attack.
- **Economic building defense:** Warriors now prioritize defending farms and food stands under attack.
- **Timed research system:** Research at Marketplace, Blacksmith, and Library takes real sim-time (30s for potions, scaled by cost for others) instead of instant unlock.

---

## Prototype v1.4 — Hero Chat, Graphics & UX Polish

### Bug Fixes

- **Chat input freeze:** Chat panel rate-limiting now uses real-time `pygame.time.get_ticks()` instead of the sim clock, so the panel no longer gets stuck on "Thinking..." after the first message.
- **OpenAI API parameter fallback:** Exception matching in `ai/providers/openai_provider.py` updated for newer OpenAI library error formats; cleanly falls back to `max_tokens` when `max_completion_tokens` is rejected.
- **Default LLM model:** Placeholder `gpt-5-nano` replaced with `gpt-4o-mini` in config and `.env` references.
- **Peasant overshoot & void walking:** Peasant `move_towards` in `game/entities/peasant.py` now clamps movement so large dt no longer causes overshoot, vibration, or drifting off-screen.
- **Skeleton 12-tile pathing loop:** Enemy `_long_distance_mode` in `game/entities/enemy.py` uses a hysteresis buffer (enter A* at 12 tiles, revert only at 10 tiles) so grid snapping no longer causes infinite pathing stutter.
- **Initial camera start position:** Edge-scroll is disabled until the window has mouse focus (`pygame.mouse.get_focused()`), preventing the camera from rapidly scrolling into fog on startup.
- **Spacebar centering after hero chats:** Background click-to-exit in INTERIOR/QUEST views now correctly notifies ChatPanel to end the conversation, releasing the keyboard hook so spacebar camera-center works again.
- **WASD while chatting:** Camera panning is skipped when the hero ChatPanel is active, so typing W/A/S/D no longer moves the view.

### Quality of Life & UI

- **Dedicated hero left panel:** HUD now has a permanent 320px left column (`_panel_left`) for hero details; right panel is strictly for Building Summaries, Building Interiors, and Player–Hero Chat.
- **Message feed offset:** System notification feed shifts horizontally when the left panel is visible so messages aren’t hidden behind hero stats.

### Graphics & Engine (4× detail pass)

- **Procedural map textures:** `game/graphics/tile_sprites.py` — Grass (24 variants): 3D grass tufts, macro clumps, pebble clusters, flower props. Paths (12): cobblestone borders, cart-rut tracks. Trees (8): 3-tier crowns, drop shadows, bark texture, root splits. Water (6): animated wave crest strokes.
- **Entity animation generation:** `tools/generate_cc0_placeholders.py` refactored to multi-frame sequences (6–8 frame walk with articulated strides, class/type weapon arcs); baked idle, walk, attack, hurt, dead for heroes, enemies, workers.
- **Building procedural detail:** Building frames upgraded with material texturing (wood slats, stone blocks), sloped roof shingle grids, and dynamic layered windows with lit/unlit states; determinism preserved via coordinate hashing.

---

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






