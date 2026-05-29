from pathlib import Path

# Patch combat gold recipient logic to use hero_id instead of hero.name
p = Path('game/systems/combat.py')
s = p.read_text(encoding='utf-8')

s = s.replace("attacker_names = getattr(enemy, 'attackers', set())", "attacker_ids = getattr(enemy, 'attackers', set())")
s = s.replace('if hero.name in attacker_names:', 'if hero.hero_id in attacker_ids:')

p.write_text(s, encoding='utf-8')
print('patched combat.py gold recipients use hero_id')
