from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fishing import EnhancedFishShopView
from cogs.house import buy_furniture_item, buy_seed_packet, buy_watering_can_upgrade, migrate_legacy_reserved_furniture
from cogs.mining import FURNITURE_ITEMS, GARDEN_CROPS, GPU_MODELS, GPU_ORDER, HOUSE_ORDER, HOUSE_TYPES, WATERING_CANS, _house_index, _house_state, format_money
from cogs.user import ShopView as LegacyMainShopView
from config import COLORS
from database import db
from inventory_system import count_general_items
from utils import check_channel, safe_defer, schedule_message_cleanup, send_wrong_channel_message

SHOP_PAGE_SIZE = 3
SHOP_CATEGORIES = [
    ("main", "Главное"),
    ("property", "Недвижимость"),
    ("fishing", "Рыбалка"),
    ("garden", "Садовод"),
    ("ikea", "ИКЕА"),
]

MAIN_SHOP_SECTIONS = [
    ("overview", "Главное"),
    ("vip", "VIP"),
    ("exchange", "Обмен"),
    ("upgrades", "Улучшения"),
    ("server", "Сервер"),
    ("customize", "Кастомизация"),
]


def _category_options(current: str) -> list[discord.SelectOption]:
    return [discord.SelectOption(label=label, value=value, default=value == current) for value, label in SHOP_CATEGORIES]


def _shop_navigation_options(current_category: str, current_main_page: str = "overview") -> list[discord.SelectOption]:
    options: list[discord.SelectOption] = []
    for value, label in MAIN_SHOP_SECTIONS:
        options.append(
            discord.SelectOption(
                label=label,
                value=f"main:{value}",
                description="Раздел главного магазина",
                default=current_category == "main" and current_main_page == value,
            )
        )
    category_descriptions = {
        "property": "Дома, подвал и GPU",
        "fishing": "Удочки, снасти и наживка",
        "garden": "Семена и лейки",
        "ikea": "Мебель и декор дома",
    }
    for value, label in SHOP_CATEGORIES:
        if value == "main":
            continue
        options.append(
            discord.SelectOption(
                label=label,
                value=f"category:{value}",
                description=category_descriptions.get(value, "Раздел магазина"),
                default=current_category == value,
            )
        )
    return options


def _shop_world_lines(shop_cog: "ShopCommandsCog", guild_id: int) -> list[str]:
    systems_cog = shop_cog.bot.get_cog("Systems")
    if systems_cog is None:
        return ["Мир сервера сейчас недоступен."]

    snapshot = systems_cog.get_world_snapshot(guild_id)
    event = snapshot.get("active_event")
    weather = snapshot.get("weather") or {}
    lines = [
        f"Погода: **{weather.get('name', 'Ясно')}**",
        f"Время: **{snapshot.get('time_phase_name', 'День')}**",
        f"Хотспот: **{snapshot.get('hotspot_name', 'Неизвестно')}**",
    ]
    if isinstance(event, dict):
        lines.append(f"Ивент: **{event.get('name', 'Событие')}**")
    else:
        lines.append("Ивент: **спокойный цикл**")
    return lines


class MainCategoryView(LegacyMainShopView):
    def __init__(
        self,
        shop_cog: "ShopCommandsCog",
        user_id: int,
        guild_id: int,
        user_data: dict[str, Any],
        custom_items: list[dict[str, Any]],
        *,
        active_page: str = "overview",
    ):
        self.shop_cog = shop_cog
        self._preferred_main_page = active_page
        super().__init__(user_id, guild_id, user_data, custom_items)
        self.active_page = active_page
        self.navigation_select = discord.ui.Select(
            placeholder="Раздел магазина",
            row=0,
            options=_shop_navigation_options("main", self.active_page),
        )
        self.navigation_select.callback = self._on_navigation
        for item in (
            self.overview_btn,
            self.vip_btn,
            self.exchange_btn,
            self.upgrades_btn,
            self.server_btn,
            self.customize_btn,
        ):
            self._toggle_visibility(item, False)
        self.add_item(self.navigation_select)
        self.action_btn_1.row = 1
        self.action_btn_2.row = 1
        self.action_btn_3.row = 1
        self.prev_btn.row = 2
        self.next_btn.row = 2
        self._sync_buttons()

    def _toggle_visibility(self, item: discord.ui.Item[Any], visible: bool):
        if visible and item not in self.children:
            self.add_item(item)
        elif not visible and item in self.children:
            self.remove_item(item)

    def _sync_buttons(self):
        super()._sync_buttons()
        navigation_select = getattr(self, "navigation_select", None)
        if navigation_select is None:
            self.active_page = getattr(self, "_preferred_main_page", self.active_page)
            return
        navigation_select.options = _shop_navigation_options("main", self.active_page)
        for item in (
            self.overview_btn,
            self.vip_btn,
            self.exchange_btn,
            self.upgrades_btn,
            self.server_btn,
            self.customize_btn,
        ):
            self._toggle_visibility(item, False)
        self._toggle_visibility(navigation_select, True)

        show_prev_next = self.active_page in {"vip", "server", "customize"}
        self._toggle_visibility(self.prev_btn, show_prev_next)
        self._toggle_visibility(self.next_btn, show_prev_next)

        for item in (self.action_btn_1, self.action_btn_2, self.action_btn_3):
            should_show = not item.disabled and item.label not in {"Недоступно", "Выбери вкладку"}
            self._toggle_visibility(item, should_show)

        if self.active_page == "overview":
            self._toggle_visibility(self.action_btn_2, False)
            self._toggle_visibility(self.action_btn_3, False)
        elif self.active_page == "exchange":
            self._toggle_visibility(self.action_btn_3, False)

    def build_embed(self) -> discord.Embed:
        embed = super().build_embed()
        if self.active_page == "overview":
            embed.title = "🛍️ Витрина сервера"
            embed.description = "Единый магазин для VIP, обмена, улучшений, серверных товаров и кастомизации."
            embed.add_field(
                name="Разделы витрины",
                value=(
                    "🏆 VIP и сезонные покупки\n"
                    "💱 Обмен валют без лишних окон\n"
                    "🧩 Улучшения и серверные лоты\n"
                    "🎨 Кастомизация профиля"
                ),
                inline=False,
            )
            embed.add_field(name="Пульс сервера", value="\n".join(_shop_world_lines(self.shop_cog, self.guild_id)), inline=False)
        embed.set_footer(text="Выбирай раздел через селект сверху, а покупки подтверждай кнопками ниже.")
        return embed

    async def _on_navigation(self, interaction: discord.Interaction):
        raw = str(self.navigation_select.values[0]) if self.navigation_select.values else "main:overview"
        if raw.startswith("main:"):
            target = raw.split(":", 1)[1] or "overview"
            async with self._view_lock:
                if not await safe_defer(interaction):
                    return
                if self.active_page != target:
                    self.page_index = 0
                self.active_page = target
                await self._refresh_message(interaction)
            return
        target = raw.split(":", 1)[1] if ":" in raw else "main"
        await self.shop_cog.open_category(interaction, self.user_id, self.guild_id, target)


class FishingCategoryView(EnhancedFishShopView):
    def __init__(self, shop_cog: "ShopCommandsCog", fishing_cog: Any, user_id: int, guild_id: int):
        self.shop_cog = shop_cog
        super().__init__(fishing_cog, user_id, guild_id)
        self.navigation_select = discord.ui.Select(
            placeholder="Раздел магазина",
            row=4,
            options=_shop_navigation_options("fishing"),
        )
        self.navigation_select.callback = self._on_navigation
        self.add_item(self.navigation_select)

    async def _on_navigation(self, interaction: discord.Interaction):
        raw = str(self.navigation_select.values[0]) if self.navigation_select.values else "category:fishing"
        if raw.startswith("main:"):
            target = raw.split(":", 1)[1] or "overview"
            await self.shop_cog.open_main_page(interaction, self.user_id, self.guild_id, target)
            return
        target = raw.split(":", 1)[1] if ":" in raw else "fishing"
        await self.shop_cog.open_category(interaction, self.user_id, self.guild_id, target)


class _BaseCategoryView(discord.ui.View):
    category_key = "main"

    def __init__(self, shop_cog: "ShopCommandsCog", user_id: int, guild_id: int, *, page: int = 0):
        super().__init__(timeout=120)
        self.shop_cog = shop_cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.page = page
        self.message: discord.Message | None = None
        self.navigation_select = discord.ui.Select(
            placeholder="Раздел магазина",
            row=0,
            options=_shop_navigation_options(self.category_key),
        )
        self.navigation_select.callback = self._on_navigation
        self.add_item(self.navigation_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это окно магазина открыто не для тебя.", ephemeral=True)
            return False
        return True

    async def _on_navigation(self, interaction: discord.Interaction):
        raw = str(self.navigation_select.values[0]) if self.navigation_select.values else f"category:{self.category_key}"
        if raw.startswith("main:"):
            target = raw.split(":", 1)[1] or "overview"
            await self.shop_cog.open_main_page(interaction, self.user_id, self.guild_id, target)
            return
        target = raw.split(":", 1)[1] if ":" in raw else self.category_key
        await self.shop_cog.open_category(interaction, self.user_id, self.guild_id, target)

    async def _show_result(self, interaction: discord.Interaction, payload: discord.Embed | str):
        if isinstance(payload, discord.Embed):
            await interaction.followup.send(embed=payload, ephemeral=True)
        else:
            await interaction.followup.send(str(payload), ephemeral=True)

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


class PropertyCategoryView(_BaseCategoryView):
    category_key = "property"

    def __init__(self, shop_cog: "ShopCommandsCog", user_id: int, guild_id: int, *, page: int = 0):
        super().__init__(shop_cog, user_id, guild_id, page=page)
        self.prev_btn = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, row=1)
        self.buy_1 = discord.ui.Button(label="Купить 1", style=discord.ButtonStyle.success, row=1)
        self.buy_2 = discord.ui.Button(label="Купить 2", style=discord.ButtonStyle.success, row=1)
        self.buy_3 = discord.ui.Button(label="Купить 3", style=discord.ButtonStyle.success, row=1)
        self.next_btn = discord.ui.Button(label="Дальше", style=discord.ButtonStyle.secondary, row=1)
        self.refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
        self.prev_btn.callback = self._on_prev
        self.buy_1.callback = lambda interaction: self._buy_slot(interaction, 0)
        self.buy_2.callback = lambda interaction: self._buy_slot(interaction, 1)
        self.buy_3.callback = lambda interaction: self._buy_slot(interaction, 2)
        self.next_btn.callback = self._on_next
        self.refresh_btn.callback = self._on_refresh
        for item in (self.prev_btn, self.buy_1, self.buy_2, self.buy_3, self.next_btn, self.refresh_btn):
            self.add_item(item)

    def _items(self) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = [("house", house_id) for house_id in HOUSE_ORDER]
        items.extend(("gpu", gpu_id) for gpu_id in GPU_ORDER)
        return items

    def _visible_items(self) -> list[tuple[str, str]]:
        start = self.page * SHOP_PAGE_SIZE
        items = self._items()
        return items[start:start + SHOP_PAGE_SIZE]

    def _max_page(self) -> int:
        items = self._items()
        return max(0, (len(items) - 1) // SHOP_PAGE_SIZE)

    async def render_embed(self) -> discord.Embed:
        user = await db.get_user(self.user_id, self.guild_id) or {"balance": 0, "game_stats": {}}
        current_house_id = _house_state(user).get("owned_house_id")
        current_index = _house_index(current_house_id)
        balance = int(user.get("balance", 0) or 0)
        current_house_name = HOUSE_TYPES[current_house_id]["name"] if current_house_id in HOUSE_TYPES else "Пока нет"
        house_cog = self.shop_cog._house_core()
        snapshot = house_cog._house_snapshot(user, self.guild_id) if house_cog is not None else {"installed_count": 0, "capacity": 0}
        embed = discord.Embed(
            title="🏠 Недвижимость и подвал",
            description=(
                f"Баланс: **{format_money(balance)}**\n"
                f"Текущий дом: **{current_house_name}**\n"
                f"GPU в подвале: **{int(snapshot.get('installed_count', 0) or 0)}/{int(snapshot.get('capacity', 0) or 0)}**"
            ),
            color=COLORS["info"],
        )
        embed.add_field(
            name="Что здесь покупают",
            value=(
                "Дома открывают новые уровни подвала и доступ к части систем `/house`.\n"
                "GPU сразу усиливают подвал и пассивную добычу."
            ),
            inline=False,
        )
        embed.add_field(name="Пульс сервера", value="\n".join(_shop_world_lines(self.shop_cog, self.guild_id)), inline=False)
        lines = []
        installed_count = int(snapshot.get("installed_count", 0) or 0)
        capacity = int(snapshot.get("capacity", 0) or 0)
        for index, (item_type, item_key) in enumerate(self._visible_items(), start=1):
            if item_type == "house":
                item = HOUSE_TYPES[item_key]
                item_index = _house_index(item_key)
                if item_key == current_house_id:
                    status = "Уже куплен"
                elif current_index >= 0 and item_index <= current_index:
                    status = "Уровень уже пройден"
                elif balance >= int(item["price"]):
                    status = "Можно купить"
                else:
                    status = f"Не хватает {format_money(int(item['price']) - balance)}"
                lines.append(
                    f"**{index}. {item['name']}**\n"
                    f"{item['description']}\n"
                    f"Цена: **{format_money(int(item['price']))}** • Подвал: **до {int(item['max_basement_level'])} ур.**\n"
                    f"Статус: **{status}**"
                )
            else:
                gpu = GPU_MODELS[item_key]
                if current_house_id not in HOUSE_TYPES:
                    status = "Сначала купи дом"
                elif installed_count >= capacity:
                    status = "Слоты подвала заполнены"
                elif balance >= int(gpu["price"]):
                    status = "Можно купить"
                else:
                    status = f"Не хватает {format_money(int(gpu['price']) - balance)}"
                lines.append(
                    f"**{index}. {gpu['emoji']} {gpu['name']}**\n"
                    f"{gpu['description']}\n"
                    f"Цена: **{format_money(int(gpu['price']))}** • Доход: **{format_money(int(gpu['hourly_income']))}/ч**\n"
                    f"Статус: **{status}**"
                )
        embed.add_field(name=f"Страница {self.page + 1}/{self._max_page() + 1}", value="\n\n".join(lines), inline=False)
        embed.set_footer(text="Покупка идёт здесь, а детальное управление домом и подвалом остаётся в `/house`.")
        return embed

    async def _rerender(self, interaction: discord.Interaction):
        view = PropertyCategoryView(self.shop_cog, self.user_id, self.guild_id, page=self.page)
        view.prev_btn.disabled = self.page <= 0
        view.next_btn.disabled = self.page >= view._max_page()
        embed = await view.render_embed()
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def _buy_slot(self, interaction: discord.Interaction, slot: int):
        await interaction.response.defer()
        visible = self._visible_items()
        if slot >= len(visible):
            await interaction.followup.send("На этой кнопке сейчас нет товара.", ephemeral=True)
            return
        house_cog = self.shop_cog._house_core()
        if house_cog is None:
            payload = (False, "Система дома недоступна.")
        else:
            item_type, item_key = visible[slot]
            if item_type == "house":
                payload = await house_cog.buy_house(self.user_id, self.guild_id, item_key)
            else:
                payload = await house_cog.buy_gpu(self.user_id, self.guild_id, item_key)
        await self._rerender(interaction)
        await self._show_result(interaction, payload[1])

    async def _on_prev(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        await self._rerender(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = min(self._max_page(), self.page + 1)
        await self._rerender(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction)


class GardenCategoryView(_BaseCategoryView):
    category_key = "garden"

    def __init__(self, shop_cog: "ShopCommandsCog", user_id: int, guild_id: int, *, page: int = 0):
        super().__init__(shop_cog, user_id, guild_id, page=page)
        self.prev_btn = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, row=1)
        self.buy_1 = discord.ui.Button(label="Купить 1", style=discord.ButtonStyle.success, row=1)
        self.buy_2 = discord.ui.Button(label="Купить 2", style=discord.ButtonStyle.success, row=1)
        self.buy_3 = discord.ui.Button(label="Купить 3", style=discord.ButtonStyle.success, row=1)
        self.next_btn = discord.ui.Button(label="Дальше", style=discord.ButtonStyle.secondary, row=1)
        self.refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
        self.prev_btn.callback = self._on_prev
        self.buy_1.callback = lambda interaction: self._buy_slot(interaction, 0)
        self.buy_2.callback = lambda interaction: self._buy_slot(interaction, 1)
        self.buy_3.callback = lambda interaction: self._buy_slot(interaction, 2)
        self.next_btn.callback = self._on_next
        self.refresh_btn.callback = self._on_refresh
        for item in (self.prev_btn, self.buy_1, self.buy_2, self.buy_3, self.next_btn, self.refresh_btn):
            self.add_item(item)

    def _items(self) -> list[tuple[str, str, dict[str, Any]]]:
        items = [("seed", crop_code, crop) for crop_code, crop in GARDEN_CROPS.items()]
        items.extend(("can", can_key, can) for can_key, can in WATERING_CANS.items())
        return items

    def _visible_items(self) -> list[tuple[str, str, dict[str, Any]]]:
        items = self._items()
        start = self.page * SHOP_PAGE_SIZE
        return items[start:start + SHOP_PAGE_SIZE]

    def _max_page(self) -> int:
        items = self._items()
        return max(0, (len(items) - 1) // SHOP_PAGE_SIZE) if items else 0

    async def render_embed(self) -> discord.Embed:
        user = await db.get_user(self.user_id, self.guild_id) or {"balance": 0, "game_stats": {}}
        house_state = _house_state(user)
        current_can = str(((house_state.get("garden") or {}) if isinstance(house_state.get("garden"), dict) else {}).get("watering_can") or "basic")
        embed = discord.Embed(
            title="🌱 Садовая лавка",
            description=f"Баланс: **{format_money(int(user.get('balance', 0) or 0))}**\nАктивная лейка: **{WATERING_CANS.get(current_can, WATERING_CANS['basic'])['name']}**",
            color=COLORS["success"],
        )
        embed.add_field(
            name="Что здесь покупают",
            value=(
                "Семена идут в огород через `/house` → `Сад`.\n"
                "Лейки сокращают микроменеджмент и помогают держать цикл роста под контролем."
            ),
            inline=False,
        )
        embed.add_field(name="Пульс сервера", value="\n".join(_shop_world_lines(self.shop_cog, self.guild_id)), inline=False)
        lines = []
        for index, (item_type, item_key, item) in enumerate(self._visible_items(), start=1):
            if item_type == "seed":
                lines.append(
                    f"**{index}. {item['emoji']} Семена {item['name']}**\n"
                    f"Цена: **{format_money(int(item['price']))}**\n"
                    f"Рост: **{int(item['growth_hours'])} ч** • Урожай: **{int(item['yield_min'])}-{int(item['yield_max'])}**"
                )
            else:
                lines.append(
                    f"**{index}. {item['emoji']} {item['name']}**\n"
                    f"Цена: **{format_money(int(item['price']))}**\n"
                    f"Интервал полива: **{int(item['water_interval_hours'])} ч**"
                )
        embed.add_field(name=f"Страница {self.page + 1}/{self._max_page() + 1}", value="\n\n".join(lines), inline=False)
        embed.set_footer(text="Семена и лейки покупаются тут, а применяются уже внутри `/house` → `Сад`.")
        return embed

    async def _rerender(self, interaction: discord.Interaction):
        view = GardenCategoryView(self.shop_cog, self.user_id, self.guild_id, page=self.page)
        view.prev_btn.disabled = self.page <= 0
        view.next_btn.disabled = self.page >= view._max_page()
        embed = await view.render_embed()
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def _buy_slot(self, interaction: discord.Interaction, slot: int):
        await interaction.response.defer()
        visible = self._visible_items()
        if slot >= len(visible):
            await interaction.followup.send("На этой кнопке сейчас нет товара.", ephemeral=True)
            return
        item_type, item_key, _ = visible[slot]
        payload = await (buy_seed_packet(self.user_id, self.guild_id, item_key) if item_type == "seed" else buy_watering_can_upgrade(self.user_id, self.guild_id, item_key))
        await self._rerender(interaction)
        await self._show_result(interaction, payload[1])

    async def _on_prev(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        await self._rerender(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = min(self._max_page(), self.page + 1)
        await self._rerender(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction)


class IkeaCategoryView(_BaseCategoryView):
    category_key = "ikea"

    def __init__(self, shop_cog: "ShopCommandsCog", user_id: int, guild_id: int):
        super().__init__(shop_cog, user_id, guild_id, page=0)
        self.buy_1 = discord.ui.Button(label="Купить 1", style=discord.ButtonStyle.success, row=1)
        self.buy_2 = discord.ui.Button(label="Купить 2", style=discord.ButtonStyle.success, row=1)
        self.buy_3 = discord.ui.Button(label="Купить 3", style=discord.ButtonStyle.success, row=1)
        self.refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
        self.buy_1.callback = lambda interaction: self._buy_slot(interaction, 0)
        self.buy_2.callback = lambda interaction: self._buy_slot(interaction, 1)
        self.buy_3.callback = lambda interaction: self._buy_slot(interaction, 2)
        self.refresh_btn.callback = self._on_refresh
        for item in (self.buy_1, self.buy_2, self.buy_3, self.refresh_btn):
            self.add_item(item)

    async def render_embed(self) -> discord.Embed:
        user = await db.get_user(self.user_id, self.guild_id) or {"balance": 0, "game_stats": {}}
        migrated_reserved_furniture = migrate_legacy_reserved_furniture(user)
        if migrated_reserved_furniture:
            await db.update_user(
                self.user_id,
                self.guild_id,
                {
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )
        house_state = _house_state(user)
        owned = set(house_state.get("furniture", []))
        pending = {item_key for item_key in FURNITURE_ITEMS if count_general_items(user, item_type="home_furniture", code=item_key) > 0}
        embed = discord.Embed(
            title="🪑 IKEA / Декор",
            description=f"Баланс: **{format_money(int(user.get('balance', 0) or 0))}**",
            color=COLORS["gold"],
        )
        embed.add_field(
            name="Что здесь покупают",
            value="Мебель попадает в инвентарь дома, а затем ставится уже из `/house` в подходящую комнату.",
            inline=False,
        )
        embed.add_field(name="Пульс сервера", value="\n".join(_shop_world_lines(self.shop_cog, self.guild_id)), inline=False)
        lines = []
        for index, (item_key, item) in enumerate(FURNITURE_ITEMS.items(), start=1):
            status = "Уже куплено" if item_key in owned else "Можно купить"
            if item_key in owned:
                status = "Installed"
            elif item_key in pending:
                status = "In inventory"
            else:
                status = "Available"
            lines.append(
                f"**{index}. {item['emoji']} {item['name']}**\n"
                f"Цена: **{format_money(int(item['price']))}**\n"
                f"Статус: **{status}**"
            )
        embed.add_field(name="Доступные предметы", value="\n\n".join(lines), inline=False)
        embed.set_footer(text="Декор влияет на атмосферу дома и часть связанных систем на сервере.")
        return embed

    async def _rerender(self, interaction: discord.Interaction):
        view = IkeaCategoryView(self.shop_cog, self.user_id, self.guild_id)
        embed = await view.render_embed()
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def _buy_slot(self, interaction: discord.Interaction, slot: int):
        await interaction.response.defer()
        keys = list(FURNITURE_ITEMS.keys())
        if slot >= len(keys):
            await interaction.followup.send("На этой кнопке сейчас нет товара.", ephemeral=True)
            return
        payload = await buy_furniture_item(self.user_id, self.guild_id, keys[slot])
        await self._rerender(interaction)
        await self._show_result(interaction, payload[1])

    async def _on_refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction)


class ShopCommandsCog(commands.Cog, name="ShopUI"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _house_core(self):
        return self.bot.get_cog("House")

    def _fishing_cog(self):
        return self.bot.get_cog("Fishing")

    async def open_main_page(self, interaction: discord.Interaction, user_id: int, guild_id: int, active_page: str = "overview"):
        user = await db.get_user(user_id, guild_id)
        custom_items = await db.get_shop_items(guild_id)
        view = MainCategoryView(self, user_id, guild_id, user or {}, custom_items, active_page=active_page)
        embed = view.build_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    async def open_category(self, interaction: discord.Interaction, user_id: int, guild_id: int, category: str):
        if category == "main":
            await self.open_main_page(interaction, user_id, guild_id, "overview")
            return
        elif category == "fishing":
            fishing_cog = self._fishing_cog()
            if fishing_cog is None:
                await interaction.response.send_message("Рыболовный раздел недоступен.", ephemeral=True)
                return
            view = FishingCategoryView(self, fishing_cog, user_id, guild_id)
            state = await fishing_cog.get_fishing_profile(user_id, guild_id)
            view._sync_buttons(state)
            embed = await fishing_cog.build_fishshop_embed_v2(user_id, guild_id, view.active_tab, view.page)
        elif category == "property":
            view = PropertyCategoryView(self, user_id, guild_id, page=0)
            embed = await view.render_embed()
            view.prev_btn.disabled = True
        elif category == "garden":
            view = GardenCategoryView(self, user_id, guild_id, page=0)
            embed = await view.render_embed()
            view.prev_btn.disabled = True
        else:
            view = IkeaCategoryView(self, user_id, guild_id)
            embed = await view.render_embed()

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="shop", description="Открыть глобальный магазин")
    async def shop(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        custom_items = await db.get_shop_items(interaction.guild_id)
        view = MainCategoryView(self, interaction.user.id, interaction.guild_id, user or {}, custom_items, active_page="overview")
        await interaction.edit_original_response(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(ShopCommandsCog(bot))
