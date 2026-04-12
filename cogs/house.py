from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from cogs.mining import (
    FURNITURE_ITEMS,
    GARDEN_CROPS,
    GPU_MODELS,
    GPU_ORDER,
    WATERING_CANS,
    _gpu_breakdown,
    _gpu_entry_id,
    _gpu_entry_resale_price,
    _current_market_rows,
    _house_current_data,
    _house_rental_capacity,
    _house_state,
    _house_vip_bonus,
    _parse_utc,
    format_money,
)
from config import COLORS, CRYPTO_TYPES
from database import db, get_user_lock
from inventory_system import add_general_item, consume_general_item, count_general_items
from utils import (
    check_channel,
    check_quest_progress,
    format_discord_deadline,
    get_crypto_price,
    record_player_progress,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
)

TENANT_EVENTS: dict[str, list[dict[str, Any]]] = {
    "positive": [
        {"name": "оставили чаевые за чистую ванну", "multiplier": 1.20, "emoji": "🔔"},
        {"name": "продлили аренду и заплатили сверху", "multiplier": 1.15, "emoji": "✨"},
        {"name": "оставили идеальный отзыв о доме", "multiplier": 1.10, "emoji": "💌"},
    ],
    "negative": [
        {"name": "сломали кран", "multiplier": 0.90, "emoji": "⚠️"},
        {"name": "сожгли ковер", "multiplier": 0.82, "emoji": "🔥"},
        {"name": "устроили шумную вечеринку и испортили мебель", "multiplier": 0.88, "emoji": "🧯"},
    ],
}

FURNITURE_BUFFS = {
    "gaming_chair": "Даёт +2% к криптодобыче.",
    "aquarium": "Даёт +5% к редкой, эпической и легендарной рыбе.",
    "plasma_tv": "Даёт +5% к арендной выплате.",
}


HOME_FURNITURE_ITEM_TYPE = "home_furniture"


def _pending_furniture_keys(user: dict[str, Any]) -> list[str]:
    return [key for key in FURNITURE_ITEMS if count_general_items(user, item_type=HOME_FURNITURE_ITEM_TYPE, code=key) > 0]


def _add_home_furniture_item(user: dict[str, Any], furniture_key: str) -> None:
    furniture = FURNITURE_ITEMS[furniture_key]
    add_general_item(
        user,
        item_type=HOME_FURNITURE_ITEM_TYPE,
        code=furniture_key,
        name=str(furniture.get("name") or furniture_key),
        description="Используй после покупки дома, чтобы установить мебель.",
        quantity=1,
        emoji=str(furniture.get("emoji") or ""),
        payload={"furniture_key": furniture_key},
        stackable=False,
    )


def migrate_legacy_reserved_furniture(user: dict[str, Any], *, house_state: dict[str, Any] | None = None) -> bool:
    current_house_state = house_state if isinstance(house_state, dict) else _house_state(user)
    if _house_current_data(current_house_state):
        return False

    raw_furniture = current_house_state.get("furniture", [])
    if not isinstance(raw_furniture, list):
        return False

    legacy_reserved = [str(key) for key in raw_furniture if str(key) in FURNITURE_ITEMS]
    if not legacy_reserved:
        return False

    pending = set(_pending_furniture_keys(user))
    for furniture_key in legacy_reserved:
        if furniture_key not in pending:
            _add_home_furniture_item(user, furniture_key)

    current_house_state["furniture"] = [key for key in raw_furniture if str(key) not in FURNITURE_ITEMS]
    return True


def _empty_plot() -> dict[str, Any]:
    return {
        "crop_code": None,
        "planted_at": None,
        "last_watered_at": None,
        "last_progress_at": None,
        "growth_seconds_total": 0,
        "growth_seconds_accumulated": 0,
        "state": "empty",
    }


def _seed_display_name(crop_code: str) -> str:
    crop = GARDEN_CROPS[crop_code]
    return f"Семена: {crop['name']}"


def _harvest_display_name(crop_code: str) -> str:
    crop = GARDEN_CROPS[crop_code]
    return f"Урожай: {crop['name']}"


def _format_crypto_amount(symbol: str, amount: float) -> str:
    precision = 8 if symbol in {"BTC", "ETH", "LTC"} else 4
    return f"{amount:.{precision}f}".rstrip("0").rstrip(".") or "0"


def _normalize_crypto_focus(value: str | None) -> str | None:
    symbol = str(value or "").upper()
    return symbol if symbol in CRYPTO_TYPES else None


def _active_watering_can(house_state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    garden = house_state.get("garden") if isinstance(house_state.get("garden"), dict) else {}
    can_key = str(garden.get("watering_can") or "basic")
    if can_key not in WATERING_CANS:
        can_key = "basic"
    return can_key, WATERING_CANS[can_key]


def _normalize_garden(house_state: dict[str, Any]) -> list[dict[str, Any]]:
    garden = house_state.get("garden")
    if not isinstance(garden, dict):
        garden = {}
        house_state["garden"] = garden
    garden.setdefault("watering_can", "basic")
    raw_plots = garden.get("plots")
    if not isinstance(raw_plots, list):
        raw_plots = []
    max_plots = max(0, int(house_state.get("max_garden_level", 0) or 0))
    plots: list[dict[str, Any]] = []
    for raw_plot in raw_plots[:max_plots]:
        if not isinstance(raw_plot, dict):
            raw_plot = {}
        plot = _empty_plot()
        plot.update(raw_plot)
        plots.append(plot)
    while len(plots) < max_plots:
        plots.append(_empty_plot())
    garden["plots"] = plots
    return plots


def _refresh_garden_state(house_state: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    plots = _normalize_garden(house_state)
    _, can = _active_watering_can(house_state)
    water_interval = timedelta(hours=int(can.get("water_interval_hours", 8) or 8))

    for plot in plots:
        crop_code = plot.get("crop_code")
        if not crop_code or crop_code not in GARDEN_CROPS:
            plot.clear()
            plot.update(_empty_plot())
            continue

        planted_at = _parse_utc(str(plot.get("planted_at") or ""), now)
        last_watered = _parse_utc(str(plot.get("last_watered_at") or ""), planted_at)
        last_progress = _parse_utc(str(plot.get("last_progress_at") or ""), planted_at)
        watered_until = last_watered + water_interval
        progress_until = min(now, watered_until)
        if progress_until > last_progress:
            gained = int((progress_until - last_progress).total_seconds())
            plot["growth_seconds_accumulated"] = int(plot.get("growth_seconds_accumulated", 0) or 0) + gained
            plot["last_progress_at"] = progress_until.isoformat()
        total = max(1, int(plot.get("growth_seconds_total", 0) or 0))
        accumulated = int(plot.get("growth_seconds_accumulated", 0) or 0)
        if accumulated >= total:
            plot["state"] = "ready"
            plot["growth_seconds_accumulated"] = total
        elif now > watered_until:
            plot["state"] = "dry"
            plot["last_progress_at"] = progress_until.isoformat()
        else:
            plot["state"] = "growing"
            plot["last_progress_at"] = now.isoformat()
    return plots


def _plot_status_line(index: int, plot: dict[str, Any], house_state: dict[str, Any], now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    state = str(plot.get("state") or "empty")
    if state == "empty":
        return f"`{index}` Свободно"

    crop_code = str(plot.get("crop_code") or "")
    crop = GARDEN_CROPS.get(crop_code)
    if crop is None:
        return f"`{index}` Свободно"

    _, can = _active_watering_can(house_state)
    water_interval = timedelta(hours=int(can.get("water_interval_hours", 8) or 8))
    last_watered = _parse_utc(str(plot.get("last_watered_at") or ""), now)
    dry_at = last_watered + water_interval
    total = max(1, int(plot.get("growth_seconds_total", 0) or 0))
    accumulated = max(0, int(plot.get("growth_seconds_accumulated", 0) or 0))
    progress = min(100, int((accumulated / total) * 100))
    emoji = str(crop.get("emoji") or "🌱")

    if state == "ready":
        return f"`{index}` {emoji} **{crop['name']}** • готово к сбору"
    if state == "dry":
        return f"`{index}` {emoji} **{crop['name']}** • нужен полив • прогресс **{progress}%**"
    return (
        f"`{index}` {emoji} **{crop['name']}** • прогресс **{progress}%** • "
        f"полить через {format_discord_deadline(dry_at)}"
    )


def _migrate_house_state(user: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    game_stats = user.get("game_stats")
    systems = game_stats.get("_systems") if isinstance(game_stats, dict) else None
    raw_house_state = systems.get("house") if isinstance(systems, dict) else None
    had_stored_gpus = isinstance(raw_house_state, dict) and isinstance(raw_house_state.get("stored_gpus"), list)
    house_state = _house_state(user)
    changed = False
    if not had_stored_gpus:
        changed = True
    if int(house_state.get("mining_version", 1) or 1) < 2:
        legacy_total = int(house_state.get("legacy_mining_wallet", 0) or 0) + int(house_state.get("mining_wallet", 0) or 0)
        house_state["legacy_mining_wallet"] = legacy_total
        house_state["mining_wallet"] = 0
        house_state["mining_version"] = 2
        changed = True
    before = len(house_state.get("garden", {}).get("plots", [])) if isinstance(house_state.get("garden"), dict) else 0
    plots = _normalize_garden(house_state)
    if len(plots) != before:
        changed = True
    focus_symbol = _normalize_crypto_focus(house_state.get("crypto_focus"))
    if house_state.get("crypto_focus") != focus_symbol:
        house_state["crypto_focus"] = focus_symbol
        changed = True
    return house_state, changed


async def buy_seed_packet(user_id: int, guild_id: int, crop_code: str) -> tuple[bool, discord.Embed | str]:
    if crop_code not in GARDEN_CROPS:
        return False, "Таких семян нет."

    crop = GARDEN_CROPS[crop_code]
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return False, "Не удалось загрузить профиль."
        if int(user.get("balance", 0) or 0) < int(crop["price"]):
            return False, f"Не хватает {format_money(int(crop['price']) - int(user.get('balance', 0) or 0))}."
        user["balance"] = int(user.get("balance", 0) or 0) - int(crop["price"])
        add_general_item(
            user,
            item_type="seed_packet",
            code=crop_code,
            name=_seed_display_name(crop_code),
            description="Посади семена в `/house` во вкладке `Сад`.",
            quantity=1,
            emoji=str(crop.get("emoji") or "🌱"),
        )
        await db.update_user(
            user_id,
            guild_id,
            {"balance": user["balance"], "inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})},
        )
    return True, discord.Embed(
        title="Семена куплены",
        description=f"Куплены **{_seed_display_name(crop_code)}**.\nБаланс: **{format_money(user['balance'])}**",
        color=COLORS["success"],
    )


async def buy_watering_can_upgrade(user_id: int, guild_id: int, can_key: str) -> tuple[bool, discord.Embed | str]:
    if can_key not in WATERING_CANS:
        return False, "Такой лейки нет."
    can = WATERING_CANS[can_key]
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return False, "Не удалось загрузить профиль."
        house_state, _ = _migrate_house_state(user)
        if not _house_current_data(house_state):
            return False, "Сначала купи дом."
        current_key, _ = _active_watering_can(house_state)
        if current_key == can_key:
            return False, "Эта лейка уже установлена."
        if int(user.get("balance", 0) or 0) < int(can["price"]):
            return False, f"Не хватает {format_money(int(can['price']) - int(user.get('balance', 0) or 0))}."
        user["balance"] = int(user.get("balance", 0) or 0) - int(can["price"])
        house_state["garden"]["watering_can"] = can_key
        await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})
    return True, discord.Embed(
        title="Лейка установлена",
        description=(
            f"Теперь у тебя **{can['name']}**.\n"
            f"Интервал полива: **{int(can['water_interval_hours'])} ч**.\n"
            f"Баланс: **{format_money(user['balance'])}**"
        ),
        color=COLORS["success"],
    )


async def buy_furniture_item(user_id: int, guild_id: int, furniture_key: str) -> tuple[bool, discord.Embed | str]:
    if furniture_key not in FURNITURE_ITEMS:
        return False, "Такого предмета мебели нет."
    furniture = FURNITURE_ITEMS[furniture_key]
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return False, "Не удалось загрузить профиль."
        house_state, _ = _migrate_house_state(user)
        migrate_legacy_reserved_furniture(user, house_state=house_state)
        house_data = _house_current_data(house_state)
        owned = [key for key in house_state.get("furniture", []) if key in FURNITURE_ITEMS]
        pending = _pending_furniture_keys(user)
        if house_data is None and len(pending) >= 1:
            return False, "Без дома можно заранее купить только один предмет мебели. Для остального сначала купи дом."
        if furniture_key in owned or furniture_key in pending:
            return False, "Этот предмет мебели уже у тебя есть."
        if int(user.get("balance", 0) or 0) < int(furniture["price"]):
            return False, f"Не хватает денег: нужно ещё {format_money(int(furniture['price']) - int(user.get('balance', 0) or 0))}."
        user["balance"] = int(user.get("balance", 0) or 0) - int(furniture["price"])
        if house_data is None:
            _add_home_furniture_item(user, furniture_key)
        else:
            owned.append(furniture_key)
            house_state["furniture"] = owned
        await db.update_user(
            user_id,
            guild_id,
            {
                "balance": user["balance"],
                "inventory": user.get("inventory"),
                "game_stats": user.get("game_stats", {}),
            },
        )
    status_line = (
        FURNITURE_BUFFS.get(furniture_key, "Бонус мебели активирован.")
        if house_data
        else "Предмет добавлен в инвентарь. Используй его после покупки дома."
    )
    return True, discord.Embed(
        title="Покупка мебели",
        description=(
            f"Куплено: **{furniture['name']}**.\n"
            f"{status_line}\n"
            f"Баланс: **{format_money(user['balance'])}**"
        ),
        color=COLORS["success"],
    )

class HouseV2View(discord.ui.View):
    def __init__(
        self,
        cog: "HouseCommandsCog",
        user_id: int,
        guild_id: int,
        *,
        tab: str = "home",
        selected_plot: int = 0,
        selected_seed: str | None = None,
        selected_symbol: str | None = None,
        crypto_section: str = "coins",
        selected_gpu: str | None = None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.tab = tab
        self.selected_plot = selected_plot
        self.selected_seed = selected_seed
        self.selected_symbol = selected_symbol
        self.crypto_section = crypto_section if crypto_section in {"coins", "gpus"} else "coins"
        self.selected_gpu = selected_gpu if selected_gpu in GPU_MODELS else GPU_ORDER[0]
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self._build_static_tabs()
        self._build_tab_controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твой экран дома.", ephemeral=True)
            return False
        return True

    def _build_static_tabs(self):
        buttons = [
            ("Дом", "home"),
            ("Сад", "garden"),
            ("Крипта", "crypto"),
            ("Аренда", "rent"),
            ("Обустройство", "decor"),
        ]
        for label, value in buttons:
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary if self.tab == value else discord.ButtonStyle.secondary,
                row=0,
            )

            async def callback(interaction: discord.Interaction, target_tab: str = value):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    await self._swap(interaction, tab=target_tab)

            button.callback = callback
            self.add_item(button)

    def _build_tab_controls(self):
        if self.tab == "garden":
            self._build_garden_controls()
        elif self.tab == "crypto":
            self._build_crypto_controls()
        elif self.tab == "rent":
            self._build_rent_controls()
        elif self.tab == "decor":
            self._build_refresh_only()
        else:
            self._build_refresh_only()

    def _build_refresh_only(self):
        refresh = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)

        async def refresh_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction)

        refresh.callback = refresh_callback
        self.add_item(refresh)
        if self.tab != "home":
            back = discord.ui.Button(label="Назад к дому", style=discord.ButtonStyle.secondary, row=1)

            async def back_callback(interaction: discord.Interaction):
                async with self._view_lock:
                    if not await safe_defer(interaction):
                        return
                    await self._swap(interaction, tab="home")

            back.callback = back_callback
            self.add_item(back)

    def _build_garden_controls(self):
        plot_options = [discord.SelectOption(label=f"Грядка {index + 1}", value=str(index), default=index == self.selected_plot) for index in range(25)]
        self.plot_select = discord.ui.Select(placeholder="Выбери грядку", row=1, options=plot_options)

        async def plot_callback(interaction: discord.Interaction):
            async with self._view_lock:
                value = str(self.plot_select.values[0]) if self.plot_select.values else "0"
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, selected_plot=int(value))

        self.plot_select.callback = plot_callback
        self.add_item(self.plot_select)

        seed_options = [
            discord.SelectOption(label=_seed_display_name(crop_code)[:100], value=crop_code, default=crop_code == self.selected_seed)
            for crop_code in GARDEN_CROPS
        ]
        self.seed_select = discord.ui.Select(placeholder="Какие семена посадить", row=2, options=seed_options[:25])

        async def seed_callback(interaction: discord.Interaction):
            async with self._view_lock:
                value = str(self.seed_select.values[0]) if self.seed_select.values else next(iter(GARDEN_CROPS))
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, selected_seed=value)

        self.seed_select.callback = seed_callback
        self.add_item(self.seed_select)

        plant_btn = discord.ui.Button(label="Посадить", style=discord.ButtonStyle.success, row=3)
        water_btn = discord.ui.Button(label="Полить", style=discord.ButtonStyle.primary, row=3)
        harvest_btn = discord.ui.Button(label="Собрать", style=discord.ButtonStyle.success, row=3)
        water_all_btn = discord.ui.Button(label="Полить всё", style=discord.ButtonStyle.secondary, row=4)
        harvest_all_btn = discord.ui.Button(label="Собрать всё", style=discord.ButtonStyle.secondary, row=4)
        refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=4)
        back_btn = discord.ui.Button(label="Назад к дому", style=discord.ButtonStyle.secondary, row=4)

        async def plant_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.plant_seed(self.user_id, self.guild_id, self.selected_plot, self.selected_seed or next(iter(GARDEN_CROPS)))
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def water_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.water_garden(self.user_id, self.guild_id, plot_index=self.selected_plot)
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def harvest_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.harvest_garden(self.user_id, self.guild_id, plot_index=self.selected_plot)
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def water_all_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.water_garden(self.user_id, self.guild_id, plot_index=None)
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def harvest_all_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.harvest_garden(self.user_id, self.guild_id, plot_index=None)
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def refresh_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction)

        async def back_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, tab="home")

        plant_btn.callback = plant_callback
        water_btn.callback = water_callback
        harvest_btn.callback = harvest_callback
        water_all_btn.callback = water_all_callback
        harvest_all_btn.callback = harvest_all_callback
        refresh_btn.callback = refresh_callback
        back_btn.callback = back_callback
        for item in (plant_btn, water_btn, harvest_btn, water_all_btn, harvest_all_btn, refresh_btn, back_btn):
            self.add_item(item)

    def _build_crypto_controls(self):
        section_options = [
            discord.SelectOption(label="Монеты", value="coins", default=self.crypto_section == "coins"),
            discord.SelectOption(label="Видеокарты", value="gpus", default=self.crypto_section == "gpus"),
        ]
        self.crypto_section_select = discord.ui.Select(placeholder="Категория крипты", row=1, options=section_options)

        async def section_callback(interaction: discord.Interaction):
            async with self._view_lock:
                next_section = str(self.crypto_section_select.values[0]) if self.crypto_section_select.values else "coins"
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, crypto_section=next_section)

        self.crypto_section_select.callback = section_callback
        self.add_item(self.crypto_section_select)

        if self.crypto_section == "gpus":
            self._build_crypto_gpu_controls()
            return

        current_focus = _normalize_crypto_focus(self.selected_symbol)
        focus_options = [
            discord.SelectOption(
                label="Авто-распределение",
                value="auto",
                default=current_focus is None,
                description="Чистый weighted random без фокуса"[:100],
            )
        ]
        for symbol, meta in CRYPTO_TYPES.items():
            focus_options.append(
                discord.SelectOption(
                    label=f"{symbol} • {meta['name']}"[:100],
                    value=symbol,
                    default=symbol == current_focus,
                    description="Повышенный шанс при сборе и выбор для продажи"[:100],
                )
            )
        self.coin_select = discord.ui.Select(placeholder="Фокус майнинга и монета для продажи", row=2, options=focus_options[:25])

        async def focus_callback(interaction: discord.Interaction):
            async with self._view_lock:
                raw_value = str(self.coin_select.values[0]) if self.coin_select.values else "auto"
                focus_symbol = None if raw_value == "auto" else raw_value
                if not await safe_defer(interaction):
                    return
                await self.cog.set_crypto_focus(self.user_id, self.guild_id, focus_symbol)
                await self._swap(interaction, selected_symbol=focus_symbol, crypto_section="coins")

        self.coin_select.callback = focus_callback
        self.add_item(self.coin_select)

        collect_btn = discord.ui.Button(label="Собрать", style=discord.ButtonStyle.success, row=3)
        sell_all_btn = discord.ui.Button(label="Продать всё", style=discord.ButtonStyle.primary, row=3)
        sell_one_btn = discord.ui.Button(label="Продать по монете", style=discord.ButtonStyle.secondary, row=3)
        upgrade_btn = discord.ui.Button(label="Улучшить подвал", style=discord.ButtonStyle.secondary, row=4)
        legacy_btn = discord.ui.Button(label="Забрать старый кошелёк", style=discord.ButtonStyle.secondary, row=4)
        back_btn = discord.ui.Button(label="Назад к дому", style=discord.ButtonStyle.secondary, row=4)
        sell_one_btn.disabled = current_focus is None

        async def collect_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.collect_crypto(self.user_id, self.guild_id)
                await self._swap(interaction, crypto_section="coins")
                await self._send_payload(interaction, payload[1])

        async def sell_all_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.sell_crypto(self.user_id, self.guild_id, symbol=None)
                await self._swap(interaction, crypto_section="coins")
                await self._send_payload(interaction, payload[1])

        async def sell_one_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                target_symbol = _normalize_crypto_focus(self.selected_symbol)
                if target_symbol is None:
                    await interaction.followup.send("Сначала выбери конкретную монету во фокусе майнинга.", ephemeral=True)
                    return
                payload = await self.cog.sell_crypto(self.user_id, self.guild_id, symbol=target_symbol)
                await self._swap(interaction, selected_symbol=target_symbol, crypto_section="coins")
                await self._send_payload(interaction, payload[1])

        async def upgrade_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                house_cog = self.cog._house_core()
                payload = await house_cog.upgrade_basement(self.user_id, self.guild_id) if house_cog is not None else (False, "Система дома недоступна.")
                await self._swap(interaction, crypto_section="coins")
                await self._send_payload(interaction, payload[1])

        async def back_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, tab="home")

        async def legacy_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.withdraw_legacy_wallet(self.user_id, self.guild_id)
                await self._swap(interaction, crypto_section="coins")
                await self._send_payload(interaction, payload[1])

        collect_btn.callback = collect_callback
        sell_all_btn.callback = sell_all_callback
        sell_one_btn.callback = sell_one_callback
        upgrade_btn.callback = upgrade_callback
        legacy_btn.callback = legacy_callback
        back_btn.callback = back_callback
        for item in (collect_btn, sell_all_btn, sell_one_btn, upgrade_btn, legacy_btn, back_btn):
            self.add_item(item)

    def _build_crypto_gpu_controls(self):
        gpu_options = [
            discord.SelectOption(
                label=f"{GPU_MODELS[gpu_id]['name']}"[:100],
                value=gpu_id,
                default=gpu_id == self.selected_gpu,
                description=f"Доход: {format_money(GPU_MODELS[gpu_id]['hourly_income'])}/ч"[:100],
                emoji=str(GPU_MODELS[gpu_id]["emoji"]),
            )
            for gpu_id in GPU_ORDER
        ]
        self.gpu_select = discord.ui.Select(placeholder="Выбери видеокарту", row=2, options=gpu_options[:25])

        async def gpu_callback(interaction: discord.Interaction):
            async with self._view_lock:
                next_gpu = str(self.gpu_select.values[0]) if self.gpu_select.values else GPU_ORDER[0]
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, crypto_section="gpus", selected_gpu=next_gpu)

        self.gpu_select.callback = gpu_callback
        self.add_item(self.gpu_select)

        install_btn = discord.ui.Button(label="Поставить", style=discord.ButtonStyle.success, row=3)
        store_btn = discord.ui.Button(label="Убрать в сарай", style=discord.ButtonStyle.secondary, row=3)
        sell_btn = discord.ui.Button(label="Продать", style=discord.ButtonStyle.primary, row=3)
        upgrade_btn = discord.ui.Button(label="Улучшить подвал", style=discord.ButtonStyle.secondary, row=4)
        refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=4)
        back_btn = discord.ui.Button(label="Назад к дому", style=discord.ButtonStyle.secondary, row=4)

        async def install_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.install_stored_gpu(self.user_id, self.guild_id, self.selected_gpu)
                await self._swap(interaction, crypto_section="gpus", selected_gpu=self.selected_gpu)
                await self._send_payload(interaction, payload[1])

        async def store_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.store_gpu(self.user_id, self.guild_id, self.selected_gpu)
                await self._swap(interaction, crypto_section="gpus", selected_gpu=self.selected_gpu)
                await self._send_payload(interaction, payload[1])

        async def sell_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.sell_owned_gpu(self.user_id, self.guild_id, self.selected_gpu)
                await self._swap(interaction, crypto_section="gpus", selected_gpu=self.selected_gpu)
                await self._send_payload(interaction, payload[1])

        async def upgrade_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                house_cog = self.cog._house_core()
                payload = await house_cog.upgrade_basement(self.user_id, self.guild_id) if house_cog is not None else (False, "Система дома недоступна.")
                await self._swap(interaction, crypto_section="gpus", selected_gpu=self.selected_gpu)
                await self._send_payload(interaction, payload[1])

        async def refresh_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, crypto_section="gpus", selected_gpu=self.selected_gpu)

        async def back_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, tab="home")

        install_btn.callback = install_callback
        store_btn.callback = store_callback
        sell_btn.callback = sell_callback
        upgrade_btn.callback = upgrade_callback
        refresh_btn.callback = refresh_callback
        back_btn.callback = back_callback
        for item in (install_btn, store_btn, sell_btn, upgrade_btn, refresh_btn, back_btn):
            self.add_item(item)

    def _build_rent_controls(self):
        offer_1 = discord.ui.Button(label="Заявка 1", style=discord.ButtonStyle.success, row=1)
        offer_2 = discord.ui.Button(label="Заявка 2", style=discord.ButtonStyle.success, row=1)
        offer_3 = discord.ui.Button(label="Заявка 3", style=discord.ButtonStyle.success, row=1)
        collect_btn = discord.ui.Button(label="Собрать аренду", style=discord.ButtonStyle.primary, row=2)
        refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)

        async def offer_callback(interaction: discord.Interaction, offer_index: int):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                house_cog = self.cog._house_core()
                payload = await house_cog.accept_rental_offer(self.user_id, self.guild_id, offer_index) if house_cog is not None else (False, "Система дома недоступна.")
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def collect_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                payload = await self.cog.collect_rent(self.user_id, self.guild_id)
                await self._swap(interaction)
                await self._send_payload(interaction, payload[1])

        async def refresh_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction)

        offer_1.callback = lambda interaction: offer_callback(interaction, 0)
        offer_2.callback = lambda interaction: offer_callback(interaction, 1)
        offer_3.callback = lambda interaction: offer_callback(interaction, 2)
        collect_btn.callback = collect_callback
        refresh_btn.callback = refresh_callback
        back_btn = discord.ui.Button(label="Назад к дому", style=discord.ButtonStyle.secondary, row=2)

        async def back_callback(interaction: discord.Interaction):
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                await self._swap(interaction, tab="home")

        back_btn.callback = back_callback
        for item in (offer_1, offer_2, offer_3, collect_btn, refresh_btn, back_btn):
            self.add_item(item)

    async def _send_payload(self, interaction: discord.Interaction, payload: discord.Embed | str | None):
        if isinstance(payload, discord.Embed):
            await interaction.followup.send(embed=payload, ephemeral=True)
        elif payload:
            await interaction.followup.send(str(payload), ephemeral=True)

    async def _swap(self, interaction: discord.Interaction, **overrides: Any):
        view = HouseV2View(
            self.cog,
            self.user_id,
            self.guild_id,
            tab=str(overrides.get("tab", self.tab)),
            selected_plot=int(overrides.get("selected_plot", self.selected_plot)),
            selected_seed=overrides.get("selected_seed", self.selected_seed),
            selected_symbol=overrides.get("selected_symbol", self.selected_symbol),
            crypto_section=str(overrides.get("crypto_section", self.crypto_section)),
            selected_gpu=overrides.get("selected_gpu", self.selected_gpu),
        )
        embed = await view.render_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()

    async def render_embed(self) -> discord.Embed:
        if self.tab == "garden":
            return await self.cog.build_garden_embed(self.user_id, self.guild_id, selected_plot=self.selected_plot, selected_seed=self.selected_seed)
        if self.tab == "crypto":
            return await self.cog.build_crypto_embed(
                self.user_id,
                self.guild_id,
                selected_symbol=self.selected_symbol,
                selected_gpu=self.selected_gpu,
                section=self.crypto_section,
            )
        if self.tab == "rent":
            return await self.cog.build_rent_embed(self.user_id, self.guild_id)
        if self.tab == "decor":
            return await self.cog.build_decor_embed(self.user_id, self.guild_id)
        return await self.cog.build_home_embed(self.user_id, self.guild_id)

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message, delay_seconds=0)


class HouseCommandsCog(commands.Cog, name="HouseUI"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _house_core(self):
        return self.bot.get_cog("House")

    async def _load_user(self, user_id: int, guild_id: int, *, persist: bool = True) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return None, None
        house_state, changed = _migrate_house_state(user)
        from easter_event import migrate_legacy_easter_decor_inventory

        migrated_easter_decor = bool(migrate_legacy_easter_decor_inventory(user))
        migrated_reserved_furniture = migrate_legacy_reserved_furniture(user, house_state=house_state)
        _refresh_garden_state(house_state)
        if (changed or migrated_reserved_furniture or migrated_easter_decor) and persist:
            payload = {"game_stats": user.get("game_stats", {})}
            if migrated_reserved_furniture or migrated_easter_decor:
                payload["inventory"] = user.get("inventory")
            await db.update_user(user_id, guild_id, payload)
        return user, house_state

    async def build_home_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user, house_state = await self._load_user(user_id, guild_id)
        if not user or not house_state:
            return discord.Embed(title="Дом", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        house_cog = self._house_core()
        snapshot = house_cog._house_snapshot(user, guild_id) if house_cog is not None else {}
        house_data = _house_current_data(house_state)
        embed = discord.Embed(title="Дом", color=COLORS["info"])
        if house_data is None:
            embed.description = "У тебя пока нет дома. Открой `/shop` и выбери категорию **Недвижимость**, чтобы купить первый дом."
            embed.add_field(name="Что откроется после покупки", value="Аренда, подвал, крипта, сад и обустройство в одном экране `/house`.", inline=False)
            return embed

        vip_bonus = _house_vip_bonus(user)
        rental_ready = house_cog._rental_status(user) if house_cog is not None else {"ready_total": 0, "ongoing_rentals": []}
        _, can = _active_watering_can(house_state)
        from easter_event import get_owned_easter_furniture

        owned = [key for key in house_state.get("furniture", []) if key in FURNITURE_ITEMS]
        pending = _pending_furniture_keys(user)
        easter_owned = get_owned_easter_furniture(user)
        installed_lines = [f"{FURNITURE_ITEMS[key]['emoji']} **{FURNITURE_ITEMS[key]['name']}**" for key in owned]
        installed_lines.extend(f"{item['emoji']} **{item['name']}**" for item in easter_owned)
        embed.description = f"**{house_data['name']}**\n{house_data['description']}"
        embed.add_field(
            name="Обзор",
            value=(
                f"Комнаты: **{house_data['rooms']}**\n"
                f"Престиж: **{house_data['prestige']}**\n"
                f"Подвал: **{int(snapshot.get('basement_level', 0) or 0)}/{int(house_data['max_basement_level'])}**\n"
                f"Грядки: **{int(house_state.get('max_garden_level', 0) or 0)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Пассивный доход",
            value=(
                f"GPU: **{int(snapshot.get('installed_count', 0) or 0)}/{int(snapshot.get('capacity', 0) or 0)}**\n"
                f"Крипто-экв/ч: **{format_money(int(snapshot.get('hourly_income', 0) or 0))}**\n"
                f"Готово по аренде: **{format_money(int(rental_ready.get('ready_total', 0) or 0))}**\n"
                f"Активных жильцов: **{len(rental_ready.get('ongoing_rentals', []))}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Домовые бонусы",
            value=(
                f"Лейка: **{can['name']}** ({int(can['water_interval_hours'])} ч)\n"
                f"Мебель: **{len(installed_lines)} шт.**\n"
                f"VIP-слоты GPU: **+{int(vip_bonus['extra_gpu_slots'])}**\n"
                f"VIP-аренда: **+{int(vip_bonus['extra_rental_slots'])} слот**"
            ),
            inline=False,
        )
        if installed_lines or pending:
            furniture_lines = installed_lines[:]
            if pending:
                furniture_lines.extend(
                    f"{FURNITURE_ITEMS[key]['emoji']} **{FURNITURE_ITEMS[key]['name']}** (в инвентаре)" for key in pending
                )
            embed.add_field(name="Мебель", value="\n".join(furniture_lines[:10]), inline=False)
        embed.set_footer(text="Новые дома и GPU покупаются в `/shop` → `Недвижимость`, а вся настройка остаётся в `/house`.")
        return embed

    async def build_garden_embed(self, user_id: int, guild_id: int, *, selected_plot: int = 0, selected_seed: str | None = None) -> discord.Embed:
        user, house_state = await self._load_user(user_id, guild_id)
        if not user or not house_state:
            return discord.Embed(title="Сад", description="Не удалось загрузить профиль.", color=COLORS["warning"])
        house_data = _house_current_data(house_state)
        embed = discord.Embed(title="Сад", color=COLORS["success"])
        if house_data is None:
            embed.description = "Сад открывается только после покупки дома."
            return embed

        plots = _refresh_garden_state(house_state)
        _, can = _active_watering_can(house_state)
        selected_plot = max(0, min(selected_plot, max(0, len(plots) - 1)))
        selected_seed = selected_seed or next(iter(GARDEN_CROPS))
        owned_seeds = [f"{GARDEN_CROPS[crop_code]['emoji']} {_seed_display_name(crop_code)}: **{count_general_items(user, item_type='seed_packet', code=crop_code)}**" for crop_code in GARDEN_CROPS]
        plot_lines = [_plot_status_line(index + 1, plot, house_state) for index, plot in enumerate(plots)]
        embed.description = (
            f"Дом: **{house_data['name']}**\n"
            f"Грядок: **{len(plots)}**\n"
            f"Лейка: **{can['name']}** • интервал полива **{int(can['water_interval_hours'])} ч**"
        )
        embed.add_field(name="Семена в инвентаре", value="\n".join(owned_seeds[:6]) if owned_seeds else "Семян пока нет.", inline=False)
        embed.add_field(name="Грядки", value="\n".join(plot_lines[:16]) if plot_lines else "Грядок пока нет.", inline=False)
        if plots:
            current_plot = plots[selected_plot]
            current_state = str(current_plot.get("state") or "empty")
            crop_code = str(current_plot.get("crop_code") or "")
            if current_state == "empty":
                details = "Грядка пустая. Выбери семена и нажми `Посадить`."
            else:
                crop = GARDEN_CROPS.get(crop_code, {})
                details = (
                    f"Культура: **{crop.get('name', 'Неизвестно')}**\n"
                    f"Статус: **{current_state}**\n"
                    f"Прогресс: **{int(current_plot.get('growth_seconds_accumulated', 0) or 0)}/{int(current_plot.get('growth_seconds_total', 0) or 0)} сек**"
                )
            embed.add_field(name=f"Выбрана грядка #{selected_plot + 1}", value=details, inline=False)
        embed.set_footer(text="Семена покупаются в `/shop` → `Садовод`.")
        return embed

    async def build_crypto_embed(
        self,
        user_id: int,
        guild_id: int,
        *,
        selected_symbol: str | None = None,
        selected_gpu: str | None = None,
        section: str = "coins",
    ) -> discord.Embed:
        user, house_state = await self._load_user(user_id, guild_id)
        if not user or not house_state:
            return discord.Embed(title="Крипта", description="Не удалось загрузить профиль.", color=COLORS["warning"])
        house_data = _house_current_data(house_state)
        embed = discord.Embed(title="Крипта", color=COLORS["purple"])
        if house_data is None:
            embed.description = "Криптодобыча открывается только после покупки дома."
            return embed

        house_cog = self._house_core()
        snapshot = house_cog._house_snapshot(user, guild_id) if house_cog is not None else {}
        section = section if section in {"coins", "gpus"} else "coins"
        selected_gpu = selected_gpu if selected_gpu in GPU_MODELS else GPU_ORDER[0]

        if section == "gpus":
            installed_entries = [
                entry for entry in house_state.get("installed_gpus", [])
                if _gpu_entry_id(entry) in GPU_MODELS
            ]
            stored_entries = [
                entry for entry in house_state.get("stored_gpus", [])
                if _gpu_entry_id(entry) in GPU_MODELS
            ]
            installed_counts = _gpu_breakdown(installed_entries)
            stored_counts = _gpu_breakdown(stored_entries)
            selected_meta = GPU_MODELS[selected_gpu]

            selected_stored_entry = next((entry for entry in stored_entries if _gpu_entry_id(entry) == selected_gpu), None)
            selected_installed_entry = next((entry for entry in installed_entries if _gpu_entry_id(entry) == selected_gpu), None)
            selected_sale_entry = selected_stored_entry or selected_installed_entry
            selected_sale_price = _gpu_entry_resale_price(selected_sale_entry) if selected_sale_entry is not None else 0
            if selected_sale_price <= 0 and (selected_stored_entry is not None or selected_installed_entry is not None):
                selected_sale_price = max(1, int(round(int(selected_meta["price"]) * 0.30)))

            installed_lines = [
                f"{GPU_MODELS[gpu_id]['emoji']} **{GPU_MODELS[gpu_id]['name']}** — {count} шт."
                for gpu_id, count in installed_counts.items()
            ] or ["В подвале пока нет установленных карт."]
            stored_lines = [
                f"{GPU_MODELS[gpu_id]['emoji']} **{GPU_MODELS[gpu_id]['name']}** — {count} шт."
                for gpu_id, count in stored_counts.items()
            ] or ["Сарай пока пуст."]

            free_slots = max(0, int(snapshot.get("capacity", 0) or 0) - int(snapshot.get("installed_count", 0) or 0))
            embed.title = "Крипта • Видеокарты"
            embed.description = (
                f"Дом: **{house_data['name']}**\n"
                f"Установлено: **{int(snapshot.get('installed_count', 0) or 0)}/{int(snapshot.get('capacity', 0) or 0)}**\n"
                f"В сарае: **{sum(stored_counts.values())}**\n"
                f"Доход дают только установленные карты: **{format_money(int(snapshot.get('hourly_income', 0) or 0))} в час**"
            )
            embed.add_field(
                name=f"Выбрана карта: {selected_meta['emoji']} {selected_meta['name']}",
                value=(
                    f"Установлено: **{installed_counts.get(selected_gpu, 0)}**\n"
                    f"В сарае: **{stored_counts.get(selected_gpu, 0)}**\n"
                    f"Свободно слотов: **{free_slots}**\n"
                    f"Продажа 1 шт.: **{format_money(selected_sale_price) if selected_sale_price > 0 else 'нет карты'}**"
                ),
                inline=False,
            )
            embed.add_field(name="Установленные", value="\n".join(installed_lines), inline=False)
            embed.add_field(name="Сарай", value="\n".join(stored_lines), inline=False)
            embed.add_field(
                name="Как это работает",
                value=(
                    "Новая GPU покупается как обычно и сразу ставится в подвал.\n"
                    "Кнопка `Убрать в сарай` снимает карту без продажи.\n"
                    "Кнопка `Поставить` возвращает карту из сарая обратно в подвал.\n"
                    "Продажа возвращает **30%** от цены покупки конкретной карты."
                ),
                inline=False,
            )
            embed.set_footer(text="Карты в сарае считаются твоими активами, но не занимают слоты и не дают доход, пока не установлены.")
            return embed

        market_rows, _ = _current_market_rows()
        furniture = set(house_state.get("furniture", []))
        pending_value = int(snapshot.get("ready", 0) or 0)
        if "gaming_chair" in furniture:
            pending_value = int(round(pending_value * 1.02))
        legacy_wallet = int(house_state.get("legacy_mining_wallet", 0) or 0)
        wallet = house_state.get("crypto_wallet", {})
        focus_symbol = _normalize_crypto_focus(selected_symbol or house_state.get("crypto_focus"))

        wallet_lines = []
        total_wallet_value = 0
        for symbol, meta in CRYPTO_TYPES.items():
            amount = float(wallet.get(symbol, 0.0) or 0.0)
            price = get_crypto_price(symbol)
            approx_value = int(amount * price)
            total_wallet_value += approx_value
            wallet_lines.append(f"{meta['emoji']} **{symbol}**: `{_format_crypto_amount(symbol, amount)}` • **{format_money(approx_value)}**")

        market_lines = []
        for row in market_rows:
            arrow = "📈" if float(row["change_amount"]) >= 0 else "📉"
            market_lines.append(f"{row['emoji']} **{row['symbol']}**: `${row['current_price']:,.2f}` {arrow} `{row['change_percent']:+.1f}%`")

        focus_text = "Авто-распределение" if focus_symbol is None else f"Фокус на **{focus_symbol}**"
        focus_hint = (
            "Монеты распределяются по обычным шансам рынка."
            if focus_symbol is None
            else f"У **{focus_symbol}** повышен шанс при сборе, но выпадение не гарантировано."
        )
        embed.description = (
            f"Дом: **{house_data['name']}**\n"
            f"GPU: **{int(snapshot.get('installed_count', 0) or 0)}/{int(snapshot.get('capacity', 0) or 0)}**\n"
            f"Подвал: **{int(snapshot.get('basement_level', 0) or 0)}/{int(house_data['max_basement_level'])}**\n"
            f"Хэшрейт / эквивалент: **{format_money(int(snapshot.get('hourly_income', 0) or 0))} в час**\n"
            f"Режим майнинга: **{focus_text}**"
        )
        if "gaming_chair" in furniture:
            embed.description += "\n🎮 Геймерское кресло даёт **+2%** к добыче."
        embed.add_field(
            name="Как это работает",
            value=(
                f"{focus_hint}\n"
                "Купить новые GPU можно в `/shop` → `Недвижимость`.\n"
                "Кнопка `Продать по монете` использует текущий фокус."
            ),
            inline=False,
        )
        embed.add_field(name="Кошелёк", value="\n".join(wallet_lines) + f"\n\nВсего в крипте: **{format_money(total_wallet_value)}**", inline=False)
        embed.add_field(
            name="Готово к сбору",
            value=(
                f"Эквивалент к распределению: **{format_money(pending_value)}**\n"
                f"Старый кошелёк: **{format_money(legacy_wallet)}**\n"
                f"Монета для продажи: **{focus_symbol or 'не выбрана'}**\n"
                f"Свободно GPU-слотов: **{max(0, int(snapshot.get('capacity', 0) or 0) - int(snapshot.get('installed_count', 0) or 0))}**"
            ),
            inline=False,
        )
        embed.add_field(name="Курсы", value="\n".join(market_lines), inline=False)
        embed.set_footer(text="`Собрать` распределяет накопленный эквивалент по рынку. Фокус только повышает шанс выбранной монеты.")
        return embed

    async def build_rent_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user, house_state = await self._load_user(user_id, guild_id)
        if not user or not house_state:
            return discord.Embed(title="Аренда", description="Не удалось загрузить профиль.", color=COLORS["warning"])
        house_data = _house_current_data(house_state)
        embed = discord.Embed(title="Аренда", color=COLORS["success"])
        if house_data is None:
            embed.description = "Аренда открывается только после покупки дома."
            return embed

        house_cog = self._house_core()
        if house_cog is None:
            embed.description = "Система аренды временно недоступна."
            return embed

        vip_bonus = _house_vip_bonus(user)
        rental_state = house_cog._rental_status(user)
        _, next_refresh, offers, accepted = house_cog._generate_rental_offers(user, house_state, house_data)
        capacity = _house_rental_capacity(house_data, vip_bonus)
        from easter_event import collection_rent_multiplier

        decor_rent_multiplier = collection_rent_multiplier(user)
        ongoing_lines = []
        for rental in rental_state.get("ongoing_rentals", []):
            ongoing_lines.append(f"**{rental.get('tenant_name', 'Жилец')}** • {format_money(int(rental.get('payout', 0) or 0))} • до {format_discord_deadline(rental.get('ends_at'))}")
        if not ongoing_lines:
            ongoing_lines.append("Активных арендаторов пока нет.")

        offer_lines = []
        for index, offer in enumerate(offers, start=1):
            status = "Уже занято" if offer["id"] in accepted else "Можно взять"
            preview_payout = int(offer["payout"] * (1 + vip_bonus["rent_bonus"]))
            if decor_rent_multiplier > 1:
                preview_payout = int(round(preview_payout * decor_rent_multiplier))
            offer_lines.append(
                f"**{index}. {offer['tenant_name']}** • {offer['duration_hours']}ч • **{format_money(preview_payout)}**\n"
                f"{offer['description']}\nСтатус: **{status}**"
            )
        embed.description = (
            f"Дом: **{house_data['name']}**\n"
            f"Занято слотов: **{len(rental_state.get('ongoing_rentals', []))}/{capacity}**\n"
            f"Готово к сбору: **{format_money(int(rental_state.get('ready_total', 0) or 0))}**\n"
            f"Следующее обновление заявок: {format_discord_deadline(next_refresh)}"
        )
        if decor_rent_multiplier > 1:
            embed.description += "\n🪔 Коллекционный декор даёт **+2%** к аренде."
        embed.add_field(name="Текущие жильцы", value="\n".join(ongoing_lines), inline=False)
        embed.add_field(name="Доступные заявки", value="\n\n".join(offer_lines), inline=False)
        embed.set_footer(text="При сборе аренды может сработать случайное событие у жильцов.")
        return embed

    async def build_decor_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user, house_state = await self._load_user(user_id, guild_id)
        if not user or not house_state:
            return discord.Embed(title="Обустройство", description="Не удалось загрузить профиль.", color=COLORS["warning"])
        house_data = _house_current_data(house_state)
        embed = discord.Embed(title="Обустройство", color=COLORS["gold"])
        from easter_event import get_owned_easter_furniture

        owned = [key for key in house_state.get("furniture", []) if key in FURNITURE_ITEMS]
        pending = _pending_furniture_keys(user)
        easter_owned = get_owned_easter_furniture(user)
        if house_data is None:
            if not pending:
                embed.description = "Обустройство откроется после покупки дома, но один предмет мебели уже можно купить заранее в `/shop` → `IKEA`."
                return embed
            embed.description = "Дома пока нет, но один предмет мебели уже ждёт в инвентаре. Его бонус активируется после покупки дома."
            lines = [f"{FURNITURE_ITEMS[key]['emoji']} **{FURNITURE_ITEMS[key]['name']}** - ждёт в инвентаре" for key in pending]
            embed.add_field(name="Отложенная мебель", value="\n".join(lines), inline=False)
            return embed
        if not owned and not pending and not easter_owned:
            embed.description = "Мебели пока нет. Открой `/shop` → `IKEA`."
            return embed
        embed.description = f"Дом: **{house_data['name']}**\nМебель и коллекционный декор дают постоянные мягкие бонусы дому и связанным системам."
        if owned:
            lines = [f"{FURNITURE_ITEMS[key]['emoji']} **{FURNITURE_ITEMS[key]['name']}** - {FURNITURE_BUFFS.get(key, 'Бонус активен.')}" for key in owned]
            embed.add_field(name="Установленная мебель", value="\n".join(lines), inline=False)
        if easter_owned:
            easter_lines = [f"{item['emoji']} **{item['name']}** - {item['description']}" for item in easter_owned]
            embed.add_field(name="Коллекционный декор", value="\n".join(easter_lines), inline=False)
        if pending:
            pending_lines = [f"{FURNITURE_ITEMS[key]['emoji']} **{FURNITURE_ITEMS[key]['name']}** - используй из инвентаря, чтобы установить" for key in pending]
            embed.add_field(name="В инвентаре", value="\n".join(pending_lines), inline=False)
        embed.add_field(
            name="Трофеи",
            value="Памятные трофеи хранятся в инвентаре и не пропадают. Сейчас их нельзя отдельно расставлять по дому, но они сохраняются у тебя навсегда.",
            inline=False,
        )
        return embed

    async def plant_seed(self, user_id: int, guild_id: int, plot_index: int, crop_code: str) -> tuple[bool, discord.Embed | str]:
        if crop_code not in GARDEN_CROPS:
            return False, "Таких семян нет."
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."
            plots = _refresh_garden_state(house_state)
            if plot_index < 0 or plot_index >= len(plots):
                return False, "Такой грядки нет."
            if str(plots[plot_index].get("state") or "empty") != "empty":
                return False, "Эта грядка уже занята."
            if consume_general_item(user, item_type="seed_packet", code=crop_code, quantity=1) is None:
                return False, f"У тебя нет предмета **{_seed_display_name(crop_code)}**."
            crop = GARDEN_CROPS[crop_code]
            now = datetime.now(timezone.utc)
            plots[plot_index].update(
                {
                    "crop_code": crop_code,
                    "planted_at": now.isoformat(),
                    "last_watered_at": now.isoformat(),
                    "last_progress_at": now.isoformat(),
                    "growth_seconds_total": int(crop["growth_hours"]) * 3600,
                    "growth_seconds_accumulated": 0,
                    "state": "growing",
                }
            )
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
        return True, discord.Embed(title="Посадка", description=f"На грядку **#{plot_index + 1}** посажены **{crop['name']}**.", color=COLORS["success"])

    async def water_garden(self, user_id: int, guild_id: int, *, plot_index: int | None) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."
            plots = _refresh_garden_state(house_state)
            now = datetime.now(timezone.utc)
            watered = 0
            indices = range(len(plots)) if plot_index is None else [plot_index]
            for index in indices:
                if index < 0 or index >= len(plots):
                    continue
                state = str(plots[index].get("state") or "empty")
                if state in {"empty", "ready"}:
                    continue
                plots[index]["last_watered_at"] = now.isoformat()
                plots[index]["last_progress_at"] = now.isoformat()
                plots[index]["state"] = "growing"
                watered += 1
            if watered <= 0:
                return False, "Поливать сейчас нечего."
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
        return True, discord.Embed(title="Полив", description=f"Полито грядок: **{watered}**.", color=COLORS["success"])

    async def harvest_garden(self, user_id: int, guild_id: int, *, plot_index: int | None) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            from easter_event import collection_garden_yield_multiplier

            garden_yield_multiplier = collection_garden_yield_multiplier(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."
            plots = _refresh_garden_state(house_state)
            harvested: list[str] = []
            indices = range(len(plots)) if plot_index is None else [plot_index]
            for index in indices:
                if index < 0 or index >= len(plots):
                    continue
                if str(plots[index].get("state") or "") != "ready":
                    continue
                crop_code = str(plots[index].get("crop_code") or "")
                crop = GARDEN_CROPS.get(crop_code)
                if crop is None:
                    continue
                amount = random.randint(int(crop["yield_min"]), int(crop["yield_max"]))
                if garden_yield_multiplier > 1:
                    amount = max(1, int(round(amount * garden_yield_multiplier)))
                add_general_item(
                    user,
                    item_type="crop_harvest",
                    code=crop_code,
                    name=_harvest_display_name(crop_code),
                    description=f"Свежий урожай культуры **{crop['name']}**.",
                    quantity=amount,
                    emoji=str(crop.get("emoji") or "🌾"),
                )
                plots[index] = _empty_plot()
                harvested.append(f"{crop['emoji']} {crop['name']} x{amount}")
            if not harvested:
                return False, "Собирать пока нечего."
            house_state["garden"]["plots"] = plots
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
        return True, discord.Embed(title="Урожай собран", description="\n".join(harvested), color=COLORS["success"])

    async def set_crypto_focus(self, user_id: int, guild_id: int, symbol: str | None) -> tuple[bool, str]:
        focus_symbol = _normalize_crypto_focus(symbol)
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."
            house_state["crypto_focus"] = focus_symbol
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
        if focus_symbol is None:
            return True, "Фокус майнинга сброшен. Снова работает авто-распределение."
        return True, f"Фокус майнинга переключен на **{focus_symbol}**."

    async def install_stored_gpu(self, user_id: int, guild_id: int, gpu_id: str) -> tuple[bool, discord.Embed | str]:
        house_cog = self._house_core()
        if house_cog is None:
            return False, "Система дома недоступна."
        return await house_cog.install_stored_gpu(user_id, guild_id, gpu_id)

    async def store_gpu(self, user_id: int, guild_id: int, gpu_id: str) -> tuple[bool, discord.Embed | str]:
        house_cog = self._house_core()
        if house_cog is None:
            return False, "Система дома недоступна."
        return await house_cog.store_gpu(user_id, guild_id, gpu_id)

    async def sell_owned_gpu(self, user_id: int, guild_id: int, gpu_id: str) -> tuple[bool, discord.Embed | str]:
        house_cog = self._house_core()
        if house_cog is None:
            return False, "Система дома недоступна."
        return await house_cog.sell_owned_gpu(user_id, guild_id, gpu_id)

    async def collect_crypto(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        house_cog = self._house_core()
        if house_cog is None:
            return False, "Система дома недоступна."
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            snapshot = house_cog._house_snapshot(user, guild_id)
            if not snapshot.get("house_data"):
                return False, "Сначала купи дом."
            equivalent_value = int(snapshot.get("ready", 0) or 0)
            if "gaming_chair" in set(house_state.get("furniture", [])):
                equivalent_value = int(round(equivalent_value * 1.02))
            if equivalent_value <= 0:
                return False, "В подвале пока ничего не накопилось."
            wallet = house_state.get("crypto_wallet", {})
            symbols = list(CRYPTO_TYPES.keys())
            weights = [float(CRYPTO_TYPES[symbol].get("chance", 1.0) or 1.0) for symbol in symbols]
            focus_symbol = _normalize_crypto_focus(house_state.get("crypto_focus"))
            if focus_symbol in symbols:
                focus_index = symbols.index(focus_symbol)
                weights[focus_index] = float(weights[focus_index]) * 2.5
            rolls = max(1, min(12, int(snapshot.get("installed_count", 0) or 0) + int(snapshot.get("basement_level", 0) or 0)))
            remaining = float(equivalent_value)
            breakdown: dict[str, float] = {symbol: 0.0 for symbol in symbols}
            for index in range(rolls):
                symbol = random.choices(symbols, weights=weights, k=1)[0]
                price = max(float(get_crypto_price(symbol)), 0.00000001)
                value = remaining if index == rolls - 1 else min(remaining, max(1.0, (remaining / max(1, rolls - index)) * random.uniform(0.7, 1.3)))
                amount = value / price
                breakdown[symbol] += amount
                wallet[symbol] = float(wallet.get(symbol, 0.0) or 0.0) + amount
                remaining -= value
            house_state["crypto_wallet"] = wallet
            house_state["mining_wallet"] = 0
            house_state["last_mining_collect"] = datetime.now(timezone.utc).isoformat()
            house_state["mining_runs"] = int(house_state.get("mining_runs", 0) or 0) + 1
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        await check_quest_progress(user_id, guild_id, "mine", 1)
        asyncio.create_task(record_player_progress(user_id, guild_id, action="mine", amount=1, money=equivalent_value))
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is not None:
            asyncio.create_task(systems_cog.progress_contracts(user_id, guild_id, "mine", 1))

        lines = [f"{CRYPTO_TYPES[symbol]['emoji']} **{symbol}**: `{_format_crypto_amount(symbol, amount)}`" for symbol, amount in breakdown.items() if amount > 0]
        focus_line = "Режим: **авто-распределение**" if focus_symbol is None else f"Режим: **фокус на {focus_symbol}**"
        return True, discord.Embed(
            title="Крипта собрана",
            description=f"Кошелёк пополнен на эквивалент **{format_money(equivalent_value)}**.\n{focus_line}\n\n" + ("\n".join(lines) if lines else "Монеты не выпали."),
            color=COLORS["success"],
        )

    async def sell_crypto(self, user_id: int, guild_id: int, *, symbol: str | None) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            if not _house_current_data(house_state):
                return False, "Сначала купи дом."
            wallet = house_state.get("crypto_wallet", {})
            symbols = [symbol] if symbol else list(CRYPTO_TYPES.keys())
            total_money = 0
            sold_lines = []
            for current_symbol in symbols:
                if current_symbol not in CRYPTO_TYPES:
                    continue
                amount = float(wallet.get(current_symbol, 0.0) or 0.0)
                if amount <= 0:
                    continue
                payout = int(amount * float(get_crypto_price(current_symbol)))
                total_money += payout
                wallet[current_symbol] = 0.0
                sold_lines.append(f"{CRYPTO_TYPES[current_symbol]['emoji']} **{current_symbol}**: `{_format_crypto_amount(current_symbol, amount)}` → **{format_money(payout)}**")
            if total_money <= 0:
                return False, "Продавать пока нечего."
            user["balance"] = int(user.get("balance", 0) or 0) + total_money
            house_state["crypto_wallet"] = wallet
            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user["balance"],
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )
        return True, discord.Embed(title="Крипта продана", description="\n".join(sold_lines) + f"\n\nБаланс: **{format_money(user['balance'])}**", color=COLORS["success"])

    async def withdraw_legacy_wallet(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            legacy_wallet = int(house_state.get("legacy_mining_wallet", 0) or 0)
            if legacy_wallet <= 0:
                return False, "Старый кошелёк уже пуст."
            house_state["legacy_mining_wallet"] = 0
            user["balance"] = int(user.get("balance", 0) or 0) + legacy_wallet
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})
        return True, discord.Embed(title="Старый кошелёк выведен", description=f"На баланс переведено **{format_money(legacy_wallet)}**.\nБаланс: **{format_money(user['balance'])}**", color=COLORS["success"])

    async def collect_rent(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        house_cog = self._house_core()
        if house_cog is None:
            return False, "Система дома недоступна."
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            house_state, _ = _migrate_house_state(user)
            rental_state = house_cog._rental_status(user)
            ready_rentals = list(rental_state.get("ready_rentals", []))
            if not ready_rentals:
                return False, "Готовой аренды пока нет."
            owned_furniture = set(house_state.get("furniture", []))
            from easter_event import collection_rent_multiplier

            decor_rent_multiplier = collection_rent_multiplier(user)
            total_value = 0
            event_lines = []
            for rental in ready_rentals:
                payout = int(rental.get("payout", 0) or 0)
                if "plasma_tv" in owned_furniture:
                    payout = int(round(payout * 1.05))
                if decor_rent_multiplier > 1:
                    payout = int(round(payout * decor_rent_multiplier))
                if random.random() <= 0.20:
                    event = random.choice(TENANT_EVENTS["positive" if random.random() < 0.5 else "negative"])
                    payout = max(0, int(round(payout * float(event["multiplier"]))))
                    event_lines.append(f"{event['emoji']} <@{user_id}>, жильцы **{rental.get('tenant_name', 'из дома')}** {event['name']}.")
                total_value += payout
            ready_ids = {rental.get("id") for rental in ready_rentals}
            house_state["active_rentals"] = [rental for rental in house_state.get("active_rentals", []) if rental.get("id") not in ready_ids]
            user["balance"] = int(user.get("balance", 0) or 0) + total_value
            from easter_event import grant_easter_drops

            easter_cog = self.bot.get_cog("EasterEvent")
            easter_payload = grant_easter_drops(
                user,
                "rent_collect",
                guild_state=easter_cog.get_cached_guild_state(guild_id) if easter_cog else None,
            )
            easter_lines = list(easter_payload["lines"])
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "game_stats": user.get("game_stats", {})})
            if easter_cog and int(easter_payload.get("server_points", 0) or 0) > 0:
                easter_lines.extend(await easter_cog.apply_server_progress(guild_id, int(easter_payload.get("server_points", 0) or 0)))

        await check_quest_progress(user_id, guild_id, "rent", len(ready_rentals))
        asyncio.create_task(record_player_progress(user_id, guild_id, action="rent", amount=len(ready_rentals), money=total_value))
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is not None:
            asyncio.create_task(systems_cog.progress_contracts(user_id, guild_id, "rent", len(ready_rentals)))

        embed = discord.Embed(
            title="Аренда собрана",
            description=f"Закрыто заявок: **{len(ready_rentals)}**\nПолучено: **{format_money(total_value)}**\nБаланс: **{format_money(user['balance'])}**",
            color=COLORS["success"],
        )
        if event_lines:
            embed.add_field(name="События жильцов", value="\n".join(event_lines[:6]), inline=False)
        if easter_lines:
            embed.add_field(name="Пасха 2026", value="\n".join(easter_lines), inline=False)
        return True, embed

    @app_commands.command(name="house", description="Открыть дом, сад, крипту, аренду и обустройство")
    async def house(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return
        user, house_state = await self._load_user(interaction.user.id, interaction.guild_id)
        selected_symbol = _normalize_crypto_focus(house_state.get("crypto_focus")) if house_state else None
        view = HouseV2View(self, interaction.user.id, interaction.guild_id, tab="home", selected_symbol=selected_symbol)
        embed = await view.render_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(HouseCommandsCog(bot))
