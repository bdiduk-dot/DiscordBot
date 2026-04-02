import asyncio
import random
import re
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import ADMIN_IDS, BUSINESSES, COLORS, get_rank, get_vip_level
from database import db, get_user_lock
from progression import (
    PROFILE_TITLES,
    SEASON_NAME,
    battle_pass_progress_to_next,
    battle_pass_tier,
    ensure_battle_pass_state,
    get_profile_state,
    get_profile_theme_color,
    get_profile_title_text,
    get_reputation,
    reputation_crime_bonus,
    reputation_label,
    set_active_title,
    set_favorite_catch,
)
from utils import (
    check_channel,
    check_quest_progress,
    create_embed,
    ensure_unique_businesses,
    format_discord_deadline,
    has_active_shield,
    record_player_progress,
    safe_defer,
    send_wrong_channel_message,
)

RANK_NAMES = {
    "Bronze": "Бронза",
    "Silver": "Серебро",
    "Gold": "Золото",
    "Platinum": "Платина",
    "Diamond": "Алмаз",
    "Master": "Мастер",
}

VIP_NAMES = {
    "None": "Без VIP",
    "Bronze VIP": "Бронзовый VIP",
    "Silver VIP": "Серебряный VIP",
    "Gold VIP": "Золотой VIP",
    "Diamond VIP": "Алмазный VIP",
}


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def clean_business_name(business: dict) -> str:
    raw_name = str(business.get("name", "Business"))
    ascii_name = re.sub(r"\s+", " ", raw_name.encode("ascii", "ignore").decode()).strip(" -")
    return ascii_name or raw_name


class ProfileView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, target_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self.customize_btn.disabled = user_id != target_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню профиля открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def refresh_message(self):
        if self.message is None:
            return
        member = self.message.guild.get_member(self.target_id) if self.message.guild else None
        if member is None:
            return
        embed = await self.cog.build_profile_embed(member, self.guild_id)
        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Кастомизация", style=discord.ButtonStyle.primary, row=0)
    async def customize_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            view = ProfileCustomizeView(self.cog, self.user_id, self.guild_id, self.target_id)
            embed = await self.cog.build_profile_customize_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=view)
            await view._remember_message(interaction)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=0)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            embed = await self.cog.build_profile_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=self)
            await self._remember_message(interaction)


class ProfileCustomizeView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, target_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self.remove_item(self.theme_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню кастомизации открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def refresh_message(self):
        if self.message is None:
            return
        member = self.message.guild.get_member(self.target_id) if self.message.guild else None
        if member is None:
            return
        embed = await self.cog.build_profile_customize_embed(member, self.guild_id)
        await self.message.edit(embed=embed, view=self)

    async def _cycle_profile_value(self, interaction: discord.Interaction, *, mode: str):
        async with self._view_lock:
            async with get_user_lock(self.user_id):
                user = await db.get_user(self.user_id, self.guild_id)
                if not user:
                    await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                    return

                profile = get_profile_state(user)
                if mode == "title":
                    owned = list(profile.get("owned_titles", []))
                    current = str(profile.get("active_title", owned[0] if owned else "rookie"))
                    if not owned:
                        await interaction.response.send_message("У тебя пока нет титулов.", ephemeral=True)
                        return
                    next_key = owned[(owned.index(current) + 1) % len(owned)]
                    set_active_title(user, next_key)
                    message = f"Активный титул: **{PROFILE_TITLES[next_key]['name']}**"
                else:
                    message = "Новые титулы теперь покупаются через `/shop` во вкладке `Кастомизация`."

                await db.update_user(self.user_id, self.guild_id, {"game_stats": user.get("game_stats", {})})

            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            embed = await self.cog.build_profile_customize_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=self)
            await self._remember_message(interaction)
            await interaction.followup.send(message, ephemeral=True)

    @discord.ui.button(label="Сменить титул", style=discord.ButtonStyle.primary, row=0)
    async def title_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cycle_profile_value(interaction, mode="title")

    @discord.ui.button(label="Где купить титулы", style=discord.ButtonStyle.secondary, row=0)
    async def theme_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Новые титулы покупаются через `/shop` во вкладке `Кастомизация`.", ephemeral=True)

    @discord.ui.button(label="Выбрать улов", style=discord.ButtonStyle.success, row=1)
    async def catch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            async with get_user_lock(self.user_id):
                user = await db.get_user(self.user_id, self.guild_id)
                if not user:
                    await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                    return
                fishing = (((user.get("game_stats") or {}).get("_systems") or {}).get("fishing") or {})
                last_catch = fishing.get("last_catch")
                if not isinstance(last_catch, dict) or not last_catch.get("name"):
                    await interaction.response.send_message(
                        "Сначала поймай рыбу через `/fish`, потом можно поставить последний улов в профиль.",
                        ephemeral=True,
                    )
                    return
                set_favorite_catch(user, last_catch)
                await db.update_user(self.user_id, self.guild_id, {"game_stats": user.get("game_stats", {})})

            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            embed = await self.cog.build_profile_customize_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=self)
            await self._remember_message(interaction)
            await interaction.followup.send(
                f"Любимый улов обновлён: **{last_catch.get('emoji', '')} {last_catch.get('name', 'Улов')}**.",
                ephemeral=True,
            )

    @discord.ui.button(label="Сбросить улов", style=discord.ButtonStyle.secondary, row=1)
    async def reset_catch_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            async with get_user_lock(self.user_id):
                user = await db.get_user(self.user_id, self.guild_id)
                if not user:
                    await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                    return
                set_favorite_catch(user, None)
                await db.update_user(self.user_id, self.guild_id, {"game_stats": user.get("game_stats", {})})

            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            embed = await self.cog.build_profile_customize_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=self)
            await self._remember_message(interaction)

    @discord.ui.button(label="Назад к профилю", style=discord.ButtonStyle.secondary, row=2)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            view = ProfileView(self.cog, self.user_id, self.guild_id, self.target_id)
            embed = await self.cog.build_profile_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=view)
            await view._remember_message(interaction)


class EconomyCog(commands.Cog, name="Economy"):
    def __init__(self, bot):
        self.bot = bot

    def _market_multiplier(self, guild_id: int, category: str) -> tuple[float, dict | None]:
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is None:
            return 1.0, None
        return systems_cog.get_reward_multiplier(guild_id, category)

    async def _progress_contracts(self, user_id: int, guild_id: int, code: str, amount: int = 1):
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is not None:
            await systems_cog.progress_contracts(user_id, guild_id, code, amount)

    async def build_profile_embed(self, target: discord.Member, guild_id: int) -> discord.Embed:
        user = await db.get_user(target.id, guild_id)
        if not user:
            return discord.Embed(title="Профиль", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        user, normalized_businesses, _ = await ensure_unique_businesses(target.id, guild_id, user=user, sync_table=False)
        if not user:
            return discord.Embed(title="Профиль", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        winrate = 0.0
        total_results = int(user.get("total_won", 0) or 0) + int(user.get("total_lost", 0) or 0)
        if total_results > 0:
            winrate = int(user.get("total_won", 0) or 0) / total_results * 100

        rank = get_rank(int(user.get("balance", 0) or 0))
        bank_balance = int(user.get("bank", 0) or 0)
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        title_text = get_profile_title_text(user)
        embed_color = get_profile_theme_color(user, rank["color"])
        is_admin = target.id in ADMIN_IDS
        admin_badge = "ADMIN " if is_admin else ""

        xp_needed = max(int(user.get("level", 1) or 1) * 100, 1)
        xp_progress = int((int(user.get("xp", 0) or 0) / xp_needed) * 10)
        xp_progress = max(0, min(10, xp_progress))
        progress_bar = "■" * xp_progress + "□" * (10 - xp_progress)

        net_profit = int(user.get("total_won", 0) or 0) - int(user.get("total_lost", 0) or 0)
        game_stats = user.get("game_stats") or {}
        public_games = {key: value for key, value in game_stats.items() if not str(key).startswith("_") and isinstance(value, dict)}
        if public_games:
            top_games = sorted(public_games.items(), key=lambda item: int(item[1].get("played", 0) or 0), reverse=True)[:3]
            top_games_text = "\n".join(
                f"{index}. **{game.replace('_', ' ').title()}**: {int(stats.get('played', 0) or 0)} игр / {int(stats.get('won', 0) or 0)} побед"
                for index, (game, stats) in enumerate(top_games, start=1)
            )
        else:
            top_games_text = "Пока нет сыгранных игр."

        total_business_types = 0
        total_business_income = 0
        business_cards = []
        for business_id, entries in sorted(normalized_businesses.items(), key=lambda item: int(item[0])):
            business = BUSINESSES.get(int(business_id))
            if business is None or not entries:
                continue
            total_business_types += 1
            daily_income = int(business["income"] * 24 / business["time"])
            total_business_income += daily_income
            label = clean_business_name(business)
            business_cards.append((daily_income, f"• **{label}** — {format_money(daily_income)}/день"))

        if business_cards:
            business_cards.sort(key=lambda item: item[0], reverse=True)
            business_preview = "\n".join(line for _, line in business_cards[:4])
            hidden_count = len(business_cards) - 4
            if hidden_count > 0:
                business_preview += f"\n+{hidden_count} ещё"
            business_value = (
                f"Бизнесов: **{total_business_types}**\n"
                f"Пассив за день: **{format_money(total_business_income)}**\n"
                f"{business_preview}"
            )
        else:
            business_value = "Бизнесов пока нет."

        reputation = get_reputation(user)
        profile_state = get_profile_state(user)
        favorite_catch = profile_state.get("favorite_catch") or {}
        if favorite_catch:
            favorite_text = (
                f"{favorite_catch.get('emoji', '')} **{favorite_catch.get('name', 'Улов')}**\n"
                f"Редкость: **{favorite_catch.get('rarity_name', 'Обычная')}**\n"
                f"Цена: **{format_money(favorite_catch.get('price', 0))}**"
            )
        else:
            favorite_text = "Любимый улов пока не выбран."

        battle_pass_state = ensure_battle_pass_state(user)
        tier = battle_pass_tier(user)
        tier_progress, tier_total = battle_pass_progress_to_next(user)
        pass_status = "PREMIUM" if battle_pass_state.get("premium_unlocked") else "FREE"
        vip_label = VIP_NAMES.get(vip["name"], vip["name"])

        embed = discord.Embed(
            title=f"{admin_badge}{title_text} {target.display_name}",
            description=f"`{RANK_NAMES.get(rank['name'], rank['name'])}` • {vip['emoji']} {vip_label}".strip(),
            color=embed_color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="Финансы",
            value=(
                f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                f"Банк: **{format_money(bank_balance)}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name=f"Уровень {int(user.get('level', 1) or 1)}",
            value=f"{progress_bar}\n`{int(user.get('xp', 0) or 0)}/{xp_needed} XP`",
            inline=True,
        )
        embed.add_field(
            name="Репутация",
            value=f"**{reputation}** ({reputation_label(reputation)})",
            inline=True,
        )
        embed.add_field(
            name="Статистика",
            value=(
                f"Игр: **{int(user.get('games_played', 0) or 0)}** • Винрейт: **{winrate:.1f}%**\n"
                f"Выиграно: **{format_money(user.get('total_won', 0))}**\n"
                f"Проиграно: **{format_money(user.get('total_lost', 0))}**\n"
                f"Итог: **{format_money(net_profit)}**\n"
                f"Серия: **{int(user.get('win_streak', 0) or 0)}** (лучшее: {int(user.get('best_streak', 0) or 0)})"
            ),
            inline=False,
        )
        embed.add_field(name="Любимые игры", value=top_games_text, inline=False)
        embed.add_field(name="Топ бизнесов", value=business_value, inline=False)
        embed.add_field(name="Любимый улов", value=favorite_text, inline=False)
        embed.add_field(
            name=SEASON_NAME,
            value=(
                f"Статус: **{pass_status}**\n"
                f"Тир: **{tier}/{20}**\n"
                f"Прогресс: **{tier_progress}/{tier_total} XP**"
            ),
            inline=False,
        )
        if int(user.get("vip_level", 0) or 0) > 0:
            embed.add_field(
                name="VIP удобства",
                value="Доп. слоты контрактов, extra reroll и более красивый профиль уже активны.",
                inline=False,
            )
        embed.set_footer(text=f"ID игрока: {target.id}")
        return embed

    async def build_profile_customize_embed(self, target: discord.Member, guild_id: int) -> discord.Embed:
        user = await db.get_user(target.id, guild_id)
        if not user:
            return discord.Embed(title="Кастомизация", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        profile = get_profile_state(user)
        active_title = str(profile.get("active_title", "rookie"))
        favorite_catch = profile.get("favorite_catch")

        title_lines = [
            f"{'•' if key != active_title else '▶'} {PROFILE_TITLES[key]['name']}"
            for key in profile.get("owned_titles", [])
            if key in PROFILE_TITLES
        ] or ["Нет доступных титулов."]

        embed = discord.Embed(
            title="Профиль: кастомизация",
            description="Меняй титул и выставляй любимый улов.",
            color=get_profile_theme_color(user, COLORS["info"]),
        )
        embed.add_field(name="Титулы", value="\n".join(title_lines[:10]), inline=False)
        if favorite_catch:
            catch_text = (
                f"{favorite_catch.get('emoji', '')} **{favorite_catch.get('name', 'Улов')}**\n"
                f"Редкость: **{favorite_catch.get('rarity_name', 'Обычная')}**\n"
                f"Цена: **{format_money(favorite_catch.get('price', 0))}**"
            )
        else:
            catch_text = "Любимый улов не выбран. Нажми кнопку, чтобы поставить последний улов из `/fish`."
        embed.add_field(name="Выбранный улов", value=catch_text, inline=False)
        embed.set_footer(text="Кнопками ниже можно менять титул и ставить последний улов из `/fish`.")
        return embed

    @app_commands.command(name="profile", description="Показать профиль")
    async def profile(self, interaction: discord.Interaction, player: discord.Member = None):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        target = player or interaction.user
        embed = await self.build_profile_embed(target, interaction.guild_id)
        view = ProfileView(self, interaction.user.id, interaction.guild_id, target.id)
        if target.id != interaction.user.id:
            view.customize_btn.disabled = True
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
        return

        user = await db.get_user(target.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
            return

        user, normalized_businesses, _ = await ensure_unique_businesses(target.id, interaction.guild_id, user=user, sync_table=False)
        if not user:
            await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
            return

        winrate = 0.0
        if user.get("games_played", 0) > 0:
            total_results = int(user.get("total_won", 0) or 0) + int(user.get("total_lost", 0) or 0)
            if total_results > 0:
                winrate = int(user.get("total_won", 0) or 0) / total_results * 100

        rank = get_rank(int(user.get("balance", 0) or 0))
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        is_admin = target.id in ADMIN_IDS
        admin_badge = "АДМИН • " if is_admin else ""

        xp_needed = max(int(user.get("level", 1) or 1) * 100, 1)
        xp_progress = int((int(user.get("xp", 0) or 0) / xp_needed) * 10)
        xp_progress = max(0, min(10, xp_progress))
        progress_bar = "█" * xp_progress + "░" * (10 - xp_progress)

        net_profit = int(user.get("total_won", 0) or 0) - int(user.get("total_lost", 0) or 0)
        profit_emoji = "📈" if net_profit >= 0 else "📉"

        game_stats = user.get("game_stats") or {}
        if game_stats:
            top_games = sorted(game_stats.items(), key=lambda item: int(item[1].get("played", 0) or 0), reverse=True)[:3]
            top_games_text = "\n".join(
                f"{index}. **{game.replace('_', ' ').title()}**: {int(stats.get('played', 0) or 0)} игр ({int(stats.get('won', 0) or 0)} побед)"
                for index, (game, stats) in enumerate(top_games, start=1)
            )
        else:
            top_games_text = "Пока нет сыгранных игр."

        total_business_types = 0
        total_business_income = 0
        business_cards = []
        for business_id, entries in sorted(normalized_businesses.items(), key=lambda item: int(item[0])):
            business = BUSINESSES.get(int(business_id))
            if business is None or not entries:
                continue

            total_business_types += 1
            daily_income = int(business["income"] * 24 / business["time"])
            total_business_income += daily_income
            label = clean_business_name(business)
            business_cards.append((daily_income, f"• **{label}** — {format_money(daily_income)}/день"))

        if business_cards:
            business_cards.sort(key=lambda item: item[0], reverse=True)
            business_preview = "\n".join(line for _, line in business_cards[:4])
            hidden_count = len(business_cards) - 4
            if hidden_count > 0:
                business_preview += f"\n+{hidden_count} ещё"
            business_value = (
                f"Бизнесов: **{total_business_types}**\n"
                f"Пассив в день: **{format_money(total_business_income)}**\n"
                f"{business_preview}"
            )
        else:
            business_value = "Бизнесов пока нет.\nОткрой `/businesses`, чтобы купить первый."

        rank_name = RANK_NAMES.get(rank["name"], rank["name"])
        vip_name = VIP_NAMES.get(vip["name"], vip["name"])
        vip_display = f"{vip['emoji']} {vip_name}".strip()

        embed = discord.Embed(
            title=f"{admin_badge}{rank['emoji']} {target.display_name}",
            description=f"`{rank_name}` • {vip_display}",
            color=rank["color"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="💵 Финансы",
            value=f"Наличные: **{format_money(user.get('balance', 0))}**\nГемы: **{int(user.get('gems', 0) or 0):,}**",
            inline=True,
        )
        embed.add_field(
            name=f"📊 Уровень {int(user.get('level', 1) or 1)}",
            value=f"{progress_bar}\n`{int(user.get('xp', 0) or 0)}/{xp_needed} XP` • x{rank['bonus']}",
            inline=True,
        )
        embed.add_field(
            name="🎮 Статистика",
            value=(
                f"Игр: **{int(user.get('games_played', 0) or 0)}** • Винрейт: **{winrate:.1f}%**\n"
                f"Выиграно: **{format_money(user.get('total_won', 0))}**\n"
                f"Проиграно: **{format_money(user.get('total_lost', 0))}**\n"
                f"{profit_emoji} Итог: **{format_money(net_profit)}**\n"
                f"🔥 Серия: **{int(user.get('win_streak', 0) or 0)}** (лучшее: {int(user.get('best_streak', 0) or 0)})"
            ),
            inline=False,
        )
        embed.add_field(name="🃏 Любимые игры", value=top_games_text, inline=False)
        embed.add_field(name="🏢 Топ бизнесы", value=business_value, inline=False)
        embed.set_footer(text=f"ID игрока: {target.id}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="daily", description="Забрать ежедневный бонус")
    async def daily(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                await interaction.edit_original_response(content="Не удалось загрузить профиль.")
                return

            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_hours = int(24 * (1 - vip["cooldown_reduction"]))

            if user.get("last_daily"):
                last_daily = datetime.fromisoformat(user["last_daily"]).replace(tzinfo=timezone.utc)
                if now - last_daily < timedelta(hours=cooldown_hours):
                    next_daily_at = last_daily + timedelta(hours=cooldown_hours)
                    await interaction.edit_original_response(
                        content=f"Ты уже забрал ежедневный бонус. Возвращайся {format_discord_deadline(next_daily_at)}."
                    )
                    return

            bonus = random.randint(3000, 8500)
            gems = random.randint(5, 15)
            if vip["daily_bonus"] > 1:
                bonus = int(bonus * vip["daily_bonus"])
                gems += int(gems * (vip["daily_bonus"] - 1))
            event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "economy")
            if event_multiplier > 1:
                bonus = int(bonus * event_multiplier)
                gems = int(gems + max(1, round((event_multiplier - 1) * 6)))

            streak_bonus = 0
            streak_gems = 0
            if user.get("last_daily"):
                last_daily = datetime.fromisoformat(user["last_daily"]).replace(tzinfo=timezone.utc)
                if (now - last_daily).days == 1:
                    user["daily_streak"] = int(user.get("daily_streak", 0) or 0) + 1
                    if user["daily_streak"] >= 7:
                        streak_bonus = 15000
                        streak_gems = 20
                else:
                    user["daily_streak"] = 1
            else:
                user["daily_streak"] = 1

            user["balance"] += bonus + streak_bonus
            user["gems"] += gems + streak_gems
            user["last_daily"] = now.isoformat()
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "earn", bonus + streak_bonus))
        asyncio.create_task(
            record_player_progress(
                interaction.user.id,
                interaction.guild_id,
                money=bonus + streak_bonus,
                gems=gems + streak_gems,
            )
        )

        embed = discord.Embed(title="🎁 ЕЖЕДНЕВНЫЙ БОНУС", color=COLORS["success"])
        embed.add_field(name="Деньги", value=f"**+{format_money(bonus)}**", inline=True)
        embed.add_field(name="Гемы", value=f"**+{gems}**", inline=True)
        embed.add_field(name="Серия", value=f"**{int(user.get('daily_streak', 1) or 1)} дней**", inline=True)
        embed.add_field(name="Следующий бонус", value=format_discord_deadline(now + timedelta(hours=cooldown_hours)), inline=False)
        if streak_bonus or streak_gems:
            embed.add_field(name="Бонус за серию", value=f"+{format_money(streak_bonus)} • +{streak_gems} гемов", inline=False)
        if active_event:
            embed.add_field(name="Событие", value=f"`{active_event['name']}`", inline=False)
        embed.add_field(name="Новый баланс", value=f"**{format_money(user['balance'])}**", inline=False)
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="work", description="Поработать и заработать деньги")
    async def work(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                await interaction.edit_original_response(content="Ошибка загрузки профиля.")
                return

            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_minutes = int(10 * (1 - vip["cooldown_reduction"]))

            if user.get("last_work"):
                last_work = datetime.fromisoformat(user["last_work"]).replace(tzinfo=timezone.utc)
                if now - last_work < timedelta(minutes=cooldown_minutes):
                    next_work_at = last_work + timedelta(minutes=cooldown_minutes)
                    await interaction.edit_original_response(
                        content=f"😓 Ты устал. Можно снова работать {format_discord_deadline(next_work_at)}."
                    )
                    return

            jobs = [
                ("🍕 Доставка пиццы", 80, 200),
                ("🚕 Такси", 100, 250),
                ("💻 Фриланс-разработка", 150, 400),
            ]
            job = random.choice(jobs)
            salary = int(random.randint(job[1], job[2]) * 1.35)
            if vip["daily_bonus"] > 1:
                salary = int(salary * vip["daily_bonus"])
            event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "economy")
            if event_multiplier > 1:
                salary = int(salary * event_multiplier)

            user["balance"] += salary
            user["last_work"] = now.isoformat()
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "work", 1))
        asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "earn", salary))
        asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "work", 1))
        asyncio.create_task(
            record_player_progress(
                interaction.user.id,
                interaction.guild_id,
                action="work",
                amount=1,
                money=salary,
            )
        )

        event_note = f"\n🔥 Событие: `{active_event['name']}`" if active_event else ""
        embed = create_embed(
            "💼 РАБОТА ЗАВЕРШЕНА",
            f"{job[0]}\n\n✅ Заработано: `{format_money(salary)}`\n💰 Баланс: `{format_money(user['balance'])}`{event_note}",
            COLORS["success"],
        )
        embed.add_field(name="Снова доступно", value=format_discord_deadline(now + timedelta(minutes=cooldown_minutes)), inline=False)
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="crime", description="Пойти на преступление ради денег")
    async def crime(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                await interaction.edit_original_response(content="Не удалось загрузить профиль.")
                return

            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_minutes = int(30 * (1 - vip["cooldown_reduction"]))

            if user.get("last_crime"):
                last_crime = datetime.fromisoformat(user["last_crime"]).replace(tzinfo=timezone.utc)
                if now - last_crime < timedelta(minutes=cooldown_minutes):
                    next_crime_at = last_crime + timedelta(minutes=cooldown_minutes)
                    await interaction.edit_original_response(
                        content=f"🚨 Нужно залечь на дно. Следующая попытка {format_discord_deadline(next_crime_at)}."
                    )
                    return

            crimes = [
                ("🏪 Ограбление магазина", 500, 2000, 0.65),
                ("🏦 Налёт на банк", 1000, 5000, 0.50),
            ]
            crime_name, min_reward, max_reward, success_rate = random.choice(crimes)
            reputation = get_reputation(user)
            success_rate = max(0.15, min(0.92, success_rate + reputation_crime_bonus(reputation)))
            event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "crime")
            if active_event is None:
                event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "economy")

            if random.random() < success_rate:
                reward = int(random.randint(min_reward, max_reward) * 1.25)
                gems_bonus = random.randint(2, 6)
                if event_multiplier > 1:
                    reward = int(reward * event_multiplier)
                    gems_bonus += max(1, round((event_multiplier - 1) * 4))
                user["balance"] += reward
                user["gems"] += gems_bonus
                user["last_crime"] = now.isoformat()
                await db.update_user(interaction.user.id, interaction.guild_id, user)
                asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "crime", 1))
                asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "earn", reward))
                asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "crime", 1))
                asyncio.create_task(
                    record_player_progress(
                        interaction.user.id,
                        interaction.guild_id,
                        action="crime",
                        amount=1,
                        money=reward,
                        gems=gems_bonus,
                        reputation=4,
                        crime_runs=1,
                    )
                )
                message = (
                    f"{crime_name}\n"
                    f"✅ Успех\n"
                    f"💵 Добыча: `{format_money(reward)}`\n"
                    f"💎 Бонус: `{gems_bonus} гем.`\n"
                    f"🕶 Репутация: `{reputation + 4}`"
                )
                color = COLORS["success"]
            else:
                shielded = has_active_shield(user)
                fine = 0 if shielded else min(random.randint(min_reward // 2, min_reward), int(user.get("balance", 0) or 0))
                user["balance"] -= fine
                user["last_crime"] = now.isoformat()
                await db.update_user(interaction.user.id, interaction.guild_id, user)
                asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "crime", 1))
                asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "crime", 1))
                asyncio.create_task(
                    record_player_progress(
                        interaction.user.id,
                        interaction.guild_id,
                        action="crime",
                        amount=1,
                        reputation=-6 if not shielded else -2,
                        crime_runs=1,
                    )
                )
                if shielded:
                    message = (
                        f"{crime_name}\n🛡️ Тебя спасла теневая страховка\n"
                        f"🚔 Штраф: `{format_money(0)}`\n"
                        f"🕶 Репутация: `{reputation - 2}`"
                    )
                    color = COLORS["warning"]
                else:
                    message = (
                        f"{crime_name}\n❌ Поймали\n"
                        f"🚔 Штраф: `-{format_money(fine)}`\n"
                        f"🕶 Репутация: `{reputation - 6}`"
                    )
                    color = COLORS["error"]

        event_note = f"\n🔥 Событие: `{active_event['name']}`" if active_event else ""
        embed = create_embed("🕵️ ПРЕСТУПЛЕНИЕ", f"{message}\n\n💰 Баланс: `{format_money(user['balance'])}`{event_note}", color)
        embed.add_field(name="Снова доступно", value=format_discord_deadline(now + timedelta(minutes=cooldown_minutes)), inline=False)
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="slut", description="Рискованный способ быстро заработать")
    async def slut(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                await interaction.edit_original_response(content="Не удалось загрузить профиль.")
                return

            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_minutes = int(15 * (1 - vip["cooldown_reduction"]))

            if user.get("last_slut"):
                last_slut = datetime.fromisoformat(user["last_slut"]).replace(tzinfo=timezone.utc)
                if now - last_slut < timedelta(minutes=cooldown_minutes):
                    next_slut_at = last_slut + timedelta(minutes=cooldown_minutes)
                    await interaction.edit_original_response(
                        content=f"😮‍💨 Ты устал. Можно снова попробовать {format_discord_deadline(next_slut_at)}."
                    )
                    return

            outcomes = [
                ("📹 Ночной стрим", 300, 800, 0.70),
                ("💃 Выступление в клубе", 400, 1000, 0.65),
            ]
            job_name, min_earn, max_earn, success_rate = random.choice(outcomes)
            event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "economy")

            if random.random() < success_rate:
                earnings = int(random.randint(min_earn, max_earn) * 1.2)
                if event_multiplier > 1:
                    earnings = int(earnings * event_multiplier)
                user["balance"] += earnings
                message = f"{job_name}\n✅ Успех\n💵 Заработано: `{format_money(earnings)}`"
                color = COLORS["success"]
            else:
                shielded = has_active_shield(user)
                loss = 0 if shielded else min(random.randint(100, 500), int(user.get("balance", 0) or 0))
                user["balance"] -= loss
                if shielded:
                    message = f"{job_name}\n🛡️ Страховка прикрыла провал\n🧾 Потеряно: `{format_money(0)}`"
                    color = COLORS["warning"]
                else:
                    message = f"{job_name}\n❌ Не повезло\n🧾 Потеряно: `-{format_money(loss)}`"
                    color = COLORS["error"]

            user["last_slut"] = now.isoformat()
            await db.update_user(interaction.user.id, interaction.guild_id, user)
            asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "slut", 1))
            asyncio.create_task(self._progress_contracts(interaction.user.id, interaction.guild_id, "slut", 1))
            if color == COLORS["success"]:
                asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "earn", earnings))
            asyncio.create_task(
                record_player_progress(
                    interaction.user.id,
                    interaction.guild_id,
                    action="slut",
                    amount=1,
                    money=earnings if color == COLORS["success"] else 0,
                )
            )

        event_note = f"\n🔥 Событие: `{active_event['name']}`" if active_event else ""
        embed = create_embed("🔥 РИСКОВАННАЯ РАБОТА", f"{message}\n\n💰 Баланс: `{format_money(user['balance'])}`{event_note}", color)
        embed.add_field(name="Снова доступно", value=format_discord_deadline(now + timedelta(minutes=cooldown_minutes)), inline=False)
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="hourly", description="Забрать почасовой бонус")
    async def hourly(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return

        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if not user:
                await interaction.edit_original_response(content="Не удалось загрузить профиль.")
                return

            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_hours = max(1, int(1 * (1 - vip["cooldown_reduction"])))

            if user.get("last_hourly"):
                last_hourly = datetime.fromisoformat(user["last_hourly"]).replace(tzinfo=timezone.utc)
                if now - last_hourly < timedelta(hours=cooldown_hours):
                    next_hourly_at = last_hourly + timedelta(hours=cooldown_hours)
                    await interaction.edit_original_response(
                        content=f"Ты уже забрал почасовой бонус. Возвращайся {format_discord_deadline(next_hourly_at)}."
                    )
                    return

            bonus = random.randint(500, 1800)
            gems = random.randint(2, 6)
            if vip["daily_bonus"] > 1:
                bonus = int(bonus * vip["daily_bonus"])
                gems += int(gems * (vip["daily_bonus"] - 1))
            event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "economy")
            if event_multiplier > 1:
                bonus = int(bonus * event_multiplier)
                gems += max(1, round((event_multiplier - 1) * 4))

            user["balance"] += bonus
            user["gems"] += gems
            user["last_hourly"] = now.isoformat()
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "hourly", 1))
        asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "earn", bonus))

        embed = discord.Embed(title="⏰ ПОЧАСОВОЙ БОНУС", color=COLORS["success"])
        embed.add_field(name="Деньги", value=f"**+{format_money(bonus)}**", inline=True)
        embed.add_field(name="Гемы", value=f"**+{gems}**", inline=True)
        embed.add_field(name="Баланс", value=f"**{format_money(user['balance'])}**", inline=True)
        embed.add_field(name="Следующий бонус", value=format_discord_deadline(now + timedelta(hours=cooldown_hours)), inline=False)
        if active_event:
            embed.add_field(name="Событие", value=f"`{active_event['name']}`", inline=False)
        await interaction.edit_original_response(content=None, embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
