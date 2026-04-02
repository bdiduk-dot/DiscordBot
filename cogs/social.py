import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from config import COLORS, EMOJI, get_vip_level
from database import db, get_user_lock
from utils import add_xp, check_channel, create_embed, format_discord_deadline, has_active_shield, schedule_message_cleanup, send_wrong_channel_message


class DuelView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, guild_id: int, bet: int):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.guild_id = guild_id
        self.bet = bet
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in {self.challenger.id, self.opponent.id}:
            await interaction.response.send_message("This duel is not yours.", ephemeral=True)
            return False
        return True

    def _lock_pair(self):
        first_id, second_id = sorted((self.challenger.id, self.opponent.id))
        return get_user_lock(first_id), get_user_lock(second_id)

    def _disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged player can accept.", ephemeral=True)
            return

        first_lock, second_lock = self._lock_pair()
        async with first_lock:
            async with second_lock:
                challenger_user = await db.get_user(self.challenger.id, self.guild_id)
                opponent_user = await db.get_user(self.opponent.id, self.guild_id)

                if challenger_user['balance'] < self.bet or opponent_user['balance'] < self.bet:
                    self._disable_all()
                    await interaction.response.edit_message(
                        content="The duel expired because one player no longer has enough money.",
                        embed=None,
                        view=self,
                    )
                    self.message = interaction.message or self.message
                    schedule_message_cleanup(self.message)
                    self.stop()
                    return

                challenger_roll = random.randint(1, 100)
                opponent_roll = random.randint(1, 100)

                if challenger_roll == opponent_roll:
                    self._disable_all()
                    await interaction.response.edit_message(
                        content=(
                            f"Duel between {self.challenger.mention} and {self.opponent.mention} ended in a draw.\n"
                            f"Rolls: `{challenger_roll}` vs `{opponent_roll}`"
                        ),
                        embed=None,
                        view=self,
                    )
                    self.message = interaction.message or self.message
                    schedule_message_cleanup(self.message)
                    self.stop()
                    return

                challenger_wins = challenger_roll > opponent_roll
                winner = self.challenger if challenger_wins else self.opponent
                loser = self.opponent if challenger_wins else self.challenger
                winner_user = challenger_user if challenger_wins else opponent_user
                loser_user = opponent_user if challenger_wins else challenger_user

                winner_user['balance'] += self.bet
                loser_user['balance'] -= self.bet

                await db.update_user(winner.id, self.guild_id, winner_user)
                await db.update_user(loser.id, self.guild_id, loser_user)

        await add_xp(winner.id, self.guild_id, 50)

        self._disable_all()
        await interaction.response.edit_message(
            content=(
                f"{winner.mention} won the duel and took **${self.bet:,}**.\n"
                f"Rolls: `{challenger_roll}` vs `{opponent_roll}`"
            ),
            embed=None,
            view=self,
        )
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.secondary, row=0)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged player can decline.", ephemeral=True)
            return

        self._disable_all()
        await interaction.response.edit_message(
            content=f"{self.opponent.mention} declined the duel from {self.challenger.mention}.",
            embed=None,
            view=self,
        )
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)
        self.stop()

    async def on_timeout(self):
        self._disable_all()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message)


class SocialCog(commands.Cog, name="Social"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="steal", description="Steal money from another player")
    async def steal(self, interaction: discord.Interaction, target: discord.Member):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if target.bot or target.id == interaction.user.id:
            await interaction.response.send_message("Choose another real player.", ephemeral=True)
            return

        first_id, second_id = sorted((interaction.user.id, target.id))
        async with get_user_lock(first_id):
            async with get_user_lock(second_id):
                thief = await db.get_user(interaction.user.id, interaction.guild_id)
                victim = await db.get_user(target.id, interaction.guild_id)
                now = datetime.now(timezone.utc)

                vip = get_vip_level(thief.get('vip_level', 0))
                cooldown_hours = max(1, int(2 * (1 - vip['cooldown_reduction'])))

                if thief.get('last_steal'):
                    last_steal = datetime.fromisoformat(thief['last_steal']).replace(tzinfo=timezone.utc)
                    if now - last_steal < timedelta(hours=cooldown_hours):
                        next_steal_at = last_steal + timedelta(hours=cooldown_hours)
                        await interaction.response.send_message(
                            embed=create_embed(
                                f"{EMOJI['steal']} Кража",
                                f"Кулдаун активен. Следующая попытка {format_discord_deadline(next_steal_at)}.",
                                COLORS['warning'],
                            ),
                            ephemeral=True,
                        )
                        return

                if victim['balance'] < 100:
                    await interaction.response.send_message("Target is too poor right now.", ephemeral=True)
                    return

                success_chance = max(
                    0.30,
                    min(0.80, 0.60 + (thief.get('level', 1) - victim.get('level', 1)) * 0.02),
                )
                thief['last_steal'] = now.isoformat()

                if random.random() < success_chance:
                    stolen = max(100, int(victim['balance'] * random.uniform(0.10, 0.30)))
                    stolen = min(stolen, victim['balance'])
                    victim['balance'] -= stolen
                    thief['balance'] += stolen
                    await db.update_user(interaction.user.id, interaction.guild_id, thief)
                    await db.update_user(target.id, interaction.guild_id, victim)
                    result_embed = create_embed(
                        f"{EMOJI['steal']} Steal",
                        (
                            f"Success. You stole **${stolen:,}** from {target.mention}.\n"
                            f"New balance: **${thief['balance']:,}**"
                        ),
                        COLORS['success'],
                    )
                    won = True
                else:
                    shielded = has_active_shield(thief)
                    fine = 0 if shielded else min(random.randint(200, 500), thief['balance'])
                    thief['balance'] -= fine
                    await db.update_user(interaction.user.id, interaction.guild_id, thief)
                    if shielded:
                        result_embed = create_embed(
                            f"{EMOJI['steal']} Steal",
                            "Your shadow insurance absorbed the failed heist penalty.",
                            COLORS['warning'],
                        )
                    else:
                        result_embed = create_embed(
                            f"{EMOJI['steal']} Steal",
                            f"You were caught and paid a fine of **${fine:,}**.",
                            COLORS['error'],
                        )
                    won = False

        if won:
            await add_xp(interaction.user.id, interaction.guild_id, 50)

        await interaction.response.send_message(embed=result_embed)

    @app_commands.command(name="duel", description="Challenge another player to a money duel")
    async def duel(self, interaction: discord.Interaction, opponent: discord.Member, bet: int):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if opponent.bot or opponent.id == interaction.user.id or bet <= 0:
            await interaction.response.send_message("Pick a valid player and a positive bet.", ephemeral=True)
            return

        challenger_user = await db.get_user(interaction.user.id, interaction.guild_id)
        opponent_user = await db.get_user(opponent.id, interaction.guild_id)

        if challenger_user['balance'] < bet:
            await interaction.response.send_message("You do not have enough money for that duel.", ephemeral=True)
            return

        if opponent_user['balance'] < bet:
            await interaction.response.send_message("That player cannot cover the duel bet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Player Duel",
            description=(
                f"{interaction.user.mention} challenged {opponent.mention}.\n\n"
                f"Pot: **${bet:,}**\n"
                f"Winner takes the full amount from the loser."
            ),
            color=COLORS['gold'],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Challenge expires in 60 seconds.")

        view = DuelView(interaction.user, opponent, interaction.guild_id, bet)
        await interaction.response.send_message(
            embed=embed,
            view=view,
        )
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(SocialCog(bot))
