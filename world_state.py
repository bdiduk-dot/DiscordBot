from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any

from cogs.fishing_world import (
    TIME_PHASES,
    WEATHER_TYPES,
    current_weather,
    get_time_phase_key,
    get_world_state as get_fishing_world_state,
)
from config import COLORS
from adventure_content import ANTIQUARY_ITEMS


WORLD_EVENT_NAMES = {
    "happy_hour": "Счастливый час",
    "crypto_boom": "Крипто-памп",
    "fish_day": "Рыбный день",
    "tax_audit": "Налоговая проверка",
    "shadow_auction": "Теневая аукционная ночь",
    "golden_rush": "Золотая лихорадка",
}

WEATHER_MULTIPLIERS: dict[str, dict[str, float]] = {
    "clear": {"fish": 1.06, "garden": 1.08, "business": 1.03},
    "rain": {"fish": 1.04, "garden": 1.20, "crime": 0.98, "dig": 0.97},
    "fog": {"crime": 1.06, "dig": 1.08, "auction": 1.02},
    "storm": {"fish": 1.10, "dive": 1.10, "casino": 1.06, "mine": 0.92, "business": 0.95},
    "moon_tide": {"fish": 1.12, "dive": 1.14, "dig": 1.06, "blackmarket": 1.03},
}

TIME_PHASE_MULTIPLIERS: dict[str, dict[str, float]] = {
    "morning": {"business": 1.04, "dig": 1.04, "garden": 1.03},
    "day": {"business": 1.05, "garden": 1.06, "auction": 1.02},
    "evening": {"casino": 1.05, "fish": 1.04, "blackmarket": 1.03},
    "night": {"crime": 1.12, "dive": 1.08, "fish": 1.05, "casino": 1.05},
}

WORLD_EVENT_DESCRIPTIONS = {
    "fish_day": "Легендарный улов подходит ближе и рыба продаётся дороже.",
    "crypto_boom": "Майнинг и добыча приносят больше, а рынок оживляется.",
    "happy_hour": "Быстрые способы заработка дают усиленную выплату.",
    "tax_audit": "Бизнесам тяжелее, зато рынок заметно осторожнее.",
    "shadow_auction": "Контрабанда, crime и аукционные сделки становятся горячее.",
    "golden_rush": "Экономика сервера временно разгоняется по нескольким фронтам.",
}

WORLD_STATUS_COLORS = {
    "active": COLORS["success"],
    "soon": COLORS["warning"],
    "ended": COLORS["info"],
}


def _normalize_event_name(event: dict[str, Any] | None) -> str:
    if not isinstance(event, dict):
        return "Без события"
    key = str(event.get("key") or "")
    if key and key in WORLD_EVENT_NAMES:
        return WORLD_EVENT_NAMES[key]
    return str(event.get("name") or "Без события")


def _normalize_event_description(event: dict[str, Any] | None) -> str:
    if not isinstance(event, dict):
        return "Сервер живёт в спокойном ритме без активного глобального бонуса."
    key = str(event.get("key") or "")
    if key and key in WORLD_EVENT_DESCRIPTIONS:
        return WORLD_EVENT_DESCRIPTIONS[key]
    return str(event.get("description") or "Глобальный ивент уже влияет на серверную экономику.")


def build_world_snapshot(guild_id: int | None, active_event: dict[str, Any] | None = None, *, now: datetime | None = None) -> dict[str, Any]:
    utc_now = now.astimezone(timezone.utc) if isinstance(now, datetime) and now.tzinfo else now or datetime.now(timezone.utc)
    fishing_world = get_fishing_world_state(utc_now)
    weather = current_weather(utc_now)
    time_key = get_time_phase_key(utc_now)
    next_window = fishing_world.get("next_event_window")

    snapshot = {
        "guild_id": int(guild_id or 0),
        "now": utc_now,
        "time_phase_key": time_key,
        "time_phase_name": TIME_PHASES[time_key]["name"],
        "weather": weather,
        "active_event": active_event,
        "market_event_name": _normalize_event_name(active_event),
        "market_event_description": _normalize_event_description(active_event),
        "fishing_world": fishing_world,
        "next_window": next_window,
        "hotspot_key": fishing_world.get("hotspot_key"),
        "hotspot_name": str((fishing_world.get("hotspot") or {}).get("name") or "Неизвестно"),
    }
    snapshot["antiquary_prices"] = build_antiquary_prices(snapshot)
    return snapshot


def category_multiplier(snapshot: dict[str, Any], category: str) -> float:
    result = 1.0
    event = snapshot.get("active_event")
    if isinstance(event, dict):
        result *= float((event.get("multipliers") or {}).get(category, 1.0) or 1.0)

    weather_key = str((snapshot.get("weather") or {}).get("key") or "clear")
    result *= float(WEATHER_MULTIPLIERS.get(weather_key, {}).get(category, 1.0) or 1.0)

    time_key = str(snapshot.get("time_phase_key") or "day")
    result *= float(TIME_PHASE_MULTIPLIERS.get(time_key, {}).get(category, 1.0) or 1.0)
    return round(max(0.1, result), 4)


def build_antiquary_prices(snapshot: dict[str, Any]) -> dict[str, int]:
    now = snapshot.get("now")
    if not isinstance(now, datetime):
        now = datetime.now(timezone.utc)
    guild_id = int(snapshot.get("guild_id", 0) or 0)
    seed = int(now.strftime("%Y%m%d")) * 1009 + guild_id * 17
    rng = random.Random(seed)
    prices: dict[str, int] = {}
    for code, item in ANTIQUARY_ITEMS.items():
        base_value = int(item.get("base_value", 0) or 0)
        family = str(item.get("family") or "")
        variance = 0.90 + rng.random() * 0.25
        if family == "leviathan_sigil":
            variance += 0.05
        if str(item.get("item_type") or "") == "antiquary_relic":
            variance += 0.08
        prices[code] = max(1, int(round(base_value * variance)))
    return prices


def describe_multiplier(multiplier: float) -> str:
    if multiplier == 1.0:
        return "x1.00"
    return f"x{multiplier:.2f}"


def build_world_lines(snapshot: dict[str, Any]) -> list[str]:
    weather = snapshot.get("weather") or {}
    event = snapshot.get("active_event")
    lines = [
        f"Погода: **{weather.get('name', 'Ясно')}**",
        f"Время суток: **{snapshot.get('time_phase_name', 'День')}**",
        f"Хотспот: **{snapshot.get('hotspot_name', 'Неизвестно')}**",
    ]
    if isinstance(event, dict):
        lines.append(f"Ивент: **{_normalize_event_name(event)}**")
    else:
        lines.append("Ивент: **сейчас нет**")
    return lines


def build_event_card_payload(snapshot: dict[str, Any], *, state: str = "active") -> dict[str, Any]:
    event = snapshot.get("active_event")
    title_name = _normalize_event_name(event)
    prefix = "Ивент" if state != "ended" else "Ивент завершён"
    return {
        "title": f"{prefix} • {title_name}",
        "description": _normalize_event_description(event),
        "color": WORLD_STATUS_COLORS.get(state, COLORS["info"]),
        "status": {
            "active": "Активно",
            "soon": "Скоро",
            "ended": "Завершено",
        }.get(state, "Активно"),
    }
