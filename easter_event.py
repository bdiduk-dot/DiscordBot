from __future__ import annotations

import os
import random
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from inventory_system import add_general_item, count_general_items, decrement_general_item, ensure_inventory_state, get_general_items

EASTER_EVENT_KEY = "easter_2026"
EASTER_PHASES = {"off", "active", "exchange"}

_DEFAULT_EVENT_END = "2026-04-20T21:00:00+03:00"
_DEFAULT_EXCHANGE_END = "2026-04-27T21:00:00+03:00"
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
    {"code": "easter_profile_theme", "name": "Mint Bunny", "emoji": "🌿", "kind": "theme", "price_common": 50, "price_painted": 2, "price_gold": 0},
    {"code": "easter_profile_title", "name": "Пасхальный титул", "emoji": "👑", "kind": "title", "price_common": 0, "price_painted": 3, "price_gold": 0},
    {"code": "easter_egg_basket", "name": "Корзина с яйцами", "emoji": "🧺", "kind": "furniture", "price_common": 45, "price_painted": 0, "price_gold": 0},
    {"code": "easter_rabbit_lamp", "name": "Кроличья лампа", "emoji": "🐰", "kind": "furniture", "price_common": 95, "price_painted": 1, "price_gold": 0},
    {"code": "easter_chocolate_fountain", "name": "Шоколадный фонтан", "emoji": "🍫", "kind": "furniture", "price_common": 80, "price_painted": 1, "price_gold": 0},
    {"code": "easter_bakery", "name": "Пасхальная лавка", "emoji": "🏪", "kind": "business", "price_common": 140, "price_painted": 3, "price_gold": 0, "money_price": 150_000},
    {"code": "easter_chocolate_lab", "name": "Шоколадная мастерская", "emoji": "🍫", "kind": "business", "price_common": 240, "price_painted": 6, "price_gold": 1, "money_price": 325_000},
]

EASTER_FISH_SPECIES = [
    {"id": "easter_carrot_koi", "name": "Морковный кои", "emoji": "🐟", "rarity": "rare", "zones": [EASTER_POND_ZONE_KEY], "phases": ["morning", "day", "evening"], "min_weight_kg": 1.0, "max_weight_kg": 4.2, "price_mult": 1.22},
    {"id": "easter_choco_trout", "name": "Шоколадная форель", "emoji": "🐠", "rarity": "epic", "zones": [EASTER_POND_ZONE_KEY], "phases": ["day", "evening"], "min_weight_kg": 2.8, "max_weight_kg": 8.5, "price_mult": 1.34},
    {"id": "easter_golden_harefin", "name": "Золотой кролик-плавник", "emoji": "🐣", "rarity": "legendary", "zones": [EASTER_POND_ZONE_KEY], "phases": ["evening", "night"], "min_weight_kg": 5.5, "max_weight_kg": 15.0, "price_mult": 1.50},
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
    return state


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
            "rarity_weights": {"common": 0.0, "uncommon": 0.0, "rare": 62.0, "epic": 28.0, "legendary": 10.0},
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
