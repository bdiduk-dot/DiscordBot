from __future__ import annotations

import asyncio
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.bank import add_bank_entry
from config import COLORS
from database import db, get_user_lock
from inventory_system import (
    extract_fish_item,
    extract_general_item,
    find_fish_item,
    find_general_item,
    restore_fish_item,
    restore_general_item,
)
from utils import (
    check_channel,
    format_discord_deadline,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
)

DURATIONS = {6, 24, 48}


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _listing_item_name(listing: dict[str, Any]) -> str:
    payload = listing.get("item_payload") if isinstance(listing.get("item_payload"), dict) else {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    return str(item.get("name") or listing.get("title") or "Лот")


def _listing_item_emoji(listing: dict[str, Any]) -> str:
    payload = listing.get("item_payload") if isinstance(listing.get("item_payload"), dict) else {}
    item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    return str(item.get("emoji") or "🪙")


def _is_fixed_listing(listing: dict[str, Any]) -> bool:
    return str(listing.get("listing_type") or "fixed_price") == "fixed_price"


def _supports_auction(listing: dict[str, Any]) -> bool:
    return not _is_fixed_listing(listing)


@asynccontextmanager
async def _user_locks(*user_ids: int):
    ordered_ids = sorted({int(user_id) for user_id in user_ids if int(user_id or 0) > 0})
    locks = [get_user_lock(user_id) for user_id in ordered_ids]
    for lock in locks:
        await lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            try:
                lock.release()
            except RuntimeError:
                pass


class AuctionCreateModal(discord.ui.Modal):
    def __init__(self, view: "AuctionView"):
        super().__init__(title="Создать лот")
        self.auction_view = view
        self.item_id = discord.ui.TextInput(label="ID предмета", placeholder="Например: 152", max_length=12)
        self.mode = discord.ui.TextInput(label="Режим", placeholder="fixed или auction", max_length=12)
        self.price = discord.ui.TextInput(label="Цена / старт", placeholder="Например: 25000", max_length=12)
        self.duration = discord.ui.TextInput(label="Длительность", placeholder="6 / 24 / 48", max_length=4)
        self.buyout = discord.ui.TextInput(label="Buyout (необязательно)", placeholder="Пусто или сумма", required=False, max_length=12)
        for item in (self.item_id, self.mode, self.price, self.duration, self.buyout):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await self.auction_view.handle_create_modal(interaction, self)


class AuctionBidModal(discord.ui.Modal):
    def __init__(self, view: "AuctionView"):
        super().__init__(title="Сделка с лотом")
        self.auction_view = view
        self.amount = discord.ui.TextInput(label="Сумма ставки", placeholder="Например: 35000", max_length=12)
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        await self.auction_view.handle_bid_modal(interaction, self)


class AuctionView(discord.ui.View):
    def __init__(self, cog: "AuctionCog", user_id: int, guild_id: int, *, scope: str = "all", page: int = 0):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.scope = scope
        self.page = page
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню аукциона открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _refresh(self, interaction: discord.Interaction):
        embed, listings = await self.cog.build_auction_embed(self.user_id, self.guild_id, scope=self.scope, page=self.page)
        self.sync_buttons(listings)
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)

    def _current_listing(self, listings: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not listings:
            return None
        if self.page >= len(listings):
            self.page = max(0, len(listings) - 1)
        return listings[self.page] if 0 <= self.page < len(listings) else None

    def sync_buttons(self, listings: list[dict[str, Any]]):
        current = self._current_listing(listings)
        total = len(listings)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max(0, total - 1)
        self.page_btn.label = f"{self.page + 1}/{max(1, total)}"
        if current is None:
            self.main_action_btn.disabled = True
            self.buyout_btn.disabled = True
            self.cancel_btn.disabled = True
            self.main_action_btn.label = "Нет лота"
            return
        self.main_action_btn.disabled = False
        self.main_action_btn.label = "Купить" if _is_fixed_listing(current) else "Ставка"
        self.buyout_btn.disabled = not (_supports_auction(current) and int(current.get("buyout_price") or 0) > 0)
        self.cancel_btn.disabled = not (
            int(current.get("seller_id", 0) or 0) == self.user_id
            and int(current.get("bid_count", 0) or 0) <= 0
            and str(current.get("status") or "") == "active"
        )

    async def handle_create_modal(self, interaction: discord.Interaction, modal: AuctionCreateModal):
        async with self._view_lock:
            try:
                item_id = int(str(modal.item_id.value).strip())
                price = int(str(modal.price.value).strip().replace(",", ""))
                duration = int(str(modal.duration.value).strip())
            except ValueError:
                await interaction.response.send_message("Проверь ID предмета, цену и длительность.", ephemeral=True)
                return
            mode = str(modal.mode.value).strip().lower()
            raw_buyout = str(modal.buyout.value).strip().replace(",", "")
            buyout_price = int(raw_buyout) if raw_buyout.isdigit() else None
            success, payload = await self.cog.create_listing(
                self.user_id,
                self.guild_id,
                item_id=item_id,
                mode=mode,
                price=price,
                duration_hours=duration,
                buyout_price=buyout_price,
            )
            if isinstance(payload, discord.Embed):
                await interaction.response.send_message(embed=payload, ephemeral=True)
            else:
                await interaction.response.send_message(str(payload), ephemeral=True)
            if success and self.message is not None:
                await self._refresh(interaction)

    async def handle_bid_modal(self, interaction: discord.Interaction, modal: AuctionBidModal):
        async with self._view_lock:
            try:
                amount = int(str(modal.amount.value).strip().replace(",", ""))
            except ValueError:
                await interaction.response.send_message("Сумма ставки должна быть числом.", ephemeral=True)
                return
            listings = await self.cog._listing_pool(self.guild_id, scope=self.scope, viewer_id=self.user_id)
            current = self._current_listing(listings)
            if current is None:
                await interaction.response.send_message("Активный лот не найден.", ephemeral=True)
                return
            success, payload = await self.cog.place_bid(self.user_id, self.guild_id, int(current["id"]), amount)
            if isinstance(payload, discord.Embed):
                await interaction.response.send_message(embed=payload, ephemeral=True)
            else:
                await interaction.response.send_message(str(payload), ephemeral=True)
            if success and self.message is not None:
                await self._refresh(interaction)

    @discord.ui.button(label="Все", style=discord.ButtonStyle.primary, row=0)
    async def all_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            self.scope = "all"
            self.page = 0
            await self._refresh(interaction)

    @discord.ui.button(label="Мои", style=discord.ButtonStyle.secondary, row=0)
    async def mine_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            self.scope = "mine"
            self.page = 0
            await self._refresh(interaction)

    @discord.ui.button(label="Создать", style=discord.ButtonStyle.success, row=0)
    async def create_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await interaction.response.send_modal(AuctionCreateModal(self))

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            self.page = max(0, self.page - 1)
            await self._refresh(interaction)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def page_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.response.is_done():
            await interaction.response.send_message("Страница меняется кнопками по бокам.", ephemeral=True)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            self.page += 1
            await self._refresh(interaction)

    @discord.ui.button(label="Купить", style=discord.ButtonStyle.primary, row=2)
    async def main_action_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            listings = await self.cog._listing_pool(self.guild_id, scope=self.scope, viewer_id=self.user_id)
            current = self._current_listing(listings)
            if current is None:
                await interaction.response.send_message("Лот не найден.", ephemeral=True)
                return
            if _is_fixed_listing(current):
                success, payload = await self.cog.buy_listing(self.user_id, self.guild_id, int(current["id"]))
            else:
                await interaction.response.send_modal(AuctionBidModal(self))
                return
            if isinstance(payload, discord.Embed):
                await interaction.response.send_message(embed=payload, ephemeral=True)
            else:
                await interaction.response.send_message(str(payload), ephemeral=True)
            if success and self.message is not None:
                await self._refresh(interaction)

    @discord.ui.button(label="Выкуп", style=discord.ButtonStyle.success, row=2)
    async def buyout_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            listings = await self.cog._listing_pool(self.guild_id, scope=self.scope, viewer_id=self.user_id)
            current = self._current_listing(listings)
            if current is None:
                await interaction.response.send_message("Лот не найден.", ephemeral=True)
                return
            success, payload = await self.cog.buyout_listing(self.user_id, self.guild_id, int(current["id"]))
            if isinstance(payload, discord.Embed):
                await interaction.response.send_message(embed=payload, ephemeral=True)
            else:
                await interaction.response.send_message(str(payload), ephemeral=True)
            if success and self.message is not None:
                await self._refresh(interaction)

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.danger, row=2)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            listings = await self.cog._listing_pool(self.guild_id, scope=self.scope, viewer_id=self.user_id)
            current = self._current_listing(listings)
            if current is None:
                await interaction.response.send_message("Лот не найден.", ephemeral=True)
                return
            success, payload = await self.cog.cancel_listing(self.user_id, self.guild_id, int(current["id"]))
            if isinstance(payload, discord.Embed):
                await interaction.response.send_message(embed=payload, ephemeral=True)
            else:
                await interaction.response.send_message(str(payload), ephemeral=True)
            if success and self.message is not None:
                await self._refresh(interaction)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self._refresh(interaction)

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


class AuctionCog(commands.Cog, name="Auction"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._listing_locks: dict[int, asyncio.Lock] = {}

    def _listing_lock(self, listing_id: int) -> asyncio.Lock:
        key = int(listing_id)
        if key not in self._listing_locks:
            self._listing_locks[key] = asyncio.Lock()
        return self._listing_locks[key]

    async def cog_load(self):
        if not self.settlement_loop.is_running():
            self.settlement_loop.start()

    def cog_unload(self):
        self.settlement_loop.cancel()

    @staticmethod
    def _auction_available() -> tuple[bool, str | None]:
        if db.sync_feature_enabled("auction_access"):
            return True, None
        return False, db.get_sync_feature_reason("auction_access") or "Таблицы аукциона пока недоступны."

    @staticmethod
    def _payload_item_kind(payload: dict[str, Any]) -> str:
        return str(payload.get("kind") or "")

    @staticmethod
    def _is_supported_general_item(item: dict[str, Any]) -> bool:
        item_type = str(item.get("item_type") or "")
        blocked_prefixes = ("active_", "tenant_", "profile_")
        return not any(item_type.startswith(prefix) for prefix in blocked_prefixes)

    def _extract_inventory_item(self, user: dict[str, Any], item_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None]:
        fish_item = find_fish_item(user, item_id)
        if fish_item is not None:
            extracted = extract_fish_item(user, item_id)
            if extracted is None:
                return None, None, "Не удалось подготовить рыбу к выставлению."
            return extracted, {"kind": "fish", "item": extracted, "title": str(extracted.get("name") or f"Рыба #{item_id}")}, None

        general_item = find_general_item(user, item_id)
        if general_item is None:
            return None, None, "Предмет с таким ID не найден в инвентаре."
        if not self._is_supported_general_item(general_item):
            return None, None, "Этот тип предмета пока нельзя выставить на аукцион."
        extracted = extract_general_item(user, item_id=item_id, quantity=max(1, int(general_item.get("quantity", 1) or 1)))
        if extracted is None:
            return None, None, "Не удалось снять предмет с инвентаря для выставления."
        return extracted, {"kind": "general", "item": extracted, "title": str(extracted.get("name") or f"Предмет #{item_id}")}, None

    def _restore_inventory_item(self, user: dict[str, Any], payload: dict[str, Any]) -> bool:
        item = payload.get("item") if isinstance(payload.get("item"), dict) else None
        if item is None:
            return False
        kind = self._payload_item_kind(payload)
        if kind == "fish":
            return restore_fish_item(user, item) is not None
        if kind == "general":
            return restore_general_item(user, item) is not None
        return False

    async def _listing_pool(self, guild_id: int, *, scope: str = "all", viewer_id: int | None = None) -> list[dict[str, Any]]:
        await self._settle_expired_once(limit=25)
        available, _ = self._auction_available()
        if not available:
            return []
        listings = await db.list_auction_listings(guild_id, status="active", limit=50)
        if scope == "mine" and viewer_id is not None:
            viewer = int(viewer_id)
            listings = [
                listing
                for listing in listings
                if int(listing.get("seller_id", 0) or 0) == viewer
                or int(listing.get("current_bidder_id", 0) or 0) == viewer
            ]
        listings.sort(key=lambda row: _parse_utc(row.get("created_at")) or datetime.now(timezone.utc), reverse=True)
        return listings

    @staticmethod
    def _minimum_bid(listing: dict[str, Any]) -> int:
        current_bid = int(listing.get("current_bid", 0) or 0)
        asking_price = max(1, int(listing.get("asking_price", 0) or 0))
        if current_bid <= 0:
            return asking_price
        return max(current_bid + 1, int(math.ceil(current_bid * 1.05)))

    @staticmethod
    def _listing_status_label(listing: dict[str, Any]) -> str:
        status = str(listing.get("status") or "active")
        return {
            "active": "Активен",
            "sold": "Продан",
            "cancelled": "Отменён",
            "expired": "Истёк",
        }.get(status, status)

    @staticmethod
    def _listing_scope_label(scope: str) -> str:
        return "Мои лоты" if scope == "mine" else "Все лоты сервера"

    @staticmethod
    def _item_preview_lines(listing: dict[str, Any]) -> list[str]:
        payload = listing.get("item_payload") if isinstance(listing.get("item_payload"), dict) else {}
        item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
        lines = [
            f"{_listing_item_emoji(listing)} **{_listing_item_name(listing)}**",
            f"Статус: **{AuctionCog._listing_status_label(listing)}**",
        ]
        rarity_name = str(item.get("rarity_name") or "")
        if rarity_name:
            lines.append(f"Редкость: **{rarity_name}**")
        quantity = int(item.get("quantity", 1) or 1)
        if quantity > 1:
            lines.append(f"Количество: **x{quantity}**")
        description = str(item.get("description") or "").strip()
        if description:
            lines.append(description[:180])
        return lines

    async def build_auction_embed(
        self,
        user_id: int,
        guild_id: int,
        *,
        scope: str = "all",
        page: int = 0,
    ) -> tuple[discord.Embed, list[dict[str, Any]]]:
        available, reason = self._auction_available()
        if not available:
            embed = discord.Embed(
                title="🏛️ Аукцион",
                description=(
                    "Система аукциона ещё не инициализирована в базе.\n"
                    f"{reason or 'Примени SQL foundation для auction_listings и auction_bids.'}"
                ),
                color=COLORS["warning"],
            )
            return embed, []

        user = await db.get_user(user_id, guild_id)
        listings = await self._listing_pool(guild_id, scope=scope, viewer_id=user_id)
        current = listings[min(max(0, page), max(0, len(listings) - 1))] if listings else None
        embed = discord.Embed(
            title="🏛️ Аукцион",
            description=(
                f"Режим: **{self._listing_scope_label(scope)}**\n"
                "Выставляй переносимые предметы из `/inventory`, делай ставки и выкупай редкие трофеи."
            ),
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        if user:
            embed.add_field(
                name="Кошелёк",
                value=(
                    f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                    f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
                ),
                inline=True,
            )
        active_count = len(listings)
        mine_count = len([row for row in listings if int(row.get("seller_id", 0) or 0) == int(user_id)])
        embed.add_field(
            name="Рынок",
            value=f"Активных лотов: **{active_count}**\nТвоих в этой витрине: **{mine_count}**",
            inline=True,
        )
        embed.add_field(
            name="Правила v1",
            value="Длительности: **6h / 24h / 48h**\nСтавки шагом **+5%**\nПредмет уходит в escrow сразу.",
            inline=True,
        )

        if current is None:
            embed.add_field(
                name="Сейчас пусто",
                value="На этой витрине пока нет активных лотов. Можно первым выставить предмет через кнопку `Создать`.",
                inline=False,
            )
            return embed, listings

        ends_at = _parse_utc(current.get("ends_at"))
        price_lines = [f"Старт / цена: **{format_money(current.get('asking_price', 0))}**"]
        if _supports_auction(current):
            current_bid = int(current.get("current_bid", 0) or 0)
            price_lines.append(f"Текущая ставка: **{format_money(current_bid)}**" if current_bid > 0 else "Текущая ставка: **ещё нет**")
            price_lines.append(f"Мин. следующая: **{format_money(self._minimum_bid(current))}**")
            price_lines.append(f"Ставок: **{int(current.get('bid_count', 0) or 0)}**")
            if int(current.get("buyout_price", 0) or 0) > 0:
                price_lines.append(f"Выкуп: **{format_money(current['buyout_price'])}**")
        if isinstance(ends_at, datetime):
            price_lines.append(f"До конца: {format_discord_deadline(ends_at)}")
        seller_id = int(current.get("seller_id", 0) or 0)
        if seller_id:
            price_lines.append(f"Продавец: <@{seller_id}>")
        bidder_id = int(current.get("current_bidder_id", 0) or 0)
        if bidder_id and _supports_auction(current):
            price_lines.append(f"Лидер ставок: <@{bidder_id}>")
        embed.add_field(name="Текущий лот", value="\n".join(self._item_preview_lines(current)), inline=False)
        embed.add_field(name="Детали сделки", value="\n".join(price_lines), inline=False)
        embed.set_footer(text="Покупка фикс-лота завершает сделку сразу. Для аукциона можно ставить или жать выкуп.")
        return embed, listings

    async def create_listing(
        self,
        user_id: int,
        guild_id: int,
        *,
        item_id: int,
        mode: str,
        price: int,
        duration_hours: int,
        buyout_price: int | None = None,
    ) -> tuple[bool, discord.Embed | str]:
        available, reason = self._auction_available()
        if not available:
            return False, reason or "Аукцион сейчас недоступен."
        listing_type = "fixed_price" if mode in {"fixed", "fixed_price", "buy"} else "auction"
        if duration_hours not in DURATIONS:
            return False, "Длительность должна быть одной из: 6, 24 или 48 часов."
        if int(price or 0) <= 0:
            return False, "Цена должна быть больше нуля."
        if listing_type == "auction" and buyout_price is not None and int(buyout_price or 0) <= int(price):
            return False, "Выкуп должен быть выше стартовой цены."

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            item, payload, error = self._extract_inventory_item(user, int(item_id))
            if payload is None:
                return False, error or "Не удалось подготовить предмет."
            created_at = datetime.now(timezone.utc)
            listing = await db.create_auction_listing(
                {
                    "guild_id": guild_id,
                    "seller_id": user_id,
                    "listing_type": listing_type,
                    "status": "active",
                    "item_payload": payload,
                    "title": str(payload.get("title") or _listing_item_name({"item_payload": payload})),
                    "asking_price": int(price),
                    "buyout_price": int(buyout_price) if buyout_price else None,
                    "current_bid": 0,
                    "current_bidder_id": None,
                    "bid_count": 0,
                    "duration_hours": int(duration_hours),
                    "ends_at": (created_at + timedelta(hours=int(duration_hours))).isoformat(),
                    "created_at": created_at.isoformat(),
                    "updated_at": created_at.isoformat(),
                }
            )
            if listing is None:
                self._restore_inventory_item(user, payload)
                await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})
                return False, "Не удалось создать лот. Проверь SQL foundation для аукциона."
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="🏛️ Лот создан",
            description=(
                f"Предмет **{item.get('name', f'#{item_id}')}** выставлен на рынок.\n"
                f"Режим: **{'Фиксированная цена' if listing_type == 'fixed_price' else 'Аукцион'}**\n"
                f"Цена старта: **{format_money(price)}**\n"
                f"Длительность: **{duration_hours}ч**"
            ),
            color=COLORS["success"],
        )
        if listing_type == "auction" and buyout_price:
            embed.add_field(name="Выкуп", value=f"**{format_money(buyout_price)}**", inline=True)
        embed.add_field(name="Лот", value=f"ID аукциона: **{listing['id']}**", inline=True)
        return True, embed

    async def _load_active_listing(self, listing_id: int, guild_id: int) -> tuple[dict[str, Any] | None, str | None]:
        listing = await db.get_auction_listing(listing_id)
        if listing is None:
            return None, "Лот не найден."
        if int(listing.get("guild_id", 0) or 0) != int(guild_id):
            return None, "Этот лот относится к другому серверу."
        if str(listing.get("status") or "") != "active":
            return None, "Этот лот уже закрыт."
        ends_at = _parse_utc(listing.get("ends_at"))
        if isinstance(ends_at, datetime) and datetime.now(timezone.utc) >= ends_at:
            await self._settle_listing(listing)
            return None, "Лот только что завершился. Обнови витрину."
        return listing, None

    async def buy_listing(self, buyer_id: int, guild_id: int, listing_id: int) -> tuple[bool, discord.Embed | str]:
        async with self._listing_lock(listing_id):
            listing, error = await self._load_active_listing(listing_id, guild_id)
            if listing is None:
                return False, error or "Лот недоступен."
            if not _is_fixed_listing(listing):
                return False, "Для этого лота нужна ставка, а не мгновенная покупка."
            seller_id = int(listing.get("seller_id", 0) or 0)
            if seller_id == int(buyer_id):
                return False, "Нельзя купить собственный лот."
            price = int(listing.get("asking_price", 0) or 0)

            async with _user_locks(buyer_id, seller_id):
                buyer = await db.get_user(buyer_id, guild_id)
                seller = await db.get_user(seller_id, guild_id)
                if not buyer or not seller:
                    return False, "Не удалось загрузить участников сделки."
                if int(buyer.get("balance", 0) or 0) < price:
                    return False, f"Не хватает денег. Нужно **{format_money(price)}**."
                buyer["balance"] = int(buyer.get("balance", 0) or 0) - price
                seller["balance"] = int(seller.get("balance", 0) or 0) + price
                if not self._restore_inventory_item(buyer, listing.get("item_payload") or {}):
                    return False, "Не удалось передать предмет покупателю."
                await add_bank_entry(
                    buyer,
                    guild_id,
                    -price,
                    "auction_purchase",
                    f"Покупка лота #{listing_id}: {_listing_item_name(listing)}.",
                    counterparty_id=seller_id,
                )
                await add_bank_entry(
                    seller,
                    guild_id,
                    price,
                    "auction_sale",
                    f"Продажа лота #{listing_id}: {_listing_item_name(listing)}.",
                    counterparty_id=buyer_id,
                )
                await db.update_user(buyer_id, guild_id, {"balance": buyer.get("balance", 0), "inventory": buyer.get("inventory"), "game_stats": buyer.get("game_stats", {})})
                await db.update_user(seller_id, guild_id, {"balance": seller.get("balance", 0), "inventory": seller.get("inventory"), "game_stats": seller.get("game_stats", {})})
                await db.update_auction_listing(
                    listing_id,
                    {
                        "status": "sold",
                        "buyer_id": buyer_id,
                        "current_bid": price,
                        "current_bidder_id": buyer_id,
                        "bid_count": max(1, int(listing.get("bid_count", 0) or 0)),
                    },
                )

        embed = discord.Embed(
            title="🏛️ Лот куплен",
            description=(
                f"Ты купил **{_listing_item_name(listing)}** за **{format_money(price)}**.\n"
                "Предмет уже доставлен в твой инвентарь."
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def place_bid(self, bidder_id: int, guild_id: int, listing_id: int, amount: int) -> tuple[bool, discord.Embed | str]:
        async with self._listing_lock(listing_id):
            listing, error = await self._load_active_listing(listing_id, guild_id)
            if listing is None:
                return False, error or "Лот недоступен."
            if not _supports_auction(listing):
                return False, "На этот лот нельзя ставить, он продаётся по фиксированной цене."
            seller_id = int(listing.get("seller_id", 0) or 0)
            current_bidder_id = int(listing.get("current_bidder_id", 0) or 0)
            if seller_id == int(bidder_id):
                return False, "Нельзя ставить на собственный лот."
            if current_bidder_id == int(bidder_id):
                return False, "Ты уже лидируешь по ставкам на этот лот."
            minimum_bid = self._minimum_bid(listing)
            if int(amount or 0) < minimum_bid:
                return False, f"Минимальная следующая ставка: **{format_money(minimum_bid)}**."

            async with _user_locks(bidder_id, current_bidder_id):
                bidder = await db.get_user(bidder_id, guild_id)
                if not bidder:
                    return False, "Не удалось загрузить твой профиль."
                previous_bidder = await db.get_user(current_bidder_id, guild_id) if current_bidder_id else None
                if int(bidder.get("balance", 0) or 0) < int(amount):
                    return False, f"Не хватает денег. Нужно **{format_money(amount)}**."
                bidder["balance"] = int(bidder.get("balance", 0) or 0) - int(amount)
                await add_bank_entry(
                    bidder,
                    guild_id,
                    -int(amount),
                    "auction_bid_reserve",
                    f"Резерв ставки по лоту #{listing_id}: {_listing_item_name(listing)}.",
                )
                if previous_bidder is not None and int(listing.get("current_bid", 0) or 0) > 0:
                    refund_amount = int(listing.get("current_bid", 0) or 0)
                    previous_bidder["balance"] = int(previous_bidder.get("balance", 0) or 0) + refund_amount
                    await add_bank_entry(
                        previous_bidder,
                        guild_id,
                        refund_amount,
                        "auction_bid_refund",
                        f"Возврат ставки по лоту #{listing_id}: {_listing_item_name(listing)}.",
                    )
                    await db.update_user(current_bidder_id, guild_id, {"balance": previous_bidder.get("balance", 0), "inventory": previous_bidder.get("inventory"), "game_stats": previous_bidder.get("game_stats", {})})
                await db.update_user(bidder_id, guild_id, {"balance": bidder.get("balance", 0), "inventory": bidder.get("inventory"), "game_stats": bidder.get("game_stats", {})})
                await db.add_auction_bid({"listing_id": listing_id, "guild_id": guild_id, "bidder_id": bidder_id, "amount": int(amount)})
                await db.update_auction_listing(
                    listing_id,
                    {
                        "current_bid": int(amount),
                        "current_bidder_id": bidder_id,
                        "bid_count": int(listing.get("bid_count", 0) or 0) + 1,
                    },
                )

        embed = discord.Embed(
            title="🏛️ Ставка принята",
            description=(
                f"Новая ставка по **{_listing_item_name(listing)}**: **{format_money(amount)}**.\n"
                "Сумма зарезервирована до перебития или завершения аукциона."
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def buyout_listing(self, buyer_id: int, guild_id: int, listing_id: int) -> tuple[bool, discord.Embed | str]:
        async with self._listing_lock(listing_id):
            listing, error = await self._load_active_listing(listing_id, guild_id)
            if listing is None:
                return False, error or "Лот недоступен."
            if not _supports_auction(listing):
                return False, "Выкуп доступен только для аукционных лотов."
            buyout_price = int(listing.get("buyout_price", 0) or 0)
            if buyout_price <= 0:
                return False, "У этого лота нет цены выкупа."

            seller_id = int(listing.get("seller_id", 0) or 0)
            previous_bidder_id = int(listing.get("current_bidder_id", 0) or 0)
            current_bid = int(listing.get("current_bid", 0) or 0)
            if seller_id == int(buyer_id):
                return False, "Нельзя выкупить собственный лот."
            extra_charge = buyout_price if previous_bidder_id != int(buyer_id) else max(0, buyout_price - current_bid)

            async with _user_locks(buyer_id, seller_id, previous_bidder_id):
                buyer = await db.get_user(buyer_id, guild_id)
                seller = await db.get_user(seller_id, guild_id)
                previous_bidder = await db.get_user(previous_bidder_id, guild_id) if previous_bidder_id and previous_bidder_id != buyer_id else None
                if not buyer or not seller:
                    return False, "Не удалось загрузить участников сделки."
                if int(buyer.get("balance", 0) or 0) < extra_charge:
                    return False, f"Не хватает денег. Нужно ещё **{format_money(extra_charge)}**."
                if extra_charge > 0:
                    buyer["balance"] = int(buyer.get("balance", 0) or 0) - extra_charge
                    await add_bank_entry(
                        buyer,
                        guild_id,
                        -extra_charge,
                        "auction_buyout_charge",
                        f"Доплата за выкуп лота #{listing_id}: {_listing_item_name(listing)}.",
                    )
                if previous_bidder is not None and current_bid > 0:
                    previous_bidder["balance"] = int(previous_bidder.get("balance", 0) or 0) + current_bid
                    await add_bank_entry(
                        previous_bidder,
                        guild_id,
                        current_bid,
                        "auction_bid_refund",
                        f"Возврат ставки по лоту #{listing_id}: {_listing_item_name(listing)}.",
                    )
                    await db.update_user(previous_bidder_id, guild_id, {"balance": previous_bidder.get("balance", 0), "inventory": previous_bidder.get("inventory"), "game_stats": previous_bidder.get("game_stats", {})})
                seller["balance"] = int(seller.get("balance", 0) or 0) + buyout_price
                if not self._restore_inventory_item(buyer, listing.get("item_payload") or {}):
                    return False, "Не удалось передать предмет после выкупа."
                await add_bank_entry(
                    seller,
                    guild_id,
                    buyout_price,
                    "auction_sale",
                    f"Продажа лота #{listing_id} по выкупу: {_listing_item_name(listing)}.",
                    counterparty_id=buyer_id,
                )
                await db.update_user(buyer_id, guild_id, {"balance": buyer.get("balance", 0), "inventory": buyer.get("inventory"), "game_stats": buyer.get("game_stats", {})})
                await db.update_user(seller_id, guild_id, {"balance": seller.get("balance", 0), "inventory": seller.get("inventory"), "game_stats": seller.get("game_stats", {})})
                await db.update_auction_listing(
                    listing_id,
                    {
                        "status": "sold",
                        "buyer_id": buyer_id,
                        "current_bid": buyout_price,
                        "current_bidder_id": buyer_id,
                        "bid_count": max(1, int(listing.get("bid_count", 0) or 0)),
                    },
                )

        embed = discord.Embed(
            title="🏛️ Выкуп завершён",
            description=(
                f"Ты выкупил **{_listing_item_name(listing)}** за **{format_money(buyout_price)}**.\n"
                "Лот закрыт, предмет уже лежит в твоём инвентаре."
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def cancel_listing(self, seller_id: int, guild_id: int, listing_id: int) -> tuple[bool, discord.Embed | str]:
        async with self._listing_lock(listing_id):
            listing, error = await self._load_active_listing(listing_id, guild_id)
            if listing is None:
                return False, error or "Лот недоступен."
            if int(listing.get("seller_id", 0) or 0) != int(seller_id):
                return False, "Отменить лот может только продавец."
            if int(listing.get("bid_count", 0) or 0) > 0:
                return False, "Нельзя отменить лот, по которому уже есть ставки."

            async with get_user_lock(seller_id):
                seller = await db.get_user(seller_id, guild_id)
                if not seller:
                    return False, "Не удалось загрузить профиль продавца."
                if not self._restore_inventory_item(seller, listing.get("item_payload") or {}):
                    return False, "Не удалось вернуть предмет в инвентарь."
                await db.update_user(seller_id, guild_id, {"inventory": seller.get("inventory"), "game_stats": seller.get("game_stats", {})})
                await db.update_auction_listing(listing_id, {"status": "cancelled"})

        embed = discord.Embed(
            title="🏛️ Лот отменён",
            description=f"Лот **{_listing_item_name(listing)}** снят с аукциона и возвращён в инвентарь.",
            color=COLORS["warning"],
        )
        return True, embed

    async def _settle_listing(self, listing: dict[str, Any]) -> None:
        listing_id = int(listing.get("id", 0) or 0)
        if listing_id <= 0:
            return
        async with self._listing_lock(listing_id):
            latest = await db.get_auction_listing(listing_id)
            if not latest or str(latest.get("status") or "") != "active":
                return
            seller_id = int(latest.get("seller_id", 0) or 0)
            bidder_id = int(latest.get("current_bidder_id", 0) or 0)
            current_bid = int(latest.get("current_bid", 0) or 0)
            guild_id = int(latest.get("guild_id", 0) or 0)

            if bidder_id and current_bid > 0:
                async with _user_locks(seller_id, bidder_id):
                    seller = await db.get_user(seller_id, guild_id)
                    buyer = await db.get_user(bidder_id, guild_id)
                    if not seller or not buyer:
                        return
                    seller["balance"] = int(seller.get("balance", 0) or 0) + current_bid
                    if not self._restore_inventory_item(buyer, latest.get("item_payload") or {}):
                        return
                    await add_bank_entry(
                        seller,
                        guild_id,
                        current_bid,
                        "auction_sale",
                        f"Автозавершение лота #{listing_id}: {_listing_item_name(latest)}.",
                        counterparty_id=bidder_id,
                    )
                    await db.update_user(seller_id, guild_id, {"balance": seller.get("balance", 0), "inventory": seller.get("inventory"), "game_stats": seller.get("game_stats", {})})
                    await db.update_user(bidder_id, guild_id, {"balance": buyer.get("balance", 0), "inventory": buyer.get("inventory"), "game_stats": buyer.get("game_stats", {})})
                    await db.update_auction_listing(listing_id, {"status": "sold", "buyer_id": bidder_id})
                return

            async with get_user_lock(seller_id):
                seller = await db.get_user(seller_id, guild_id)
                if not seller:
                    return
                if self._restore_inventory_item(seller, latest.get("item_payload") or {}):
                    await db.update_user(seller_id, guild_id, {"inventory": seller.get("inventory"), "game_stats": seller.get("game_stats", {})})
                await db.update_auction_listing(listing_id, {"status": "expired"})

    async def _settle_expired_once(self, *, limit: int = 20) -> None:
        available, _ = self._auction_available()
        if not available:
            return
        expired = await db.list_expired_auction_listings(limit=limit)
        for listing in expired:
            await self._settle_listing(listing)

    @tasks.loop(minutes=5)
    async def settlement_loop(self):
        await self._settle_expired_once(limit=25)

    @settlement_loop.before_loop
    async def before_settlement_loop(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="auction", description="Открыть серверный аукцион")
    async def auction(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return
        view = AuctionView(self, interaction.user.id, interaction.guild_id)
        embed, listings = await self.build_auction_embed(interaction.user.id, interaction.guild_id, scope=view.scope, page=view.page)
        view.sync_buttons(listings)
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        await view._remember_message(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(AuctionCog(bot))
