from __future__ import annotations

from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from cogs.fishing import InventoryView as LegacyInventoryView
from easter_event import EASTER_POND_ZONE_KEY, easter_pond_available
from config import COLORS
from utils import check_channel, safe_defer, safe_edit_original_response, send_wrong_channel_message


class InventoryV2View(LegacyInventoryView):
    def __init__(self, inventory_cog: "InventoryCommandsCog", fishing_cog: Any, user_id: int, guild_id: int):
        self.inventory_cog = inventory_cog
        super().__init__(fishing_cog, user_id, guild_id)
        self.general_btn.label = "🎒 Предметы"
        self.fish_btn.label = "🐟 Рыба"
        self.gear_btn.label = "🎣 Снаряжение"

    async def _refresh(self, interaction: discord.Interaction):
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

        last_catch = fishing.get("last_catch") if isinstance(fishing.get("last_catch"), dict) else None
        selected_zone = str(fishing.get('selected_zone', 'river_bank') or 'river_bank')
        if selected_zone == EASTER_POND_ZONE_KEY and not easter_pond_available():
            selected_zone = "river_bank"

        summary_lines = [
            f"Удочка: **{fishing_cog.display_rod_name(str(user.get('fishing_rod', 'none') or 'none'))}**",
            f"Снасть: **{fishing_cog.display_tackle_name(str(fishing.get('equipped_tackle', 'starter') or 'starter'))}**",
            f"Наживка: **{fishing_cog.display_bait_name(fishing.get('equipped_bait'))}**",
            f"Зона: **{fishing_cog.display_zone_name(selected_zone)}**",
        ]
        if last_catch:
            summary_lines.append(
                f"Последний улов: **{last_catch.get('name', 'Рыба')}** за **{fishing_cog._format_weight(last_catch.get('weight_kg', 0))}**"
            )
        embed.add_field(name="Краткая сводка", value="\n".join(summary_lines), inline=False)
        return embed

    @app_commands.command(name="inventory", description="Открыть инвентарь рыбы и предметов")
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
