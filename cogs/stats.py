from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, DAILY_QUESTS_POOL, WEEKLY_QUESTS_POOL
from database import db
from utils import check_channel, format_discord_deadline, get_kyiv_timezone, send_wrong_channel_message

DAILY_QUEST_COUNT = 4
WEEKLY_QUEST_COUNT = 7
KYIV_TZ = get_kyiv_timezone()

GAME_LABELS = {
    "blackjack": "Блэкджек",
    "blackjack_pvp": "PvP-блэкджек",
    "roulette": "Рулетка",
    "slots": "Слоты",
    "dice": "Кости",
    "coinflip": "Монетка",
    "rps": "Камень-ножницы-бумага",
}


def parse_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def roll_quests(pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    selected = random.sample(pool, min(count, len(pool)))
    return [{**quest, "completed": False} for quest in selected]


def week_anchor(dt: datetime) -> datetime.date:
    return (dt - timedelta(days=dt.weekday())).date()


def format_game_label(game_name: str) -> str:
    return GAME_LABELS.get(game_name, game_name.replace("_", " ").title())


def format_quest_line(quest: dict[str, Any], progress: int) -> str:
    current = min(progress, int(quest["target"]))
    status = "✅" if quest.get("completed") else "🕒"
    return (
        f"{status} **{quest['name']}**\n"
        f"{quest['desc']}\n"
        f"Прогресс: `{current}/{quest['target']}` • Награда: `${quest['reward_money']:,}` + `{quest['reward_gems']} гем.`"
    )


class StatsCog(commands.Cog, name="Stats"):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_quest_rotation(self, user_id: int, guild_id: int, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        user = user or await db.get_user(user_id, guild_id)
        if not user:
            return None

        now_kyiv = datetime.now(KYIV_TZ)
        daily_reset = False
        weekly_reset = False

        last_daily_reset = parse_timestamp(user.get("last_daily_reset"))
        if not user.get("daily_quests") or last_daily_reset is None or last_daily_reset.astimezone(KYIV_TZ).date() != now_kyiv.date():
            user["daily_quests"] = roll_quests(DAILY_QUESTS_POOL, DAILY_QUEST_COUNT)
            user["last_daily_reset"] = now_kyiv.astimezone(timezone.utc).isoformat()
            daily_reset = True

        last_weekly_reset = parse_timestamp(user.get("last_weekly_reset"))
        if (
            not user.get("weekly_quests")
            or last_weekly_reset is None
            or week_anchor(last_weekly_reset.astimezone(KYIV_TZ)) != week_anchor(now_kyiv)
        ):
            user["weekly_quests"] = roll_quests(WEEKLY_QUESTS_POOL, WEEKLY_QUEST_COUNT)
            user["last_weekly_reset"] = now_kyiv.astimezone(timezone.utc).isoformat()
            weekly_reset = True

        old_progress = user.get("quest_progress") or {}
        new_progress: dict[str, int] = {}

        for quest in user.get("daily_quests", []):
            quest_id = quest["id"]
            new_progress[quest_id] = 0 if daily_reset else int(old_progress.get(quest_id, 0))
            quest["completed"] = False if daily_reset else bool(new_progress[quest_id] >= int(quest["target"]) or quest.get("completed"))

        for quest in user.get("weekly_quests", []):
            quest_id = quest["id"]
            new_progress[quest_id] = 0 if weekly_reset else int(old_progress.get(quest_id, 0))
            quest["completed"] = False if weekly_reset else bool(new_progress[quest_id] >= int(quest["target"]) or quest.get("completed"))

        user["quest_progress"] = new_progress
        if daily_reset or weekly_reset or new_progress != old_progress:
            await db.update_user(user_id, guild_id, user)
            user = await db.get_user(user_id, guild_id)
        return user

    @app_commands.command(name="top", description="Показать топ игроков по капиталу")
    async def top(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        entries = await db.get_top_net_worth(limit=15)
        if not entries:
            await interaction.response.send_message("Топ пока пуст.", ephemeral=True)
            return

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for entry in entries:
            rank = int(entry.get("rank", 0) or 0)
            badge = medals.get(rank, f"`#{rank}`")
            username = str(entry.get("username") or f"User {entry.get('user_id')}")
            net_worth = int(entry.get("net_worth", 0) or 0)
            lines.append(
                f"{badge} **{username}**\n"
                f"Капитал: **${net_worth:,}**\n"
                f"Ликвидка: **${int(entry.get('balance_value', 0) or 0):,}** • "
                f"Дом: **${int(entry.get('house_value', 0) or 0):,}** • "
                f"Подвал/GPU: **${int(entry.get('basement_value', 0) or 0) + int(entry.get('gpu_value', 0) or 0):,}** • "
                f"Бизнесы: **${int(entry.get('business_value', 0) or 0) + int(entry.get('business_upgrade_value', 0) or 0):,}**"
            )

        embed = discord.Embed(
            title="Топ капитала",
            description=(
                "Рейтинг считается вживую по капиталу игрока.\n"
                "**Баланс + банк + депозит + дом + апгрейды подвала + GPU + бизнесы + апгрейды бизнесов + мебель**\n\n"
                + "\n\n".join(lines)
            ),
            color=COLORS["gold"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Крипта, рыба, сундуки и обычный лут в рейтинг не входят.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="stats", description="Посмотреть подробную статистику")
    async def stats(self, interaction: discord.Interaction, player: discord.Member | None = None):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        target = player or interaction.user
        user = await db.get_user(target.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Профиль не найден.", ephemeral=True)
            return

        game_stats = user.get("game_stats", {})
        net_profit = int(user.get("total_won", 0) or 0) - int(user.get("total_lost", 0) or 0)
        profit_emoji = "📈" if net_profit >= 0 else "📉"

        embed = discord.Embed(
            title=f"Статистика • {target.display_name}",
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="Финансы",
            value=(
                f"Баланс: **${int(user.get('balance', 0) or 0):,}**\n"
                f"Банк: **${int(user.get('bank', 0) or 0):,}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**\n"
                f"Уровень: **{int(user.get('level', 1) or 1)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Игры",
            value=(
                f"Сыграно: **{int(user.get('games_played', 0) or 0)}**\n"
                f"Выиграно: **${int(user.get('total_won', 0) or 0):,}**\n"
                f"Проиграно: **${int(user.get('total_lost', 0) or 0):,}**\n"
                f"{profit_emoji} Итог: **${net_profit:,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Серии",
            value=(
                f"Текущая: **{int(user.get('win_streak', 0) or 0)}**\n"
                f"Лучшая: **{int(user.get('best_streak', 0) or 0)}**"
            ),
            inline=True,
        )

        if isinstance(game_stats, dict):
            lines = []
            valid_games = [
                (game_name, stats_data)
                for game_name, stats_data in game_stats.items()
                if not str(game_name).startswith("_") and isinstance(stats_data, dict) and int(stats_data.get("played", 0) or 0) > 0
            ]
            sorted_games = sorted(valid_games, key=lambda item: int(item[1].get("played", 0) or 0), reverse=True)[:6]
            for game_name, stats_data in sorted_games:
                played = int(stats_data.get("played", 0) or 0)
                won = int(stats_data.get("won", 0) or 0)
                winrate = (won / played * 100) if played > 0 else 0
                lines.append(f"• **{format_game_label(game_name)}** • {played} игр, винрейт {winrate:.0f}%")
            if lines:
                embed.add_field(name="Любимые режимы", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="quest", description="Посмотреть ежедневные и недельные квесты")
    async def quest(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await self.ensure_quest_rotation(interaction.user.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Профиль не найден.", ephemeral=True)
            return

        progress = user.get("quest_progress", {})
        now_kyiv = datetime.now(KYIV_TZ)
        next_daily_reset = datetime.combine(now_kyiv.date() + timedelta(days=1), datetime.min.time(), tzinfo=KYIV_TZ)
        next_weekly_reset = datetime.combine(week_anchor(now_kyiv) + timedelta(days=7), datetime.min.time(), tzinfo=KYIV_TZ)

        daily_lines = [format_quest_line(quest, int(progress.get(quest["id"], 0) or 0)) for quest in user.get("daily_quests", [])]
        weekly_lines = [format_quest_line(quest, int(progress.get(quest["id"], 0) or 0)) for quest in user.get("weekly_quests", [])]

        embed = discord.Embed(
            title="Квесты",
            description=(
                f"Ежедневный сброс: {format_discord_deadline(next_daily_reset)}\n"
                f"Недельный сброс: {format_discord_deadline(next_weekly_reset)}"
            ),
            color=COLORS["purple"],
        )
        embed.add_field(name="Ежедневные", value="\n\n".join(daily_lines) if daily_lines else "Пока нет квестов.", inline=False)
        embed.add_field(name="Недельные", value="\n\n".join(weekly_lines) if weekly_lines else "Пока нет квестов.", inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
