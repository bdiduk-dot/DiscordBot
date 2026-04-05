import asyncio
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from economy_events import CRIME_POOL, SLUT_POOL, WORK_POOL
from config import ADMIN_IDS, BUSINESSES, COLORS, get_rank, get_vip_level
from database import db, get_user_lock
from progression import (
    PROFILE_THEMES,
    PROFILE_TITLES,
    SEASON_NAME,
    battle_pass_progress_to_next,
    battle_pass_tier,
    ensure_battle_pass_state,
    get_profile_state,
    get_profile_theme_color,
    get_profile_theme_image,
    get_profile_title_text,
    get_reputation,
    reputation_crime_bonus,
    reputation_label,
    set_active_theme,
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
    schedule_message_cleanup,
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

HOUSE_PROFILE_NAMES = {
    "studio": "Дачный домик",
    "flat_one": "Небольшой дом",
    "flat_two": "Семейный дом",
    "townhouse": "Таунхаус",
    "country_house": "Загородный дом",
    "penthouse": "Особняк",
}


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def clean_business_name(business: dict) -> str:
    raw_name = str(business.get("name", "Business"))
    ascii_name = re.sub(r"\s+", " ", raw_name.encode("ascii", "ignore").decode()).strip(" -")
    return ascii_name or raw_name


def _profile_progress_bar(current: int, total: int, *, length: int = 10) -> str:
    total = max(1, int(total))
    current = max(0, min(int(current), total))
    filled = round((current / total) * length)
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


def _profile_house_name(user: dict[str, Any]) -> str:
    game_stats = user.get("game_stats") or {}
    systems = game_stats.get("_systems") if isinstance(game_stats, dict) else {}
    house_state = systems.get("house") if isinstance(systems, dict) else {}
    house_id = str((house_state or {}).get("owned_house_id") or "").strip()
    if not house_id:
        return "Нет"
    return HOUSE_PROFILE_NAMES.get(house_id, house_id.replace("_", " ").title())


class ProfileView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, target_id: int):
        super().__init__(timeout=120)
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

    @discord.ui.button(label="Дом", style=discord.ButtonStyle.secondary, row=1)
    async def house_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            view = ProfileInfoView(self.cog, self.user_id, self.guild_id, self.target_id, section="house")
            embed = await self.cog.build_profile_house_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=view)
            await view._remember_message(interaction)

    @discord.ui.button(label="Бизнесы", style=discord.ButtonStyle.secondary, row=1)
    async def businesses_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            member = interaction.guild.get_member(self.target_id) if interaction.guild else None
            if member is None:
                await interaction.response.send_message("Игрок не найден.", ephemeral=True)
                return
            view = ProfileInfoView(self.cog, self.user_id, self.guild_id, self.target_id, section="businesses")
            embed = await self.cog.build_profile_businesses_embed(member, self.guild_id)
            await interaction.response.edit_message(embed=embed, view=view)
            await view._remember_message(interaction)


class WorkChoiceView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, choices: list[dict[str, Any]]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.choices = choices[:3]
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню работы открыто не тобой.", ephemeral=True)
            return False
        return True

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

    async def _resolve(self, interaction: discord.Interaction, index: int):
        if index >= len(self.choices):
            await interaction.response.send_message("Этот вариант сейчас недоступен.", ephemeral=True)
            return
        choice = self.choices[index]
        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                await interaction.response.send_message("Ошибка загрузки профиля.", ephemeral=True)
                return
            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_minutes = int(10 * (1 - vip["cooldown_reduction"]))
            if user.get("last_work"):
                last_work = datetime.fromisoformat(user["last_work"]).replace(tzinfo=timezone.utc)
                if now - last_work < timedelta(minutes=cooldown_minutes):
                    next_work_at = last_work + timedelta(minutes=cooldown_minutes)
                    await interaction.response.send_message(f"Следующая работа будет доступна {format_discord_deadline(next_work_at)}.", ephemeral=True)
                    return
            salary = random.randint(int(choice["reward_min"]), int(choice["reward_max"]))
            if vip["daily_bonus"] > 1:
                salary = int(salary * vip["daily_bonus"])
            event_multiplier, active_event = self.cog._market_multiplier(self.guild_id, "economy")
            if event_multiplier > 1:
                salary = int(salary * event_multiplier)
            from easter_event import grant_easter_drops, maybe_apply_easter_work_bonus

            easter_cog = self.cog.bot.get_cog("EasterEvent")
            salary = maybe_apply_easter_work_bonus(user, salary)
            user["balance"] = int(user.get("balance", 0) or 0) + salary
            easter_lines = grant_easter_drops(
                user,
                "work",
                guild_state=easter_cog.get_cached_guild_state(self.guild_id) if easter_cog else None,
            )
            user["last_work"] = now.isoformat()
            await db.update_user(self.user_id, self.guild_id, user)

        asyncio.create_task(check_quest_progress(self.user_id, self.guild_id, "work", 1))
        asyncio.create_task(check_quest_progress(self.user_id, self.guild_id, "earn", salary))
        asyncio.create_task(self.cog._progress_contracts(self.user_id, self.guild_id, "work", 1))
        asyncio.create_task(record_player_progress(self.user_id, self.guild_id, action="work", amount=1, money=salary))

        event_note = f"\n🔥 Событие: `{active_event['name']}`" if active_event else ""
        embed = create_embed(
            "💼 РАБОТА ВЫПОЛНЕНА",
            f"{choice['summary']}\n\n✅ Получено: `{format_money(salary)}`\n💰 Баланс: `{format_money(user['balance'])}`{event_note}",
            COLORS["success"],
        )
        embed.add_field(name="Снова доступно", value=format_discord_deadline(now + timedelta(minutes=cooldown_minutes)), inline=False)
        if easter_lines:
            embed.add_field(name="Пасха 2026", value="\n".join(easter_lines), inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)

    @discord.ui.button(label="Вариант 1", style=discord.ButtonStyle.success, row=0)
    async def option_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, 0)

    @discord.ui.button(label="Вариант 2", style=discord.ButtonStyle.success, row=0)
    async def option_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, 1)

    @discord.ui.button(label="Вариант 3", style=discord.ButtonStyle.success, row=0)
    async def option_three(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, 2)


class CrimeChoiceView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, choices: list[dict[str, Any]]):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.choices = choices[:3]
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню преступлений открыто не тобой.", ephemeral=True)
            return False
        return True

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

    async def _resolve(self, interaction: discord.Interaction, index: int):
        if index >= len(self.choices):
            await interaction.response.send_message("Этот вариант сейчас недоступен.", ephemeral=True)
            return
        choice = self.choices[index]
        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return
            now = datetime.now(timezone.utc)
            vip = get_vip_level(int(user.get("vip_level", 0) or 0))
            cooldown_minutes = int(30 * (1 - vip["cooldown_reduction"]))
            if user.get("last_crime"):
                last_crime = datetime.fromisoformat(user["last_crime"]).replace(tzinfo=timezone.utc)
                if now - last_crime < timedelta(minutes=cooldown_minutes):
                    next_crime_at = last_crime + timedelta(minutes=cooldown_minutes)
                    await interaction.response.send_message(f"Следующая попытка будет доступна {format_discord_deadline(next_crime_at)}.", ephemeral=True)
                    return
            reputation = get_reputation(user)
            success_rate = max(0.15, min(0.92, float(choice["success_rate"]) + reputation_crime_bonus(reputation)))
            event_multiplier, active_event = self.cog._market_multiplier(self.guild_id, "crime")
            if active_event is None:
                event_multiplier, active_event = self.cog._market_multiplier(self.guild_id, "economy")
            if random.random() < success_rate:
                reward = random.randint(int(choice["reward_min"]), int(choice["reward_max"]))
                reward = int(reward * event_multiplier) if event_multiplier > 1 else reward
                gems_bonus = random.randint(2, 6)
                user["balance"] = int(user.get("balance", 0) or 0) + reward
                user["gems"] = int(user.get("gems", 0) or 0) + gems_bonus
                message = (
                    f"{choice['success_text']}\n"
                    f"✅ Успех\n"
                    f"💵 Добыча: `{format_money(reward)}`\n"
                    f"💎 Бонус: `{gems_bonus} гем.`"
                )
                color = COLORS["success"]
                asyncio.create_task(check_quest_progress(self.user_id, self.guild_id, "earn", reward))
                asyncio.create_task(record_player_progress(self.user_id, self.guild_id, action="crime", amount=1, money=reward, gems=gems_bonus, reputation=4, crime_runs=1))
            else:
                shielded = has_active_shield(user)
                fine = 0 if shielded else min(random.randint(int(choice["fine_min"]), int(choice["fine_max"])), int(user.get("balance", 0) or 0))
                user["balance"] = int(user.get("balance", 0) or 0) - fine
                if shielded:
                    message = (
                        f"{choice['fail_text']}\n"
                        "🛡️ Теневая страховка спасла тебя.\n"
                        f"🚫 Штраф: `{format_money(0)}`\n"
                        "📉 Репутация: `0`"
                    )
                    color = COLORS["warning"]
                    asyncio.create_task(record_player_progress(self.user_id, self.guild_id, action="crime", amount=1, reputation=0, crime_runs=1))
                else:
                    message = (
                        f"{choice['fail_text']}\n"
                        "❌ Провал\n"
                        f"🚫 Штраф: `-{format_money(fine)}`\n"
                        "📉 Репутация: `-6`"
                    )
                    color = COLORS["error"]
                    asyncio.create_task(record_player_progress(self.user_id, self.guild_id, action="crime", amount=1, reputation=-6, crime_runs=1))
            from easter_event import grant_easter_drops

            easter_cog = self.cog.bot.get_cog("EasterEvent")
            easter_lines = grant_easter_drops(
                user,
                "crime",
                guild_state=easter_cog.get_cached_guild_state(self.guild_id) if easter_cog else None,
            )
            user["last_crime"] = now.isoformat()
            await db.update_user(self.user_id, self.guild_id, user)

        asyncio.create_task(check_quest_progress(self.user_id, self.guild_id, "crime", 1))
        asyncio.create_task(self.cog._progress_contracts(self.user_id, self.guild_id, "crime", 1))

        event_note = f"\n🔥 Событие: `{active_event['name']}`" if active_event else ""
        embed = create_embed("🕵️ ПРЕСТУПЛЕНИЕ", f"{message}\n\n💰 Баланс: `{format_money(user['balance'])}`{event_note}", color)
        embed.add_field(name="Снова доступно", value=format_discord_deadline(now + timedelta(minutes=cooldown_minutes)), inline=False)
        if easter_lines:
            embed.add_field(name="Пасха 2026", value="\n".join(easter_lines), inline=False)
        await interaction.response.edit_message(embed=embed, view=None)
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)

    @discord.ui.button(label="Риск 1", style=discord.ButtonStyle.danger, row=0)
    async def option_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, 0)

    @discord.ui.button(label="Риск 2", style=discord.ButtonStyle.danger, row=0)
    async def option_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, 1)

    @discord.ui.button(label="Риск 3", style=discord.ButtonStyle.danger, row=0)
    async def option_three(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, 2)


class ProfileCustomizeView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, target_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

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
                elif mode == "theme":
                    owned = [key for key in profile.get("owned_themes", []) if key in PROFILE_THEMES]
                    current = str(profile.get("active_theme", owned[0] if owned else "classic"))
                    if not owned:
                        await interaction.response.send_message("У тебя пока нет доступных фонов.", ephemeral=True)
                        return
                    next_key = owned[(owned.index(current) + 1) % len(owned)]
                    set_active_theme(user, next_key)
                    message = f"Активный фон: **{PROFILE_THEMES[next_key]['name']}**"
                else:
                    message = "Новые фоны и титулы открываются через награды, сезон и временные ивенты."

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

    @discord.ui.button(label="Сменить фон", style=discord.ButtonStyle.secondary, row=0)
    async def theme_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._cycle_profile_value(interaction, mode="theme")

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


class ProfileInfoView(discord.ui.View):
    def __init__(self, cog: "EconomyCog", user_id: int, guild_id: int, target_id: int, *, section: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.target_id = target_id
        self.section = section
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

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

    @discord.ui.button(label="Назад к профилю", style=discord.ButtonStyle.secondary, row=0)
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
        admin_badge = "АДМИН • " if is_admin else ""

        level = int(user.get("level", 1) or 1)
        xp_current = int(user.get("xp", 0) or 0)
        xp_needed = max(level * 100, 1)
        progress_bar = _profile_progress_bar(xp_current, xp_needed, length=10)

        net_profit = int(user.get("total_won", 0) or 0) - int(user.get("total_lost", 0) or 0)

        total_business_types = 0
        total_business_income = 0
        for business_id, entries in sorted(normalized_businesses.items(), key=lambda item: int(item[0])):
            business = BUSINESSES.get(int(business_id))
            if business is None or not entries:
                continue
            total_business_types += 1
            daily_income = int(business["income"] * 24 / business["time"])
            total_business_income += daily_income

        reputation = get_reputation(user)
        profile_state = get_profile_state(user)
        favorite_catch = profile_state.get("favorite_catch") or {}
        battle_pass_state = ensure_battle_pass_state(user)
        tier = battle_pass_tier(user)
        tier_progress, tier_total = battle_pass_progress_to_next(user)
        pass_status = "Премиум" if battle_pass_state.get("premium_unlocked") else "Бесплатный"
        vip_label = VIP_NAMES.get(vip["name"], vip["name"])
        house_name = _profile_house_name(user)
        streak_now = int(user.get("win_streak", 0) or 0)
        streak_best = int(user.get("best_streak", 0) or 0)
        games_played = int(user.get("games_played", 0) or 0)

        description_lines = [
            f"{rank['emoji']} **{RANK_NAMES.get(rank['name'], rank['name'])}** • {vip['emoji']} **{vip_label}**",
            f"**Репутация:** {reputation} ({reputation_label(reputation)})",
            f"**Уровень {level}:** `{progress_bar}` **{xp_current}/{xp_needed} XP**",
        ]

        embed = discord.Embed(
            title=title_text,
            description="\n".join(description_lines),
            color=embed_color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_author(name=f"{admin_badge}{target.display_name}", icon_url=target.display_avatar.url)
        embed.set_thumbnail(url=target.display_avatar.url)
        theme_image = get_profile_theme_image(user)
        if theme_image:
            embed.set_image(url=theme_image)
        embed.add_field(
            name="💳 Кошелёк",
            value=(
                f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                f"Банк: **{format_money(bank_balance)}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🏠 Активы",
            value=(
                f"Дом: **{house_name}**\n"
                f"Бизнесов: **{total_business_types}**\n"
                f"Пассив/день: **{format_money(total_business_income)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="🎮 Игра",
            value=(
                f"Игр: **{games_played}**\n"
                f"Винрейт: **{winrate:.1f}%**\n"
                f"Серия: **{streak_now}** / лучший: **{streak_best}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="📊 Итоги по играм",
            value=(
                f"Выиграно: **{format_money(user.get('total_won', 0))}**\n"
                f"Проиграно: **{format_money(user.get('total_lost', 0))}**\n"
                f"Чистый итог: **{format_money(net_profit)}**"
            ),
            inline=False,
        )
        embed.add_field(
            name=f"🎟️ {SEASON_NAME}",
            value=(
                f"Статус: **{pass_status}**\n"
                f"Тир: **{tier}/20**\n"
                f"Прогресс: **{tier_progress}/{tier_total} XP**"
            ),
            inline=False,
        )
        if favorite_catch:
            embed.add_field(
                name="🐟 Любимый улов",
                value=(
                    f"{favorite_catch.get('emoji', '')} **{favorite_catch.get('name', 'Улов')}**\n"
                    f"Редкость: **{favorite_catch.get('rarity_name', 'Обычная')}**\n"
                    f"Цена: **{format_money(favorite_catch.get('price', 0))}**"
                ),
                inline=False,
            )
        embed.set_footer(text=f"ID игрока: {target.id}")
        return embed

    async def build_profile_house_embed(self, target: discord.Member, guild_id: int) -> discord.Embed:
        user = await db.get_user(target.id, guild_id)
        if not user:
            return discord.Embed(title="Дом", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        house_cog = self.bot.get_cog("House")
        embed = discord.Embed(title="🏠 Дом", color=COLORS["info"], timestamp=datetime.now(timezone.utc))
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        if house_cog is None:
            embed.description = "Система дома сейчас недоступна."
            return embed

        snapshot = house_cog._house_snapshot(user, guild_id)
        house_state = snapshot.get("house_state") or {}
        house_data = snapshot.get("house_data")
        if not house_data:
            embed.description = f"{target.mention} пока не купил дом."
            embed.add_field(
                name="Что появится после покупки",
                value="Подвал, крипта, аренда, сад и обустройство доступны через `/house`.",
                inline=False,
            )
            return embed

        rental_state = house_cog._rental_status(user)
        ongoing_rentals = rental_state.get("ongoing_rentals", [])
        next_rent_at = None
        for rental in ongoing_rentals:
            raw_ends_at = rental.get("ends_at")
            if isinstance(raw_ends_at, str):
                try:
                    ready_at = datetime.fromisoformat(raw_ends_at)
                except ValueError:
                    continue
                if ready_at.tzinfo is None:
                    ready_at = ready_at.replace(tzinfo=timezone.utc)
                else:
                    ready_at = ready_at.astimezone(timezone.utc)
            else:
                ready_at = raw_ends_at
            if ready_at is None:
                continue
            if next_rent_at is None or ready_at < next_rent_at:
                next_rent_at = ready_at

        garden_state = house_state.get("garden") if isinstance(house_state.get("garden"), dict) else {}
        plots = garden_state.get("plots") if isinstance(garden_state, dict) else []
        total_plots = max(int(house_state.get("max_garden_level", 0) or 0), len(plots))
        active_plots = sum(1 for plot in plots if str(plot.get("state") or "empty") != "empty")
        ready_plots = sum(1 for plot in plots if str(plot.get("state") or "") == "ready")
        furniture = [str(code).replace("_", " ").title() for code in house_state.get("furniture", [])]
        wallet = house_state.get("crypto_wallet", {}) if isinstance(house_state.get("crypto_wallet"), dict) else {}
        wallet_lines = [
            f"**{symbol}:** `{float(amount):.6f}`"
            for symbol, amount in wallet.items()
            if float(amount or 0) > 0
        ] or ["Криптокошелёк пока пуст."]

        embed.description = f"**{house_data['name']}**\n{house_data['description']}"
        embed.add_field(
            name="Обзор",
            value=(
                f"Комнаты: **{house_data['rooms']}**\n"
                f"Престиж: **{house_data['prestige']}**\n"
                f"Подвал: **{int(snapshot.get('basement_level', 0) or 0)}/{int(house_data['max_basement_level'])}**\n"
                f"Грядки: **{total_plots}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Крипта",
            value=(
                f"GPU: **{int(snapshot.get('installed_count', 0) or 0)}/{int(snapshot.get('capacity', 0) or 0)}**\n"
                f"Экв/ч: **{format_money(int(snapshot.get('hourly_income', 0) or 0))}**\n"
                f"Готово к сбору: **{format_money(int(snapshot.get('ready', 0) or 0))}**\n"
                f"Старый кошелёк: **{format_money(int(house_state.get('legacy_mining_wallet', 0) or 0))}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Аренда и сад",
            value=(
                f"Активных жильцов: **{len(ongoing_rentals)}**\n"
                f"Готово по аренде: **{format_money(int(rental_state.get('ready_total', 0) or 0))}**\n"
                f"Следующая аренда: **{format_discord_deadline(next_rent_at) if next_rent_at else 'Нет'}**\n"
                f"Сад: **{active_plots}/{total_plots}** занято, **{ready_plots}** готово"
            ),
            inline=False,
        )
        embed.add_field(name="Криптокошелёк", value="\n".join(wallet_lines[:6]), inline=False)
        embed.add_field(
            name="Обустройство",
            value=(
                f"Мебель: **{len(furniture)} шт.**\n"
                f"{', '.join(furniture[:4]) if furniture else 'Пока без мебели.'}"
            ),
            inline=False,
        )
        return embed

    async def build_profile_businesses_embed(self, target: discord.Member, guild_id: int) -> discord.Embed:
        business_cog = self.bot.get_cog("Business")
        embed = discord.Embed(title="🏢 Бизнесы", color=COLORS["gold"], timestamp=datetime.now(timezone.utc))
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        if business_cog is None:
            embed.description = "Система бизнесов сейчас недоступна."
            return embed

        summaries, totals = await business_cog.get_owned_summaries(target.id, guild_id, sync_table=False)
        if not summaries:
            embed.description = f"{target.mention} пока не купил ни одного бизнеса."
            embed.add_field(
                name="Старт",
                value="Первый источник пассивного дохода можно купить через `/businesses` или `/shop`.",
                inline=False,
            )
            return embed

        portfolio_lines = []
        for item in summaries[:6]:
            if item["ready_count"] > 0:
                status = f"Готово: **{item['ready_count']}**"
            elif item["next_ready_at"] is not None:
                status = f"Следующий сбор {format_discord_deadline(item['next_ready_at'])}"
            else:
                status = "Ожидает цикла"
            portfolio_lines.append(
                f"**{item['name']}** ×{item['count']}\n"
                f"Доход/день: **{format_money(item['daily_income'])}** • {status}"
            )

        embed.description = (
            f"Всего бизнесов: **{totals['total_owned']}**\n"
            f"Пассив/день: **{format_money(totals['total_income_per_day'])}**\n"
            f"Готово к сбору: **{totals['ready_total']}**"
        )
        embed.add_field(
            name="Сводка",
            value=(
                f"Вложено: **{format_money(totals['total_invested'])}**\n"
                f"Заработано: **{format_money(totals['total_earned'])}**\n"
                f"Баланс игрока: **{format_money(totals['balance'])}**"
            ),
            inline=False,
        )
        embed.add_field(name="Портфель", value="\n\n".join(portfolio_lines), inline=False)
        if len(summaries) > 6:
            embed.set_footer(text=f"Показано 6 из {len(summaries)} типов бизнесов.")
        return embed

    async def _build_profile_embed_legacy(self, target: discord.Member, guild_id: int) -> discord.Embed:
        user = await db.get_user(target.id, guild_id)
        if not user:
            return discord.Embed(title="Профиль", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        user, normalized_businesses, _ = await ensure_unique_businesses(target.id, guild_id, user=user, sync_table=False)
        if not user:
            return discord.Embed(title="Профиль", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        total_results = int(user.get("total_won", 0) or 0) + int(user.get("total_lost", 0) or 0)
        winrate = (int(user.get("total_won", 0) or 0) / total_results * 100) if total_results > 0 else 0.0
        rank = get_rank(int(user.get("balance", 0) or 0))
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        title_text = get_profile_title_text(user)
        embed_color = get_profile_theme_color(user, rank["color"])
        admin_badge = "ADMIN • " if target.id in ADMIN_IDS else ""

        xp_needed = max(int(user.get("level", 1) or 1) * 100, 1)
        xp_current = int(user.get("xp", 0) or 0)
        xp_progress = max(0, min(10, int((xp_current / xp_needed) * 10)))
        progress_bar = "█" * xp_progress + "░" * (10 - xp_progress)

        total_business_types = 0
        total_business_income = 0
        for business_id, entries in sorted(normalized_businesses.items(), key=lambda item: int(item[0])):
            business = BUSINESSES.get(int(business_id))
            if business is None or not entries:
                continue
            total_business_types += 1
            total_business_income += int(business["income"] * 24 / business["time"])

        systems = ((user.get("game_stats") or {}).get("_systems") or {})
        house_state = systems.get("house") if isinstance(systems, dict) else {}
        house_id = str((house_state or {}).get("owned_house_id") or "").strip()
        house_name = house_id.replace("_", " ").title() if house_id else "Нет"

        net_profit = int(user.get("total_won", 0) or 0) - int(user.get("total_lost", 0) or 0)
        rank_name = RANK_NAMES.get(rank["name"], rank["name"])
        vip_name = VIP_NAMES.get(vip["name"], vip["name"])
        vip_display = f"{vip['emoji']} {vip_name}".strip() if vip.get("emoji") else vip_name

        embed = discord.Embed(
            title=f"{admin_badge}{title_text} {target.display_name}",
            description=(
                f"**Ранг:** {rank_name}\n"
                f"**VIP:** {vip_display}\n"
                f"**Уровень:** {int(user.get('level', 1) or 1)} • `{xp_current}/{xp_needed} XP`\n"
                f"`{progress_bar}`"
            ),
            color=embed_color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(
            name="Деньги",
            value=(
                f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                f"Банк: **{format_money(user.get('bank', 0))}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Активность",
            value=(
                f"Игр: **{int(user.get('games_played', 0) or 0)}**\n"
                f"Винрейт: **{winrate:.1f}%**\n"
                f"Серия: **{int(user.get('win_streak', 0) or 0)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Имущество",
            value=(
                f"Дом: **{house_name}**\n"
                f"Бизнесов: **{total_business_types}**\n"
                f"Пассив/день: **{format_money(total_business_income)}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Краткая статистика",
            value=(
                f"Выиграно: **{format_money(user.get('total_won', 0))}**\n"
                f"Проиграно: **{format_money(user.get('total_lost', 0))}**\n"
                f"Итог по играм: **{format_money(net_profit)}**\n"
                f"Лучшая серия: **{int(user.get('best_streak', 0) or 0)}**"
            ),
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
        active_theme = str(profile.get("active_theme", "classic"))
        favorite_catch = profile.get("favorite_catch")

        title_lines = [
            f"{'•' if key != active_title else '▶'} {PROFILE_TITLES[key]['name']}"
            for key in profile.get("owned_titles", [])
            if key in PROFILE_TITLES
        ] or ["Нет доступных титулов."]
        theme_lines = [
            f"{'•' if key != active_theme else '▶'} {PROFILE_THEMES[key]['name']}"
            for key in profile.get("owned_themes", [])
            if key in PROFILE_THEMES
        ] or ["Нет доступных фонов."]

        embed = discord.Embed(
            title="Профиль: кастомизация",
            description="Меняй титул, фон профиля и выставляй любимый улов.",
            color=get_profile_theme_color(user, COLORS["info"]),
        )
        theme_image = get_profile_theme_image(user)
        embed.add_field(name="Титулы", value="\n".join(title_lines[:10]), inline=False)
        embed.add_field(name="Фоны", value="\n".join(theme_lines[:10]), inline=False)
        if theme_image:
            embed.set_image(url=theme_image)
        if favorite_catch:
            catch_text = (
                f"{favorite_catch.get('emoji', '')} **{favorite_catch.get('name', 'Улов')}**\n"
                f"Редкость: **{favorite_catch.get('rarity_name', 'Обычная')}**\n"
                f"Цена: **{format_money(favorite_catch.get('price', 0))}**"
            )
        else:
            catch_text = "Любимый улов не выбран. Нажми кнопку, чтобы поставить последний улов из `/fish`."
        embed.add_field(name="Выбранный улов", value=catch_text, inline=False)
        embed.set_footer(text="Кнопками ниже можно менять титул, фон профиля и ставить последний улов из `/fish`.")
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

            streak_multiplier = 1
            if user.get("last_daily"):
                last_daily = datetime.fromisoformat(user["last_daily"]).replace(tzinfo=timezone.utc)
                if now - last_daily <= timedelta(hours=48):
                    user["daily_streak"] = int(user.get("daily_streak", 0) or 0) + 1
                else:
                    user["daily_streak"] = 1
            else:
                user["daily_streak"] = 1

            if int(user.get("daily_streak", 1) or 1) % 7 == 0:
                streak_multiplier = 2

            final_bonus = int(bonus * streak_multiplier)
            from easter_event import grant_easter_drops

            user["balance"] += final_bonus
            user["gems"] += gems
            easter_cog = self.bot.get_cog("EasterEvent")
            easter_lines = grant_easter_drops(
                user,
                "daily",
                guild_state=easter_cog.get_cached_guild_state(interaction.guild_id) if easter_cog else None,
            )
            user["last_daily"] = now.isoformat()
            await db.update_user(interaction.user.id, interaction.guild_id, user)

        asyncio.create_task(check_quest_progress(interaction.user.id, interaction.guild_id, "earn", final_bonus))
        asyncio.create_task(
            record_player_progress(
                interaction.user.id,
                interaction.guild_id,
                money=final_bonus,
                gems=gems,
            )
        )

        embed = discord.Embed(title="🎁 ЕЖЕДНЕВНЫЙ БОНУС", color=COLORS["success"])
        embed.add_field(name="Деньги", value=f"**+{format_money(final_bonus)}**", inline=True)
        embed.add_field(name="Гемы", value=f"**+{gems}**", inline=True)
        embed.add_field(name="Серия", value=f"**{int(user.get('daily_streak', 1) or 1)} дней**", inline=True)
        embed.add_field(name="Следующий бонус", value=format_discord_deadline(now + timedelta(hours=cooldown_hours)), inline=False)
        embed.add_field(
            name="Окно серии",
            value="Серия не сбрасывается, если забирать `/daily` хотя бы раз в **48 часов**.",
            inline=False,
        )
        if streak_multiplier > 1:
            embed.add_field(name="Бонус серии", value="Это **7-й daily** в серии, поэтому денежная часть награды удвоена.", inline=False)
        if active_event:
            embed.add_field(name="Событие", value=f"`{active_event['name']}`", inline=False)
        embed.add_field(name="Новый баланс", value=f"**{format_money(user['balance'])}**", inline=False)
        if easter_lines:
            embed.add_field(name="Пасха 2026", value="\n".join(easter_lines), inline=False)
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(name="work", description="Поработать и заработать деньги")
    async def work(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Ошибка загрузки профиля.", ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        cooldown_minutes = int(10 * (1 - vip["cooldown_reduction"]))
        if user.get("last_work"):
            last_work = datetime.fromisoformat(user["last_work"]).replace(tzinfo=timezone.utc)
            if now - last_work < timedelta(minutes=cooldown_minutes):
                next_work_at = last_work + timedelta(minutes=cooldown_minutes)
                await interaction.response.send_message(f"Следующая работа будет доступна {format_discord_deadline(next_work_at)}.", ephemeral=True)
                return

        choices = random.sample(WORK_POOL, k=3)
        embed = discord.Embed(
            title="💼 Работа",
            description="Выбери одну из трёх безопасных подработок. Успех всегда 100%.",
            color=COLORS["success"],
        )
        for index, choice in enumerate(choices, start=1):
            embed.add_field(
                name=f"Вариант {index}",
                value=f"{choice['summary']}\nОплата: **{format_money(choice['reward_min'])} - {format_money(choice['reward_max'])}**",
                inline=False,
            )
        embed.set_footer(text="После выбора награда сразу зачислится на баланс.")
        view = WorkChoiceView(self, interaction.user.id, interaction.guild_id, choices)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="crime", description="Пойти на преступление ради денег")
    async def crime(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
            return
        now = datetime.now(timezone.utc)
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        cooldown_minutes = int(30 * (1 - vip["cooldown_reduction"]))
        if user.get("last_crime"):
            last_crime = datetime.fromisoformat(user["last_crime"]).replace(tzinfo=timezone.utc)
            if now - last_crime < timedelta(minutes=cooldown_minutes):
                next_crime_at = last_crime + timedelta(minutes=cooldown_minutes)
                await interaction.response.send_message(f"Следующая попытка будет доступна {format_discord_deadline(next_crime_at)}.", ephemeral=True)
                return

        choices = random.sample(CRIME_POOL, k=3)
        embed = discord.Embed(
            title="🕵️ Преступление",
            description="Выбери один из трёх рисковых вариантов. На кнопках ниже — только выбор, подробности здесь.",
            color=COLORS["error"],
        )
        for index, choice in enumerate(choices, start=1):
            embed.add_field(
                name=f"Риск {index}",
                value=(
                    f"{choice['summary']}\n"
                    f"Шанс успеха: **{int(choice['success_rate'] * 100)}%**\n"
                    f"Куш: **{format_money(choice['reward_min'])} - {format_money(choice['reward_max'])}**\n"
                    f"Штраф: **{format_money(choice['fine_min'])} - {format_money(choice['fine_max'])}**"
                ),
                inline=False,
            )
        embed.set_footer(text="Выбор фиксирует попытку и запускает кулдаун.")
        view = CrimeChoiceView(self, interaction.user.id, interaction.guild_id, choices)
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

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

            outcome = random.choice(SLUT_POOL)
            event_multiplier, active_event = self._market_multiplier(interaction.guild_id, "economy")

            if random.random() < float(outcome["success_rate"]):
                earnings = int(random.randint(int(outcome["reward_min"]), int(outcome["reward_max"])) * 1.2)
                if event_multiplier > 1:
                    earnings = int(earnings * event_multiplier)
                user["balance"] += earnings
                message = f"{outcome['success_text']}\n✅ Успех\n💵 Заработано: `{format_money(earnings)}`"
                color = COLORS["success"]
                reputation_penalty = 0
            else:
                shielded = has_active_shield(user)
                loss = 0 if shielded else min(random.randint(int(outcome["loss_min"]), int(outcome["loss_max"])), int(user.get("balance", 0) or 0))
                user["balance"] -= loss
                reputation_penalty = 0 if shielded else -4
                if shielded:
                    message = (
                        f"{outcome['fail_text']}\n"
                        "🛡️ Теневая страховка прикрыла провал\n"
                        f"🧾 Потеряно: `{format_money(0)}`\n"
                        "📉 Репутация: `0`"
                    )
                    color = COLORS["warning"]
                else:
                    message = (
                        f"{outcome['fail_text']}\n"
                        "❌ Не повезло\n"
                        f"🧾 Потеряно: `-{format_money(loss)}`\n"
                        "📉 Репутация: `-4`"
                    )
                    color = COLORS["error"]

            from easter_event import grant_easter_drops

            easter_cog = self.bot.get_cog("EasterEvent")
            easter_lines = grant_easter_drops(
                user,
                "slut",
                guild_state=easter_cog.get_cached_guild_state(interaction.guild_id) if easter_cog else None,
            )
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
                    reputation=reputation_penalty,
                )
            )

        event_note = f"\n🔥 Событие: `{active_event['name']}`" if active_event else ""
        embed = create_embed("🔥 РИСКОВАННАЯ РАБОТА", f"{message}\n\n💰 Баланс: `{format_money(user['balance'])}`{event_note}", color)
        embed.add_field(name="Снова доступно", value=format_discord_deadline(now + timedelta(minutes=cooldown_minutes)), inline=False)
        if easter_lines:
            embed.add_field(name="Пасха 2026", value="\n".join(easter_lines), inline=False)
        await interaction.edit_original_response(content=None, embed=embed)
        try:
            schedule_message_cleanup(await interaction.original_response())
        except Exception:
            pass

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
