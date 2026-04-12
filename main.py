import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.views import GamesMenuView, MainMenuView

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
LEGACY_COMMANDS = [
    "quest",
    "bankdep",
    "bankwith",
    "deposit",
    "withdraw_deposit",
    "leaderboard",
    "houseshop",
    "fishshop",
]


class CasinoBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self._views_registered = False
        self._slash_commands_synced = False

    def _register_persistent_views(self):
        if self._views_registered:
            return
        self.add_view(MainMenuView())
        self.add_view(GamesMenuView())
        self._views_registered = True

    async def sync_guild_commands(self, guild: discord.Guild):
        self.tree.clear_commands(guild=guild)
        self.tree.copy_global_to(guild=guild)
        for command_name in LEGACY_COMMANDS:
            self.tree.remove_command(command_name, guild=guild)
        await self.tree.sync(guild=guild)

    async def global_interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.command and interaction.command.name == "setting":
            return True
        if interaction.guild_id is None:
            return True
        from database import Database
        settings = await Database.get_guild_settings(interaction.guild_id)
        channel_id = settings.get("allowed_channel_id") if isinstance(settings, dict) else None
        if not channel_id:
            await interaction.response.send_message("Бот не настроен! Администратор должен использовать `/setting` и указать канал для работы бота.", ephemeral=True)
            return False
        if interaction.channel_id != int(channel_id):
            await interaction.response.send_message(f"Бот работает только в канале <#{channel_id}>.", ephemeral=True)
            return False
        return True

    async def setup_hook(self):
        self.tree.interaction_check = self.global_interaction_check
        cogs = [
            "cogs.core",
            "cogs.economy",
            "cogs.systems",
            "cogs.fishing",
            "cogs.business",
            "cogs.bank",
            "cogs.stats",
            "cogs.cases",
            "cogs.games_core",
            "cogs.social",
            "cogs.misc",
            "cogs.clans",
            "cogs.help",
            "cogs.updates",
            "cogs.mining",
            "cogs.house",
            "cogs.user",
            "cogs.shop",
            "cogs.inventory",
            "cogs.easter",
        ]

        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"Loaded {cog}")
            except Exception as exc:
                print(f"Failed to load {cog}: {exc}")

        self._register_persistent_views()
        for command_name in LEGACY_COMMANDS:
            self.tree.remove_command(command_name)


bot = CasinoBot()


@bot.event
async def on_ready():
    print(f"Bot started as {bot.user}")
    print(f"Guilds: {len(bot.guilds)}")

    bot._register_persistent_views()
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="/hohelp",
            )
        )
    except Exception as exc:
        print(f"Presence error: {exc}")

    if not bot._slash_commands_synced:
        try:
            global_commands = sorted(command.name for command in bot.tree.get_commands())
            print(f"Local commands before sync: {', '.join(global_commands)}")
            synced_guilds = 0
            for guild in bot.guilds:
                await bot.sync_guild_commands(guild)
                guild_commands = sorted(command.name for command in bot.tree.get_commands(guild=guild))
                print(f"Synced {guild.name} ({guild.id}): {', '.join(guild_commands)}")
                synced_guilds += 1

            # Keep slash-commands guild-scoped so Discord does not show duplicated
            # global + guild copies in the same server command picker.
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()
            bot._slash_commands_synced = True
            print(f"Synced guild slash commands on {synced_guilds} guild(s) and cleared global duplicates")
        except Exception as exc:
            print(f"Guild sync error: {exc}")

    # updates_cog = bot.get_cog("Updates")
    # if updates_cog is not None:
    #     try:
    #         await updates_cog.ensure_startup_post()
    #     except Exception as exc:
    #         print(f"Updates startup hook error: {exc}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        await bot.wait_until_ready()
        await bot.sync_guild_commands(guild)
        guild_commands = sorted(command.name for command in bot.tree.get_commands(guild=guild))
        print(f"Joined {guild.name} ({guild.id}) and synced: {', '.join(guild_commands)}")
    except Exception as exc:
        print(f"Guild join sync error for {guild.id}: {exc}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    try:
        await bot.wait_until_ready()
        await bot.sync_guild_commands(guild)
        guild_commands = sorted(command.name for command in bot.tree.get_commands(guild=guild))
        print(f"Joined {guild.name} ({guild.id}) and synced: {', '.join(guild_commands)}")
    except Exception as exc:
        print(f"Guild join sync error for {guild.id}: {exc}")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("DISCORD_BOT_TOKEN not found in .env")
    else:
        bot.run(DISCORD_TOKEN)
