import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS
from database import db
from game_logic import games
from utils import add_xp, check_channel, create_embed, send_wrong_channel_message, update_game_stats

from cogs.views import BlackjackGame, BlackjackPvpInviteView, BlackjackView


class GamesCoreCog(commands.Cog, name="GamesCore"):
    def __init__(self, bot):
        self.bot = bot

    async def _progress_contracts(self, user_id: int, guild_id: int, code: str, amount: int = 1):
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is not None:
            await systems_cog.progress_contracts(user_id, guild_id, code, amount)

    def _parse_blackjack_bet(self, balance: int, bet_input: str | int) -> tuple[int | None, str | None]:
        raw_value = str(bet_input).strip().lower().replace(",", "")
        if raw_value in {"all", "max", "все", "всё"}:
            bet = int(balance)
        else:
            try:
                bet = int(raw_value)
            except ValueError:
                return None, "Используй число или `всё`."

        if bet <= 0:
            return None, "Ставка должна быть больше нуля."
        if balance < bet:
            return None, f"Недостаточно денег. Баланс: `${balance:,}`"
        return bet, None

    async def _start_blackjack(self, interaction: discord.Interaction, bet_input: str | int):
        if not await check_channel(interaction):
            return await send_wrong_channel_message(interaction)

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if not user:
            return await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)

        bet, error = self._parse_blackjack_bet(int(user.get("balance", 0) or 0), bet_input)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)

        user["balance"] = int(user.get("balance", 0) or 0) - bet
        await db.update_user(interaction.user.id, interaction.guild_id, user)

        game = BlackjackGame(interaction.user.id, interaction.guild_id, bet)
        view = BlackjackView(game)
        await interaction.response.send_message(embed=game.get_game_embed(), view=view)
        view.message = await interaction.original_response()
        asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "play", 1))

    async def _start_blackjack_pvp(self, interaction: discord.Interaction, opponent: discord.Member, bet_input: str | int):
        if not await check_channel(interaction):
            return await send_wrong_channel_message(interaction)

        if opponent.bot or opponent.id == interaction.user.id:
            return await interaction.response.send_message("Выбери другого реального игрока.", ephemeral=True)

        challenger_user = await db.get_user(interaction.user.id, interaction.guild_id)
        opponent_user = await db.get_user(opponent.id, interaction.guild_id)
        if not challenger_user or not opponent_user:
            return await interaction.response.send_message("Не удалось загрузить профили игроков.", ephemeral=True)

        bet, error = self._parse_blackjack_bet(int(challenger_user.get("balance", 0) or 0), bet_input)
        if error:
            return await interaction.response.send_message(error, ephemeral=True)

        if int(opponent_user.get("balance", 0) or 0) < bet:
            return await interaction.response.send_message(
                f"У игрока {opponent.mention} недостаточно денег для ставки **${bet:,}**.",
                ephemeral=True,
            )

        embed = discord.Embed(
            title="🃏 ВЫЗОВ НА МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
            description=(
                f"Игрок 1: {interaction.user.mention}\n"
                f"Игрок 2: {opponent.mention}\n"
                f"Ставка с каждого: **${bet:,}**\n"
                f"Общий банк: **${bet * 2:,}**\n\n"
                f"{opponent.mention}, прими вызов кнопкой ниже."
            ),
            color=COLORS["gold"],
        )
        embed.set_footer(text="После принятия ставки списываются у обоих игроков.")

        view = BlackjackPvpInviteView(interaction.user, opponent, interaction.guild_id, bet)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
        asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "play", 1))

    @app_commands.command(name="blackjack", description="Сыграть в блэкджек")
    @app_commands.describe(
        bet="Ставка числом или всё",
        multiplayer="Включить мультиплеер-режим",
        opponent="Игрок для мультиплеера",
    )
    async def blackjack(
        self,
        interaction: discord.Interaction,
        bet: str,
        multiplayer: bool = False,
        opponent: discord.Member | None = None,
    ):
        if multiplayer or opponent is not None:
            if opponent is None:
                await interaction.response.send_message(
                    "Для мультиплеера укажи игрока в параметре `opponent`.",
                    ephemeral=True,
                )
                return
            await self._start_blackjack_pvp(interaction, opponent, bet)
            return
        await self._start_blackjack(interaction, bet)

    @app_commands.command(name="bj", description="Короткая команда для блэкджека")
    @app_commands.describe(
        bet="Ставка числом или всё",
        multiplayer="Включить мультиплеер-режим",
        opponent="Игрок для мультиплеера",
    )
    async def bj(
        self,
        interaction: discord.Interaction,
        bet: str,
        multiplayer: bool = False,
        opponent: discord.Member | None = None,
    ):
        if multiplayer or opponent is not None:
            if opponent is None:
                await interaction.response.send_message(
                    "Для мультиплеера укажи игрока в параметре `opponent`.",
                    ephemeral=True,
                )
                return
            await self._start_blackjack_pvp(interaction, opponent, bet)
            return
        await self._start_blackjack(interaction, bet)

    @app_commands.command(name="roulette", description="Сыграть в рулетку")
    async def roulette(self, interaction: discord.Interaction, bet: int, bet_type: str, value: str = None):
        if not await check_channel(interaction):
            return await send_wrong_channel_message(interaction)
        if bet <= 0:
            return await interaction.response.send_message("Ставка должна быть больше нуля.", ephemeral=True)

        valid_types = ["number", "color", "even", "odd", "low", "high"]
        if bet_type not in valid_types:
            return await interaction.response.send_message(
                f"Неверный тип ставки. Доступно: {', '.join(valid_types)}",
                ephemeral=True,
            )

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if int(user.get("balance", 0) or 0) < bet:
            return await interaction.response.send_message(
                f"Недостаточно денег. Баланс: `${int(user.get('balance', 0) or 0):,}`",
                ephemeral=True,
            )

        result, multiplier, description = games.roulette(bet, bet_type, value)
        user["games_played"] = int(user.get("games_played", 0) or 0) + 1
        won = result == "win"
        tracked_money = 0
        xp_gain = 20 if won else 0

        if won:
            winnings = bet * multiplier
            tracked_money = winnings
            user["balance"] = int(user.get("balance", 0) or 0) + winnings
            user["total_won"] = int(user.get("total_won", 0) or 0) + winnings
            color = COLORS["success"]
        else:
            user["balance"] = int(user.get("balance", 0) or 0) - bet
            user["total_lost"] = int(user.get("total_lost", 0) or 0) + bet
            color = COLORS["error"]

        await db.update_user(interaction.user.id, interaction.guild_id, user)
        if xp_gain:
            level_msg = await add_xp(interaction.user.id, interaction.guild_id, xp_gain)
            if level_msg:
                description += level_msg
        await update_game_stats(interaction.user.id, interaction.guild_id, "roulette", won, bet, money_earned=tracked_money)
        asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "play", 1))

        description += f"\n\n💵 Баланс: `${int(user.get('balance', 0) or 0):,}`"
        embed = create_embed("🎰 Рулетка", description, color)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="slots", description="Сыграть в слоты")
    async def slots(self, interaction: discord.Interaction, bet: int):
        if not await check_channel(interaction):
            return await send_wrong_channel_message(interaction)
        if bet <= 0:
            return await interaction.response.send_message("Ставка должна быть больше нуля.", ephemeral=True)

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if int(user.get("balance", 0) or 0) < bet:
            return await interaction.response.send_message(
                f"Недостаточно денег. Баланс: `${int(user.get('balance', 0) or 0):,}`",
                ephemeral=True,
            )

        embed = discord.Embed(title="🎰 СЛОТЫ", color=COLORS["info"])
        embed.add_field(name="Ставка", value=f"**${bet:,}**", inline=True)
        embed.add_field(name="Барабаны", value="**[ SLOT | SLOT | SLOT ]**\nКрутятся...", inline=False)
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        symbols = ["Вишня", "Лимон", "Колокол", "Алмаз", "Гем", "Семёрка", "Монета"]
        for _ in range(3):
            await asyncio.sleep(0.7)
            random_reels = [random.choice(symbols) for _ in range(3)]
            embed.clear_fields()
            embed.add_field(name="Ставка", value=f"**${bet:,}**", inline=True)
            embed.add_field(
                name="Барабаны",
                value=f"**[ {random_reels[0]} | {random_reels[1]} | {random_reels[2]} ]**\nКрутятся...",
                inline=False,
            )
            try:
                await message.edit(embed=embed)
            except Exception:
                pass

        result, multiplier, description = games.slots(bet)
        user["games_played"] = int(user.get("games_played", 0) or 0) + 1
        won = result in ["win", "jackpot"]
        tracked_money = 0
        xp_gain = 50 if result == "jackpot" else 15 if won else 0

        if won:
            winnings = bet * multiplier
            tracked_money = winnings
            user["balance"] = int(user.get("balance", 0) or 0) + winnings
            user["total_won"] = int(user.get("total_won", 0) or 0) + winnings
            color = COLORS["gold"] if result == "jackpot" else COLORS["success"]
        else:
            user["balance"] = int(user.get("balance", 0) or 0) - bet
            user["total_lost"] = int(user.get("total_lost", 0) or 0) + bet
            color = COLORS["error"]

        await db.update_user(interaction.user.id, interaction.guild_id, user)
        if xp_gain:
            level_msg = await add_xp(interaction.user.id, interaction.guild_id, xp_gain)
            if level_msg:
                description += level_msg
        await update_game_stats(interaction.user.id, interaction.guild_id, "slots", won, bet, money_earned=tracked_money)
        asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "play", 1))

        description += f"\n\n💵 Баланс: `${int(user.get('balance', 0) or 0):,}`"
        final_embed = create_embed("🎰 Слоты", description, color)
        await message.edit(embed=final_embed)

    @app_commands.command(name="dice", description="Сыграть в кости")
    async def dice(self, interaction: discord.Interaction, bet: int, prediction: int):
        if not await check_channel(interaction):
            return await send_wrong_channel_message(interaction)
        if bet <= 0:
            return await interaction.response.send_message("Ставка должна быть больше нуля.", ephemeral=True)
        if prediction < 2 or prediction > 12:
            return await interaction.response.send_message("Прогноз должен быть от 2 до 12.", ephemeral=True)

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if int(user.get("balance", 0) or 0) < bet:
            return await interaction.response.send_message(
                f"Недостаточно денег. Баланс: `${int(user.get('balance', 0) or 0):,}`",
                ephemeral=True,
            )

        result, multiplier, description = games.dice(bet, prediction)
        user["games_played"] = int(user.get("games_played", 0) or 0) + 1
        won = result == "win"
        tracked_money = 0
        xp_gain = 50 if multiplier == 10 and won else 15 if won else 0

        if won:
            winnings = bet * multiplier
            tracked_money = winnings
            user["balance"] = int(user.get("balance", 0) or 0) + winnings
            user["total_won"] = int(user.get("total_won", 0) or 0) + winnings
            color = COLORS["success"]
        else:
            user["balance"] = int(user.get("balance", 0) or 0) - bet
            user["total_lost"] = int(user.get("total_lost", 0) or 0) + bet
            color = COLORS["error"]

        await db.update_user(interaction.user.id, interaction.guild_id, user)
        if xp_gain:
            level_msg = await add_xp(interaction.user.id, interaction.guild_id, xp_gain)
            if level_msg:
                description += level_msg
        await update_game_stats(interaction.user.id, interaction.guild_id, "dice", won, bet, money_earned=tracked_money)
        asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "play", 1))

        description += f"\n\n💵 Баланс: `${int(user.get('balance', 0) or 0):,}`"
        embed = create_embed("🎲 Кости", description, color)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(GamesCoreCog(bot))
