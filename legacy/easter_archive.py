from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from inventory_system import ensure_inventory_state

EASTER_EVENT_KEY = "easter_2026"
EASTER_POND_ZONE_KEY = "easter_rabbit_pond"
EASTER_POND_PASS_CODE = "easter_pond_pass"
EASTER_CHEST_CODE = "easter_chest"
EASTER_ARCHIVE_CATEGORY = "Архив 2026"
EASTER_DECOR_TROPHY_PREFIX = "easter_decor_"
EASTER_INACTIVE_CODES = {
    "easter_egg_common",
    "easter_egg_painted",
    "easter_egg_gold",
    EASTER_CHEST_CODE,
    EASTER_POND_PASS_CODE,
}

EASTER_FURNITURE_BUFFS: dict[str, dict[str, Any]] = {
    "easter_egg_basket": {
        "name": "Плетёная корзина",
        "emoji": "🧺",
        "description": "Даёт +2% к урожаю в саду.",
        "garden_yield_bonus": 0.02,
    },
    "easter_rabbit_lamp": {
        "name": "Тёплая лампа",
        "emoji": "🪔",
        "description": "Даёт +2% к выплате аренды.",
        "rent_bonus": 0.02,
    },
    "easter_chocolate_fountain": {
        "name": "Домашний фонтан",
        "emoji": "⛲",
        "description": "Даёт +2% к награде /work.",
        "work_bonus": 0.02,
    },
}


def _systems_state(user: dict[str, Any]) -> dict[str, Any]:
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
    systems = _systems_state(user)
    state = systems.get(EASTER_EVENT_KEY)
    if not isinstance(state, dict):
        state = {}
        systems[EASTER_EVENT_KEY] = state
    owned_furniture = state.get("owned_furniture")
    if not isinstance(owned_furniture, list):
        owned_furniture = []
        state["owned_furniture"] = owned_furniture
    return state


def get_easter_phase(now: datetime | None = None) -> str:
    return "off"


def easter_pond_available(now: datetime | None = None) -> bool:
    return False


def grant_easter_drops(
    user: dict[str, Any],
    source: str,
    *,
    guild_state: dict[str, Any] | None = None,
    natural_blackjack: bool | None = None,
) -> dict[str, Any]:
    return {"lines": [], "server_points": 0}


def grant_pond_bonus_loot(user: dict[str, Any], *, guild_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"lines": [], "server_points": 0}


def get_server_progress_bonuses(guild_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {}


def advance_chapter2_progress(user: dict[str, Any], key: str, amount: int = 1) -> None:
    return None


def unlock_easter_pond(user: dict[str, Any]) -> bool:
    return False


def open_easter_chest(user: dict[str, Any], *, guild_state: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "lines": [
            "Пасхальный сундук уже архивный: после завершения Easter 2026 он больше не открывается."
        ],
        "server_points": 0,
    }


def item_belongs_to_easter(item: dict[str, Any]) -> bool:
    payload = item.get("payload")
    return isinstance(payload, dict) and str(payload.get("event_key") or "") == EASTER_EVENT_KEY


def split_active_and_archived_items(general_items: list[dict[str, Any]], now: datetime | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
    return code in {str(item) for item in easter_state.get("owned_furniture", [])}


def _furniture_bonus_value(user: dict[str, Any], code: str, field: str) -> float:
    if not has_easter_furniture(user, code):
        return 0.0
    furniture = EASTER_FURNITURE_BUFFS.get(code, {})
    return max(0.0, float(furniture.get(field, 0.0) or 0.0))


def collection_garden_yield_multiplier(user: dict[str, Any]) -> float:
    return 1.0 + _furniture_bonus_value(user, "easter_egg_basket", "garden_yield_bonus")


def collection_rent_multiplier(user: dict[str, Any]) -> float:
    return 1.0 + _furniture_bonus_value(user, "easter_rabbit_lamp", "rent_bonus")


def maybe_apply_easter_work_bonus(user: dict[str, Any], amount: int) -> int:
    multiplier = 1.0 + _furniture_bonus_value(user, "easter_chocolate_fountain", "work_bonus")
    return int(round(int(amount) * multiplier))


def migrate_legacy_easter_decor_inventory(user: dict[str, Any]) -> list[str]:
    inventory = ensure_inventory_state(user)
    easter_state = ensure_easter_state(user)
    owned_furniture = {str(item) for item in easter_state.get("owned_furniture", [])}
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


def archived_item_message(item: dict[str, Any] | None = None) -> str:
    name = str((item or {}).get("name") or "Предмет Easter 2026")
    return (
        f"**{name}** уже находится в архиве Easter 2026.\n"
        "Ивент завершён: яйца были автоматически обменяны, а оставшиеся сезонные предметы больше не активируются вручную."
    )
