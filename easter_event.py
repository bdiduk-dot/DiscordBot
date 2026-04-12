from __future__ import annotations

import os
import random
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from inventory_system import add_general_item, count_general_items, decrement_general_item, ensure_inventory_state, get_general_items

EASTER_EVENT_KEY = "easter_2026"
EASTER_PHASES = {"off", "active", "exchange"}

_DEFAULT_EVENT_END = "2026-04-12T00:00:00+03:00"
_DEFAULT_EXCHANGE_END = "2026-04-12T00:30:00+03:00"
_PHASE_OVERRIDE = (os.getenv("EASTER_PHASE") or "").strip().lower()

EASTER_EVENT_END_AT_RAW = os.getenv("EASTER_EVENT_END_AT", _DEFAULT_EVENT_END)
EASTER_EXCHANGE_END_AT_RAW = os.getenv("EASTER_EXCHANGE_END_AT", _DEFAULT_EXCHANGE_END)

EASTER_POND_ZONE_KEY = "easter_rabbit_pond"
EASTER_POND_PASS_CODE = "easter_pond_pass"
EASTER_CHEST_CODE = "easter_chest"
EASTER_TALISMAN_CODE = "easter_talisman"
EASTER_COMMON_EGG_CODE = "easter_egg_common"
EASTER_PAINTED_EGG_CODE = "easter_egg_painted"
EASTER_GOLD_EGG_CODE = "easter_egg_gold"
EASTER_ARCHIVE_CATEGORY = "Архив 2026"

EASTER_INACTIVE_CODES = {
    EASTER_COMMON_EGG_CODE,
    EASTER_PAINTED_EGG_CODE,
    EASTER_GOLD_EGG_CODE,
    EASTER_CHEST_CODE,
    EASTER_POND_PASS_CODE,
    "easter_bait_festive",
}
EASTER_DECOR_TROPHY_PREFIX = "easter_decor_"

EASTER_REWARD_ITEMS = {
    EASTER_COMMON_EGG_CODE: {
        "item_type": "event_currency",
        "name": "Обычное яйцо",
        "emoji": "🥚",
        "description": "Главная валюта пасхального ивента 2026.",
        "stackable": True,
    },
    EASTER_PAINTED_EGG_CODE: {
        "item_type": "event_currency",
        "name": "Расписное яйцо",
        "emoji": "🎨",
        "description": "Редкая пасхальная валюта для дорогих наград.",
        "stackable": True,
    },
    EASTER_GOLD_EGG_CODE: {
        "item_type": "event_currency",
        "name": "Золотое яйцо",
        "emoji": "✨",
        "description": "Ультраредкая пасхальная валюта для самых жирных наград.",
        "stackable": True,
    },
    EASTER_CHEST_CODE: {
        "item_type": "event_chest",
        "name": "Пасхальный сундук",
        "emoji": "📦",
        "description": "Редкий пасхальный сундук с валютой, деньгами и декором.",
        "stackable": True,
    },
    EASTER_TALISMAN_CODE: {
        "item_type": "event_collectible",
        "name": "Кроличий талисман",
        "emoji": "🐇",
        "description": "Редкий предмет для закрытия Пасхальной коллекции.",
        "stackable": True,
    },
    "easter_bait_festive": {
        "item_type": "bait_bundle",
        "name": "Праздничная наживка",
        "emoji": "🪱",
        "description": "Праздничный набор наживки для пасхального пруда.",
        "stackable": True,
    },
    EASTER_POND_PASS_CODE: {
        "item_type": "event_pass",
        "name": "Пропуск на Пруд золотого кролика",
        "emoji": "🎟️",
        "description": "Разовый пропуск, который открывает пасхальный пруд навсегда на время ивента.",
        "stackable": True,
    },
}

EASTER_COLLECTION_REQUIREMENTS = (
    EASTER_COMMON_EGG_CODE,
    EASTER_PAINTED_EGG_CODE,
    EASTER_GOLD_EGG_CODE,
    EASTER_CHEST_CODE,
    EASTER_TALISMAN_CODE,
)
EASTER_COLLECTION_TURNIN_CODES = {
    EASTER_COMMON_EGG_CODE,
    EASTER_PAINTED_EGG_CODE,
    EASTER_GOLD_EGG_CODE,
}
EASTER_COLLECTION_HISTORY_CODES = {
    EASTER_CHEST_CODE,
    EASTER_TALISMAN_CODE,
}

EASTER_CHAPTER2_STEPS: tuple[dict[str, Any], ...] = (
    {"id": "earn_common", "name": "Заработать 20 обычных яиц", "target": 20},
    {"id": "pond_catch", "name": "Поймать 5 рыб в пасхальном пруду", "target": 5},
    {"id": "open_chest", "name": "Открыть 1 пасхальный сундук", "target": 1},
    {"id": "buy_shop_item", "name": "Купить 1 предмет в пасхальном магазине", "target": 1},
    {"id": "exchange_once", "name": "Сделать 1 апгрейд валюты", "target": 1},
    {"id": "rabbit_reward", "name": "Получить награду при активном Золотом кролике", "target": 1},
)

EASTER_SECRET_EGG_CODES = (
    "easter_secret_moon_egg",
    "easter_secret_choco_heart",
    "easter_secret_rabbit_egg",
    "easter_secret_dawn_egg",
    "easter_secret_mirror_egg",
)

EASTER_SERVER_PROGRESS_POINT_VALUES = {
    EASTER_COMMON_EGG_CODE: 1,
    EASTER_PAINTED_EGG_CODE: 25,
    EASTER_GOLD_EGG_CODE: 250,
}

EASTER_SERVER_UNLOCK_SHOP_CODE = "easter_chronicle_title"

EASTER_SECRET_EGG_META: dict[str, dict[str, Any]] = {
    "easter_secret_moon_egg": {
        "name": "Лунное яйцо",
        "emoji": "🌙",
        "description": "Редчайшее пасхальное яйцо, которое можно заметить только в ночной воде.",
        "hint": "Ищи его ночью в пасхальном пруду.",
    },
    "easter_secret_choco_heart": {
        "name": "Шоколадное сердце",
        "emoji": "🍫",
        "description": "Секретная находка, которая иногда прячется внутри пасхального сундука.",
        "hint": "Не всё сладкое лежит в магазине. Иногда оно спрятано в сундуках.",
    },
    "easter_secret_rabbit_egg": {
        "name": "Яйцо кролика",
        "emoji": "🐇",
        "description": "Редкий след Золотого кролика, который остаётся только во время его появления.",
        "hint": "Появляется только пока сервер гонится за Золотым кроликом.",
    },
    "easter_secret_dawn_egg": {
        "name": "Яйцо рассвета",
        "emoji": "🌅",
        "description": "Редкое яйцо, которое удаётся найти только на самом раннем утре.",
        "hint": "Проверь утренние награды, пока город только просыпается.",
    },
    "easter_secret_mirror_egg": {
        "name": "Зеркальное яйцо",
        "emoji": "🪞",
        "description": "Редкая пасхальная находка, которая иногда отражается прямо в обменнике.",
        "hint": "Иногда тайна появляется не в дропе, а в самом обмене валюты.",
    },
}

EASTER_SERVER_PROGRESS_MILESTONES: tuple[dict[str, Any], ...] = (
    {
        "level": 1,
        "points": 2_500,
        "name": "Тёплый след",
        "description": "+5% к шансу выпадения яиц по серверу.",
        "egg_drop_bonus": 0.05,
    },
    {
        "level": 2,
        "points": 7_500,
        "name": "Сундук следопыта",
        "description": "+3% к шансу пасхального сундука по серверу.",
        "chest_bonus": 0.03,
    },
    {
        "level": 3,
        "points": 15_000,
        "name": "Тайная витрина",
        "description": "Открывает дополнительный товар во вкладке пасхального магазина.",
        "unlock_shop_item": EASTER_SERVER_UNLOCK_SHOP_CODE,
    },
    {
        "level": 4,
        "points": 30_000,
        "name": "Весенний размах",
        "description": "+10% к деньгам с пасхальных бизнесов и +10% к цене рыбы в пасхальном пруду.",
        "business_money_bonus": 0.10,
        "pond_value_bonus": 0.10,
    },
)

EASTER_FURNITURE_BUFFS = {
    "easter_egg_basket": {
        "name": "Корзина с яйцами",
        "emoji": "🧺",
        "description": "Увеличивает шанс выпадения пасхальных яиц.",
        "price_common": 45,
        "price_painted": 0,
        "price_gold": 0,
        "egg_drop_bonus": 0.05,
    },
    "easter_rabbit_lamp": {
        "name": "Кроличья лампа",
        "emoji": "🐰",
        "description": "Даёт бонус к доходу пасхальных бизнесов.",
        "price_common": 95,
        "price_painted": 1,
        "price_gold": 0,
        "business_bonus": 0.05,
    },
    "easter_chocolate_fountain": {
        "name": "Шоколадный фонтан",
        "emoji": "🍫",
        "description": "Даёт бонус к награде /work во время ивента.",
        "price_common": 80,
        "price_painted": 1,
        "price_gold": 0,
        "work_bonus": 0.05,
    },
}

EASTER_SHOP_CATEGORY_META = {
    "loot": {"label": "Лут и расходники", "emoji": "🎁", "hint": "Кейсы, наживка и пропуск на пасхальный пруд."},
    "profile": {"label": "Профиль и титулы", "emoji": "🎨", "hint": "Косметика профиля и пасхальные статусные награды."},
    "decor": {"label": "Мебель и баффы", "emoji": "🛋️", "hint": "Домашний декор с пассивными пасхальными бонусами."},
    "business": {"label": "Бизнесы", "emoji": "🏪", "hint": "Временные бизнесы с яйцами и дополнительным доходом."},
}

EASTER_TEMP_BUSINESSES = {
    "easter_bakery": {
        "name": "Пасхальная лавка",
        "emoji": "🏪",
        "money_price": 150_000,
        "common_price": 140,
        "painted_price": 3,
        "gold_price": 0,
        "income_money": 28_000,
        "income_common": (10, 16),
        "painted_chance": 0.14,
        "cycle_hours": 6,
        "trophy_code": "easter_trophy_bakery",
    },
    "easter_chocolate_lab": {
        "name": "Шоколадная мастерская",
        "emoji": "🍫",
        "money_price": 325_000,
        "common_price": 240,
        "painted_price": 6,
        "gold_price": 1,
        "income_money": 55_000,
        "income_common": (16, 24),
        "painted_chance": 0.22,
        "cycle_hours": 8,
        "trophy_code": "easter_trophy_chocolate_lab",
    },
}

EASTER_SHOP_ITEMS: list[dict[str, Any]] = [
    {"code": "easter_case_basic", "name": "Пасхальный кейс", "emoji": "🎁", "kind": "case", "price_common": 30, "price_painted": 0, "price_gold": 0},
    {"code": "easter_bait_pack", "name": "Праздничная наживка", "emoji": "🪱", "kind": "bait", "price_common": 12, "price_painted": 0, "price_gold": 0},
    {"code": EASTER_POND_PASS_CODE, "name": "Пропуск на Пруд золотого кролика", "emoji": "🎟️", "kind": "pass", "price_common": 60, "price_painted": 1, "price_gold": 0},
    {"code": "easter_profile_theme", "name": "Mint Bunny", "emoji": "🌿", "kind": "theme", "price_common": 50, "price_painted": 2, "price_gold": 0, "theme_key": "mint_bunny"},
    {"code": "easter_profile_title", "name": "Пасхальный титул", "emoji": "👑", "kind": "title", "price_common": 0, "price_painted": 3, "price_gold": 0, "title_key": "easter_hunter"},
    {"code": EASTER_SERVER_UNLOCK_SHOP_CODE, "name": "Летописец весны", "emoji": "📜", "kind": "title", "price_common": 90, "price_painted": 2, "price_gold": 1, "title_key": "spring_chronicler", "locked_until_level": 3},
    {"code": "easter_egg_basket", "name": "Корзина с яйцами", "emoji": "🧺", "kind": "furniture", "price_common": 45, "price_painted": 0, "price_gold": 0},
    {"code": "easter_rabbit_lamp", "name": "Кроличья лампа", "emoji": "🐰", "kind": "furniture", "price_common": 95, "price_painted": 1, "price_gold": 0},
    {"code": "easter_chocolate_fountain", "name": "Шоколадный фонтан", "emoji": "🍫", "kind": "furniture", "price_common": 80, "price_painted": 1, "price_gold": 0},
    {"code": "easter_bakery", "name": "Пасхальная лавка", "emoji": "🏪", "kind": "business", "price_common": 140, "price_painted": 3, "price_gold": 0, "money_price": 150_000},
    {"code": "easter_chocolate_lab", "name": "Шоколадная мастерская", "emoji": "🍫", "kind": "business", "price_common": 240, "price_painted": 6, "price_gold": 1, "money_price": 325_000},
]

EASTER_FISH_SPECIES = [
    {"id": "easter_confetti_bleak", "name": "Конфетти-уклейка", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day"], "min_weight_kg": 0.12, "max_weight_kg": 0.58, "price_mult": 0.94},
    {"id": "easter_pastel_roach", "name": "Пастельная плотва", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening"], "min_weight_kg": 0.24, "max_weight_kg": 1.18, "price_mult": 0.97},
    {"id": "easter_marshmallow_minnow", "name": "Зефирная верховка", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "evening"], "min_weight_kg": 0.10, "max_weight_kg": 0.82, "price_mult": 0.99},
    {"id": "easter_sugar_dace", "name": "Сахарная ельца", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day"], "min_weight_kg": 0.18, "max_weight_kg": 0.94, "price_mult": 1.01},
    {"id": "easter_cotton_ruffe", "name": "Ватный ёрш", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening", "night"], "min_weight_kg": 0.16, "max_weight_kg": 0.88, "price_mult": 1.02},
    {"id": "easter_pearl_gudgeon", "name": "Жемчужный пескарь", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "night"], "min_weight_kg": 0.14, "max_weight_kg": 0.76, "price_mult": 1.00},
    {"id": "easter_candy_sprat", "name": "Конфетная килька", "emoji": "🐟", "rarity": "common", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening", "night"], "min_weight_kg": 0.11, "max_weight_kg": 0.69, "price_mult": 1.03},
    {"id": "easter_ribbon_carp", "name": "Ленточный карп", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening"], "min_weight_kg": 0.75, "max_weight_kg": 3.30, "price_mult": 1.06},
    {"id": "easter_mint_crucian", "name": "Мятный карасик", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day"], "min_weight_kg": 0.62, "max_weight_kg": 2.75, "price_mult": 1.08},
    {"id": "easter_jelly_perch", "name": "Желейный окунь", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 0.85, "max_weight_kg": 3.10, "price_mult": 1.10},
    {"id": "easter_toffee_ide", "name": "Ирисовый язь", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening"], "min_weight_kg": 0.92, "max_weight_kg": 3.44, "price_mult": 1.12},
    {"id": "easter_speckled_tench", "name": "Крапчатый линь-леденец", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 0.96, "max_weight_kg": 3.56, "price_mult": 1.13},
    {"id": "easter_blossom_bream", "name": "Цветочный лещ", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "evening"], "min_weight_kg": 0.88, "max_weight_kg": 3.24, "price_mult": 1.09},
    {"id": "easter_macaron_bluefish", "name": "Макароновый синец", "emoji": "🐠", "rarity": "uncommon", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "night"], "min_weight_kg": 0.80, "max_weight_kg": 3.02, "price_mult": 1.11},
    {"id": "easter_carrot_koi", "name": "Морковный кои", "emoji": "🐟", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "evening"], "min_weight_kg": 1.0, "max_weight_kg": 4.2, "price_mult": 1.22},
    {"id": "easter_lilac_zander", "name": "Сиреневый судак", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening", "night"], "min_weight_kg": 1.70, "max_weight_kg": 5.60, "price_mult": 1.27},
    {"id": "easter_cream_pike", "name": "Сливочная щука", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 1.95, "max_weight_kg": 6.40, "price_mult": 1.30},
    {"id": "easter_berry_catfish", "name": "Ягодный сом", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 2.10, "max_weight_kg": 6.90, "price_mult": 1.31},
    {"id": "easter_lavender_mullet", "name": "Лавандовая кефаль", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening"], "min_weight_kg": 1.84, "max_weight_kg": 5.74, "price_mult": 1.29},
    {"id": "easter_honey_gar", "name": "Медовый гар", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "night"], "min_weight_kg": 2.30, "max_weight_kg": 7.20, "price_mult": 1.33},
    {"id": "easter_citrus_chub", "name": "Цитрусовый голавль", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "evening"], "min_weight_kg": 1.60, "max_weight_kg": 5.48, "price_mult": 1.28},
    {"id": "easter_rose_sterlet", "name": "Розовая стерлядь", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "night"], "min_weight_kg": 2.20, "max_weight_kg": 6.80, "price_mult": 1.32},
    {"id": "easter_velvet_salmon", "name": "Бархатный лосось", "emoji": "🐡", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 2.40, "max_weight_kg": 7.40, "price_mult": 1.35},
    {"id": "easter_choco_trout", "name": "Шоколадная форель", "emoji": "🐠", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening"], "min_weight_kg": 2.8, "max_weight_kg": 8.5, "price_mult": 1.34},
    {"id": "easter_caramel_sturgeon", "name": "Карамельный осётр", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening", "night"], "min_weight_kg": 4.40, "max_weight_kg": 13.80, "price_mult": 1.39},
    {"id": "easter_marzipan_ray", "name": "Марципановый скат", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 4.90, "max_weight_kg": 12.60, "price_mult": 1.41},
    {"id": "easter_glazed_eel", "name": "Глазурный угорь", "emoji": "🦑", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 3.60, "max_weight_kg": 11.20, "price_mult": 1.43},
    {"id": "easter_fudge_barracuda", "name": "Помадная барракуда", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening", "night"], "min_weight_kg": 4.80, "max_weight_kg": 14.20, "price_mult": 1.45},
    {"id": "easter_icing_sawfish", "name": "Айсинг-пила", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["night"], "min_weight_kg": 5.20, "max_weight_kg": 15.60, "price_mult": 1.47},
    {"id": "easter_praline_moray", "name": "Пралиновая мурена", "emoji": "🦑", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 4.10, "max_weight_kg": 12.80, "price_mult": 1.46},
    {"id": "easter_ginger_krakenling", "name": "Имбирный кракеныш", "emoji": "🦑", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "evening", "night"], "min_weight_kg": 4.60, "max_weight_kg": 13.90, "price_mult": 1.48},
    {"id": "easter_truffle_taimen", "name": "Трюфельный таймень", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "evening"], "min_weight_kg": 5.10, "max_weight_kg": 14.80, "price_mult": 1.44},
    {"id": "easter_satin_beluga", "name": "Атласная белуга", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "night"], "min_weight_kg": 5.40, "max_weight_kg": 16.40, "price_mult": 1.49},
    {"id": "easter_custard_arapaima", "name": "Заварная арапайма", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 5.80, "max_weight_kg": 17.20, "price_mult": 1.50},
    {"id": "easter_creme_marlin", "name": "Крем-брюле марлин", "emoji": "🦈", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "night"], "min_weight_kg": 5.60, "max_weight_kg": 16.80, "price_mult": 1.51},
    {"id": "easter_golden_harefin", "name": "Золотой кролик-плавник", "emoji": "🐣", "rarity": "legendary", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 5.5, "max_weight_kg": 15.0, "price_mult": 1.50},
    {"id": "easter_crown_carp", "name": "Королевский пасхальный карп", "emoji": "👑", "rarity": "legendary", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening", "night"], "min_weight_kg": 7.80, "max_weight_kg": 22.50, "price_mult": 1.56},
    {"id": "easter_prism_angler", "name": "Призматический фонарник", "emoji": "💠", "rarity": "legendary", "zones": [EASTER_POND_ZONE_KEY], "phases": ["night"], "min_weight_kg": 8.40, "max_weight_kg": 24.60, "price_mult": 1.59},
    {"id": "easter_sunrise_leviathan", "name": "Рассветный левиафан", "emoji": "🌅", "rarity": "legendary", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "night"], "min_weight_kg": 10.50, "max_weight_kg": 30.00, "price_mult": 1.62},
    {"id": "easter_aurora_manta", "name": "Аврора-манта", "emoji": "🪽", "rarity": "legendary", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 9.60, "max_weight_kg": 27.40, "price_mult": 1.64},
]


def _parse_dt(raw_value: str) -> datetime:
    parsed = datetime.fromisoformat(str(raw_value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


EASTER_EVENT_END_AT = _parse_dt(EASTER_EVENT_END_AT_RAW)
EASTER_EXCHANGE_END_AT = _parse_dt(EASTER_EXCHANGE_END_AT_RAW)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_easter_phase(now: datetime | None = None) -> str:
    if _PHASE_OVERRIDE in EASTER_PHASES:
        return _PHASE_OVERRIDE
    current = now or utc_now()
    if current < EASTER_EVENT_END_AT:
        return "active"
    if current < EASTER_EXCHANGE_END_AT:
        return "exchange"
    return "off"


def easter_is_active(now: datetime | None = None) -> bool:
    return get_easter_phase(now) == "active"


def easter_exchange_active(now: datetime | None = None) -> bool:
    return get_easter_phase(now) == "exchange"


def rabbit_is_active(guild_state: dict[str, Any] | None, now: datetime | None = None) -> bool:
    current = now or utc_now()
    if not isinstance(guild_state, dict):
        return False
    raw_until = guild_state.get("rabbit_active_until")
    if not raw_until:
        return False
    try:
        active_until = _parse_dt(str(raw_until))
    except ValueError:
        return False
    return active_until > current


def _ensure_systems_state(user: dict[str, Any]) -> dict[str, Any]:
    game_stats = user.get("game_stats")
    if not isinstance(game_stats, dict):
        game_stats = {}
        user["game_stats"] = game_stats
    systems = game_stats.get("_systems")
    if not isinstance(systems, dict):
        systems = {}
        game_stats["_systems"] = systems
    return systems


def ensure_easter_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _ensure_systems_state(user)
    state = systems.get(EASTER_EVENT_KEY)
    if not isinstance(state, dict):
        state = {}
        systems[EASTER_EVENT_KEY] = state
    state.setdefault("collection_reward_claimed", False)
    state.setdefault("eggs_found_common", 0)
    state.setdefault("eggs_found_painted", 0)
    state.setdefault("eggs_found_gold", 0)
    state.setdefault("rabbit_pond_catches", 0)
    collection_found_codes = state.get("collection_found_codes")
    if not isinstance(collection_found_codes, list):
        collection_found_codes = []
        state["collection_found_codes"] = collection_found_codes
    businesses = state.get("businesses")
    if not isinstance(businesses, dict):
        businesses = {}
        state["businesses"] = businesses
    owned_furniture = state.get("owned_furniture")
    if not isinstance(owned_furniture, list):
        owned_furniture = []
        state["owned_furniture"] = owned_furniture
    chapter2_progress = state.get("chapter2_progress")
    if not isinstance(chapter2_progress, dict):
        chapter2_progress = {}
        state["chapter2_progress"] = chapter2_progress
    for step in EASTER_CHAPTER2_STEPS:
        chapter2_progress.setdefault(str(step["id"]), 0)
    state.setdefault("chapter2_completed", False)
    state.setdefault("chapter2_reward_claimed", False)
    secret_found_codes = state.get("secret_found_codes")
    if not isinstance(secret_found_codes, list):
        secret_found_codes = []
        state["secret_found_codes"] = secret_found_codes
    state["secret_found_codes"] = [
        str(code)
        for code in secret_found_codes
        if str(code) in EASTER_SECRET_EGG_META
    ]
    state.setdefault("secret_collection_reward_claimed", False)
    state.setdefault("final_reward_claimed", False)
    return state


def _time_phase_key(now: datetime | None = None) -> str:
    current = (now or utc_now()).astimezone(timezone.utc)
    hour = int(current.hour)
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "day"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def get_server_progress_state(guild_state: dict[str, Any] | None) -> dict[str, Any]:
    raw_state = guild_state if isinstance(guild_state, dict) else {}
    points = max(0, int(raw_state.get("server_progress_points", 0) or 0))
    unlocked_raw = raw_state.get("server_progress_unlocked")
    if not isinstance(unlocked_raw, list):
        unlocked_raw = []
    unlocked_levels = {
        int(level)
        for level in unlocked_raw
        if str(level).isdigit()
    }
    for milestone in EASTER_SERVER_PROGRESS_MILESTONES:
        if points >= int(milestone["points"]):
            unlocked_levels.add(int(milestone["level"]))
    level = max(unlocked_levels, default=0)
    next_milestone = next(
        (milestone for milestone in EASTER_SERVER_PROGRESS_MILESTONES if int(milestone["level"]) not in unlocked_levels),
        None,
    )
    return {
        "points": points,
        "level": level,
        "unlocked_levels": sorted(unlocked_levels),
        "next_milestone": next_milestone,
    }


def get_server_progress_bonuses(guild_state: dict[str, Any] | None) -> dict[str, Any]:
    state = get_server_progress_state(guild_state)
    bonuses = {
        "egg_drop_bonus": 0.0,
        "chest_bonus": 0.0,
        "business_money_bonus": 0.0,
        "pond_value_bonus": 0.0,
        "unlocked_shop_codes": set(),
    }
    for milestone in EASTER_SERVER_PROGRESS_MILESTONES:
        if int(milestone["level"]) not in state["unlocked_levels"]:
            continue
        bonuses["egg_drop_bonus"] += float(milestone.get("egg_drop_bonus", 0.0) or 0.0)
        bonuses["chest_bonus"] += float(milestone.get("chest_bonus", 0.0) or 0.0)
        bonuses["business_money_bonus"] += float(milestone.get("business_money_bonus", 0.0) or 0.0)
        bonuses["pond_value_bonus"] += float(milestone.get("pond_value_bonus", 0.0) or 0.0)
        unlock_code = str(milestone.get("unlock_shop_item") or "").strip()
        if unlock_code:
            bonuses["unlocked_shop_codes"].add(unlock_code)
    return bonuses


def easter_shop_item_visible(item: dict[str, Any], guild_state: dict[str, Any] | None = None) -> bool:
    locked_until_level = int(item.get("locked_until_level", 0) or 0)
    if locked_until_level <= 0:
        return True
    state = get_server_progress_state(guild_state)
    return int(state["level"]) >= locked_until_level


def get_visible_easter_shop_items(guild_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [item for item in EASTER_SHOP_ITEMS if easter_shop_item_visible(item, guild_state)]


def _server_points_from_reward_counts(common: int = 0, painted: int = 0, gold: int = 0) -> int:
    return (
        int(common or 0) * int(EASTER_SERVER_PROGRESS_POINT_VALUES[EASTER_COMMON_EGG_CODE])
        + int(painted or 0) * int(EASTER_SERVER_PROGRESS_POINT_VALUES[EASTER_PAINTED_EGG_CODE])
        + int(gold or 0) * int(EASTER_SERVER_PROGRESS_POINT_VALUES[EASTER_GOLD_EGG_CODE])
    )


def _empty_easter_reward_payload() -> dict[str, Any]:
    return {
        "lines": [],
        "common": 0,
        "painted": 0,
        "gold": 0,
        "chests": 0,
        "server_points": 0,
    }


def get_chapter2_current_step(user: dict[str, Any]) -> dict[str, Any] | None:
    state = ensure_easter_state(user)
    progress = state.get("chapter2_progress", {})
    for index, step in enumerate(EASTER_CHAPTER2_STEPS):
        current_value = int(progress.get(str(step["id"]), 0) or 0)
        if current_value < int(step["target"]):
            return {
                "index": index,
                "step": step,
                "progress": current_value,
                "target": int(step["target"]),
            }
    state["chapter2_completed"] = True
    return None


def advance_chapter2_progress(user: dict[str, Any], step_id: str, amount: int = 1) -> dict[str, Any]:
    state = ensure_easter_state(user)
    progress = state["chapter2_progress"]
    current = get_chapter2_current_step(user)
    if current is None:
        state["chapter2_completed"] = True
        return {"advanced": False, "step_completed": False, "chapter_completed": False}
    if str(current["step"]["id"]) != str(step_id):
        return {"advanced": False, "step_completed": False, "chapter_completed": False}
    target = int(current["target"])
    before = int(progress.get(step_id, 0) or 0)
    after = min(target, before + max(1, int(amount or 1)))
    progress[step_id] = after
    step_completed = before < target and after >= target
    next_step = get_chapter2_current_step(user)
    chapter_completed = step_completed and next_step is None
    if chapter_completed:
        state["chapter2_completed"] = True
    return {
        "advanced": after != before,
        "step_completed": step_completed,
        "chapter_completed": chapter_completed,
        "progress": after,
        "target": target,
    }


def chapter2_reward_can_claim(user: dict[str, Any]) -> bool:
    state = ensure_easter_state(user)
    return bool(state.get("chapter2_completed")) and not bool(state.get("chapter2_reward_claimed"))


def claim_chapter2_reward(user: dict[str, Any]) -> bool:
    if not chapter2_reward_can_claim(user):
        return False
    state = ensure_easter_state(user)
    user["gems"] = int(user.get("gems", 0) or 0) + 50
    add_easter_trophy(
        user,
        "easter_rabbit_trail_map",
        "Карта кроличьих следов",
        "Памятная карта за полное прохождение второй главы пасхального ивента 2026.",
    )
    state["chapter2_reward_claimed"] = True
    return True


def secret_hints_unlocked(user: dict[str, Any]) -> bool:
    state = ensure_easter_state(user)
    return bool(state.get("chapter2_reward_claimed"))


def _register_secret_egg(user: dict[str, Any], code: str) -> bool:
    if code not in EASTER_SECRET_EGG_META:
        return False
    state = ensure_easter_state(user)
    found_codes = set(str(entry) for entry in state.get("secret_found_codes", []))
    if code in found_codes:
        return False
    state["secret_found_codes"].append(code)
    return True


def get_secret_collection_progress(user: dict[str, Any]) -> dict[str, bool]:
    state = ensure_easter_state(user)
    found_codes = set(str(entry) for entry in state.get("secret_found_codes", []))
    return {code: code in found_codes for code in EASTER_SECRET_EGG_CODES}


def secret_collection_can_claim(user: dict[str, Any], now: datetime | None = None) -> bool:
    phase = get_easter_phase(now)
    state = ensure_easter_state(user)
    return (
        phase in {"active", "exchange"}
        and not bool(state.get("secret_collection_reward_claimed"))
        and all(get_secret_collection_progress(user).values())
    )


def claim_secret_collection(user: dict[str, Any]) -> bool:
    if not secret_collection_can_claim(user):
        return False
    from progression import unlock_theme, unlock_title

    state = ensure_easter_state(user)
    unlock_title(user, "easter_secret_keeper")
    unlock_theme(user, "moon_hare")
    add_easter_trophy(
        user,
        "easter_secret_collection_trophy",
        "Запечатанное яйцо 2026",
        "Секретный трофей за полную hidden-коллекцию пасхальных яиц 2026.",
    )
    state["secret_collection_reward_claimed"] = True
    return True


def final_easter_reward_can_claim(user: dict[str, Any], guild_state: dict[str, Any] | None) -> bool:
    state = ensure_easter_state(user)
    server_state = get_server_progress_state(guild_state)
    return (
        bool(state.get("collection_reward_claimed"))
        and bool(state.get("chapter2_reward_claimed"))
        and bool(state.get("secret_collection_reward_claimed"))
        and not bool(state.get("final_reward_claimed"))
        and int(server_state["level"]) >= len(EASTER_SERVER_PROGRESS_MILESTONES)
    )


def claim_final_easter_reward(user: dict[str, Any], guild_state: dict[str, Any] | None) -> bool:
    if not final_easter_reward_can_claim(user, guild_state):
        return False
    from progression import unlock_title

    state = ensure_easter_state(user)
    unlock_title(user, "spring_archivist")
    user["gems"] = int(user.get("gems", 0) or 0) + 200
    add_easter_trophy(
        user,
        "easter_rabbit_relic",
        "Реликвия Золотого кролика",
        "Финальная скрытая реликвия за 100% прохождение пасхального ивента 2026.",
    )
    state["final_reward_claimed"] = True
    return True


def _maybe_grant_secret_egg(user: dict[str, Any], code: str, chance: float) -> list[str]:
    if chance <= 0 or random.random() > chance:
        return []
    if not _register_secret_egg(user, code):
        return []
    meta = EASTER_SECRET_EGG_META[code]
    return [f"{meta['emoji']} Тайная находка: **{meta['name']}** добавлена в `/eggcollection`."]


def _ensure_fishing_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _ensure_systems_state(user)
    fishing = systems.get("fishing")
    if not isinstance(fishing, dict):
        fishing = {}
        systems["fishing"] = fishing
    fishing.setdefault("unlocked_zones", ["river_bank"])
    fishing.setdefault("selected_zone", "river_bank")
    return fishing


def _count_code(user: dict[str, Any], code: str) -> int:
    return count_general_items(user, code=code)


def get_easter_counts(user: dict[str, Any]) -> dict[str, int]:
    return {
        "common": _count_code(user, EASTER_COMMON_EGG_CODE),
        "painted": _count_code(user, EASTER_PAINTED_EGG_CODE),
        "gold": _count_code(user, EASTER_GOLD_EGG_CODE),
    }


def _event_payload(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"event_key": EASTER_EVENT_KEY}
    if isinstance(extra, dict):
        payload.update(deepcopy(extra))
    return payload


def add_easter_item(user: dict[str, Any], code: str, quantity: int = 1, *, payload: dict[str, Any] | None = None) -> None:
    definition = EASTER_REWARD_ITEMS[code]
    add_general_item(
        user,
        item_type=str(definition["item_type"]),
        code=code,
        name=str(definition["name"]),
        emoji=str(definition["emoji"]),
        description=str(definition["description"]),
        quantity=max(1, int(quantity)),
        payload=_event_payload(payload),
        stackable=bool(definition["stackable"]),
    )
    if quantity > 0 and code in EASTER_COLLECTION_HISTORY_CODES:
        state = ensure_easter_state(user)
        found_codes = set(str(entry) for entry in state.get("collection_found_codes", []))
        if code not in found_codes:
            state["collection_found_codes"].append(code)


def add_easter_trophy(user: dict[str, Any], code: str, name: str, description: str) -> None:
    add_general_item(
        user,
        item_type="event_trophy",
        code=code,
        name=name,
        emoji="🏆",
        description=description,
        quantity=1,
        payload=_event_payload({"archive": False}),
        stackable=False,
    )

def migrate_legacy_easter_decor_inventory(user: dict[str, Any]) -> list[str]:
    inventory = ensure_inventory_state(user)
    easter_state = ensure_easter_state(user)
    owned_furniture = set(str(item) for item in easter_state.get("owned_furniture", []))
    kept_items: list[dict[str, Any]] = []
    migrated: list[str] = []
    changed = False

    for item in inventory.get("general_items", []):
        if not isinstance(item, dict):
            continue

        item_type = str(item.get("item_type") or "")
        code = str(item.get("code") or "")
        if item_type != "event_trophy" or not code.startswith(EASTER_DECOR_TROPHY_PREFIX):
            kept_items.append(item)
            continue

        furniture_code = code.removeprefix(EASTER_DECOR_TROPHY_PREFIX)
        furniture = EASTER_FURNITURE_BUFFS.get(furniture_code)
        if furniture is None:
            kept_items.append(item)
            continue

        if furniture_code not in owned_furniture:
            easter_state["owned_furniture"].append(furniture_code)
            owned_furniture.add(furniture_code)
            migrated.append(str(furniture["name"]))
        changed = True

    if changed:
        inventory["general_items"] = kept_items
    return migrated


def get_owned_easter_furniture(user: dict[str, Any]) -> list[dict[str, Any]]:
    easter_state = ensure_easter_state(user)
    owned_codes: set[str] = set()
    owned_items: list[dict[str, Any]] = []
    for raw_code in easter_state.get("owned_furniture", []):
        code = str(raw_code)
        furniture = EASTER_FURNITURE_BUFFS.get(code)
        if furniture is None or code in owned_codes:
            continue
        owned_codes.add(code)
        owned_items.append({"code": code, **deepcopy(furniture)})
    return owned_items


def has_easter_furniture(user: dict[str, Any], code: str) -> bool:
    easter_state = ensure_easter_state(user)
    return code in set(str(item) for item in easter_state.get("owned_furniture", []))


def _egg_drop_bonus_chance(user: dict[str, Any]) -> float:
    if not has_easter_furniture(user, "easter_egg_basket"):
        return 0.0
    furniture = EASTER_FURNITURE_BUFFS.get("easter_egg_basket", {})
    return max(0.0, float(furniture.get("egg_drop_bonus", 0.0) or 0.0))


def _work_money_bonus_multiplier(user: dict[str, Any]) -> float:
    return 1.05 if has_easter_furniture(user, "easter_chocolate_fountain") else 1.0


def _event_business_money_bonus(user: dict[str, Any]) -> float:
    return 1.05 if has_easter_furniture(user, "easter_rabbit_lamp") else 1.0


def maybe_apply_easter_work_bonus(user: dict[str, Any], amount: int) -> int:
    if not easter_is_active():
        return int(amount)
    return int(round(int(amount) * _work_money_bonus_multiplier(user)))


def _increment_counter(user: dict[str, Any], code: str, quantity: int) -> None:
    if quantity <= 0:
        return
    state = ensure_easter_state(user)
    if code == EASTER_COMMON_EGG_CODE:
        state["eggs_found_common"] = int(state.get("eggs_found_common", 0) or 0) + quantity
    elif code == EASTER_PAINTED_EGG_CODE:
        state["eggs_found_painted"] = int(state.get("eggs_found_painted", 0) or 0) + quantity
    elif code == EASTER_GOLD_EGG_CODE:
        state["eggs_found_gold"] = int(state.get("eggs_found_gold", 0) or 0) + quantity


def _roll_range_with_bonus(base_min: int, base_max: int, multiplier: float) -> int:
    value = random.randint(int(base_min), int(base_max))
    return max(1, int(round(value * multiplier)))


def _grant_code(user: dict[str, Any], code: str, quantity: int) -> None:
    if quantity <= 0:
        return
    add_easter_item(user, code, quantity)
    _increment_counter(user, code, quantity)


def grant_easter_drops(
    user: dict[str, Any],
    source: str,
    *,
    guild_state: dict[str, Any] | None = None,
    natural_blackjack: bool = False,
) -> list[str]:
    now = utc_now()
    if get_easter_phase(now) != "active":
        return []

    rabbit_active = rabbit_is_active(guild_state, now)
    egg_drop_bonus = _egg_drop_bonus_chance(user)
    lines: list[str] = []
    common_count = 0
    painted_count = 0
    gold_count = 0
    chest_count = 0

    common_drop_chances = {
        "work": 0.55,
        "crime": 0.70,
        "slut": 0.50,
        "fish": 0.60,
        "daily": 1.00,
        "blackjack_win": 0.65,
        "business_collect": 0.55,
        "rent_collect": 0.60,
    }
    common_drop_ranges = {
        "work": (1, 3),
        "crime": (2, 5),
        "slut": (1, 4),
        "fish": (1, 4),
        "daily": (5, 5),
        "blackjack_win": (2, 4),
        "business_collect": (1, 3),
        "rent_collect": (2, 4),
    }

    drop_chance = min(1.0, common_drop_chances.get(source, 0.0) + egg_drop_bonus)
    if source in common_drop_ranges and random.random() <= drop_chance:
        low, high = common_drop_ranges[source]
        common_count += random.randint(low, high)

    if source == "crime" and random.random() <= 0.05:
        painted_count += 1
    elif source == "slut" and random.random() <= 0.03:
        painted_count += 1
    elif source == "fish" and random.random() <= 0.06:
        painted_count += 1
    elif source == "blackjack_win" and natural_blackjack and random.random() <= 0.12:
        painted_count += 1

    if rabbit_active:
        rabbit_common_chance = min(1.0, 0.65 + egg_drop_bonus)
        if random.random() <= rabbit_common_chance:
            common_count += random.randint(1, 3)
        if random.random() <= 0.18:
            painted_count += 1
        if random.random() <= 0.03:
            gold_count += 1
        if random.random() <= 0.08:
            chest_count += 1

    if common_count > 0:
        _grant_code(user, EASTER_COMMON_EGG_CODE, common_count)
        lines.append(f"🥚 Пасха: **+{common_count}** обычн. яйц.")
    if painted_count > 0:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, painted_count)
        lines.append(f"🎨 Пасха: **+{painted_count}** расписн. яйц.")
    if gold_count > 0:
        _grant_code(user, EASTER_GOLD_EGG_CODE, gold_count)
        lines.append(f"✨ Пасха: **+{gold_count}** золот. яйц.")
    if chest_count > 0:
        add_easter_item(user, EASTER_CHEST_CODE, chest_count)
        lines.append(f"📦 Пасха: **+{chest_count}** сундук(а) добавлено в инвентарь.")
    return lines

def grant_pond_bonus_loot(user: dict[str, Any], *, guild_state: dict[str, Any] | None = None) -> list[str]:
    if get_easter_phase() != "active":
        return []
    rabbit_active = rabbit_is_active(guild_state)
    lines: list[str] = []
    common = random.randint(2, 5)
    painted = 1 if random.random() <= 0.14 else 0
    gold = 1 if rabbit_active and random.random() <= 0.08 else 0
    chests = 1 if random.random() <= (0.12 if rabbit_active else 0.05) else 0
    _grant_code(user, EASTER_COMMON_EGG_CODE, common)
    lines.append(f"🥚 Пасха: **+{common}** обычн. яйц.")
    if painted:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, painted)
        lines.append("🎨 Пасха: **+1** расписное яйцо.")
    if gold:
        _grant_code(user, EASTER_GOLD_EGG_CODE, gold)
        lines.append("✨ Пасха: **+1** золотое яйцо.")
    if chests:
        add_easter_item(user, EASTER_CHEST_CODE, chests)
        lines.append("📦 Пасха: Пасхальный сундук добавлен в инвентарь.")
        lines.append("📦 Пасха: найден Пасхальный сундук.")
    return lines

def open_easter_chest(user: dict[str, Any]) -> dict[str, Any]:
    rewards = {
        "money": random.randint(12_000, 55_000),
        "gems": random.randint(2, 8),
        "lines": [],
    }
    user["balance"] = int(user.get("balance", 0) or 0) + rewards["money"]
    user["gems"] = int(user.get("gems", 0) or 0) + rewards["gems"]
    rewards["lines"].append(f"💰 Деньги: **+${rewards['money']:,}**")
    rewards["lines"].append(f"💎 Гемы: **+{rewards['gems']}**")

    common = random.randint(1, 4)
    _grant_code(user, EASTER_COMMON_EGG_CODE, common)
    rewards["lines"].append(f"🥚 Обычные яйца: **+{common}**")
    if random.random() <= 0.28:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, 1)
        rewards["lines"].append("🎨 Расписное яйцо: **+1**")
    if random.random() <= 0.05:
        _grant_code(user, EASTER_GOLD_EGG_CODE, 1)
        rewards["lines"].append("✨ Золотое яйцо: **+1**")
    if random.random() <= 0.08:
        add_easter_item(user, EASTER_TALISMAN_CODE, 1)
        rewards["lines"].append("🐇 Кроличий талисман: **+1**")
    return rewards

def grant_easter_drops(
    user: dict[str, Any],
    source: str,
    *,
    guild_state: dict[str, Any] | None = None,
    natural_blackjack: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    if get_easter_phase(now) != "active":
        return _empty_easter_reward_payload()

    rabbit_active = rabbit_is_active(guild_state, now)
    server_bonuses = get_server_progress_bonuses(guild_state)
    egg_drop_bonus = _egg_drop_bonus_chance(user) + float(server_bonuses["egg_drop_bonus"])
    payload = _empty_easter_reward_payload()
    common_count = 0
    painted_count = 0
    gold_count = 0
    chest_count = 0

    common_drop_chances = {
        "work": 0.55,
        "crime": 0.70,
        "slut": 0.50,
        "fish": 0.60,
        "daily": 1.00,
        "blackjack_win": 0.65,
        "business_collect": 0.55,
        "rent_collect": 0.60,
    }
    common_drop_ranges = {
        "work": (1, 3),
        "crime": (2, 5),
        "slut": (1, 4),
        "fish": (1, 4),
        "daily": (5, 5),
        "blackjack_win": (2, 4),
        "business_collect": (1, 3),
        "rent_collect": (2, 4),
    }

    drop_chance = min(1.0, common_drop_chances.get(source, 0.0) + egg_drop_bonus)
    if source in common_drop_ranges and random.random() <= drop_chance:
        low, high = common_drop_ranges[source]
        common_count += random.randint(low, high)

    if source == "crime" and random.random() <= 0.05:
        painted_count += 1
    elif source == "slut" and random.random() <= 0.03:
        painted_count += 1
    elif source == "fish" and random.random() <= 0.06:
        painted_count += 1
    elif source == "blackjack_win" and natural_blackjack and random.random() <= 0.12:
        painted_count += 1

    if rabbit_active:
        rabbit_common_chance = min(1.0, 0.65 + egg_drop_bonus)
        if random.random() <= rabbit_common_chance:
            common_count += random.randint(1, 3)
        if random.random() <= 0.18:
            painted_count += 1
        if random.random() <= 0.03:
            gold_count += 1
        if random.random() <= min(1.0, 0.08 + float(server_bonuses["chest_bonus"])):
            chest_count += 1

    if common_count > 0:
        _grant_code(user, EASTER_COMMON_EGG_CODE, common_count)
        payload["lines"].append(f"🥚 Пасха: **+{common_count}** обычн. яиц.")
    if painted_count > 0:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, painted_count)
        payload["lines"].append(f"🎨 Пасха: **+{painted_count}** расписн. яиц.")
    if gold_count > 0:
        _grant_code(user, EASTER_GOLD_EGG_CODE, gold_count)
        payload["lines"].append(f"✨ Пасха: **+{gold_count}** золот. яиц.")
    if chest_count > 0:
        add_easter_item(user, EASTER_CHEST_CODE, chest_count)
        payload["lines"].append(f"📦 Пасха: **+{chest_count}** сундук(а) добавлено в инвентарь.")

    payload["common"] = common_count
    payload["painted"] = painted_count
    payload["gold"] = gold_count
    payload["chests"] = chest_count
    payload["server_points"] = _server_points_from_reward_counts(common_count, painted_count, gold_count)

    if common_count > 0:
        advance_chapter2_progress(user, "earn_common", common_count)
    if rabbit_active and (common_count > 0 or painted_count > 0 or gold_count > 0 or chest_count > 0):
        advance_chapter2_progress(user, "rabbit_reward", 1)
        payload["lines"].extend(_maybe_grant_secret_egg(user, "easter_secret_rabbit_egg", 0.025))
    if source in {"work", "daily"} and _time_phase_key(now) == "morning" and (common_count > 0 or painted_count > 0 or gold_count > 0):
        payload["lines"].extend(_maybe_grant_secret_egg(user, "easter_secret_dawn_egg", 0.03 if source == "daily" else 0.02))
    return payload


def grant_pond_bonus_loot(user: dict[str, Any], *, guild_state: dict[str, Any] | None = None) -> dict[str, Any]:
    if get_easter_phase() != "active":
        return _empty_easter_reward_payload()
    rabbit_active = rabbit_is_active(guild_state)
    server_bonuses = get_server_progress_bonuses(guild_state)
    payload = _empty_easter_reward_payload()
    common = random.randint(2, 5)
    painted = 1 if random.random() <= 0.14 else 0
    gold = 1 if rabbit_active and random.random() <= 0.08 else 0
    chest_chance = 0.12 if rabbit_active else 0.05
    chests = 1 if random.random() <= min(1.0, chest_chance + float(server_bonuses["chest_bonus"])) else 0
    _grant_code(user, EASTER_COMMON_EGG_CODE, common)
    payload["lines"].append(f"🥚 Пасха: **+{common}** обычн. яиц.")
    if painted:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, painted)
        payload["lines"].append("🎨 Пасха: **+1** расписное яйцо.")
    if gold:
        _grant_code(user, EASTER_GOLD_EGG_CODE, gold)
        payload["lines"].append("✨ Пасха: **+1** золотое яйцо.")
    if chests:
        add_easter_item(user, EASTER_CHEST_CODE, chests)
        payload["lines"].append("📦 Пасха: Пасхальный сундук добавлен в инвентарь.")
        payload["lines"].append("📦 Пасха: найден Пасхальный сундук.")
    payload["common"] = common
    payload["painted"] = painted
    payload["gold"] = gold
    payload["chests"] = chests
    payload["server_points"] = _server_points_from_reward_counts(common, painted, gold)
    if rabbit_active:
        advance_chapter2_progress(user, "rabbit_reward", 1)
        payload["lines"].extend(_maybe_grant_secret_egg(user, "easter_secret_rabbit_egg", 0.03))
    if _time_phase_key() == "night":
        payload["lines"].extend(_maybe_grant_secret_egg(user, "easter_secret_moon_egg", 0.03))
    return payload


def open_easter_chest(user: dict[str, Any], *, guild_state: dict[str, Any] | None = None) -> dict[str, Any]:
    rewards = {
        "money": random.randint(12_000, 55_000),
        "gems": random.randint(2, 8),
        "lines": [],
        "common": 0,
        "painted": 0,
        "gold": 0,
        "server_points": 0,
    }
    user["balance"] = int(user.get("balance", 0) or 0) + rewards["money"]
    user["gems"] = int(user.get("gems", 0) or 0) + rewards["gems"]
    rewards["lines"].append(f"💰 Деньги: **+${rewards['money']:,}**")
    rewards["lines"].append(f"💎 Гемы: **+{rewards['gems']}**")

    common = random.randint(1, 4)
    _grant_code(user, EASTER_COMMON_EGG_CODE, common)
    rewards["common"] = common
    rewards["lines"].append(f"🥚 Обычные яйца: **+{common}**")
    if random.random() <= 0.28:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, 1)
        rewards["painted"] = 1
        rewards["lines"].append("🎨 Расписное яйцо: **+1**")
    if random.random() <= 0.05:
        _grant_code(user, EASTER_GOLD_EGG_CODE, 1)
        rewards["gold"] = 1
        rewards["lines"].append("✨ Золотое яйцо: **+1**")
    if random.random() <= 0.08:
        add_easter_item(user, EASTER_TALISMAN_CODE, 1)
        rewards["lines"].append("🐇 Кроличий талисман: **+1**")
    rewards["server_points"] = _server_points_from_reward_counts(rewards["common"], rewards["painted"], rewards["gold"])
    advance_chapter2_progress(user, "open_chest", 1)
    if rabbit_is_active(guild_state):
        advance_chapter2_progress(user, "rabbit_reward", 1)
        rewards["lines"].extend(_maybe_grant_secret_egg(user, "easter_secret_rabbit_egg", 0.03))
    rewards["lines"].extend(_maybe_grant_secret_egg(user, "easter_secret_choco_heart", 0.08))
    return rewards


def upgrade_egg_currency_v2(user: dict[str, Any], tier: str) -> tuple[bool, str]:
    if get_easter_phase() not in {"active", "exchange"}:
        return False, "Обменник сейчас закрыт."

    if tier == "painted":
        if _count_code(user, EASTER_COMMON_EGG_CODE) < 25:
            return False, "Для обмена нужно 25 обычных яиц."
        if not _consume_code(user, EASTER_COMMON_EGG_CODE, 25):
            return False, "Не удалось списать обычные яйца."
        _grant_code(user, EASTER_PAINTED_EGG_CODE, 1)
        advance_chapter2_progress(user, "exchange_once", 1)
        secret_lines = _maybe_grant_secret_egg(user, "easter_secret_mirror_egg", 0.02)
        message = "Обмен завершён: **25 обычных → 1 расписное**."
        if secret_lines:
            message += "\n" + "\n".join(secret_lines)
        return True, message

    if tier == "gold":
        if _count_code(user, EASTER_PAINTED_EGG_CODE) < 10:
            return False, "Для обмена нужно 10 расписных яиц."
        if not _consume_code(user, EASTER_PAINTED_EGG_CODE, 10):
            return False, "Не удалось списать расписные яйца."
        _grant_code(user, EASTER_GOLD_EGG_CODE, 1)
        advance_chapter2_progress(user, "exchange_once", 1)
        secret_lines = _maybe_grant_secret_egg(user, "easter_secret_mirror_egg", 0.03)
        message = "Обмен завершён: **10 расписных → 1 золотое**."
        if secret_lines:
            message += "\n" + "\n".join(secret_lines)
        return True, message

    return False, "Неизвестный тип обмена."


def buy_easter_business_v2(user: dict[str, Any], business_key: str) -> tuple[bool, str]:
    if get_easter_phase() != "active":
        return False, "Пасхальные бизнесы доступны только во время активного ивента."
    business = EASTER_TEMP_BUSINESSES.get(business_key)
    if business is None:
        return False, "Такого пасхального бизнеса нет."
    businesses = get_easter_businesses(user)
    if business_key in businesses:
        return False, "Этот пасхальный бизнес уже куплен."

    counts = get_easter_counts(user)
    if counts["common"] < int(business["common_price"]):
        return False, "Не хватает обычных яиц."
    if counts["painted"] < int(business["painted_price"]):
        return False, "Не хватает расписных яиц."
    if counts["gold"] < int(business["gold_price"]):
        return False, "Не хватает золотых яиц."
    if int(user.get("balance", 0) or 0) < int(business["money_price"]):
        return False, "Не хватает денег."

    if int(business["common_price"]) > 0 and not _consume_code(user, EASTER_COMMON_EGG_CODE, int(business["common_price"])):
        return False, "Не удалось списать обычные яйца."
    if int(business["painted_price"]) > 0 and not _consume_code(user, EASTER_PAINTED_EGG_CODE, int(business["painted_price"])):
        return False, "Не удалось списать расписные яйца."
    if int(business["gold_price"]) > 0 and not _consume_code(user, EASTER_GOLD_EGG_CODE, int(business["gold_price"])):
        return False, "Не удалось списать золотые яйца."

    user["balance"] = int(user.get("balance", 0) or 0) - int(business["money_price"])
    businesses[business_key] = {
        "owned_at": utc_now().isoformat(),
        "last_collect": utc_now().isoformat(),
        "converted_to_trophy": False,
    }
    advance_chapter2_progress(user, "buy_shop_item", 1)
    return True, f"Куплен бизнес **{business['name']}**."


def collect_easter_businesses_v2(
    user: dict[str, Any],
    *,
    guild_state: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, Any]]:
    if get_easter_phase() != "active":
        return False, {"message": "Сбор пасхальных бизнесов закрыт."}
    businesses = get_easter_businesses(user)
    if not businesses:
        return False, {"message": "Пасхальных бизнесов пока нет."}

    now = utc_now()
    total_money = 0
    total_common = 0
    total_painted = 0
    ready = 0
    lines: list[str] = []
    server_bonuses = get_server_progress_bonuses(guild_state)
    money_bonus = _event_business_money_bonus(user) * (1.0 + float(server_bonuses["business_money_bonus"]))

    for business_key, payload in businesses.items():
        business = EASTER_TEMP_BUSINESSES.get(business_key)
        if business is None:
            continue
        try:
            last_collect = _parse_dt(str(payload.get("last_collect") or payload.get("owned_at") or now.isoformat()))
        except ValueError:
            last_collect = now
        cycle = timedelta(hours=int(business["cycle_hours"]))
        if now - last_collect < cycle:
            continue

        ready += 1
        money = int(round(int(business["income_money"]) * money_bonus))
        eggs = random.randint(*business["income_common"])
        total_money += money
        total_common += eggs
        if random.random() <= float(business["painted_chance"]):
            total_painted += 1
        payload["last_collect"] = now.isoformat()
        lines.append(f"{business['emoji']} **{business['name']}**: +${money:,} и +{eggs} 🥚")

    if ready <= 0:
        return False, {"message": "Пасхальные бизнесы ещё не готовы."}

    user["balance"] = int(user.get("balance", 0) or 0) + total_money
    _grant_code(user, EASTER_COMMON_EGG_CODE, total_common)
    if total_painted > 0:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, total_painted)

    advance_chapter2_progress(user, "earn_common", total_common)
    if rabbit_is_active(guild_state) and (total_common > 0 or total_painted > 0):
        advance_chapter2_progress(user, "rabbit_reward", 1)
        lines.extend(_maybe_grant_secret_egg(user, "easter_secret_rabbit_egg", 0.03))

    return True, {
        "money": total_money,
        "common": total_common,
        "painted": total_painted,
        "lines": lines,
        "server_points": _server_points_from_reward_counts(total_common, total_painted, 0),
    }


def buy_easter_shop_item_v2(
    user: dict[str, Any],
    item_code: str,
    *,
    guild_state: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    if get_easter_phase() != "active":
        return False, "Пасхальный магазин открыт только во время активного ивента."

    visible_items = get_visible_easter_shop_items(guild_state)
    item = next((entry for entry in visible_items if entry["code"] == item_code), None)
    if item is None:
        hidden_item = next((entry for entry in EASTER_SHOP_ITEMS if entry["code"] == item_code), None)
        if hidden_item is not None and not easter_shop_item_visible(hidden_item, guild_state):
            return False, "Этот товар откроется позже, когда сервер продвинется дальше по пасхальному прогрессу."
        return False, "Такого предмета нет."

    kind = str(item["kind"])
    if kind == "business":
        return buy_easter_business_v2(user, item_code)

    counts = get_easter_counts(user)
    if counts["common"] < int(item.get("price_common", 0) or 0):
        return False, "Не хватает обычных яиц."
    if counts["painted"] < int(item.get("price_painted", 0) or 0):
        return False, "Не хватает расписных яиц."
    if counts["gold"] < int(item.get("price_gold", 0) or 0):
        return False, "Не хватает золотых яиц."

    money_price = int(item.get("money_price", 0) or 0)
    if money_price > 0 and int(user.get("balance", 0) or 0) < money_price:
        return False, "Не хватает денег."

    if int(item.get("price_common", 0) or 0) > 0 and not _consume_code(user, EASTER_COMMON_EGG_CODE, int(item["price_common"])):
        return False, "Не удалось списать обычные яйца."
    if int(item.get("price_painted", 0) or 0) > 0 and not _consume_code(user, EASTER_PAINTED_EGG_CODE, int(item["price_painted"])):
        return False, "Не удалось списать расписные яйца."
    if int(item.get("price_gold", 0) or 0) > 0 and not _consume_code(user, EASTER_GOLD_EGG_CODE, int(item["price_gold"])):
        return False, "Не удалось списать золотые яйца."
    if money_price > 0:
        user["balance"] = int(user.get("balance", 0) or 0) - money_price

    if kind == "case":
        add_easter_item(user, EASTER_CHEST_CODE, 1)
        advance_chapter2_progress(user, "buy_shop_item", 1)
        return True, "Куплен **Пасхальный кейс** и добавлен в инвентарь."
    if kind == "bait":
        add_general_item(
            user,
            item_type="bait_bundle",
            code="easter_bait_festive",
            name="Праздничная наживка",
            emoji="",
            description="Праздничная наживка. Используй её через `/inventory`.",
            quantity=3,
            payload=_event_payload({"bait": "festive", "amount": 2}),
            stackable=True,
        )
        advance_chapter2_progress(user, "buy_shop_item", 1)
        return True, "Куплена **Праздничная наживка**."
    if kind == "pass":
        add_easter_item(user, EASTER_POND_PASS_CODE, 1)
        advance_chapter2_progress(user, "buy_shop_item", 1)
        return True, "Куплен пропуск на **Пруд золотого кролика**."
    if kind == "theme":
        theme_key = str(item.get("theme_key") or "mint_bunny")
        add_general_item(
            user,
            item_type="cosmetic_pack",
            code=str(item["code"]),
            name=str(item["name"]),
            emoji="",
            description=f"Открывает тему профиля {item['name']} при использовании.",
            quantity=1,
            payload=_event_payload({"theme": theme_key}),
            stackable=False,
        )
        advance_chapter2_progress(user, "buy_shop_item", 1)
        return True, f"Куплена тема **{item['name']}**."
    if kind == "title":
        title_key = str(item.get("title_key") or "easter_hunter")
        add_general_item(
            user,
            item_type="cosmetic_pack",
            code=str(item["code"]),
            name=str(item["name"]),
            emoji="",
            description=f"Открывает титул {item['name']} при использовании.",
            quantity=1,
            payload=_event_payload({"title": title_key}),
            stackable=False,
        )
        advance_chapter2_progress(user, "buy_shop_item", 1)
        return True, f"Куплен титул **{item['name']}**."
    if kind == "furniture":
        easter_state = ensure_easter_state(user)
        owned = set(str(entry) for entry in easter_state.get("owned_furniture", []))
        if item_code in owned:
            return False, "Этот пасхальный декор уже куплен."
        easter_state["owned_furniture"].append(item_code)
        advance_chapter2_progress(user, "buy_shop_item", 1)
        furniture_name = EASTER_FURNITURE_BUFFS[item_code]["name"]
        return True, f"Куплен декор **{furniture_name}**. Его бонус активируется сразу, без отдельного предмета в инвентаре."
    return False, "Этот тип предмета пока не поддерживается."


def unlock_easter_pond(user: dict[str, Any]) -> bool:
    fishing = _ensure_fishing_state(user)
    unlocked = fishing.get("unlocked_zones", ["river_bank"])
    if EASTER_POND_ZONE_KEY in unlocked:
        return False
    unlocked.append(EASTER_POND_ZONE_KEY)
    fishing["unlocked_zones"] = unlocked
    if not fishing.get("selected_zone"):
        fishing["selected_zone"] = EASTER_POND_ZONE_KEY
    return True


def easter_pond_available(now: datetime | None = None) -> bool:
    return get_easter_phase(now) == "active"


def register_easter_fishing_content() -> None:
    from cogs import fishing as fishing_cog
    from cogs import fishing_world

    if EASTER_POND_ZONE_KEY not in fishing_world.FISHING_ZONES:
        fishing_world.FISHING_ZONES[EASTER_POND_ZONE_KEY] = {
            "name": "Пруд золотого кролика",
            "price": 0,
            "gems": 0,
            "tag": "event",
            "boss_enabled": False,
            "value_bonus": 1.18,
            "weight_bonus": 1.05,
            "chance_bonus": {"rare": 1.08, "epic": 1.12, "legendary": 1.16},
            "legendary_pool": [],
            "fish_pool": {},
            "rarity_weights": {"common": 18.0, "uncommon": 20.0, "rare": 22.0, "epic": 30.0, "legendary": 10.0},
            "description": "Временный пасхальный пруд с яйцами, сундуками и редкой ивентовой рыбой.",
        }

    existing_ids = {str(species.get("id") or "") for species in fishing_world.SPECIES}
    for species in EASTER_FISH_SPECIES:
        if species["id"] not in existing_ids:
            fishing_world.SPECIES.append(deepcopy(species))

    fishing_cog.FISHING_ZONES = fishing_world.FISHING_ZONES
    fishing_cog.ZONE_DISPLAY_NAMES[EASTER_POND_ZONE_KEY] = "Пруд золотого кролика"
    for species in EASTER_FISH_SPECIES:
        fishing_cog.SPECIES_DISPLAY_NAMES[species["id"]] = species["name"]


def get_collection_progress(user: dict[str, Any]) -> dict[str, bool]:
    state = ensure_easter_state(user)
    if bool(state.get("collection_reward_claimed")):
        return {code: True for code in EASTER_COLLECTION_REQUIREMENTS}
    found_codes = set(str(entry) for entry in state.get("collection_found_codes", []))
    talisman_seen = _count_code(user, EASTER_TALISMAN_CODE) > 0 or EASTER_TALISMAN_CODE in found_codes
    progress: dict[str, bool] = {}
    for code in EASTER_COLLECTION_REQUIREMENTS:
        in_inventory = _count_code(user, code) > 0
        if code == EASTER_CHEST_CODE:
            progress[code] = in_inventory or code in found_codes or talisman_seen
        elif code in EASTER_COLLECTION_HISTORY_CODES:
            progress[code] = in_inventory or code in found_codes
        else:
            progress[code] = in_inventory
    return progress


def collection_can_claim(user: dict[str, Any], now: datetime | None = None) -> bool:
    phase = get_easter_phase(now)
    if phase not in {"active", "exchange"}:
        return False
    state = ensure_easter_state(user)
    if bool(state.get("collection_reward_claimed")):
        return False
    progress = get_collection_progress(user)
    return all(progress.values())


def _consume_code(user: dict[str, Any], code: str, quantity: int = 1) -> bool:
    remaining = quantity
    general_items = sorted(
        [item for item in get_general_items(user) if str(item.get("code") or "") == code],
        key=lambda item: int(item.get("id", 0) or 0),
    )
    for item in general_items:
        item_quantity = int(item.get("quantity", 0) or 0)
        if item_quantity <= 0:
            continue
        step = min(item_quantity, remaining)
        decremented = decrement_general_item(user, int(item["id"]), step)
        if decremented is not None:
            remaining -= step
        if remaining <= 0:
            return True
    return remaining <= 0


def claim_collection(user: dict[str, Any]) -> bool:
    if not collection_can_claim(user):
        return False
    for code in EASTER_COLLECTION_TURNIN_CODES:
        if not _consume_code(user, code, 1):
            return False
    state = ensure_easter_state(user)
    state["collection_reward_claimed"] = True
    return True


def upgrade_egg_currency(user: dict[str, Any], tier: str) -> tuple[bool, str]:
    if get_easter_phase() not in {"active", "exchange"}:
        return False, "Обменник сейчас закрыт."
    if tier == "painted":
        if _count_code(user, EASTER_COMMON_EGG_CODE) < 25:
            return False, "Для обмена нужно 25 обычных яиц."
        if not _consume_code(user, EASTER_COMMON_EGG_CODE, 25):
            return False, "Не удалось списать обычные яйца."
        _grant_code(user, EASTER_PAINTED_EGG_CODE, 1)
        return True, "Обмен завершён: **25 обычных → 1 расписное**."
    if tier == "gold":
        if _count_code(user, EASTER_PAINTED_EGG_CODE) < 10:
            return False, "Для обмена нужно 10 расписных яиц."
        if not _consume_code(user, EASTER_PAINTED_EGG_CODE, 10):
            return False, "Не удалось списать расписные яйца."
        _grant_code(user, EASTER_GOLD_EGG_CODE, 1)
        return True, "Обмен завершён: **10 расписных → 1 золотое**."
    return False, "Неизвестный тип обмена."


def sellback_eggs(user: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if get_easter_phase() != "exchange":
        return False, {"message": "Выкуп яиц доступен только в фазе exchange."}
    common = _count_code(user, EASTER_COMMON_EGG_CODE)
    painted = _count_code(user, EASTER_PAINTED_EGG_CODE)
    gold = _count_code(user, EASTER_GOLD_EGG_CODE)
    if common <= 0 and painted <= 0 and gold <= 0:
        return False, {"message": "Сдавать пока нечего."}

    payout = common * 300 + painted * 4_000 + gold * 35_000
    if common:
        _consume_code(user, EASTER_COMMON_EGG_CODE, common)
    if painted:
        _consume_code(user, EASTER_PAINTED_EGG_CODE, painted)
    if gold:
        _consume_code(user, EASTER_GOLD_EGG_CODE, gold)
    user["balance"] = int(user.get("balance", 0) or 0) + payout
    return True, {"money": payout, "common": common, "painted": painted, "gold": gold}


def item_belongs_to_easter(item: dict[str, Any]) -> bool:
    payload = item.get("payload")
    return isinstance(payload, dict) and str(payload.get("event_key") or "") == EASTER_EVENT_KEY


def split_active_and_archived_items(general_items: list[dict[str, Any]], now: datetime | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if get_easter_phase(now) != "off":
        return list(general_items), []
    active: list[dict[str, Any]] = []
    archived: list[dict[str, Any]] = []
    for item in general_items:
        code = str(item.get("code") or "")
        if item_belongs_to_easter(item) and code in EASTER_INACTIVE_CODES:
            archived.append(item)
        else:
            active.append(item)
    return active, archived


def archive_summary_lines(archived_items: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in archived_items[:8]:
        quantity = int(item.get("quantity", 1) or 1)
        emoji = f"{item.get('emoji', '')} " if item.get("emoji") else ""
        lines.append(f"{emoji}**{item.get('name', 'Предмет')}** x{quantity}")
    return lines


def get_easter_businesses(user: dict[str, Any]) -> dict[str, Any]:
    state = ensure_easter_state(user)
    businesses = state.get("businesses")
    if not isinstance(businesses, dict):
        businesses = {}
        state["businesses"] = businesses
    return businesses


def buy_easter_business(user: dict[str, Any], business_key: str) -> tuple[bool, str]:
    if get_easter_phase() != "active":
        return False, "Пасхальные бизнесы доступны только во время активного ивента."
    business = EASTER_TEMP_BUSINESSES.get(business_key)
    if business is None:
        return False, "Такого пасхального бизнеса нет."
    businesses = get_easter_businesses(user)
    if business_key in businesses:
        return False, "Этот пасхальный бизнес уже куплен."
    counts = get_easter_counts(user)
    if counts["common"] < int(business["common_price"]):
        return False, "Не хватает обычных яиц."
    if counts["painted"] < int(business["painted_price"]):
        return False, "Не хватает расписных яиц."
    if counts["gold"] < int(business["gold_price"]):
        return False, "Не хватает золотых яиц."
    if int(user.get("balance", 0) or 0) < int(business["money_price"]):
        return False, "Не хватает денег."
    if int(business["common_price"]) > 0 and not _consume_code(user, EASTER_COMMON_EGG_CODE, int(business["common_price"])):
        return False, "Не удалось списать обычные яйца."
    if int(business["painted_price"]) > 0 and not _consume_code(user, EASTER_PAINTED_EGG_CODE, int(business["painted_price"])):
        return False, "Не удалось списать расписные яйца."
    if int(business["gold_price"]) > 0 and not _consume_code(user, EASTER_GOLD_EGG_CODE, int(business["gold_price"])):
        return False, "Не удалось списать золотые яйца."
    user["balance"] = int(user.get("balance", 0) or 0) - int(business["money_price"])
    businesses[business_key] = {
        "owned_at": utc_now().isoformat(),
        "last_collect": utc_now().isoformat(),
        "converted_to_trophy": False,
    }
    return True, f"Куплен бизнес **{business['name']}**."


def collect_easter_businesses(user: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    if get_easter_phase() != "active":
        return False, {"message": "Сбор пасхальных бизнесов закрыт."}
    businesses = get_easter_businesses(user)
    if not businesses:
        return False, {"message": "Пасхальных бизнесов пока нет."}
    now = utc_now()
    total_money = 0
    total_common = 0
    total_painted = 0
    ready = 0
    lines: list[str] = []
    money_bonus = _event_business_money_bonus(user)
    for business_key, payload in businesses.items():
        business = EASTER_TEMP_BUSINESSES.get(business_key)
        if business is None:
            continue
        try:
            last_collect = _parse_dt(str(payload.get("last_collect") or payload.get("owned_at") or now.isoformat()))
        except ValueError:
            last_collect = now
        cycle = timedelta(hours=int(business["cycle_hours"]))
        if now - last_collect < cycle:
            continue
        ready += 1
        money = int(round(int(business["income_money"]) * money_bonus))
        eggs = random.randint(*business["income_common"])
        total_money += money
        total_common += eggs
        if random.random() <= float(business["painted_chance"]):
            total_painted += 1
        payload["last_collect"] = now.isoformat()
        lines.append(f"{business['emoji']} **{business['name']}**: +${money:,} и +{eggs} 🥚")
    if ready <= 0:
        return False, {"message": "Пасхальные бизнесы ещё не готовы."}
    user["balance"] = int(user.get("balance", 0) or 0) + total_money
    _grant_code(user, EASTER_COMMON_EGG_CODE, total_common)
    if total_painted > 0:
        _grant_code(user, EASTER_PAINTED_EGG_CODE, total_painted)
    return True, {"money": total_money, "common": total_common, "painted": total_painted, "lines": lines}


def convert_inactive_easter_businesses_to_trophies(user: dict[str, Any]) -> list[str]:
    if get_easter_phase() == "active":
        return []
    businesses = get_easter_businesses(user)
    if not businesses:
        return []
    converted: list[str] = []
    for business_key, payload in list(businesses.items()):
        business = EASTER_TEMP_BUSINESSES.get(business_key)
        if business is None:
            continue
        if bool(payload.get("converted_to_trophy")):
            continue
        add_easter_trophy(
            user,
            str(business["trophy_code"]),
            f"Трофей: {business['name']} 2026",
            f"Памятный трофей за участие в пасхальном ивенте 2026. Раньше это был бизнес **{business['name']}**.",
        )
        payload["converted_to_trophy"] = True
        converted.append(str(business["name"]))
    for business_key in list(businesses):
        if bool(businesses[business_key].get("converted_to_trophy")):
            businesses.pop(business_key, None)
    return converted


def buy_easter_shop_item(user: dict[str, Any], item_code: str) -> tuple[bool, str]:
    if get_easter_phase() != "active":
        return False, "Пасхальный магазин открыт только во время активного ивента."
    item = next((entry for entry in EASTER_SHOP_ITEMS if entry["code"] == item_code), None)
    if item is None:
        return False, "Такого предмета нет."
    kind = str(item["kind"])
    if kind == "business":
        return buy_easter_business(user, item_code)
    counts = get_easter_counts(user)
    if counts["common"] < int(item.get("price_common", 0) or 0):
        return False, "Не хватает обычных яиц."
    if counts["painted"] < int(item.get("price_painted", 0) or 0):
        return False, "Не хватает расписных яиц."
    if counts["gold"] < int(item.get("price_gold", 0) or 0):
        return False, "Не хватает золотых яиц."
    money_price = int(item.get("money_price", 0) or 0)
    if money_price > 0 and int(user.get("balance", 0) or 0) < money_price:
        return False, "Не хватает денег."
    if int(item.get("price_common", 0) or 0) > 0 and not _consume_code(user, EASTER_COMMON_EGG_CODE, int(item["price_common"])):
        return False, "Не удалось списать обычные яйца."
    if int(item.get("price_painted", 0) or 0) > 0 and not _consume_code(user, EASTER_PAINTED_EGG_CODE, int(item["price_painted"])):
        return False, "Не удалось списать расписные яйца."
    if int(item.get("price_gold", 0) or 0) > 0 and not _consume_code(user, EASTER_GOLD_EGG_CODE, int(item["price_gold"])):
        return False, "Не удалось списать золотые яйца."
    if money_price > 0:
        user["balance"] = int(user.get("balance", 0) or 0) - money_price

    if kind == "case":
        add_easter_item(user, EASTER_CHEST_CODE, 1)
        return True, "Куплен **Пасхальный кейс** и добавлен в инвентарь."
    if kind == "bait":
        add_general_item(
            user,
            item_type="bait_bundle",
            code="easter_bait_festive",
            name="Праздничная наживка",
            emoji="",
            description="Праздничная наживка. Используй её через `/inventory`.",
            quantity=3,
            payload=_event_payload({"bait": "festive", "amount": 2}),
            stackable=True,
        )
        return True, "Куплена **Праздничная наживка**."
    if kind == "pass":
        add_easter_item(user, EASTER_POND_PASS_CODE, 1)
        return True, "Куплен пропуск на **Пруд золотого кролика**."
    if kind == "theme":
        add_general_item(
            user,
            item_type="cosmetic_pack",
            code="easter_profile_theme",
            name="Mint Bunny",
            emoji="",
            description="Открывает тему профиля Mint Bunny при использовании.",
            quantity=1,
            payload=_event_payload({"theme": "mint_bunny"}),
            stackable=False,
        )
        return True, "Куплена тема **Mint Bunny**."
    if kind == "title":
        add_general_item(
            user,
            item_type="cosmetic_pack",
            code="easter_profile_title",
            name="Пасхальный титул",
            emoji="",
            description="Открывает Пасхальный титул при использовании.",
            quantity=1,
            payload=_event_payload({"title": "easter_hunter"}),
            stackable=False,
        )
        return True, "Куплен **Пасхальный титул**."
    if kind == "furniture":
        easter_state = ensure_easter_state(user)
        owned = set(str(entry) for entry in easter_state.get("owned_furniture", []))
        if item_code in owned:
            return False, "Этот пасхальный декор уже куплен."
        easter_state["owned_furniture"].append(item_code)
        furniture_name = EASTER_FURNITURE_BUFFS[item_code]["name"]
        return True, f"Куплен декор **{furniture_name}**. Его бонус активируется сразу, без отдельного предмета в инвентаре."
    if kind == "business":
        return buy_easter_business(user, item_code)
    return False, "Этот тип предмета пока не поддерживается."
