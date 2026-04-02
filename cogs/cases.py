import asyncio
import random
from datetime import datetime, timedelta, timezone
from textwrap import shorten
import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS
from database import db, get_user_lock
from inventory_system import add_general_item, consume_case_item
from utils import check_channel, check_quest_progress, format_discord_deadline, get_kyiv_timezone, send_wrong_channel_message

KYIV_TZ = get_kyiv_timezone()


LOOTBOXES = {
    'common': {
        'name': 'Обычный кейс',
        'price': 5000,
        'emoji': '[C]',
        'color': 0x95A5A6,
        'prizes': [
            {'name': '$1,000', 'type': 'money', 'value': 1000, 'weight': 30},
            {'name': '$2,500', 'type': 'money', 'value': 2500, 'weight': 25},
            {'name': '$5,000', 'type': 'money', 'value': 5000, 'weight': 15},
            {'name': '$10,000', 'type': 'money', 'value': 10000, 'weight': 8},
            {'name': '5 гемов', 'type': 'gems', 'value': 5, 'weight': 20},
            {'name': '15 гемов', 'type': 'gems', 'value': 15, 'weight': 10},
            {'name': '30 гемов', 'type': 'gems', 'value': 30, 'weight': 3},
            {'name': 'x2 опыта (1ч)', 'type': 'buff_xp', 'value': 1, 'weight': 7},
            {'name': 'x2 денег (1ч)', 'type': 'buff_money', 'value': 1, 'weight': 5},
        ],
    },
    'rare': {
        'name': 'Редкий кейс',
        'price': 25000,
        'emoji': '[R]',
        'color': 0x9B59B6,
        'prizes': [
            {'name': '$10,000', 'type': 'money', 'value': 10000, 'weight': 25},
            {'name': '$25,000', 'type': 'money', 'value': 25000, 'weight': 20},
            {'name': '$50,000', 'type': 'money', 'value': 50000, 'weight': 10},
            {'name': '$100,000', 'type': 'money', 'value': 100000, 'weight': 3},
            {'name': '25 гемов', 'type': 'gems', 'value': 25, 'weight': 20},
            {'name': '50 гемов', 'type': 'gems', 'value': 50, 'weight': 10},
            {'name': '100 гемов', 'type': 'gems', 'value': 100, 'weight': 3},
            {'name': 'x2 опыта (3ч)', 'type': 'buff_xp', 'value': 3, 'weight': 5},
            {'name': 'x2 денег (3ч)', 'type': 'buff_money', 'value': 3, 'weight': 4},
        ],
    },
    'epic': {
        'name': 'Эпический кейс',
        'price': 100000,
        'emoji': '[E]',
        'color': 0xF1C40F,
        'prizes': [
            {'name': '$50,000', 'type': 'money', 'value': 50000, 'weight': 20},
            {'name': '$100,000', 'type': 'money', 'value': 100000, 'weight': 15},
            {'name': '$250,000', 'type': 'money', 'value': 250000, 'weight': 8},
            {'name': '$500,000', 'type': 'money', 'value': 500000, 'weight': 2},
            {'name': '100 гемов', 'type': 'gems', 'value': 100, 'weight': 15},
            {'name': '250 гемов', 'type': 'gems', 'value': 250, 'weight': 5},
            {'name': '500 гемов', 'type': 'gems', 'value': 500, 'weight': 2},
            {'name': 'x2 опыта (6ч)', 'type': 'buff_xp', 'value': 6, 'weight': 8},
            {'name': 'x2 денег (6ч)', 'type': 'buff_money', 'value': 6, 'weight': 5},
            {'name': 'VIP на 1 день', 'type': 'temp_vip', 'value': 1, 'weight': 3},
        ],
    },
    'legendary': {
        'name': 'Легендарный кейс',
        'price': 500000,
        'emoji': '[L]',
        'color': 0xE74C3C,
        'prizes': [
            {'name': '$250,000', 'type': 'money', 'value': 250000, 'weight': 15},
            {'name': '$500,000', 'type': 'money', 'value': 500000, 'weight': 12},
            {'name': '$1,000,000', 'type': 'money', 'value': 1000000, 'weight': 5},
            {'name': '$2,500,000', 'type': 'money', 'value': 2500000, 'weight': 1},
            {'name': '250 гемов', 'type': 'gems', 'value': 250, 'weight': 12},
            {'name': '500 гемов', 'type': 'gems', 'value': 500, 'weight': 8},
            {'name': '1000 гемов', 'type': 'gems', 'value': 1000, 'weight': 2},
            {'name': 'x2 опыта (24ч)', 'type': 'buff_xp', 'value': 24, 'weight': 6},
            {'name': 'x2 денег (24ч)', 'type': 'buff_money', 'value': 24, 'weight': 4},
            {'name': 'VIP на 3 дня', 'type': 'temp_vip', 'value': 3, 'weight': 3},
        ],
    },
}


WHEEL_PRIZES = [
    {'name': '$500', 'type': 'money', 'value': 500, 'emoji': '$', 'weight': 20},
    {'name': '$1,500', 'type': 'money', 'value': 1500, 'emoji': '$', 'weight': 15},
    {'name': '$5,000', 'type': 'money', 'value': 5000, 'emoji': '$', 'weight': 10},
    {'name': '$15,000', 'type': 'money', 'value': 15000, 'emoji': '$', 'weight': 5},
    {'name': '5 гемов', 'type': 'gems', 'value': 5, 'emoji': 'G', 'weight': 18},
    {'name': '20 гемов', 'type': 'gems', 'value': 20, 'emoji': 'G', 'weight': 8},
    {'name': '50 гемов', 'type': 'gems', 'value': 50, 'emoji': 'G', 'weight': 3},
    {'name': 'x2 опыта (1ч)', 'type': 'buff_xp', 'value': 1, 'emoji': 'XP', 'weight': 10},
    {'name': 'x2 опыта (3ч)', 'type': 'buff_xp', 'value': 3, 'emoji': 'XP', 'weight': 4},
    {'name': 'x2 денег (1ч)', 'type': 'buff_money', 'value': 1, 'emoji': 'M', 'weight': 8},
    {'name': 'x2 денег (3ч)', 'type': 'buff_money', 'value': 3, 'emoji': 'M', 'weight': 3},
    {'name': 'VIP на 1 день', 'type': 'temp_vip', 'value': 1, 'emoji': 'VIP', 'weight': 2},
    {'name': 'VIP на 3 дня', 'type': 'temp_vip', 'value': 3, 'emoji': 'VIP', 'weight': 1},
]


def apply_prize_to_user(user: dict, prize: dict, *, now: datetime | None = None):
    current_time = now or datetime.now(timezone.utc)

    if prize['type'] == 'money':
        user['balance'] = int(user.get('balance', 0) or 0) + int(prize['value'])
    elif prize['type'] == 'gems':
        user['gems'] = int(user.get('gems', 0) or 0) + int(prize['value'])
    elif prize['type'] == 'buff_xp':
        user['buff_xp_until'] = (current_time + timedelta(hours=prize['value'])).isoformat()
    elif prize['type'] == 'buff_money':
        user['buff_money_until'] = (current_time + timedelta(hours=prize['value'])).isoformat()
    elif prize['type'] == 'temp_vip':
        user['temp_vip_until'] = (current_time + timedelta(days=prize['value'])).isoformat()
        if int(user.get('vip_level', 0) or 0) < 1:
            user['vip_level'] = 1


async def apply_prize(user_id: int, guild_id: int, prize: dict):
    user = await db.get_user(user_id, guild_id)
    apply_prize_to_user(user, prize)
    await db.update_user(user_id, guild_id, user)


def roll_case_prize(case_id: str) -> dict:
    case = LOOTBOXES[case_id]
    return random.choices(case['prizes'], weights=[prize['weight'] for prize in case['prizes']], k=1)[0]


def build_case_result_embed(case_id: str, user: dict, prize: dict, *, source_label: str | None = None) -> discord.Embed:
    case = LOOTBOXES[case_id]
    rarity_name, rarity_label = get_rarity_info(prize['weight'])
    extra = ""
    if prize['type'] in ('buff_xp', 'buff_money'):
        extra = f"\nДлительность: **{prize['value']}ч**"
    elif prize['type'] == 'temp_vip':
        extra = f"\nДлительность: **{prize['value']} дн.**"

    result_embed = discord.Embed(
        title=f"{rarity_name} дроп!",
        color=COLORS['gold'] if prize['weight'] <= 5 else case['color'],
    )
    result_embed.add_field(
        name=f"{rarity_label} награда",
        value=f"**{prize['name']}**{extra}",
        inline=False,
    )
    result_embed.add_field(name="Кейс", value=case['name'], inline=True)
    result_embed.add_field(name="Баланс", value=f"**${int(user.get('balance', 0) or 0):,}**", inline=True)
    result_embed.add_field(name="Гемы", value=f"**{int(user.get('gems', 0) or 0)}**", inline=True)
    if source_label:
        result_embed.set_footer(text=source_label)
    return result_embed


async def play_case_opening_animation(
    interaction: discord.Interaction,
    case_id: str,
    prize: dict,
    user: dict,
    *,
    ephemeral: bool = False,
    source_label: str | None = None,
):
    case = LOOTBOXES[case_id]
    opening_embed = discord.Embed(
        title=f"Открываем {case['name']}",
        description=f"Цена: **${case['price']:,}**\n\n[ СЛОТ ] [ СЛОТ ] [ СЛОТ ]\n\nОткрытие...",
        color=case['color'],
    )

    message: discord.Message | None = None
    if interaction.response.is_done():
        try:
            message = await interaction.followup.send(embed=opening_embed, ephemeral=ephemeral, wait=True)
        except Exception:
            message = None
    else:
        await interaction.response.send_message(embed=opening_embed, ephemeral=ephemeral)
        try:
            message = await interaction.original_response()
        except Exception:
            message = None

    prizes = case['prizes']
    for frame in range(3):
        await asyncio.sleep(0.8)
        random_prizes = random.sample(prizes, min(3, len(prizes)))
        spin_display = " -> ".join(prize_item['name'].split(' ')[0] for prize_item in random_prizes)
        speed_text = ["Крутится...", "Замедляется...", "Почти..."][frame]
        frame_embed = discord.Embed(
            title=f"Открываем {case['name']}",
            description=f"Цена: **${case['price']:,}**\n\n{spin_display}\n\n{speed_text}",
            color=case['color'],
        )
        if message is not None:
            try:
                await message.edit(embed=frame_embed)
            except Exception:
                pass

    await asyncio.sleep(1.0)
    result_embed = build_case_result_embed(case_id, user, prize, source_label=source_label)
    if message is not None:
        try:
            await message.edit(embed=result_embed)
            return
        except Exception:
            pass

    if interaction.response.is_done():
        await interaction.followup.send(embed=result_embed, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(embed=result_embed, ephemeral=ephemeral)


async def open_case_from_inventory(
    interaction: discord.Interaction,
    *,
    user_id: int,
    guild_id: int,
    item_id: int | None = None,
    case_type: str | None = None,
    ephemeral: bool = False,
) -> tuple[bool, str | None]:
    if item_id is None and case_type is None:
        return False, "Не указан кейс для открытия."

    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return False, "Не удалось загрузить профиль."

        owned_case = consume_case_item(user, item_id=item_id, case_type=case_type)
        if owned_case is None:
            return False, "Кейс не найден в инвентаре. Сначала купи его через `/cases`."

        payload = owned_case.get("payload") if isinstance(owned_case.get("payload"), dict) else {}
        current_case_type = str(payload.get("case_type") or owned_case.get("code") or "")
        if current_case_type not in LOOTBOXES:
            return False, "Этот тип кейса больше не поддерживается."

        won_prize = roll_case_prize(current_case_type)
        apply_prize_to_user(user, won_prize)
        await db.update_user(
            user_id,
            guild_id,
            {
                "balance": user.get("balance", 0),
                "gems": user.get("gems", 0),
                "vip_level": user.get("vip_level", 0),
                "buff_xp_until": user.get("buff_xp_until"),
                "buff_money_until": user.get("buff_money_until"),
                "temp_vip_until": user.get("temp_vip_until"),
                "inventory": user.get("inventory"),
                "game_stats": user.get("game_stats", {}),
            },
        )

    await play_case_opening_animation(
        interaction,
        current_case_type,
        won_prize,
        user,
        ephemeral=ephemeral,
        source_label=f"Открыто из предмета инвентаря #{owned_case['id']}.",
    )
    return True, None


def get_rarity_info(weight: int):
    if weight <= 3:
        return "Легендарный", "ЛЕГ"
    if weight <= 5:
        return "Эпический", "ЭПИК"
    if weight <= 10:
        return "Редкий", "РЕДК"
    return "Обычный", "ОБЫЧ"


def get_wheel_rarity(weight: int):
    if weight <= 2:
        return "Джекпот", COLORS['gold'], "ДЖЕКПОТ"
    if weight <= 5:
        return "Редкий приз", COLORS['purple'], "РЕДКИЙ ПРИЗ"
    return "Приз", COLORS['success'], "ПРИЗ"


def format_wheel_line(prize: dict, width: int = 26) -> str:
    return shorten(f"{prize['emoji']} {prize['name']}", width=width, placeholder="...")


def build_wheel_block(window: list[dict], pointer_index: int = 1) -> str:
    width = 30
    border = "+" + "-" * (width + 8) + "+"
    lines = [border]
    for index, prize in enumerate(window):
        label = format_wheel_line(prize, width=width)
        marker_left = ">>" if index == pointer_index else "  "
        marker_right = "<<" if index == pointer_index else "  "
        lines.append(f"| {marker_left} {label:<{width}} {marker_right} |")
    lines.append(border)
    return "\n".join(lines)


def build_wheel_spin_embed(
    user: discord.abc.User,
    window: list[dict],
    step: int,
    total_steps: int,
    status_text: str,
    next_spin: datetime,
):
    filled = "#" * step
    remaining = "-" * (total_steps - step)
    embed = discord.Embed(
        title="КОЛЕСО ФОРТУНЫ",
        description="Стрелка ловит центральную дорожку.",
        color=COLORS['purple'],
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(
        name="Лента приза",
        value=f"```text\n{build_wheel_block(window)}\n```",
        inline=False,
    )
    embed.add_field(name="Разгон", value=f"`[{filled}{remaining}]`", inline=False)
    embed.add_field(name="Статус", value=status_text, inline=False)
    embed.set_footer(text=f"Следующий сброс: {format_discord_deadline(next_spin)}")
    return embed


def build_wheel_cooldown_embed(next_spin: datetime):
    embed = discord.Embed(
        title="🎡 КОЛЕСО ФОРТУНЫ",
        description="Сегодняшний спин уже использован.",
        color=COLORS['warning'],
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Следующий спин",
        value=format_discord_deadline(next_spin),
        inline=False,
    )
    return embed


def build_wheel_result_embed(user: discord.abc.User, user_data: dict, prize: dict, next_spin: datetime):
    rarity_name, color, banner = get_wheel_rarity(prize['weight'])
    extra = ""
    if prize['type'] == 'buff_xp':
        extra = f"\nБуст опыта активен на **{prize['value']}ч**"
    elif prize['type'] == 'buff_money':
        extra = f"\nБуст денег активен на **{prize['value']}ч**"
    elif prize['type'] == 'temp_vip':
        extra = f"\nVIP активен на **{prize['value']} дн.**"

    embed = discord.Embed(
        title=f"КОЛЕСО ФОРТУНЫ - {banner}",
        description=f"Колесо остановилось на награде уровня **{rarity_name.lower()}**.",
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    embed.add_field(
        name="Победная дорожка",
        value=f"```text\n>> {format_wheel_line(prize, 30):<30} <<\n```",
        inline=False,
    )
    embed.add_field(name="Приз", value=f"**{prize['name']}**{extra}", inline=False)
    embed.add_field(name="Деньги", value=f"**${user_data['balance']:,}**", inline=True)
    embed.add_field(name="Гемы", value=f"**{user_data['gems']}**", inline=True)
    embed.add_field(name="Следующий спин", value=format_discord_deadline(next_spin), inline=True)
    embed.set_footer(text="Заходи завтра за новой попыткой.")
    return embed


def build_case_menu_embed():
    embed = discord.Embed(
        title="Кейсы",
        description="Выбери кейс, чтобы посмотреть награды и отправить его в инвентарь.",
        color=0x2B2D31,
    )

    for case in LOOTBOXES.values():
        total_weight = sum(prize['weight'] for prize in case['prizes'])
        best_prize = min(case['prizes'], key=lambda prize: prize['weight'])
        best_chance = round(best_prize['weight'] / total_weight * 100, 1)
        embed.add_field(
            name=f"{case['emoji']} {case['name']}",
            value=(
                f"Цена: **${case['price']:,}**\n"
                f"Лучший приз: {best_prize['name']}\n"
                f"Лучший шанс: `{best_chance}%`"
            ),
            inline=True,
        )

    embed.set_footer(text="Используй кнопки ниже, чтобы открыть карточку кейса.")
    return embed


def build_case_detail_embed(case_id: str):
    case = LOOTBOXES[case_id]
    total_weight = sum(prize['weight'] for prize in case['prizes'])

    embed = discord.Embed(
        title=f"{case['emoji']} {case['name']}",
        description=f"Цена: **${case['price']:,}**",
        color=case['color'],
    )

    prize_lines = []
    for prize in sorted(case['prizes'], key=lambda item: item['weight']):
        chance = round(prize['weight'] / total_weight * 100, 1)
        rarity_name, rarity_label = get_rarity_info(prize['weight'])
        prize_lines.append(f"{rarity_label} {prize['name']} - `{chance}%` ({rarity_name})")

    embed.add_field(name="Возможные награды", value="\n".join(prize_lines), inline=False)
    embed.set_footer(text="Купи кейс в инвентарь, а потом открой его через /inventory или /opencase.")
    return embed


class CasesMenuView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню открыто не для тебя!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Обычный", style=discord.ButtonStyle.secondary, row=0)
    async def common_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_case_detail_embed('common'),
            view=CaseDetailView(self.user_id, 'common'),
        )

    @discord.ui.button(label="Редкий", style=discord.ButtonStyle.primary, row=0)
    async def rare_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_case_detail_embed('rare'),
            view=CaseDetailView(self.user_id, 'rare'),
        )

    @discord.ui.button(label="Эпический", style=discord.ButtonStyle.success, row=0)
    async def epic_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_case_detail_embed('epic'),
            view=CaseDetailView(self.user_id, 'epic'),
        )

    @discord.ui.button(label="Легендарный", style=discord.ButtonStyle.danger, row=0)
    async def legendary_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_case_detail_embed('legendary'),
            view=CaseDetailView(self.user_id, 'legendary'),
        )


class CaseDetailView(discord.ui.View):
    def __init__(self, user_id: int, case_id: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.case_id = case_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню открыто не для тебя!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Купить в инвентарь", style=discord.ButtonStyle.success, row=0)
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        case = LOOTBOXES[self.case_id]
        async with get_user_lock(interaction.user.id):
            user = await db.get_user(interaction.user.id, interaction.guild_id)
            if user['balance'] < case['price']:
                await interaction.response.send_message(
                    f"Не хватает денег. Нужно **${case['price']:,}**, у тебя **${user['balance']:,}**.",
                    ephemeral=True,
                )
                return

            user['balance'] -= case['price']
            inventory_item = add_general_item(
                user,
                item_type="case",
                code=self.case_id,
                name=case['name'],
                emoji=case['emoji'],
                description=f"Открой через `/inventory` или `/opencase {self.case_id}`.",
                payload={"case_type": self.case_id},
                stackable=True,
            )
            await db.update_user(
                interaction.user.id,
                interaction.guild_id,
                {
                    "balance": user['balance'],
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        confirmation = discord.Embed(
            title="Кейс отправлен в инвентарь",
            description=(
                f"Куплен **{case['name']}** за **${case['price']:,}**.\n"
                f"Предмет инвентаря: **#{inventory_item['id']}**\n"
                f"Открой его через `/inventory` или используй `/opencase {self.case_id}`."
            ),
            color=case['color'],
        )
        confirmation.add_field(name="Баланс", value=f"**${int(user['balance']):,}**", inline=True)
        confirmation.add_field(name="В инвентаре", value=f"**x{int(inventory_item.get('quantity', 1) or 1)}**", inline=True)
        await interaction.response.send_message(embed=confirmation, ephemeral=True)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_case_menu_embed(), view=CasesMenuView(self.user_id))


class AfterOpenView(discord.ui.View):
    def __init__(self, user_id: int, case_id: str):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.case_id = case_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню открыто не для тебя!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Открыть ещё", style=discord.ButtonStyle.success, row=0)
    async def again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=build_case_detail_embed(self.case_id),
            view=CaseDetailView(self.user_id, self.case_id),
        )

    @discord.ui.button(label="Все кейсы", style=discord.ButtonStyle.secondary, row=0)
    async def menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=build_case_menu_embed(), view=CasesMenuView(self.user_id))


class CasesCog(commands.Cog, name="Кейсы"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="cases", description="Открыть все доступные кейсы")
    async def cases(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        await interaction.response.send_message(
            embed=build_case_menu_embed(),
            view=CasesMenuView(interaction.user.id),
        )

    @app_commands.command(name="opencase", description="Открыть кейс напрямую")
    async def opencase(self, interaction: discord.Interaction, case_type: str):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        case_type = case_type.lower()
        if case_type not in LOOTBOXES:
            await interaction.response.send_message(
                "Неизвестный тип кейса. Доступно: `common`, `rare`, `epic`, `legendary`.",
                ephemeral=True,
            )
            return

        success, message = await open_case_from_inventory(
            interaction,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            case_type=case_type,
            ephemeral=False,
        )
        if not success and message:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="fortunewheel", description="Крутнуть ежедневное колесо фортуны")
    async def fortunewheel(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        now = datetime.now(timezone.utc)
        now_kyiv = now.astimezone(KYIV_TZ)

        if user.get('last_wheel'):
            try:
                last_spin = datetime.fromisoformat(user['last_wheel'])
                if last_spin.tzinfo is None:
                    last_spin = last_spin.replace(tzinfo=timezone.utc)
                else:
                    last_spin = last_spin.astimezone(timezone.utc)
            except ValueError:
                last_spin = None

            if last_spin and last_spin.astimezone(KYIV_TZ).date() == now_kyiv.date():
                next_spin = datetime.combine(
                    now_kyiv.date() + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=KYIV_TZ,
                )
                await interaction.response.send_message(
                    embed=build_wheel_cooldown_embed(next_spin),
                    ephemeral=True,
                )
                return

        await interaction.response.defer()

        won_prize = random.choices(WHEEL_PRIZES, weights=[prize['weight'] for prize in WHEEL_PRIZES], k=1)[0]
        next_spin = datetime.combine(
            now_kyiv.date() + timedelta(days=1),
            datetime.min.time(),
            tzinfo=KYIV_TZ,
        )
        total_steps = 6
        sequence = [random.choice(WHEEL_PRIZES) for _ in range(total_steps + 2)]
        sequence[total_steps] = won_prize
        step_delays = [0.15, 0.22, 0.3, 0.45, 0.65, 0.9]
        step_labels = [
            "Wheel released.",
            "Picking up speed.",
            "Crowd is watching.",
            "Slowing into the reward lane.",
            "Final alignment.",
            "Locked in.",
        ]

        await interaction.edit_original_response(
            embed=build_wheel_spin_embed(interaction.user, sequence[:3], 0, total_steps, "Wheel released.", next_spin)
        )

        for frame in range(total_steps):
            await asyncio.sleep(step_delays[frame])
            window = sequence[frame:frame + 3]
            embed = build_wheel_spin_embed(
                interaction.user,
                window,
                frame + 1,
                total_steps,
                step_labels[frame],
                next_spin,
            )
            try:
                await interaction.edit_original_response(embed=embed)
            except Exception:
                pass

        await asyncio.sleep(0.8)

        user['last_wheel'] = now.isoformat()
        await db.update_user(interaction.user.id, interaction.guild_id, user)

        await apply_prize(interaction.user.id, interaction.guild_id, won_prize)
        await check_quest_progress(interaction.user.id, interaction.guild_id, 'wheel', 1)
        user = await db.get_user(interaction.user.id, interaction.guild_id)
        await interaction.edit_original_response(
            embed=build_wheel_result_embed(interaction.user, user, won_prize, next_spin)
        )


async def setup(bot):
    await bot.add_cog(CasesCog(bot))

