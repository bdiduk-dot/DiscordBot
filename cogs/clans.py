import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import datetime, timezone

from config import COLORS, EMOJI
from database import db, supabase

class ClanInviteView(discord.ui.View):
    def __init__(self, member, user_clan):
        super().__init__(timeout=120)
        self.member = member
        self.user_clan = user_clan
    
    @discord.ui.button(label="Принять", style=discord.ButtonStyle.green, emoji="✅")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("❌ Это приглашение не для тебя!", ephemeral=True)
        
        members = self.user_clan.get('members', [])
        members.append(self.member.id)
        await asyncio.to_thread(lambda: supabase.table('clans').update({'members': members}).eq('id', self.user_clan['id']).execute())
        
        embed = discord.Embed(title="🏰 ВСТУПЛЕНИЕ В КЛАН", description=f"{self.member.mention} вступил в **{self.user_clan['name']}**!", color=COLORS['success'])
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.red, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("❌ Это приглашение не для тебя!", ephemeral=True)
        
        embed = discord.Embed(title="🏰 ПРИГЛАШЕНИЕ ОТКЛОНЕНО", description=f"{self.member.mention} отклонил приглашение.", color=COLORS['error'])
        await interaction.response.edit_message(embed=embed, view=None)

class ClanCog(commands.Cog, name="Clans"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="create_clan", description="Create a clan ($10,000)")
    async def create_clan(self, interaction: discord.Interaction, name: str):
        user = await db.get_user(interaction.user.id, interaction.guild_id)
        if user['balance'] < 10000:
            return await interaction.response.send_message("❌ Insufficient funds! Need $10,000", ephemeral=True)
        
        if not (3 <= len(name) <= 20):
            return await interaction.response.send_message("❌ Name must be 3-20 chars!", ephemeral=True)
            
        # Check if already in clan
        res = await asyncio.to_thread(lambda: supabase.table('clans').select('*').eq('guild_id', interaction.guild_id).execute())
        for clan in res.data:
            if interaction.user.id in clan.get('members', []):
                return await interaction.response.send_message("❌ You are already in a clan!", ephemeral=True)
            if clan['name'].lower() == name.lower():
                return await interaction.response.send_message("❌ Name taken!", ephemeral=True)
                
        clan_data = {
            'guild_id': interaction.guild_id, 'name': name, 'leader_id': interaction.user.id,
            'members': [interaction.user.id], 'balance': 0, 'level': 1, 'xp': 0,
            'upgrades': {'bank_capacity': 1, 'daily_bonus': 1, 'member_slots': 1},
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await asyncio.to_thread(lambda: supabase.table('clans').insert(clan_data).execute())
        user['balance'] -= 10000
        await db.update_user(interaction.user.id, interaction.guild_id, user)
        
        await interaction.response.send_message(embed=discord.Embed(title="🏰 CLAN CREATED!", description=f"👑 **{name}** created!", color=COLORS['gold']))

    @app_commands.command(name="clan_info", description="View clan info")
    async def clan_info(self, interaction: discord.Interaction, clan_name: str = None):
        res = await asyncio.to_thread(lambda: supabase.table('clans').select('*').eq('guild_id', interaction.guild_id).execute())
        clan = None
        if clan_name:
            clan = next((c for c in res.data if c['name'].lower() == clan_name.lower()), None)
        else:
            clan = next((c for c in res.data if interaction.user.id in c.get('members', [])), None)
            
        if not clan:
            return await interaction.response.send_message("❌ Clan not found!", ephemeral=True)
            
        upgrades = clan.get('upgrades', {})
        member_slots = upgrades.get('member_slots', 1) * 5
        embed = discord.Embed(title=f"🏰 {clan['name']}", color=COLORS['purple'])
        embed.add_field(name="📊 Level", value=f"{clan['level']} ({clan['xp']}/{clan['level']*1000} XP)")
        embed.add_field(name="💰 Bank", value=f"${clan.get('balance',0):,}")
        embed.add_field(name="👥 Members", value=f"{len(clan.get('members',[]))}/{member_slots}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="clan_invite", description="Invite to clan")
    async def clan_invite(self, interaction: discord.Interaction, member: discord.Member):
        res = await asyncio.to_thread(lambda: supabase.table('clans').select('*').eq('guild_id', interaction.guild_id).execute())
        user_clan = next((c for c in res.data if c['leader_id'] == interaction.user.id), None)
        if not user_clan: return await interaction.response.send_message("❌ Only leader can invite!", ephemeral=True)
        
        embed = discord.Embed(title="🏰 CLAN INVITE", description=f"{interaction.user.mention} invites {member.mention} to **{user_clan['name']}**", color=COLORS['info'])
        await interaction.response.send_message(embed=embed, view=ClanInviteView(member, user_clan))

async def setup(bot):
    await bot.add_cog(ClanCog(bot))
