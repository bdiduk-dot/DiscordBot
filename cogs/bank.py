from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS
from database import db, get_user_lock
from utils import check_channel, format_discord_deadline, send_wrong_channel_message


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


class BankCog(commands.Cog, name="Bank"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bank", description="Посмотреть банковский счёт")
    async def bank(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if not user:
            return

        bank_balance = int(user.get("bank", 0) or 0)
        deposit_amount = int(user.get("deposit_amount", 0) or 0)
        deposit_rate = float(user.get("deposit_rate", 0) or 0)
        deposit_days = int(user.get("deposit_days", 0) or 0)

        deposit_info = ""
        if deposit_amount > 0 and user.get("deposit_start"):
            deposit_start = datetime.fromisoformat(user["deposit_start"]).replace(tzinfo=timezone.utc)
            days_passed = (datetime.now(timezone.utc) - deposit_start).days
            days_left = deposit_days - days_passed
            expected_return = int(deposit_amount * (1 + deposit_rate))
            deposit_matures_at = deposit_start + timedelta(days=deposit_days)

            if days_left <= 0:
                deposit_info = (
                    "\n📈 **АКТИВНЫЙ ВКЛАД**\n"
                    f"💰 Сумма: `{format_money(deposit_amount)}`\n"
                    f"📊 Ставка: `{deposit_rate * 100:.1f}%`\n"
                    f"⏰ Срок: `{deposit_days} дн.`\n"
                    f"✅ **Созрел**\n"
                    f"💎 Возврат: `{format_money(expected_return)}`\n"
                    f"🎁 Прибыль: `{format_money(expected_return - deposit_amount)}`\n"
                    "Используй `/withdraw_deposit`, чтобы забрать."
                )
            else:
                progress_done = max(0, days_passed)
                progress_left = max(0, days_left)
                deposit_info = (
                    "\n📈 **АКТИВНЫЙ ВКЛАД**\n"
                    f"💰 Сумма: `{format_money(deposit_amount)}`\n"
                    f"📊 Ставка: `{deposit_rate * 100:.1f}%`\n"
                    f"⏰ Созреет: {format_discord_deadline(deposit_matures_at)}\n"
                    f"📉 Прогресс: {'■' * progress_done}{'□' * progress_left}\n"
                    f"💎 Ожидаемо: `{format_money(expected_return)}`\n"
                    f"🎁 Прибыль: `{format_money(expected_return - deposit_amount)}`"
                )

        total_wealth = int(user.get("balance", 0) or 0) + bank_balance + deposit_amount
        embed = discord.Embed(
            title="🏦 БАНКОВСКИЙ СЧЁТ",
            description=(
                f"👤 **{interaction.user.display_name}**\n\n"
                f"💵 Наличные: `{format_money(user.get('balance', 0))}`\n"
                f"🏦 Банк: `{format_money(bank_balance)}`\n"
                f"📈 Вклад: `{format_money(deposit_amount)}`\n"
                f"💎 Общее состояние: `{format_money(total_wealth)}`\n"
                f"{deposit_info}"
            ),
            color=COLORS["info"],
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bankdep", description="Положить деньги на банковский счёт")
    async def bankdep(self, interaction: discord.Interaction, amount: int):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                return
            if amount <= 0 or int(user.get("balance", 0) or 0) < amount:
                await interaction.response.send_message("Некорректная сумма или не хватает денег.", ephemeral=True)
                return

            user["balance"] = int(user.get("balance", 0) or 0) - amount
            user["bank"] = int(user.get("bank", 0) or 0) + amount
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        embed = discord.Embed(
            title="🏦 Пополнение банка",
            description=(
                f"Внесено: `{format_money(amount)}`\n"
                f"Наличные: `{format_money(user['balance'])}`\n"
                f"Банк: `{format_money(user['bank'])}`"
            ),
            color=COLORS["success"],
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="bankwith", description="Снять деньги с банковского счёта")
    async def bankwith(self, interaction: discord.Interaction, amount: int):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                return
            if amount <= 0 or int(user.get("bank", 0) or 0) < amount:
                await interaction.response.send_message("Некорректная сумма или не хватает денег в банке.", ephemeral=True)
                return

            user["balance"] = int(user.get("balance", 0) or 0) + amount
            user["bank"] = int(user.get("bank", 0) or 0) - amount
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        embed = discord.Embed(
            title="🏦 Снятие с банка",
            description=(
                f"Снято: `{format_money(amount)}`\n"
                f"Наличные: `{format_money(user['balance'])}`\n"
                f"Банк: `{format_money(user['bank'])}`"
            ),
            color=COLORS["success"],
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="deposit", description="Открыть вклад в банке под проценты")
    async def deposit(self, interaction: discord.Interaction, amount: int, days: int):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                return
            if int(user.get("deposit_amount", 0) or 0) > 0:
                await interaction.response.send_message("У тебя уже есть активный вклад.", ephemeral=True)
                return
            if amount <= 0 or int(user.get("bank", 0) or 0) < amount:
                await interaction.response.send_message("Некорректная сумма вклада.", ephemeral=True)
                return

            rates = {7: 0.05, 14: 0.12, 30: 0.30}
            if days not in rates:
                await interaction.response.send_message("Выбери срок: 7, 14 или 30 дней.", ephemeral=True)
                return

            rate = rates[days]
            vip_bonus = {1: 0.02, 2: 0.05, 3: 0.10, 4: 0.20}.get(int(user.get("vip_level", 0) or 0), 0)
            final_rate = rate + vip_bonus

            user["bank"] = int(user.get("bank", 0) or 0) - amount
            user["deposit_amount"] = amount
            user["deposit_rate"] = final_rate
            user["deposit_start"] = datetime.now(timezone.utc).isoformat()
            user["deposit_days"] = days
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        expected_return = int(amount * (1 + final_rate))
        embed = discord.Embed(
            title="📈 Вклад открыт",
            description=(
                f"Сумма: `{format_money(amount)}`\n"
                f"Ставка: `{rate * 100:.1f}%` (+`{vip_bonus * 100:.0f}%` VIP)\n"
                f"Срок: `{days} дн.`\n"
                f"Ожидаемый возврат: `{format_money(expected_return)}`"
            ),
            color=COLORS["gold"],
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="withdraw_deposit", description="Забрать вклад")
    async def withdraw_deposit(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user or int(user.get("deposit_amount", 0) or 0) == 0:
                await interaction.response.send_message("У тебя нет активного вклада.", ephemeral=True)
                return

            dep = int(user["deposit_amount"])
            rate = float(user["deposit_rate"])
            days = int(user["deposit_days"])
            start_at = datetime.fromisoformat(user["deposit_start"]).replace(tzinfo=timezone.utc)
            days_left = days - (datetime.now(timezone.utc) - start_at).days

            if days_left <= 0:
                profit = int(dep * rate)
                user["bank"] = int(user.get("bank", 0) or 0) + dep + profit
                color = COLORS["success"]
                msg = (
                    "Вклад созрел!\n"
                    f"💰 Тело: `{format_money(dep)}`\n"
                    f"🎁 Прибыль: `+{format_money(profit)}`\n"
                    f"🏦 Банк: `{format_money(user['bank'])}`"
                )
            else:
                profit = int(dep * rate)
                penalty = profit // 2
                actual_profit = profit - penalty
                user["bank"] = int(user.get("bank", 0) or 0) + dep + actual_profit
                color = COLORS["warning"]
                msg = (
                    "Вклад снят досрочно.\n"
                    f"💰 Тело: `{format_money(dep)}`\n"
                    f"⚠ Штраф: `-{format_money(penalty)}`\n"
                    f"🏦 Банк: `{format_money(user['bank'])}`"
                )

            user["deposit_amount"], user["deposit_rate"], user["deposit_start"], user["deposit_days"] = 0, 0, None, 0
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        await interaction.response.send_message(
            embed=discord.Embed(title="📈 Вклад закрыт", description=msg, color=color)
        )

    @app_commands.command(name="transfer", description="Перевести деньги другому игроку")
    async def transfer(self, interaction: discord.Interaction, recipient: discord.Member, amount: int):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if recipient.bot or recipient.id == interaction.user.id or amount <= 0:
            await interaction.response.send_message("Некорректный перевод.", ephemeral=True)
            return

        u1, u2 = sorted([interaction.user.id, recipient.id])
        async with get_user_lock(u1):
            async with get_user_lock(u2):
                sender = await db.get_user(interaction.user.id, interaction.guild_id)
                if int(sender.get("balance", 0) or 0) < amount:
                    await interaction.response.send_message(
                        f"Не хватает денег. Баланс: {format_money(sender.get('balance', 0))}",
                        ephemeral=True,
                    )
                    return
                receiver = await db.get_user(recipient.id, interaction.guild_id)
                sender["balance"] = int(sender.get("balance", 0) or 0) - amount
                receiver["balance"] = int(receiver.get("balance", 0) or 0) + amount
                await db.update_user(interaction.user.id, interaction.guild_id, sender)
                await db.update_user(recipient.id, interaction.guild_id, receiver)

        embed = discord.Embed(
            title="💸 Перевод выполнен",
            description=(
                f"От: {interaction.user.mention}\n"
                f"Кому: {recipient.mention}\n"
                f"Сумма: `{format_money(amount)}`"
            ),
            color=COLORS["success"],
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(BankCog(bot))
