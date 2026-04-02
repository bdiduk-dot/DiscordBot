from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-04-02-upd-2-global-rebalance"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243
UPDATE_TITLE = "🌐 Глобальное обновление 2.0"

LATEST_UPDATE_TEXT = """
> Большой этап 2.0 уже в боте. Прогресс игроков сохранён, а ключевые системы стали заметно чище, понятнее и удобнее в использовании.

**Дома и крипта**
▸ Публичные квартиры полностью убраны: теперь везде показываются только дома
▸ Подвалы, GPU, аренда, мебель, сад и старый майнинг-кошелёк сохранены без потери прогресса
▸ `/house` стал главным экраном дома с вкладками `Дом`, `Сад`, `Крипта`, `Аренда`, `Обустройство`
▸ Крипта живёт внутри `/house`: сбор, продажа, фокус монеты и вывод старого кошелька теперь в одном месте
▸ Новые GPU покупаются через `/shop` → `Недвижимость`, а не из вкладки крипты

**Сад, рыбалка и инвентарь**
▸ Семена покупаются в `/shop`, урожай падает в инвентарь предметами
▸ В саду теперь используется понятный статус `полить через`, а сухие грядки явно помечаются как требующие полива
▸ В `/inventory` снова доступны три вкладки: `🎒 Предметы`, `🐟 Рыба`, `🎣 Снаряжение`
▸ Без наживки легендарная рыба не выпадает, а `Затонувший сундук` может принести деньги или крипту

**Экономика и интерфейсы**
▸ `/profile` стал компактнее и чище, а внутри появились read-only кнопки `Дом` и `Бизнесы`
▸ `/bank @player` открывает чужой банк в режиме только чтения с полной депозитной сводкой
▸ `/top` считает капитал по деньгам, банку, депозиту, домам, подвалам, GPU, бизнесам и мебели
▸ `/timers` переложен в компактный dashboard со статусами по экономике, активностям, рыбалке, бизнесам, дому и сбросам
▸ `/shop` теперь единый: `Главное`, `Недвижимость`, `Рыбалка`, `Садовод`, `ИКЕА`

**Риск и защита**
▸ `/crime`, `/slut` и `/steal` теперь прямо показывают, когда теневая страховка спасла от штрафа и не сняла репутацию
▸ Теневая страховка из чёрного маркета снова проходит полный цикл: покупка, активация и защита в рискованных сценариях
▸ Аренда получила случайные события с бонусами и штрафами

**fastFIX**
▸ Временные игровые и UI-сообщения удаляются после 2 минут неактива
▸ Блэкджек, дуэли, банк, дом, магазин, инвентарь и другие временные меню больше не висят лишнее время
▸ Вкладка `Крипта` в `/house` упрощена и стала понятнее
▸ `/timers` получил более аккуратный вид без визуального мусора
▸ После каждого рестарта бот публикует новое сообщение с обновлением в канал updates и закрепляет его
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
