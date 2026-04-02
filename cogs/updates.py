from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from update_notes import (
    LATEST_UPDATE_ID,
    UPDATE_CHANNEL_ID,
    UPDATE_PING_ROLE_ID,
    build_update_embed,
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
        return message.embeds[0].title == build_update_embed().title

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

    async def _find_latest_update_message(self, channel: discord.TextChannel) -> discord.Message | None:
        footer_text = f"Update ID: {LATEST_UPDATE_ID}"

        try:
            pinned_messages = await channel.pins()
        except Exception:
            pinned_messages = []

        for message in pinned_messages:
            if not self._is_update_message(message):
                continue
            embed = message.embeds[0]
            if embed.footer and embed.footer.text == footer_text:
                return message

        async for message in channel.history(limit=25):
            if not self._is_update_message(message):
                continue
            embed = message.embeds[0]
            if embed.footer and embed.footer.text == footer_text:
                return message
        return None

    async def _announce_updates(self) -> bool:
        channel = await self._get_updates_channel()
        if channel is None:
            print("Updates startup: channel not found or unavailable")
            return False

        desired_content = f"<@&{UPDATE_PING_ROLE_ID}>"
        desired_embed = build_update_embed()
        existing = await self._find_latest_update_message(channel)
        if existing is not None:
            current_embed = existing.embeds[0] if existing.embeds else None
            needs_refresh = (
                existing.content != desired_content
                or current_embed is None
                or current_embed.title != desired_embed.title
                or current_embed.description != desired_embed.description
                or (current_embed.footer.text if current_embed.footer else None) != (desired_embed.footer.text if desired_embed.footer else None)
            )
            if needs_refresh:
                try:
                    await existing.edit(
                        content=desired_content,
                        embed=desired_embed,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except Exception as exc:
                    print(f"Updates startup: failed to refresh existing post: {exc}")
                    existing = None
            if existing is not None:
                await self._pin_message(existing)
                await self._remove_old_update_messages(channel, keep_message_id=existing.id)
                return True

        try:
            message = await channel.send(
                desired_content,
                embed=desired_embed,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except Exception as exc:
            print(f"Updates startup: failed to send update post: {exc}")
            return False

        await self._pin_message(message)
        await self._remove_old_update_messages(channel, keep_message_id=message.id)
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

        await interaction.response.send_message(embed=build_update_embed())


async def setup(bot):
    await bot.add_cog(UpdatesCog(bot))
