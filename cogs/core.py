from discord.ext import commands


class CoreCog(commands.Cog, name="Core"):
    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(CoreCog(bot))
