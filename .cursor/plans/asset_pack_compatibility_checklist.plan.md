# Revised Asset Pack Compatibility Checklist

Here’s the full revised checklist, assuming your current terrain foundation stays as the Kenney-derived set in `assets/models/environment` with the current visual language of:

- simple stylized low-poly forms
- clean silhouettes
- modest material complexity
- readable from a strategy camera
- no dependence on advanced engine-specific shading

That means you are not shopping for "the best buildings pack" or "the best characters pack" in the abstract. You are shopping for packs that can convincingly live in the same world as that terrain.

## 1. House Style Rules

Every candidate pack should be judged against these baseline rules first.

- Must feel compatible with stylized low-poly terrain.
- Must read well from gameplay distance, not only in close-up beauty shots.
- Must look acceptable in neutral lighting.
- Must not rely on Unreal/Godot/Blender material magic to feel "complete."
- Must be usable with simple PBR or even simple diffuse shading if needed.
- Must not make the current terrain look like temporary placeholder art by comparison.
- Must not force an immediate terrain replacement unless it is extraordinarily good.

If a pack fails those, stop there.

## 2. Hard Reject Rules

Reject a candidate immediately if any of these are true.

- License is unclear or unsafe for a commercial Steam game.
- The pack only ships as engine-native content with no clean runtime export.
- Folder structure is chaotic enough that you cannot identify the intended runtime files quickly.
- Materials rely on engine-specific shader graphs or node setups.
- Texture paths are broken, absolute, or obviously export-machine-dependent.
- Visual style is much more realistic or much more detailed than the Kenney terrain base.
- The pack only looks good with aggressive post-processing, GI, HDRI, or showcase lighting.
- Scale, pivots, or orientation are inconsistent across the pack.
- It ships many export formats but no obvious canonical one.
- You catch yourself thinking, "I can probably hack this into working."

## 3. Revised Priority Weights

Use this weighting when evaluating future packs.

- Compatibility with current terrain foundation: `30`
- Visual fit with intended game: `20`
- Technical cleanliness: `20`
- Readability at gameplay distance: `15`
- Content usefulness: `15`

Total: `100`

Interpretation:
- `85-100`: strong candidate
- `70-84`: workable if it fills a real need
- `55-69`: risky, probably reject
- `<55`: reject

## 4. Buildings Pack Checklist

This is now the most important pack category.

### Style Fit

- Would these buildings feel natural sitting on the current `grass`, `path`, `rock`, and `tree_pine` terrain?
- Do they share a similar stylization level with the current environment?
- Are the shapes bold and readable, not fussy and hyper-detailed?
- Is the color palette compatible with the terrain’s palette?
- Do they feel like part of the same world, not from a different asset store ecosystem?

### Readability

- Can I identify roof, wall, doorway, windows, and silhouette from the actual gameplay camera?
- Will the buildings still read clearly when several are grouped together?
- Are outlines and roof shapes strong enough to support gameplay readability?
- Are small details decorative rather than necessary to perceive the building?

### Technical Structure

- Is there one obvious runtime export format to use?
- Are meshes cleanly organized and named?
- Are pivots sensible?
- Do buildings sit on the ground correctly without manual correction every time?
- Are scales internally consistent across the pack?
- Are materials simple and manageable?

### Modular Usefulness

- If modular, do pieces actually snap and combine well?
- If not modular, do the building variants still cover enough gameplay use cases?
- Are there enough building types to support your economy/fantasy kingdom variety?
- Are there enough roof/wall/trim variants to avoid repetition?
- Is the pack useful for your actual building roster, not just pretty in isolation?

### Material / Shader Sanity

- Does it look acceptable with simple lighting?
- Does it avoid heavy transparency tricks?
- Does it avoid requiring layered decals or custom shader features?
- Are textures clearly organized and relative?
- Are there reasonable material counts per building?

### Performance / Scope

- Is the geometry density appropriate for a strategy game?
- Are you paying for cinematic detail you will never show?
- Will you actually use enough of the pack to justify integration cost?

### Buildings Pack Pass/Fail Questions

- Would I feel comfortable leaving the current terrain in place if I adopt this buildings pack?
- Does this improve world cohesion?
- Would this create pressure to replace the terrain immediately?
- Is it better because it is truly better for the game, or just more detailed?

If it makes the terrain feel cheap, that is a serious warning sign.

## 5. Characters Pack Checklist

Characters are the second-hardest category after buildings, because they can easily outclass or clash with the environment.

### Style Fit

- Do these characters feel believable standing next to the current terrain assets?
- Are their proportions compatible with the world?
- Is the stylization level close to the environment?
- Are they visually readable without being overly realistic?
- Do they look like they belong in a strategy sim rather than a close-up RPG?

### Gameplay Readability

- Can worker, peasant, guard, ranger, mage, and enemy silhouettes be told apart quickly?
- Can I distinguish roles from camera distance?
- Are hats, weapons, capes, bags, and class markers readable at game scale?
- Do idle and movement poses preserve silhouette clarity?

### Material / Rendering Sanity

- Do they avoid advanced hair, skin, cloth, and transparency dependencies?
- Can they look acceptable without specialized character shading?
- Are materials simple and consistent?
- Are colors doing useful gameplay work, not just beauty work?

### Rig / Animation Sanity

- Are they static props, animated characters, or modular rigs?
- If animated, is the rig clean and reusable?
- If modular, is the modularity actually useful or just fragile complexity?
- Do all characters share one skeleton family or clear compatibility?
- Are animations included or obviously supportable?

### Technical Structure

- Is there one clean runtime format?
- Are the exports named clearly?
- Are texture and material files intact and relative?
- Is the hierarchy understandable?
- Are there hidden dependencies on engine-specific character controllers or shaders?

### Scope / Usefulness

- Does this pack cover enough of your role taxonomy?
- Can it support civilian life and hero differentiation?
- Are there enough variations without becoming a maintenance nightmare?
- Will it give you the fantasy kingdom vibe you want without demanding a whole new environment style?

### Characters Pack Pass/Fail Questions

- Would these characters still look right if the terrain stayed as-is?
- Do they elevate the world or dominate it awkwardly?
- Are they readable enough for gameplay?
- Are they more detailed than the game needs?

If the answer is "they’re gorgeous, but clearly from a different game," reject.

## 6. Optional Nature Expansion Checklist

Since you’re likely keeping the Kenney terrain base for now, this is for supplemental terrain/nature packs, not replacements.

### Good Supplemental Nature Pack Qualities

- Matches the Kenney terrain stylization closely enough.
- Adds breadth without changing the whole visual language.
- Gives you more trees, rocks, shrubs, stumps, logs, bushes, flowers, or clutter.
- Uses simple materials and clean geometry.
- Keeps silhouettes readable.
- Doesn’t rely on alpha-heavy foliage tricks.

### Good Use Case

- "I want more variety while keeping the base terrain philosophy."

### Bad Use Case

- "This pack is way fancier, so maybe I can just mix it in and hope."

If a supplemental pack visually overpowers the Kenney base, it is not supplemental. It is a replacement candidate.

## 7. Intake Workflow Before Staging

Use this every time before bringing a pack into staging.

### Phase A: First Pass

- Read the license.
- Identify the canonical export format.
- Ignore all other exports unless necessary.
- Inspect folder structure.
- Check whether textures and materials are intact and relative.
- Open representative screenshots or preview files.

### Phase B: Visual Fit

Check 5 representative assets:

- one simple asset
- one hero/centerpiece asset
- one multi-material asset
- one alpha/transparency asset if applicable
- one complex or "stress test" asset

Ask:

- Does it look good in neutral light?
- Does it fit the Kenney terrain style?
- Does it read from your gameplay camera?
- Does it feel too realistic or too detailed?

### Phase C: Technical Fit

- Check scale consistency.
- Check pivot placement.
- Check orientation/up-axis sanity.
- Check material count.
- Check texture path health.
- Check for engine-specific shader dependence.
- Check if file naming and structure are sane.

### Phase D: Strategic Fit

- Does this fill a real gap in the game?
- Does it save time?
- Does it improve cohesion?
- Does it create future maintenance burden?

## 8. Shopping Questions To Ask Yourself

When evaluating any candidate, ask these directly:

- Would this still look good if dropped into my current terrain world today?
- Does this make the Kenney terrain feel more complete, or more temporary?
- Does this help the game camera, or only the marketing screenshot?
- Am I buying a pack, or buying six months of integration work?
- If this becomes my house standard, am I happy about that?
- If I ship with this plus the Kenney terrain, will the game feel coherent?

## 9. Copy-Paste Scorecard

Use this while shopping.

```text
PACK NAME:
CATEGORY: Buildings / Characters / Nature Supplement
SOURCE:
PRICE:
LICENSE:

1. Terrain Compatibility (30)
- Fits current Kenney terrain style:
- Works with current palette/silhouette language:
- Does not force terrain replacement:
Score: __ / 30

2. Visual Fit (20)
- Matches intended Kingdom Sim tone:
- Looks good in neutral lighting:
- Reads well from gameplay camera:
Score: __ / 20

3. Technical Cleanliness (20)
- Clear canonical export:
- Clean materials/textures:
- No broken paths or engine-only dependencies:
- Sensible pivots/scale/orientation:
Score: __ / 20

4. Gameplay Readability (15)
- Strong silhouettes:
- Important gameplay classes/buildings read clearly:
- Detail level appropriate for camera distance:
Score: __ / 15

5. Content Usefulness (15)
- Covers real game needs:
- Enough variation:
- Worth integration effort:
Score: __ / 15

TOTAL: __ / 100

Decision:
- Accept
- Maybe
- Reject

Main reasons:
-
-
-

Biggest risk:
-

Would this force terrain replacement later?
- Yes
- No
- Maybe
```

## 10. Final Rule Of Thumb

With the Kenney terrain as your current foundation, the decision rule becomes very simple:

- If a candidate pack works with the current terrain, it gets a serious look.
- If it makes the current terrain feel obviously wrong, reject it unless you are deliberately planning a whole-world visual reset.
- If it is technically messy and stylistically only "kind of" compatible, reject it faster than you would have before.

That is the biggest revision.

If you want, I can next turn this into two shorter ready-to-use versions:

- a fast 2-minute shopping filter
- a deep 15-minute pre-staging review
