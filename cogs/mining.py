from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, CRYPTO_TYPES, get_vip_level
from database import db, get_user_lock
from utils import (
    check_channel,
    check_quest_progress,
    format_discord_deadline,
    get_crypto_history,
    get_crypto_price,
    get_kyiv_timezone,
    record_player_progress,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
)

KYIV_TZ = get_kyiv_timezone()
HOUSE_PAGE_SIZE = 3
MAX_MINING_STORAGE_HOURS = 24

HOUSE_TYPES: dict[str, dict[str, Any]] = {
    "studio": {
        "name": "Дачный домик",
        "category": "Дом",
        "price": 80_000,
        "rooms": 1,
        "prestige": 1,
        "base_gpu_slots": 1,
        "rental_slots": 1,
        "max_basement_level": 2,
        "description": "Первый маленький дом для старта, аренды и базового подвала.",
    },
    "flat_one": {
        "name": "Небольшой дом",
        "category": "Дом",
        "price": 220_000,
        "rooms": 2,
        "prestige": 2,
        "base_gpu_slots": 2,
        "rental_slots": 1,
        "max_basement_level": 3,
        "description": "Уютный дом с лучшими заявками, садом и нормальным подвалом.",
    },
    "flat_two": {
        "name": "Семейный дом",
        "category": "Дом",
        "price": 520_000,
        "rooms": 3,
        "prestige": 3,
        "base_gpu_slots": 3,
        "rental_slots": 1,
        "max_basement_level": 3,
        "description": "Больше комнат, сильнее аренда и заметно полезнее подвал.",
    },
    "townhouse": {
        "name": "Таунхаус",
        "category": "Дом",
        "price": 1_250_000,
        "rooms": 4,
        "prestige": 4,
        "base_gpu_slots": 5,
        "rental_slots": 2,
        "max_basement_level": 4,
        "description": "Первый серьезный дом с двумя арендными слотами.",
    },
    "country_house": {
        "name": "Загородный дом",
        "category": "Дом",
        "price": 3_200_000,
        "rooms": 5,
        "prestige": 5,
        "base_gpu_slots": 7,
        "rental_slots": 2,
        "max_basement_level": 5,
        "description": "Большой дом для сильной аренды и жирного подвала.",
    },
    "penthouse": {
        "name": "Особняк",
        "category": "Дом",
        "price": 7_500_000,
        "rooms": 6,
        "prestige": 6,
        "base_gpu_slots": 9,
        "rental_slots": 3,
        "max_basement_level": 5,
        "description": "Топовый дом с премиальными заявками, сильной арендой и лучшим подвалом.",
    },
}

HOUSE_ORDER = list(HOUSE_TYPES.keys())
GARDEN_SLOT_LIMITS = {
    "studio": 6,
    "flat_one": 8,
    "flat_two": 10,
    "townhouse": 12,
    "country_house": 14,
    "penthouse": 16,
}

GARDEN_CROPS: dict[str, dict[str, Any]] = {
    "carrot": {"name": "Морковь", "price": 1_200, "growth_hours": 2, "yield_min": 2, "yield_max": 4, "emoji": "🥕"},
    "potato": {"name": "Картофель", "price": 1_800, "growth_hours": 3, "yield_min": 2, "yield_max": 5, "emoji": "🥔"},
    "tomato": {"name": "Помидор", "price": 2_500, "growth_hours": 4, "yield_min": 2, "yield_max": 4, "emoji": "🍅"},
    "cucumber": {"name": "Огурец", "price": 3_100, "growth_hours": 4, "yield_min": 2, "yield_max": 4, "emoji": "🥒"},
    "pumpkin": {"name": "Тыква", "price": 4_800, "growth_hours": 6, "yield_min": 1, "yield_max": 3, "emoji": "🎃"},
    "strawberry": {"name": "Клубника", "price": 5_600, "growth_hours": 5, "yield_min": 2, "yield_max": 5, "emoji": "🍓"},
}

WATERING_CANS: dict[str, dict[str, Any]] = {
    "basic": {"name": "Базовая лейка", "price": 18_000, "water_interval_hours": 8, "emoji": "🪣"},
    "metal": {"name": "Металлическая лейка", "price": 55_000, "water_interval_hours": 12, "emoji": "🚿"},
    "drip": {"name": "Капельный набор", "price": 180_000, "water_interval_hours": 24, "emoji": "💧"},
}

FURNITURE_ITEMS: dict[str, dict[str, Any]] = {
    "gaming_chair": {"name": "Геймерское кресло", "price": 120_000, "emoji": "🪑", "buff": "crypto"},
    "aquarium": {"name": "Аквариум", "price": 260_000, "emoji": "🐠", "buff": "fishing"},
    "plasma_tv": {"name": "Плазменный ТВ", "price": 410_000, "emoji": "📺", "buff": "rent"},
}

GPU_MODELS: dict[str, dict[str, Any]] = {
    "gtx_1060": {
        "name": "NVIDIA GTX 1060 6GB",
        "price": 42_000,
        "hourly_income": 130,
        "emoji": "🟩",
        "description": "Дешевая стартовая карта для маленького подвала.",
    },
    "rtx_2060": {
        "name": "NVIDIA RTX 2060 SUPER",
        "price": 112_000,
        "hourly_income": 315,
        "emoji": "🟦",
        "description": "Надёжная карта среднего уровня для первых серьёзных сборок.",
    },
    "rtx_3060_ti": {
        "name": "NVIDIA RTX 3060 Ti",
        "price": 245_000,
        "hourly_income": 650,
        "emoji": "🟪",
        "description": "Хороший баланс цены и дохода на длинной дистанции.",
    },
    "rtx_4080": {
        "name": "NVIDIA RTX 4080 SUPER",
        "price": 590_000,
        "hourly_income": 1_500,
        "emoji": "🟧",
        "description": "Топовая карта для дорогих домов и жирного фарма.",
    },
    "rtx_5090": {
        "name": "NVIDIA RTX 5090",
        "price": 1_380_000,
        "hourly_income": 3_400,
        "emoji": "💠",
        "description": "Премиум-карта для поздней игры и сильного подвала.",
    },
}

GPU_ORDER = list(GPU_MODELS.keys())

TENANT_TYPES: list[dict[str, Any]] = [
    {"name": "Студент", "description": "Снимает быстро, платит скромно, но стабильно.", "min_rooms": 1, "min_prestige": 1, "multiplier": 0.92, "durations": [6, 12]},
    {"name": "Фрилансер", "description": "Любит короткие заезды и спокойные дома.", "min_rooms": 2, "min_prestige": 1, "multiplier": 1.0, "durations": [6, 12, 24]},
    {"name": "Семья", "description": "Нуждается в комнатах и остается подольше.", "min_rooms": 3, "min_prestige": 2, "multiplier": 1.15, "durations": [12, 24]},
    {"name": "Стример", "description": "Ищет красивое место и готов платить больше обычного.", "min_rooms": 2, "min_prestige": 3, "multiplier": 1.22, "durations": [6, 12]},
    {"name": "Стартап-команда", "description": "Любит простор и длинные заезды с жирной оплатой.", "min_rooms": 4, "min_prestige": 4, "multiplier": 1.35, "durations": [12, 24]},
    {"name": "Премиум-клиент", "description": "Редкий арендатор с лучшей выплатой.", "min_rooms": 5, "min_prestige": 5, "multiplier": 1.55, "durations": [24]},
]


HOUSE_TYPES["studio"].update(
    {"name": "Дачный домик", "category": "Дом", "description": "Базовый дом для старта, первых арендаторов и маленького подвала."}
)
HOUSE_TYPES["flat_one"].update(
    {"name": "Небольшой дом", "category": "Дом", "description": "Уютный дом с лучшими заявками и уверенным подвалом."}
)
HOUSE_TYPES["flat_two"].update(
    {"name": "Семейный дом", "category": "Дом", "description": "Больше комнат, сильнее аренда и заметно полезнее подвал."}
)
HOUSE_TYPES["townhouse"].update(
    {"name": "Таунхаус", "category": "Дом", "description": "Первый серьёзный дом с двумя слотами аренды и заметным подвалом."}
)
HOUSE_TYPES["country_house"].update(
    {"name": "Загородный дом", "category": "Дом", "description": "Большой дом для жирной аренды и мощного подвала."}
)
HOUSE_TYPES["penthouse"].update(
    {"name": "Особняк", "category": "Дом", "description": "Топовый дом с премиальными заявками, сильной арендой и лучшим подвалом."}
)

GPU_MODELS["gtx_1060"].update({"description": "Бюджетная карта для первого маленького подвала."})
GPU_MODELS["rtx_2060"].update({"description": "Хороший средний уровень для стабильного дохода."})
GPU_MODELS["rtx_3060_ti"].update({"description": "Сильный баланс цены и дохода для долгой игры."})
GPU_MODELS["rtx_4080"].update({"description": "Мощная карта для дорогих домов и развитого подвала."})
GPU_MODELS["rtx_5090"].update({"description": "Топовая видеокарта для поздней игры и сильной фермы."})

TENANT_TYPES[0].update({"name": "Студент", "description": "Снимает быстро, платит скромно, но стабильно."})
TENANT_TYPES[1].update({"name": "Фрилансер", "description": "Любит короткие заезды и спокойные дома."})
TENANT_TYPES[2].update({"name": "Семья", "description": "Нуждается в комнатах и остаётся подольше."})
TENANT_TYPES[3].update({"name": "Стример", "description": "Ищет красивое место и готов платить выше обычного."})
TENANT_TYPES[4].update({"name": "Стартап-команда", "description": "Любит простор и длинные заезды с хорошей оплатой."})
TENANT_TYPES[5].update({"name": "Премиум-клиент", "description": "Редкий арендатор с лучшей выплатой."})

def format_money(value: int | float) -> str:
    return f"${int(value):,}"


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


def _house_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _system_state(user)
    house = systems.get("house")
    if not isinstance(house, dict):
        house = {}
    house.setdefault("owned_house_id", None)
    house.setdefault("basement_level", 0)
    house.setdefault("installed_gpus", [])
    house.setdefault("last_mining_collect", None)
    house.setdefault("mining_wallet", 0)
    house.setdefault("legacy_mining_wallet", 0)
    house.setdefault("mining_runs", 0)
    house.setdefault("active_rentals", [])
    house.setdefault("crypto_wallet", {symbol: 0.0 for symbol in CRYPTO_TYPES})
    house.setdefault("crypto_focus", None)
    house.setdefault("furniture", [])
    current_house_id = str(house.get("owned_house_id") or "")
    house.setdefault("max_garden_level", GARDEN_SLOT_LIMITS.get(current_house_id, 0))
    garden_state = house.get("garden")
    if not isinstance(garden_state, dict):
        garden_state = {}
    garden_state.setdefault("watering_can", "basic")
    garden_state.setdefault("plots", [])
    house["garden"] = garden_state
    accepted = house.get("accepted_offers")
    if not isinstance(accepted, dict):
        accepted = {"window": None, "keys": []}
    accepted.setdefault("window", None)
    accepted.setdefault("keys", [])
    house["accepted_offers"] = accepted
    for symbol in CRYPTO_TYPES:
        house["crypto_wallet"].setdefault(symbol, 0.0)
    if current_house_id:
        house["max_garden_level"] = GARDEN_SLOT_LIMITS.get(current_house_id, int(house.get("max_garden_level", 0) or 0))
    systems["house"] = house
    return house


def _parse_utc(raw_value: str | None, fallback: datetime) -> datetime:
    if not raw_value:
        return fallback
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return fallback
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _house_vip_bonus(user: dict[str, Any]) -> dict[str, Any]:
    vip_level = int(user.get("vip_level", 0) or 0)
    vip = get_vip_level(vip_level)
    bonus = {"extra_gpu_slots": 0, "extra_rental_slots": 0, "mining_bonus": 0.0, "rent_bonus": 0.0, "upgrade_discount": 0.0}
    if vip_level >= 1:
        bonus["mining_bonus"] += 0.04
    if vip_level >= 2:
        bonus["extra_gpu_slots"] += 1
        bonus["rent_bonus"] += 0.04
        bonus["upgrade_discount"] += 0.05
    if vip_level >= 3:
        bonus["extra_rental_slots"] += 1
        bonus["mining_bonus"] += 0.06
    if vip_level >= 4:
        bonus["extra_gpu_slots"] += 1
        bonus["rent_bonus"] += 0.08
        bonus["upgrade_discount"] += 0.05
    bonus["vip_name"] = vip["name"]
    return bonus


def _house_current_data(house_state: dict[str, Any]) -> dict[str, Any] | None:
    house_id = str(house_state.get("owned_house_id") or "")
    return HOUSE_TYPES.get(house_id)


def _house_index(house_id: str | None) -> int:
    if house_id in HOUSE_ORDER:
        return HOUSE_ORDER.index(str(house_id))
    return -1


def _house_basement_capacity(house_data: dict[str, Any], basement_level: int, vip_bonus: dict[str, Any]) -> int:
    effective_level = max(1, basement_level)
    return int(house_data["base_gpu_slots"]) + max(0, effective_level - 1) * 2 + int(vip_bonus["extra_gpu_slots"])


def _house_rental_capacity(house_data: dict[str, Any], vip_bonus: dict[str, Any]) -> int:
    return int(house_data["rental_slots"]) + int(vip_bonus["extra_rental_slots"])


def _house_basement_upgrade_cost(house_data: dict[str, Any], current_level: int, vip_bonus: dict[str, Any]) -> int:
    base_cost = int(house_data["price"] * (0.18 + current_level * 0.08))
    return max(35_000, int(base_cost * (1 - float(vip_bonus["upgrade_discount"]))))


def _rental_window_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    kyiv_now = now.astimezone(KYIV_TZ)
    hour_bucket = (kyiv_now.hour // 6) * 6
    return kyiv_now.replace(hour=hour_bucket, minute=0, second=0, microsecond=0)


def _current_market_rows() -> tuple[list[dict[str, Any]], float]:
    rows: list[dict[str, Any]] = []
    ratios: list[float] = []
    for symbol, crypto in CRYPTO_TYPES.items():
        history = get_crypto_history(symbol, 2)
        current_price = history[-1]
        previous_price = history[0] if history else current_price
        change_amount = current_price - previous_price
        change_percent = (change_amount / previous_price * 100) if previous_price else 0
        rows.append({"symbol": symbol, "name": crypto["name"], "emoji": crypto["emoji"], "current_price": current_price, "change_amount": change_amount, "change_percent": change_percent})
        ratios.append(current_price / float(crypto["base_price"]))
    market_factor = max(0.72, min(1.35, sum(ratios) / max(1, len(ratios))))
    return rows, market_factor


def _gpu_entry_id(entry: Any) -> str:
    if isinstance(entry, dict):
        raw_value = entry.get("gpu_id", entry.get("id"))
    else:
        raw_value = entry
    return str(raw_value or "")


def _gpu_entry_buy_price(entry: Any) -> int:
    if isinstance(entry, dict):
        try:
            return int(entry.get("buy_price", 0) or 0)
        except (TypeError, ValueError):
            return 0
    gpu_id = _gpu_entry_id(entry)
    return int(GPU_MODELS.get(gpu_id, {}).get("price", 0) or 0)


def _gpu_entry_resale_price(entry: Any) -> int:
    buy_price = _gpu_entry_buy_price(entry)
    if buy_price <= 0:
        return 0
    return max(1, int(round(buy_price * 0.30)))


def _gpu_breakdown(installed_gpus: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in installed_gpus:
        gpu_id = _gpu_entry_id(entry)
        if gpu_id not in GPU_MODELS:
            continue
        counts[gpu_id] = counts.get(gpu_id, 0) + 1
    return counts


class HouseView(discord.ui.View):
    def __init__(self, cog: "HouseCog", user_id: int, guild_id: int, *, tab: str = "house", house_page: int = 0, entry_mode: str | None = None):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.tab = tab
        self.house_page = house_page
        self.entry_mode = entry_mode or ("shop" if tab == "shop" else "house")
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню дома открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _show_new_view(self, interaction: discord.Interaction, view: "HouseView"):
        embed = await view.render_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        await view._remember_message(interaction)

    async def render_embed(self) -> discord.Embed:
        if self.tab == "shop":
            return await self.cog.build_house_shop_embed(self.user_id, self.guild_id, self.house_page)
        if self.tab == "rent":
            return await self.cog.build_rental_embed(self.user_id, self.guild_id)
        if self.tab == "basement":
            return await self.cog.build_basement_embed(self.user_id, self.guild_id)
        if self.tab == "gpus":
            return await self.cog.build_gpu_embed(self.user_id, self.guild_id)
        return await self.cog.build_house_embed(self.user_id, self.guild_id, self.house_page)

    def _add_nav_button(self, label: str, target_tab: str):
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary if self.tab == target_tab else discord.ButtonStyle.secondary,
            row=0,
        )

        async def callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab=target_tab, house_page=self.house_page, entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)

        button.callback = callback
        self.add_item(button)

    def _add_action_button(self, label: str, style: discord.ButtonStyle, row: int, callback, *, disabled: bool = False):
        button = discord.ui.Button(label=label, style=style, row=row, disabled=disabled)
        button.callback = callback
        self.add_item(button)

    def _build(self):
        self._add_nav_button("Магазин", "shop")
        self._add_nav_button("Дом", "house")
        self._add_nav_button("Аренда", "rent")
        self._add_nav_button("Подвал", "basement")
        self._add_nav_button("Видеокарты", "gpus")

        if self.tab == "house":
            self._build_house_buttons()
        elif self.tab == "shop":
            self._build_shop_buttons()
        elif self.tab == "rent":
            self._build_rent_buttons()
        elif self.tab == "basement":
            self._build_basement_buttons()
        elif self.tab == "gpus":
            self._build_gpu_buttons()

    def _build_house_buttons(self):
        async def open_shop(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=self.house_page)
                await self._show_new_view(interaction, view)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="house", house_page=self.house_page)
                await self._show_new_view(interaction, view)

        self._add_action_button("Магазин домов", discord.ButtonStyle.primary, 1, open_shop)
        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 1, refresh)
        return

        async def prev_page(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                new_page = max(0, self.house_page - 1)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="house", house_page=new_page)
                await self._show_new_view(interaction, view)

        async def next_page(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                new_page = min(self.cog.max_house_page(), self.house_page + 1)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="house", house_page=new_page)
                await self._show_new_view(interaction, view)

        self._add_action_button("Назад", discord.ButtonStyle.secondary, 1, prev_page, disabled=self.house_page <= 0)

        visible_houses = self.cog.visible_houses(self.house_page)
        for slot in range(HOUSE_PAGE_SIZE):
            if slot >= len(visible_houses):
                self._add_action_button("Нет дома", discord.ButtonStyle.secondary, 1, prev_page, disabled=True)
                continue

            house_id = visible_houses[slot]

            async def buy_house_callback(interaction: discord.Interaction, target_house_id: str = house_id):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.buy_house(self.user_id, self.guild_id, target_house_id)
                    view = HouseView(self.cog, self.user_id, self.guild_id, tab="house", house_page=self.house_page)
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Купить #{slot + 1}", discord.ButtonStyle.success, 1, buy_house_callback)

        self._add_action_button("Дальше", discord.ButtonStyle.secondary, 1, next_page, disabled=self.house_page >= self.cog.max_house_page())

    def _build(self):
        if self.entry_mode == "shop":
            self._add_nav_button("Магазин", "shop")
        else:
            self._add_nav_button("Дом", "house")
            self._add_nav_button("Аренда", "rent")
            self._add_nav_button("Подвал", "basement")
            self._add_nav_button("Видеокарты", "gpus")

        if self.tab == "house":
            self._build_house_buttons()
        elif self.tab == "shop":
            self._build_shop_buttons()
        elif self.tab == "rent":
            self._build_rent_buttons()
        elif self.tab == "basement":
            self._build_basement_buttons()
        elif self.tab == "gpus":
            self._build_gpu_buttons()

    def _build_house_buttons(self):
        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="house", house_page=self.house_page, entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)

        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 1, refresh)

    def _build_shop_buttons(self):
        async def prev_page(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                new_page = max(0, self.house_page - 1)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=new_page)
                await self._show_new_view(interaction, view)

        async def next_page(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                new_page = min(self.cog.max_house_page(), self.house_page + 1)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=new_page)
                await self._show_new_view(interaction, view)

        self._add_action_button("Назад", discord.ButtonStyle.secondary, 1, prev_page, disabled=self.house_page <= 0)

        visible_houses = self.cog.visible_houses(self.house_page)
        for slot in range(HOUSE_PAGE_SIZE):
            if slot >= len(visible_houses):
                self._add_action_button("Нет дома", discord.ButtonStyle.secondary, 1, prev_page, disabled=True)
                continue

            house_id = visible_houses[slot]

            async def buy_house_callback(interaction: discord.Interaction, target_house_id: str = house_id):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.buy_house(self.user_id, self.guild_id, target_house_id)
                    view = HouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=self.house_page)
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Купить #{slot + 1}", discord.ButtonStyle.success, 1, buy_house_callback)

        self._add_action_button("Дальше", discord.ButtonStyle.secondary, 1, next_page, disabled=self.house_page >= self.cog.max_house_page())

    def _build_rent_buttons(self):
        for slot in range(3):
            async def take_offer_callback(interaction: discord.Interaction, offer_index: int = slot):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.accept_rental_offer(self.user_id, self.guild_id, offer_index)
                    view = HouseView(self.cog, self.user_id, self.guild_id, tab="rent")
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Взять #{slot + 1}", discord.ButtonStyle.primary, 1, take_offer_callback)

        async def collect_rent(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                _, payload = await self.cog.collect_rent(self.user_id, self.guild_id)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="rent")
                await self._show_new_view(interaction, view)
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="rent")
                await self._show_new_view(interaction, view)

        self._add_action_button("Собрать аренду", discord.ButtonStyle.success, 2, collect_rent)
        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 2, refresh)

    def _build_basement_buttons(self):
        async def collect_mining(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                _, payload = await self.cog.collect_mining(self.user_id, self.guild_id)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="basement")
                await self._show_new_view(interaction, view)
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

        async def upgrade_basement(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                _, payload = await self.cog.upgrade_basement(self.user_id, self.guild_id)
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="basement")
                await self._show_new_view(interaction, view)
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="basement")
                await self._show_new_view(interaction, view)

        self._add_action_button("Собрать", discord.ButtonStyle.success, 1, collect_mining)
        self._add_action_button("Улучшить подвал", discord.ButtonStyle.primary, 1, upgrade_basement)
        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 1, refresh)

    def _build_gpu_buttons(self):
        for slot, gpu_id in enumerate(GPU_ORDER):
            async def buy_gpu_callback(interaction: discord.Interaction, target_gpu_id: str = gpu_id):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.buy_gpu(self.user_id, self.guild_id, target_gpu_id)
                    view = HouseView(self.cog, self.user_id, self.guild_id, tab="gpus")
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Купить #{slot + 1}", discord.ButtonStyle.success, 1, buy_gpu_callback)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = HouseView(self.cog, self.user_id, self.guild_id, tab="gpus")
                await self._show_new_view(interaction, view)

        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 2, refresh)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message, delay_seconds=0)


class CleanHouseView(discord.ui.View):
    def __init__(self, cog: "HouseCog", user_id: int, guild_id: int, *, tab: str = "house", house_page: int = 0, entry_mode: str | None = None):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.tab = tab
        self.house_page = house_page
        self.entry_mode = entry_mode or ("shop" if tab == "shop" else "house")
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню дома открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _show_new_view(self, interaction: discord.Interaction, view: "CleanHouseView"):
        embed = await view.render_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        await view._remember_message(interaction)

    async def render_embed(self) -> discord.Embed:
        if self.tab == "shop":
            return await self.cog.build_house_shop_embed(self.user_id, self.guild_id, self.house_page)
        if self.tab == "rent":
            return await self.cog.build_rental_embed(self.user_id, self.guild_id)
        if self.tab == "basement":
            return await self.cog.build_basement_embed(self.user_id, self.guild_id)
        if self.tab == "gpus":
            return await self.cog.build_gpu_embed(self.user_id, self.guild_id)
        return await self.cog.build_house_embed(self.user_id, self.guild_id, self.house_page)

    def _add_nav_button(self, label: str, target_tab: str):
        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.primary if self.tab == target_tab else discord.ButtonStyle.secondary,
            row=0,
        )

        async def callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(
                    self.cog,
                    self.user_id,
                    self.guild_id,
                    tab=target_tab,
                    house_page=self.house_page,
                    entry_mode=self.entry_mode,
                )
                await self._show_new_view(interaction, view)

        button.callback = callback
        self.add_item(button)

    def _add_action_button(self, label: str, style: discord.ButtonStyle, row: int, callback, *, disabled: bool = False):
        button = discord.ui.Button(label=label, style=style, row=row, disabled=disabled)
        button.callback = callback
        self.add_item(button)

    def _build(self):
        if self.entry_mode == "shop":
            self._add_nav_button("Магазин домов", "shop")
        else:
            self._add_nav_button("Дом", "house")
            self._add_nav_button("Аренда", "rent")
            self._add_nav_button("Подвал", "basement")
            self._add_nav_button("Видеокарты", "gpus")

        if self.tab == "house":
            self._build_house_buttons()
        elif self.tab == "shop":
            self._build_shop_buttons()
        elif self.tab == "rent":
            self._build_rent_buttons()
        elif self.tab == "basement":
            self._build_basement_buttons()
        elif self.tab == "gpus":
            self._build_gpu_buttons()

    def _build_house_buttons(self):
        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="house", house_page=self.house_page, entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)

        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 1, refresh)

    def _build_shop_buttons(self):
        async def prev_page(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=max(0, self.house_page - 1), entry_mode="shop")
                await self._show_new_view(interaction, view)

        async def next_page(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(
                    self.cog,
                    self.user_id,
                    self.guild_id,
                    tab="shop",
                    house_page=min(self.cog.max_house_page(), self.house_page + 1),
                    entry_mode="shop",
                )
                await self._show_new_view(interaction, view)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=self.house_page, entry_mode="shop")
                await self._show_new_view(interaction, view)

        self._add_action_button("Назад", discord.ButtonStyle.secondary, 1, prev_page, disabled=self.house_page <= 0)

        visible_houses = self.cog.visible_houses(self.house_page)
        for slot in range(HOUSE_PAGE_SIZE):
            if slot >= len(visible_houses):
                self._add_action_button("Нет дома", discord.ButtonStyle.secondary, 1, prev_page, disabled=True)
                continue

            house_id = visible_houses[slot]

            async def buy_house_callback(interaction: discord.Interaction, target_house_id: str = house_id):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.buy_house(self.user_id, self.guild_id, target_house_id)
                    view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="shop", house_page=self.house_page, entry_mode="shop")
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Купить #{slot + 1}", discord.ButtonStyle.success, 1, buy_house_callback)

        self._add_action_button("Дальше", discord.ButtonStyle.secondary, 1, next_page, disabled=self.house_page >= self.cog.max_house_page())
        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 2, refresh)

    def _build_rent_buttons(self):
        for slot in range(3):
            async def take_offer_callback(interaction: discord.Interaction, offer_index: int = slot):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.accept_rental_offer(self.user_id, self.guild_id, offer_index)
                    view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="rent", entry_mode=self.entry_mode)
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Взять #{slot + 1}", discord.ButtonStyle.primary, 1, take_offer_callback)

        async def collect_rent(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                _, payload = await self.cog.collect_rent(self.user_id, self.guild_id)
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="rent", entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="rent", entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)

        self._add_action_button("Собрать аренду", discord.ButtonStyle.success, 2, collect_rent)
        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 2, refresh)

    def _build_basement_buttons(self):
        async def collect_mining(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                _, payload = await self.cog.collect_mining(self.user_id, self.guild_id)
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="basement", entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

        async def upgrade_basement(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                _, payload = await self.cog.upgrade_basement(self.user_id, self.guild_id)
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="basement", entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="basement", entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)

        self._add_action_button("Собрать", discord.ButtonStyle.success, 1, collect_mining)
        self._add_action_button("Улучшить подвал", discord.ButtonStyle.primary, 1, upgrade_basement)
        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 1, refresh)

    def _build_gpu_buttons(self):
        for slot, gpu_id in enumerate(GPU_ORDER):
            async def buy_gpu_callback(interaction: discord.Interaction, target_gpu_id: str = gpu_id):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.buy_gpu(self.user_id, self.guild_id, target_gpu_id)
                    view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="gpus", entry_mode=self.entry_mode)
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Купить #{slot + 1}", discord.ButtonStyle.success, 1, buy_gpu_callback)

            async def sell_gpu_callback(interaction: discord.Interaction, target_gpu_id: str = gpu_id):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    _, payload = await self.cog.sell_gpu(self.user_id, self.guild_id, target_gpu_id)
                    view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="gpus", entry_mode=self.entry_mode)
                    await self._show_new_view(interaction, view)
                    if isinstance(payload, discord.Embed):
                        await interaction.followup.send(embed=payload, ephemeral=True)
                    else:
                        await interaction.followup.send(str(payload), ephemeral=True)

            self._add_action_button(f"Продать #{slot + 1}", discord.ButtonStyle.secondary, 2, sell_gpu_callback)

        async def refresh(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                view = CleanHouseView(self.cog, self.user_id, self.guild_id, tab="gpus", entry_mode=self.entry_mode)
                await self._show_new_view(interaction, view)

        self._add_action_button("Обновить", discord.ButtonStyle.secondary, 3, refresh)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message, delay_seconds=0)


HouseView = CleanHouseView


class HouseCog(commands.Cog, name="House"):
    def __init__(self, bot):
        self.bot = bot

    def max_house_page(self) -> int:
        return max(0, (len(HOUSE_ORDER) - 1) // HOUSE_PAGE_SIZE)

    def visible_houses(self, page: int) -> list[str]:
        start = max(0, page) * HOUSE_PAGE_SIZE
        return HOUSE_ORDER[start:start + HOUSE_PAGE_SIZE]

    def _systems_cog(self):
        return self.bot.get_cog("Systems")

    def _market_multiplier(self, guild_id: int | None, category: str) -> tuple[float, dict[str, Any] | None]:
        systems_cog = self._systems_cog()
        if systems_cog is None:
            return 1.0, None
        return systems_cog.get_reward_multiplier(guild_id, category)

    def _house_snapshot(self, user: dict[str, Any], guild_id: int | None) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        house_state = _house_state(user)
        house_data = _house_current_data(house_state)
        vip_bonus = _house_vip_bonus(user)

        if not house_data:
            return {
                "house_state": house_state,
                "house_data": None,
                "vip_bonus": vip_bonus,
                "basement_level": 0,
                "capacity": 0,
                "installed_count": 0,
                "hourly_income": 0,
                "wallet": int(house_state.get("mining_wallet", 0) or 0),
                "accrued": 0,
                "ready": int(house_state.get("mining_wallet", 0) or 0),
                "market_rows": [],
                "market_factor": 1.0,
                "event": None,
                "event_multiplier": 1.0,
                "next_cap_at": now,
            }

        basement_level = max(1, min(int(house_state.get("basement_level", 1) or 1), int(house_data["max_basement_level"])))
        installed_gpu_entries = list(house_state.get("installed_gpus", []))
        installed_gpus = [
            gpu_id for gpu_id in (_gpu_entry_id(entry) for entry in installed_gpu_entries)
            if gpu_id in GPU_MODELS
        ]
        market_rows, market_factor = _current_market_rows()
        event_multiplier, event = self._market_multiplier(guild_id, "mine")
        base_hourly = sum(int(GPU_MODELS[gpu_id]["hourly_income"]) for gpu_id in installed_gpus)
        efficiency = 1 + (basement_level - 1) * 0.12
        vip_factor = 1 + float(vip_bonus["mining_bonus"])
        hourly_income = int(base_hourly * efficiency * market_factor * event_multiplier * vip_factor)
        last_collect = _parse_utc(str(house_state.get("last_mining_collect") or ""), now)
        elapsed_hours = max(0.0, (now - last_collect).total_seconds() / 3600)
        capped_hours = min(MAX_MINING_STORAGE_HOURS, elapsed_hours)
        accrued = int(hourly_income * capped_hours)
        wallet = int(house_state.get("mining_wallet", 0) or 0)
        capacity = _house_basement_capacity(house_data, basement_level, vip_bonus)
        return {
            "house_state": house_state,
            "house_data": house_data,
            "vip_bonus": vip_bonus,
            "basement_level": basement_level,
            "capacity": capacity,
            "installed_count": len(installed_gpus),
            "hourly_income": hourly_income,
            "wallet": wallet,
            "accrued": accrued,
            "ready": wallet + accrued,
            "market_rows": market_rows,
            "market_factor": market_factor,
            "event": event,
            "event_multiplier": event_multiplier,
            "next_cap_at": last_collect + timedelta(hours=MAX_MINING_STORAGE_HOURS),
        }

    def _sync_mining_wallet(self, user: dict[str, Any], guild_id: int | None) -> dict[str, Any]:
        snapshot = self._house_snapshot(user, guild_id)
        if not snapshot["house_data"]:
            return snapshot
        house_state = snapshot["house_state"]
        house_state["mining_wallet"] = snapshot["ready"]
        house_state["last_mining_collect"] = datetime.now(timezone.utc).isoformat()
        return snapshot

    def _generate_rental_offers(self, user: dict[str, Any], house_state: dict[str, Any], house_data: dict[str, Any]) -> tuple[str, datetime, list[dict[str, Any]], set[str]]:
        now = datetime.now(timezone.utc)
        window_start = _rental_window_start(now)
        window_key = window_start.isoformat()
        next_refresh_at = window_start + timedelta(hours=6)
        accepted_state = house_state.get("accepted_offers", {"window": None, "keys": []})
        if accepted_state.get("window") != window_key:
            accepted_state = {"window": window_key, "keys": []}
            house_state["accepted_offers"] = accepted_state
        accepted_keys = set(accepted_state.get("keys", []))

        eligible = [
            tenant
            for tenant in TENANT_TYPES
            if int(tenant["min_rooms"]) <= int(house_data["rooms"]) and int(tenant["min_prestige"]) <= int(house_data["prestige"])
        ]
        if not eligible:
            eligible = TENANT_TYPES[:2]

        rng = random.Random(f"{int(user.get('user_id', 0) or 0)}:{house_state.get('owned_house_id')}:{window_key}")
        offers: list[dict[str, Any]] = []
        for index in range(3):
            tenant = rng.choice(eligible)
            duration_hours = rng.choice(list(tenant["durations"]))
            duration_factor = {6: 1.0, 12: 1.85, 24: 3.9}[duration_hours]
            payout = int(
                house_data["price"]
                * 0.018
                * duration_factor
                * float(tenant["multiplier"])
                * rng.uniform(0.94, 1.16)
            )
            offer_id = f"{window_key}:{tenant['name']}:{duration_hours}:{index}"
            offers.append(
                {
                    "id": offer_id,
                    "tenant_name": tenant["name"],
                    "description": tenant["description"],
                    "duration_hours": duration_hours,
                    "payout": payout,
                    "next_refresh_at": next_refresh_at,
                }
            )
        return window_key, next_refresh_at, offers, accepted_keys

    def _rental_status(self, user: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        house_state = _house_state(user)
        active_rentals = house_state.get("active_rentals", [])
        ready_rentals = []
        ongoing_rentals = []
        for rental in active_rentals:
            ends_at = _parse_utc(str(rental.get("ends_at") or ""), now)
            if ends_at <= now:
                ready_rentals.append(rental)
            else:
                ongoing_rentals.append(rental)
        return {
            "ready_rentals": ready_rentals,
            "ongoing_rentals": ongoing_rentals,
            "ready_total": sum(int(rental.get("payout", 0) or 0) for rental in ready_rentals),
        }

    async def build_house_embed(self, user_id: int, guild_id: int, page: int = 0) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            user = {"balance": 0, "vip_level": 0, "game_stats": {}}
        snapshot = self._house_snapshot(user, guild_id)
        house_data = snapshot["house_data"]
        vip_bonus = snapshot["vip_bonus"]
        rental_state = self._rental_status(user)

        embed = discord.Embed(title="Дом", color=COLORS["info"])
        if house_data is None:
            embed.description = "У тебя пока нет дома. Используй `/shop`, чтобы посмотреть недвижимость и купить первый дом."
            embed.add_field(
                name="Что откроется после покупки",
                value=(
                    "Аренда для пассивного дохода\n"
                    "Подвал с апгрейдами и майнингом\n"
                    "Установка видеокарт и сбор дохода"
                ),
                inline=False,
            )
        else:
            embed.description = f"**{house_data['name']}**\n{house_data['description']}"
            embed.add_field(
                name="Текущий дом",
                value=(
                    f"Категория: **{house_data['category']}**\n"
                    f"Комнаты: **{house_data['rooms']}**\n"
                    f"Престиж: **{house_data['prestige']}**\n"
                    f"Подвал: **{snapshot['basement_level']}/{house_data['max_basement_level']}**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Доход и слоты",
                value=(
                    f"Аренда: **{_house_rental_capacity(house_data, vip_bonus)} слота**\n"
                    f"GPU: **{snapshot['installed_count']}/{snapshot['capacity']}**\n"
                    f"Майнинг: **{format_money(snapshot['hourly_income'])}/ч**\n"
                    f"Готово к сбору: **{format_money(snapshot['ready'])}**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Быстрый обзор",
                value=(
                    f"Готово по аренде: **{format_money(rental_state['ready_total'])}**\n"
                    "Покупка новых домов вынесена в `/shop` → `Недвижимость`."
                ),
                inline=False,
            )

        embed.add_field(
            name="VIP бонусы дома",
            value=(
                f"Доп. GPU слоты: **+{vip_bonus['extra_gpu_slots']}**\n"
                f"Доп. аренда: **+{vip_bonus['extra_rental_slots']} слот**\n"
                f"Майнинг: **+{int(vip_bonus['mining_bonus'] * 100)}%**\n"
                f"Скидка на подвал: **-{int(vip_bonus['upgrade_discount'] * 100)}%**"
            ),
            inline=False,
        )
        embed.set_footer(text="Здесь отображается только твой дом. Покупка новых домов перенесена в `/shop` → `Недвижимость`.")
        return embed

        user = await db.get_user(user_id, guild_id)
        if not user:
            user = {"balance": 0, "vip_level": 0, "game_stats": {}}
        snapshot = self._house_snapshot(user, guild_id)
        house_data = snapshot["house_data"]
        vip_bonus = snapshot["vip_bonus"]
        rental_state = self._rental_status(user)

        embed = discord.Embed(title="🏠 Дом", color=COLORS["info"])
        if house_data is None:
            embed.description = "У тебя пока нет недвижимости. Купи первый дом ниже и открой аренду и подвал."
        else:
            embed.description = f"**{house_data['name']}** • `{house_data['category']}`\n{house_data['description']}"
            embed.add_field(
                name="Текущий дом",
                value=(
                    f"Комнаты: **{house_data['rooms']}**\n"
                    f"Престиж: **{house_data['prestige']}**\n"
                    f"Слоты аренды: **{_house_rental_capacity(house_data, vip_bonus)}**\n"
                    f"Подвал: **{snapshot['basement_level']}/{house_data['max_basement_level']}**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Пассивка дома",
                value=(
                    f"GPU: **{snapshot['installed_count']}/{snapshot['capacity']}**\n"
                    f"Доход подвала: **{format_money(snapshot['hourly_income'])}/ч**\n"
                    f"Готово в подвале: **{format_money(snapshot['ready'])}**\n"
                    f"Готово по аренде: **{format_money(rental_state['ready_total'])}**"
                ),
                inline=True,
            )

        current_house_id = _house_state(user).get("owned_house_id")
        current_index = _house_index(current_house_id)
        balance = int(user.get("balance", 0) or 0)
        market_lines = []
        for index, house_id in enumerate(self.visible_houses(page), start=1):
            item = HOUSE_TYPES[house_id]
            item_index = _house_index(house_id)
            if house_id == current_house_id:
                status = "✅ Твой дом"
            elif current_index >= 0 and item_index <= current_index:
                status = "🔒 Уже пройдено"
            elif balance >= item["price"]:
                status = "🛒 Можно купить"
            else:
                status = f"💸 Не хватает {format_money(item['price'] - balance)}"
            market_lines.append(
                f"**{index}. {item['name']}**\n"
                f"`{item['category']}` Комнат: **{item['rooms']}** • Подвал: **до {item['max_basement_level']} ур.**\n"
                f"Цена: **{format_money(item['price'])}** • Статус: **{status}**"
            )
        embed.add_field(name=f"Рынок домов • страница {page + 1}/{self.max_house_page() + 1}", value="\n\n".join(market_lines), inline=False)
        embed.add_field(
            name="VIP бонусы для дома",
            value=(
                f"Доп. GPU слоты: **+{vip_bonus['extra_gpu_slots']}**\n"
                f"Доп. аренда: **+{vip_bonus['extra_rental_slots']} слот**\n"
                f"Майнинг: **+{int(vip_bonus['mining_bonus'] * 100)}%**\n"
                f"Скидка на подвал: **-{int(vip_bonus['upgrade_discount'] * 100)}%**"
            ),
            inline=False,
        )
        embed.set_footer(text="Кнопками ниже можно купить дом, открыть аренду, подвал и видеокарты.")
        return embed

    async def build_house_shop_embed(self, user_id: int, guild_id: int, page: int = 0) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            user = {"balance": 0, "vip_level": 0, "game_stats": {}}

        current_house_id = _house_state(user).get("owned_house_id")
        current_index = _house_index(current_house_id)
        balance = int(user.get("balance", 0) or 0)
        current_house_name = HOUSE_TYPES[current_house_id]["name"] if current_house_id in HOUSE_TYPES else "Пока нет"

        embed = discord.Embed(
            title="Магазин домов",
            description=(
                f"Баланс: **{format_money(balance)}**\n"
                f"Текущий дом: **{current_house_name}**"
            ),
            color=COLORS["info"],
        )

        market_lines = []
        for index, house_id in enumerate(self.visible_houses(page), start=1):
            item = HOUSE_TYPES[house_id]
            item_index = _house_index(house_id)
            if house_id == current_house_id:
                status = "Уже куплен"
            elif current_index >= 0 and item_index <= current_index:
                status = "Уровень уже пройден"
            elif balance >= item["price"]:
                status = "Можно купить"
            else:
                status = f"Не хватает {format_money(item['price'] - balance)}"
            market_lines.append(
                f"**{index}. {item['name']}**\n"
                f"{item['description']}\n"
                f"Категория: **{item['category']}** | Комнаты: **{item['rooms']}** | Престиж: **{item['prestige']}**\n"
                f"Подвал: **до {item['max_basement_level']} ур.** | Аренда: **{item['rental_slots']} слот**\n"
                f"Цена: **{format_money(item['price'])}** | Статус: **{status}**"
            )

        embed.add_field(
            name=f"Дома в продаже • страница {page + 1}/{self.max_house_page() + 1}",
            value="\n\n".join(market_lines) or "Сейчас нет доступных домов.",
            inline=False,
        )
        embed.set_footer(text="Покупка домов происходит здесь. Личный экран дома открывается через `/house`.")
        return embed

    async def build_rental_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            user = {"balance": 0, "vip_level": 0, "game_stats": {}}
        house_state = _house_state(user)
        house_data = _house_current_data(house_state)
        embed = discord.Embed(title="🏘 Аренда", color=COLORS["success"])
        if house_data is None:
            embed.description = "Сначала купи дом во вкладке `Дом`, чтобы получать заявки на аренду."
            return embed

        vip_bonus = _house_vip_bonus(user)
        _, next_refresh_at, offers, accepted_keys = self._generate_rental_offers(user, house_state, house_data)
        rental_state = self._rental_status(user)
        capacity = _house_rental_capacity(house_data, vip_bonus)

        embed.description = (
            f"**{house_data['name']}** • активных аренд: **{len(rental_state['ongoing_rentals'])}/{capacity}**\n"
            f"Новые запросы появятся {format_discord_deadline(next_refresh_at)}."
        )
        embed.add_field(
            name="Готово к сбору",
            value=f"Заявок: **{len(rental_state['ready_rentals'])}**\nДоход: **{format_money(rental_state['ready_total'])}**",
            inline=True,
        )
        ongoing_lines = []
        for rental in rental_state["ongoing_rentals"][:3]:
            ongoing_lines.append(
                f"**{rental['tenant_name']}** • {rental['duration_hours']}ч\n"
                f"Выплата: **{format_money(rental['payout'])}**\n"
                f"Освободится {format_discord_deadline(rental['ends_at'])}"
            )
        embed.add_field(name="Активные аренды", value="\n\n".join(ongoing_lines) or "Свободно. Можно брать новые заявки.", inline=True)

        offer_lines = []
        for index, offer in enumerate(offers, start=1):
            if offer["id"] in accepted_keys:
                status = "✅ Уже взято"
            elif len(rental_state["ongoing_rentals"]) >= capacity:
                status = "🚫 Нет свободных слотов"
            else:
                status = "🛎 Можно взять"
            payout = int(offer["payout"] * (1 + vip_bonus["rent_bonus"]))
            offer_lines.append(
                f"**{index}. {offer['tenant_name']}**\n"
                f"{offer['description']}\n"
                f"Срок: **{offer['duration_hours']}ч** • Выплата: **{format_money(payout)}**\n"
                f"Статус: **{status}**"
            )
        embed.add_field(name="Заявки на аренду", value="\n\n".join(offer_lines), inline=False)
        embed.set_footer(text="Кнопками ниже можно взять одну из трёх заявок или собрать готовую аренду.")
        return embed

    async def build_basement_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            user = {"balance": 0, "vip_level": 0, "game_stats": {}}
        snapshot = self._house_snapshot(user, guild_id)
        house_data = snapshot["house_data"]
        embed = discord.Embed(title="🧱 Подвал", color=COLORS["warning"])
        if house_data is None:
            embed.description = "Без дома подвал недоступен. Сначала купи недвижимость."
            return embed

        vip_bonus = snapshot["vip_bonus"]
        next_upgrade_cost = (
            _house_basement_upgrade_cost(house_data, snapshot["basement_level"], vip_bonus)
            if snapshot["basement_level"] < house_data["max_basement_level"]
            else None
        )
        embed.description = (
            f"**{house_data['name']}** • подвал **{snapshot['basement_level']}/{house_data['max_basement_level']}**\n"
            f"Доход накапливается до **{MAX_MINING_STORAGE_HOURS}ч**."
        )
        embed.add_field(
            name="Стата подвала",
            value=(
                f"GPU слоты: **{snapshot['installed_count']}/{snapshot['capacity']}**\n"
                f"Доход: **{format_money(snapshot['hourly_income'])}/ч**\n"
                f"Готово к сбору: **{format_money(snapshot['ready'])}**\n"
                f"Буфер заполнится {format_discord_deadline(snapshot['next_cap_at'])}"
            ),
            inline=False,
        )
        if next_upgrade_cost is not None:
            embed.add_field(name="Следующий апгрейд", value=f"Цена: **{format_money(next_upgrade_cost)}**", inline=True)
        else:
            embed.add_field(name="Следующий апгрейд", value="Подвал уже на максимальном уровне для этого дома.", inline=True)
        if snapshot["event"] is not None:
            embed.add_field(
                name="Событие рынка",
                value=f"Сейчас действует **{snapshot['event']['name']}**.\nБонус события уже учтен в доходе.",
                inline=True,
            )

        market_lines = []
        for row in snapshot["market_rows"]:
            arrow = "📈" if row["change_amount"] >= 0 else "📉"
            market_lines.append(f"{row['emoji']} **{row['symbol']}**: `${row['current_price']:,.2f}` {arrow} `{row['change_percent']:+.1f}%`")
        embed.add_field(name="Курс крипты", value="\n".join(market_lines), inline=False)
        embed.set_footer(text="Сбор дохода и апгрейд подвала доступны кнопками ниже.")
        return embed

    async def build_gpu_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            user = {"balance": 0, "vip_level": 0, "game_stats": {}}
        snapshot = self._house_snapshot(user, guild_id)
        house_data = snapshot["house_data"]
        embed = discord.Embed(title="🖥 Видеокарты", color=COLORS["purple"])
        if house_data is None:
            embed.description = "Сначала купи дом, чтобы ставить видеокарты в подвал."
            return embed

        installed_entries = [
            entry for entry in snapshot["house_state"].get("installed_gpus", [])
            if _gpu_entry_id(entry) in GPU_MODELS
        ]
        installed_counts = _gpu_breakdown(installed_entries)
        resale_by_gpu: dict[str, int] = {}
        for entry in installed_entries:
            gpu_id = _gpu_entry_id(entry)
            resale_by_gpu[gpu_id] = resale_by_gpu.get(gpu_id, 0) + _gpu_entry_resale_price(entry)
        installed_lines = [
            f"{GPU_MODELS[gpu_id]['emoji']} {GPU_MODELS[gpu_id]['name']}: **{count}x** • Продажа: **{format_money(resale_by_gpu.get(gpu_id, 0))}**"
            for gpu_id, count in installed_counts.items()
        ] or ["Пока не куплено ни одной карты."]
        total_resale_value = sum(resale_by_gpu.values())
        free_slots = max(0, int(snapshot["capacity"]) - int(snapshot["installed_count"]))

        embed.description = (
            f"**{house_data['name']}**\n"
            f"GPU: **{snapshot['installed_count']}/{snapshot['capacity']}** • Свободно: **{free_slots}**\n"
            f"Доход: **{format_money(snapshot['hourly_income'])}/ч** • Продажа всего: **{format_money(total_resale_value)}**"
        )
        embed.add_field(name="Установленные карты", value="\n".join(installed_lines), inline=False)
        embed.add_field(
            name="Управление",
            value="Верхний ряд кнопок покупает GPU по номеру. Нижний ряд продаёт одну установленную карту того же номера за **30%** от цены покупки.",
            inline=False,
        )

        balance = int(user.get("balance", 0) or 0)
        shop_lines = []
        for index, gpu_id in enumerate(GPU_ORDER, start=1):
            gpu = GPU_MODELS[gpu_id]
            owned_count = installed_counts.get(gpu_id, 0)
            next_sale_value = 0
            for entry in installed_entries:
                if _gpu_entry_id(entry) == gpu_id:
                    next_sale_value = _gpu_entry_resale_price(entry)
                    break
            if snapshot["installed_count"] >= snapshot["capacity"]:
                status = "🚫 Нет свободных слотов"
            elif balance >= gpu["price"]:
                status = "🛒 Можно купить"
            else:
                status = f"💸 Не хватает {format_money(gpu['price'] - balance)}"
            shop_lines.append(
                f"**{index}. {gpu['emoji']} {gpu['name']}**\n"
                f"{gpu['description']}\n"
                f"Покупка: **{format_money(gpu['price'])}** • Доход: **{format_money(gpu['hourly_income'])}/ч**\n"
                f"Установлено: **{owned_count}x** • Продажа 1 шт.: **{format_money(next_sale_value) if next_sale_value > 0 else 'нет'}**\n"
                f"Статус: **{status}**"
            )
        embed.add_field(name="Магазин GPU", value="\n\n".join(shop_lines), inline=False)
        embed.set_footer(text="Ряд 1 — покупка GPU. Ряд 2 — продажа установленной карты. Возврат считается от цены покупки.")
        return embed

    async def buy_house(self, user_id: int, guild_id: int, house_id: str) -> tuple[bool, discord.Embed | str]:
        if house_id not in HOUSE_TYPES:
            return False, "Такого дома нет."

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state = _house_state(user)
            current_id = house_state.get("owned_house_id")
            target = HOUSE_TYPES[house_id]
            if current_id == house_id:
                return False, "Этот дом у тебя уже куплен."
            if _house_index(current_id) >= 0 and _house_index(house_id) <= _house_index(current_id):
                return False, "Можно покупать только следующий или более дорогой дом."
            if int(user.get("balance", 0) or 0) < int(target["price"]):
                return False, f"Не хватает {format_money(target['price'] - int(user.get('balance', 0) or 0))}."

            if current_id:
                self._sync_mining_wallet(user, guild_id)
            user["balance"] = int(user.get("balance", 0) or 0) - int(target["price"])
            house_state["owned_house_id"] = house_id
            if int(house_state.get("basement_level", 0) or 0) <= 0:
                house_state["basement_level"] = 1
                house_state["last_mining_collect"] = datetime.now(timezone.utc).isoformat()
            house_state["basement_level"] = min(int(house_state["basement_level"]), int(target["max_basement_level"]))
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})

        embed = discord.Embed(title="🏠 Дом куплен", description=f"Теперь у тебя **{target['name']}**.\nБаланс: **{format_money(user['balance'])}**", color=COLORS["success"])
        return True, embed

    async def upgrade_basement(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state = _house_state(user)
            house_data = _house_current_data(house_state)
            if not house_data:
                return False, "Сначала купи дом."
            vip_bonus = _house_vip_bonus(user)
            current_level = max(1, int(house_state.get("basement_level", 1) or 1))
            if current_level >= int(house_data["max_basement_level"]):
                return False, "Подвал уже на максимуме для этого дома."

            upgrade_cost = _house_basement_upgrade_cost(house_data, current_level, vip_bonus)
            if int(user.get("balance", 0) or 0) < upgrade_cost:
                return False, f"Не хватает {format_money(upgrade_cost - int(user.get('balance', 0) or 0))}."

            self._sync_mining_wallet(user, guild_id)
            user["balance"] = int(user.get("balance", 0) or 0) - upgrade_cost
            house_state["basement_level"] = current_level + 1
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="🧱 Подвал улучшен",
            description=f"Новый уровень подвала: **{current_level + 1}**\nБаланс: **{format_money(user['balance'])}**",
            color=COLORS["success"],
        )
        return True, embed

    async def buy_gpu(self, user_id: int, guild_id: int, gpu_id: str) -> tuple[bool, discord.Embed | str]:
        if gpu_id not in GPU_MODELS:
            return False, "Такой видеокарты нет."

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state = _house_state(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."
            snapshot = self._house_snapshot(user, guild_id)
            if snapshot["installed_count"] >= snapshot["capacity"]:
                return False, "В подвале больше нет свободных слотов."

            gpu = GPU_MODELS[gpu_id]
            if int(user.get("balance", 0) or 0) < int(gpu["price"]):
                return False, f"Не хватает {format_money(gpu['price'] - int(user.get('balance', 0) or 0))}."

            self._sync_mining_wallet(user, guild_id)
            user["balance"] = int(user.get("balance", 0) or 0) - int(gpu["price"])
            installed = house_state.get("installed_gpus", [])
            installed.append(
                {
                    "gpu_id": gpu_id,
                    "buy_price": int(gpu["price"]),
                    "bought_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            house_state["installed_gpus"] = installed
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="🖥 Видеокарта куплена",
            description=f"Установлена **{gpu['name']}**.\nБаланс: **{format_money(user['balance'])}**",
            color=COLORS["success"],
        )
        return True, embed

    async def sell_gpu(self, user_id: int, guild_id: int, gpu_id: str) -> tuple[bool, discord.Embed | str]:
        if gpu_id not in GPU_MODELS:
            return False, "Такой видеокарты нет."

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state = _house_state(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."

            installed = list(house_state.get("installed_gpus", []))
            sell_index = next((index for index, entry in enumerate(installed) if _gpu_entry_id(entry) == gpu_id), None)
            if sell_index is None:
                return False, f"У тебя не установлена **{GPU_MODELS[gpu_id]['name']}**."

            self._sync_mining_wallet(user, guild_id)
            installed = list(house_state.get("installed_gpus", []))
            sell_index = next((index for index, entry in enumerate(installed) if _gpu_entry_id(entry) == gpu_id), None)
            if sell_index is None:
                return False, f"У тебя не установлена **{GPU_MODELS[gpu_id]['name']}**."

            gpu_entry = installed.pop(sell_index)
            resale_value = _gpu_entry_resale_price(gpu_entry)
            if resale_value <= 0:
                resale_value = max(1, int(round(int(GPU_MODELS[gpu_id]["price"]) * 0.30)))

            house_state["installed_gpus"] = installed
            user["balance"] = int(user.get("balance", 0) or 0) + resale_value
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})

        gpu = GPU_MODELS[gpu_id]
        embed = discord.Embed(
            title="🖥 Видеокарта продана",
            description=(
                f"Продана **{gpu['name']}**.\n"
                f"Возврат: **{format_money(resale_value)}**\n"
                f"Баланс: **{format_money(user['balance'])}**"
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def collect_mining(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            snapshot = self._house_snapshot(user, guild_id)
            if not snapshot["house_data"]:
                return False, "Сначала купи дом."
            ready_amount = int(snapshot["ready"])
            if ready_amount <= 0:
                return False, "В подвале пока нечего собирать."

            house_state = snapshot["house_state"]
            house_state["mining_wallet"] = 0
            house_state["last_mining_collect"] = datetime.now(timezone.utc).isoformat()
            house_state["mining_runs"] = int(house_state.get("mining_runs", 0) or 0) + 1
            user["balance"] = int(user.get("balance", 0) or 0) + ready_amount
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})

        await check_quest_progress(user_id, guild_id, "mine", 1)
        asyncio.create_task(
            record_player_progress(
                user_id,
                guild_id,
                action="mine",
                amount=1,
                money=ready_amount,
            )
        )
        systems_cog = self._systems_cog()
        if systems_cog is not None:
            asyncio.create_task(systems_cog.progress_contracts(user_id, guild_id, "mine", 1))

        embed = discord.Embed(
            title="💸 Доход из подвала собран",
            description=f"Получено: **{format_money(ready_amount)}**\nБаланс: **{format_money(user['balance'])}**",
            color=COLORS["success"],
        )
        if snapshot["event"] is not None:
            embed.add_field(name="Событие рынка", value=f"Бонус **{snapshot['event']['name']}** уже учтен в расчете.", inline=False)
        return True, embed

    async def accept_rental_offer(self, user_id: int, guild_id: int, offer_index: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state = _house_state(user)
            house_data = _house_current_data(house_state)
            if not house_data:
                return False, "Сначала купи дом."
            vip_bonus = _house_vip_bonus(user)
            capacity = _house_rental_capacity(house_data, vip_bonus)
            rental_state = self._rental_status(user)
            if len(rental_state["ongoing_rentals"]) >= capacity:
                return False, "Все слоты аренды уже заняты."

            window_key, _, offers, accepted_keys = self._generate_rental_offers(user, house_state, house_data)
            if offer_index >= len(offers):
                return False, "Такой заявки нет."
            offer = offers[offer_index]
            if offer["id"] in accepted_keys:
                return False, "Эта заявка уже была взята."

            payout = int(offer["payout"] * (1 + vip_bonus["rent_bonus"]))
            now = datetime.now(timezone.utc)
            active_rentals = house_state.get("active_rentals", [])
            active_rentals.append(
                {
                    "id": offer["id"],
                    "tenant_name": offer["tenant_name"],
                    "duration_hours": offer["duration_hours"],
                    "payout": payout,
                    "starts_at": now.isoformat(),
                    "ends_at": (now + timedelta(hours=int(offer["duration_hours"]))).isoformat(),
                }
            )
            house_state["active_rentals"] = active_rentals
            accepted_state = house_state.get("accepted_offers", {"window": window_key, "keys": []})
            if accepted_state.get("window") != window_key:
                accepted_state = {"window": window_key, "keys": []}
            accepted_state["keys"].append(offer["id"])
            house_state["accepted_offers"] = accepted_state
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="🛎 Аренда оформлена",
            description=f"Заселен арендатор **{offer['tenant_name']}**.\nСрок: **{offer['duration_hours']}ч** • Выплата: **{format_money(payout)}**",
            color=COLORS["success"],
        )
        return True, embed

    async def collect_rent(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state = _house_state(user)
            rental_state = self._rental_status(user)
            ready_rentals = rental_state["ready_rentals"]
            if not ready_rentals:
                return False, "Готовой аренды пока нет."

            total_value = sum(int(rental.get("payout", 0) or 0) for rental in ready_rentals)
            ready_ids = {rental["id"] for rental in ready_rentals}
            house_state["active_rentals"] = [rental for rental in house_state.get("active_rentals", []) if rental.get("id") not in ready_ids]
            user["balance"] = int(user.get("balance", 0) or 0) + total_value
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})

        await check_quest_progress(user_id, guild_id, "rent", len(ready_rentals))
        asyncio.create_task(
            record_player_progress(
                user_id,
                guild_id,
                action="rent",
                amount=len(ready_rentals),
                money=total_value,
            )
        )
        systems_cog = self._systems_cog()
        if systems_cog is not None:
            asyncio.create_task(systems_cog.progress_contracts(user_id, guild_id, "rent", len(ready_rentals)))

        embed = discord.Embed(
            title="🏘 Аренда собрана",
            description=f"Закрыто заявок: **{len(ready_rentals)}**\nПолучено: **{format_money(total_value)}**\nБаланс: **{format_money(user['balance'])}**",
            color=COLORS["success"],
        )
        return True, embed

    async def open_legacy_house(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        view = HouseView(self, interaction.user.id, interaction.guild_id, tab="house", house_page=0, entry_mode="house")
        embed = await view.render_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()

    async def open_legacy_houseshop(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        view = HouseView(self, interaction.user.id, interaction.guild_id, tab="shop", house_page=0, entry_mode="shop")
        embed = await view.render_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(HouseCog(bot))
