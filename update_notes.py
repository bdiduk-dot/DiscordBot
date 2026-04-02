from __future__ import annotations

import discord

from config import COLORS

LATEST_UPDATE_ID = "2026-03-30-upd-1-fishing-rebalance"
UPDATE_PING_ROLE_ID = 1486391112330379304
UPDATE_CHANNEL_ID = 1486032811809964243

LATEST_UPDATE_TEXT = (
    "- Пересобран баланс рыбалки: кулдаун теперь зависит от удочки и растёт по tier от 3 до 11 минут.\n"
    "- Рыба по-прежнему сохраняется в инвентарь и продаётся только через `/inventory`.\n"
    "- Наживка больше не убирает кулдаун, а каждый заброс тратит ровно 1 штуку.\n"
    "- Зафиксированы размеры паков наживки: дешёвые по 5, средние по 4, сильные и топовые по 3.\n"
    "- Дорогие наживки понерфлены: уменьшены luck, chance, value и boss-бонусы для эпика, легендарок и боссов.\n"
    "- Рыболовные ивенты и hotspot-бонусы ослаблены, шанс боссов и цена event fish тоже снижены.\n"
    "- `/blackmarket` стал персональным для каждого игрока и обновляется раз в 12 часов.\n"
    "- Рыночное событие `fish_day` теперь усиливает рыбалку мягче и не разгоняет экономику так агрессивно."
)


def build_update_embed() -> discord.Embed:
    embed = discord.Embed(
        title="UPD 1 (Рыбалка)",
        description=LATEST_UPDATE_TEXT,
        color=COLORS["info"],
    )
    embed.set_footer(text=f"Update ID: {LATEST_UPDATE_ID}")
    return embed
