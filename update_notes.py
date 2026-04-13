from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-13-upd-3-0-core-wave"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🧩 Обновление 3.0 • core wave"
FAST_UPDATE_TITLE = "⚡ fastFIX / 3.0 core wave"

ARCHIVED_UPDATE_TEXT = """
## Что было сделано на подготовительном этапе
• Ветка `test` приведена к стабильной базе после синхронизации с `main`.
• Пасхальный ивент переведён в архивный режим и больше не должен ломать обычный геймплей.
• Почищены шумные footer/debug-тексты, поправлены `guild_settings`, обновлены базовые everyday-системы.

## Что сохранилось
• Основной прогресс игроков, деньги, уровень, инвентарь, дома, бизнесы и сезонные данные не сбрасывались.
• Существующие системы `cases`, `/bp`, улучшенный `/fish`, `HouseV2` и прогрессия остались основой для 3.0.

## Что это означало для сервера
• `test` стала безопасной площадкой для развёртывания 3.0 без Easter-хвостов и без старых регрессий.
"""

ARCHIVED_FAST_TEXT = """
**phase 0**
• Стабильные фиксы из `main` перенесены в `test`.
• Easter переведён в архивный режим.
• `/setting`, `/profile`, `/shop` и базовые системные view очищены от старого шума.
"""

LATEST_UPDATE_TEXT = """
## Что добавлено
• Добавлены новые команды **`/dive`**, **`/dig`** и **`/auction`**.
• Введён полноценный **BlackMarket 2.0** с тремя разделами:
• `🛒 Экипировка`
• `🃏 Контрабанда`
• `🏺 Антиквар`
• Для `BlackMarket 2.0` добавлено новое снаряжение для экспедиций:
• баллоны на `100 / 200 / 300 O2`
• фонарик для глубинного дайва
• набор археолога
• сигнальный сканер
• В игру добавлен **Антиквар**:
• принимает лут из `/dive` и `/dig`
• использует ежедневные server-local цены
• умеет собирать цельные реликвии из фрагментов
• платит **x3** за собранную целую реликвию
• Добавлен рабочий **серверный аукцион**:
• `fixed-price`
• `auction`
• `auction + buyout`
• Добавлена инфраструктура для таблиц:
• `transactions`
• `auction_listings`
• `auction_bids`

## Что переделано
• `/battlepass` и `/bp` переделаны в компактный интерфейс из трёх панелей:
• `Обзор`
• `Награды`
• `🎖️ Квесты`
• Глобальные и рыночные уведомления переделаны в карточки формата **`Ивент • ...`** и **`Ивент завершён • ...`**.
• `/blackmarket` больше не ощущается старым текстовым списком: теперь это хаб с отдельными экранами по разделам.
• `/inventory` получил более читаемый карточный слой поверх старой логики:
• видны категории предметов
• быстрее понятен состав инвентаря
• появились подсказки по быстрым действиям
• `/profile` переделан в более аккуратную игровую визитку:
• ключевые деньги и активы остались компактными
• добавлен блок активных бафов
• добавлен краткий world-status сервера
• `/shop` собран в более цельную storefront-структуру:
• главный экран теперь выглядит как единая витрина
• разделы недвижимости, сада и декора получили свои более понятные карточки
• `/business` получил более живые панели:
• текущий рыночный тренд
• погода и время суток
• влияние мира сервера на доходность

## Что убрано / архивировано
• Убраны старые debug/footer-маркеры из event-уведомлений и рыночных сообщений.
• Старые legacy-paths чёрного рынка перестали быть основным пользовательским сценарием.
• Пасхальные хвосты из активного цикла окончательно оставлены в архивной части проекта.

## Что исправлено
• Исправлен визуальный баг Battle Pass, из-за которого награду можно было увидеть как повторно доступную после уже успешного клейма.
• Добавлен stale-view guard для старых BP-панелей: устаревшее сообщение теперь обновляется, а не показывает ложный повторный успех.
• Исправлен найм арендаторов в `/house`:
• в одной ротации больше не должны появляться одинаковые арендаторы
• повторно нанять уже активного арендатора через старую панель больше нельзя
• Исправлена подача `update_notes` и `/updates`: нормальная UTF-8 кодировка вместо битого текста.
• Дедупликация event/market уведомлений больше не завязана на пользовательский технический мусор в footer.

## Изменения экономики и баланса
• Мир сервера теперь сильнее влияет на экономику через один общий слой:
• глобальный ивент
• погода
• время суток
• Для `/dive` введён риск аварийного завершения:
• при провале или таймауте игрок сохраняет только **20%** стоимости ходки
• **80%** забирают спасатели
• Для `/dig` введён мягкий таймаут:
• уже извлечённый лут сохраняется
• незавершённая текущая точка теряется
• На аукционе:
• предмет сразу уходит в escrow
• предыдущий лидер получает auto-refund при перебитии ставки
• отмена после ставок запрещена
• settlement просроченных лотов идёт автоматически
• Кейсы окончательно встроены в progression-loop:
• Battle Pass
• weekly completion
• streak milestones `7 / 14 / 21 / 28`
• roulette drop chance

## Важно для игроков
• Лут из `/dive`, `/dig`, чёрного рынка и части новых систем сначала попадает в **`/inventory`**.
• Для продажи экспедиционного лута используй **`/blackmarket` → `🏺 Антиквар`**.
• На аукцион сейчас можно выставлять переносимые предметы из инвентаря:
• рыбу
• general items
• семена
• кейсы
• контрабанду
• артефакты
• неустановленную мебель
• На аукцион нельзя выставлять state-based сущности без предмета в инвентаре:
• уже установленную мебель
• активных арендаторов
• house-апгрейды как состояние
• крипто-состояние из `/house`
• Отдельный редизайн `/crypto` не делался: всё, что связано с криптой, остаётся внутри `/house`.
"""

LATEST_FAST_TEXT = """
**core 3.0**
• Запущены `/dive`, `/dig`, `/auction`.
• BlackMarket 2.0 теперь разбит на `Экипировку`, `Контрабанду` и `Антиквара`.
• Ивент-окна и рыночные уведомления переведены в стиль `Ивент • ...`.

**fixes**
• Battle Pass больше не должен визуально показывать уже забранную награду как доступную.
• В аренде `/house` убраны дубли арендаторов и повторный найм через старые офферы.
• `/updates` и `update_notes.py` переведены на нормальный UTF-8 текст.

**ux wave**
• `/inventory` стал понятнее по категориям и быстрым действиям.
• `/profile` показывает активные бафы и world-status без раздувания экрана.
• `/shop` собран в более цельную витрину.
• `/business` показывает рынок, тренд и влияния мира сервера.
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
