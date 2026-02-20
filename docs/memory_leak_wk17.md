# WK17 Memory Leak Profile Report

**For Agent 03 (Technical Director):** Use this document to implement fixes in Round 2.

---

## Root cause summary (documented for Agent 03)

Profile: **5-minute headless `--no-llm` run** (300s). Tracemalloc comparison: end vs start. Total net allocated size increase ~**0.28 MiB** (growth plateaus; not an unbounded leak in headless). The **lag/long-session choke** reported in playtests is driven by **allocation churn** and **GC pressure**, not a single retained reference. Main contributors:

### 1. **Pathfinding (primary)**

- **Location:** `game/systems/pathfinding.py` — `get_neighbors()` (lines 22, 31) and `find_path()` (lines 82, 122, 127, 130).
- **What happens:** Every A* call allocates new lists/sets/dicts (neighbors, blocked, open_set, came_from, g_score, f_score). There is **no path cache**. With many entities replanning every tick (or frequently), this produces **~1.2k+ tuple allocations per run** from neighbor lists alone, plus heappush/came_from/g_score traffic.
- **Evidence:** Top size growth: +64 KiB (line 31), +23 KiB (line 130), +19 KiB (line 22). Top block count: +1176, +425, +356 from pathfinding.
- **Recommendation:** (a) Add a **path cache** keyed by (start, goal, blocked_hash or world_version) with a small max size and TTL, or (b) **Reduce replan frequency** (commitment window: do not replan every tick if goal unchanged and path still valid). Prefer (b) first to avoid cache invalidation complexity; then consider (a) if needed.

### 2. **Graphics / animation (secondary)**

- **Locations:** `game/graphics/animation.py` (line 95: `pygame.transform.scale`), `game/graphics/renderers/enemy_renderer.py` (line 99: `pygame.transform.flip`), `game/graphics/enemy_sprites.py` (clips/AnimationPlayer).
- **What happens:** Scale and flip create new surfaces when not fully cached; new enemy types or frame requests create clips/players. Sprite libraries cache by (type, size) but per-entity or per-frame code paths may bypass cache.
- **Recommendation:** Ensure all transform.scale/transform.flip in render paths are served from caches (e.g. by (source_id, size) or (frame, flip_key)). Cap cache size or use LRU.

### 3. **Perf overlay font (secondary)**

- **Location:** `game/engine.py` line 1290: `font = pygame.font.Font(None, 72)`.
- **What happens:** A new Font is created (likely every overlay refresh). Should be created once and reused.
- **Recommendation:** Create the overlay font once at init or first use and reuse (same as other font_cache patterns).

### 4. **Renderer registry and dead entities**

- **Status:** `RendererRegistry.prune()` is called every 1.0 sim seconds in the engine; dead entities are removed from `engine.enemies` in `_cleanup_after_combat()`. No unbounded renderer growth observed in profile.
- **Recommendation:** Keep current prune cadence; ensure `_cleanup_after_combat()` is always called after combat resolution so dead enemies are removed from the list and prune can drop their renderers.

### 5. **Bounty list comprehension**

- **Location:** `game/systems/bounty.py` line 353: `self.bounties = [b for b in self.bounties if not b.claimed]`.
- **What happens:** New list allocated on each cleanup. Minor; acceptable if cleanup is cadenced. If this runs every tick, consider in-place removal or less frequent filter.

---

## Acceptance criteria (Round 2)

- Memory **plateaus** over a 5-minute run (no monotonic growth beyond ~0.3 MiB in headless; real play with window may differ slightly).
- Pathfinding-related allocation rate reduced (commitment window or path cache).
- Perf overlay does not create a new Font every refresh.
- `python tools/qa_smoke.py --quick` remains PASS after changes.

---

## Raw tracemalloc report (300s headless, --no-llm)

## Top 40 allocations by size increase (traceback)

1. **64.3 KiB** (1176 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 31
       neighbors.append((nx, ny))

2. **23.2 KiB** (425 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 130
       heapq.heappush(open_set, (f_score[neighbor], neighbor))

3. **19.6 KiB** (338 blocks)
     File "C:\Python313\Lib\tracemalloc.py", line 558
       traces = _get_traces()

4. **19.5 KiB** (356 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 22
       neighbors.append((nx, ny))

5. **19.0 KiB** (206 blocks)
     File "<frozen abc>", line 123

6. **-17.2 KiB** (-314 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\world.py", line 185
       newly_revealed.add((x, y))

7. **12.4 KiB** (16 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\enemy.py", line 253
       self._path_goal = None

8. **11.6 KiB** (185 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\animation.py", line 95
       img = pygame.transform.scale(img, scale_to)

9. **6.4 KiB** (150 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\enemy_renderer.py", line 99
       frame = pygame.transform.flip(frame, True, False)

10. **6.2 KiB** (30 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\registry.py", line 42
       renderer = EnemyRenderer(enemy_id=key, enemy_type=str(getattr(enemy, "enemy_type", "goblin")))

11. **5.5 KiB** (115 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\engine.py", line 1290
       font = pygame.font.Font(None, 72)

12. **5.1 KiB** (30 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\enemy_sprites.py", line 69
       return AnimationPlayer(clips=clips, initial="idle")

13. **-4.8 KiB** (-44 blocks)
     File "<frozen importlib._bootstrap_external>", line 784

14. **3.6 KiB** (76 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\ui\widgets.py", line 67
       key = (id(font), normalized_text, normalized_color)

15. **3.3 KiB** (29 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\enemy_sprites.py", line 61
       clips[action] = AnimationClip(frames=frames, frame_time_sec=meta["frame_time"], loop=meta["loop"])

16. **3.2 KiB** (11 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\lair.py", line 195
       return [Wolf(world_x, world_y) for _ in range(n)]

17. **2.9 KiB** (13 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\worker_sprites.py", line 84
       clips[action] = AnimationClip(frames=frames, frame_time_sec=meta["frame_time"], loop=meta["loop"])

18. **2.8 KiB** (44 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 83
       surf = pygame.Surface((s, s), pygame.SRCALPHA)

19. **2.8 KiB** (44 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 68
       key = (int(tile_type), int(v), s)

20. **2.5 KiB** (46 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\bounty.py", line 353
       self.bounties = [b for b in self.bounties if not b.claimed]

21. **-2.5 KiB** (-10 blocks)
     File "C:\Users\Jaimie Montague\AppData\Roaming\Python\Python313\site-packages\pygame\__init__.py", line 53
       class MissingModule:

22. **2.4 KiB** (39 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\ui\widgets.py", line 66
       normalized_color = (int(color[0]), int(color[1]), int(color[2]))

23. **2.4 KiB** (38 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\ui\widgets.py", line 70
       surf = font.render(normalized_text, True, normalized_color)

24. **2.1 KiB** (1 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 74
       cls._cache[key] = surf

25. **2.1 KiB** (8 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\engine.py", line 712
       self.peasants.append(Peasant(castle.center_x, castle.center_y))

26. **2.1 KiB** (7 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\registry.py", line 50
       renderer = PeasantRenderer(peasant_id=key)

27. **2.1 KiB** (48 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 116
       surf.fill(pal.grass)

28. **2.0 KiB** (51 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\enemy.py", line 254
       goal_key = (int(target_x), int(target_y))

29. **2.0 KiB** (36 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\animation.py", line 90
       frames: List[pygame.Surface] = []

30. **2.0 KiB** (25 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\font_cache.py", line 68
       key = (

31. **1.9 KiB** (35 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 82
       blocked.add((building.grid_x + dx, building.grid_y + dy))

32. **1.9 KiB** (6 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\lair.py", line 255
       return [Bandit(world_x, world_y) for _ in range(n)]

33. **1.9 KiB** (6 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\lair.py", line 177
       return [Goblin(world_x, world_y) for _ in range(n)]

34. **1.8 KiB** (36 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\animation.py", line 96
       frames.append(img)

35. **1.6 KiB** (29 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\enemy_renderer.py", line 53
       self._last_pos = (x, y)

36. **1.6 KiB** (25 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\font_cache.py", line 91
       surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)

37. **1.6 KiB** (25 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\font_cache.py", line 72
       (int(shadow_color[0]), int(shadow_color[1]), int(shadow_color[2])),

38. **1.6 KiB** (25 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\font_cache.py", line 71
       (int(color[0]), int(color[1]), int(color[2])),

39. **1.5 KiB** (2 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\enemy.py", line 414
       self._max_kite_attempts = 5  # Fallback to stand-and-shoot after N attempts

40. **1.5 KiB** (29 blocks)
     File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\enemy_renderer.py", line 21
       self.enemy_id = str(enemy_id)

## Top 20 by block count increase

1. **+1176 blocks**, +64.3 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 31
2. **+425 blocks**, +23.2 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 130
3. **+356 blocks**, +19.5 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 22
4. **+338 blocks**, +19.6 KiB — File "C:\Python313\Lib\tracemalloc.py", line 558
5. **+206 blocks**, +19.0 KiB — File "<frozen abc>", line 123
6. **+185 blocks**, +11.6 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\animation.py", line 95
7. **+150 blocks**, +6.4 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\enemy_renderer.py", line 99
8. **+115 blocks**, +5.5 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\engine.py", line 1290
9. **+76 blocks**, +3.6 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\ui\widgets.py", line 67
10. **+51 blocks**, +2.0 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\entities\enemy.py", line 254
11. **+48 blocks**, +2.1 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 116
12. **+46 blocks**, +2.5 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\bounty.py", line 353
13. **+44 blocks**, +2.8 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 83
14. **+44 blocks**, +2.8 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\tile_sprites.py", line 68
15. **+43 blocks**, +1.0 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\systems\pathfinding.py", line 122
16. **+39 blocks**, +2.4 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\ui\widgets.py", line 66
17. **+38 blocks**, +2.4 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\ui\widgets.py", line 70
18. **+37 blocks**, +1.2 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\renderers\registry.py", line 28
19. **+36 blocks**, +2.0 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\animation.py", line 90
20. **+36 blocks**, +1.8 KiB — File "C:\Users\Jaimie Montague\OneDrive\Documents\Kingdom\game\graphics\animation.py", line 96
