import asyncio
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import BUSINESSES, COLORS
from database import db, get_user_lock, supabase
from utils import (
    check_channel,
    check_quest_progress,
    count_owned_businesses,
    ensure_unique_businesses,
    format_discord_deadline,
    get_business_autocollect_state,
    process_business_autocollect,
    record_player_progress,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
)

BUSINESSES_PER_PAGE = 5
OWNED_BUSINESSES_PER_PAGE = 4
BUSINESS_THEMES = (
    (("lemonade", "hot dog", "coffee", "pizza", "burger"), "ЕДА", "Быстрый оборот и стабильный поток клиентов."),
    (("store", "supermarket", "mall", "shop"), "ТОРГОВЛЯ", "Постоянный спрос и лёгкий рост."),
    (("gaming", "data", "ai", "robotics"), "ТЕХ", "Дороже на входе, но сильнее в лейте."),
    (("hotel", "resort", "hospital", "gym", "barber"), "СЕРВИС", "Стабильная выручка и лояльная аудитория."),
    (("factory", "office", "bank"), "КАПИТАЛ", "Крупные вложения и солидный кэшфлоу."),
    (("airport", "port", "fleet", "stadium", "shipyard", "megacity", "skyscraper"), "ИМПЕРИЯ", "Поздние бизнесы для настоящего магната."),
)

BUSINESS_DISPLAY_NAMES = {
    "🍋 Lemonade Stand": "🍋 Лимонадная стойка",
    "🌭 Hot Dog Cart": "🌭 Тележка с хот-догами",
    "☕ Coffee Shop": "☕ Кофейня",
    "🍕 Pizza Place": "🍕 Пиццерия",
    "🍔 Burger Joint": "🍔 Бургерная",
    "🎮 Gaming Cafe": "🎮 Игровое кафе",
    "🏪 Convenience Store": "🏪 Мини-маркет",
    "💇 Barbershop": "💇 Барбершоп",
    "🏋️ Gym": "🏋️ Спортзал",
    "🎬 Movie Theater": "🎬 Кинотеатр",
    "🏨 Small Hotel": "🏨 Небольшой отель",
    "🏪 Supermarket": "🏪 Супермаркет",
    "🏭 Factory": "🏭 Завод",
    "🏢 Office Building": "🏢 Офисное здание",
    "🏬 Shopping Mall": "🏬 Торговый центр",
    "🏦 Bank Branch": "🏦 Филиал банка",
    "🏥 Hospital": "🏥 Больница",
    "🏰 Casino": "🏰 Казино",
    "✈️ Airport": "✈️ Аэропорт",
    "🌆 Skyscraper": "🌆 Небоскрёб",
}

BUSINESS_UPGRADE_MAX_LEVEL = 5


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def clean_business_name(business: dict[str, Any]) -> str:
    raw_name = str(business.get("name", "Business"))
    ascii_name = re.sub(r"\s+", " ", raw_name.encode("ascii", "ignore").decode()).strip(" -")
    return ascii_name or raw_name


def display_business_name(business: dict[str, Any]) -> str:
    raw_name = str(business.get("name", "Business"))
    if raw_name in BUSINESS_DISPLAY_NAMES:
        return BUSINESS_DISPLAY_NAMES[raw_name]
    pretty_name = re.sub(r"\s+", " ", raw_name).strip()
    return pretty_name or clean_business_name(business)


def business_daily_income(business: dict[str, Any]) -> int:
    return int(business["income"] * 24 / business["time"])


def business_upgrade_level(instance: dict[str, Any]) -> int:
    return max(0, min(BUSINESS_UPGRADE_MAX_LEVEL, int(instance.get("upgrade_level", 0) or 0)))


def business_upgrade_cost(business: dict[str, Any], current_level: int) -> int:
    return int(business["cost"] * 0.6 * (current_level + 1))


def business_income_for_instance(business: dict[str, Any], instance: dict[str, Any]) -> int:
    level = business_upgrade_level(instance)
    return int(business["income"] * (1 + level * 0.25))


def business_daily_income_for_instance(business: dict[str, Any], instance: dict[str, Any]) -> int:
    return int(business_income_for_instance(business, instance) * 24 / business["time"])


def business_upgrade_spent(business: dict[str, Any], instance: dict[str, Any]) -> int:
    level = business_upgrade_level(instance)
    return sum(business_upgrade_cost(business, previous_level) for previous_level in range(level))


def business_roi_days(business: dict[str, Any]) -> float:
    return round(business["cost"] / max(1, business_daily_income(business)), 1)


def business_tier(business: dict[str, Any]) -> str:
    cost = business["cost"]
    if cost < 10_000:
        return "Старт"
    if cost < 100_000:
        return "Рост"
    if cost < 1_000_000:
        return "Опытный"
    if cost < 25_000_000:
        return "Элита"
    return "Империя"


def business_theme(business: dict[str, Any]) -> tuple[str, str]:
    normalized_name = clean_business_name(business).lower()
    for keywords, badge, tagline in BUSINESS_THEMES:
        if any(keyword in normalized_name for keyword in keywords):
            return badge, tagline
    return "ПАССИВ", "Сбалансированный источник долгого пассивного дохода."


def format_delta(delta: timedelta | None) -> str:
    if delta is None:
        return "готово сейчас"

    total_seconds = max(0, int(delta.total_seconds()))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"


def parse_utc_timestamp(raw_value: str | None, fallback: datetime) -> datetime:
    if not raw_value:
        return fallback

    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return fallback

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def create_business_instance(now: datetime) -> dict[str, Any]:
    return {
        "bought_at": now.isoformat(),
        "last_collect": now.isoformat(),
        "total_earned": 0,
        "upgrade_level": 0,
    }


def market_status_text(business: dict[str, Any], balance: int, owned_count: int) -> str:
    if owned_count > 0:
        return "✅ Уже куплен"

    shortfall = max(0, business["cost"] - balance)
    if shortfall == 0:
        return "🛒 Можно купить"
    return f"💸 Не хватает {format_money(shortfall)}"


def market_card_value(business_id: int, business: dict[str, Any], balance: int, owned_count: int) -> str:
    return (
        f"`ID {business_id}`\n"
        f"💰 Цена: **{format_money(business['cost'])}**\n"
        f"💵 Доход: **{format_money(business['income'])}** каждые **{business['time']}ч**\n"
        f"📈 Окупаемость: **~{business_roi_days(business)} дн.**\n"
        f"📦 Статус: **{market_status_text(business, balance, owned_count)}**"
    )


def portfolio_card_value(item: dict[str, Any]) -> str:
    business = item["business"]
    badge, _ = business_theme(business)
    status_line = (
        f"✅ Готово к сбору: **{format_money(item['ready_value'])}**"
        if item["ready_count"] > 0
        else f"⏳ Следующая выплата: {format_discord_deadline(item['next_ready_at'])}"
    )
    return (
        f"`ID {item['id']}` `{badge}` `{business_tier(business)}` `Ур. {item['upgrade_level']}/{BUSINESS_UPGRADE_MAX_LEVEL}`\n"
        f"{status_line}\n"
        f"💵 Доход: **{format_money(item['income_per_cycle'])}** / **{business['time']}ч**\n"
        f"📈 В день: **{format_money(item['daily_income'])}**\n"
        f"🏦 Заработано: **{format_money(item['total_earned'])}**\n"
        f"💼 Вложено: **{format_money(item['invested'])}**\n"
        f"⬆️ След. апгрейд: **{item['next_upgrade_text']}**"
    )


class BaseBusinessView(discord.ui.View):
    def __init__(self, cog: "BusinessCog", user_id: int, guild_id: int, page: int = 0):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.page = page
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню открыто не тобой.", ephemeral=True)
            return False
        return True

    def disable_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _edit_deferred_response(
        self,
        interaction: discord.Interaction,
        *,
        embed: discord.Embed,
        view: "BaseBusinessView | None" = None,
    ):
        target_view = view or self
        if not await safe_edit_original_response(interaction, embed=embed, view=target_view):
            return
        await target_view._remember_message(interaction)

    async def on_timeout(self):
        if self.message is None:
            return

        self.disable_buttons()
        try:
            await self.message.edit(view=self)
        except Exception:
            pass
        schedule_message_cleanup(self.message, delay_seconds=0)


class BusinessShopView(BaseBusinessView):
    def __init__(self, cog: "BusinessCog", user_id: int, guild_id: int, page: int = 0):
        self.total_pages = max(1, math.ceil(len(BUSINESSES) / BUSINESSES_PER_PAGE))
        self.owned_business_ids: set[str] = set()
        super().__init__(cog, user_id, guild_id, max(0, min(page, self.total_pages - 1)))
        self._sync_buttons()

    async def _load_owned_state(self, sync_table: bool = False):
        _, normalized_businesses, _ = await ensure_unique_businesses(
            self.user_id,
            self.guild_id,
            sync_table=sync_table,
        )
        self.owned_business_ids = set(normalized_businesses.keys())

    def _page_items(self):
        items = sorted(BUSINESSES.items())
        start = self.page * BUSINESSES_PER_PAGE
        return items[start:start + BUSINESSES_PER_PAGE]

    def _sync_buttons(self):
        page_items = self._page_items()
        buttons = [self.buy_1, self.buy_2, self.buy_3, self.buy_4, self.buy_5]

        for index, button in enumerate(buttons):
            if index < len(page_items):
                business_id, _ = page_items[index]
                if str(business_id) in self.owned_business_ids:
                    button.label = f"Есть #{business_id}"
                    button.disabled = True
                    button.style = discord.ButtonStyle.secondary
                    button.emoji = "✅"
                else:
                    button.label = f"Купить #{business_id}"
                    button.disabled = False
                    button.style = discord.ButtonStyle.success
                    button.emoji = "🛒"
            else:
                button.label = "Недоступно"
                button.disabled = True
                button.style = discord.ButtonStyle.secondary
                button.emoji = "➖"

        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.total_pages - 1
        self.page_indicator.label = f"{self.page + 1}/{self.total_pages}"
        self.my_businesses.label = f"Мои {len(self.owned_business_ids)}"
        self.my_businesses.disabled = True
        self.my_businesses.style = discord.ButtonStyle.secondary
        self.my_businesses.emoji = "🏢"

    async def _refresh_message(self):
        await self._load_owned_state()
        self._sync_buttons()
        embed = await self.cog.build_businesses_embed(self.user_id, self.guild_id, self.page)
        if self.message is not None:
            await self.message.edit(embed=embed, view=self)

    async def _refresh_from_interaction(self, interaction: discord.Interaction):
        await self._load_owned_state()
        self._sync_buttons()
        embed = await self.cog.build_businesses_embed(self.user_id, self.guild_id, self.page)
        await self._edit_deferred_response(interaction, embed=embed)

    async def _buy_slot(self, interaction: discord.Interaction, slot: int):
        async with self._view_lock:
            page_items = self._page_items()
            if slot >= len(page_items):
                await interaction.response.send_message("В этом слоте сейчас нет бизнеса.", ephemeral=True)
                return

            business_id, _ = page_items[slot]
            if not await safe_defer(interaction):
                return
            success, payload = await self.cog.purchase_business(interaction.user.id, interaction.guild_id, business_id)
            await self._refresh_from_interaction(interaction)

            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(payload, ephemeral=True)

    @discord.ui.button(label="Купить #1", style=discord.ButtonStyle.success, row=0)
    async def buy_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 0)

    @discord.ui.button(label="Купить #2", style=discord.ButtonStyle.success, row=0)
    async def buy_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 1)

    @discord.ui.button(label="Купить #3", style=discord.ButtonStyle.success, row=0)
    async def buy_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 2)

    @discord.ui.button(label="Купить #4", style=discord.ButtonStyle.success, row=0)
    async def buy_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 3)

    @discord.ui.button(label="Купить #5", style=discord.ButtonStyle.success, row=0)
    async def buy_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 4)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.page = max(0, self.page - 1)
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Мои 0", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def my_businesses(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="Дальше", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.page = min(self.total_pages - 1, self.page + 1)
            await self._refresh_from_interaction(interaction)


class OwnedBusinessesView(BaseBusinessView):
    def __init__(self, cog: "BusinessCog", user_id: int, guild_id: int, page: int = 0):
        self.total_pages = 1
        super().__init__(cog, user_id, guild_id, page)
        self._sync_buttons()

    async def _page_count(self) -> int:
        summaries, _ = await self.cog.get_owned_summaries(self.user_id, self.guild_id)
        return max(1, math.ceil(len(summaries) / OWNED_BUSINESSES_PER_PAGE))

    def _sync_buttons(self):
        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.total_pages - 1
        self.page_indicator.label = f"{self.page + 1}/{self.total_pages}"

    async def _refresh_message(self):
        self.total_pages = await self._page_count()
        self.page = max(0, min(self.page, self.total_pages - 1))
        self._sync_buttons()
        embed = await self.cog.build_owned_businesses_embed(self.user_id, self.guild_id, self.page)
        if self.message is not None:
            await self.message.edit(embed=embed, view=self)

    async def _refresh_from_interaction(self, interaction: discord.Interaction):
        self.total_pages = await self._page_count()
        self.page = max(0, min(self.page, self.total_pages - 1))
        self._sync_buttons()
        embed = await self.cog.build_owned_businesses_embed(self.user_id, self.guild_id, self.page)
        await self._edit_deferred_response(interaction, embed=embed)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, row=0)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.page = max(0, self.page - 1)
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Собрать всё", style=discord.ButtonStyle.success, row=0)
    async def collect_ready(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            success, payload = await self.cog.collect_business_income(interaction.user.id, interaction.guild_id)
            await self._refresh_from_interaction(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(payload, ephemeral=True)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.primary, row=0)
    async def open_market(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="Дальше", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.total_pages = await self._page_count()
            self.page = min(self.total_pages - 1, self.page + 1)
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="Автосбор", style=discord.ButtonStyle.primary, row=1)
    async def auto_collect_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            view = AutoCollectView(self.cog, self.user_id, self.guild_id)
            view._sync_buttons(await self.cog.get_autocollect_state(self.user_id, self.guild_id))
            embed = await self.cog.build_autocollect_embed(self.user_id, self.guild_id)
            await interaction.edit_original_response(embed=embed, view=view)
            view.message = await interaction.original_response()

    @discord.ui.button(label="Апгрейды", style=discord.ButtonStyle.success, row=1)
    async def business_upgrades(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            view = BusinessUpgradeView(self.cog, self.user_id, self.guild_id, self.page)
            view.total_pages = await view._page_count()
            view._sync_buttons(await self.cog.get_owned_summaries(self.user_id, self.guild_id))
            embed = await self.cog.build_business_upgrades_embed(self.user_id, self.guild_id, view.page)
            await interaction.edit_original_response(embed=embed, view=view)
            view.message = await interaction.original_response()


class BusinessUpgradeView(BaseBusinessView):
    def __init__(self, cog: "BusinessCog", user_id: int, guild_id: int, page: int = 0):
        self.total_pages = 1
        super().__init__(cog, user_id, guild_id, page)
        self._sync_buttons(([], {}))

    async def _page_count(self) -> int:
        summaries, _ = await self.cog.get_owned_summaries(self.user_id, self.guild_id)
        return max(1, math.ceil(len(summaries) / OWNED_BUSINESSES_PER_PAGE))

    def _visible_items(self, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        start = self.page * OWNED_BUSINESSES_PER_PAGE
        return summaries[start:start + OWNED_BUSINESSES_PER_PAGE]

    def _sync_buttons(self, payload: tuple[list[dict[str, Any]], dict[str, Any]]):
        summaries, _ = payload
        visible_items = self._visible_items(summaries)
        buttons = [self.upgrade_1, self.upgrade_2, self.upgrade_3, self.upgrade_4]

        for index, button in enumerate(buttons):
            if index >= len(visible_items):
                button.disabled = True
                button.label = "Нет бизнеса"
                button.style = discord.ButtonStyle.secondary
                continue

            item = visible_items[index]
            if item["next_upgrade_cost"] is None:
                button.disabled = True
                button.label = f"MAX #{item['id']}"
                button.style = discord.ButtonStyle.secondary
            else:
                button.disabled = False
                button.label = f"#{item['id']} -> {format_money(item['next_upgrade_cost'])}"
                button.style = discord.ButtonStyle.success

        self.prev_page.disabled = self.page == 0
        self.next_page.disabled = self.page >= self.total_pages - 1
        self.page_indicator.label = f"{self.page + 1}/{self.total_pages}"

    async def _refresh_from_interaction(self, interaction: discord.Interaction):
        self.total_pages = await self._page_count()
        self.page = max(0, min(self.page, self.total_pages - 1))
        payload = await self.cog.get_owned_summaries(self.user_id, self.guild_id)
        self._sync_buttons(payload)
        embed = await self.cog.build_business_upgrades_embed(self.user_id, self.guild_id, self.page)
        await self._edit_deferred_response(interaction, embed=embed)

    async def _buy_slot(self, interaction: discord.Interaction, slot: int):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            summaries, _ = await self.cog.get_owned_summaries(self.user_id, self.guild_id)
            visible_items = self._visible_items(summaries)
            if slot >= len(visible_items):
                await interaction.followup.send("В этом слоте нет бизнеса.", ephemeral=True)
                return
            success, payload = await self.cog.upgrade_business(self.user_id, self.guild_id, visible_items[slot]["id"])
            await self._refresh_from_interaction(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="#1", style=discord.ButtonStyle.success, row=0)
    async def upgrade_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 0)

    @discord.ui.button(label="#2", style=discord.ButtonStyle.success, row=0)
    async def upgrade_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 1)

    @discord.ui.button(label="#3", style=discord.ButtonStyle.success, row=0)
    async def upgrade_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 2)

    @discord.ui.button(label="#4", style=discord.ButtonStyle.success, row=0)
    async def upgrade_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 3)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.page = max(0, self.page - 1)
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        await safe_defer(interaction)

    @discord.ui.button(label="К бизнесам", style=discord.ButtonStyle.primary, row=1)
    async def back_to_businesses(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            view = OwnedBusinessesView(self.cog, self.user_id, self.guild_id, self.page)
            view.total_pages = await view._page_count()
            view._sync_buttons()
            embed = await self.cog.build_owned_businesses_embed(self.user_id, self.guild_id, view.page, sync_table=True)
            await interaction.edit_original_response(embed=embed, view=view)
            view.message = await interaction.original_response()

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="Дальше", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.total_pages = await self._page_count()
            self.page = min(self.total_pages - 1, self.page + 1)
            await self._refresh_from_interaction(interaction)


class AutoCollectView(BaseBusinessView):
    def __init__(self, cog: "BusinessCog", user_id: int, guild_id: int):
        super().__init__(cog, user_id, guild_id, 0)
        self._sync_buttons({"owned": False, "enabled": False, "interval_hours": 6})

    def _sync_buttons(self, state: dict[str, Any]):
        owned = bool(state.get("owned"))
        enabled = bool(state.get("enabled"))
        interval_hours = int(state.get("interval_hours", 6) or 6)

        self.toggle_enabled.label = "Выключить" if enabled else "Включить"
        self.toggle_enabled.style = discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success
        self.toggle_enabled.disabled = not owned

        self.refresh.disabled = False
        self.back_to_businesses.disabled = False

        self.interval_select.disabled = not owned
        for option in self.interval_select.options:
            option.default = option.value == str(interval_hours)

    async def _refresh_from_interaction(self, interaction: discord.Interaction):
        state = await self.cog.get_autocollect_state(self.user_id, self.guild_id)
        self._sync_buttons(state)
        embed = await self.cog.build_autocollect_embed(self.user_id, self.guild_id)
        await self._edit_deferred_response(interaction, embed=embed)

    @discord.ui.button(label="Включить", style=discord.ButtonStyle.success, row=0)
    async def toggle_enabled(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            if not db.user_field_supported("business_autocollect"):
                await interaction.followup.send(
                    "Автосбор временно недоступен. Добавь колонку `business_autocollect` в таблицу `users`.",
                    ephemeral=True,
                )
                return
            state = await self.cog.get_autocollect_state(self.user_id, self.guild_id)
            if not state["owned"]:
                await interaction.followup.send("Сначала купи апгрейд автосбора в `/shop`.", ephemeral=True)
                return
            await self.cog.update_autocollect_state(
                self.user_id,
                self.guild_id,
                enabled=not state["enabled"],
            )
            await self._refresh_from_interaction(interaction)

    @discord.ui.select(
        placeholder="Выбери интервал автосбора",
        row=1,
        options=[
            discord.SelectOption(label="Каждый 1 час", value="1"),
            discord.SelectOption(label="Каждые 3 часа", value="3"),
            discord.SelectOption(label="Каждые 6 часов", value="6", default=True),
            discord.SelectOption(label="Каждые 12 часов", value="12"),
            discord.SelectOption(label="Каждые 24 часа", value="24"),
        ],
    )
    async def interval_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            if not db.user_field_supported("business_autocollect"):
                await interaction.followup.send(
                    "Автосбор временно недоступен. Добавь колонку `business_autocollect` в таблицу `users`.",
                    ephemeral=True,
                )
                return
            state = await self.cog.get_autocollect_state(self.user_id, self.guild_id)
            if not state["owned"]:
                await interaction.followup.send("Сначала купи апгрейд автосбора в `/shop`.", ephemeral=True)
                return
            collected, payload = await self.cog.collect_business_income(self.user_id, self.guild_id)
            await self.cog.update_autocollect_state(
                self.user_id,
                self.guild_id,
                interval_hours=int(select.values[0]),
            )
            await self._refresh_from_interaction(interaction)
            if collected:
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_from_interaction(interaction)

    @discord.ui.button(label="Назад к бизнесам", style=discord.ButtonStyle.primary, row=2)
    async def back_to_businesses(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            view = OwnedBusinessesView(self.cog, self.user_id, self.guild_id)
            view.total_pages = await view._page_count()
            view._sync_buttons()
            embed = await self.cog.build_owned_businesses_embed(self.user_id, self.guild_id, view.page, sync_table=True)
            if not await safe_edit_original_response(interaction, embed=embed, view=view):
                return
            view.message = await interaction.original_response()


class BusinessCog(commands.Cog, name="Business"):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self.autocollect_loop.is_running():
            self.autocollect_loop.start()

    def cog_unload(self):
        self.autocollect_loop.cancel()

    @tasks.loop(minutes=5)
    async def autocollect_loop(self):
        if not db.user_field_supported("business_autocollect"):
            return

        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("users").select("user_id,guild_id,business_autocollect").execute()
            )
            for row in result.data or []:
                state = get_business_autocollect_state(row)
                user_id = row.get("user_id")
                guild_id = row.get("guild_id")
                if not state["owned"] or not state["enabled"] or user_id is None or guild_id is None:
                    continue
                await process_business_autocollect(int(user_id), int(guild_id))
        except Exception as exc:
            error_msg = str(exc)
            if "business_autocollect" in error_msg and ("does not exist" in error_msg or "schema cache" in error_msg):
                db._mark_user_field_unsupported("business_autocollect")
                return
            print(f"Business autocollect loop error: {exc}")

    @autocollect_loop.before_loop
    async def before_autocollect_loop(self):
        await self.bot.wait_until_ready()

    async def get_autocollect_state(self, user_id: int, guild_id: int) -> dict[str, Any]:
        user = await db.get_user(user_id, guild_id)
        return get_business_autocollect_state(user or {})

    async def update_autocollect_state(self, user_id: int, guild_id: int, **updates) -> dict[str, Any] | None:
        if not db.user_field_supported("business_autocollect"):
            return get_business_autocollect_state({})

        user = await db.get_user(user_id, guild_id)
        if not user:
            return None

        state = get_business_autocollect_state(user)
        state.update(updates)
        if "interval_hours" in state:
            state["interval_hours"] = max(1, min(24, int(state["interval_hours"] or 6)))
        user["business_autocollect"] = state
        await db.update_user(user_id, guild_id, {"business_autocollect": state})
        return state

    async def build_autocollect_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        summaries, totals = await self.get_owned_summaries(user_id, guild_id)
        state = get_business_autocollect_state(user or {})

        if not db.user_field_supported("business_autocollect"):
            embed = discord.Embed(
                title="🤖 АВТОСБОР БИЗНЕСОВ",
                description=(
                    "Автосбор временно недоступен.\n"
                    "В таблице `users` нет колонки `business_autocollect`, поэтому настройки не сохраняются."
                ),
                color=COLORS["warning"],
                timestamp=datetime.now(timezone.utc),
            )
            embed.add_field(
                name="Что нужно сделать",
                value="Добавь колонку `business_autocollect` в Supabase и перезапусти бота.",
                inline=False,
            )
            return embed

        enabled_text = "Включён" if state["enabled"] else "Выключен"
        owned_text = "Куплен" if state["owned"] else "Не куплен"
        last_run = state.get("last_run")
        if last_run:
            try:
                last_run_dt = datetime.fromisoformat(str(last_run))
                if last_run_dt.tzinfo is None:
                    last_run_dt = last_run_dt.replace(tzinfo=timezone.utc)
                next_run_dt = last_run_dt.astimezone(timezone.utc) + timedelta(hours=state["interval_hours"])
                next_run_text = format_discord_deadline(next_run_dt)
            except ValueError:
                next_run_text = "Сразу после включения"
        else:
            next_run_text = "Сразу после включения"

        embed = discord.Embed(
            title="🤖 АВТОСБОР БИЗНЕСОВ",
            description=(
                f"Статус апгрейда: **{owned_text}**\n"
                f"Автосбор: **{enabled_text}**\n"
                f"Интервал: **каждые {state['interval_hours']} ч**"
            ),
            color=COLORS["info"] if state["owned"] else COLORS["warning"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Бизнесов под управлением", value=f"**{totals['total_owned']}**", inline=True)
        embed.add_field(name="Пассив в день", value=f"**{format_money(totals['total_income_per_day'])}**", inline=True)
        embed.add_field(name="Готово сейчас", value=f"**{totals['ready_total']}**", inline=True)
        embed.add_field(name="Автоматически собрано", value=f"**{format_money(state['total_collected'])}**", inline=True)
        embed.add_field(name="Циклов собрано", value=f"**{state['total_cycles']}**", inline=True)
        embed.add_field(name="Следующий запуск", value=f"**{next_run_text}**", inline=True)

        if not state["owned"]:
            embed.add_field(
                name="Как получить",
                value="Открой `/shop`, перейди во вкладку улучшений и купи **Автосбор бизнесов**.",
                inline=False,
            )
        else:
            embed.add_field(
                name="Как это работает",
                value=(
                    "Бот сам проверяет бизнесы по таймеру и забирает готовую прибыль.\n"
                    "Ты можешь включать/выключать автосбор и менять интервал ниже."
                ),
                inline=False,
            )

        embed.set_footer(text="Автосбор проверяется фоновым циклом бота и дополнительно при использовании команд.")
        return embed

    async def get_owned_summaries(self, user_id: int, guild_id: int, sync_table: bool = False):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return [], {
                "user": None,
                "normalized_businesses": {},
                "balance": 0,
                "total_owned": 0,
                "total_invested": 0,
                "total_earned": 0,
                "total_income_per_day": 0,
                "ready_total": 0,
            }

        user, normalized_businesses, _ = await ensure_unique_businesses(
            user_id,
            guild_id,
            user=user,
            sync_table=sync_table,
        )
        if not user:
            return [], {
                "user": None,
                "normalized_businesses": {},
                "balance": 0,
                "total_owned": 0,
                "total_invested": 0,
                "total_earned": 0,
                "total_income_per_day": 0,
                "ready_total": 0,
            }
        now = datetime.now(timezone.utc)
        summaries = []
        total_invested = 0
        total_earned = 0
        total_income_per_day = 0
        ready_total = 0

        for business_id, instances in sorted(normalized_businesses.items(), key=lambda item: int(item[0])):
            business = BUSINESSES.get(int(business_id))
            if business is None or not instances:
                continue

            ready_count = 0
            total_business_earned = 0
            next_ready_delta = None
            next_ready_at = None
            ready_value = 0
            daily_income = 0
            invested = 0
            cycle_income = 0
            upgrade_level = 0

            for instance in instances:
                total_business_earned += int(instance.get("total_earned", 0))
                instance_income = business_income_for_instance(business, instance)
                cycle_income += instance_income
                daily_income += business_daily_income_for_instance(business, instance)
                invested += business["cost"] + business_upgrade_spent(business, instance)
                upgrade_level = max(upgrade_level, business_upgrade_level(instance))
                last_collect = parse_utc_timestamp(instance.get("last_collect"), now)
                ready_at = last_collect + timedelta(hours=business["time"])
                if now >= ready_at:
                    ready_count += 1
                    ready_value += instance_income
                else:
                    delta = ready_at - now
                    if next_ready_delta is None or delta < next_ready_delta:
                        next_ready_delta = delta
                        next_ready_at = ready_at

            count = len(instances)
            ready_total += ready_count
            total_invested += invested
            total_earned += total_business_earned
            total_income_per_day += daily_income
            next_upgrade_cost = None if upgrade_level >= BUSINESS_UPGRADE_MAX_LEVEL else business_upgrade_cost(business, upgrade_level)

            summaries.append(
                {
                    "id": int(business_id),
                    "business": business,
                    "name": display_business_name(business),
                    "count": count,
                    "ready_count": ready_count,
                    "ready_value": ready_value,
                    "next_ready_delta": next_ready_delta,
                    "next_ready_at": next_ready_at,
                    "total_earned": total_business_earned,
                    "daily_income": daily_income,
                    "invested": invested,
                    "income_per_cycle": cycle_income,
                    "upgrade_level": upgrade_level,
                    "next_upgrade_cost": next_upgrade_cost,
                    "next_upgrade_text": "максимум" if next_upgrade_cost is None else format_money(next_upgrade_cost),
                }
            )

        totals = {
            "user": user,
            "normalized_businesses": normalized_businesses,
            "balance": user.get("balance", 0),
            "total_owned": count_owned_businesses(normalized_businesses),
            "total_invested": total_invested,
            "total_earned": total_earned,
            "total_income_per_day": int(total_income_per_day),
            "ready_total": ready_total,
        }
        return summaries, totals

    async def build_businesses_embed(self, user_id: int, guild_id: int, page: int, sync_table: bool = False) -> discord.Embed:
        _, totals = await self.get_owned_summaries(user_id, guild_id, sync_table=sync_table)
        normalized_businesses = totals["normalized_businesses"]
        balance = totals["balance"]

        items = sorted(BUSINESSES.items())
        max_page = max(0, math.ceil(len(items) / BUSINESSES_PER_PAGE) - 1)
        page = max(0, min(page, max_page))
        start = page * BUSINESSES_PER_PAGE
        page_items = items[start:start + BUSINESSES_PER_PAGE]

        embed = discord.Embed(
            title="🏢 БИЗНЕС-МАГАЗИН",
            description=(
                f"Страница **{page + 1}/{max_page + 1}** • Куплено бизнесов: **{totals['total_owned']}**\n"
                f"Баланс: **{format_money(balance)}** • Пассив/день: **{format_money(totals['total_income_per_day'])}** • Готово: **{totals['ready_total']}**\n"
                f"Листай по 5 бизнесов и покупай кнопками ниже.\n"
                f"Управление купленными бизнесами находится в `/mybusinesses`."
            ),
            color=COLORS["purple"],
            timestamp=datetime.now(timezone.utc),
        )

        for slot, (business_id, business) in enumerate(page_items, start=1):
            owned_count = len(normalized_businesses.get(str(business_id), []))
            embed.add_field(
                name=f"{slot}. {display_business_name(business)}",
                value=market_card_value(business_id, business, balance, owned_count),
                inline=False,
            )

        embed.set_footer(text="Можно купить только 1 бизнес каждого типа. Управление находится в /mybusinesses.")
        return embed

    async def build_owned_businesses_embed(self, user_id: int, guild_id: int, page: int, sync_table: bool = False) -> discord.Embed:
        summaries, totals = await self.get_owned_summaries(user_id, guild_id, sync_table=sync_table)
        state = await self.get_autocollect_state(user_id, guild_id)
        systems_cog = self.bot.get_cog("Systems")
        business_multiplier = 1.0
        active_event = None
        if systems_cog is not None:
            business_multiplier, active_event = systems_cog.get_reward_multiplier(guild_id, "business")
        max_page = max(0, math.ceil(max(1, len(summaries)) / OWNED_BUSINESSES_PER_PAGE) - 1)
        page = max(0, min(page, max_page))
        start = page * OWNED_BUSINESSES_PER_PAGE
        page_items = summaries[start:start + OWNED_BUSINESSES_PER_PAGE]

        embed = discord.Embed(
            title="🏦 МОИ БИЗНЕСЫ",
            description=(
                f"Страница **{page + 1}/{max_page + 1}** • Всего бизнесов: **{totals['total_owned']}** • Готово: **{totals['ready_total']}**\n"
                f"Баланс: **{format_money(totals['balance'])}** • Пассив/день: **{format_money(totals['total_income_per_day'])}**"
            ),
            color=COLORS["gold"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Заработано всего", value=f"**{format_money(totals['total_earned'])}**", inline=True)
        embed.add_field(name="Вложено в бизнесы", value=f"**{format_money(totals['total_invested'])}**", inline=True)
        embed.add_field(name="Готово к сбору", value=f"**{totals['ready_total']} выплат(ы)**", inline=True)
        embed.add_field(
            name="Автосбор",
            value=(
                f"**{'Включён' if state['enabled'] else 'Выключен'}**\n"
                f"Интервал: **{state['interval_hours']}ч**"
                if state["owned"]
                else "**Не куплен**\nКупить можно в `/shop`"
            ),
            inline=True,
        )
        if active_event is not None and business_multiplier < 1:
            embed.add_field(
                name="Событие рынка",
                value=f"**{active_event['name']}**\nДоход сейчас идёт с множителем **x{business_multiplier:.2f}**.",
                inline=True,
            )

        if not page_items:
            embed.add_field(name="Пока пусто", value="У тебя еще нет бизнесов. Открой `/businesses` и купи первый источник пассивного дохода.", inline=False)
            embed.set_footer(text="Кнопка «Собрать всё» автоматически забирает доход со всех готовых бизнесов.")
            return embed

        for item in page_items:
            embed.add_field(
                name=f"{display_business_name(item['business'])}",
                value=portfolio_card_value(item),
                inline=False,
            )

        embed.set_footer(text="Кнопка «Собрать всё» собирает прибыль со всех готовых бизнесов сразу.")
        return embed

    async def build_business_upgrades_embed(self, user_id: int, guild_id: int, page: int) -> discord.Embed:
        summaries, totals = await self.get_owned_summaries(user_id, guild_id)
        max_page = max(0, math.ceil(max(1, len(summaries)) / OWNED_BUSINESSES_PER_PAGE) - 1)
        page = max(0, min(page, max_page))
        start = page * OWNED_BUSINESSES_PER_PAGE
        page_items = summaries[start:start + OWNED_BUSINESSES_PER_PAGE]

        embed = discord.Embed(
            title="⬆️ АПГРЕЙДЫ БИЗНЕСОВ",
            description=(
                f"Страница **{page + 1}/{max_page + 1}**\n"
                f"Баланс: **{format_money(totals['balance'])}**\n"
                f"Каждый уровень апгрейда даёт примерно **+25%** к доходу конкретного бизнеса."
            ),
            color=COLORS["purple"],
            timestamp=datetime.now(timezone.utc),
        )

        if not page_items:
            embed.add_field(name="Пока пусто", value="Сначала купи бизнес в `/businesses`.", inline=False)
            return embed

        for item in page_items:
            if item["next_upgrade_cost"] is None:
                upgrade_text = "Максимальный уровень"
            else:
                upgrade_text = f"Следующий апгрейд: **{format_money(item['next_upgrade_cost'])}**"

            embed.add_field(
                name=display_business_name(item["business"]),
                value=(
                    f"Уровень: **{item['upgrade_level']}/{BUSINESS_UPGRADE_MAX_LEVEL}**\n"
                    f"Доход за цикл: **{format_money(item['income_per_cycle'])}**\n"
                    f"Доход в день: **{format_money(item['daily_income'])}**\n"
                    f"{upgrade_text}"
                ),
                inline=False,
            )

        embed.set_footer(text="Кнопки ниже улучшают бизнесы с текущей страницы.")
        return embed

    async def upgrade_business(self, user_id: int, guild_id: int, business_id: int):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            user, normalized_businesses, _ = await ensure_unique_businesses(user_id, guild_id, user=user, sync_table=False)
            if not user:
                return False, "Не удалось загрузить профиль."

            instances = normalized_businesses.get(str(business_id), [])
            business = BUSINESSES.get(int(business_id))
            if business is None or not instances:
                return False, "У тебя нет такого бизнеса."

            instance = instances[0]
            current_level = business_upgrade_level(instance)
            if current_level >= BUSINESS_UPGRADE_MAX_LEVEL:
                return False, "Этот бизнес уже улучшен до максимума."

            cost = business_upgrade_cost(business, current_level)
            if int(user.get("balance", 0) or 0) < cost:
                return False, f"Не хватает денег. Нужно **{format_money(cost)}**."

            user["balance"] = int(user.get("balance", 0) or 0) - cost
            instance["upgrade_level"] = current_level + 1
            normalized_businesses[str(business_id)] = [instance]
            user["businesses"] = normalized_businesses
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "businesses": normalized_businesses})
            await db.sync_server_businesses(user_id, guild_id, normalized_businesses)

        new_income = business_income_for_instance(business, instance)
        embed = discord.Embed(
            title="Бизнес улучшен",
            description=f"**{display_business_name(business)}** получил новый уровень.",
            color=COLORS["success"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Новый уровень", value=f"**{instance['upgrade_level']}/{BUSINESS_UPGRADE_MAX_LEVEL}**", inline=True)
        embed.add_field(name="Доход за цикл", value=f"**{format_money(new_income)}**", inline=True)
        embed.add_field(name="Баланс", value=f"**{format_money(user['balance'])}**", inline=True)
        return True, embed

    async def purchase_business(self, user_id: int, guild_id: int, business_id: int):
        business = BUSINESSES.get(business_id)
        if business is None:
            return False, "Бизнес не найден."

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            user, normalized_businesses, removed = await ensure_unique_businesses(
                user_id,
                guild_id,
                user=user,
                sync_table=False,
            )
            if not user:
                return False, "Не удалось загрузить профиль."

            if normalized_businesses.get(str(business_id)):
                legacy_note = " Лишние дубликаты были очищены." if removed > 0 else ""
                return False, f"У тебя уже есть {display_business_name(business)}. Разрешён только 1 бизнес каждого типа.{legacy_note}"
            if user["balance"] < business["cost"]:
                return False, f"Для покупки нужно {format_money(business['cost'])}."

            now = datetime.now(timezone.utc)
            user["balance"] -= business["cost"]
            normalized_businesses.setdefault(str(business_id), []).append(create_business_instance(now))
            user["businesses"] = normalized_businesses
            await db.update_user(user_id, guild_id, user)
            await db.sync_server_businesses(user_id, guild_id, normalized_businesses)

        asyncio.create_task(check_quest_progress(user_id, guild_id, "business", 1))

        owned_count = len(user["businesses"].get(str(business_id), []))
        badge, tagline = business_theme(business)
        embed = discord.Embed(
            title="Бизнес куплен",
            description=f"**{display_business_name(business)}** теперь приносит тебе пассивный доход.",
            color=COLORS["success"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Тип", value=f"`{badge}` `{business_tier(business)}`", inline=True)
        embed.add_field(name="Цена", value=f"**{format_money(business['cost'])}**", inline=True)
        embed.add_field(name="Количество", value=f"**x{owned_count}**", inline=True)
        embed.add_field(name="Цикл", value=f"**{format_money(business['income'])}** / {business['time']}ч", inline=True)
        embed.add_field(name="В день", value=f"**{format_money(business_daily_income(business))}**", inline=True)
        embed.add_field(name="Баланс", value=f"**{format_money(user['balance'])}**", inline=True)
        embed.add_field(name="Комментарий", value=tagline, inline=False)
        return True, embed

    async def collect_business_income(self, user_id: int, guild_id: int):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            user, normalized_businesses, _ = await ensure_unique_businesses(
                user_id,
                guild_id,
                user=user,
                sync_table=False,
            )
            if not user:
                return False, "Не удалось загрузить профиль."
            if not normalized_businesses:
                return False, "У тебя пока нет бизнесов."

            now = datetime.now(timezone.utc)
            total_collected = 0
            collected_instances = 0
            collected_summary = []
            systems_cog = self.bot.get_cog("Systems")
            multiplier = 1.0
            active_event = None
            if systems_cog is not None:
                multiplier, active_event = systems_cog.get_reward_multiplier(guild_id, "business")

            for business_id, instances in normalized_businesses.items():
                business = BUSINESSES.get(int(business_id))
                if business is None:
                    continue

                collected_here = 0
                collected_amount = 0
                for instance in instances:
                    last_collect = parse_utc_timestamp(instance.get("last_collect"), now)
                    if now - last_collect >= timedelta(hours=business["time"]):
                        payout = int(business_income_for_instance(business, instance) * multiplier)
                        collected_here += 1
                        collected_instances += 1
                        collected_amount += payout
                        total_collected += payout
                        instance["last_collect"] = now.isoformat()
                        instance["total_earned"] = int(instance.get("total_earned", 0)) + payout

                if collected_here > 0:
                    collected_summary.append(
                        {
                        "name": display_business_name(business),
                            "count": collected_here,
                            "amount": collected_amount,
                        }
                    )

            if total_collected == 0:
                return False, "Сейчас нет готовых выплат с бизнесов."

            user["businesses"] = normalized_businesses
            user["balance"] += total_collected
            from easter_event import grant_easter_drops

            easter_cog = self.bot.get_cog("EasterEvent")
            easter_lines = grant_easter_drops(
                user,
                "business_collect",
                guild_state=easter_cog.get_cached_guild_state(guild_id) if easter_cog else None,
            )
            user.setdefault("quest_progress", {})
            user["quest_progress"]["collect_business"] = user["quest_progress"].get("collect_business", 0) + collected_instances
            await db.update_user(user_id, guild_id, user)
            await db.sync_server_businesses(user_id, guild_id, normalized_businesses)

        asyncio.create_task(check_quest_progress(user_id, guild_id, "collect_business", collected_instances))
        asyncio.create_task(
            record_player_progress(
                user_id,
                guild_id,
                action="collect_business",
                amount=collected_instances,
                money=total_collected,
                business_cycles=collected_instances,
            )
        )
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is not None:
            asyncio.create_task(systems_cog.progress_contracts(user_id, guild_id, "collect_business", collected_instances))

        collected_summary.sort(key=lambda item: item["amount"], reverse=True)
        summary_lines = [
            f"**{item['name']}** x{item['count']} -> +{format_money(item['amount'])}"
            for item in collected_summary[:8]
        ]
        hidden_count = len(collected_summary) - len(summary_lines)
        if hidden_count > 0:
            summary_lines.append(f"...и ещё {hidden_count} типов бизнеса")

        embed = discord.Embed(
            title="Доход собран",
            description=(
                f"Собрано из **{collected_instances}** циклов бизнеса.\n"
                f"Всего получено: **{format_money(total_collected)}**"
            ),
            color=COLORS["success"],
            timestamp=datetime.now(timezone.utc),
        )
        if active_event is not None and multiplier < 1:
            embed.add_field(
                name="Активное событие",
                value=f"Сейчас действует **{active_event['name']}**, поэтому доход временно снижен до **x{multiplier:.2f}**.",
                inline=False,
            )
        embed.add_field(name="Разбивка", value="\n".join(summary_lines), inline=False)
        embed.add_field(name="Новый баланс", value=f"**{format_money(user['balance'])}**", inline=False)
        if easter_lines:
            embed.add_field(name="Пасха 2026", value="\n".join(easter_lines), inline=False)
        return True, embed

    @app_commands.command(name="businesses", description="Посмотреть бизнесы для покупки")
    async def businesses(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return
        view = BusinessShopView(self, interaction.user.id, interaction.guild_id)
        await view._load_owned_state(sync_table=True)
        view._sync_buttons()
        embed = await self.build_businesses_embed(interaction.user.id, interaction.guild_id, view.page)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="mybusinesses", description="Посмотреть свои бизнесы")
    async def mybusinesses(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return
        view = OwnedBusinessesView(self, interaction.user.id, interaction.guild_id)
        view.total_pages = await view._page_count()
        view._sync_buttons()
        embed = await self.build_owned_businesses_embed(interaction.user.id, interaction.guild_id, view.page, sync_table=True)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

async def setup(bot):
    await bot.add_cog(BusinessCog(bot))
