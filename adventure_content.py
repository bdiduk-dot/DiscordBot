from __future__ import annotations

from copy import deepcopy
from typing import Any


DIVE_TANKS: dict[str, dict[str, Any]] = {
    "scuba_basic": {
        "name": "Базовый акваланг",
        "emoji": "🤿",
        "oxygen": 100,
        "price": 18_000,
        "description": "Стартовый баллон для безопасных погружений.",
    },
    "scuba_reinforced": {
        "name": "Усиленный акваланг",
        "emoji": "🤿",
        "oxygen": 200,
        "price": 42_000,
        "description": "Увеличенный запас кислорода для длинных вылазок.",
    },
    "scuba_titan": {
        "name": "Титановый акваланг",
        "emoji": "🤿",
        "oxygen": 300,
        "price": 88_000,
        "description": "Премиум-баллон для самых жадных и глубоких забегов.",
    },
}

DIVE_GEAR: dict[str, dict[str, Any]] = {
    "abyss_lamp": {
        "name": "Фонарик бездны",
        "emoji": "🔦",
        "price": 26_000,
        "description": "Нужен для погружений в кромешную тьму Марианской впадины.",
        "reusable": True,
    },
}

DIG_TOOLS: dict[str, dict[str, Any]] = {
    "excavation_kit": {
        "name": "Набор археолога",
        "emoji": "⛏️",
        "price": 14_000,
        "description": "Расходник для одной раскопочной экспедиции.",
        "uses": 1,
    },
    "signal_scanner": {
        "name": "Сканер пустот",
        "emoji": "📡",
        "price": 36_000,
        "description": "Повышает шанс поймать мощный сигнал и редкую находку.",
        "reusable": True,
    },
}

DIVE_LOCATIONS: dict[str, dict[str, Any]] = {
    "coral_reef": {
        "name": "Коралловый риф",
        "emoji": "🪸",
        "min_level": 1,
        "risk": 0.20,
        "loot_bias": "safe",
        "description": "Много рыбы и ракушек, почти без серьёзной угрозы.",
    },
    "sunken_galleon": {
        "name": "Затонувший галеон",
        "emoji": "🏴‍☠️",
        "min_level": 2,
        "risk": 0.38,
        "loot_bias": "treasure",
        "description": "Сундуки, золото и зубастые соседи по маршруту.",
    },
    "mariana_trench": {
        "name": "Марианская впадина",
        "emoji": "🌑",
        "min_level": 4,
        "risk": 0.58,
        "loot_bias": "mythic",
        "requires": "abyss_lamp",
        "description": "Темнота, давление и самые редкие артефакты глубины.",
    },
}

DIG_ZONES: dict[str, dict[str, Any]] = {
    "dusty_fields": {
        "name": "Пыльные поля",
        "emoji": "🏺",
        "min_level": 1,
        "rarity_bias": "common",
        "description": "Тихая стартовая зона с мелкими фрагментами и монетами.",
    },
    "forgotten_ruins": {
        "name": "Забытые руины",
        "emoji": "🗿",
        "min_level": 2,
        "rarity_bias": "rare",
        "description": "Старые залы и обломки реликвий с хорошим сигналом.",
    },
    "royal_catacombs": {
        "name": "Королевские катакомбы",
        "emoji": "👑",
        "min_level": 4,
        "rarity_bias": "epic",
        "description": "Опасная археология с шансом на элитные реликвии.",
    },
}

ANTIQUARY_ITEMS: dict[str, dict[str, Any]] = {
    "reef_shell": {
        "name": "Рифовая раковина",
        "emoji": "🐚",
        "item_type": "antiquary_loot",
        "base_value": 3_400,
        "description": "Красивая раковина, которую охотно скупает Антиквар.",
    },
    "pirate_compass": {
        "name": "Пиратский компас",
        "emoji": "🧭",
        "item_type": "antiquary_loot",
        "base_value": 12_500,
        "description": "Добыча с галеона, ценится за сохранность и редкость.",
    },
    "abyss_shard": {
        "name": "Осколок бездны",
        "emoji": "💠",
        "item_type": "antiquary_loot",
        "base_value": 21_000,
        "description": "Странный кристалл из глубинных зон.",
    },
    "coral_idol_a": {
        "name": "Фрагмент идола рифа I",
        "emoji": "🪸",
        "item_type": "antiquary_fragment",
        "family": "coral_idol",
        "base_value": 5_500,
        "description": "Часть кораллового идола.",
    },
    "coral_idol_b": {
        "name": "Фрагмент идола рифа II",
        "emoji": "🪸",
        "item_type": "antiquary_fragment",
        "family": "coral_idol",
        "base_value": 5_700,
        "description": "Часть кораллового идола.",
    },
    "coral_idol_c": {
        "name": "Фрагмент идола рифа III",
        "emoji": "🪸",
        "item_type": "antiquary_fragment",
        "family": "coral_idol",
        "base_value": 6_200,
        "description": "Часть кораллового идола.",
    },
    "leviathan_sigil_a": {
        "name": "Фрагмент сигила Левиафана I",
        "emoji": "🌊",
        "item_type": "antiquary_fragment",
        "family": "leviathan_sigil",
        "base_value": 10_500,
        "description": "Редкая древняя пластина с давящим холодом.",
    },
    "leviathan_sigil_b": {
        "name": "Фрагмент сигила Левиафана II",
        "emoji": "🌊",
        "item_type": "antiquary_fragment",
        "family": "leviathan_sigil",
        "base_value": 11_200,
        "description": "Редкая древняя пластина с давящим холодом.",
    },
    "leviathan_sigil_c": {
        "name": "Фрагмент сигила Левиафана III",
        "emoji": "🌊",
        "item_type": "antiquary_fragment",
        "family": "leviathan_sigil",
        "base_value": 11_900,
        "description": "Редкая древняя пластина с давящим холодом.",
    },
    "coral_idol": {
        "name": "Идол рифа",
        "emoji": "🗿",
        "item_type": "antiquary_relic",
        "family": "coral_idol",
        "assembled": True,
        "base_value": 17_400,
        "description": "Собранная реликвия рифовых погружений.",
    },
    "leviathan_sigil": {
        "name": "Сигил Левиафана",
        "emoji": "👁️",
        "item_type": "antiquary_relic",
        "family": "leviathan_sigil",
        "assembled": True,
        "base_value": 33_600,
        "description": "Собранный древний символ бездны.",
    },
}

RELIC_RECIPES: dict[str, dict[str, Any]] = {
    "coral_idol": {
        "name": "Идол рифа",
        "emoji": "🗿",
        "parts": ["coral_idol_a", "coral_idol_b", "coral_idol_c"],
    },
    "leviathan_sigil": {
        "name": "Сигил Левиафана",
        "emoji": "👁️",
        "parts": ["leviathan_sigil_a", "leviathan_sigil_b", "leviathan_sigil_c"],
    },
}

BLACKMARKET_EQUIPMENT_OFFERS: list[dict[str, Any]] = [
    {
        "code": "scuba_basic",
        "name": DIVE_TANKS["scuba_basic"]["name"],
        "emoji": DIVE_TANKS["scuba_basic"]["emoji"],
        "currency": "money",
        "price": DIVE_TANKS["scuba_basic"]["price"],
        "description": DIVE_TANKS["scuba_basic"]["description"],
        "grant": {"type": "equipment_item", "item_code": "scuba_basic"},
    },
    {
        "code": "scuba_reinforced",
        "name": DIVE_TANKS["scuba_reinforced"]["name"],
        "emoji": DIVE_TANKS["scuba_reinforced"]["emoji"],
        "currency": "money",
        "price": DIVE_TANKS["scuba_reinforced"]["price"],
        "description": DIVE_TANKS["scuba_reinforced"]["description"],
        "grant": {"type": "equipment_item", "item_code": "scuba_reinforced"},
    },
    {
        "code": "scuba_titan",
        "name": DIVE_TANKS["scuba_titan"]["name"],
        "emoji": DIVE_TANKS["scuba_titan"]["emoji"],
        "currency": "gems",
        "price": 28,
        "description": DIVE_TANKS["scuba_titan"]["description"],
        "grant": {"type": "equipment_item", "item_code": "scuba_titan"},
    },
    {
        "code": "abyss_lamp",
        "name": DIVE_GEAR["abyss_lamp"]["name"],
        "emoji": DIVE_GEAR["abyss_lamp"]["emoji"],
        "currency": "money",
        "price": DIVE_GEAR["abyss_lamp"]["price"],
        "description": DIVE_GEAR["abyss_lamp"]["description"],
        "grant": {"type": "equipment_item", "item_code": "abyss_lamp"},
    },
    {
        "code": "excavation_kit",
        "name": DIG_TOOLS["excavation_kit"]["name"],
        "emoji": DIG_TOOLS["excavation_kit"]["emoji"],
        "currency": "money",
        "price": DIG_TOOLS["excavation_kit"]["price"],
        "description": DIG_TOOLS["excavation_kit"]["description"],
        "grant": {"type": "equipment_item", "item_code": "excavation_kit"},
    },
    {
        "code": "signal_scanner",
        "name": DIG_TOOLS["signal_scanner"]["name"],
        "emoji": DIG_TOOLS["signal_scanner"]["emoji"],
        "currency": "gems",
        "price": 12,
        "description": DIG_TOOLS["signal_scanner"]["description"],
        "grant": {"type": "equipment_item", "item_code": "signal_scanner"},
    },
]


def get_equipment_definition(item_code: str) -> dict[str, Any] | None:
    if item_code in DIVE_TANKS:
        return {"kind": "dive_tank", **deepcopy(DIVE_TANKS[item_code])}
    if item_code in DIVE_GEAR:
        return {"kind": "dive_gear", **deepcopy(DIVE_GEAR[item_code])}
    if item_code in DIG_TOOLS:
        return {"kind": "dig_tool", **deepcopy(DIG_TOOLS[item_code])}
    return None


def get_antiquary_definition(code: str) -> dict[str, Any] | None:
    item = ANTIQUARY_ITEMS.get(str(code))
    return deepcopy(item) if isinstance(item, dict) else None


def antiquary_codes() -> list[str]:
    return list(ANTIQUARY_ITEMS.keys())


def relic_recipe_output(part_code: str) -> str | None:
    for relic_code, recipe in RELIC_RECIPES.items():
        if str(part_code) in set(recipe.get("parts", [])):
            return relic_code
    return None
