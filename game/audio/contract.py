"""
Audio event → sound-key contract (single source of truth).

WK79: Lifted out of audio_system.py so any reader (audio_system, tools,
future contract unification) imports the canonical mapping from one place.
Behavior byte-identical to the prior in-module dict literals.
"""
from __future__ import annotations

# WK6: Canonical event name → sound key mapping (flat contract)
# WK6 Mid-Sprint: Expanded to cover more real-world actions
# This is the contract that Agent 14 and Agent 12 must align with.
# Uses flat keys: building_place, building_destroy, bounty_place, bow_release, ui_click, etc.
# Files are located at: assets/audio/sfx/{sound_key}.wav or .ogg
AUDIO_EVENT_MAP = {
    # Building events
    "building_placed": "building_place",
    "building_destroyed": "building_destroy",

    # Combat events
    "hero_attack": "melee_hit",
    "ranged_projectile": "bow_release",
    "enemy_killed": "enemy_death",
    "lair_cleared": "lair_cleared",

    # Boss encounter events (dragon-only cues; non-dragon bosses stay silent)
    "boss_encounter_started": "dragon_roar",
    "boss_phase_changed": "dragon_phase",
    "boss_ability_telegraphed": "dragon_fire_telegraph",
    "boss_ability_resolved": "dragon_fire_impact",

    # Bounty events
    "bounty_placed": "bounty_place",
    "bounty_claimed": "bounty_claimed",

    # Economy/Shop events
    "hero_hired": "hero_hired",
    "purchase_made": "purchase",

    # POI discovery event (WK55)
    "poi_discovered": "poi_discovered",

    # UI events (optional, not visibility-gated)
    "ui_click": "ui_click",
    "ui_confirm": "ui_confirm",
    "ui_error": "ui_error",
    # wk14: interior building under attack (while player is in interior view)
    "interior_building_under_attack": "building_under_attack_rumble",
}

# Sound cooldowns (milliseconds) to prevent spam
# Agent 14 will provide final values; these are Build A defaults
SOUND_COOLDOWNS_MS = {
    "building_place": 200,
    "building_destroy": 500,
    "bounty_place": 200,
    "bounty_claimed": 300,
    "bow_release": 150,
    "melee_hit": 100,
    "enemy_death": 200,
    "lair_cleared": 500,
    "dragon_roar": 2000,
    "dragon_phase": 1200,
    "dragon_fire_telegraph": 300,
    "dragon_fire_impact": 500,
    "hero_hired": 300,
    "purchase": 150,
    "ui_click": 100,
    "ui_confirm": 150,
    "ui_error": 200,
    "building_under_attack_rumble": 3000,  # wk14: throttle so not every frame
    "poi_discovered": 1000,  # WK55: brief cooldown for discovery chime
}
