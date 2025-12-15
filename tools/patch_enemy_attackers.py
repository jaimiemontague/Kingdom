from pathlib import Path

# Patch goblin attacker tracking to use hero_id instead of hero.name
p = Path('game/entities/enemy.py')
s = p.read_text(encoding='utf-8')

s = s.replace('self.attackers = set()  # Set of hero names who have hit this goblin', 'self.attackers = set()  # Set of hero_ids who have hit this goblin')
s = s.replace('self.attackers.add(hero.name)', 'self.attackers.add(hero.hero_id)')

p.write_text(s, encoding='utf-8')
print('patched enemy.py attackers use hero_id')
