## Third-Party Asset Packs (Licenses + Provenance)

Each third-party pack lives under:

`assets/third_party/<pack_name>/`

Required contents per pack:
- `LICENSE.txt` (or `LICENSE*.txt`) — verbatim license text
- `README.txt` — verbatim upstream readme OR a short provenance note if none exists upstream

Recommended (when mixing packs or curating subsets):
- `SOURCES.md` — what we took and where it landed (folders/files)

Global rule:
- If any `assets/third_party/<pack_name>/` directory exists, `assets/ATTRIBUTION.md` must exist and list that pack with source + license + usage locations.





