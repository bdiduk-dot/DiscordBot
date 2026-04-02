from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS
from database import db, get_user_lock
from utils import check_channel, format_discord_deadline, schedule_message_cleanup, send_wrong_channel_message

DEPOSIT_TERMS: dict[str, dict[str, Any]] = {
    "1d": {"days": 1, "rate": 0.02, "label": "1 день"},
    "3d": {"days": 3, "rate": 0.07, "label": "3 дня"},
    "7d": {"days": 7, "rate": 0.20, "label": "7 дней"},
}
EARLY_WITHDRAW_PENALTY = 0.10


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def deposit_snapshot(user: dict[str, Any]) -> dict[str, Any]:
    amount = max(0, int(user.get("deposit_amount", 0) or 0))
    rate = max(0.0, float(user.get("deposit_rate", 0) or 0))
    days = max(0, int(user.get("deposit_days", 0) or 0))
    start_at = parse_utc(user.get("deposit_start"))
    active = amount > 0 and start_at is not None and days > 0

    if not active:
        return {
            "active": False,
            "amount": 0,
            "rate": 0.0,
            "days": 0,
            "start_at": None,
            "matures_at": None,
            "matured": False,
            "normal_payout": 0,
            "normal_profit": 0,
            "early_penalty": 0,
            "early_payout": 0,
        }

    matures_at = start_at + timedelta(days=days)
    matured = datetime.now(timezone.utc) >= matures_at
    normal_profit = int(round(amount * rate))
    normal_payout = amount + normal_profit
    early_penalty = int(round(amount * EARLY_WITHDRAW_PENALTY))
    early_payout = max(0, amount - early_penalty)
    return {
        "active": True,
        "amount": amount,
        "rate": rate,
        "days": days,
        "start_at": start_at,
        "matures_at": matures_at,
        "matured": matured,
        "normal_payout": normal_payout,
        "normal_profit": normal_profit,
        "early_penalty": early_penalty,
        "early_payout": early_payout,
    }


async def remember_interaction_message(
    interaction: discord.Interaction,
    current: discord.Message | None = None,
) -> discord.Message | None:
    try:
        return await interaction.original_response()
    except Exception:
        return interaction.message or current


def build_bank_embed(
    user: dict[str, Any],
    *,
    member: discord.Member | discord.User | None = None,
    read_only: bool = False,
) -> discord.Embed:
    snapshot = deposit_snapshot(user)
    title = "Банк"
    if member is not None and read_only:
        title = f"Банк • {member.display_name}"

    embed = discord.Embed(
        title=title,
        description=(
            f"**Наличные:** {format_money(user.get('balance', 0))}\n"
            f"**Банковский счёт:** {format_money(user.get('bank', 0))}"
        ),
        color=COLORS["info"],
        timestamp=datetime.now(timezone.utc),
    )
    if member is not None:
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)

    if not snapshot["active"]:
        deposit_text = (
            "**Активный депозит:** нет\n"
            "**Ставки:** 1 день = 2% • 3 дня = 7% • 7 дней = 20%\n"
            f"**Штраф за моментальный вывод:** {int(EARLY_WITHDRAW_PENALTY * 100)}% от суммы"
        )
    else:
        status = "Созрел" if snapshot["matured"] else format_discord_deadline(snapshot["matures_at"])
        deposit_text = (
            f"**Сумма:** {format_money(snapshot['amount'])}\n"
            f"**Процент:** {snapshot['rate'] * 100:.0f}%\n"
            f"**Срок:** {snapshot['days']} дн.\n"
            f"**До завершения:** {status}\n"
            f"**Штраф за моментальный вывод:** -{format_money(snapshot['early_penalty'])}\n"
            f"**К выплате при завершении:** {format_money(snapshot['normal_payout'])}"
        )

    embed.add_field(name="Депозит", value=deposit_text, inline=False)
    if read_only:
        embed.set_footer(text="Чужой банковский счёт доступен только для просмотра.")
    else:
        embed.set_footer(text="Депозит открывается с банковского счёта.")
    return embed


class BankAmountModal(discord.ui.Modal):
    def __init__(self, view: "BankView", mode: str):
        self.bank_view = view
        self.mode = mode
        title_map = {
            "deposit_bank": "Пополнение банка",
            "withdraw_bank": "Снятие из банка",
        }
        placeholder_map = {
            "deposit_bank": "Например: 5000 или all",
            "withdraw_bank": "Например: 5000 или all",
        }
        label_map = {
            "deposit_bank": "Сумма для перевода в банк",
            "withdraw_bank": "Сумма для снятия из банка",
        }
        super().__init__(title=title_map[mode])
        self.amount = discord.ui.TextInput(
            label=label_map[mode],
            placeholder=placeholder_map[mode],
            max_length=12,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.amount.value).strip().lower().replace(",", "")
        async with get_user_lock(self.bank_view.user_id):
            user = await db.get_user(self.bank_view.user_id, self.bank_view.guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return

            if raw_value in {"all", "max", "все", "макс"}:
                amount = int(user.get("balance", 0) or 0) if self.mode == "deposit_bank" else int(user.get("bank", 0) or 0)
            elif raw_value.isdigit():
                amount = int(raw_value)
            else:
                await interaction.response.send_message("Введи положительное число или `all`.", ephemeral=True)
                return

            if amount <= 0:
                await interaction.response.send_message("Сумма должна быть больше нуля.", ephemeral=True)
                return

            if self.mode == "deposit_bank":
                if int(user.get("balance", 0) or 0) < amount:
                    await interaction.response.send_message("Не хватает наличных для пополнения банка.", ephemeral=True)
                    return
                user["balance"] = int(user.get("balance", 0) or 0) - amount
                user["bank"] = int(user.get("bank", 0) or 0) + amount
                title = "Банк пополнен"
                description = (
                    f"Переведено в банк: **{format_money(amount)}**\n"
                    f"Наличные: **{format_money(user['balance'])}**\n"
                    f"Банк: **{format_money(user['bank'])}**"
                )
            else:
                if int(user.get("bank", 0) or 0) < amount:
                    await interaction.response.send_message("В банке недостаточно денег.", ephemeral=True)
                    return
                user["bank"] = int(user.get("bank", 0) or 0) - amount
                user["balance"] = int(user.get("balance", 0) or 0) + amount
                title = "Деньги сняты"
                description = (
                    f"Выведено из банка: **{format_money(amount)}**\n"
                    f"Наличные: **{format_money(user['balance'])}**\n"
                    f"Банк: **{format_money(user['bank'])}**"
                )

            await db.update_user(
                self.bank_view.user_id,
                self.bank_view.guild_id,
                {"balance": user["balance"], "bank": user["bank"]},
            )
            self.bank_view.user_data = user

        await interaction.response.send_message(
            embed=discord.Embed(title=title, description=description, color=COLORS["success"]),
            ephemeral=True,
        )
        await self.bank_view.refresh_message()


class DepositCreateModal(discord.ui.Modal):
    def __init__(self, parent_view: "BankView", term_key: str):
        self.parent_view = parent_view
        self.term_key = term_key
        term = DEPOSIT_TERMS[term_key]
        super().__init__(title=f"Депозит на {term['label']}")
        self.amount = discord.ui.TextInput(
            label="Сумма из банковского счёта",
            placeholder="Например: 15000 или all",
            max_length=12,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        raw_value = str(self.amount.value).strip().lower().replace(",", "")
        term = DEPOSIT_TERMS[self.term_key]

        async with get_user_lock(self.parent_view.user_id):
            user = await db.get_user(self.parent_view.user_id, self.parent_view.guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return

            current_deposit = deposit_snapshot(user)
            if current_deposit["active"]:
                await interaction.response.send_message("У тебя уже есть активный депозит.", ephemeral=True)
                return

            if raw_value in {"all", "max", "все", "макс"}:
                amount = int(user.get("bank", 0) or 0)
            elif raw_value.isdigit():
                amount = int(raw_value)
            else:
                await interaction.response.send_message("Введи положительное число или `all`.", ephemeral=True)
                return

            if amount <= 0:
                await interaction.response.send_message("Сумма должна быть больше нуля.", ephemeral=True)
                return
            if int(user.get("bank", 0) or 0) < amount:
                await interaction.response.send_message("На банковском счёте недостаточно денег.", ephemeral=True)
                return

            user["bank"] = int(user.get("bank", 0) or 0) - amount
            user["deposit_amount"] = amount
            user["deposit_rate"] = float(term["rate"])
            user["deposit_days"] = int(term["days"])
            user["deposit_start"] = datetime.now(timezone.utc).isoformat()

            await db.update_user(
                self.parent_view.user_id,
                self.parent_view.guild_id,
                {
                    "bank": user["bank"],
                    "deposit_amount": user["deposit_amount"],
                    "deposit_rate": user["deposit_rate"],
                    "deposit_days": user["deposit_days"],
                    "deposit_start": user["deposit_start"],
                },
            )
            self.parent_view.user_data = user

        payout = int(amount * (1 + float(term["rate"])))
        early_penalty = int(round(amount * EARLY_WITHDRAW_PENALTY))
        await interaction.response.send_message(
            embed=discord.Embed(
                title="Депозит открыт",
                description=(
                    f"Срок: **{term['label']}**\n"
                    f"Сумма: **{format_money(amount)}**\n"
                    f"Процент: **{term['rate'] * 100:.0f}%**\n"
                    f"К выплате при завершении: **{format_money(payout)}**\n"
                    f"Штраф за моментальный вывод: **-{format_money(early_penalty)}**"
                ),
                color=COLORS["gold"],
            ),
            ephemeral=True,
        )
        await self.parent_view.refresh_message()


class DepositTermView(discord.ui.View):
    def __init__(self, parent_view: "BankView"):
        super().__init__(timeout=120)
        self.parent_view = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent_view.user_id:
            await interaction.response.send_message("Это меню депозита открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _open_modal(self, interaction: discord.Interaction, term_key: str):
        await interaction.response.send_modal(DepositCreateModal(self.parent_view, term_key))

    @discord.ui.button(label="1 день • 2%", style=discord.ButtonStyle.success)
    async def one_day(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "1d")

    @discord.ui.button(label="3 дня • 7%", style=discord.ButtonStyle.primary)
    async def three_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "3d")

    @discord.ui.button(label="7 дней • 20%", style=discord.ButtonStyle.danger)
    async def seven_days(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._open_modal(interaction, "7d")


class EarlyWithdrawConfirmView(discord.ui.View):
    def __init__(self, parent_view: "BankView"):
        super().__init__(timeout=120)
        self.parent_view = parent_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent_view.user_id:
            await interaction.response.send_message("Это подтверждение открыто не тобой.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Подтвердить вывод", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        success, payload = await self.parent_view.close_deposit(early=True)
        if not success:
            await interaction.response.send_message(str(payload), ephemeral=True)
            return
        await interaction.response.edit_message(content="Досрочный вывод выполнен.", embed=None, view=None)
        await interaction.followup.send(embed=payload, ephemeral=True)
        await self.parent_view.refresh_message()

    @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Вывод депозита отменён.", embed=None, view=None)


class BankView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, user_data: dict[str, Any] | None = None):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.user_data = user_data or {}
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self.sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню банка открыто не тобой.", ephemeral=True)
            return False
        return True

    async def reload_user(self):
        self.user_data = await db.get_user(self.user_id, self.guild_id) or {}

    def build_embed(self) -> discord.Embed:
        return build_bank_embed(self.user_data or {})
        user = self.user_data or {}
        snapshot = deposit_snapshot(user)
        embed = discord.Embed(
            title="Банк",
            description=(
                f"**Наличные:** {format_money(user.get('balance', 0))}\n"
                f"**Банковский счёт:** {format_money(user.get('bank', 0))}"
            ),
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )

        if not snapshot["active"]:
            deposit_text = (
                "**Активный депозит:** нет\n"
                "**Ставки:** 1 день = 2% • 3 дня = 7% • 7 дней = 20%\n"
                f"**Штраф за моментальный вывод:** {int(EARLY_WITHDRAW_PENALTY * 100)}% от суммы"
            )
        else:
            status = "Созрел" if snapshot["matured"] else format_discord_deadline(snapshot["matures_at"])
            deposit_text = (
                f"**Сумма:** {format_money(snapshot['amount'])}\n"
                f"**Процент:** {snapshot['rate'] * 100:.0f}%\n"
                f"**Срок:** {snapshot['days']} дн.\n"
                f"**До завершения:** {status}\n"
                f"**Штраф за моментальный вывод:** -{format_money(snapshot['early_penalty'])}\n"
                f"**К выплате при завершении:** {format_money(snapshot['normal_payout'])}"
            )
        embed.add_field(name="Депозит", value=deposit_text, inline=False)
        embed.set_footer(text="Депозит открывается с банковского счёта.")
        return embed

    def sync_buttons(self):
        snapshot = deposit_snapshot(self.user_data or {})
        if not snapshot["active"]:
            self.deposit_action.label = "🏦 Депозит"
            self.deposit_action.style = discord.ButtonStyle.success
        elif snapshot["matured"]:
            self.deposit_action.label = "✅ Забрать депозит"
            self.deposit_action.style = discord.ButtonStyle.success
        else:
            self.deposit_action.label = "📤 Вывести из депозита"
            self.deposit_action.style = discord.ButtonStyle.danger

    async def refresh_message(self):
        await self.reload_user()
        self.sync_buttons()
        if self.message is not None:
            try:
                await self.message.edit(embed=self.build_embed(), view=self)
            except Exception:
                pass

    async def close_deposit(self, *, early: bool) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(self.user_id):
            user = await db.get_user(self.user_id, self.guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            snapshot = deposit_snapshot(user)
            if not snapshot["active"]:
                return False, "У тебя нет активного депозита."

            if not early and not snapshot["matured"]:
                return False, "Депозит ещё не созрел."

            if early:
                payout = snapshot["early_payout"]
                description = (
                    f"Возвращено на банковский счёт: **{format_money(payout)}**\n"
                    f"Штраф: **-{format_money(snapshot['early_penalty'])}**\n"
                    "Проценты сгорели полностью."
                )
                color = COLORS["warning"]
                title = "Депозит выведен досрочно"
            else:
                payout = snapshot["normal_payout"]
                description = (
                    f"Возвращено на банковский счёт: **{format_money(payout)}**\n"
                    f"Чистая прибыль: **{format_money(snapshot['normal_profit'])}**"
                )
                color = COLORS["success"]
                title = "Депозит закрыт"

            user["bank"] = int(user.get("bank", 0) or 0) + payout
            user["deposit_amount"] = 0
            user["deposit_rate"] = 0
            user["deposit_days"] = 0
            user["deposit_start"] = None

            await db.update_user(
                self.user_id,
                self.guild_id,
                {
                    "bank": user["bank"],
                    "deposit_amount": 0,
                    "deposit_rate": 0,
                    "deposit_days": 0,
                    "deposit_start": None,
                },
            )
            self.user_data = user

        embed = discord.Embed(
            title=title,
            description=f"{description}\nБанк: **{format_money(self.user_data['bank'])}**",
            color=color,
        )
        return True, embed

    @discord.ui.button(label="💰 Пополнить", style=discord.ButtonStyle.primary, row=0)
    async def deposit_bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BankAmountModal(self, "deposit_bank"))

    @discord.ui.button(label="💸 Снять", style=discord.ButtonStyle.primary, row=0)
    async def withdraw_bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BankAmountModal(self, "withdraw_bank"))

    @discord.ui.button(label="🏦 Депозит", style=discord.ButtonStyle.success, row=0)
    async def deposit_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.reload_user()
            self.sync_buttons()
            snapshot = deposit_snapshot(self.user_data)
            if not snapshot["active"]:
                await interaction.response.send_message(
                    "Выбери срок депозита. После выбора откроется окно для ввода суммы.",
                    view=DepositTermView(self),
                    ephemeral=True,
                )
                return

            if snapshot["matured"]:
                success, payload = await self.close_deposit(early=False)
                if not success:
                    await interaction.response.send_message(str(payload), ephemeral=True)
                    return
                await interaction.response.send_message(embed=payload, ephemeral=True)
                await self.refresh_message()
                return

            await interaction.response.send_message(
                (
                    f"Ты собираешься вывести депозит досрочно.\n"
                    f"Штраф: **-{format_money(snapshot['early_penalty'])}**\n"
                    "Проценты будут потеряны полностью."
                ),
                view=EarlyWithdrawConfirmView(self),
                ephemeral=True,
            )

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await interaction.response.defer()
            await self.reload_user()
            self.sync_buttons()
            await interaction.edit_original_response(embed=self.build_embed(), view=self)
            self.message = await remember_interaction_message(interaction, self.message)

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message)


class BankCog(commands.Cog, name="Bank"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bank", description="Открыть банковский интерфейс")
    async def bank(self, interaction: discord.Interaction, player: discord.Member | None = None):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        target = player or interaction.user
        user = await db.get_user(target.id, interaction.guild_id)
        if not user:
            await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
            return

        if target.id != interaction.user.id:
            await interaction.response.send_message(embed=build_bank_embed(user, member=target, read_only=True))
            return

        view = BankView(interaction.user.id, interaction.guild_id, user)
        await interaction.response.send_message(embed=view.build_embed(), view=view)
        view.message = await interaction.original_response()

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
                if sender is None or int(sender.get("balance", 0) or 0) < amount:
                    await interaction.response.send_message(
                        f"Не хватает денег. Баланс: {format_money(sender.get('balance', 0) if sender else 0)}",
                        ephemeral=True,
                    )
                    return
                receiver = await db.get_user(recipient.id, interaction.guild_id)
                if receiver is None:
                    await interaction.response.send_message("Не удалось загрузить получателя.", ephemeral=True)
                    return

                sender["balance"] = int(sender.get("balance", 0) or 0) - amount
                receiver["balance"] = int(receiver.get("balance", 0) or 0) + amount
                await db.update_user(interaction.user.id, interaction.guild_id, {"balance": sender["balance"]})
                await db.update_user(recipient.id, interaction.guild_id, {"balance": receiver["balance"]})

        embed = discord.Embed(
            title="Перевод выполнен",
            description=(
                f"От: {interaction.user.mention}\n"
                f"Кому: {recipient.mention}\n"
                f"Сумма: **{format_money(amount)}**"
            ),
            color=COLORS["success"],
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(BankCog(bot))
