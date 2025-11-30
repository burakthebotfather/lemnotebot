import re
from typing import Tuple, Optional

CHAT_MAP = {
    -1002079167705: ("A. Mousse Art Bakery - Белинского, 23", 48),
    -1002936236597: ("B. Millionroz.by - Тимирязева, 67", 3),
    -1002423500927: ("E. Flovi.Studio - Тимирязева, 65Б", 2),
    -1003117964688: ("F. Flowers Titan - Мележа, 1", 5),
    -1002864795738: ("G. Цветы Мира - Академическая, 6", 3),
    -1002535060344: ("H. Kudesnica.by - Старовиленский тракт, 10", 5),
    -1002477650634: ("I. Cvetok.by - Восточная, 41", 3),
    -1003204457764: ("J. Jungle.by - Неманская, 2", 4),
    -1002660511483: ("K. Pastel Flowers - Сурганова, 31", 3),
    -1002360529455: ("333. ТЕСТ БОТОВ - 1-й Нагатинский пр-д", 3),
    -1002538985387: ("L. Lamour.by - Кропоткина, 84", 3),
}

TRIGGERS = {
    "+ мк светло-серая": 10.35,
    "+ мк темно-серая": 12.67,
    "+ мк голубая": 13.33,
    "+ мк розовая": 11.01,
    "+ мк коричневая": 8.69,
    "+ мк салатовая": 8.03,
    "+ мк оранжевая": 6.37,
    "+ мк красная": 5.71,
    "+ мк синяя": 4.05,
    "+ мк": 2.39,
    "+": 2.56,
    "габ": 2.89,
}

_sorted_triggers = sorted(TRIGGERS.items(), key=lambda x: -len(x[0]))

def parse_trigger_and_amount(text: str) -> Tuple[Optional[float], Optional[str]]:
    if "+" not in text:
        return None, None
    idx = text.find("+")
    right = text[idx:].lower().strip()
    # check for multiplier for gаб like '3габ' or '3 габ'
    gab_match = re.search(r"(\d+)\s*габ", right)
    if gab_match:
        n = int(gab_match.group(1))
        amount = n * TRIGGERS["габ"]
        return amount, f"{n}габ"
    if "габ" in right:
        return TRIGGERS["габ"], "габ"
    # match longest trigger
    for key, val in _sorted_triggers:
        if right.startswith(key):
            return val, key
    # fallback: if there's '+' alone
    if right.startswith("+"):
        return TRIGGERS["+"], "+"
    return None, None
