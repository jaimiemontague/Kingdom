# Panda3D `.bam` cache noise (WK32)

When launching Ursina mode, you may see scary looking log lines like:

```
:loader(error): Unable to open models_compressed/assets/models/environment/rock_gy_tall.bam
saved .bam to: models_compressed\assets\models\environment\rock_gy_tall.bam
```

## What it means

- This is usually **expected first-run cache generation** for **new `.obj` models**.
- Panda3D checks for an existing cached `.bam` file first; if it’s missing, it logs a cache miss as `loader(error)`, then loads the `.obj` and writes the cache (`saved .bam to:`).
- The **first run can be slow** because parsing `.obj` and converting to `.bam` is work.
- If you terminate the game during this first run, you may repeatedly pay some of this cost on later attempts.

## How to prewarm (recommended)

From repo root:

```bash
python tools/prewarm_panda_bam_cache.py --environment
```

That loads all `.obj` files under `assets/models/environment/` once (offscreen) and writes their `.bam` caches under `models_compressed/`.

After this, `python main.py` (default is Ursina) or `python main.py --renderer ursina` should start faster and the cache-miss noise should disappear for those assets.

## Tree brightness note (WK32 r4)

Some promoted environment trees (notably `assets/models/environment/tree_*.obj`) can still read too bright even after the global environment/Nature tint.
You can locally retune the tree-only multiplier without code changes:

```bash
set KINGDOM_ENV_TREE_COLOR_MULT=0.65
python main.py --no-llm
```


