from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from update_notes import (
    UPDATE_CHANNEL_ID,
    UPDATE_PING_ROLE_ID,
    build_update_embeds,
)
from utils import check_channel, send_wrong_channel_message


class UpdatesCog(commands.Cog, name="Updates"):
    def __init__(self, bot):
        self.bot = bot
        self._startup_post_sent = False
        self._startup_lock = asyncio.Lock()
        self._startup_task: asyncio.Task[bool] | None = None

    async def _get_updates_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(UPDATE_CHANNEL_ID)
        if isinstance(channel, discord.TextChannel):
            return channel
        try:
            fetched = await self.bot.fetch_channel(UPDATE_CHANNEL_ID)
        except Exception:
            return None
        return fetched if isinstance(fetched, discord.TextChannel) else None

    @staticmethod
    def _is_update_message(message: discord.Message) -> bool:
        if not message.author.bot or not message.embeds:
            return False
        first_embed = message.embeds[0]
        footer_text = first_embed.footer.text if first_embed.footer else None
        return bool(footer_text and footer_text.startswith("Update ID: "))

    async def _pin_message(self, message: discord.Message) -> None:
        try:
            if not message.pinned:
                await message.pin(reason="Последние изменения бота")
        except Exception:
            pass

    async def _remove_old_update_messages(
        self,
        channel: discord.TextChannel,
        keep_message_id: int | None = None,
    ) -> None:
        seen_ids: set[int] = set()

        try:
            pinned_messages = await channel.pins()
        except Exception:
            pinned_messages = []

        for message in pinned_messages:
            if message.id in seen_ids:
                continue
            seen_ids.add(message.id)
            if message.id != keep_message_id and self._is_update_message(message):
                try:
                    await message.delete()
                except Exception:
                    try:
                        await message.unpin(reason="Оставляем только последнее сообщение с обновлением")
                    except Exception:
                        pass

        try:
            async for message in channel.history(limit=50):
                if message.id in seen_ids or message.id == keep_message_id:
                    continue
                seen_ids.add(message.id)
                if not self._is_update_message(message):
                    continue
                try:
                    await message.delete()
                except Exception:
                    continue
        except Exception:
            return

    async def _announce_updates(self) -> bool:
        channel = await self._get_updates_channel()
        if channel is None:
            print("Updates startup: channel not found or unavailable")
            return False

        desired_content = f"<@&{UPDATE_PING_ROLE_ID}>"
        desired_embeds = build_update_embeds()

        try:
            message = await channel.send(
                desired_content,
                embeds=desired_embeds,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except Exception as exc:
            print(f"Updates startup: failed to send update post: {exc}")
            return False

        await self._remove_old_update_messages(channel, keep_message_id=message.id)
        await self._pin_message(message)
        return True

    async def ensure_startup_post(self) -> bool:
        if self._startup_post_sent:
            return True

        async with self._startup_lock:
            if self._startup_post_sent:
                return True

            for attempt in range(1, 6):
                try:
                    await self.bot.wait_until_ready()
                    success = await self._announce_updates()
                except Exception as exc:
                    success = False
                    print(f"Updates startup: unexpected error on attempt {attempt}: {exc}")

                if success:
                    self._startup_post_sent = True
                    print(f"Updates startup: post ensured on attempt {attempt}")
                    return True

                if attempt < 5:
                    await asyncio.sleep(min(5 * attempt, 20))

            print("Updates startup: failed to ensure update post after retries")
            return False

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if self._startup_post_sent:
            return

        if self._startup_task is not None and not self._startup_task.done():
            return

        self._startup_task = asyncio.create_task(self.ensure_startup_post())

    @app_commands.command(name="updates", description="Показать последние изменения бота")
    async def updates(self, interaction: discord.Interaction) -> None:
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        await interaction.response.send_message(embeds=build_update_embeds())


async def setup(bot):
    await bot.add_cog(UpdatesCog(bot))
