from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-14-upd-3-0-bugfix-wave"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🛠️ Обновление 3.0 • bugfix wave"
FAST_UPDATE_TITLE = "⚡ fastFIX / 3.0 bugfix wave"

LATEST_UPDATE_TEXT = """
## Что исправлено
• Починен магазин снаряжения в **`/blackmarket`**:
• покупка больше не открывает то же окно как будто ничего не произошло
• после сделки показывается нормальное подтверждение покупки
• expedition gear теперь кладётся в инвентарь с правильным `item_type`
• коды `scuba_basic`, `scuba_reinforced`, `scuba_titan`, `abyss_lamp`, `excavation_kit`, `signal_scanner` синхронизированы с `/dive` и `/dig`

• Починен **`/inventory`** для general items:
• основной сценарий больше не завязан на ввод ID
• вместо этого работает выбор предмета через меню
• кнопка действия теперь меняется по типу предмета
• экспедиционное снаряжение больше не выглядит как “мертвый” предмет без применения

• Починена связка **инвентарь → `/dive` / `/dig`**:
• баллоны распознаются как `dive_tank`
• фонарик распознаётся как `dive_gear`
• набор археолога и сканер распознаются как `dig_tool`
• `/dig` больше не должен писать, что набора нет, если он реально куплен

• Починены **`/businesses`** и **`/mybusinesses`**:
• покупка бизнеса подтверждается повторной проверкой после записи в профиль
• сбор дохода перечитывает актуальное состояние после действия
• старые панели больше не должны визуально давать ложный повторный сбор
• добавлена более жёсткая stale-view защита для экранов бизнеса

• Починен **`/house`**:
• повторный найм уже активного арендатора блокируется стабильнее
• stale-панели аренды и дома перестают притворяться актуальными
• продажа GPU теперь дополнительно проверяется после записи
• после продажи карта не должна “возвращаться” на следующем обновлении экрана

• Починено восстановление после **Easter transition** в рыбалке:
• архивный спот `easter_rabbit_pond` автоматически сбрасывается на обычный валидный спот
• это состояние теперь сохраняется обратно в БД, а не только временно подменяется в embed
• legacy-наживка `festive` остаётся рабочей, если она ещё есть у игрока
• если пасхальная наживка больше невалидна, она снимается и не блокирует выбор обычной наживки

## Что переделано
• Рыболовное **ивент-окно** стало понятнее:
• описание теперь сразу объясняет, что меняется в окне
• добавлен аккуратный footer с понятным действием через `/fish`

• **Рыночные уведомления** стали чище:
• карточки сохраняют формат `Ивент • ...`
• у события теперь явный блок `Эффект`
• карточка подсказывает, где смотреть влияние мира сервера: `/blackmarket`, `/business`, `/fish`

• `update_notes.py` и `/updates` обновлены под текущую волну фиксов:
• отдельный блок про blackmarket equipment
• отдельный блок про inventory UX
• отдельный блок про Easter recovery
• отдельный блок про business / house crypto / GPU

## Что важно для игроков
• Если ты купил снаряжение в **`/blackmarket`**, оно должно сразу корректно работать в **`/inventory`**, **`/dive`** и **`/dig`**.
• Для general items теперь основной сценарий идёт через **меню выбора предметов**, а не через ручной ввод ID.
• Если после Easter у тебя был залипший спот или старая наживка, бот должен автоматически вернуть тебя в нормальный рабочий state.
• Если старая кнопка бизнеса, аренды или Battle Pass устарела, бот теперь должен просить открыть свежую панель вместо ложного повторного успеха.
"""

LATEST_FAST_TEXT = """
**blackmarket**
• Починена покупка expedition gear: предметы попадают в инвентарь с правильными типами.
• После покупки магазин даёт нормальное подтверждение, а не просто открывает тот же экран заново.

**inventory + expeditions**
• General items теперь выбираются через меню.
• `/dive` и `/dig` снова корректно видят купленное снаряжение.

**business + house**
• Усилена защита от повторных кликов по старым панелям бизнеса.
• Аренда и продажа GPU в `/house` стабильнее перечитывают актуальное состояние.

**easter recovery**
• Архивный Easter-спот больше не блокирует обычную рыбалку.
• Legacy-наживка `festive` работает корректно, если она ещё осталась у игрока.
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
    return embeds[0] if embeds else discord.Embed(title=FAST_UPDATE_TITLE, description="Сейчас нет опубликованного блока fastFIX / важное.", color=COLORS["info"])
