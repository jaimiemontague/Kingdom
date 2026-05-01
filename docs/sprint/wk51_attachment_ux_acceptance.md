# WK51 — Attachment UX (Pin + Recall) — Player acceptance checklist

**How to run:** from the repo root, `python main.py --provider mock`  
**Time budget:** about 5 minutes for items 1–6; item 7 includes a one-line automated proof when available.

**Renderers:** default is 3D (Ursina). For the same checks in 2D, use `python main.py --provider mock --renderer pygame`.

Alignment: [WK49 roadmap Phase 3 — Attachment UX](.cursor/plans/wk49_hero_profile_roadmap_6f3a1b2c.plan.md) (pin/favorite as player UI state, not sim signal), and sprint plan [WK51 Phase 3](.cursor/plans/wk51_phase_3_attachment_94c67db4.plan.md).

---

## Checklist

- [ ] **Pin is obvious in the hero panel.** With a hero selected, a **Pin** control appears at the **top-right** of the **left** hero panel (beside the close control). At a glance you can tell **pinned** (filled/highlight “P”) vs **not pinned** (outline/dim “P”).
- [ ] **Pin does not poke the kingdom.** While that hero stays selected, click Pin/Unpin a few times. **Nothing** in the world should change because of it: same hero movement intents, fights, purchases, AI pacing — no sudden retarget or economy jump tied to Pin.
- [ ] **Recall appears when the panel is closed.** Pin the hero, then close the sheet (× or clicking away on the map). A **Recall** control appears on the **bottom HUD**, shows that hero’s **name**, and identifies who you pinned.
- [ ] **Recall = panel + camera, fast, both renderers.** Pan the camera away, click **Recall**. The **left hero panel** opens again on that pinned hero **and** the **camera snaps** so they are centered. The snap should finish **within one second** (instant snap is fine). Repeat once in **default (Ursina)** and once with `--renderer pygame`.
- [ ] **Single pin slot.** Pin hero A (see Recall shows A). Select hero B and pin B. Recall should now show **B’s** name — **only one** pinned hero at a time (latest wins).
- [ ] **Fallen hero.** Let the pinned hero **die**. Recall should show their name with **“(fallen)”**, look **greyed/disabled**, stay up for **roughly ten seconds** of game time, then the Recall control **goes away** (pin clears).
- [ ] **No AI, combat, or bounty bias from Pin.** Hero behavior must not favor pinned heroes; combat and bounty picks stay the same whether you Pin or not. **Proof:** two **seeded** mock-provider runs identical except for Pin/recall UI actions must match hero outcomes — **automated**: `python -m pytest tests/test_wk51_pin_determinism.py -q` once Agent 11 adds that test (`test_two_runs_match_with_and_without_pin`). Until then, manual sanity: spam Pin during a stable moment and confirm no change to bounty text, intent lines, or a fight already in progress.

---

## Pass / fail notes

If anything fails, record: renderer (`ursina` vs `python.exe … --renderer pygame`), step number, expected vs observed, and the last lines of terminal output.
