from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-10-upd-5-easter-part2"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🐣 Пасхальный ивент 2026 — Part 2"
FAST_UPDATE_TITLE = "⚡ fastFIX / fastUPD"

LATEST_UPDATE_TEXT = ""

LATEST_FAST_TEXT = ""

ARCHIVED_UPDATE_TEXT = """
> Пасхальный ивент получил вторую главу: новые долгие цели, секретную коллекцию и общий прогресс сервера.

## 📖 Глава 2
▸ Во вкладке `/easter` появилась отдельная `Глава 2`
▸ Цепочка состоит из 6 последовательных шагов:
　— заработать обычные яйца
　— половить в пасхальном пруду
　— открыть сундук
　— купить предмет в пасхальном магазине
　— сделать апгрейд валюты
　— получить награду при активном Золотом кролике
▸ Награда за полное прохождение:
　— `+50` гемов
　— трофей `Карта кроличьих следов`
　— открытие подсказок в `/eggcollection`

## 🌐 Прогресс сервера
▸ Во вкладке `/easter` появился `Прогресс сервера`
▸ Очки сервера копятся автоматически из пасхальных наград:
　— 🥚 = `1`
　— 🎨 = `25`
　— ✨ = `250`
▸ Этапы сервера:
　— `2,500` очков: `+5%` к шансу выпадения яиц
　— `7,500` очков: `+3%` к шансу пасхального сундука
　— `15,000` очков: открывается скрытый товар в магазине
　— `30,000` очков: `+10%` к деньгам с пасхальных бизнесов и `+10%` к цене рыбы из пасхального пруда

## 🥚 Secret Collection
▸ Добавлена отдельная команда `/eggcollection`
▸ В ней собираются 5 редких секретных яиц:
　— `Лунное яйцо`
　— `Шоколадное сердце`
　— `Яйцо кролика`
　— `Яйцо рассвета`
　— `Зеркальное яйцо`
▸ Награда за полную secret-коллекцию:
　— титул `Хранитель пасхальных тайн`
　— тема `moon_hare`
　— трофей `Запечатанное яйцо 2026`

## 👑 Hidden 100%
▸ Если закрыть обычную пасхальную коллекцию, `Главу 2`, `/eggcollection` и все этапы сервера, открывается hidden-награда:
　— `+200` гемов
　— титул `Архивариус весны`
　— трофей `Реликвия Золотого кролика`
"""

ARCHIVED_FAST_TEXT = """
**fastFIX**
• `/profile -> Настройки`: исправлен крэш `item would not fit at row ...`. Кнопка `Настройки` снова стабильно открывает личные настройки, а `Назад к профилю` корректно возвращает в тот же профиль.
• Добавлен `public/guild_settings.sql`, чтобы таблица серверных настроек создавалась сразу и не ломала multi-server режим после рестарта.
• `/work`, `/crime`, `/daily`, `/slut`, `blackjack`, бизнесы, аренда, `/fish` и открытие пасхального сундука переведены на новый Easter reward flow с серверными очками и скрытыми дропами.
• `/easter -> Бизнесы` и `/easter -> Мои бизнесы` теперь используют общий серверный state и не расходятся по логике с Part 2.

**fastUPD**
• `/easter` получил две новые вкладки: `Глава 2` и `Прогресс сервера`.
• Добавлена новая slash-команда `/eggcollection` для hidden-пасхальной коллекции.
• В ивент добавлены `5` secret-яиц с разными источниками: пруд ночью, сундук, Золотой кролик, утренние награды и обменник.
• В магазин встроен скрытый Part 2-товар, который открывается только на 3-м этапе серверного прогресса.
• Финал Easter теперь имеет полноценную hidden-награду за 100% прохождение всего ивента.
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


def _build_embeds(text: str, *, title: str) -> list[discord.Embed]:
    chunks = _split_update_text(text)
    embeds: list[discord.Embed] = []

    for index, chunk in enumerate(chunks, start=1):
        embed_title = title if index == 1 else f"{title} • продолжение {index}/{len(chunks)}"
        embed = discord.Embed(
            title=embed_title,
            description=chunk,
            color=COLORS["easter"],
        )
        embed.set_footer(text=f"Update ID: {LATEST_UPDATE_ID}")
        embeds.append(embed)

    return embeds


def build_update_embeds() -> list[discord.Embed]:
    return _build_embeds(LATEST_UPDATE_TEXT, title=UPDATE_TITLE)


def build_fast_update_embeds() -> list[discord.Embed]:
    return _build_embeds(LATEST_FAST_TEXT, title=FAST_UPDATE_TITLE)


def build_update_embed() -> discord.Embed:
    embeds = build_update_embeds()
    return embeds[0] if embeds else discord.Embed(title=UPDATE_TITLE, description="Сейчас нет опубликованного текста обновления.", color=COLORS["easter"])


def build_fast_update_embed() -> discord.Embed:
    embeds = build_fast_update_embeds()
    return embeds[0] if embeds else discord.Embed(title=FAST_UPDATE_TITLE, description="Сейчас нет опубликованного fastFIX / fastUPD блока.", color=COLORS["easter"])
