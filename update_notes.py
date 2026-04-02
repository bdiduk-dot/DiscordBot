from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-03-fastfix-short-update"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🌐 Глобальное обновление 2.0"

LATEST_UPDATE_TEXT = """
> 2.0 уже в боте. Прогресс игроков сохранён, а ключевые системы стали чище, удобнее и понятнее.

## Что уже обновили
▸ Дома полностью заменили публичные квартиры без потери подвала, GPU, аренды, сада и накоплений
▸ `/house` стал главным экраном дома: `Дом`, `Сад`, `Крипта`, `Аренда`, `Обустройство`
▸ Крипта, огород, мебель, аренда и магазин собраны в более понятные экраны
▸ `/inventory`, `/profile`, `/bank`, `/top` и `/timers` получили более чистый и удобный интерфейс
▸ Теневая страховка снова работает в рискованных сценариях и показывает, когда спасает от штрафа
▸ Временные игровые и UI-сообщения теперь не висят лишнее время и автоматически убираются после неактива
▸ После рестарта бот публикует новое сообщение с обновлением в канал updates, удаляет старое и закрепляет новое

## Что добавим дальше
▸ Умные уведомления: бот будет писать, когда готов депозит, аренда, бизнес, урожай и когда daily streak почти сгорает
▸ `Blackjack` станет богаче по механикам, но останется простым по интерфейсу
▸ В `blackjack` появятся реальные фишки: `Удвоить`, `Сплит` и `Страховка`, если у дилера туз
"""


def _split_update_text(text: str, limit: int = 3800) -> list[str]:
    lines = text.strip().splitlines()
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        extra = len(line) + (1 if current else 0)
        if current and current_len + extra > limit:
            chunks.append("\n".join(current).strip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += extra

    if current:
        chunks.append("\n".join(current).strip())
    return chunks or [text[:limit]]


def build_update_embeds() -> list[discord.Embed]:
    chunks = _split_update_text(LATEST_UPDATE_TEXT)
    embeds: list[discord.Embed] = []

    for index, chunk in enumerate(chunks, start=1):
        title = UPDATE_TITLE if index == 1 else f"{UPDATE_TITLE} • продолжение {index}/{len(chunks)}"
        embed = discord.Embed(
            title=title,
            description=chunk,
            color=COLORS["info"],
        )
        embed.set_footer(text=f"Update ID: {LATEST_UPDATE_ID}")
        embeds.append(embed)

    return embeds


def build_update_embed() -> discord.Embed:
    return build_update_embeds()[0]
