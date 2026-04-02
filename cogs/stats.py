import math
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, DAILY_QUESTS_POOL, WEEKLY_QUESTS_POOL
from database import db
from utils import check_channel, format_discord_deadline, get_kyiv_timezone, send_wrong_channel_message

ITEMS_PER_PAGE = 10
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

LEADERBOARD_METRICS = {
    "money": ("💵 Деньги", "Баланс"),
    "gems": ("💎 Гемы", "Гемы"),
    "businesses": ("🏢 Бизнесы", "Бизнесы"),
    "games": ("🎮 Игры", "Победы"),
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


def roll_quests(pool: list[dict], count: int) -> list[dict]:
    selected = random.sample(pool, min(count, len(pool)))
    return [{**quest, "completed": False} for quest in selected]


def week_anchor(dt: datetime) -> datetime.date:
    return (dt - timedelta(days=dt.weekday())).date()


def format_game_label(game_name: str) -> str:
    return GAME_LABELS.get(game_name, game_name.replace("_", " ").title())


def format_quest_line(quest: dict, progress: int) -> str:
    current = min(progress, int(quest["target"]))
    status = "✅" if quest.get("completed") else "🕒"
    return (
        f"{status} **{quest['name']}**\n"
        f"{quest['desc']}\n"
        f"Прогресс: `{current}/{quest['target']}` • Награда: `${quest['reward_money']:,}` + `{quest['reward_gems']} гем.`"
    )


class LeaderboardView(discord.ui.View):
    def __init__(self, entries: list[dict], owner_id: int, metric: str, scope: str = "all"):
        super().__init__(timeout=180)
        self.entries = entries
        self.owner_id = owner_id
        self.metric = metric
        self.scope = scope
        self.page = 0
        self.max_page = max(0, math.ceil(len(entries) / ITEMS_PER_PAGE) - 1)
        self._sync_buttons()

    def _metric_value(self, entry: dict) -> str:
        if self.scope == "weekly":
            if self.metric == "gems":
                return f"💎 **{int(entry.get('weekly_gems', 0) or 0):,}**"
            if self.metric == "businesses":
                return f"🏢 **{int(entry.get('weekly_businesses', 0) or 0)}**"
            if self.metric == "games":
                wins = int(entry.get("weekly_wins", 0) or 0)
                played = int(entry.get("weekly_games", 0) or 0)
                return f"🎯 **{wins}** побед • 🎮 **{played}** игр"
            return f"💵 **${int(entry.get('weekly_money', 0) or 0):,}**"

        if self.metric == "gems":
            return f"💎 **{int(entry.get('gems_balance', 0) or 0):,}**"
        if self.metric == "businesses":
            return f"🏢 **{int(entry.get('businesses_owned', 0) or 0)}**"
        if self.metric == "games":
            wins = int(entry.get("total_wins", 0) or 0)
            played = int(entry.get("total_games_played", 0) or 0)
            return f"🎯 **{wins}** побед • 🎮 **{played}** игр"
        return f"💵 **${int(entry.get('total_balance', 0) or 0):,}**"

    def _sync_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.max_page
        self.page_btn.label = f"{self.page + 1}/{self.max_page + 1}"
        self.money_btn.style = discord.ButtonStyle.primary if self.metric == "money" else discord.ButtonStyle.secondary
        self.gems_btn.style = discord.ButtonStyle.primary if self.metric == "gems" else discord.ButtonStyle.secondary
        self.businesses_btn.style = discord.ButtonStyle.primary if self.metric == "businesses" else discord.ButtonStyle.secondary
        self.games_btn.style = discord.ButtonStyle.primary if self.metric == "games" else discord.ButtonStyle.secondary
        self.all_time_btn.style = discord.ButtonStyle.primary if self.scope == "all" else discord.ButtonStyle.secondary
        self.week_btn.style = discord.ButtonStyle.primary if self.scope == "weekly" else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Это меню лидерборда открыто не тобой.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        start = self.page * ITEMS_PER_PAGE
        page_entries = self.entries[start:start + ITEMS_PER_PAGE]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        metric_title, metric_label = LEADERBOARD_METRICS[self.metric]
        scope_label = "За неделю" if self.scope == "weekly" else "Общий"

        embed = discord.Embed(
            title=f"🏆 Глобальный лидерборд • {metric_title}",
            description=(
                f"Режим: **{scope_label}**\n"
                f"Страница **{self.page + 1}/{self.max_page + 1}** • Игроков: **{len(self.entries)}**"
            ),
            color=COLORS["gold"],
        )

        for entry in page_entries:
            rank = int(entry.get("rank", 0) or 0)
            username = str(entry.get("username") or f"User {entry.get('user_id')}")
            vip_level = int(entry.get("vip_level", 0) or 0)
            vip_badge = f"VIP {vip_level}" if vip_level > 0 else "Без VIP"
            rank_badge = medals.get(rank, f"#{rank}")

            if self.scope == "weekly":
                value = (
                    f"{metric_label}: {self._metric_value(entry)}\n"
                    f"💵 За неделю: **${int(entry.get('weekly_money', 0) or 0):,}**\n"
                    f"💎 За неделю: **{int(entry.get('weekly_gems', 0) or 0):,}**\n"
                    f"🎮 Игры: **{int(entry.get('weekly_games', 0) or 0)}** • Победы: **{int(entry.get('weekly_wins', 0) or 0)}**\n"
                    f"🏢 Бизнес-циклы: **{int(entry.get('weekly_businesses', 0) or 0)}**\n"
                    f"👑 {vip_badge}"
                )
            else:
                value = (
                    f"{metric_label}: {self._metric_value(entry)}\n"
                    f"💵 Баланс: **${int(entry.get('total_balance', 0) or 0):,}**\n"
                    f"💎 Гемы: **{int(entry.get('gems_balance', 0) or 0):,}**\n"
                    f"🎮 Игр: **{int(entry.get('total_games_played', 0) or 0)}** • Побед: **{int(entry.get('total_wins', 0) or 0)}**\n"
                    f"👑 {vip_badge}"
                )

            embed.add_field(name=f"{rank_badge} {username}", value=value, inline=False)

        return embed

    async def _reload(self, interaction: discord.Interaction):
        self.entries = await db.get_leaderboard(metric=self.metric, limit=100, scope=self.scope)
        self.page = 0
        self.max_page = max(0, math.ceil(len(self.entries) / ITEMS_PER_PAGE) - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _switch_metric(self, interaction: discord.Interaction, metric: str):
        self.metric = metric
        await self._reload(interaction)

    async def _switch_scope(self, interaction: discord.Interaction, scope: str):
        self.scope = scope
        await self._reload(interaction)

    @discord.ui.button(label="Деньги", style=discord.ButtonStyle.primary, row=0)
    async def money_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_metric(interaction, "money")

    @discord.ui.button(label="Гемы", style=discord.ButtonStyle.secondary, row=0)
    async def gems_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_metric(interaction, "gems")

    @discord.ui.button(label="Бизнесы", style=discord.ButtonStyle.secondary, row=0)
    async def businesses_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_metric(interaction, "businesses")

    @discord.ui.button(label="Игры", style=discord.ButtonStyle.secondary, row=0)
    async def games_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_metric(interaction, "games")

    @discord.ui.button(label="Общий", style=discord.ButtonStyle.primary, row=1)
    async def all_time_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_scope(interaction, "all")

    @discord.ui.button(label="Неделя", style=discord.ButtonStyle.secondary, row=1)
    async def week_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_scope(interaction, "weekly")

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, row=2)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=2)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="Дальше", style=discord.ButtonStyle.secondary, row=2)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.max_page, self.page + 1)
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class StatsCog(commands.Cog, name="Stats"):
    def __init__(self, bot):
        self.bot = bot

    async def ensure_quest_rotation(self, user_id: int, guild_id: int, user: dict | None = None) -> dict | None:
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

    @app_commands.command(name="leaderboard", description="Посмотреть глобальный лидерборд")
    async def leaderboard(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        await interaction.response.defer()
        await db.sync_global_leaderboard(interaction.user.id, username=interaction.user.display_name)
        entries = await db.get_leaderboard(metric="money", limit=100, scope="all")
        if not entries:
            await db.sync_all_global_leaderboard()
            entries = await db.get_leaderboard(metric="money", limit=100, scope="all")
            if not entries:
                await interaction.edit_original_response(content="Лидерборд пока пуст.")
                return

        view = LeaderboardView(entries, interaction.user.id, "money", scope="all")
        await interaction.edit_original_response(embed=view.build_embed(), view=view)

    @app_commands.command(name="stats", description="Посмотреть подробную статистику")
    async def stats(self, interaction: discord.Interaction, player: discord.Member = None):
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
        streak = int(user.get("win_streak", 0) or 0)
        best_streak = int(user.get("best_streak", 0) or 0)

        embed = discord.Embed(
            title=f"📊 Статистика • {target.display_name}",
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="💵 Финансы",
            value=(
                f"Баланс: **${int(user.get('balance', 0) or 0):,}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**\n"
                f"Уровень: **{int(user.get('level', 1) or 1)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎮 Игры",
            value=(
                f"Сыграно: **{int(user.get('games_played', 0) or 0)}**\n"
                f"Выиграно: **${int(user.get('total_won', 0) or 0):,}**\n"
                f"Проиграно: **${int(user.get('total_lost', 0) or 0):,}**\n"
                f"{profit_emoji} Итог: **${net_profit:,}**\n"
                f"Поставлено: **${int(user.get('total_wagered', 0) or 0):,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🔥 Серии",
            value=f"Текущая: **{streak}**\nЛучшая: **{best_streak}**",
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
                embed.add_field(name="🃏 Любимые режимы", value="\n".join(lines), inline=False)

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
            title="🎯 Квесты",
            description=(
                f"Ежедневный сброс: {format_discord_deadline(next_daily_reset)}\n"
                f"Недельный сброс: {format_discord_deadline(next_weekly_reset)}"
            ),
            color=COLORS["purple"],
        )
        embed.add_field(name="Ежедневные", value="\n\n".join(daily_lines) if daily_lines else "Список пока пуст.", inline=False)
        embed.add_field(name="Недельные", value="\n\n".join(weekly_lines) if weekly_lines else "Список пока пуст.", inline=False)
        embed.set_footer(text="Квесты обновляются автоматически в 00:00 по Киеву.")
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
