from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-13-upd-3-0-foundation"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🧩 Обновление 3.0 • foundation"
FAST_UPDATE_TITLE = "⚡ fastFIX / 3.0 foundation"

ARCHIVED_UPDATE_TEXT = """
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

ARCHIVED_FAST_TEXT = """
**fastFIX**
• `/profile -> Настройки`: кнопка настроек и возврат в профиль работают без падения view.
• Easter по умолчанию переведён в архивный режим, чтобы старый ивент не активировался повторно после смены ветки.
• Архивные Easter-предметы в `/inventory` больше не упираются в сухое «предмет нельзя использовать» и теперь дают понятное объяснение.

**Переход**
• Профиль игрока остаётся общим между серверами: деньги, уровень, инвентарь и основной прогресс синхронизируются по `user_id`.
• Постоянные Easter-награды сохраняются, а архивные остатки ивента не мешают обычной игре.
• `main` подготовлена как безопасная точка входа перед началом обновления `3.0`.
"""

LATEST_UPDATE_TEXT = """
## Что добавлено
▸ В `/bank` добавлена кнопка **📜 История** с последними значимыми движениями по банку, депозитам и переводам.
▸ В кодовую базу добавлен foundation под `transactions` и подготовлен SQL-файл для таблиц `transactions`, `auction_listings`, `auction_bids`.
▸ В Battle Pass добавлены **кейс-награды** в free и premium ветках.
▸ За полное закрытие weekly-комплекта теперь может выдаваться **редкий кейс**.
▸ В `/daily` появились milestone-награды кейсами на серии `7 / 14 / 21 / 28`.
▸ В рулетке появился дополнительный шанс на кейс как часть 3.0 progression loop.

## Что переделано
▸ `/battlepass` и `/bp` больше не показывают одну длинную простыню текста.
▸ Боевой пропуск разделён на 3 панели:
▸ `Обзор`
▸ `Награды`
▸ `🎖️ Квесты`
▸ В панели `🎖️ Квесты` теперь отдельно видны BP-daily и weekly-прогресс сервера.
▸ `/fish` получил более современный главный экран: текущий спот, снасть, наживка, статус следующего заброса и последний улов теперь видны сразу.
▸ После улова в `/fish` появилась кнопка **`🎣 Закинуть снова`**, чтобы не переоткрывать меню каждый раз.
▸ Рыбные event window сообщения переделаны в формат карточек вида **`Ивент • ...`** и **`Ивент завершён • ...`**.
▸ Внутренняя дедупликация event window больше не завязана на debug/footer-маркеры для игрока.
▸ `/house` переработан по UX:
▸ вкладка `Крипта` упрощена и оставляет только действия по монетам и видеокартам
▸ добавлена отдельная вкладка **`Улучшения`**
▸ общие house-wide действия вроде апгрейда подвала и старого кошелька вынесены из `Крипта`

## Что убрано / архивировано
▸ Из вкладки `Крипта` убраны лишние служебные кнопки, которые не относятся напрямую к кошельку или GPU.
▸ Старый техничный стиль рыболовных event window с marker-like подачей больше не используется как пользовательский UI.
▸ Decor/house-wide действия перестали засорять крипто-экран и переехали в отдельную точку управления.

## Что исправлено
▸ Battle Pass награды, которые теперь выдают кейсы, корректно сохраняют `inventory` при клейме.
▸ История банка не ломается, даже если `public.transactions` ещё не докатан в Supabase: есть мягкий локальный резерв в `game_stats`.
▸ `/updates` продолжает использовать двухслойную модель:
▸ полный changelog
▸ отдельный блок `fastFIX / важное`

## Изменения экономики и баланса
▸ Кейсы встроены в progression loop, а не существуют отдельно от остальной игры.
▸ Источники кейсов на этой фазе:
▸ Battle Pass
▸ weekly completion
▸ daily streak milestones
▸ roulette drop chance
▸ Недельный кейс за full weekly set сейчас выдается как **редкий кейс**.

## Важно для игроков
▸ Кейсы из Battle Pass, weekly, daily streak и рулетки открываются через `/inventory`.
▸ Вкладка `Крипта` стала короче и понятнее: там теперь только монеты и видеокарты.
▸ Все общие улучшения дома ищите во вкладке **`Улучшения`**.
▸ Новый BP-интерфейс по-прежнему использует те же данные сезона, но показывает их заметно чище и быстрее читается.
"""

LATEST_FAST_TEXT = """
**UI / UX**
• `/battlepass` и `/bp` разделены на `Обзор`, `Награды`, `🎖️ Квесты`.
• `/fish` получил новый главный экран и кнопку `🎣 Закинуть снова` после улова.
• Рыболовные event window теперь оформляются как карточки `Ивент • ...`, без техничного footer-шума.
• `/house` получил новую вкладку `Улучшения`, а `Крипта` очищена от лишних служебных кнопок.

**Экономика**
• В `/bank` добавлена `📜 История`.
• Battle Pass теперь выдает кейсы в наградах.
• Weekly completion, roulette и daily streak milestones тоже подключены к кейсам.

**Foundation**
• Подготовлен SQL foundation под `transactions`, `auction_listings`, `auction_bids`.
• История банка умеет работать с локальным fallback, если таблица `transactions` ещё не создана в Supabase.
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
