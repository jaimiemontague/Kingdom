## Attribution Standard (CC0 / Open-License Assets)

### Goals
- Keep attribution **clean, consistent, and auditable**.
- Make it easy to answer: “Which pack did this sprite come from, and what license applies?”
- Ensure Steam patch notes include a short **Credits** section when third-party assets ship.

### Required files (repo conventions)
- **Human-readable rollup**: `assets/ATTRIBUTION.md`
- **Per-pack verbatim license + readme**:
  - `assets/third_party/<pack_name>/LICENSE.txt`
  - `assets/third_party/<pack_name>/README.txt` (or source page text if no README)
- **Optional mapping file** (recommended if mixing packs):
  - `assets/third_party/<pack_name>/SOURCES.md` (what folders/files were taken from the pack)

### `assets/ATTRIBUTION.md` format (recommended)
For each pack:
- **Pack name**
- **Author / publisher**
- **License** (exact name)
- **Source** (URL)
- **Modifications** (e.g., resized to 32×32, palette adjustments)
- **Used for** (heroes/enemies/buildings/UI)
- **File locations** (which `assets/sprites/...` directories contain derived work)

### Patch notes “Credits” snippet (copy/paste)
Add a short section when third-party assets change:

```text
Credits / Attribution
- Pixel art includes assets from: <Pack Name> by <Author> (License: <License>). Source: <URL>.
```

### Guardrails
- Prefer **CC0** where possible; otherwise ensure the license is compatible with Steam distribution.
- Never commit assets without at least: a source URL + license text saved under `assets/third_party/<pack_name>/`.
- If we heavily edit an asset, still keep the original pack attribution; note “modified”.





