from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

LEGACY_ZONE_NAME_TO_KEY = {
    "Речной берег": "river_bank",
    "Тростниковая топь": "reed_swamp",
    "Лунное озеро": "moon_lake",
    "Штормовой берег": "storm_coast",
    "Кристальная бухта": "crystal_cove",
    "Бездна Левиафана": "abyss_trench",
}


def _system_state(user: dict[str, Any]) -> dict[str, Any]:
    game_stats = user.get("game_stats")
    if not isinstance(game_stats, dict):
        game_stats = {}
        user["game_stats"] = game_stats
    systems = game_stats.get("_systems")
    if not isinstance(systems, dict):
        systems = {}
        game_stats["_systems"] = systems
    return systems


def _empty_inventory_state() -> dict[str, Any]:
    return {
        "fish_items": [],
        "general_items": [],
        "next_item_id": 1,
    }


def _payload_signature(payload: dict[str, Any] | None) -> str:
    normalized = payload if isinstance(payload, dict) else {}
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_iso(value: Any) -> str:
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return _now_iso()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    return _now_iso()


def _reserve_normalized_id(item: dict[str, Any], used_ids: set[int], next_item_id: int) -> tuple[int, int]:
    candidate = _safe_int(item.get("id"), 0)
    if candidate > 0 and candidate not in used_ids:
        used_ids.add(candidate)
        return candidate, max(next_item_id, candidate + 1)

    next_id = max(1, next_item_id)
    while next_id in used_ids:
        next_id += 1
    used_ids.add(next_id)
    return next_id, next_id + 1


def _normalize_fish_item(
    raw_item: dict[str, Any],
    used_ids: set[int],
    next_item_id: int,
) -> tuple[dict[str, Any] | None, int]:
    if not isinstance(raw_item, dict):
        return None, next_item_id

    item = deepcopy(raw_item)
    item_id, next_item_id = _reserve_normalized_id(item, used_ids, next_item_id)
    zone_name = str(item.get("zone") or item.get("zone_name") or "")
    zone_key = str(item.get("zone_key") or LEGACY_ZONE_NAME_TO_KEY.get(zone_name, "river_bank"))
    if not zone_name:
        zone_name = zone_key

    item["id"] = item_id
    item["species_id"] = str(item.get("species_id") or "")
    item["name"] = str(item.get("name") or "Рыба")
    item["emoji"] = str(item.get("emoji") or "🐟")
    item["rarity"] = str(item.get("rarity") or "common")
    item["rarity_name"] = str(item.get("rarity_name") or item["rarity"] or "Обычная")
    item["price"] = max(0, _safe_int(item.get("price"), 0))
    item["zone_key"] = zone_key
    item["zone"] = zone_name
    item["weight_kg"] = _safe_float(item.get("weight_kg"), 0.0)
    item["caught_at"] = _coerce_iso(item.get("caught_at"))
    item["locked"] = bool(item.get("locked"))
    return item, next_item_id


def _normalize_general_item(
    raw_item: dict[str, Any],
    used_ids: set[int],
    next_item_id: int,
) -> tuple[dict[str, Any] | None, int]:
    if not isinstance(raw_item, dict):
        return None, next_item_id

    item = deepcopy(raw_item)
    item_id, next_item_id = _reserve_normalized_id(item, used_ids, next_item_id)
    item_type = str(item.get("item_type") or item.get("type") or "legacy_item")
    code = str(item.get("code") or item.get("symbol") or item_type or f"item_{item_id}")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    item["id"] = item_id
    item["item_type"] = item_type
    item["code"] = code
    item["name"] = str(item.get("name") or code.replace("_", " ").title())
    item["emoji"] = str(item.get("emoji") or "")
    item["description"] = str(
        item.get("description")
        or (
            "Старый предмет из инвентаря. Используй, чтобы забрать стоимость."
            if item_type == "crypto_cache"
            else "Предмет перенесён из старого инвентаря."
            if item_type.startswith("legacy_")
            else "Предмет из инвентаря."
        )
    )
    item["quantity"] = max(1, _safe_int(item.get("quantity"), 1))
    item["payload"] = payload
    item["acquired_at"] = _coerce_iso(item.get("acquired_at") or item.get("caught_at") or item.get("mined_at"))
    return item, next_item_id


def _convert_legacy_entry(raw_item: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    if not isinstance(raw_item, dict):
        return None, None

    raw_type = str(raw_item.get("type") or "").lower()
    if raw_type == "fish":
        return "fish", {
            "id": raw_item.get("id"),
            "species_id": raw_item.get("species_id"),
            "name": raw_item.get("name"),
            "emoji": raw_item.get("emoji"),
            "rarity": raw_item.get("rarity"),
            "rarity_name": raw_item.get("rarity_name"),
            "price": raw_item.get("price"),
            "zone_key": raw_item.get("zone_key"),
            "zone": raw_item.get("zone"),
            "weight_kg": raw_item.get("weight_kg"),
            "caught_at": raw_item.get("caught_at"),
            "locked": raw_item.get("locked", False),
        }

    if raw_type == "crypto":
        crypto_amount = _safe_float(raw_item.get("amount"), 1.0)
        mined_price = _safe_float(raw_item.get("mined_price"), _safe_float(raw_item.get("price"), 0.0))
        payout = max(0, int(round(crypto_amount * mined_price)))
        return "general", {
            "id": raw_item.get("id"),
            "item_type": "crypto_cache",
            "code": str(raw_item.get("symbol") or "legacy_crypto"),
            "name": str(raw_item.get("name") or "Крипта"),
            "emoji": str(raw_item.get("emoji") or "💠"),
            "description": "Старая криптопозиция из инвентаря. Используй, чтобы забрать её стоимость.",
            "quantity": 1,
            "payload": {
                "amount": payout,
                "crypto_name": str(raw_item.get("name") or "Crypto"),
                "crypto_amount": str(raw_item.get("amount") or "1"),
            },
            "acquired_at": raw_item.get("mined_at") or raw_item.get("acquired_at"),
        }

    code = str(raw_item.get("code") or raw_item.get("symbol") or raw_item.get("name") or raw_type or "legacy_item")
    item_type = f"legacy_{raw_type}" if raw_type else "legacy_item"
    return "general", {
        "id": raw_item.get("id"),
        "item_type": item_type,
        "code": code,
        "name": str(raw_item.get("name") or code.replace("_", " ").title()),
        "emoji": str(raw_item.get("emoji") or ""),
        "description": str(raw_item.get("description") or "Перенесено из старого инвентаря."),
        "quantity": max(1, _safe_int(raw_item.get("quantity"), 1)),
        "payload": {"raw_item": deepcopy(raw_item)},
        "acquired_at": raw_item.get("acquired_at") or raw_item.get("caught_at") or raw_item.get("mined_at"),
    }


def _raw_inventory_to_state(raw_inventory: Any) -> dict[str, Any]:
    if isinstance(raw_inventory, dict):
        return deepcopy(raw_inventory)

    state = _empty_inventory_state()
    if not isinstance(raw_inventory, list):
        return state

    for raw_item in raw_inventory:
        kind, item = _convert_legacy_entry(raw_item)
        if kind == "fish" and isinstance(item, dict):
            state["fish_items"].append(item)
        elif kind == "general" and isinstance(item, dict):
            state["general_items"].append(item)
    return state


def _item_signature(kind: str, item: dict[str, Any]) -> str:
    if kind == "fish":
        payload = {
            "id": _safe_int(item.get("id"), 0),
            "species_id": str(item.get("species_id") or ""),
            "name": str(item.get("name") or ""),
            "rarity": str(item.get("rarity") or ""),
            "price": _safe_int(item.get("price"), 0),
            "zone_key": str(item.get("zone_key") or ""),
            "zone": str(item.get("zone") or ""),
            "weight_kg": _safe_float(item.get("weight_kg"), 0.0),
            "caught_at": str(item.get("caught_at") or ""),
            "locked": bool(item.get("locked")),
        }
    else:
        payload = {
            "id": _safe_int(item.get("id"), 0),
            "item_type": str(item.get("item_type") or item.get("type") or ""),
            "code": str(item.get("code") or item.get("symbol") or ""),
            "name": str(item.get("name") or ""),
            "quantity": max(1, _safe_int(item.get("quantity"), 1)),
            "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
            "acquired_at": str(item.get("acquired_at") or item.get("mined_at") or ""),
        }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _merge_inventory_sources(*sources: Any) -> dict[str, Any]:
    merged = _empty_inventory_state()
    seen_ids: set[int] = set()
    seen_signatures: set[str] = set()
    next_item_id = 1

    for raw_source in sources:
        source = _raw_inventory_to_state(raw_source)
        next_item_id = max(next_item_id, _safe_int(source.get("next_item_id"), 1))

        for kind, key in (("fish", "fish_items"), ("general", "general_items")):
            for item in source.get(key, []):
                if not isinstance(item, dict):
                    continue
                item_id = _safe_int(item.get("id"), 0)
                signature = _item_signature(kind, item)
                if item_id > 0 and item_id in seen_ids:
                    continue
                if signature in seen_signatures:
                    continue
                if item_id > 0:
                    seen_ids.add(item_id)
                seen_signatures.add(signature)
                merged[key].append(deepcopy(item))

    normalized = _empty_inventory_state()
    used_ids: set[int] = set()
    current_next_id = max(1, next_item_id)

    for item in merged["fish_items"]:
        normalized_item, current_next_id = _normalize_fish_item(item, used_ids, current_next_id)
        if normalized_item is not None:
            normalized["fish_items"].append(normalized_item)

    for item in merged["general_items"]:
        normalized_item, current_next_id = _normalize_general_item(item, used_ids, current_next_id)
        if normalized_item is not None:
            normalized["general_items"].append(normalized_item)

    normalized["next_item_id"] = max(1, current_next_id)
    return normalized


def ensure_inventory_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _system_state(user)
    column_inventory = user.get("inventory")
    systems_inventory = systems.get("inventory")

    if column_inventory is systems_inventory and isinstance(column_inventory, dict):
        inventory = _merge_inventory_sources(column_inventory)
    else:
        inventory = _merge_inventory_sources(column_inventory, systems_inventory)

    user["inventory"] = inventory
    systems["inventory"] = inventory
    return inventory


def _reserve_item_id(inventory: dict[str, Any]) -> int:
    used_ids = {
        _safe_int(item.get("id"), 0)
        for item in inventory.get("fish_items", []) + inventory.get("general_items", [])
        if isinstance(item, dict)
    }
    next_item_id = max(1, _safe_int(inventory.get("next_item_id"), 1))
    while next_item_id in used_ids:
        next_item_id += 1
    inventory["next_item_id"] = next_item_id + 1
    return next_item_id


def add_fish_item(
    user: dict[str, Any],
    *,
    species_id: str,
    name: str,
    emoji: str,
    rarity: str,
    rarity_name: str,
    price: int,
    zone_key: str,
    zone: str,
    weight_kg: float,
    caught_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    inventory = ensure_inventory_state(user)
    item = {
        "id": _reserve_item_id(inventory),
        "species_id": species_id,
        "name": name,
        "emoji": emoji,
        "rarity": rarity,
        "rarity_name": rarity_name,
        "price": int(price),
        "zone_key": zone_key,
        "zone": zone,
        "weight_kg": float(weight_kg),
        "caught_at": caught_at or _now_iso(),
        "locked": False,
    }
    if isinstance(extra, dict):
        item.update(deepcopy(extra))
    inventory["fish_items"].append(item)
    return item


def add_general_item(
    user: dict[str, Any],
    *,
    item_type: str,
    code: str,
    name: str,
    description: str,
    quantity: int = 1,
    emoji: str = "",
    payload: dict[str, Any] | None = None,
    stackable: bool = True,
) -> dict[str, Any]:
    inventory = ensure_inventory_state(user)
    safe_payload = deepcopy(payload) if isinstance(payload, dict) else {}
    amount = max(1, int(quantity or 1))
    if stackable:
        signature = _payload_signature(safe_payload)
        for item in inventory["general_items"]:
            if not isinstance(item, dict):
                continue
            if (
                str(item.get("item_type") or "") == item_type
                and str(item.get("code") or "") == code
                and _payload_signature(item.get("payload")) == signature
            ):
                item["quantity"] = max(1, int(item.get("quantity", 1) or 1) + amount)
                if emoji and not item.get("emoji"):
                    item["emoji"] = emoji
                if description and not item.get("description"):
                    item["description"] = description
                return item

    item = {
        "id": _reserve_item_id(inventory),
        "item_type": item_type,
        "code": code,
        "name": name,
        "emoji": emoji,
        "description": description,
        "quantity": amount,
        "payload": safe_payload,
        "acquired_at": _now_iso(),
    }
    inventory["general_items"].append(item)
    return item


def get_fish_items(user: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = ensure_inventory_state(user)
    return [item for item in inventory.get("fish_items", []) if isinstance(item, dict)]


def get_general_items(user: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = ensure_inventory_state(user)
    return [item for item in inventory.get("general_items", []) if isinstance(item, dict)]


def find_fish_item(user: dict[str, Any], item_id: int) -> dict[str, Any] | None:
    target = int(item_id)
    for item in get_fish_items(user):
        if int(item.get("id", 0) or 0) == target:
            return item
    return None


def find_general_item(user: dict[str, Any], item_id: int) -> dict[str, Any] | None:
    target = int(item_id)
    for item in get_general_items(user):
        if int(item.get("id", 0) or 0) == target:
            return item
    return None


def toggle_fish_lock(user: dict[str, Any], item_id: int) -> dict[str, Any] | None:
    item = find_fish_item(user, item_id)
    if item is None:
        return None
    item["locked"] = not bool(item.get("locked"))
    return item


def sell_fish_items(
    user: dict[str, Any],
    predicate: Callable[[dict[str, Any]], bool],
) -> tuple[list[dict[str, Any]], int]:
    inventory = ensure_inventory_state(user)
    sold: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    total = 0
    for item in inventory.get("fish_items", []):
        if not isinstance(item, dict):
            continue
        if bool(item.get("locked")) or not predicate(item):
            kept.append(item)
            continue
        sold.append(item)
        total += int(item.get("price", 0) or 0)
    inventory["fish_items"] = kept
    return sold, total


def sell_fish_by_id(user: dict[str, Any], item_id: int) -> tuple[dict[str, Any] | None, int]:
    sold, total = sell_fish_items(user, lambda item: int(item.get("id", 0) or 0) == int(item_id))
    if not sold:
        return None, 0
    return sold[0], total


def decrement_general_item(user: dict[str, Any], item_id: int, quantity: int = 1) -> dict[str, Any] | None:
    inventory = ensure_inventory_state(user)
    target = int(item_id)
    amount = max(1, int(quantity or 1))
    for index, item in enumerate(list(inventory.get("general_items", []))):
        if not isinstance(item, dict):
            continue
        if int(item.get("id", 0) or 0) != target:
            continue
        current = max(1, int(item.get("quantity", 1) or 1))
        item_copy = deepcopy(item)
        if current <= amount:
            inventory["general_items"].pop(index)
        else:
            item["quantity"] = current - amount
        return item_copy
    return None


def find_case_item(user: dict[str, Any], case_type: str | None = None, item_id: int | None = None) -> dict[str, Any] | None:
    for item in get_general_items(user):
        if str(item.get("item_type") or "") != "case":
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        current_case_type = str(payload.get("case_type") or item.get("code") or "")
        if item_id is not None and int(item.get("id", 0) or 0) != int(item_id):
            continue
        if case_type is not None and current_case_type != str(case_type):
            continue
        return item
    return None


def consume_case_item(user: dict[str, Any], *, case_type: str | None = None, item_id: int | None = None) -> dict[str, Any] | None:
    item = find_case_item(user, case_type=case_type, item_id=item_id)
    if item is None:
        return None
    return decrement_general_item(user, int(item["id"]), 1)
