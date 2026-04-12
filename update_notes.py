from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-12-upd-main-transition"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🌱 Переход после Easter 2026"
FAST_UPDATE_TITLE = "⚡ fastFIX / переход"

LATEST_UPDATE_TEXT = """
> Основной бот подготовлен к мягкому переходу после Easter Event 2026. Прогресс игроков сохраняется, а оставшиеся пасхальные предметы больше не ломают повседневный геймплей.

## 📦 Что сохраняется
▸ Баланс, гемы, уровень, инвентарь, дома, бизнесы и остальной основной прогресс остаются без сброса
▸ Памятные Easter-трофеи, титулы, темы и другие постоянные награды никуда не исчезают
▸ Общий профиль игрока продолжает работать на разных серверах, а не живёт отдельно в каждой гильдии

## 🐣 Что происходит с Easter после перехода
▸ Easter-ивент считается завершённым и больше не должен снова запускаться сам по себе
▸ Оставшиеся пасхальные предметы воспринимаются как архивные
▸ Если игрок нажмёт на старый Easter-предмет в инвентаре, бот теперь объяснит, что ивент уже закрыт, вместо немого отказа

## ⚙️ Стабильность после переключения
▸ `/profile -> Настройки` работает стабильно и не падает при открытии
▸ Серверные настройки по каналу и роли продолжают работать через `guild_settings`
▸ После переключения на `main` не требуется отдельная ручная чистка Easter-данных в профилях игроков

## 🚀 Что это значит дальше
▸ `main` готова быть базой для следующего большого апдейта
▸ Easter-прогресс не мешает обычной игре
▸ Можно спокойно переходить к разработке `3.0`, не ломая старые профили
"""

LATEST_FAST_TEXT = """
**fastFIX**
• `/profile -> Настройки`: кнопка настроек и возврат в профиль работают без падения view.
• Easter по умолчанию переведён в архивный режим, чтобы старый ивент не активировался повторно после смены ветки.
• Архивные Easter-предметы в `/inventory` больше не упираются в сухое «предмет нельзя использовать» и теперь дают понятное объяснение.

**Переход**
• Профиль игрока остаётся общим между серверами: деньги, уровень, инвентарь и основной прогресс синхронизируются по `user_id`.
• Постоянные Easter-награды сохраняются, а архивные остатки ивента не мешают обычной игре.
• `main` подготовлена как безопасная точка входа перед началом обновления `3.0`.
"""

ARCHIVED_UPDATE_TEXT = LATEST_UPDATE_TEXT
ARCHIVED_FAST_TEXT = LATEST_FAST_TEXT


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
            color=COLORS["info"],
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
    return embeds[0] if embeds else discord.Embed(title=UPDATE_TITLE, description="Сейчас нет опубликованного текста обновления.", color=COLORS["info"])


def build_fast_update_embed() -> discord.Embed:
    embeds = build_fast_update_embeds()
    return embeds[0] if embeds else discord.Embed(title=FAST_UPDATE_TITLE, description="Сейчас нет опубликованного блока fastFIX / переход.", color=COLORS["info"])
