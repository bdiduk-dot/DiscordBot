from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-05-fastfix-1"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "Обновления"
LATEST_UPDATE_TEXT = """
**fastFIX**
• `/shop` → `Обмен валют`: возвращён прежний порядок обмена. Первая кнопка снова открывает `Гемы -> деньги`, вторая — `Деньги -> гемы`, и действия под кнопками теперь совпадают с подписями.
• `/work`, `/fish`, `/crime`, `/daily` и бонусный пасхальный дроп снова показывают русские сообщения о яйцах и сундуках вместо `Egg Hunt`.
• `/house` и вкладка обустройства снова говорят по-русски: покупка мебели, отложенная мебель в инвентаре, пасхальный декор и список установленной мебели.
• Пасхальная коллекция теперь стабильно засчитывает Пасхальный сундук, даже если он уже был открыт, а награда за коллекцию больше не ломает прогресс.
• Исправлена выдача награды за победу в `blackjack`: баланс и выплата теперь корректно сохраняются после выигрыша.

**fastUPD**
• В доме добавлено отдельное отображение мебели: обычная, пасхальная и та, что ещё лежит в инвентаре до установки.
• Разрешена предварительная покупка одного предмета мебели без дома: после покупки дома он ставится через инвентарь.
• Пасхальные кейсы и сундуки теперь везде идут как инвентарные предметы: из магазина, общего пасхального дропа и бонусного пруда.
• В `/easter` добавлена подсказка, что Кроличий талисман выпадает из Пасхального сундука с шансом `8%`.
• Для старых пасхальных предметов и мебели добавлена миграция legacy-структуры, чтобы корзина, декор и старая мебель корректно подхватывались новым инвентарём и домом.
"""


def _split_update_text(text: str, limit: int = 3800) -> list[str]:
    raw = text.strip()
    if not raw:
        return []

    lines = raw.splitlines()
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
    return chunks


def build_update_embeds() -> list[discord.Embed]:
    chunks = _split_update_text(LATEST_UPDATE_TEXT)
    if not chunks:
        return []

    embeds: list[discord.Embed] = []
    for index, chunk in enumerate(chunks, start=1):
        title = UPDATE_TITLE if index == 1 else f"{UPDATE_TITLE} • продолжение {index}/{len(chunks)}"
        embed = discord.Embed(
            title=title,
            description=chunk,
            color=COLORS["easter"],
        )
        embed.set_footer(text=f"Update ID: {LATEST_UPDATE_ID}")
        embeds.append(embed)
    return embeds


def build_update_embed() -> discord.Embed:
    embeds = build_update_embeds()
    if embeds:
        return embeds[0]
    return discord.Embed(
        title=UPDATE_TITLE,
        description="Сейчас нет опубликованного текста обновления.",
        color=COLORS["easter"],
    )
