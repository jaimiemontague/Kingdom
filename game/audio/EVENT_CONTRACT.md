# Audio Event Contract (WK6)

**Canonical event name → sound key mapping (flat contract)**

This document defines the contract between simulation events and audio file naming.
Uses flat contract keys for simplicity.

## Event Types → Sound Keys

| Event Type | Sound Key | File Path | Notes |
|------------|-----------|-----------|-------|
| `building_placed` | `building_place` | `assets/audio/sfx/building_place.wav` or `.ogg` | Building placement sound |
| `building_destroyed` | `building_destroy` | `assets/audio/sfx/building_destroy.wav` or `.ogg` | Building destruction/demolish sound |
| `bounty_placed` | `bounty_place` | `assets/audio/sfx/bounty_place.wav` or `.ogg` | Bounty placement sound |
| `ranged_projectile` | `bow_release` | `assets/audio/sfx/bow_release.wav` or `.ogg` | Bow/arrow release sound (all ranged projectiles) |
| `ui_click` | `ui_click` | `assets/audio/sfx/ui_click.wav` or `.ogg` | UI click sound (optional, Build B) |

## Ambient Tracks

- **Build A**: Single neutral loop (cozy/peaceful tone)
- **Sound Key**: `ambient_loop`
- **File**: `assets/audio/ambient/ambient_loop.ogg` or `.wav`
- **Volume**: 0.4 (background only, never masks critical cues)

## Cooldowns (milliseconds)

Default cooldowns (Build A):

- `building_place`: 200ms
- `building_destroy`: 500ms
- `bounty_place`: 200ms
- `bow_release`: 150ms
- `ui_click`: 100ms

## Implementation Notes

- AudioSystem maps event types to sound keys via `AUDIO_EVENT_MAP`
- Sound files are loaded from flat paths: `assets/audio/sfx/{sound_key}.wav` or `.ogg`
- Supports both .wav and .ogg formats (tries .wav first, then .ogg)
- Missing files are handled gracefully (no-op, no crashes)
- Cooldowns prevent audio spam
- All audio is non-authoritative (never affects simulation)
- Ambient starts automatically on game start (Build A)

## For Agent 14 (SoundDirector)

Use flat filenames matching the sound keys:
- `assets/audio/sfx/building_place.wav` or `.ogg`
- `assets/audio/sfx/building_destroy.wav` or `.ogg`
- `assets/audio/sfx/bounty_place.wav` or `.ogg`
- `assets/audio/sfx/bow_release.wav` or `.ogg`
- `assets/audio/sfx/ui_click.wav` or `.ogg` (optional)
- `assets/audio/ambient/ambient_loop.ogg` or `.wav`

## For Agent 12 (ToolsDevEx)

Validate that audio files match this flat structure in `tools/validate_assets.py`.
