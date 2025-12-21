# Release QA Checklist (Prototype)

## Before tagging a release
- **Version bump**: confirm `config.py` `PROTOTYPE_VERSION` matches release notes.
- **Changelog**: `CHANGELOG.md` updated with player-facing bullets.
- **Deps sanity**: `pip install -r requirements.txt` works on a clean venv.

## Automated smoke (required)
- Run:
  - `python tools/qa_smoke.py --quick`
- Pass criteria:
  - Exit code 0
  - No uncaught exceptions

## Manual smoke (required, ~10 minutes)
Run:
- `python main.py --provider mock`

Checklist:
- **Boot + quit**: start game, open/close debug panel, quit cleanly.
- **Build + construct**: place marketplace, confirm peasants build it.
- **Hire hero**: hire at least 1 hero, confirm they move and fight.
- **Bounties**: place bounty, confirm hero attempts to respond.
- **Pause**: toggle pause and confirm sim halts/resumes.

## Performance sanity (quick)
- Observe: no sustained “stutter” in the first few minutes at default settings.
- Optional: run longer headless:
  - `python tools/qa_smoke.py --seconds 60 --heroes 20`

## Ship/Archive
- Store the exact commands used and any known issues in release notes.



