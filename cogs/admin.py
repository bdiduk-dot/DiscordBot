import asyncio
import copy
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import ADMIN_IDS, BUSINESSES
from database import db, supabase
from utils import ensure_unique_businesses


class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot):
        self.bot = bot

    def is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id in ADMIN_IDS

    @app_commands.command(name="give_money", description="Выдать деньги игроку (только для админа)")
    async def give_money(self, interaction: discord.Interaction, target: discord.Member, amount: int):
        if not self.is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        user = await db.get_user(target.id, interaction.guild_id)
        user["balance"] += amount
        await db.update_user(target.id, interaction.guild_id, user)

        await interaction.response.send_message(f"Выдано **${amount:,}** игроку {target.mention}")

    @app_commands.command(name="give_gems", description="Выдать гемы игроку (только для админа)")
    async def give_gems(self, interaction: discord.Interaction, target: discord.Member, amount: int):
        if not self.is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        user = await db.get_user(target.id, interaction.guild_id)
        user["gems"] += amount
        await db.update_user(target.id, interaction.guild_id, user)

        await interaction.response.send_message(f"Выдано **{amount} гемов** игроку {target.mention}")

    @app_commands.command(name="set_vip", description="Установить VIP-уровень игроку (только для админа)")
    async def set_vip(self, interaction: discord.Interaction, target: discord.Member, level: int):
        if not self.is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        if level < 0 or level > 4:
            await interaction.response.send_message("Уровень должен быть от 0 до 4.", ephemeral=True)
            return

        user = await db.get_user(target.id, interaction.guild_id)
        user["vip_level"] = level
        await db.update_user(target.id, interaction.guild_id, user)

        await interaction.response.send_message(f"Игроку {target.mention} установлен VIP-уровень **{level}**")

    @app_commands.command(name="reset_profile", description="Сбросить профиль игрока (только для админа)")
    async def reset_profile(self, interaction: discord.Interaction, target: discord.Member):
        if not self.is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        reset_payload = copy.deepcopy(db.NEW_USER_TEMPLATE)
        await db.update_user(target.id, interaction.guild_id, reset_payload)
        await db.sync_server_businesses(target.id, interaction.guild_id, {})
        await interaction.response.send_message(f"Профиль игрока {target.mention} сброшен")

    @app_commands.command(name="give_business", description="Выдать бизнес игроку по ID (только для админа)")
    async def give_business(self, interaction: discord.Interaction, target: discord.Member, business_id: int):
        if not self.is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        business = BUSINESSES.get(business_id)
        if business is None:
            await interaction.response.send_message("Некорректный ID бизнеса.", ephemeral=True)
            return

        user = await db.get_user(target.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Профиль игрока не найден.", ephemeral=True)
            return

        user, normalized_businesses, removed = await ensure_unique_businesses(
            target.id,
            interaction.guild_id,
            user=user,
            sync_table=False,
        )
        if not user:
            await interaction.response.send_message("Профиль игрока не найден.", ephemeral=True)
            return

        if normalized_businesses.get(str(business_id)):
            legacy_text = " Старые дубликаты были очищены автоматически." if removed > 0 else ""
            await interaction.response.send_message(
                f"У {target.mention} уже есть **{business['name']}**.{legacy_text}",
                ephemeral=True,
            )
            return

        now = datetime.now(timezone.utc).isoformat()
        normalized_businesses[str(business_id)] = [
            {
                "bought_at": now,
                "last_collect": now,
                "total_earned": 0,
            }
        ]
        await db.update_user(target.id, interaction.guild_id, {"businesses": normalized_businesses})
        await db.sync_server_businesses(target.id, interaction.guild_id, normalized_businesses)

        await interaction.response.send_message(
            f"Игроку {target.mention} выдан бизнес **{business['name']}** (`ID {business_id}`)"
        )

    @app_commands.command(name="clear_businesses", description="Удалить все бизнесы у игроков на этом сервере")
    async def clear_businesses(self, interaction: discord.Interaction):
        if not self.is_admin(interaction):
            await interaction.response.send_message("Нет доступа.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("users").select("user_id,businesses").eq("guild_id", interaction.guild_id).execute()
            )
        except Exception as exc:
            await interaction.edit_original_response(content=f"Не удалось очистить бизнесы: {exc}")
            return

        players_changed = 0
        removed_businesses = 0

        for row in result.data or []:
            user_id = row.get("user_id")
            if not user_id:
                continue

            businesses = row.get("businesses") or {}
            if not businesses:
                continue

            players_changed += 1
            removed_businesses += len(businesses)
            await db.update_user(int(user_id), interaction.guild_id, {"businesses": {}})
            await db.sync_server_businesses(int(user_id), interaction.guild_id, {})

        await interaction.edit_original_response(
            content=(
                "Очистка бизнесов завершена.\n"
                f"Игроков изменено: **{players_changed}**\n"
                f"Удалено бизнесов: **{removed_businesses}**"
            )
        )


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
