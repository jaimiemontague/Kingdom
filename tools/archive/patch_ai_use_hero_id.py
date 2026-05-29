from pathlib import Path
import re

# Patch BasicAI to use hero.hero_id as the stable key instead of hero.name
p = Path('ai/basic_ai.py')
s = p.read_text(encoding='utf-8')

# hero_zones key usage
s = s.replace('self.hero_zones = {}  # hero.name -> (center_x, center_y)', 'self.hero_zones = {}  # hero.hero_id -> (center_x, center_y)')
s = s.replace('if hero.name in self.hero_zones:', 'if hero.hero_id in self.hero_zones:')
s = s.replace('return self.hero_zones[hero.name]', 'return self.hero_zones[hero.hero_id]')
s = s.replace('self.hero_zones[hero.name] = (zone_x, zone_y)', 'self.hero_zones[hero.hero_id] = (zone_x, zone_y)')

# LLM decision keying
s = s.replace('decision = self.llm_brain.get_decision(hero.name)', 'decision = self.llm_brain.get_decision(hero.hero_id)')

# debug throttle keys (best-effort)
s = re.sub(r'throttle_key=f"\{hero\.name\}_idle"', 'throttle_key=f"{hero.hero_id}_idle"', s)
s = re.sub(r'throttle_key=f"\{hero\.name\}_zone"', 'throttle_key=f"{hero.hero_id}_zone"', s)
s = re.sub(r'throttle_key=f"\{hero\.name\}_no_enemy"', 'throttle_key=f"{hero.hero_id}_no_enemy"', s)

p.write_text(s, encoding='utf-8')
print('patched basic_ai.py hero_id keys')
