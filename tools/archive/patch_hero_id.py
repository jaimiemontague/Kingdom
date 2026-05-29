import re
from pathlib import Path

p = Path("game/entities/hero.py")
s = p.read_text(encoding="utf-8")

if "import itertools" not in s:
    s = re.sub(r"(import\s+math\s*\r?\n)", "\\1import itertools\n", s, count=1)

if "HERO_ID_COUNTER" not in s:
    s = re.sub(
        r"(\)\s*\r?\n\s*\r?\n)(class\s+HeroState)",
        "\\1# Stable numeric IDs for heroes (names can collide).\nHERO_ID_COUNTER = itertools.count(1)\n\n\\2",
        s,
        count=1,
    )

if "self.hero_id" not in s:
    s = re.sub(
        r"(def __init__\(self, x: float, y: float, hero_class: str = \"warrior\"\):\s*\r?\n)",
        "\\1        self.hero_id = next(HERO_ID_COUNTER)\n",
        s,
        count=1,
    )

p.write_text(s, encoding="utf-8")
print("patched hero.py hero_id")
