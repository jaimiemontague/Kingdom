# Audio Event Contract (WK6)

**Canonical event name → sound file path mapping**

This document defines the contract between simulation events and audio file naming.
Uses nested directory structure per Agent 14's specification.

## Event Types → Sound File Paths

| Event Type | Sound File Path | Notes |
|------------|-----------------|-------|
| `building_placed` | `assets/audio/sfx/build/place.wav` | Building placement sound |
| `building_destroyed` | `assets/audio/sfx/build/destroyed.wav` | Building destruction/demolish sound |
| `bounty_placed` | `assets/audio/sfx/bounty/placed.wav` | Bounty placement sound |
| `ranged_projectile` | `assets/audio/sfx/weapons/ranger_shot.wav` or `skeleton_archer_shot.wav` | Bow/arrow release sound (determined by projectile_kind/source) |
| `ui_click` | `assets/audio/sfx/ui/click.wav` | UI click sound (optional, Build B) |

## Ambient Tracks

- **Build A**: Single neutral loop (cozy/peaceful tone)
- **File**: `assets/audio/ambient/day_loop.ogg` (or `.wav` fallback)
- **Volume**: 0.4 (background only, never masks critical cues)

## Cooldowns (milliseconds)

Default cooldowns (per Agent 14's sound map):

- `sfx/build/place`: 200ms
- `sfx/build/destroyed`: 500ms
- `sfx/bounty/placed`: 200ms
- `sfx/weapons/ranger_shot`: 150ms
- `sfx/weapons/skeleton_archer_shot`: 150ms
- `sfx/ui/click`: 100ms

## Implementation Notes

- AudioSystem maps event types to sound paths via `AUDIO_EVENT_MAP`
- Sound files are loaded from nested paths: `assets/audio/sfx/{category}/{filename}.wav`
- Missing files are handled gracefully (no-op, no crashes)
- Cooldowns prevent audio spam
- All audio is non-authoritative (never affects simulation)
- Ambient starts automatically on game start (Build A)

## For Agent 14 (SoundDirector)

Use this nested structure to organize your audio files:
- `assets/audio/sfx/build/` - Building-related sounds
- `assets/audio/sfx/bounty/` - Bounty-related sounds
- `assets/audio/sfx/weapons/` - Combat/ranged weapon sounds
- `assets/audio/sfx/ui/` - UI interaction sounds (optional)
- `assets/audio/ambient/` - Background ambient loops

## For Agent 12 (ToolsDevEx)

Validate that audio files match this nested structure in `tools/validate_assets.py`.

