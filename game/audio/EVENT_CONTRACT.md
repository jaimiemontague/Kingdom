# Audio Event Contract (WK6)

**Canonical event name → sound key mapping (flat contract)**

This document defines the contract between simulation events and audio file naming.
Uses flat contract keys for simplicity.

**WK6 Mid-Sprint**: Visibility-gated audio - world SFX only play if event is on-screen and `Visibility.VISIBLE`.

## Event Types → Sound Keys

### Building Events

| Event Type | Sound Key | File Path | Position Field | Notes |
|------------|-----------|-----------|----------------|-------|
| `building_placed` | `building_place` | `assets/audio/sfx/building_place.wav` or `.ogg` | `x`, `y` | Building placement sound |
| `building_destroyed` | `building_destroy` | `assets/audio/sfx/building_destroy.wav` or `.ogg` | `x`, `y` | Building destruction/demolish sound |

### Combat Events

| Event Type | Sound Key | File Path | Position Field | Notes |
|------------|-----------|-----------|----------------|-------|
| `hero_attack` | `melee_hit` | `assets/audio/sfx/melee_hit.wav` or `.ogg` | `x`, `y` | Melee attack impact sound |
| `ranged_projectile` | `bow_release` | `assets/audio/sfx/bow_release.wav` or `.ogg` | `from_x`, `from_y` (or `to_x`, `to_y`) | Bow/arrow release sound (all ranged projectiles) |
| `enemy_killed` | `enemy_death` | `assets/audio/sfx/enemy_death.wav` or `.ogg` | `x`, `y` | Enemy death sound |
| `lair_cleared` | `lair_cleared` | `assets/audio/sfx/lair_cleared.wav` or `.ogg` | (from lair_obj) | Lair cleared sound |

### Economy/Shop Events

| Event Type | Sound Key | File Path | Position Field | Notes |
|------------|-----------|-----------|----------------|-------|
| `hero_hired` | `hero_hired` | `assets/audio/sfx/hero_hired.wav` or `.ogg` | (from guild) | Hero hired sound |
| `purchase_made` | `purchase` | `assets/audio/sfx/purchase.wav` or `.ogg` | (optional) | Purchase/transaction sound |

### Bounty Events

| Event Type | Sound Key | File Path | Position Field | Notes |
|------------|-----------|-----------|----------------|-------|
| `bounty_placed` | `bounty_place` | `assets/audio/sfx/bounty_place.wav` or `.ogg` | `x`, `y` | Bounty placement sound |
| `bounty_claimed` | `bounty_claimed` | `assets/audio/sfx/bounty_claimed.wav` or `.ogg` | (from bounty) | Bounty claimed sound |

### UI Events (Not Visibility-Gated)

| Event Type | Sound Key | File Path | Position Field | Notes |
|------------|-----------|-----------|----------------|-------|
| `ui_click` | `ui_click` | `assets/audio/sfx/ui_click.wav` or `.ogg` | N/A | UI click sound (always audible) |
| `ui_confirm` | `ui_confirm` | `assets/audio/sfx/ui_confirm.wav` or `.ogg` | N/A | UI confirm sound (always audible) |
| `ui_error` | `ui_error` | `assets/audio/sfx/ui_error.wav` or `.ogg` | N/A | UI error sound (always audible) |

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
- `bounty_claimed`: 300ms
- `bow_release`: 150ms
- `melee_hit`: 100ms
- `enemy_death`: 200ms
- `lair_cleared`: 500ms
- `hero_hired`: 300ms
- `purchase`: 150ms
- `ui_click`: 100ms
- `ui_confirm`: 150ms
- `ui_error`: 200ms

## Visibility Gating (WK6 Mid-Sprint)

**Audibility Rule**: World SFX only play if:
1. Event position is within camera viewport (with 50px margin)
2. Event's grid tile is `Visibility.VISIBLE` (not `SEEN` or `UNSEEN`)

**UI Events**: Always audible (not gated by visibility)

**Position Extraction**: AudioSystem extracts position from events in this order:
1. `x`, `y` (for point events)
2. `from_x`, `from_y` (for projectiles, use source)
3. `to_x`, `to_y` (for projectiles, use target if source not available)

If no position is found, event defaults to audible (better to play than miss).

## Implementation Notes

- AudioSystem maps event types to sound keys via `AUDIO_EVENT_MAP`
- Sound files are loaded from flat paths: `assets/audio/sfx/{sound_key}.wav` or `.ogg`
- Supports both .wav and .ogg formats (tries .wav first, then .ogg)
- Missing files are handled gracefully (no-op, no crashes)
- Cooldowns prevent audio spam
- All audio is non-authoritative (never affects simulation)
- Ambient starts automatically on game start (Build A)
- Viewport context updated each frame via `AudioSystem.set_listener_view()`

## For Agent 14 (SoundDirector)

Use flat filenames matching the sound keys:
- `assets/audio/sfx/building_place.wav` or `.ogg`
- `assets/audio/sfx/building_destroy.wav` or `.ogg`
- `assets/audio/sfx/bounty_place.wav` or `.ogg`
- `assets/audio/sfx/bounty_claimed.wav` or `.ogg`
- `assets/audio/sfx/bow_release.wav` or `.ogg`
- `assets/audio/sfx/melee_hit.wav` or `.ogg`
- `assets/audio/sfx/enemy_death.wav` or `.ogg`
- `assets/audio/sfx/lair_cleared.wav` or `.ogg`
- `assets/audio/sfx/hero_hired.wav` or `.ogg`
- `assets/audio/sfx/purchase.wav` or `.ogg`
- `assets/audio/sfx/ui_click.wav` or `.ogg` (optional)
- `assets/audio/sfx/ui_confirm.wav` or `.ogg` (optional)
- `assets/audio/sfx/ui_error.wav` or `.ogg` (optional)
- `assets/audio/ambient/ambient_loop.ogg` or `.wav`

## For Agent 12 (ToolsDevEx)

Validate that audio files match this flat structure in `tools/validate_assets.py`.

## Audio Settings (WK7)

**Master Volume Control**:
- **API**: `AudioSystem.set_master_volume(volume_0_to_1: float)` and `AudioSystem.get_master_volume() -> float`
- **Range**: 0.0 to 1.0 (0.0 = mute, 1.0 = full volume)
- **Default**: 0.8 (80% per PM decision)
- **UI Display**: 0-100% slider (UI converts to 0.0-1.0 for API)
- **Applies To**: All SFX and ambient (master volume multiplies individual sound volumes)
- **Behavior**: 
  - Volume changes are immediate (no restart required)
  - Volume is post-processing (applied at playback time, not during event emission)
  - Volume does not bypass visibility gating (world SFX still requires on-screen + Visibility.VISIBLE)
  - UI sounds are exempt from fog gating but still respect master volume
- **Persistence**: In-memory for Build A (defer to Build B if file persistence is needed)
- **Non-authoritative**: Volume settings are UI-only state; never affect simulation state or determinism

**Optional Split (Build B)**:
- SFX volume and ambient volume can be split in future (separate sliders)
- For Build A: master volume only (simple and safe)

## For Agent 03 (Architecture)

Ensure all sound-worthy events include position fields:
- Point events: `x`, `y`
- Projectile events: `from_x`, `from_y` (and optionally `to_x`, `to_y`)
- Building events: `x`, `y` (world position, not grid)
- UI events: no position required (always audible)

## For Agent 08 (UX/UI)

**Audio Settings UI Contract**:
- Call `audio_system.set_master_volume(volume_0_to_1)` when slider changes
- Call `audio_system.get_master_volume()` to read current value
- Display 0-100% in UI (convert: `ui_value = api_value * 100`, `api_value = ui_value / 100`)
- Default slider position: 80% (0.8 in API)
- Volume changes are immediate (no apply button needed)
