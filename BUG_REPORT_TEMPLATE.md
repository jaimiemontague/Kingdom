# Bug Report Template (Kingdom Sim)

## Summary
- **Title**:
- **Severity**: Crash / Major / Minor / Cosmetic
- **Frequency**: Always / Often / Sometimes / Once

## Build / Environment
- **Version**: (see `config.py` `PROTOTYPE_VERSION`)
- **OS**:
- **Python**: `python --version`
- **Pygame**: `python -c "import pygame; print(pygame.ver)"`
- **LLM mode**: `--no-llm` / `--provider mock|openai|claude|gemini|grok`
- **API provider** (if not mock): include whether key was set (do **not** paste the key)

## Repro Steps
1.
2.
3.

## Expected

## Actual

## Repro Assets (high signal)
- **Command used** (pick one):
  - `python main.py --no-llm`
  - `python main.py --provider mock`
  - `python tools/observe_sync.py --seconds 20 --heroes 10 --seed 3 --log-every 120 --realtime`
  - `python tools/qa_smoke.py --quick`
- **Seed / parameters** (if relevant): `--seed`, `--heroes`, `--no-enemies`, etc.
- **Logs / stdout**: paste the last ~200 lines around the failure
- **Screenshot / video**: attach if visual/UI issue

## Notes / Suspicions (optional)
- **Regression?**: last known good version/commit:
- **Related systems**: AI / Combat / Economy / Pathfinding / UI / Spawner / LLM





