from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fishing import InventoryView as LegacyInventoryView
from config import COLORS
from inventory_system import ensure_inventory_state, get_fish_items, get_general_items
from legacy.easter_archive import EASTER_POND_ZONE_KEY, easter_pond_available
from utils import check_channel, safe_defer, safe_edit_original_response, send_wrong_channel_message


def _item_type_total(general_items: list[dict[str, Any]], *types: str) -> int:
    allowed = {str(item_type) for item_type in types}
    total = 0
    for item in general_items:
        if str(item.get("item_type") or "") not in allowed:
            continue
        total += max(1, int(item.get("quantity", 1) or 1))
    return total


def _inventory_sections(general_items: list[dict[str, Any]]) -> dict[str, int]:
    cases = _item_type_total(general_items, "case")
    antiquary = sum(
        max(1, int(item.get("quantity", 1) or 1))
        for item in general_items
        if str(item.get("item_type") or "").startswith("antiquary_")
    )
    equipment = _item_type_total(
        general_items,
        "dive_tank",
        "dive_gear",
        "dig_tool",
        "bait_bundle",
        "black_market_item",
        "shield_card",
        "cash_bundle",
        "house_wallet_cache",
        "crypto_cache",
        "cosmetic_pack",
    )
    home = _item_type_total(
        general_items,
        "home_furniture",
        "seed_packet",
        "watering_can_upgrade",
    )
    total_general = sum(max(1, int(item.get("quantity", 1) or 1)) for item in general_items)
    other = max(0, total_general - cases - antiquary - equipment - home)
    return {
        "cases": cases,
        "antiquary": antiquary,
        "equipment": equipment,
        "home": home,
        "other": other,
        "total_general": total_general,
    }


class InventoryV2View(LegacyInventoryView):
    def __init__(self, inventory_cog: "InventoryCommandsCog", fishing_cog: Any, user_id: int, guild_id: int):
        self.inventory_cog = inventory_cog
        super().__init__(fishing_cog, user_id, guild_id)
        self.general_btn.label = "🎒 Предметы"
        self.fish_btn.label = "🐟 Рыба"
        self.gear_btn.label = "🎣 Снаряжение"

    async def _refresh_view(self, interaction: discord.Interaction):
        embed = await self.inventory_cog.build_inventory_embed(self.user_id, self.guild_id, self.active_tab, self.page)
        user, _, _, fish_items, general_items = await self.cog._inventory_snapshot(self.user_id, self.guild_id)
        self.sync_buttons(user, fish_items, general_items)
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)

    def sync_buttons(self, user: dict[str, Any] | None, fish_items: list[dict[str, Any]], general_items: list[dict[str, Any]]):
        super().sync_buttons(user, fish_items, general_items)
        self.general_btn.label = "🎒 Предметы"
        self.fish_btn.label = "🐟 Рыба"
        self.gear_btn.label = "🎣 Снаряжение"


class InventoryCommandsCog(commands.Cog, name="InventoryUI"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _fishing_cog(self):
        return self.bot.get_cog("Fishing")

    async def build_inventory_embed(self, user_id: int, guild_id: int, tab: str = "general", page: int = 0) -> discord.Embed:
        fishing_cog = self._fishing_cog()
        if fishing_cog is None:
            return discord.Embed(title="Инвентарь", description="Система рыбалки недоступна.", color=COLORS["warning"])

        user, fishing, _, _, _ = await fishing_cog._inventory_snapshot(user_id, guild_id)
        embed = await fishing_cog.build_inventory_embed(user_id, guild_id, tab, page)
        if not user:
            return embed

        inventory = ensure_inventory_state(user)
        fish_items = get_fish_items(user)
        general_items = get_general_items(user)
        sections = _inventory_sections(general_items)

        last_catch = fishing.get("last_catch") if isinstance(fishing.get("last_catch"), dict) else None
        selected_zone = str(fishing.get("selected_zone", "river_bank") or "river_bank")
        if selected_zone == EASTER_POND_ZONE_KEY and not easter_pond_available():
            selected_zone = "river_bank"

        active_tab_name = {
            "general": "🎒 Предметы",
            "fish": "🐟 Рыба",
            "gear": "🎣 Снаряжение",
        }.get(tab, "🎒 Инвентарь")

        embed.title = f"{active_tab_name} • Инвентарь"
        embed.add_field(
            name="Карточка инвентаря",
            value=(
                f"Рыба: **{len(fish_items)}**\n"
                f"Предметы: **{sections['total_general']}**\n"
                f"Кейсы и контрабанда: **{sections['cases']}**\n"
                f"Артефакты / реликвии: **{sections['antiquary']}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Категории",
            value=(
                f"Экспедиции: **{sections['equipment']}**\n"
                f"Дом и сад: **{sections['home']}**\n"
                f"Прочее: **{sections['other']}**\n"
                f"Текущая вкладка: **{active_tab_name}**"
            ),
            inline=True,
        )

        summary_lines = [
            f"Удочка: **{fishing_cog.display_rod_name(str(user.get('fishing_rod', 'none') or 'none'))}**",
            f"Снасть: **{fishing_cog.display_tackle_name(str(fishing.get('equipped_tackle', 'starter') or 'starter'))}**",
            f"Наживка: **{fishing_cog.display_bait_name(fishing.get('equipped_bait'))}**",
            f"Зона: **{fishing_cog.display_zone_name(selected_zone)}**",
        ]
        if last_catch:
            summary_lines.append(
                f"Последний улов: **{last_catch.get('name', 'Рыба')}** • **{fishing_cog._format_weight(last_catch.get('weight_kg', 0))}**"
            )
        embed.add_field(name="Сейчас с собой", value="\n".join(summary_lines), inline=False)

        if tab == "general":
            action_lines = [
                "Открывай кейсы и активируй редкие предметы прямо из этой вкладки.",
                "Контрабанда и расходники из `/blackmarket` тоже лежат здесь.",
                "Артефакты для Антиквара можно сразу продать через `/blackmarket` → `🏺 Антиквар`.",
            ]
        elif tab == "fish":
            action_lines = [
                "Редкие уловы выгоднее держать до хорошего рыночного окна.",
                "Лишнюю рыбу можно быстро продать, а любимую оставить в профиле.",
                "Смотри погоду и ивенты: они влияют на стоимость и редкость улова.",
            ]
        else:
            action_lines = [
                "Снаряжение для `/dive` и `/dig` хранится здесь же, рядом с рыболовным.",
                "Баллоны, фонарик и раскопочный набор тратятся только при запуске экспедиции.",
                "Если место в голове закончилось, ориентируйся по карточкам и категориям сверху.",
            ]
        embed.add_field(name="Быстрые действия", value="\n".join(action_lines), inline=False)

        embed.set_footer(
            text=(
                f"Слотов рыбы: {len(inventory.get('fish_items', []))} • "
                f"слотов предметов: {len(inventory.get('general_items', []))} • "
                "переключай вкладки кнопками ниже"
            )
        )
        return embed

    @app_commands.command(name="inventory", description="Открыть инвентарь рыбы, предметов и снаряжения")
    async def inventory(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return

        fishing_cog = self._fishing_cog()
        if fishing_cog is None:
            await interaction.edit_original_response(content="Система рыбалки недоступна.")
            return

        view = InventoryV2View(self, fishing_cog, interaction.user.id, interaction.guild_id)
        embed = await self.build_inventory_embed(interaction.user.id, interaction.guild_id, view.active_tab, view.page)
        user, _, _, fish_items, general_items = await fishing_cog._inventory_snapshot(interaction.user.id, interaction.guild_id)
        view.sync_buttons(user, fish_items, general_items)
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(InventoryCommandsCog(bot))
