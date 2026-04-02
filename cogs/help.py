import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS
from utils import check_channel, send_wrong_channel_message


def _build_info_embed(title: str, description: str, color: int) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="HO Help")
    return embed


class HoHelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Экономика", style=discord.ButtonStyle.primary, row=0)
    async def economy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Экономика и профиль",
            (
                "`/profile`, `/stats`, `/rank`, `/top`\n"
                "`/daily`, `/hourly`, `/work`, `/crime`, `/slut`\n"
                "`/bank`, `/transfer`\n\n"
                "Баланс, банк, заработок, профиль и таблицы лидеров."
            ),
            COLORS["gold"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Игры", style=discord.ButtonStyle.success, row=0)
    async def games_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Игры и PvP",
            (
                "`/blackjack`, `/bj`, `/roulette`, `/slots`, `/dice`\n"
                "`/steal`, `/duel`\n"
                "`/cases`, `/opencase`, `/fortunewheel`\n"
                "`/lottery`, `/buy_ticket`, `/draw_lottery`\n\n"
                "Казино-режимы, дуэли, кражи, кейсы и колесо фортуны."
            ),
            COLORS["success"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Рыбалка", style=discord.ButtonStyle.secondary, row=0)
    async def fishing_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Рыбалка и инвентарь",
            (
                "`/fish`, `/inventory`, `/timers`, `/shop`\n\n"
                "Удочки, снасти, наживка, споты, хот-споты, мир рыбалки, "
                "ивенты и весь улов в одном инвентаре."
            ),
            COLORS["info"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Дом", style=discord.ButtonStyle.danger, row=0)
    async def house_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Дом и майнинг",
            (
                "`/house`, `/shop`\n\n"
                "Недвижимость, аренда, огород, крипта, мебель и добыча."
            ),
            COLORS["warning"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Бизнес", style=discord.ButtonStyle.primary, row=1)
    async def business_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Бизнесы",
            (
                "`/businesses`, `/mybusinesses`\n\n"
                "Покупка бизнесов, сбор прибыли и управление улучшениями."
            ),
            COLORS["error"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Системы", style=discord.ButtonStyle.primary, row=1)
    async def systems_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Системы и события",
            (
                "`/contracts`, `/blackmarket`, `/updates`\n\n"
                "Контракты, черный рынок и свежие заметки об обновлениях."
            ),
            COLORS["purple"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Магазин", style=discord.ButtonStyle.secondary, row=1)
    async def shop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Магазин и сезон",
            (
                "`/shop`, `/battlepass`, `/bp`\n\n"
                "Главный магазин со вкладками VIP, обмена, рыбалки, недвижимости, садоводства, мебели и боевого пропуска."
            ),
            COLORS["info"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Комьюнити", style=discord.ButtonStyle.secondary, row=1)
    async def community_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = _build_info_embed(
            "Кланы и навигация",
            (
                "`/create_clan`, `/clan_info`, `/clan_invite`, `/hohelp`\n\n"
                "Клановые команды и быстрый возврат к общему меню бота."
            ),
            COLORS["success"],
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class HelpCog(commands.Cog, name="Help"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hohelp", description="Показать меню со всеми системами и командами бота")
    async def hohelp(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        bot_user = interaction.client.user or interaction.user
        embed = discord.Embed(
            title="HO Help",
            description=(
                "Здесь собраны все основные системы бота: экономика, игры, рыбалка, кейсы, "
                "бизнесы, дом, кланы, сезон и черный рынок.\n"
                "Нажми нужную кнопку ниже, чтобы быстро открыть список команд по разделу."
            ),
            color=COLORS["gold"],
        )
        embed.set_thumbnail(url=bot_user.display_avatar.url)
        embed.add_field(
            name="Что умеет бот",
            value=(
                "Экономика и банк\n"
                "Казино-игры и PvP\n"
                "Рыбалка с инвентарем и мировыми событиями\n"
                "Кейсы, лотерея и черный рынок\n"
                "Дома, бизнесы, кланы и сезонный пропуск"
            ),
            inline=False,
        )
        embed.add_field(
            name="Быстрый старт",
            value=(
                "`/profile`, `/shop`, `/battlepass`\n"
                "`/fish`, `/inventory`, `/cases`\n"
                "`/businesses`, `/house`, `/contracts`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Разделы",
            value="Экономика | Игры | Рыбалка | Дом | Бизнес | Системы | Магазин | Комьюнити",
            inline=False,
        )
        embed.set_footer(text="Открой нужный раздел кнопками ниже")
        await interaction.response.send_message(embed=embed, view=HoHelpView())


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
