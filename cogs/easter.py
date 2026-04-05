from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import ALLOWED_CHANNEL_ID, COLORS
from database import db, get_user_lock, supabase
from easter_event import (
    EASTER_ARCHIVE_CATEGORY,
    EASTER_CHEST_CODE,
    EASTER_COLLECTION_REQUIREMENTS,
    EASTER_EVENT_END_AT,
    EASTER_EXCHANGE_END_AT,
    EASTER_POND_PASS_CODE,
    EASTER_SHOP_CATEGORY_META,
    EASTER_SHOP_ITEMS,
    EASTER_TEMP_BUSINESSES,
    claim_collection,
    collection_can_claim,
    convert_inactive_easter_businesses_to_trophies,
    ensure_easter_state,
    get_collection_progress,
    get_easter_businesses,
    get_easter_counts,
    get_easter_phase,
    has_easter_furniture,
    migrate_legacy_easter_decor_inventory,
    open_easter_chest,
    rabbit_is_active,
    register_easter_fishing_content,
    sellback_eggs,
    upgrade_egg_currency,
    buy_easter_shop_item,
    collect_easter_businesses,
    easter_is_active,
)
from progression import unlock_theme, unlock_title
from utils import (
    check_channel,
    discord_timestamp,
    format_discord_deadline,
    normalize_datetime,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
)

RABBIT_DURATION = timedelta(minutes=15)
RABBIT_MIN_RESPAWN = timedelta(hours=4)
RABBIT_SPAWN_CHANCE = 0.10


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


class EasterView(discord.ui.View):
    def __init__(
        self,
        cog: "EasterCog",
        user_id: int,
        guild_id: int,
        *,
        section: str = "hub",
        selected_shop_code: str | None = None,
        selected_shop_category: str | None = None,
        selected_business_code: str | None = None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.section = section
        self.selected_shop_code = selected_shop_code or (EASTER_SHOP_ITEMS[0]["code"] if EASTER_SHOP_ITEMS else None)
        self.selected_shop_category = selected_shop_category or self.cog.normalize_shop_category(None, self.selected_shop_code)
        self.selected_business_code = selected_business_code or self.cog.normalize_business_code(None)
        self.message: discord.Message | None = None
        self._build_dynamic_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это пасхальное меню открыто не для тебя.", ephemeral=True)
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

    def _build_dynamic_items(self):
        if self.section == "shop":
            self.selected_shop_category = self.cog.normalize_shop_category(self.selected_shop_category, self.selected_shop_code)
            shop_items = self.cog.shop_items_for_category(self.selected_shop_category)
            selected_codes = {str(item["code"]) for item in shop_items}
            if self.selected_shop_code not in selected_codes and shop_items:
                self.selected_shop_code = str(shop_items[0]["code"])
            category_options = [
                discord.SelectOption(
                    label=str(meta["label"])[:100],
                    value=str(category_key),
                    description=str(meta["hint"])[:100],
                    default=str(category_key) == str(self.selected_shop_category),
                    emoji=str(meta.get("emoji") or None),
                )
                for category_key, meta in EASTER_SHOP_CATEGORY_META.items()
            ]
            self.shop_category_select = discord.ui.Select(placeholder="Категория магазина", row=1, options=category_options)
            self.shop_category_select.callback = self._on_shop_category_select
            self.add_item(self.shop_category_select)
            options = [
                discord.SelectOption(
                    label=str(item["name"])[:100],
                    value=str(item["code"]),
                    description=self.cog.describe_shop_price(item)[:100],
                    default=str(item["code"]) == str(self.selected_shop_code),
                    emoji=str(item.get("emoji") or None),
                )
                for item in shop_items[:25]
            ]
            self.shop_select = discord.ui.Select(placeholder="Выбери товар", row=1, options=options)
            self.shop_select.callback = self._on_shop_select
            self.shop_select.row = 2
            self.add_item(self.shop_select)
            self.buy_btn = discord.ui.Button(label="Купить", style=discord.ButtonStyle.success, row=2)
            self.buy_btn.callback = self._on_buy
            self.buy_btn.row = 3
            self.add_item(self.buy_btn)

        if self.section == "exchange":
            self.to_painted_btn = discord.ui.Button(label="25 🥚 → 1 🎨", style=discord.ButtonStyle.primary, row=1)
            self.to_gold_btn = discord.ui.Button(label="10 🎨 → 1 ✨", style=discord.ButtonStyle.primary, row=1)
            self.sellback_btn = discord.ui.Button(label="Сдать яйца в деньги", style=discord.ButtonStyle.secondary, row=2)
            self.to_painted_btn.callback = self._upgrade_to_painted
            self.to_gold_btn.callback = self._upgrade_to_gold
            self.sellback_btn.callback = self._sellback
            self.add_item(self.to_painted_btn)
            self.add_item(self.to_gold_btn)
            self.add_item(self.sellback_btn)

        if self.section == "collection":
            self.claim_btn = discord.ui.Button(label="Получить награду", style=discord.ButtonStyle.success, row=1)
            self.claim_btn.callback = self._claim_collection
            self.add_item(self.claim_btn)

        if self.section == "businesses":
            self.selected_business_code = self.cog.normalize_business_code(self.selected_business_code)
            business_items = self.cog.business_catalog_items()
            if business_items:
                business_options = [
                    discord.SelectOption(
                        label=str(item["name"])[:100],
                        value=str(item["code"]),
                        description=self.cog.describe_shop_price(item)[:100],
                        default=str(item["code"]) == str(self.selected_business_code),
                        emoji=str(item.get("emoji") or None),
                    )
                    for item in business_items[:25]
                ]
                self.business_select = discord.ui.Select(placeholder="Выбери пасхальный бизнес для покупки", row=2, options=business_options)
                self.business_select.callback = self._on_business_select
                self.add_item(self.business_select)
            self.buy_business_btn = discord.ui.Button(label="Купить бизнес", style=discord.ButtonStyle.success, row=3)
            self.buy_business_btn.callback = self._buy_business
            self.add_item(self.buy_business_btn)
            self.open_my_businesses_btn = discord.ui.Button(label="Мои бизнесы", style=discord.ButtonStyle.secondary, row=3)
            self.open_my_businesses_btn.callback = self._open_my_businesses
            self.add_item(self.open_my_businesses_btn)

        if self.section == "my_businesses":
            self.collect_business_btn = discord.ui.Button(label="Собрать доход", style=discord.ButtonStyle.success, row=3)
            self.collect_business_btn.callback = self._collect_businesses
            self.add_item(self.collect_business_btn)
            self.open_business_shop_btn = discord.ui.Button(label="Купить бизнес", style=discord.ButtonStyle.secondary, row=3)
            self.open_business_shop_btn.callback = self._open_business_shop
            self.add_item(self.open_business_shop_btn)

        self.shop_nav = discord.ui.Button(label="🛒 Магазин", style=discord.ButtonStyle.secondary, row=0)
        self.exchange_nav = discord.ui.Button(label="🔄 Обменник", style=discord.ButtonStyle.secondary, row=0)
        self.collection_nav = discord.ui.Button(label="🏆 Коллекция", style=discord.ButtonStyle.secondary, row=0)
        self.leaderboard_nav = discord.ui.Button(label="📊 Топ", style=discord.ButtonStyle.secondary, row=0)
        self.business_nav = discord.ui.Button(label="💼 Бизнесы", style=discord.ButtonStyle.secondary, row=0)
        self.my_business_nav = discord.ui.Button(label="🏪 Мои бизнесы", style=discord.ButtonStyle.secondary, row=4)
        self.shop_nav.callback = self._open_shop
        self.exchange_nav.callback = self._open_exchange
        self.collection_nav.callback = self._open_collection
        self.leaderboard_nav.callback = self._open_leaderboard
        self.business_nav.callback = self._open_businesses
        self.my_business_nav.callback = self._open_my_businesses
        self.add_item(self.shop_nav)
        self.add_item(self.exchange_nav)
        self.add_item(self.collection_nav)
        self.add_item(self.leaderboard_nav)
        self.add_item(self.business_nav)
        self.add_item(self.my_business_nav)
        self._sync_nav_styles()

    def _sync_nav_styles(self):
        self.shop_nav.style = discord.ButtonStyle.primary if self.section == "shop" else discord.ButtonStyle.secondary
        self.exchange_nav.style = discord.ButtonStyle.primary if self.section == "exchange" else discord.ButtonStyle.secondary
        self.collection_nav.style = discord.ButtonStyle.primary if self.section == "collection" else discord.ButtonStyle.secondary
        self.leaderboard_nav.style = discord.ButtonStyle.primary if self.section == "leaderboard" else discord.ButtonStyle.secondary
        self.business_nav.style = discord.ButtonStyle.primary if self.section == "businesses" else discord.ButtonStyle.secondary
        self.my_business_nav.style = discord.ButtonStyle.primary if self.section == "my_businesses" else discord.ButtonStyle.secondary

    async def _rerender(
        self,
        interaction: discord.Interaction,
        *,
        section: str | None = None,
        selected_shop_code: str | None = None,
        selected_shop_category: str | None = None,
        selected_business_code: str | None = None,
    ):
        target_section = section or self.section
        selected_code = selected_shop_code if selected_shop_code is not None else self.selected_shop_code
        category_key = selected_shop_category if selected_shop_category is not None else self.selected_shop_category
        business_code = selected_business_code if selected_business_code is not None else self.selected_business_code
        view = EasterView(
            self.cog,
            self.user_id,
            self.guild_id,
            section=target_section,
            selected_shop_code=selected_code,
            selected_shop_category=category_key,
            selected_business_code=business_code,
        )
        embed = await self.cog.build_embed(
            self.user_id,
            self.guild_id,
            section=target_section,
            selected_shop_code=selected_code,
            selected_shop_category=category_key,
            selected_business_code=business_code,
        )
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()

    async def _open_shop(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction, section="shop", selected_shop_category=self.selected_shop_category)

    async def _open_exchange(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction, section="exchange")

    async def _open_collection(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction, section="collection")

    async def _open_leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction, section="leaderboard")

    async def _open_businesses(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction, section="businesses", selected_business_code=self.selected_business_code)

    async def _open_my_businesses(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(interaction, section="my_businesses", selected_business_code=self.selected_business_code)

    async def _on_shop_select(self, interaction: discord.Interaction):
        selected = self.shop_select.values[0] if self.shop_select.values else self.selected_shop_code
        await interaction.response.defer()
        await self._rerender(
            interaction,
            section="shop",
            selected_shop_code=selected,
            selected_shop_category=self.selected_shop_category,
        )

    async def _on_shop_category_select(self, interaction: discord.Interaction):
        selected_category = self.shop_category_select.values[0] if self.shop_category_select.values else self.selected_shop_category
        items = self.cog.shop_items_for_category(selected_category)
        selected_code = str(items[0]["code"]) if items else self.selected_shop_code
        await interaction.response.defer()
        await self._rerender(
            interaction,
            section="shop",
            selected_shop_code=selected_code,
            selected_shop_category=selected_category,
        )

    async def _on_business_select(self, interaction: discord.Interaction):
        selected = self.business_select.values[0] if self.business_select.values else self.selected_business_code
        await interaction.response.defer()
        await self._rerender(interaction, section=self.section, selected_business_code=selected)

    async def _buy_business(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.buy_shop_item(self.user_id, self.guild_id, str(self.selected_business_code or ""))
        await self._rerender(
            interaction,
            section="businesses",
            selected_business_code=self.selected_business_code,
            selected_shop_category="business",
        )
        await interaction.followup.send(result, ephemeral=True)

    async def _on_buy(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.buy_shop_item(self.user_id, self.guild_id, str(self.selected_shop_code or ""))
        await self._rerender(
            interaction,
            section="shop",
            selected_shop_code=self.selected_shop_code,
            selected_shop_category=self.selected_shop_category,
        )
        await interaction.followup.send(result, ephemeral=True)

    async def _upgrade_to_painted(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.exchange_currency(self.user_id, self.guild_id, "painted")
        await self._rerender(interaction, section="exchange")
        await interaction.followup.send(result, ephemeral=True)

    async def _upgrade_to_gold(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.exchange_currency(self.user_id, self.guild_id, "gold")
        await self._rerender(interaction, section="exchange")
        await interaction.followup.send(result, ephemeral=True)

    async def _sellback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.sellback_currency(self.user_id, self.guild_id)
        await self._rerender(interaction, section="exchange")
        await interaction.followup.send(result, ephemeral=True)

    async def _claim_collection(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.claim_collection_reward(self.user_id, self.guild_id)
        await self._rerender(interaction, section="collection")
        await interaction.followup.send(result, ephemeral=True)

    async def _open_business_shop(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self._rerender(
            interaction,
            section="businesses",
            selected_business_code=self.selected_business_code,
        )

    async def _collect_businesses(self, interaction: discord.Interaction):
        await interaction.response.defer()
        result = await self.cog.collect_business_rewards(self.user_id, self.guild_id)
        await self._rerender(
            interaction,
            section="my_businesses",
            selected_shop_category=self.selected_shop_category,
            selected_business_code=self.selected_business_code,
        )
        await interaction.followup.send(result, ephemeral=True)


class EasterCog(commands.Cog, name="EasterEvent"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._guild_state_cache: dict[int, dict[str, Any]] = {}
        register_easter_fishing_content()
        self.rabbit_loop.start()

    def cog_unload(self):
        self.rabbit_loop.cancel()

    def get_cached_guild_state(self, guild_id: int) -> dict[str, Any]:
        return self._guild_state_cache.get(guild_id, {"guild_id": guild_id, "phase": get_easter_phase()})

    async def _refresh_guild_state(self, guild_id: int) -> dict[str, Any]:
        state = await db.get_easter_guild_state(guild_id)
        state["phase"] = get_easter_phase()
        self._guild_state_cache[guild_id] = state
        return state

    async def _save_guild_state(self, guild_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        state = {**self.get_cached_guild_state(guild_id), **payload, "phase": get_easter_phase()}
        self._guild_state_cache[guild_id] = state
        await db.upsert_easter_guild_state(guild_id, state)
        return state

    def describe_shop_price(self, item: dict[str, Any]) -> str:
        parts: list[str] = []
        if int(item.get("price_common", 0) or 0) > 0:
            parts.append(f"{int(item['price_common'])} 🥚")
        if int(item.get("price_painted", 0) or 0) > 0:
            parts.append(f"{int(item['price_painted'])} 🎨")
        if int(item.get("price_gold", 0) or 0) > 0:
            parts.append(f"{int(item['price_gold'])} ✨")
        if int(item.get("money_price", 0) or 0) > 0:
            parts.append(format_money(int(item["money_price"])))
        return " + ".join(parts) or "Бесплатно"

    def shop_category_key(self, item: dict[str, Any]) -> str:
        category = str(item.get("category") or "")
        if category in EASTER_SHOP_CATEGORY_META:
            return category
        kind = str(item.get("kind") or "")
        kind_map = {
            "case": "loot",
            "bait": "loot",
            "pass": "loot",
            "theme": "profile",
            "title": "profile",
            "furniture": "decor",
            "business": "business",
        }
        return kind_map.get(kind, "loot")

    def normalize_shop_category(self, category: str | None, selected_shop_code: str | None = None) -> str:
        if str(category or "") in EASTER_SHOP_CATEGORY_META:
            return str(category)
        if selected_shop_code:
            selected = next((item for item in EASTER_SHOP_ITEMS if str(item.get("code")) == str(selected_shop_code)), None)
            if selected is not None:
                return self.shop_category_key(selected)
        return next(iter(EASTER_SHOP_CATEGORY_META))

    def shop_items_for_category(self, category: str | None) -> list[dict[str, Any]]:
        normalized = self.normalize_shop_category(category)
        items = [item for item in EASTER_SHOP_ITEMS if self.shop_category_key(item) == normalized]
        return items or list(EASTER_SHOP_ITEMS)

    def business_catalog_items(self) -> list[dict[str, Any]]:
        return [
            item
            for item in EASTER_SHOP_ITEMS
            if str(item.get("kind") or "") == "business" and str(item.get("code") or "") in EASTER_TEMP_BUSINESSES
        ]

    def normalize_business_code(self, business_code: str | None) -> str | None:
        items = self.business_catalog_items()
        if not items:
            return None
        valid_codes = {str(item["code"]) for item in items}
        if str(business_code or "") in valid_codes:
            return str(business_code)
        return str(items[0]["code"])

    def business_runtime_snapshot(
        self,
        user: dict[str, Any],
        business_key: str,
        owned_payload: dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        business = EASTER_TEMP_BUSINESSES.get(str(business_key), {})
        current_time = now or datetime.now(timezone.utc)
        cycle_hours = max(1, int(business.get("cycle_hours", 1) or 1))
        cycles_per_day = 24 / cycle_hours
        money_multiplier = 1.05 if has_easter_furniture(user, "easter_rabbit_lamp") else 1.0
        reward_money = int(round(int(business.get("income_money", 0) or 0) * money_multiplier))
        common_min, common_max = business.get("income_common", (0, 0))
        common_min = int(common_min or 0)
        common_max = int(common_max or 0)
        daily_money = int(round(reward_money * cycles_per_day))
        daily_common_min = int(round(common_min * cycles_per_day))
        daily_common_max = int(round(common_max * cycles_per_day))
        painted_chance = int(round(float(business.get("painted_chance", 0.0) or 0.0) * 100))
        owned_at = normalize_datetime(owned_payload.get("owned_at")) if isinstance(owned_payload, dict) else None
        last_collect = normalize_datetime(owned_payload.get("last_collect") or owned_payload.get("owned_at")) if isinstance(owned_payload, dict) else None
        ready_at = last_collect + timedelta(hours=cycle_hours) if last_collect is not None else None
        ready = ready_at is None or ready_at <= current_time if isinstance(owned_payload, dict) else False
        return {
            "reward_money": reward_money,
            "common_min": common_min,
            "common_max": common_max,
            "cycle_hours": cycle_hours,
            "cycles_per_day": cycles_per_day,
            "daily_money": daily_money,
            "daily_common_min": daily_common_min,
            "daily_common_max": daily_common_max,
            "painted_chance": painted_chance,
            "owned_at": owned_at,
            "last_collect": last_collect,
            "ready_at": ready_at,
            "ready": ready,
        }

    def describe_shop_item(self, item: dict[str, Any]) -> str:
        code = str(item.get("code") or "")
        kind = str(item.get("kind") or "")
        code_descriptions = {
            "easter_case_basic": "Открывается через инвентарь и может принести деньги, яйца, декор и редкие пасхальные награды.",
            "easter_bait_pack": "Даёт набор праздничной наживки. Используй предмет через `/inventory`, чтобы получить заряды наживки.",
            EASTER_POND_PASS_CODE: "Открывает доступ к Пруду золотого кролика, где ловится ивентовая рыба, яйца и сундуки.",
            "easter_profile_theme": "После использования через `/inventory` открывает и сразу активирует мятную пасхальную тему профиля.",
            "easter_profile_title": "После использования через `/inventory` открывает пасхальный титул для профиля.",
            "easter_egg_basket": "Декор дома: повышает шанс выпадения яиц на 5% во время ивента.",
            "easter_rabbit_lamp": "Декор дома: даёт +5% к доходу пасхальных бизнесов во время ивента.",
            "easter_chocolate_fountain": "Декор дома: даёт +5% к денежной награде из `/work` во время ивента.",
            "easter_bakery": "Временный бизнес: приносит немного денег и пасхальные яйца, а после ивента превращается в трофей.",
            "easter_chocolate_lab": "Продвинутый временный бизнес: приносит больше денег, яиц и может дать расписное яйцо. После ивента становится трофеем.",
        }
        if code in code_descriptions:
            return code_descriptions[code]
        descriptions = {
            "case": "Кейс с валютой, декором и редкими пасхальными наградами.",
            "bait": "Набор праздничной наживки для обычной рыбалки и пасхального пруда.",
            "pass": "Открывает доступ к Пруду золотого кролика на время ивента.",
            "theme": "Косметический фон профиля в пасхальном стиле.",
            "title": "Статусный пасхальный титул для профиля.",
            "furniture": "Домашний декор с пассивным бонусом на время ивента.",
            "business": "Временный бизнес с пассивным доходом и дропом яиц.",
        }
        return descriptions.get(kind, "Пасхальный предмет из временного магазина.")

    async def build_leaderboard_payload(self, guild_id: int) -> dict[str, list[str]]:
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("users").select("user_id,game_stats").eq("guild_id", guild_id).execute()
            )
            rows = result.data or []
        except Exception:
            fallback = ["Не удалось загрузить топ."]
            return {"common": fallback, "gold": fallback, "pond": fallback}

        entries: list[dict[str, int]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            game_stats = row.get("game_stats")
            systems = game_stats.get("_systems") if isinstance(game_stats, dict) else {}
            easter_state = systems.get("easter_2026") if isinstance(systems, dict) else {}
            if not isinstance(easter_state, dict):
                continue
            user_id = int(row.get("user_id") or 0)
            if user_id <= 0:
                continue
            entries.append(
                {
                    "user_id": user_id,
                    "common": int(easter_state.get("eggs_found_common", 0) or 0),
                    "gold": int(easter_state.get("eggs_found_gold", 0) or 0),
                    "pond": int(easter_state.get("rabbit_pond_catches", 0) or 0),
                }
            )

        def _top_lines(key: str, icon: str) -> list[str]:
            ranked = [entry for entry in entries if int(entry.get(key, 0) or 0) > 0]
            ranked.sort(key=lambda entry: int(entry.get(key, 0) or 0), reverse=True)
            if not ranked:
                return ["Пока никто не вышел в топ."]
            return [
                f"**{index}.** <@{entry['user_id']}> • {icon} **{int(entry.get(key, 0) or 0)}**"
                for index, entry in enumerate(ranked[:5], start=1)
            ]

        return {
            "common": _top_lines("common", "🥚"),
            "gold": _top_lines("gold", "✨"),
            "pond": _top_lines("pond", "🎣"),
        }

    async def build_embed(
        self,
        user_id: int,
        guild_id: int,
        *,
        section: str = "hub",
        selected_shop_code: str | None = None,
        selected_shop_category: str | None = None,
        selected_business_code: str | None = None,
    ) -> discord.Embed:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return discord.Embed(title="Пасха 2026", description="Не удалось загрузить профиль.", color=COLORS["warning"])
            migrated_decor = migrate_legacy_easter_decor_inventory(user)
            converted = convert_inactive_easter_businesses_to_trophies(user)
            if migrated_decor or converted:
                await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {}), "balance": user.get("balance", 0), "gems": user.get("gems", 0)})
            easter_state = ensure_easter_state(user)
            counts = get_easter_counts(user)
            guild_state = await self._refresh_guild_state(guild_id)

        phase = get_easter_phase()
        rabbit_active = rabbit_is_active(guild_state)
        end_target = EASTER_EVENT_END_AT if phase == "active" else EASTER_EXCHANGE_END_AT
        base_description = (
            f"Фаза: **{phase}**\n"
            f"До конца: {format_discord_deadline(end_target)}\n"
            f"Золотой кролик: **{'активен' if rabbit_active else 'не активен'}**"
        )

        if section == "shop":
            embed = discord.Embed(title="🐰 Пасхальный магазин", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
            normalized_category = self.normalize_shop_category(selected_shop_category, selected_shop_code)
            category_meta = EASTER_SHOP_CATEGORY_META[normalized_category]
            category_items = self.shop_items_for_category(normalized_category)
            selected = next((item for item in category_items if item["code"] == selected_shop_code), category_items[0])
            category_lines = [
                f"{'→' if key == normalized_category else '•'} {meta['emoji']} **{meta['label']}**"
                for key, meta in EASTER_SHOP_CATEGORY_META.items()
            ]
            section_lines = [
                f"{item['emoji']} **{item['name']}** — {self.describe_shop_price(item)}"
                for item in category_items[:6]
            ]
            embed.add_field(name="Кошелёк яиц", value=f"🥚 **{counts['common']}**\n🎨 **{counts['painted']}**\n✨ **{counts['gold']}**", inline=True)
            embed.add_field(name="Баланс", value=f"💰 **{format_money(int(user.get('balance', 0) or 0))}**", inline=True)
            embed.add_field(
                name="Категории",
                value="\n".join(category_lines),
                inline=False,
            )
            embed.add_field(
                name=f"{category_meta['emoji']} {category_meta['label']}",
                value="\n".join(section_lines) if section_lines else "В этой категории пока нет товаров.",
                inline=False,
            )
            embed.add_field(
                name=f"Выбранный товар: {selected['emoji']} {selected['name']}",
                value=(
                    f"Цена: **{self.describe_shop_price(selected)}**\n"
                    f"{self.describe_shop_item(selected)}"
                ),
                inline=False,
            )
            embed.set_footer(text="Магазин работает только в фазе active.")
            return embed

        if section == "exchange":
            embed = discord.Embed(title="🔄 Пасхальный обменник", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
            embed.add_field(name="У тебя сейчас", value=f"🥚 **{counts['common']}**\n🎨 **{counts['painted']}**\n✨ **{counts['gold']}**", inline=True)
            embed.add_field(name="Апгрейд", value="`25` 🥚 → `1` 🎨\n`10` 🎨 → `1` ✨", inline=True)
            embed.add_field(name="Выкуп", value="Во время `exchange` яйца можно сдать боту:\n🥚 `$300`\n🎨 `$4,000`\n✨ `$35,000`", inline=False)
            return embed

        if section == "collection":
            progress = get_collection_progress(user)
            item_meta = {
                EASTER_COLLECTION_REQUIREMENTS[0]: "🥚 Обычное яйцо",
                EASTER_COLLECTION_REQUIREMENTS[1]: "🎨 Расписное яйцо",
                EASTER_COLLECTION_REQUIREMENTS[2]: "✨ Золотое яйцо",
                EASTER_COLLECTION_REQUIREMENTS[3]: "📦 Пасхальный сундук",
                EASTER_COLLECTION_REQUIREMENTS[4]: "🐇 Кроличий талисман",
            }
            lines = []
            for code in EASTER_COLLECTION_REQUIREMENTS:
                icon = "✅" if progress.get(code) else "❌"
                lines.append(f"{icon} {item_meta.get(code, code)}")
            embed = discord.Embed(title="🏆 Пасхальная коллекция", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
            embed.add_field(name="Нужно собрать", value="\n".join(lines), inline=False)
            embed.add_field(
                name="Награда",
                value="Легендарный титул, редкий фон, гемы и вечный пасхальный трофей.",
                inline=False,
            )
            embed.add_field(
                name="Подсказка",
                value="🐇 Кроличий талисман падает из пасхальных сундуков с шансом 8%. Сам сундук для коллекции теперь засчитывается в момент получения, даже если ты его потом открыл.",
                inline=False,
            )
            embed.add_field(
                name="Статус",
                value="Награда уже забрана." if bool(easter_state.get("collection_reward_claimed")) else ("Можно забирать." if collection_can_claim(user) else "Пока не хватает предметов."),
                inline=False,
            )
            return embed

        if section == "businesses":
            embed = discord.Embed(title="💼 Пасхальные бизнесы", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
            businesses = get_easter_businesses(user)
            business_items = self.business_catalog_items()
            selected_code = self.normalize_business_code(selected_business_code)
            selected_item = next((item for item in business_items if str(item["code"]) == str(selected_code)), business_items[0] if business_items else None)
            owned_codes = {str(key) for key, value in businesses.items() if isinstance(value, dict)} if isinstance(businesses, dict) else set()
            now = datetime.now(timezone.utc)
            lamp_active = has_easter_furniture(user, "easter_rabbit_lamp")

            catalog_lines: list[str] = []
            for item in business_items:
                business_key = str(item["code"])
                snapshot = self.business_runtime_snapshot(user, business_key, businesses.get(business_key) if isinstance(businesses, dict) else None, now=now)
                status_icon = "✅" if business_key in owned_codes else "🛒"
                catalog_lines.append(
                    f"{status_icon} {item['emoji']} **{item['name']}** — {self.describe_shop_price(item)}\n"
                    f"Доход: **{format_money(snapshot['reward_money'])}/цикл** • **{format_money(snapshot['daily_money'])}/сутки**"
                )

            embed.add_field(name="Кошелёк яиц", value=f"🥚 **{counts['common']}**\n🎨 **{counts['painted']}**\n✨ **{counts['gold']}**", inline=True)
            embed.add_field(name="Баланс", value=f"💰 **{format_money(int(user.get('balance', 0) or 0))}**", inline=True)
            embed.add_field(name="Статус", value=f"Куплено: **{len(owned_codes)}/{len(business_items)}**\nЛампа: **{'активна' if lamp_active else 'не активна'}**", inline=True)
            embed.add_field(
                name="Витрина бизнеса",
                value="\n\n".join(catalog_lines) if catalog_lines else "В этой категории пока нет пасхальных бизнесов.",
                inline=False,
            )

            if selected_item is not None:
                business_key = str(selected_item["code"])
                owned_payload = businesses.get(business_key) if isinstance(businesses, dict) else None
                snapshot = self.business_runtime_snapshot(user, business_key, owned_payload, now=now)
                cycles_per_day = f"{snapshot['cycles_per_day']:g}"
                detail_lines = [
                    f"Статус: **{'уже куплен' if isinstance(owned_payload, dict) else 'доступен к покупке'}**",
                    f"Цена: **{self.describe_shop_price(selected_item)}**",
                    f"Деньги: **{format_money(snapshot['reward_money'])} / цикл** • **{format_money(snapshot['daily_money'])} / сутки**",
                    f"Обычные яйца: **{snapshot['common_min']}-{snapshot['common_max']} / цикл** • **{snapshot['daily_common_min']}-{snapshot['daily_common_max']} / сутки**",
                    f"Шанс расписного яйца: **{snapshot['painted_chance']}% за цикл**",
                    f"Цикл сбора: **каждые {snapshot['cycle_hours']} ч** • **{cycles_per_day} цикла/сутки**",
                    self.describe_shop_item(selected_item),
                ]
                if isinstance(owned_payload, dict):
                    detail_lines.append(
                        f"Сейчас: **{'можно собирать' if snapshot['ready'] else format_discord_deadline(snapshot['ready_at'])}**"
                    )
                if lamp_active:
                    detail_lines.append("Бонус лампы: **+5% к денежной награде уже учтены**.")
                embed.add_field(
                    name=f"Покупка: {selected_item['emoji']} {selected_item['name']}",
                    value="\n".join(detail_lines),
                    inline=False,
                )

            embed.set_footer(text="Здесь только покупка пасхальных бизнесов. Управление и сбор дохода находятся во вкладке «Мои бизнесы».")
            return embed

        if section == "my_businesses":
            embed = discord.Embed(title="🏪 Мои пасхальные бизнесы", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
            businesses = get_easter_businesses(user)
            business_items = self.business_catalog_items()
            now = datetime.now(timezone.utc)
            lamp_active = has_easter_furniture(user, "easter_rabbit_lamp")

            total_owned = 0
            total_ready = 0
            total_cycle_money = 0
            total_daily_money = 0
            total_common_min = 0
            total_common_max = 0
            owned_blocks: list[str] = []

            for item in business_items:
                business_key = str(item["code"])
                owned_payload = businesses.get(business_key) if isinstance(businesses, dict) else None
                if not isinstance(owned_payload, dict):
                    continue
                snapshot = self.business_runtime_snapshot(user, business_key, owned_payload, now=now)
                total_owned += 1
                total_cycle_money += int(snapshot["reward_money"])
                total_daily_money += int(snapshot["daily_money"])
                total_common_min += int(snapshot["common_min"])
                total_common_max += int(snapshot["common_max"])
                if snapshot["ready"]:
                    total_ready += 1
                cycles_per_day = f"{snapshot['cycles_per_day']:g}"
                status_text = "✅ Можно собирать" if snapshot["ready"] else f"⏳ Готов {discord_timestamp(snapshot['ready_at'], 'R')}"
                owned_blocks.append(
                    f"{item['emoji']} **{item['name']}**\n"
                    f"{status_text}\n"
                    f"Деньги: **{format_money(snapshot['reward_money'])} / цикл** • **{format_money(snapshot['daily_money'])} / сутки**\n"
                    f"Обычные яйца: **{snapshot['common_min']}-{snapshot['common_max']} / цикл** • **{snapshot['daily_common_min']}-{snapshot['daily_common_max']} / сутки**\n"
                    f"Расписное яйцо: **{snapshot['painted_chance']}% за цикл**\n"
                    f"Цикл: **каждые {snapshot['cycle_hours']} ч** • **{cycles_per_day} цикла/сутки**\n"
                    f"Куплен: **{discord_timestamp(owned_payload.get('owned_at'), 'R')}**"
                )

            embed.add_field(name="Кошелёк яиц", value=f"🥚 **{counts['common']}**\n🎨 **{counts['painted']}**\n✨ **{counts['gold']}**", inline=True)
            embed.add_field(name="Баланс", value=f"💰 **{format_money(int(user.get('balance', 0) or 0))}**", inline=True)
            embed.add_field(
                name="Сводка",
                value=(
                    f"Куплено: **{total_owned}/{len(business_items)}**\n"
                    f"Готово к сбору: **{total_ready}**\n"
                    f"Пассив/сутки: **{format_money(total_daily_money)}**"
                ),
                inline=True,
            )
            embed.add_field(
                name="Мой портфель",
                value="\n\n".join(owned_blocks) if owned_blocks else "У тебя пока нет пасхальных бизнесов. Открой вкладку «Бизнесы» и купи первый.",
                inline=False,
            )
            cycle_summary = (
                f"За полный цикл всех бизнесов: **{format_money(total_cycle_money)}** и **{total_common_min}-{total_common_max} 🥚**."
                if total_owned > 0
                else "Дохода пока нет: сначала купи хотя бы один пасхальный бизнес."
            )
            embed.add_field(name="Общий цикл", value=cycle_summary, inline=False)
            if lamp_active:
                embed.add_field(name="Бонус дома", value="🐰 Кроличья лампа активна и уже даёт **+5% к денежной награде** каждого пасхального бизнеса.", inline=False)
            embed.set_footer(text="Кнопка «Собрать доход» забирает награды сразу со всех готовых пасхальных бизнесов.")
            return embed

        if section == "leaderboard":
            tops = await self.build_leaderboard_payload(guild_id)
            embed = discord.Embed(title="📊 Пасхальный топ", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
            embed.add_field(name="🥚 Больше всего яиц", value="\n".join(tops["common"]), inline=False)
            embed.add_field(name="✨ Шейхи золотых яиц", value="\n".join(tops["gold"]), inline=False)
            embed.add_field(name="🎣 Лучшие рыбаки пруда", value="\n".join(tops["pond"]), inline=False)
            return embed

        businesses = get_easter_businesses(user)
        business_lines = []
        for business_key, payload in businesses.items():
            business = next((item for item in EASTER_SHOP_ITEMS if item["code"] == business_key), None)
            if business is None:
                continue
            business_lines.append(f"{business['emoji']} **{business['name']}**")
        if not business_lines:
            business_lines.append("Пасхальных бизнесов пока нет.")

        progress = get_collection_progress(user)
        collection_ready = sum(1 for value in progress.values() if value)
        embed = discord.Embed(title="🐰 Пасха 2026", description=base_description, color=COLORS["easter"], timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Яйца в инвентаре", value=f"🥚 **{counts['common']}**\n🎨 **{counts['painted']}**\n✨ **{counts['gold']}**", inline=True)
        embed.add_field(
            name="Коллекция",
            value=f"Собрано: **{collection_ready}/{len(EASTER_COLLECTION_REQUIREMENTS)}**\nНаграда: **{'забрана' if easter_state.get('collection_reward_claimed') else 'не забрана'}**",
            inline=True,
        )
        embed.add_field(name="Пасхальные бизнесы", value="\n".join(business_lines[:4]), inline=False)
        if rabbit_active:
            active_until = guild_state.get("rabbit_active_until")
            if active_until:
                embed.add_field(name="Золотой кролик", value=f"Сейчас активен до {discord_timestamp(active_until, 'R')}.", inline=False)
        if converted:
            embed.add_field(name="Трофеи после ивента", value="Преобразованы в трофеи: " + ", ".join(converted), inline=False)
        if phase == "off":
            embed.set_footer(text=f"Ивент закрыт. Мёртвые предметы ушли в {EASTER_ARCHIVE_CATEGORY}.")
        return embed

    async def buy_shop_item(self, user_id: int, guild_id: int, item_code: str) -> str:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return "Не удалось загрузить профиль."
            ok, message = buy_easter_shop_item(user, item_code)
            if not ok:
                return message
            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user.get("balance", 0),
                    "gems": user.get("gems", 0),
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )
            return message

    async def exchange_currency(self, user_id: int, guild_id: int, tier: str) -> str:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return "Не удалось загрузить профиль."
            ok, message = upgrade_egg_currency(user, tier)
            if not ok:
                return message
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
            return message

    async def sellback_currency(self, user_id: int, guild_id: int) -> str:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return "Не удалось загрузить профиль."
            ok, payload = sellback_eggs(user)
            if not ok:
                return str(payload["message"])
            await db.update_user(user_id, guild_id, {"balance": user.get("balance", 0), "inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
            return (
                f"Выкуп завершён.\n"
                f"🥚 Сдано: **{payload['common']}**\n"
                f"🎨 Сдано: **{payload['painted']}**\n"
                f"✨ Сдано: **{payload['gold']}**\n"
                f"💰 Получено: **{format_money(payload['money'])}**"
            )

    async def claim_collection_reward(self, user_id: int, guild_id: int) -> str:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return "Не удалось загрузить профиль."
            if not claim_collection(user):
                return "Коллекция пока не готова или награда уже забрана."
            user["gems"] = int(user.get("gems", 0) or 0) + 125
            unlock_title(user, "tideborn")
            unlock_theme(user, "royal")
            add_general_item = __import__("inventory_system").add_general_item
            add_general_item(
                user,
                item_type="event_trophy",
                code="easter_collection_grand_trophy",
                name="Вечный пасхальный декор",
                emoji="🌸",
                description="Уникальный декор за полную Пасхальную коллекцию 2026.",
                quantity=1,
                payload={"event_key": "easter_2026", "archive": False},
                stackable=False,
            )
            await db.update_user(user_id, guild_id, {"gems": user.get("gems", 0), "inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
            return "Коллекция закрыта. Получены: **125 гемов**, титул, фон и уникальный пасхальный декор."

    async def collect_business_rewards(self, user_id: int, guild_id: int) -> str:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return "Не удалось загрузить профиль."
            ok, payload = collect_easter_businesses(user)
            if not ok:
                return str(payload["message"])
            await db.update_user(user_id, guild_id, {"balance": user.get("balance", 0), "inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
            extra = f"\n🎨 Расписных яиц: **+{payload['painted']}**" if int(payload["painted"]) > 0 else ""
            return (
                "\n".join(payload["lines"])
                + f"\n\n💰 Деньги: **+{format_money(payload['money'])}**\n🥚 Обычных яиц: **+{payload['common']}**{extra}"
            )

    @tasks.loop(minutes=5)
    async def rabbit_loop(self):
        if not self.bot.is_ready():
            return
        for guild in list(self.bot.guilds):
            await self._tick_guild_rabbit(guild)

    @rabbit_loop.before_loop
    async def before_rabbit_loop(self):
        await self.bot.wait_until_ready()

    async def _tick_guild_rabbit(self, guild: discord.Guild):
        now = datetime.now(timezone.utc)
        state = await self._refresh_guild_state(guild.id)
        phase = get_easter_phase(now)

        if phase != "active":
            if state.get("active_rabbit_event_id") or state.get("rabbit_active_until"):
                await self._save_guild_state(
                    guild.id,
                    {
                        "active_rabbit_event_id": None,
                        "rabbit_active_until": None,
                        "rabbit_last_announce_message_id": state.get("rabbit_last_announce_message_id"),
                    },
                )
            return

        if rabbit_is_active(state, now):
            return

        raw_last_spawn = state.get("rabbit_last_spawn_at")
        last_spawn = None
        if raw_last_spawn:
            try:
                parsed = datetime.fromisoformat(str(raw_last_spawn))
                last_spawn = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
                last_spawn = last_spawn.astimezone(timezone.utc)
            except ValueError:
                last_spawn = None
        if last_spawn and now - last_spawn < RABBIT_MIN_RESPAWN:
            return
        if random.random() > RABBIT_SPAWN_CHANCE:
            return

        channel = guild.get_channel(ALLOWED_CHANNEL_ID)
        announce_message_id = None
        if isinstance(channel, discord.TextChannel):
            try:
                embed = discord.Embed(
                    title="🐇 На сервере заметили Золотого кролика!",
                    description="Следующие **15 минут** из активностей чаще падают яйца, сундуки и редкий пасхальный лут.",
                    color=COLORS["easter"],
                    timestamp=now,
                )
                message = await channel.send(embed=embed)
                announce_message_id = message.id
            except Exception:
                announce_message_id = None

        await self._save_guild_state(
            guild.id,
            {
                "active_rabbit_event_id": f"{guild.id}-{int(now.timestamp())}",
                "rabbit_active_until": (now + RABBIT_DURATION).isoformat(),
                "rabbit_last_spawn_at": now.isoformat(),
                "rabbit_last_announce_message_id": announce_message_id,
            },
        )

    @app_commands.command(name="easter", description="Открыть пасхальный ивент 2026")
    async def easter(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return
        view = EasterView(self, interaction.user.id, interaction.guild_id, section="hub")
        embed = await self.build_embed(interaction.user.id, interaction.guild_id, section="hub")
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()


async def setup(bot: commands.Bot):
    await bot.add_cog(EasterCog(bot))
