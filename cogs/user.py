from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.bank import deposit_snapshot
from cogs.fishing_world import describe_world_lines, get_world_state
from cogs.house import _refresh_garden_state
from config import BUSINESSES, COLORS, FISHING_RODS, VIP_LEVELS, get_vip_level
from database import db, get_user_lock, supabase
from inventory_system import get_general_items
from progression import (
    PROFILE_THEMES,
    PROFILE_TITLES,
    SEASON_FREE_REWARDS,
    SEASON_MAX_TIERS,
    SEASON_NAME,
    SEASON_PREMIUM_COST,
    SEASON_PREMIUM_REWARDS,
    battle_pass_progress_to_next,
    battle_pass_tier,
    buy_premium_pass,
    claim_battle_pass_reward,
    contract_rerolls_for_vip,
    contract_slots_for_vip,
    ensure_battle_pass_state,
    get_profile_state,
    get_profile_theme_image,
    reward_text,
    unlock_theme,
    unlock_title,
)
from utils import (
    check_channel,
    format_discord_deadline,
    get_business_autocollect_state,
    get_preferred_guild_text_channel,
    get_kyiv_timezone,
    get_guild_runtime_settings,
    get_user_preferences,
    has_active_shield,
    notification_type_enabled,
    normalize_businesses,
    normalize_datetime,
    resolve_activity_role_id,
    resolve_allowed_channel_id,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
    smart_notifications_enabled,
)

AUTO_COLLECT_UPGRADE = {
    "name": "Автосбор бизнесов",
    "price": 250,
    "currency": "gems",
    "description": "Автоматически собирает готовый доход с бизнесов по выбранному интервалу.",
}

SERVER_ITEMS_PER_PAGE = 3
VIP_LEVELS_PER_PAGE = 3
TITLE_ITEMS_PER_PAGE = 3
KYIV_TZ = get_kyiv_timezone()
SMART_NOTIFICATION_SETTINGS: dict[str, dict[str, str]] = {
    "notify_deposit": {"label": "Депозит", "marker": "deposit_ready"},
    "notify_rent": {"label": "Аренда", "marker": "rent_ready"},
    "notify_business": {"label": "Бизнес", "marker": "business_ready"},
    "notify_harvest": {"label": "Урожай", "marker": "harvest_ready"},
    "notify_daily_streak": {"label": "Daily streak", "marker": "daily_warning"},
}


async def _remember_interaction_message(
    interaction: discord.Interaction,
    current: discord.Message | None = None,
) -> discord.Message | None:
    try:
        return await interaction.original_response()
    except Exception:
        return interaction.message or current

TITLE_SHOP_ITEMS: list[dict[str, Any]] = [
    {
        "key": "wallet_destroyer",
        "name": "Убийца зарплат",
        "price": 45_000,
        "currency": "money",
        "description": "Для тех, кто тратит быстрее, чем считает.",
    },
    {
        "key": "lord_of_memes",
        "name": "Лорд мемов",
        "price": 60_000,
        "currency": "money",
        "description": "Немного пафоса, немного абсурда и максимум самоуважения.",
    },
    {
        "key": "pro_afk",
        "name": "Профессиональный АФК",
        "price": 75_000,
        "currency": "money",
        "description": "На минуту отошел, а вернулся уже легендой.",
    },
    {
        "key": "fish_psychic",
        "name": "Рыбный телепат",
        "price": 90_000,
        "currency": "money",
        "description": "Чувствует поклевку раньше, чем дернется поплавок.",
    },
    {
        "key": "panic_investor",
        "name": "Паник-инвестор",
        "price": 110_000,
        "currency": "money",
        "description": "Покупает на хаях, продает на нервах, но делает это красиво.",
    },
    {
        "key": "sofa_tycoon",
        "name": "Диванный магнат",
        "price": 135_000,
        "currency": "money",
        "description": "Строит империю, не вставая с дивана.",
    },
]

THEME_SHOP_ITEMS: list[dict[str, Any]] = [
    {
        "kind": "theme",
        "key": "sakura",
        "name": "Sakura",
        "price": 125_000,
        "currency": "money",
        "description": "Нежный пасхальный фон профиля с большим баннером и мягкой розовой темой.",
        "preview_url": str(PROFILE_THEMES.get("sakura", {}).get("image_url") or ""),
    },
    {
        "kind": "theme",
        "key": "void",
        "name": "Void",
        "price": 165_000,
        "currency": "money",
        "description": "Темная космическая тема профиля с анимированным баннером и холодным глубоким вайбом.",
        "preview_url": str(PROFILE_THEMES.get("void", {}).get("image_url") or ""),
    },
]


def build_progress_bar(current: int, total: int, length: int = 10) -> str:
    total = max(1, int(total))
    current = max(0, min(int(current), total))
    filled = int(round((current / total) * length))
    filled = max(0, min(length, filled))
    return f"{'-' * filled}{'-' * (length - filled)}"


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def format_price(value: int | float, currency: str) -> str:
    return f"{int(value):,} гем." if str(currency).lower() == "gems" else format_money(value)


def clamp_text(value: str | None, limit: int = 150) -> str:
    text = (value or "").strip()
    if not text:
        return "Без описания."
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def format_vip_name(level: int) -> str:
    names = {
        0: "Без VIP",
        1: "Бронзовый VIP",
        2: "Серебряный VIP",
        3: "Золотой VIP",
        4: "Алмазный VIP",
    }
    return names.get(level, f"VIP {level}")


def vip_status_label(current_level: int, level: int) -> str:
    if current_level == level:
        return "Текущий"
    if current_level > level:
        return "Уже куплен"
    return "Доступен"


def general_item_quantity(user: dict[str, Any], item_type: str, code: str) -> int:
    total = 0
    for item in get_general_items(user):
        if str(item.get("item_type") or "") != item_type:
            continue
        if str(item.get("code") or "") != code:
            continue
        total += int(item.get("quantity", 0) or 0)
    return total


class ExchangeModal(discord.ui.Modal):
    def __init__(self, view: "ShopView", direction: str):
        self.shop_view = view
        self.direction = direction
        title = "Обмен денег на гемы" if direction == "to_gems" else "Обмен гемов на деньги"
        super().__init__(title=title)
        placeholder = "Сколько гемов купить" if direction == "to_gems" else "Сколько гемов продать"
        self.amount = discord.ui.TextInput(label="Количество", placeholder=placeholder, max_length=10)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.amount.value).strip().replace(",", "")
        if not raw_value.isdigit() or int(raw_value) <= 0:
            await interaction.response.send_message("Введи положительное число.", ephemeral=True)
            return

        amount = int(raw_value)
        async with get_user_lock(self.shop_view.user_id):
            user = await db.get_user(self.shop_view.user_id, self.shop_view.guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return

            if self.direction == "to_gems":
                cost = amount * 1000
                if int(user.get("balance", 0) or 0) < cost:
                    await interaction.response.send_message(
                        f"Не хватает денег. Нужно: **{format_money(cost)}**.",
                        ephemeral=True,
                    )
                    return
                user["balance"] = int(user.get("balance", 0) or 0) - cost
                user["gems"] = int(user.get("gems", 0) or 0) + amount
                title = "Обмен выполнен"
                description = (
                    f"Потрачено: **{format_money(cost)}**\n"
                    f"Получено: **{amount} гем.**\n"
                    f"Баланс: **{format_money(user['balance'])}**\n"
                    f"Гемы: **{int(user['gems']):,}**"
                )
            else:
                payout = amount * 900
                if int(user.get("gems", 0) or 0) < amount:
                    await interaction.response.send_message(
                        f"Не хватает гемов. Нужно: **{amount}**.",
                        ephemeral=True,
                    )
                    return
                user["gems"] = int(user.get("gems", 0) or 0) - amount
                user["balance"] = int(user.get("balance", 0) or 0) + payout
                title = "Обмен выполнен"
                description = (
                    f"Потрачено: **{amount} гем.**\n"
                    f"Получено: **{format_money(payout)}**\n"
                    f"Баланс: **{format_money(user['balance'])}**\n"
                    f"Гемы: **{int(user['gems']):,}**"
                )

            await db.update_user(self.shop_view.user_id, self.shop_view.guild_id, user)
            self.shop_view.user_data = user

        await interaction.response.send_message(
            embed=discord.Embed(title=title, description=description, color=COLORS["success"]),
            ephemeral=True,
        )
        self.shop_view._sync_buttons()
        if self.shop_view.message is not None:
            await self.shop_view.message.edit(embed=self.shop_view.build_embed(), view=self.shop_view)


class _BaseShopView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, user_data: dict[str, Any], custom_items: list[dict[str, Any]]):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.user_data = user_data or {}
        self.custom_items = sorted(custom_items or [], key=lambda item: int(item.get("id", 0) or 0))
        self.active_page = "overview"
        self.page_index = 0
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self.customize_btn.row = 2
        self.clear_items()
        for item in (
            self.overview_btn,
            self.vip_btn,
            self.exchange_btn,
            self.upgrades_btn,
            self.server_btn,
            self.prev_btn,
            self.action_btn_1,
            self.action_btn_2,
            self.action_btn_3,
            self.next_btn,
            self.customize_btn,
        ):
            self.add_item(item)
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню магазина открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        self.message = await _remember_interaction_message(interaction, self.message)

    async def _reload_user(self):
        self.user_data = await db.get_user(self.user_id, self.guild_id) or {}

    def _is_role_item(self, item: dict[str, Any]) -> bool:
        item_type = str(item.get("item_type") or item.get("type") or "").lower()
        return bool(item.get("role_id")) or item_type in {"role", "discord_role"}

    def _server_item_kind(self, item: dict[str, Any]) -> str:
        if self._is_role_item(item):
            return "Discord-роль"
        item_type = str(item.get("item_type") or item.get("type") or "").strip()
        return item_type or "Предмет"

    def _get_vip_levels(self) -> list[tuple[int, dict[str, Any]]]:
        return [(level, data) for level, data in VIP_LEVELS.items() if level > 0]

    def _current_vip_slice(self) -> list[tuple[int, dict[str, Any]]]:
        levels = self._get_vip_levels()
        start = self.page_index * VIP_LEVELS_PER_PAGE
        return levels[start:start + VIP_LEVELS_PER_PAGE]

    def _max_vip_page(self) -> int:
        levels = self._get_vip_levels()
        if not levels:
            return 0
        return max(0, (len(levels) - 1) // VIP_LEVELS_PER_PAGE)

    def _current_server_items(self) -> list[dict[str, Any]]:
        start = self.page_index * SERVER_ITEMS_PER_PAGE
        return self.custom_items[start:start + SERVER_ITEMS_PER_PAGE]

    def _max_server_page(self) -> int:
        if not self.custom_items:
            return 0
        return max(0, (len(self.custom_items) - 1) // SERVER_ITEMS_PER_PAGE)

    def _current_title_items(self) -> list[dict[str, Any]]:
        items = [dict(item) for item in THEME_SHOP_ITEMS]
        items.extend({"kind": "title", **item} for item in TITLE_SHOP_ITEMS)
        start = self.page_index * TITLE_ITEMS_PER_PAGE
        return items[start:start + TITLE_ITEMS_PER_PAGE]

    def _max_title_page(self) -> int:
        total_items = len(THEME_SHOP_ITEMS) + len(TITLE_SHOP_ITEMS)
        if total_items <= 0:
            return 0
        return max(0, (total_items - 1) // TITLE_ITEMS_PER_PAGE)

    def _sync_buttons(self):
        self.overview_btn.style = discord.ButtonStyle.primary if self.active_page == "overview" else discord.ButtonStyle.secondary
        self.vip_btn.style = discord.ButtonStyle.primary if self.active_page == "vip" else discord.ButtonStyle.secondary
        self.exchange_btn.style = discord.ButtonStyle.primary if self.active_page == "exchange" else discord.ButtonStyle.secondary
        self.upgrades_btn.style = discord.ButtonStyle.primary if self.active_page == "upgrades" else discord.ButtonStyle.secondary
        self.server_btn.style = discord.ButtonStyle.primary if self.active_page == "server" else discord.ButtonStyle.secondary
        self.customize_btn.style = discord.ButtonStyle.primary if self.active_page == "customize" else discord.ButtonStyle.secondary

        self.prev_btn.disabled = True
        self.next_btn.disabled = True
        self.prev_btn.label = "-"
        self.next_btn.label = "-"

        for action_button in (self.action_btn_1, self.action_btn_2, self.action_btn_3):
            action_button.disabled = True
            action_button.style = discord.ButtonStyle.secondary
            action_button.label = "Недоступно"
            action_button.emoji = None

        if self.active_page == "overview":
            premium_open = bool(ensure_battle_pass_state(self.user_data).get("premium_unlocked"))
            self.action_btn_1.disabled = premium_open
            self.action_btn_1.style = discord.ButtonStyle.success if not premium_open else discord.ButtonStyle.secondary
            self.action_btn_1.label = "Купить пропуск" if not premium_open else "Пропуск куплен"
            self.action_btn_1.emoji = "???"

            self.action_btn_2.disabled = True
            self.action_btn_2.style = discord.ButtonStyle.secondary
            self.action_btn_2.label = "Выбери вкладку"
            self.action_btn_2.emoji = None

            self.action_btn_3.disabled = True
            self.action_btn_3.style = discord.ButtonStyle.secondary
            self.action_btn_3.label = "Выбери вкладку"
            self.action_btn_3.emoji = None
            return

        if self.active_page == "vip":
            visible_levels = self._current_vip_slice()
            current_level = int(self.user_data.get("vip_level", 0) or 0)
            self.prev_btn.disabled = self.page_index == 0
            self.next_btn.disabled = self.page_index >= self._max_vip_page()
            self.prev_btn.label = "Назад"
            self.next_btn.label = "Дальше"

            for index, button in enumerate((self.action_btn_1, self.action_btn_2, self.action_btn_3)):
                if index >= len(visible_levels):
                    continue
                level, data = visible_levels[index]
                button.disabled = current_level >= level
                button.style = discord.ButtonStyle.success if current_level < level else discord.ButtonStyle.secondary
                button.label = f"VIP {level}"
                button.emoji = data.get("emoji")
            return

        if self.active_page == "exchange":
            self.action_btn_1.disabled = False
            self.action_btn_1.style = discord.ButtonStyle.success
            self.action_btn_1.label = "Гемы -> деньги"

            self.action_btn_2.disabled = False
            self.action_btn_2.style = discord.ButtonStyle.success
            self.action_btn_2.label = "Деньги -> гемы"

            self.action_btn_3.disabled = True
            self.action_btn_3.style = discord.ButtonStyle.secondary
            self.action_btn_3.label = "Недоступно"
            return

        if self.active_page == "upgrades":
            auto_state = get_business_autocollect_state(self.user_data)
            autocollect_available = db.user_field_supported("business_autocollect")
            self.action_btn_1.disabled = (not autocollect_available) or auto_state["owned"]
            self.action_btn_1.style = (
                discord.ButtonStyle.success if autocollect_available and not auto_state["owned"] else discord.ButtonStyle.secondary
            )
            self.action_btn_1.label = (
                "Купить автосбор"
                if autocollect_available and not auto_state["owned"]
                else "Недоступно"
                if not autocollect_available
                else "Уже куплено"
            )

            self.action_btn_2.disabled = False
            self.action_btn_2.style = discord.ButtonStyle.primary
            self.action_btn_2.label = "Как работает"

            self.action_btn_3.disabled = False
            self.action_btn_3.style = discord.ButtonStyle.primary
            self.action_btn_3.label = "Открыть бизнесы"
            return

        if self.active_page == "server":
            visible_items = self._current_server_items()
            self.prev_btn.disabled = self.page_index == 0
            self.next_btn.disabled = self.page_index >= self._max_server_page()
            self.prev_btn.label = "Назад"
            self.next_btn.label = "Дальше"

            for index, button in enumerate((self.action_btn_1, self.action_btn_2, self.action_btn_3)):
                if index >= len(visible_items):
                    continue
                item = visible_items[index]
                item_id = int(item.get("id", 0) or 0)
                can_buy = self._is_role_item(item)
                button.label = f"Купить #{item_id}" if can_buy else f"Закрыто #{item_id}"
                button.disabled = not can_buy
                button.style = discord.ButtonStyle.success if can_buy else discord.ButtonStyle.secondary
            return

        if self.active_page == "customize":
            profile = get_profile_state(self.user_data)
            owned_titles = set(profile.get("owned_titles", []))
            visible_items = self._current_title_items()
            self.prev_btn.disabled = self.page_index == 0
            self.next_btn.disabled = self.page_index >= self._max_title_page()
            self.prev_btn.label = "Назад"
            self.next_btn.label = "Дальше"

            for index, button in enumerate((self.action_btn_1, self.action_btn_2, self.action_btn_3)):
                if index >= len(visible_items):
                    continue
                item = visible_items[index]
                already_owned = item["key"] in owned_titles
                button.disabled = already_owned
                button.style = discord.ButtonStyle.success if not already_owned else discord.ButtonStyle.secondary
                button.label = item["name"]
            return

    def build_embed(self) -> discord.Embed:
        builders = {
            "overview": self._build_overview_embed,
            "vip": self._build_vip_embed,
            "exchange": self._build_exchange_embed,
            "upgrades": self._build_upgrades_embed,
            "server": self._build_server_embed,
            "customize": self._build_customize_embed,
        }
        return builders[self.active_page]()

    def _build_overview_embed(self) -> discord.Embed:
        vip_level = int(self.user_data.get("vip_level", 0) or 0)
        auto_state = get_business_autocollect_state(self.user_data)
        embed = discord.Embed(
            title="?? Магазин сервера",
            description="Здесь собраны VIP, обмен валют, улучшения и серверные покупки.",
            color=COLORS["purple"],
        )
        embed.add_field(
            name="Кошелёк",
            value=(
                f"Наличные: **{format_money(self.user_data.get('balance', 0))}**\n"
                f"Гемы: **{int(self.user_data.get('gems', 0) or 0):,}**\n"
                f"VIP: **{format_vip_name(vip_level)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Доступно сейчас",
            value=(
                f"VIP-уровней: **{max(0, len(VIP_LEVELS) - 1)}**\n"
                f"Серверных товаров: **{len(self.custom_items)}**\n"
                f"Автосбор: **{'Куплен' if auto_state['owned'] else 'Не куплен'}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Быстрые разделы",
            value=(
                "• VIP и обмен теперь покупаются кнопками внутри `/shop`\n"
                "• Автосбор настраивается через `/mybusinesses`\n"
                "• Серверные роли покупаются кнопками здесь же"
            ),
            inline=False,
        )
        embed.set_footer(text="Переключай вкладки кнопками ниже.")
        return embed

    def _build_vip_embed(self) -> discord.Embed:
        current_vip = int(self.user_data.get("vip_level", 0) or 0)
        visible_levels = self._current_vip_slice()

        embed = discord.Embed(
            title="?? VIP-магазин",
            description=f"Текущий уровень: **{format_vip_name(current_vip)}**",
            color=COLORS["gold"],
        )

        for level, vip_data in visible_levels:
            embed.add_field(
                name=f"{vip_data['emoji']} {format_vip_name(level)} | {format_price(vip_data['cost'], 'gems')}",
                value=(
                    f"Статус: **{vip_status_label(current_vip, level)}**\n"
                    f"Бонус к daily: **+{int((vip_data['daily_bonus'] - 1) * 100)}%**\n"
                    f"Снижение кулдауна: **-{int(vip_data['cooldown_reduction'] * 100)}%**"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Страница {self.page_index + 1}/{self._max_vip_page() + 1}. Покупка VIP идёт кнопками ниже.")
        return embed

    def _build_exchange_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="?? Обмен валют",
            description="Обменивай деньги и гемы прямо кнопками ниже.",
            color=COLORS["info"],
        )
        embed.add_field(
            name="Гемы -> деньги",
            value="Курс: **1 гем = $900**\nКнопка ниже откроет ввод количества гемов.",
            inline=True,
        )
        embed.add_field(
            name="Деньги -> гемы",
            value="Курс: **$1,000 = 1 гем**\nКнопка ниже откроет ввод количества гемов.",
            inline=True,
        )
        embed.add_field(
            name="Подсказка",
            value="Гемы чаще выгоднее держать под VIP и улучшения, а деньги пускать в бизнесы и игры.",
            inline=False,
        )
        return embed

    def _build_upgrades_embed(self) -> discord.Embed:
        auto_state = get_business_autocollect_state(self.user_data)
        autocollect_available = db.user_field_supported("business_autocollect")
        status = "Куплен" if auto_state["owned"] else "Не куплен"
        mode = "Включён" if auto_state["enabled"] else "Выключен"
        embed = discord.Embed(
            title="?? Постоянные улучшения",
            description="Полезные улучшения для экономики и бизнеса.",
            color=COLORS["purple"],
        )
        embed.add_field(
            name=f"{AUTO_COLLECT_UPGRADE['name']} | {format_price(AUTO_COLLECT_UPGRADE['price'], AUTO_COLLECT_UPGRADE['currency'])}",
            value=(
                f"Статус: **{status}**\n"
                f"Режим: **{mode}**\n"
                f"Интервал: **{auto_state['interval_hours']}ч**\n"
                f"{AUTO_COLLECT_UPGRADE['description']}"
                if autocollect_available
                else "Автосбор временно недоступен. В таблице users нет колонки business_autocollect."
            ),
            inline=False,
        )
        embed.add_field(
            name="Где управлять",
            value="После покупки открой `/mybusinesses` и используй кнопку `Автосбор`.",
            inline=False,
        )
        return embed

    def _build_server_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="?? Серверный магазин",
            description="Серверные товары покупаются прямо кнопками ниже.",
            color=COLORS["success"],
        )
        if not self.custom_items:
            embed.add_field(name="Пока пусто", value="Сейчас нет активных серверных товаров.", inline=False)
            return embed

        for item in self._current_server_items():
            item_id = int(item.get("id", 0) or 0)
            embed.add_field(
                name=f"#{item_id} | {item.get('name', 'Товар')}",
                value=(
                    f"Тип: **{self._server_item_kind(item)}**\n"
                    f"Цена: **{format_price(item.get('price', 0), str(item.get('currency', 'money')))}**\n"
                    f"{clamp_text(item.get('description'))}"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Страница {self.page_index + 1}/{self._max_server_page() + 1}.")
        return embed

    def _build_customize_embed(self) -> discord.Embed:
        profile = get_profile_state(self.user_data)
        owned_titles = set(profile.get("owned_titles", []))
        active_title = str(profile.get("active_title", "rookie"))
        owned_themes = set(profile.get("owned_themes", []))
        active_theme = str(profile.get("active_theme", "classic"))
        visible_items = self._current_title_items()
        embed = discord.Embed(
            title="Кастомизация профиля",
            description="Покупай титулы и фоны для профиля. Включать их можно через `/profile` > `Кастомизация`.",
            color=COLORS["gold"],
        )
        preview_url = ""
        for item in visible_items:
            if str(item.get("kind") or "title") == "theme":
                theme_data = PROFILE_THEMES.get(str(item["key"]), {"name": item["name"]})
                status = "Уже куплен" if item["key"] in owned_themes else "Можно купить"
                if item["key"] == active_theme:
                    status = "Сейчас активен"
                embed.add_field(
                    name=f"{item['name']} | {format_price(item['price'], item['currency'])}",
                    value=(
                        f"{item['description']}\n"
                        f"Тема профиля: **{theme_data['name']}**\n"
                        f"Статус: **{status}**"
                    ),
                    inline=False,
                )
                preview_url = str(item.get("preview_url") or preview_url)
                continue
            title_data = PROFILE_TITLES.get(item["key"], {"display": item["name"]})
            status = "Уже куплен" if item["key"] in owned_titles else "Можно купить"
            if item["key"] == active_title:
                status = "Сейчас активен"
            embed.add_field(
                name=f"{item['name']} | {format_price(item['price'], item['currency'])}",
                value=(
                    f"{item['description']}\n"
                    f"Вид в профиле: `{title_data['display']}`\n"
                    f"Статус: **{status}**"
                ),
                inline=False,
            )
        if not preview_url:
            preview_url = get_profile_theme_image(self.user_data) or ""
        if preview_url:
            embed.set_image(url=preview_url)
        embed.set_footer(text=f"Страница {self.page_index + 1}/{self._max_title_page() + 1}.")
        return embed

    async def _refresh_message(self, interaction: discord.Interaction):
        await self._reload_user()
        self._sync_buttons()
        if not await safe_edit_original_response(interaction, embed=self.build_embed(), view=self):
            return False
        await self._remember_message(interaction)
        return True

    async def _switch_page(self, interaction: discord.Interaction, page: str):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            if self.active_page != page:
                self.page_index = 0
            self.active_page = page
            await self._refresh_message(interaction)

    async def _purchase_vip(self, level: int) -> tuple[bool, discord.Embed | str]:
        vip_data = VIP_LEVELS.get(level)
        if not vip_data or level <= 0:
            return False, "Такого VIP-уровня нет."

        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            current_level = int(user.get("vip_level", 0) or 0)
            if current_level >= level:
                return False, f"У тебя уже есть {format_vip_name(level)} или выше."

            cost = int(vip_data["cost"])
            current_gems = int(user.get("gems", 0) or 0)
            if current_gems < cost:
                return False, f"Не хватает гемов. Нужно: **{cost}**."

            user["gems"] = current_gems - cost
            user["vip_level"] = level
            await db.update_user(self.user_id, self.guild_id, {"gems": user["gems"], "vip_level": level})
            self.user_data = user

        embed = discord.Embed(
            title="VIP активирован",
            description=(
                f"Активирован: **{format_vip_name(level)}**\n"
                f"Потрачено: **{cost} гем.**\n"
                f"Осталось гемов: **{int(self.user_data['gems']):,}**"
            ),
            color=COLORS["gold"],
        )
        embed.add_field(
            name="Бонусы",
            value=(
                f"Daily: **+{int((vip_data['daily_bonus'] - 1) * 100)}%**\n"
                f"Кулдауны: **-{int(vip_data['cooldown_reduction'] * 100)}%**"
            ),
            inline=False,
        )
        return True, embed

    async def _purchase_autocollect_upgrade(self) -> tuple[bool, discord.Embed | str]:
        if not db.user_field_supported("business_autocollect"):
            return False, "Автосбор временно недоступен. Сначала добавь колонку `business_autocollect` в таблицу `users`."

        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            auto_state = get_business_autocollect_state(user)
            if auto_state["owned"]:
                return False, "Автосбор уже куплен."

            price = int(AUTO_COLLECT_UPGRADE["price"])
            current_gems = int(user.get("gems", 0) or 0)
            if current_gems < price:
                return False, f"Нужно **{price} гемов**, а у тебя только **{current_gems}**."

            auto_state.update({"owned": True, "enabled": False, "interval_hours": 6})
            user["gems"] = current_gems - price
            user["business_autocollect"] = auto_state

            await db.update_user(
                self.user_id,
                self.guild_id,
                {"gems": user["gems"], "business_autocollect": auto_state},
            )
            self.user_data = user

        embed = discord.Embed(
            title="Улучшение куплено",
            description=(
                f"Ты купил **{AUTO_COLLECT_UPGRADE['name']}** за **{format_price(price, 'gems')}**.\n"
                "Открой `/mybusinesses`, чтобы включить его и настроить интервал."
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def _purchase_server_item(self, interaction: discord.Interaction, slot_index: int) -> tuple[bool, discord.Embed | str]:
        visible_items = self._current_server_items()
        if slot_index >= len(visible_items):
            return False, "На этой кнопке сейчас нет товара."

        item = visible_items[slot_index]
        price = int(item.get("price", 0) or 0)
        currency = str(item.get("currency", "money")).lower()
        role_id = item.get("role_id")

        if not self._is_role_item(item):
            return False, "У этого серверного товара пока нет логики покупки кнопкой."

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False, "Эта покупка доступна только внутри сервера."

        try:
            role = interaction.guild.get_role(int(role_id)) if role_id is not None else None
        except (TypeError, ValueError):
            role = None

        if role is None:
            return False, "Роль для этого товара не найдена на сервере."
        if role in interaction.user.roles:
            return False, "У тебя уже есть эта роль."

        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            if currency == "gems":
                current_value = int(user.get("gems", 0) or 0)
                if current_value < price:
                    return False, f"Не хватает гемов. Нужно: **{price}**."
                user["gems"] = current_value - price
                update_payload = {"gems": user["gems"]}
            else:
                current_value = int(user.get("balance", 0) or 0)
                if current_value < price:
                    return False, f"Не хватает денег. Нужно: **{format_money(price)}**."
                user["balance"] = current_value - price
                update_payload = {"balance": user["balance"]}

            await db.update_user(self.user_id, self.guild_id, update_payload)
            try:
                await interaction.user.add_roles(role)
            except Exception:
                if currency == "gems":
                    await db.update_user(self.user_id, self.guild_id, {"gems": current_value})
                else:
                    await db.update_user(self.user_id, self.guild_id, {"balance": current_value})
                return False, "Не удалось выдать роль. Проверь права бота и позицию роли."

            self.user_data = user

        embed = discord.Embed(
            title="Покупка завершена",
            description=(
                f"Куплено: **{item.get('name', 'Товар')}**\n"
                f"Цена: **{format_price(price, currency)}**\n"
                f"Получено: {role.mention}"
            ),
            color=COLORS["success"],
        )
        embed.add_field(
            name="После покупки",
            value=(
                f"Наличные: **{format_money(self.user_data.get('balance', 0))}**\n"
                f"Гемы: **{int(self.user_data.get('gems', 0) or 0):,}**"
            ),
            inline=False,
        )
        return True, embed

    async def _purchase_title_item(self, slot_index: int) -> tuple[bool, discord.Embed | str]:
        visible_items = self._current_title_items()
        if slot_index >= len(visible_items):
            return False, "На этой кнопке сейчас нет косметики."

        item = visible_items[slot_index]
        item_kind = str(item.get("kind") or "title")
        item_key = str(item["key"])
        price = int(item["price"])
        currency = str(item["currency"]).lower()

        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            profile = get_profile_state(user)
            if item_kind == "theme":
                if item_key in set(profile.get("owned_themes", [])):
                    return False, "Этот фон у тебя уже есть."
            else:
                if item_key in set(profile.get("owned_titles", [])):
                    return False, "Этот титул у тебя уже есть."

            if currency == "gems":
                current_value = int(user.get("gems", 0) or 0)
                if current_value < price:
                    return False, f"Не хватает гемов. Нужно: **{price}**."
                user["gems"] = current_value - price
                update_payload = {"gems": user["gems"]}
            else:
                current_value = int(user.get("balance", 0) or 0)
                if current_value < price:
                    return False, f"Не хватает денег. Нужно: **{format_money(price)}**."
                user["balance"] = current_value - price
                update_payload = {"balance": user["balance"]}

            if item_kind == "theme":
                unlock_theme(user, item_key)
            else:
                unlock_title(user, item_key)
            update_payload["game_stats"] = user.get("game_stats", {})
            await db.update_user(self.user_id, self.guild_id, update_payload)
            self.user_data = user

        if item_kind == "theme":
            theme_data = PROFILE_THEMES.get(item_key, {"name": item["name"]})
            embed = discord.Embed(
                title="Фон куплен",
                description=(
                    f"Куплен фон: **{theme_data['name']}**\n"
                    f"Цена: **{format_price(price, currency)}**\n"
                    f"Новый фон можно включить через `/profile` -> `Кастомизация`."
                ),
                color=COLORS["success"],
            )
            preview_url = str(item.get("preview_url") or "")
            if preview_url:
                embed.set_image(url=preview_url)
            return True, embed

        title_data = PROFILE_TITLES.get(item_key, {"name": item["name"], "display": item["name"]})
        embed = discord.Embed(
            title="Титул куплен",
            description=(
                f"Куплен титул: **{title_data['name']}**\n"
                f"Цена: **{format_price(price, currency)}**\n"
                f"Новый титул можно включить через `/profile` -> `Кастомизация`."
            ),
            color=COLORS["success"],
        )
        embed.add_field(name="Вид в профиле", value=f"`{title_data['display']}`", inline=False)
        return True, embed

    async def _handle_action(self, interaction: discord.Interaction, slot_index: int | None = None):
        async with self._view_lock:
            if self.active_page == "exchange" and slot_index == 0:
                await interaction.response.send_modal(ExchangeModal(self, "to_money"))
                return
            if self.active_page == "exchange" and slot_index == 1:
                await interaction.response.send_modal(ExchangeModal(self, "to_gems"))
                return

            await interaction.response.defer()

            if self.active_page == "vip":
                visible_levels = self._current_vip_slice()
                if slot_index is None or slot_index >= len(visible_levels):
                    return
                payload = await self._purchase_vip(visible_levels[slot_index][0])
            elif self.active_page == "server":
                payload = await self._purchase_server_item(interaction, slot_index or 0)
            elif self.active_page == "exchange" and slot_index == 2:
                payload = (
                    False,
                    discord.Embed(
                        title="Курс обмена",
                        description="1 гем = $1,000 при покупке\n1 гем = $900 при продаже",
                        color=COLORS["info"],
                    ),
                )
            elif self.active_page == "upgrades" and slot_index == 0:
                payload = await self._purchase_autocollect_upgrade()
            elif self.active_page == "upgrades" and slot_index == 1:
                payload = (
                    False,
                    discord.Embed(
                        title="Как работает автосбор",
                        description=(
                            "После покупки бот сам проверяет твои бизнесы по выбранному интервалу "
                            "и переводит готовую прибыль на баланс."
                        ),
                        color=COLORS["info"],
                    ),
                )
            elif self.active_page == "upgrades" and slot_index == 2:
                payload = (False, "Открой `/mybusinesses` и используй кнопку `Автосбор`.")
            else:
                return

            _, result = payload
            await self._refresh_message(interaction)
            if isinstance(result, discord.Embed):
                await interaction.followup.send(embed=result, ephemeral=True)
            else:
                await interaction.followup.send(str(result), ephemeral=True)

    @discord.ui.button(label="Обзор", style=discord.ButtonStyle.primary, row=0)
    async def overview_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_page(interaction, "overview")

    @discord.ui.button(label="VIP", style=discord.ButtonStyle.secondary, row=0)
    async def vip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_page(interaction, "vip")

    @discord.ui.button(label="Обмен", style=discord.ButtonStyle.secondary, row=0)
    async def exchange_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_page(interaction, "exchange")

    @discord.ui.button(label="Улучшения", style=discord.ButtonStyle.secondary, row=0)
    async def upgrades_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_page(interaction, "upgrades")

    @discord.ui.button(label="Сервер", style=discord.ButtonStyle.secondary, row=0)
    async def server_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_page(interaction, "server")

    @discord.ui.button(label="Кастомизация", style=discord.ButtonStyle.secondary, row=2)
    async def customize_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_page(interaction, "customize")

    @discord.ui.button(label="-", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await interaction.response.defer()
            if self.active_page == "vip":
                self.page_index = max(0, self.page_index - 1)
            elif self.active_page == "server":
                self.page_index = max(0, self.page_index - 1)
            elif self.active_page == "customize":
                self.page_index = max(0, self.page_index - 1)
            await self._refresh_message(interaction)

    @discord.ui.button(label="Недоступно", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def action_btn_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, 0)

    @discord.ui.button(label="Недоступно", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def action_btn_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, 1)

    @discord.ui.button(label="Недоступно", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def action_btn_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_action(interaction, 2)

    @discord.ui.button(label="-", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await interaction.response.defer()
            if self.active_page == "vip":
                self.page_index = min(self._max_vip_page(), self.page_index + 1)
            elif self.active_page == "server":
                self.page_index = min(self._max_server_page(), self.page_index + 1)
            elif self.active_page == "customize":
                self.page_index = min(self._max_title_page(), self.page_index + 1)
            await self._refresh_message(interaction)

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

class BattlePassView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню боевого пропуска открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        self.message = await _remember_interaction_message(interaction, self.message)

    async def _get_user(self) -> dict[str, Any]:
        return await db.get_user(self.user_id, self.guild_id) or {}

    @staticmethod
    def _next_claimable_tier(user: dict[str, Any], *, premium: bool = False) -> int | None:
        state = ensure_battle_pass_state(user)
        unlocked = battle_pass_tier(user)
        claimed_key = "claimed_premium" if premium else "claimed_free"
        claimed = {int(value) for value in state.get(claimed_key, []) if str(value).isdigit()}
        for tier in range(1, unlocked + 1):
            if tier not in claimed:
                return tier
        return None

    def _sync_buttons(self, user: dict[str, Any]):
        state = ensure_battle_pass_state(user)
        premium_open = bool(state.get("premium_unlocked"))
        next_free = self._next_claimable_tier(user, premium=False)
        next_premium = self._next_claimable_tier(user, premium=True)

        self.buy_premium_btn.label = "Покупка в /shop" if not premium_open else "Премиум открыт"
        self.buy_premium_btn.style = discord.ButtonStyle.success if not premium_open else discord.ButtonStyle.secondary
        self.buy_premium_btn.disabled = premium_open

        self.claim_free_btn.disabled = next_free is None
        self.claim_premium_btn.disabled = (not premium_open) or next_premium is None
        self.claim_premium_btn.style = discord.ButtonStyle.primary if premium_open and next_premium is not None else discord.ButtonStyle.secondary

    async def build_embed(self) -> discord.Embed:
        user = await self._get_user()
        if not user:
            return discord.Embed(title="Боевой пропуск", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        self._sync_buttons(user)
        state = ensure_battle_pass_state(user)
        unlocked = battle_pass_tier(user)
        tier_progress, tier_total = battle_pass_progress_to_next(user)
        premium_open = bool(state.get("premium_unlocked"))
        next_free = self._next_claimable_tier(user, premium=False)
        next_premium = self._next_claimable_tier(user, premium=True)
        total_xp = int(state.get("xp", 0) or 0)
        max_xp = SEASON_MAX_TIERS * 100
        pass_status = "ПРЕМИУМ" if premium_open else "БЕСПЛАТНО"

        embed = discord.Embed(
            title=f"{SEASON_NAME} • {pass_status}",
            description=(
                "Сезонный пропуск с ежедневными заданиями, бесплатной и платной веткой наград.\n"
                f"`{build_progress_bar(total_xp, max_xp, length=12)}` **{total_xp}/{max_xp} XP**"
            ),
            color=COLORS["gold"],
        )
        embed.add_field(
            name="Прогресс",
            value=(
                f"Уровень: **{unlocked}/{SEASON_MAX_TIERS}**\n"
                f"До следующего: `{build_progress_bar(tier_progress, tier_total)}` **{tier_progress}/{tier_total}**\n"
                f"Статус пропуска: **{pass_status}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Следующие награды",
            value=(
                f"БЕСПЛАТНО: **{reward_text(SEASON_FREE_REWARDS[min(max(unlocked, 0), SEASON_MAX_TIERS - 1)])}**\n"
                f"ПРЕМИУМ: **{reward_text(SEASON_PREMIUM_REWARDS[min(max(unlocked, 0), SEASON_MAX_TIERS - 1)])}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Платная ветка",
            value=(
                f"Цена открытия: **{format_money(SEASON_PREMIUM_COST)}**\n"
                "Покупка доступна только через `/shop`."
            ),
            inline=False,
        )

        mission_lines: list[str] = []
        for mission in state.get("daily_missions", []):
            marker = "Готово" if mission.get("completed") else "В процессе"
            mission_lines.append(
                f"{marker} • {mission.get('description', 'Задание')} "
                f"({int(mission.get('progress', 0) or 0)}/{int(mission.get('target', 0) or 0)}) "
                f"+{int(mission.get('xp_reward', 0) or 0)} XP"
            )
        embed.add_field(name="Ежедневные задания", value="\n".join(mission_lines) or "Сегодня заданий нет.", inline=False)

        preview_lines: list[str] = []
        start_tier = min(SEASON_MAX_TIERS, max(1, unlocked + 1 if next_free is None else next_free))
        for tier in range(start_tier, min(SEASON_MAX_TIERS, start_tier + 4) + 1):
            free_reward = reward_text(SEASON_FREE_REWARDS[tier - 1])
            premium_reward = reward_text(SEASON_PREMIUM_REWARDS[tier - 1])
            preview_lines.append(f"Уровень {tier}: FREE {free_reward} | PREMIUM {premium_reward}")
        embed.add_field(name="Ближайшие уровни", value="\n".join(preview_lines), inline=False)
        embed.set_footer(
            text=(
                f"Следующая бесплатная награда: {'уровень ' + str(next_free) if next_free else 'всё получено'} | "
                f"следующая премиум-награда: {'уровень ' + str(next_premium) if next_premium else 'нет доступных'}"
            )
        )
        return embed

        user = await self._get_user()
        if not user:
            return discord.Embed(title="Боевой пропуск", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        self._sync_buttons(user)
        state = ensure_battle_pass_state(user)
        unlocked = battle_pass_tier(user)
        tier_progress, tier_total = battle_pass_progress_to_next(user)
        premium_open = bool(state.get("premium_unlocked"))
        next_free = self._next_claimable_tier(user, premium=False)
        next_premium = self._next_claimable_tier(user, premium=True)
        total_xp = int(state.get("xp", 0) or 0)
        max_xp = SEASON_MAX_TIERS * 100

        embed = discord.Embed(
            title=f"{SEASON_NAME} - боевой пропуск",
            description=(
                "Бесплатная и платная ветка с ежедневными заданиями, бустами, косметикой и гемами.\n"
                f"`{build_progress_bar(total_xp, max_xp, length=12)}` **{total_xp}/{max_xp} XP**"
            ),
            color=COLORS["gold"],
        )
        embed.add_field(
            name="Прогресс",
            value=(
                f"Уровень: **{unlocked}/{SEASON_MAX_TIERS}**\n"
                f"До следующего: `{build_progress_bar(tier_progress, tier_total)}` **{tier_progress}/{tier_total}**\n"
                f"Платная ветка: **{'Открыта' if premium_open else 'Закрыта'}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Следующие награды",
            value=(
                f"Бесплатно: **{reward_text(SEASON_FREE_REWARDS[min(max(unlocked, 0), SEASON_MAX_TIERS - 1)])}**\n"
                f"Платно: **{reward_text(SEASON_PREMIUM_REWARDS[min(max(unlocked, 0), SEASON_MAX_TIERS - 1)])}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Платная ветка",
            value=(
                f"Цена открытия: **{format_money(SEASON_PREMIUM_COST)}**\n"
                "Покупка доступна только через `/shop`."
            ),
            inline=False,
        )

        mission_lines: list[str] = []
        for mission in state.get("daily_missions", []):
            marker = "Выполнено" if mission.get("completed") else "В процессе"
            mission_lines.append(
                f"{marker} {mission.get('description', 'Задание')} "
                f"({int(mission.get('progress', 0) or 0)}/{int(mission.get('target', 0) or 0)}) "
                f"+{int(mission.get('xp_reward', 0) or 0)} XP"
            )
        embed.add_field(name="Ежедневные задания", value="\n".join(mission_lines) or "Сегодня заданий нет.", inline=False)

        preview_lines: list[str] = []
        start_tier = min(SEASON_MAX_TIERS, max(1, unlocked + 1 if next_free is None else next_free))
        for tier in range(start_tier, min(SEASON_MAX_TIERS, start_tier + 4) + 1):
            free_reward = reward_text(SEASON_FREE_REWARDS[tier - 1])
            premium_reward = reward_text(SEASON_PREMIUM_REWARDS[tier - 1])
            preview_lines.append(f"Уровень {tier}: бесплатно {free_reward} | платно {premium_reward}")
        embed.add_field(name="Ближайшие уровни", value="\n".join(preview_lines), inline=False)
        embed.set_footer(
            text=(
                f"Следующая бесплатная награда: {'уровень ' + str(next_free) if next_free else 'всё получено'} | "
                f"следующая платная: {'уровень ' + str(next_premium) if next_premium else 'нет доступных'}"
            )
        )
        return embed

    async def _refresh_message(self, interaction: discord.Interaction):
        embed = await self.build_embed()
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return False
        await self._remember_message(interaction)
        return True

    @discord.ui.button(label="Открыть премиум", style=discord.ButtonStyle.success, row=0)
    async def buy_premium_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            user = await db.get_user(self.user_id, self.guild_id)
            custom_items = await db.get_shop_items(self.guild_id)
            view = ShopView(self.user_id, self.guild_id, user or {}, custom_items)
            if not await safe_edit_original_response(interaction, embed=view.build_embed(), view=view):
                return
            await view._remember_message(interaction)

    @discord.ui.button(label="Забрать бесплатную", style=discord.ButtonStyle.primary, row=0)
    async def claim_free_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            async with get_user_lock(self.user_id):
                user = await db.get_user(self.user_id, self.guild_id)
                if not user:
                    await interaction.followup.send("Не удалось загрузить профиль.", ephemeral=True)
                    return
                tier = self._next_claimable_tier(user, premium=False)
                if tier is None:
                    await interaction.followup.send("Сейчас нет бесплатных наград для получения.", ephemeral=True)
                    return
                success, payload = claim_battle_pass_reward(user, tier, premium=False)
                if not success:
                    await interaction.followup.send(str(payload), ephemeral=True)
                    return
                await db.update_user(
                    self.user_id,
                    self.guild_id,
                    {
                        "balance": user.get("balance", 0),
                        "gems": user.get("gems", 0),
                        "buff_xp_until": user.get("buff_xp_until"),
                        "buff_money_until": user.get("buff_money_until"),
                        "game_stats": user.get("game_stats", {}),
                    },
                )
            await self._refresh_message(interaction)
            await interaction.followup.send(f"Получена бесплатная награда уровня {tier}: {reward_text(payload)}", ephemeral=True)

    @discord.ui.button(label="Забрать премиум", style=discord.ButtonStyle.primary, row=1)
    async def claim_premium_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            async with get_user_lock(self.user_id):
                user = await db.get_user(self.user_id, self.guild_id)
                if not user:
                    await interaction.followup.send("Не удалось загрузить профиль.", ephemeral=True)
                    return
                tier = self._next_claimable_tier(user, premium=True)
                if tier is None:
                    await interaction.followup.send("Сейчас нет платных наград для получения.", ephemeral=True)
                    return
                success, payload = claim_battle_pass_reward(user, tier, premium=True)
                if not success:
                    await interaction.followup.send(str(payload), ephemeral=True)
                    return
                await db.update_user(
                    self.user_id,
                    self.guild_id,
                    {
                        "balance": user.get("balance", 0),
                        "gems": user.get("gems", 0),
                        "buff_xp_until": user.get("buff_xp_until"),
                        "buff_money_until": user.get("buff_money_until"),
                        "game_stats": user.get("game_stats", {}),
                    },
                )
            await self._refresh_message(interaction)
            await interaction.followup.send(f"Получена платная награда уровня {tier}: {reward_text(payload)}", ephemeral=True)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_message(interaction)

    @discord.ui.button(label="Назад в магазин", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            user = await db.get_user(self.user_id, self.guild_id)
            custom_items = await db.get_shop_items(self.guild_id)
            view = ShopView(self.user_id, self.guild_id, user or {}, custom_items)
            if not await safe_edit_original_response(interaction, embed=view.build_embed(), view=view):
                return
            await view._remember_message(interaction)

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


# Legacy CleanBattlePassView removed; the active BattlePassView above stays canonical.
class ShopView(_BaseShopView):
    def _build_overview_embed(self) -> discord.Embed:
        vip_level = int(self.user_data.get("vip_level", 0) or 0)
        auto_state = get_business_autocollect_state(self.user_data)
        pass_state = ensure_battle_pass_state(self.user_data)
        tier = battle_pass_tier(self.user_data)
        tier_progress, tier_total = battle_pass_progress_to_next(self.user_data)
        embed = discord.Embed(
            title="Магазин сервера",
            description="Главный раздел покупок для VIP, обмена, кастомизации и постоянных улучшений.",
            color=COLORS["purple"],
        )
        embed.add_field(
            name="Кошелёк",
            value=(
                f"Наличные: **{format_money(self.user_data.get('balance', 0))}**\n"
                f"Гемы: **{int(self.user_data.get('gems', 0) or 0):,}**\n"
                f"VIP: **{format_vip_name(vip_level)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Сезон",
            value=(
                f"{SEASON_NAME}\n"
                f"Уровень: **{tier}/{SEASON_MAX_TIERS}**\n"
                f"Прогресс: `{build_progress_bar(tier_progress, tier_total)}` **{tier_progress}/{tier_total} XP**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Быстрый обзор",
            value=(
                f"Платная ветка пропуска: **{'Открыта' if pass_state.get('premium_unlocked') else 'Закрыта'}**\n"
                f"Автосбор: **{'Куплен' if auto_state['owned'] else 'Не куплен'}**\n"
                f"Серверные товары: **{len(self.custom_items)}**\n"
                f"Косметика: **{len(THEME_SHOP_ITEMS) + len(TITLE_SHOP_ITEMS)}**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Что доступно ниже",
            value=(
                "Боевой пропуск: купить платную ветку, а задания и награды смотреть через `/bp`\n"
                "VIP: удобство, бонусы, дополнительные слоты контрактов и обновления\n"
                "Обмен: покупка и продажа гемов в одном месте\n"
                "Кастомизация: покупка титулов и фоновых тем для профиля"
            ),
            inline=False,
        )
        embed.set_footer(text="Выбирай раздел магазина в селекте сверху, а действия выполняй кнопками ниже.")
        return embed

    def _build_vip_embed(self) -> discord.Embed:
        current_vip = int(self.user_data.get("vip_level", 0) or 0)
        visible_levels = self._current_vip_slice()
        embed = discord.Embed(
            title="VIP-магазин",
            description=f"Текущий уровень: **{format_vip_name(current_vip)}**",
            color=COLORS["gold"],
        )

        for level, vip_data in visible_levels:
            embed.add_field(
                name=f"{vip_data['emoji']} {format_vip_name(level)} | {format_price(vip_data['cost'], 'gems')}",
                value=(
                    f"Статус: **{vip_status_label(current_vip, level)}**\n"
                    f"Бонус к ежедневной награде: **+{int((vip_data['daily_bonus'] - 1) * 100)}%**\n"
                    f"Снижение кулдаунов: **-{int(vip_data['cooldown_reduction'] * 100)}%**\n"
                    f"Контракты: **{contract_slots_for_vip(level)} слотов**, **{contract_rerolls_for_vip(level)} обновлений в день**\n"
                    "Профиль: более аккуратный вид и дополнительные удобства"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Страница {self.page_index + 1}/{self._max_vip_page() + 1}. Покупка VIP доступна кнопками ниже.")
        return embed

    async def _handle_action(self, interaction: discord.Interaction, slot_index: int | None = None):
        async with self._view_lock:
            if self.active_page == "overview" and slot_index == 0:
                if not await safe_defer(interaction):
                    return
                async with get_user_lock(self.user_id):
                    user = await db.get_user(self.user_id, self.guild_id)
                    if not user:
                        await interaction.followup.send("Не удалось загрузить профиль.", ephemeral=True)
                        return
                    if ensure_battle_pass_state(user).get("premium_unlocked"):
                        self.user_data = user
                        await self._refresh_message(interaction)
                        await interaction.followup.send("Платная ветка уже куплена. Для заданий и наград используй `/bp`.", ephemeral=True)
                        return
                    success, message = buy_premium_pass(user)
                    if not success:
                        await interaction.followup.send(message, ephemeral=True)
                        return
                    await db.update_user(
                        self.user_id,
                        self.guild_id,
                        {
                            "balance": user.get("balance", 0),
                            "game_stats": user.get("game_stats", {}),
                        },
                    )
                    self.user_data = user
                await self._refresh_message(interaction)
                await interaction.followup.send("Боевой пропуск куплен. Всё остальное по нему открывается через `/bp`.", ephemeral=True)
                return
            if self.active_page == "overview" and slot_index == 1:
                await interaction.response.send_message("Переключайся на вкладку `VIP` верхней кнопкой.", ephemeral=True)
                return
            if self.active_page == "overview" and slot_index == 2:
                await interaction.response.send_message("Переключайся на вкладку `Обмен` верхней кнопкой.", ephemeral=True)
                return

            if self.active_page == "exchange" and slot_index == 0:
                await interaction.response.send_modal(ExchangeModal(self, "to_money"))
                return
            if self.active_page == "exchange" and slot_index == 1:
                await interaction.response.send_modal(ExchangeModal(self, "to_gems"))
                return

            if not await safe_defer(interaction):
                return

            if self.active_page == "vip":
                visible_levels = self._current_vip_slice()
                if slot_index is None or slot_index >= len(visible_levels):
                    return
                payload = await self._purchase_vip(visible_levels[slot_index][0])
            elif self.active_page == "server":
                payload = await self._purchase_server_item(interaction, slot_index or 0)
            elif self.active_page == "customize":
                if slot_index is None:
                    return
                payload = await self._purchase_title_item(slot_index)
            elif self.active_page == "exchange" and slot_index == 2:
                return
            elif self.active_page == "upgrades" and slot_index == 0:
                payload = await self._purchase_autocollect_upgrade()
            elif self.active_page == "upgrades" and slot_index == 1:
                payload = (
                    False,
                    discord.Embed(
                        title="Как работает автосбор",
                        description=(
                            "После покупки бот проверяет твои бизнесы через выбранный интервал "
                            "и автоматически переводит готовую прибыль на баланс."
                        ),
                        color=COLORS["info"],
                    ),
                )
            elif self.active_page == "upgrades" and slot_index == 2:
                payload = (False, "Открой `/mybusinesses` и используй там кнопку `Автосбор`.")
            else:
                return

            _, result = payload
            await self._refresh_message(interaction)
            if isinstance(result, discord.Embed):
                await interaction.followup.send(embed=result, ephemeral=True)
            else:
                await interaction.followup.send(str(result), ephemeral=True)


class SettingsView(discord.ui.View):
    def __init__(
        self,
        cog: "UserCog",
        user_id: int,
        guild_id: int,
        *,
        profile_cog: Any | None = None,
        profile_target_id: int | None = None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.profile_cog = profile_cog
        self.profile_target_id = profile_target_id or user_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        if self.profile_cog is not None:
            back_button = discord.ui.Button(label="Назад к профилю", style=discord.ButtonStyle.secondary, row=3)
            back_button.callback = self._go_back_to_profile
            self.add_item(back_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню настроек открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        self.message = await _remember_interaction_message(interaction, self.message)

    async def _refresh_view(self, interaction: discord.Interaction):
        embed = await self.cog.build_settings_embed(interaction.user, self.guild_id)
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)

    async def _go_back_to_profile(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.profile_cog is None:
                await interaction.response.send_message("Профиль сейчас недоступен.", ephemeral=True)
                return
            member = interaction.guild.get_member(self.profile_target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            from cogs.economy import ProfileView

            view = ProfileView(self.profile_cog, self.user_id, self.guild_id, self.profile_target_id)
            embed = await self.profile_cog.build_profile_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=view)
            await view._remember_message(interaction)

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

    @discord.ui.button(label="Уведомления", style=discord.ButtonStyle.primary, row=0)
    async def toggle_notifications(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            enabled = await self.cog.toggle_smart_notifications(self.user_id, self.guild_id)
            await self._refresh_view(interaction)
            await interaction.followup.send(
                "Умные уведомления включены." if enabled else "Умные уведомления отключены.",
                ephemeral=True,
            )

    @discord.ui.button(label="Роль активности", style=discord.ButtonStyle.secondary, row=0)
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            enabled, role_changed = await self.cog.toggle_auto_casino_role(interaction.user, self.guild_id)
            await self._refresh_view(interaction)
            guild = interaction.guild
            role_id = await resolve_activity_role_id(guild, self.guild_id)
            if enabled:
                message = "Автовыдача роли активности снова включена."
                if role_changed:
                    message += " Роль выдана."
                elif role_id is None:
                    message += " Админ пока не настроил роль на сервере."
            else:
                message = "Автовыдача роли активности отключена."
                if role_changed:
                    message += " Роль снята и больше не будет выдаваться автоматически."
            await interaction.followup.send(message, ephemeral=True)

    @discord.ui.select(
        placeholder="Переключить конкретное уведомление",
        min_values=1,
        max_values=1,
        row=1,
        options=[
            discord.SelectOption(label="Депозит", value="notify_deposit", emoji="??"),
            discord.SelectOption(label="Аренда", value="notify_rent", emoji="??"),
            discord.SelectOption(label="Бизнес", value="notify_business", emoji="??"),
            discord.SelectOption(label="Урожай", value="notify_harvest", emoji="??"),
            discord.SelectOption(label="Daily streak", value="notify_daily_streak", emoji="?"),
        ],
    )
    async def notification_type_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            preference_key = select.values[0]
            enabled = await self.cog.toggle_notification_type(self.user_id, self.guild_id, preference_key)
            await self._refresh_view(interaction)
            label = SMART_NOTIFICATION_SETTINGS.get(preference_key, {}).get("label", "Уведомление")
            await interaction.followup.send(
                f"Уведомление «{label}» {'включено' if enabled else 'выключено'}.",
                ephemeral=True,
            )

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_view(interaction)


class ChannelIdModal(discord.ui.Modal, title="Игровой канал"):
    channel_id = discord.ui.TextInput(
        label="ID текстового канала",
        placeholder="Например: 123456789012345678",
        required=True,
        max_length=25,
    )

    def __init__(self, parent_view: "ServerSettingsView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.channel_id.value or "").strip()
        if not raw_value.isdigit():
            await interaction.response.send_message("Нужен числовой ID текстового канала.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Эта настройка доступна только на сервере.", ephemeral=True)
            return

        channel = guild.get_channel(int(raw_value))
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Канал не найден или это не текстовый канал.", ephemeral=True)
            return

        await self.parent_view.cog.update_server_settings(guild.id, {"allowed_channel_id": channel.id})
        embed = await self.parent_view.cog.build_server_settings_embed(guild)
        if self.parent_view.message is not None:
            try:
                await self.parent_view.message.edit(embed=embed, view=self.parent_view)
            except Exception:
                pass
        await interaction.response.send_message(f"Игровой канал установлен: {channel.mention}", ephemeral=True)


class ActivityRoleModal(discord.ui.Modal, title="Роль активности"):
    role_id = discord.ui.TextInput(
        label="ID роли",
        placeholder="Например: 123456789012345678",
        required=True,
        max_length=25,
    )

    def __init__(self, parent_view: "ServerSettingsView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.role_id.value or "").strip()
        if not raw_value.isdigit():
            await interaction.response.send_message("Нужен числовой ID роли.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Эта настройка доступна только на сервере.", ephemeral=True)
            return

        role = guild.get_role(int(raw_value))
        if role is None:
            await interaction.response.send_message("Роль с таким ID не найдена на этом сервере.", ephemeral=True)
            return

        await self.parent_view.cog.update_server_settings(guild.id, {"activity_role_id": role.id})
        embed = await self.parent_view.cog.build_server_settings_embed(guild)
        if self.parent_view.message is not None:
            try:
                await self.parent_view.message.edit(embed=embed, view=self.parent_view)
            except Exception:
                pass
        await interaction.response.send_message(f"Роль активности установлена: {role.mention}", ephemeral=True)


class ServerSettingsView(discord.ui.View):
    def __init__(self, cog: "UserCog", user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню настроек сервера открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        self.message = await _remember_interaction_message(interaction, self.message)

    async def _refresh_view(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return
        embed = await self.cog.build_server_settings_embed(guild)
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)

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

    @discord.ui.button(label="Задать канал", style=discord.ButtonStyle.primary, row=0)
    async def set_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChannelIdModal(self))

    @discord.ui.button(label="Сбросить канал", style=discord.ButtonStyle.secondary, row=0)
    async def clear_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self.cog.update_server_settings(self.guild_id, {"allowed_channel_id": None})
            await self._refresh_view(interaction)
            await interaction.followup.send("Ограничение по игровому каналу снято.", ephemeral=True)

    @discord.ui.button(label="Задать роль", style=discord.ButtonStyle.primary, row=1)
    async def set_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActivityRoleModal(self))

    @discord.ui.button(label="Сбросить роль", style=discord.ButtonStyle.secondary, row=1)
    async def clear_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self.cog.update_server_settings(self.guild_id, {"activity_role_id": None})
            await self._refresh_view(interaction)
            await interaction.followup.send("Роль активности отключена для сервера.", ephemeral=True)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh_view(interaction)


class UserCog(commands.Cog, name="User"):
    def __init__(self, bot):
        self.bot = bot
        if not self.smart_notifications_loop.is_running():
            self.smart_notifications_loop.start()

    def cog_unload(self):
        self.smart_notifications_loop.cancel()

    def make_settings_view(
        self,
        *,
        user_id: int,
        guild_id: int,
        profile_cog: Any | None = None,
        profile_target_id: int | None = None,
    ) -> SettingsView:
        return SettingsView(
            self,
            user_id,
            guild_id,
            profile_cog=profile_cog,
            profile_target_id=profile_target_id,
        )

    async def update_server_settings(self, guild_id: int, payload: dict[str, Any]) -> bool:
        return await db.upsert_guild_settings(guild_id, payload)

    async def build_server_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        settings = await get_guild_runtime_settings(guild.id)
        settings_present = bool(settings.get("settings_present"))
        configured_channel_id = settings.get("allowed_channel_id")
        configured_role_id = settings.get("activity_role_id")
        active_channel_id = await resolve_allowed_channel_id(guild, guild.id)
        active_role_id = await resolve_activity_role_id(guild, guild.id)

        channel_text = "Не задан. Команды можно использовать в любом текстовом канале."
        if active_channel_id is not None:
            channel_text = f"<#{active_channel_id}>"
            if not settings_present and configured_channel_id is None:
                channel_text += "\nСейчас используется старый базовый канал по умолчанию."
        elif configured_channel_id is not None:
            channel_text = (
                f"`{configured_channel_id}` не найден.\n"
                "Задай новый текстовый канал или сними ограничение."
            )

        role_text = "Не задана. Бот не будет автоматически выдавать роль за активность."
        if active_role_id is not None:
            role = guild.get_role(active_role_id)
            role_text = role.mention if role is not None else f"`{active_role_id}`"
            if not settings_present and configured_role_id is None:
                role_text += "\nСейчас используется старая базовая роль по умолчанию."
        elif configured_role_id is not None:
            role_text = (
                f"`{configured_role_id}` не найдена.\n"
                "Задай новую роль или отключи автовыдачу роли на сервере."
            )

        embed = discord.Embed(
            title="?? Настройки сервера",
            description="Здесь админ задаёт игровой канал и роль активности для текущего сервера.",
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        if guild.icon:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
        else:
            embed.set_author(name=guild.name)
        embed.add_field(
            name="Игровой канал",
            value=(
                f"{channel_text}\n"
                "Если канал указан, все игровые команды работают только там."
            ),
            inline=False,
        )
        embed.add_field(
            name="Роль активности",
            value=(
                f"{role_text}\n"
                "Выдаётся при активности с ботом, если игрок не отключил это у себя в `/profile`."
            ),
            inline=False,
        )
        embed.add_field(
            name="Как это работает",
            value=(
                "• `/setting` — серверные настройки админа\n"
                "• `/profile` > `Настройки` — личные уведомления и авто-роль\n"
                "• без настроенного канала бот доступен в любом текстовом канале"
            ),
            inline=False,
        )
        embed.set_footer(text="Вводи ID текстового канала и ID роли кнопками ниже.")
        return embed

    @staticmethod
    def _notification_state(user: dict[str, Any]) -> dict[str, Any]:
        game_stats = user.get("game_stats")
        if not isinstance(game_stats, dict):
            game_stats = {}
            user["game_stats"] = game_stats

        systems = game_stats.get("_systems")
        if not isinstance(systems, dict):
            systems = {}
            game_stats["_systems"] = systems

        state = systems.get("smart_notification_state")
        if not isinstance(state, dict):
            state = {}
            systems["smart_notification_state"] = state

        markers = state.get("markers")
        if not isinstance(markers, dict):
            markers = {}
            state["markers"] = markers
        return state

    @classmethod
    def _get_notification_markers(cls, user: dict[str, Any]) -> dict[str, str]:
        state = cls._notification_state(user)
        raw_markers = state.get("markers")
        if not isinstance(raw_markers, dict):
            raw_markers = {}
            state["markers"] = raw_markers
        return {str(key): str(value) for key, value in raw_markers.items() if value}

    @classmethod
    def _set_notification_markers(cls, user: dict[str, Any], markers: dict[str, str]) -> None:
        state = cls._notification_state(user)
        state["markers"] = {str(key): str(value) for key, value in markers.items() if value}

    @staticmethod
    def _update_notification_marker(markers: dict[str, str], key: str, marker: str | None) -> bool:
        previous = markers.get(key)
        if not marker:
            if key in markers:
                markers.pop(key, None)
                return True
            return False

        markers[key] = marker
        return previous != marker

    def _clear_notification_markers_for_user(self, user: dict[str, Any]) -> bool:
        markers = self._get_notification_markers(user)
        if not markers:
            return False
        self._set_notification_markers(user, {})
        return True

    def _clear_notification_marker(self, user: dict[str, Any], key: str) -> bool:
        markers = self._get_notification_markers(user)
        if key not in markers:
            return False
        markers.pop(key, None)
        self._set_notification_markers(user, markers)
        return True

    async def build_settings_embed(self, member: discord.Member | discord.User, guild_id: int) -> discord.Embed:
        user = await db.get_user(member.id, guild_id)
        preferences = get_user_preferences(user or {})
        auto_role = bool(preferences.get("auto_casino_role", True))
        notifications = bool(preferences.get("smart_notifications", True))
        notification_lines = [
            f"• {config['label']}: **{'Вкл' if bool(preferences.get(key, True)) else 'Выкл'}**"
            for key, config in SMART_NOTIFICATION_SETTINGS.items()
        ]

        channel_id = await resolve_allowed_channel_id(member.guild if isinstance(member, discord.Member) else None, guild_id)
        channel_text = f"<#{channel_id}>" if channel_id is not None else "Любой текстовый канал сервера"

        role_text = "Админ ещё не настроил роль активности."
        if isinstance(member, discord.Member):
            role_id = await resolve_activity_role_id(member.guild, guild_id)
            role = member.guild.get_role(role_id) if role_id is not None else None
            if role is not None:
                has_role = role in member.roles
                status = "есть" if has_role else "нет"
                role_text = f"{role.mention} • сейчас: **{status}**"

        embed = discord.Embed(
            title="?? Личные настройки",
            description="Здесь ты управляешь уведомлениями и своей ролью активности.",
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.add_field(
            name="Умные уведомления",
            value=(
                f"Статус: **{'Включены' if notifications else 'Выключены'}**\n"
                f"Канал: {channel_text}\n"
                "Следят за депозитом, арендой, бизнесами, урожаем и почти сгорающим daily streak.\n\n"
                "**Отдельные типы:**\n"
                + "\n".join(notification_lines)
            ),
            inline=False,
        )
        embed.add_field(
            name="Роль активности",
            value=(
                f"Статус: **{'Включена' if auto_role else 'Выключена'}**\n"
                f"Текущая роль: {role_text}\n"
                "Если отключить, роль снимется и больше не будет выдаваться автоматически."
            ),
            inline=False,
        )
        embed.set_footer(text="Уведомления и роль можно менять здесь, а серверные параметры задаются через /setting.")
        return embed

    async def toggle_smart_notifications(self, user_id: int, guild_id: int) -> bool:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return True
            preferences = get_user_preferences(user)
            new_value = not bool(preferences.get("smart_notifications", True))
            preferences["smart_notifications"] = new_value
            if not new_value:
                self._clear_notification_markers_for_user(user)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
        return new_value

    async def toggle_notification_type(self, user_id: int, guild_id: int, preference_key: str) -> bool:
        if preference_key not in SMART_NOTIFICATION_SETTINGS:
            return True

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return True
            preferences = get_user_preferences(user)
            new_value = not bool(preferences.get(preference_key, True))
            preferences[preference_key] = new_value
            if not new_value:
                marker_key = SMART_NOTIFICATION_SETTINGS[preference_key]["marker"]
                self._clear_notification_marker(user, marker_key)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
        return new_value

    async def toggle_auto_casino_role(self, member: discord.Member | discord.User, guild_id: int) -> tuple[bool, bool]:
        role_changed = False
        async with get_user_lock(member.id):
            user = await db.get_user(member.id, guild_id)
            if not user:
                return True, False
            preferences = get_user_preferences(user)
            new_value = not bool(preferences.get("auto_casino_role", True))
            preferences["auto_casino_role"] = new_value
            await db.update_user(member.id, guild_id, {"game_stats": user.get("game_stats", {})})

        if isinstance(member, discord.Member):
            role_id = await resolve_activity_role_id(member.guild, guild_id)
            role = member.guild.get_role(role_id) if role_id is not None else None
            if role is not None:
                try:
                    if new_value and role not in member.roles:
                        await member.add_roles(role, reason="Игрок включил автовыдачу роли активности")
                        role_changed = True
                    elif not new_value and role in member.roles:
                        await member.remove_roles(role, reason="Игрок отключил автовыдачу роли активности")
                        role_changed = True
                except Exception:
                    pass
        return new_value, role_changed

    def _get_business_ready_marker(self, user: dict[str, Any], now: datetime) -> tuple[int, str | None]:
        ready_tokens: list[str] = []
        businesses = normalize_businesses(user.get("businesses", {}))
        for business_id, entries in businesses.items():
            business = BUSINESSES.get(int(business_id)) if str(business_id).isdigit() else None
            if business is None:
                continue
            for index, entry in enumerate(entries):
                last_collect = normalize_datetime(entry.get("last_collect") or entry.get("last_collected"))
                if last_collect is None or last_collect + timedelta(hours=int(business["time"])) <= now:
                    marker = "none" if last_collect is None else last_collect.isoformat()
                    ready_tokens.append(f"{business_id}:{index}:{marker}")
        if not ready_tokens:
            return 0, None
        ready_tokens.sort()
        return len(ready_tokens), "|".join(ready_tokens)

    def _get_daily_warning_marker(self, user: dict[str, Any], now: datetime) -> str | None:
        last_daily = normalize_datetime(user.get("last_daily"))
        daily_streak = int(user.get("daily_streak", 0) or 0)
        if last_daily is None or daily_streak <= 0:
            return None

        streak_expires_at = last_daily + timedelta(hours=48)
        warning_at = streak_expires_at - timedelta(hours=2)
        if warning_at <= now < streak_expires_at:
            return last_daily.isoformat()
        return None

    async def _get_notification_channel(self, guild_id: int) -> discord.TextChannel | None:
        return await get_preferred_guild_text_channel(self.bot, guild_id)

    async def _build_smart_notification_lines(
        self,
        user: dict[str, Any],
        guild_id: int,
        now: datetime,
    ) -> tuple[list[str], bool, dict[str, str]]:
        user_id = int(user.get("user_id", 0) or 0)
        if user_id <= 0:
            return [], False, {}

        lines: list[str] = []
        markers = self._get_notification_markers(user)
        next_markers = dict(markers)
        deposit_enabled = notification_type_enabled(user, "notify_deposit")
        rent_enabled = notification_type_enabled(user, "notify_rent")
        business_enabled = notification_type_enabled(user, "notify_business")
        harvest_enabled = notification_type_enabled(user, "notify_harvest")
        daily_enabled = notification_type_enabled(user, "notify_daily_streak")

        deposit = deposit_snapshot(user)
        deposit_marker = deposit["matures_at"].isoformat() if deposit["active"] and deposit["matured"] and deposit["matures_at"] else None
        deposit_changed = self._update_notification_marker(next_markers, "deposit_ready", deposit_marker if deposit_enabled else None)
        if deposit_enabled and deposit_marker and deposit_changed:
            lines.append("?? Депозит созрел и готов к выдаче через `/bank`.")

        auto_collect_state = get_business_autocollect_state(user)
        if business_enabled and not auto_collect_state.get("enabled"):
            business_count, business_marker = self._get_business_ready_marker(user, now)
            business_changed = self._update_notification_marker(next_markers, "business_ready", business_marker)
            if business_marker and business_changed:
                lines.append(f"?? Бизнесы готовы к сбору: **{business_count}** шт.")
        else:
            self._update_notification_marker(next_markers, "business_ready", None)

        house_cog = self.bot.get_cog("House")
        if house_cog is not None:
            rental_state = house_cog._rental_status(user)
            ready_rentals = rental_state.get("ready_rentals", [])
            rent_marker = "|".join(sorted(str(rental.get("id")) for rental in ready_rentals if rental.get("id"))) or None
            rent_changed = self._update_notification_marker(next_markers, "rent_ready", rent_marker if rent_enabled else None)
            if rent_enabled and rent_marker and rent_changed:
                lines.append(f"?? Аренда готова к сбору: **{len(ready_rentals)}** заявок.")

            game_stats = user.get("game_stats") if isinstance(user.get("game_stats"), dict) else {}
            systems = game_stats.get("_systems") if isinstance(game_stats, dict) else {}
            house_state = systems.get("house") if isinstance(systems, dict) else {}
            if isinstance(house_state, dict):
                refreshed_plots = _refresh_garden_state(house_state, now)
                ready_plot_tokens = [
                    f"{index}:{plot.get('crop_code')}"
                    for index, plot in enumerate(refreshed_plots)
                    if isinstance(plot, dict) and str(plot.get("state") or "") == "ready"
                ]
                harvest_marker = "|".join(ready_plot_tokens) or None
                harvest_changed = self._update_notification_marker(next_markers, "harvest_ready", harvest_marker if harvest_enabled else None)
                if harvest_enabled and harvest_marker and harvest_changed:
                    lines.append(f"?? Урожай готов: **{len(ready_plot_tokens)}** грядок можно собрать.")
        else:
            self._update_notification_marker(next_markers, "rent_ready", None)
            self._update_notification_marker(next_markers, "harvest_ready", None)

        daily_warning_marker = self._get_daily_warning_marker(user, now)
        daily_changed = self._update_notification_marker(next_markers, "daily_warning", daily_warning_marker if daily_enabled else None)
        if daily_enabled and daily_warning_marker and daily_changed:
            lines.append("? Daily streak почти сгорает. Забери `/daily`, чтобы не потерять серию.")

        return lines, next_markers != markers, next_markers

    @tasks.loop(minutes=2)
    async def smart_notifications_loop(self):
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("users").select(
                    "user_id,guild_id,deposit_amount,deposit_rate,deposit_start,deposit_days,last_daily,daily_streak,vip_level,businesses,game_stats"
                ).execute()
            )
        except Exception as exc:
            print(f"Smart notifications loop error: {exc}")
            return

        now = datetime.now(timezone.utc)
        for row in result.data or []:
            user_id = int(row.get("user_id") or 0)
            guild_id = int(row.get("guild_id") or 0)
            if user_id <= 0 or guild_id <= 0:
                continue
            if not smart_notifications_enabled(row):
                if self._clear_notification_markers_for_user(row):
                    await db.update_user(user_id, guild_id, {"game_stats": row.get("game_stats", {})})
                continue

            lines, markers_changed, next_markers = await self._build_smart_notification_lines(row, guild_id, now)
            if not lines:
                if markers_changed:
                    self._set_notification_markers(row, next_markers)
                    await db.update_user(user_id, guild_id, {"game_stats": row.get("game_stats", {})})
                continue

            channel = await self._get_notification_channel(guild_id)
            if channel is None:
                continue

            embed = discord.Embed(
                title="?? Умные уведомления",
                description="\n".join(f"? {line}" for line in lines),
                color=COLORS["info"],
                timestamp=now,
            )
            embed.set_footer(text="Эти уведомления можно отключить через /profile > Настройки.")
            try:
                await channel.send(
                    f"<@{user_id}>",
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions(users=True),
                )
            except Exception:
                continue
            if markers_changed:
                self._set_notification_markers(row, next_markers)
                await db.update_user(user_id, guild_id, {"game_stats": row.get("game_stats", {})})

    @smart_notifications_loop.before_loop
    async def before_smart_notifications_loop(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def _timer_value(now: datetime, ready_at: datetime | None, ready_label: str = "Готово") -> str:
        if ready_at is None or ready_at <= now:
            return f"**{ready_label}**"
        return format_discord_deadline(ready_at)

    @staticmethod
    def _next_ready_at(last_value: datetime | str | None, cooldown: timedelta, now: datetime) -> datetime | None:
        last_dt = normalize_datetime(last_value)
        if last_dt is None:
            return None
        ready_at = last_dt + cooldown
        return ready_at if ready_at > now else None

    @staticmethod
    def _fish_cooldown_minutes(user: dict[str, Any]) -> int:
        current_rod = str(user.get("fishing_rod", "none") or "none")
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        base_cd = 10
        if current_rod == "wooden":
            base_cd = 7
        elif current_rod == "fiberglass":
            base_cd = 5
        elif current_rod == "carbon":
            base_cd = 3
        elif current_rod == "diamond":
            base_cd = 1
        return max(1, int(base_cd * (1 - vip["cooldown_reduction"])))

    @staticmethod
    def _next_kyiv_midnight(now: datetime) -> datetime:
        now_kyiv = now.astimezone(KYIV_TZ)
        return datetime.combine(
            now_kyiv.date() + timedelta(days=1),
            datetime.min.time(),
            tzinfo=KYIV_TZ,
        ).astimezone(timezone.utc)

    @staticmethod
    def _dashboard_status(now: datetime, ready_at: datetime | None, ready_label: str = "Готово") -> str:
        if ready_at is None or ready_at <= now:
            return ready_label
        return f"Через {format_discord_deadline(ready_at)}"

    async def _open_battle_pass(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        view = BattlePassView(interaction.user.id, interaction.guild_id)
        await interaction.response.send_message(embed=await view.build_embed(), view=view)
        view.message = await interaction.original_response()

    async def open_legacy_shop(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        custom_items = await db.get_shop_items(interaction.guild_id)
        view = ShopView(interaction.user.id, interaction.guild_id, user or {}, custom_items)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="battlepass", description="Открыть боевой пропуск")
    async def battlepass(self, interaction: discord.Interaction):
        await self._open_battle_pass(interaction)

    @app_commands.command(name="bp", description="Быстро открыть боевой пропуск")
    async def bp(self, interaction: discord.Interaction):
        await self._open_battle_pass(interaction)

    @app_commands.command(name="timers", description="Показать таймеры и состояние игровых систем")
    async def timers(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
            return

        now = datetime.now(timezone.utc)
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))

        daily_ready = self._next_ready_at(user.get("last_daily"), timedelta(hours=int(24 * (1 - vip["cooldown_reduction"]))), now)
        hourly_ready = self._next_ready_at(user.get("last_hourly"), timedelta(hours=max(1, int(1 * (1 - vip["cooldown_reduction"])))), now)
        work_ready = self._next_ready_at(user.get("last_work"), timedelta(minutes=int(10 * (1 - vip["cooldown_reduction"]))), now)
        crime_ready = self._next_ready_at(user.get("last_crime"), timedelta(minutes=int(30 * (1 - vip["cooldown_reduction"]))), now)
        slut_ready = self._next_ready_at(user.get("last_slut"), timedelta(minutes=int(15 * (1 - vip["cooldown_reduction"]))), now)

        fish_cd = self._fish_cooldown_minutes(user)
        fish_ready = None if fish_cd <= 0 else self._next_ready_at(user.get("last_fish"), timedelta(minutes=fish_cd), now)
        fishing_world = get_world_state(now)

        businesses = normalize_businesses(user.get("businesses", {}))
        ready_businesses = 0
        next_business_ready = None
        total_businesses = 0
        for business_id, entries in businesses.items():
            business = BUSINESSES.get(int(business_id)) if str(business_id).isdigit() else None
            if business is None:
                continue
            for entry in entries:
                total_businesses += 1
                last_collect = normalize_datetime(entry.get("last_collect") or entry.get("last_collected"))
                if last_collect is None:
                    ready_businesses += 1
                    continue
                ready_at = last_collect + timedelta(hours=int(business["time"]))
                if ready_at <= now:
                    ready_businesses += 1
                elif next_business_ready is None or ready_at < next_business_ready:
                    next_business_ready = ready_at

        auto_state = get_business_autocollect_state(user)
        if not auto_state["owned"]:
            auto_collect_text = "Нет модуля"
        elif not auto_state["enabled"]:
            auto_collect_text = "Выключен"
        else:
            last_run = normalize_datetime(auto_state.get("last_run"))
            next_run = None if last_run is None else last_run + timedelta(hours=int(auto_state["interval_hours"]))
            auto_collect_text = self._timer_value(now, next_run, "готов к запуску")

        if total_businesses <= 0:
            business_collect_text = "Нет бизнесов"
        elif ready_businesses > 0:
            business_collect_text = f"**Готово:** {ready_businesses} шт."
        else:
            business_collect_text = self._timer_value(now, next_business_ready)

        house_cog = self.bot.get_cog("House")
        basement_text = "Система дома недоступна"
        rent_text = "Система дома недоступна"
        if house_cog is not None:
            snapshot = house_cog._house_snapshot(user, interaction.guild_id)
            rental_state = house_cog._rental_status(user)
            if snapshot.get("house_data") is None:
                basement_text = "Дом не куплен"
                rent_text = "Дом не куплен"
            else:
                ready_amount = int(snapshot.get("ready", 0) or 0)
                if int(snapshot.get("hourly_income", 0) or 0) <= 0:
                    basement_text = "Подвал не настроен"
                elif ready_amount > 0:
                    basement_text = f"**Готово:** {format_money(ready_amount)}"
                else:
                    basement_text = f"Заполнится {format_discord_deadline(snapshot.get('next_cap_at'))}"

                ready_rentals = rental_state.get("ready_rentals", [])
                ongoing_rentals = rental_state.get("ongoing_rentals", [])
                if ready_rentals:
                    rent_text = f"**Готово:** {len(ready_rentals)} шт."
                elif ongoing_rentals:
                    next_rent_ready = min(normalize_datetime(rental.get("ends_at")) or now for rental in ongoing_rentals)
                    rent_text = self._timer_value(now, next_rent_ready)
                else:
                    rent_text = "Нет активной аренды"

        reset_at = self._next_kyiv_midnight(now)
        rod_name = FISHING_RODS.get(str(user.get("fishing_rod", "none") or "none"), FISHING_RODS["none"])["name"]
        next_event = fishing_world["next_event_window"]

        ready_count = sum(
            1
            for ready_at in (daily_ready, hourly_ready, work_ready, crime_ready, slut_ready)
            if ready_at is None
        )
        if fish_cd <= 0 or fish_ready is None:
            ready_count += 1
        if ready_businesses > 0:
            ready_count += 1
        if basement_text.startswith("**Готово:**"):
            ready_count += 1
        if rent_text.startswith("**Готово:**"):
            ready_count += 1

        fishing_status = "Без кд" if fish_cd <= 0 else self._dashboard_status(now, fish_ready)
        if fishing_world["active_event"] is not None:
            event_status = f"Активен `{fishing_world['active_event']['name']}` до {format_discord_deadline(fishing_world['active_event']['end_at'].astimezone(timezone.utc))}"
        elif next_event is not None:
            event_status = f"Следующее окно {format_discord_deadline(next_event['start_at'].astimezone(timezone.utc))}"
        else:
            event_status = "Следующее окно пока не найдено"

        shield_until = normalize_datetime(user.get("shield_until"))
        shield_text = "Не активна"
        if has_active_shield(user) and shield_until is not None:
            shield_text = f"Активна до {format_discord_deadline(shield_until)}"

        game_stats = user.get("game_stats") if isinstance(user.get("game_stats"), dict) else {}
        systems = game_stats.get("_systems") if isinstance(game_stats, dict) else {}
        house_state = systems.get("house") if isinstance(systems, dict) else {}
        garden = house_state.get("garden") if isinstance(house_state, dict) and isinstance(house_state.get("garden"), dict) else {}
        plots = garden.get("plots") if isinstance(garden.get("plots"), list) else []
        ready_plots = sum(1 for plot in plots if isinstance(plot, dict) and str(plot.get("state") or "") == "ready")
        dry_plots = sum(1 for plot in plots if isinstance(plot, dict) and str(plot.get("state") or "") == "dry")
        active_plots = sum(1 for plot in plots if isinstance(plot, dict) and plot.get("crop_code"))
        if basement_text == "Дом не куплен":
            garden_text = "Дом не куплен"
        elif active_plots <= 0:
            garden_text = "Нет посадок"
        elif ready_plots > 0:
            garden_text = f"Готово: {ready_plots} гряд."
        elif dry_plots > 0:
            garden_text = f"Нужен полив: {dry_plots} гряд."
        else:
            garden_text = f"Растёт: {active_plots} гряд."

        economy_lines = [
            f"• /daily — {self._dashboard_status(now, daily_ready)}",
            f"• /hourly — {self._dashboard_status(now, hourly_ready)}",
            f"• /work — {self._dashboard_status(now, work_ready)}",
        ]
        activity_lines = [
            f"• /crime — {self._dashboard_status(now, crime_ready)}",
            f"• /slut — {self._dashboard_status(now, slut_ready)}",
            f"• Теневая страховка — {shield_text}",
        ]
        fishing_lines = [
            f"• Заброс — {fishing_status}",
            f"• Погода — {describe_world_lines(fishing_world)[1].replace('• ', '')}",
            f"• Ивент — {event_status}",
        ]
        business_lines = [
            f"• Ручной сбор — {business_collect_text.replace('**', '')}",
            f"• Автосбор — {auto_collect_text.replace('**', '')}",
            f"• Всего точек — {total_businesses}",
        ]
        house_lines = [
            f"• Подвал — {basement_text.replace('**', '')}",
            f"• Аренда — {rent_text.replace('**', '')}",
            f"• Сад — {garden_text}",
        ]
        reset_lines = [
            f"• Новый daily — {format_discord_deadline(reset_at)}",
            f"• Смена фазы — {format_discord_deadline(fishing_world['next_phase_change_at'])}",
            f"• Погода/спот — {format_discord_deadline(fishing_world['next_hotspot_change_at'])}",
        ]

        embed = discord.Embed(
            title="?? Панель таймеров",
            description=(
                "Самое важное по кулдаунам и системам аккаунта в одном экране.\n"
                f"Доступно прямо сейчас: **{ready_count}** • Активная удочка: **{rod_name}**"
            ),
            color=COLORS["info"],
            timestamp=now,
        )
        embed.add_field(
            name="?? Экономика",
            value="\n".join(economy_lines),
            inline=True,
        )
        embed.add_field(
            name="?? Активности",
            value="\n".join(activity_lines),
            inline=True,
        )
        embed.add_field(
            name="?? Рыбалка",
            value="\n".join(fishing_lines),
            inline=True,
        )
        embed.add_field(
            name="?? Бизнесы",
            value="\n".join(business_lines),
            inline=True,
        )
        embed.add_field(
            name="?? Дом",
            value="\n".join(house_lines),
            inline=False,
        )
        embed.add_field(
            name="?? Сбросы",
            value="\n".join(reset_lines),
            inline=False,
        )
        embed.set_footer(text="Статусы с «Через …» обновляются автоматически через Discord-таймеры.")
        await interaction.response.send_message(embed=embed)
        try:
            schedule_message_cleanup(await interaction.original_response())
        except Exception:
            pass

    @app_commands.command(name="setting", description="Настроить канал и роль активности для сервера")
    async def setting(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if guild is None or member is None:
            await interaction.response.send_message("Эта команда доступна только внутри сервера.", ephemeral=True)
            return
        if not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            await interaction.response.send_message("Нужны права `Управление сервером`.", ephemeral=True)
            return

        view = ServerSettingsView(self, interaction.user.id, guild.id)
        embed = await self.build_server_settings_embed(guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(UserCog(bot))



