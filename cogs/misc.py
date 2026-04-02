import discord
from discord import app_commands
from discord.ext import commands

from config import ADMIN_IDS, COLORS, RANKS, get_rank
from database import db
from utils import check_channel, create_embed, send_wrong_channel_message


def get_next_rank(balance: int):
    for rank_name, rank_data in sorted(RANKS.items(), key=lambda item: item[1]['min']):
        if rank_data['min'] > balance:
            return {'name': rank_name, **rank_data}
    return None


class MiscCog(commands.Cog, name="Misc"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="lottery", description="View the current lottery jackpot")
    async def lottery(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        jackpot = await db.get_lottery_jackpot(interaction.guild_id)
        await interaction.response.send_message(
            embed=create_embed(
                "Lottery",
                f"Current jackpot: **${jackpot:,}**\nBuy a ticket with `/buy_ticket` for **$100**.",
                COLORS['gold'],
            )
        )

    @app_commands.command(name="buy_ticket", description="Buy a lottery ticket for $100")
    async def buy_ticket(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if user['balance'] < 100:
            await interaction.response.send_message("You need $100 to buy a ticket.", ephemeral=True)
            return

        user['balance'] -= 100
        await db.update_user(interaction.user.id, interaction.guild_id, user)
        ticket_number = await db.buy_lottery_ticket(interaction.user.id, interaction.guild_id)

        if not ticket_number:
            await interaction.response.send_message("Failed to buy a ticket. Try again later.", ephemeral=True)
            return

        jackpot = await db.get_lottery_jackpot(interaction.guild_id)
        embed = discord.Embed(title="Lottery Ticket Purchased", color=COLORS['success'])
        embed.add_field(name="Ticket", value=f"**#{ticket_number}**", inline=True)
        embed.add_field(name="Jackpot", value=f"**${jackpot:,}**", inline=True)
        embed.add_field(name="Balance", value=f"**${user['balance']:,}**", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rank", description="View your current rank")
    async def rank_command(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        user = await db.get_user(interaction.user.id, interaction.guild_id)
        rank = get_rank(user['balance'])
        next_rank = get_next_rank(user['balance'])

        description = (
            f"Current rank: **{rank['name']}**\n"
            f"Dollars: **${user['balance']:,}**\n"
            f"Bonus multiplier: **x{rank['bonus']}**"
        )
        if next_rank:
            description += (
                f"\n\nNext rank: **{next_rank['name']}**\n"
                f"Needed: **${next_rank['min'] - user['balance']:,}** more"
            )
        else:
            description += "\n\nYou already reached the top rank."

        await interaction.response.send_message(
            embed=create_embed("Rank", description, rank['color'])
        )

    @app_commands.command(name="draw_lottery", description="[ADMIN] Draw the lottery winner")
    async def draw_lottery(self, interaction: discord.Interaction):
        if interaction.user.id not in ADMIN_IDS:
            await interaction.response.send_message("Admin only.", ephemeral=True)
            return

        result = await db.draw_lottery(interaction.guild_id)
        if not result:
            await interaction.response.send_message("No tickets were sold.", ephemeral=True)
            return

        winner = await db.get_user(result['winner_id'], interaction.guild_id)
        winner['balance'] += result['jackpot']
        await db.update_user(result['winner_id'], interaction.guild_id, winner)

        winner_user = self.bot.get_user(result['winner_id'])
        if winner_user is None:
            try:
                winner_user = await self.bot.fetch_user(result['winner_id'])
            except Exception:
                winner_user = None

        winner_label = winner_user.mention if winner_user else f"<@{result['winner_id']}>"
        embed = discord.Embed(title="Lottery Draw", color=COLORS['gold'])
        embed.add_field(name="Winner", value=winner_label, inline=False)
        embed.add_field(name="Ticket", value=f"**#{result['ticket_number']}**", inline=True)
        embed.add_field(name="Jackpot", value=f"**${result['jackpot']:,}**", inline=True)
        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(MiscCog(bot))
