from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from adventure_content import (
    DIG_TOOLS,
    DIG_ZONES,
    DIVE_GEAR,
    DIVE_LOCATIONS,
    DIVE_TANKS,
    RELIC_RECIPES,
    get_antiquary_definition,
)
from config import COLORS
from database import db, get_user_lock
from inventory_system import add_general_item, consume_general_item, count_general_items, get_general_items
from utils import (
    check_channel,
    format_discord_deadline,
    safe_defer,
    safe_edit_original_response,
    schedule_message_cleanup,
    send_wrong_channel_message,
)
from world_state import build_world_lines, build_world_snapshot, category_multiplier

DIVE_TIMEOUT_HOURS = 2
DIG_TIMEOUT_HOURS = 2


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _systems_state(user: dict[str, Any]) -> dict[str, Any]:
    game_stats = user.get("game_stats")
    if not isinstance(game_stats, dict):
        game_stats = {}
        user["game_stats"] = game_stats
    systems = game_stats.get("_systems")
    if not isinstance(systems, dict):
        systems = {}
        game_stats["_systems"] = systems
    return systems


def _adventure_state(user: dict[str, Any], key: str) -> dict[str, Any]:
    systems = _systems_state(user)
    state = systems.get(key)
    if not isinstance(state, dict):
        state = {}
        systems[key] = state
    state.setdefault("xp", 0)
    state.setdefault("runs", 0)
    state.setdefault("completed", 0)
    state.setdefault("rescues", 0)
    state.setdefault("session", None)
    state["level"] = _level_from_xp(int(state.get("xp", 0) or 0))
    return state


def _level_from_xp(xp: int) -> int:
    return max(1, int(xp // 120) + 1)


def _session_expired(session: dict[str, Any] | None, *, timeout_hours: int) -> bool:
    if not isinstance(session, dict):
        return False
    last_action_at = _parse_utc(session.get("last_action_at"))
    if last_action_at is None:
        return False
    return datetime.now(timezone.utc) >= last_action_at + timedelta(hours=timeout_hours)


def _session_value(session: dict[str, Any]) -> int:
    cash = int(session.get("cash_found", 0) or 0)
    loot_value = 0
    for loot in session.get("loot", []):
        if not isinstance(loot, dict):
            continue
        loot_value += int(loot.get("value", 0) or 0) * max(1, int(loot.get("quantity", 1) or 1))
    return cash + loot_value


def _compact_loot_lines(loot_entries: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for entry in loot_entries[:6]:
        quantity = max(1, int(entry.get("quantity", 1) or 1))
        quantity_label = f"x{quantity} " if quantity > 1 else ""
        lines.append(
            f"{entry.get('emoji', '🏺')} {quantity_label}**{entry.get('name', 'Находка')}** • {format_money(entry.get('value', 0))}"
        )
    return lines or ["Пока без трофеев."]


def _grant_antiquary_item(
    user: dict[str, Any],
    code: str,
    *,
    quantity: int = 1,
    source: str,
    source_zone: str,
) -> dict[str, Any] | None:
    definition = get_antiquary_definition(code)
    if not definition:
        return None
    return add_general_item(
        user,
        item_type=str(definition.get("item_type") or "antiquary_loot"),
        code=code,
        name=str(definition.get("name") or code.replace("_", " ").title()),
        emoji=str(definition.get("emoji") or "🏺"),
        description=str(definition.get("description") or "Редкая находка для Антиквара."),
        quantity=quantity,
        payload={
            "source": source,
            "zone": source_zone,
            "family": str(definition.get("family") or ""),
            "assembled": bool(definition.get("assembled")),
        },
        stackable=True,
    )


def _append_loot(session: dict[str, Any], code: str, value: int) -> dict[str, Any] | None:
    definition = get_antiquary_definition(code)
    if not definition:
        return None
    loot_entries = session.setdefault("loot", [])
    for entry in loot_entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("code") or "") != code:
            continue
        entry["quantity"] = max(1, int(entry.get("quantity", 1) or 1) + 1)
        return entry
    entry = {
        "code": code,
        "name": str(definition.get("name") or code),
        "emoji": str(definition.get("emoji") or "🏺"),
        "quantity": 1,
        "value": max(1, int(value or 0)),
        "item_type": str(definition.get("item_type") or "antiquary_loot"),
    }
    loot_entries.append(entry)
    return entry


def _rescue_loot(session: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    flattened: list[tuple[str, int]] = []
    for entry in session.get("loot", []):
        if not isinstance(entry, dict):
            continue
        quantity = max(1, int(entry.get("quantity", 1) or 1))
        for _ in range(quantity):
            flattened.append((str(entry.get("code") or ""), int(entry.get("value", 0) or 0)))

    kept_count = max(0, int(round(len(flattened) * 0.2)))
    if flattened and kept_count <= 0:
        kept_count = 1

    rng = random.Random()
    kept_units = rng.sample(flattened, k=min(kept_count, len(flattened))) if kept_count else []
    grouped: dict[str, dict[str, Any]] = {}
    for code, value in kept_units:
        definition = get_antiquary_definition(code)
        if not definition:
            continue
        current = grouped.setdefault(
            code,
            {
                "code": code,
                "name": str(definition.get("name") or code),
                "emoji": str(definition.get("emoji") or "🏺"),
                "quantity": 0,
                "value": max(1, int(value or 0)),
                "item_type": str(definition.get("item_type") or "antiquary_loot"),
            },
        )
        current["quantity"] = max(0, int(current.get("quantity", 0) or 0) + 1)
    kept_loot = list(grouped.values())
    kept_cash = int(round(int(session.get("cash_found", 0) or 0) * 0.2))
    return kept_loot, kept_cash


def _equipment_count(user: dict[str, Any], *, item_type: str, code: str) -> int:
    return count_general_items(user, item_type=item_type, code=code)


def _pick_best_tank(user: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    for tank_code in ("scuba_titan", "scuba_reinforced", "scuba_basic"):
        if _equipment_count(user, item_type="dive_tank", code=tank_code) > 0:
            return tank_code, deepcopy(DIVE_TANKS[tank_code])
    return None


def _describe_dive_roll(location_code: str, action: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    location = DIVE_LOCATIONS[location_code]
    rng = random.Random()
    base_costs = {
        "descend": rng.randint(18, 28),
        "search": rng.randint(14, 22),
        "open": rng.randint(22, 34),
    }
    descriptions = {
        "descend": [
            "Ты уходишь глубже в темноту и замечаешь новый след на дне.",
            "Течение уводит тебя в сторону и открывает скрытую нишу.",
            "Под водой становится холоднее, но маршрут выглядит многообещающе.",
        ],
        "search": [
            "Ты обшариваешь ближайшие обломки и поднимаешь муть со дна.",
            "Луч фонаря цепляет что-то ценное в песке.",
            "Ты медленно проходишь вдоль рифа, всматриваясь в трещины.",
        ],
        "open": [
            "Замок поддаётся, и внутри блеснул старый трофей.",
            "Ты рискуешь и вскрываешь находку прямо на глубине.",
            "Сундук скрипит, но внутри явно есть что-то ценное.",
        ],
    }

    reward_roll = rng.random()
    bias = str(location.get("loot_bias") or "safe")
    loot_code = None
    cash_found = 0
    if bias == "safe":
        if reward_roll < 0.58:
            loot_code = "reef_shell"
        elif reward_roll < 0.82:
            loot_code = rng.choice(["coral_idol_a", "coral_idol_b", "coral_idol_c"])
        else:
            cash_found = rng.randint(1800, 5200)
    elif bias == "treasure":
        if reward_roll < 0.34:
            loot_code = "pirate_compass"
        elif reward_roll < 0.70:
            loot_code = rng.choice(["coral_idol_a", "coral_idol_b", "coral_idol_c"])
        else:
            cash_found = rng.randint(4500, 14000)
    else:
        if reward_roll < 0.30:
            loot_code = "abyss_shard"
        elif reward_roll < 0.72:
            loot_code = rng.choice(["leviathan_sigil_a", "leviathan_sigil_b", "leviathan_sigil_c"])
        else:
            cash_found = rng.randint(8500, 24000)

    danger_text = None
    danger_cost = 0
    risk = float(location.get("risk", 0.2) or 0.2)
    if rng.random() < risk + (0.08 if action == "open" else 0.0):
        danger_cost = rng.randint(8, 40)
        danger_text = rng.choice(
            [
                "Мурена рванула рядом и ты теряешь часть кислорода.",
                "Острый металл цепляет баллон и воздух уходит быстрее.",
                "Течение сбивает с курса и забирает драгоценный O2.",
            ]
        )

    prices = snapshot.get("antiquary_prices", {})
    loot_value = int(prices.get(loot_code, 0) or 0)
    value_multiplier = category_multiplier(snapshot, "dive")
    if loot_code and loot_value > 0:
        loot_value = max(1, int(round(loot_value * value_multiplier)))
    if cash_found > 0:
        cash_found = max(1, int(round(cash_found * value_multiplier)))

    return {
        "oxygen_cost": base_costs.get(action, 18),
        "text": rng.choice(descriptions.get(action, descriptions["search"])),
        "loot_code": loot_code,
        "loot_value": loot_value,
        "cash_found": cash_found,
        "danger_text": danger_text,
        "danger_cost": danger_cost,
    }


def _new_dig_target(zone_code: str, *, scanner: bool) -> dict[str, Any]:
    zone = DIG_ZONES[zone_code]
    bias = str(zone.get("rarity_bias") or "common")
    rng = random.Random()
    signal_floor = 45 if scanner else 25
    signal = rng.randint(signal_floor, 100)
    threshold = 2 if signal >= 80 else 3 if signal >= 55 else 4
    reward_roll = rng.random()
    loot_code = None
    cash_found = 0
    if bias == "common":
        if reward_roll < 0.44:
            loot_code = rng.choice(["coral_idol_a", "coral_idol_b"])
        elif reward_roll < 0.78:
            loot_code = "reef_shell"
        else:
            cash_found = rng.randint(1600, 5200)
    elif bias == "rare":
        if reward_roll < 0.38:
            loot_code = "pirate_compass"
        elif reward_roll < 0.74:
            loot_code = rng.choice(["coral_idol_c", "leviathan_sigil_a"])
        else:
            cash_found = rng.randint(4200, 12000)
    else:
        if reward_roll < 0.36:
            loot_code = rng.choice(["leviathan_sigil_b", "leviathan_sigil_c"])
        elif reward_roll < 0.68:
            loot_code = "abyss_shard"
        else:
            cash_found = rng.randint(9000, 22000)
    return {
        "signal": signal,
        "threshold": threshold,
        "progress": 0,
        "loot_code": loot_code,
        "cash_found": cash_found,
    }


class _AdventureBaseView(discord.ui.View):
    def __init__(self, cog: "AdventuresCog", user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню приключения открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message, delay_seconds=0)


class DiveStartView(_AdventureBaseView):
    def __init__(self, cog: "AdventuresCog", user_id: int, guild_id: int):
        super().__init__(cog, user_id, guild_id)
        for row, location_code in enumerate(DIVE_LOCATIONS.keys(), start=0):
            location = DIVE_LOCATIONS[location_code]
            button = discord.ui.Button(
                label=str(location.get("name") or location_code),
                emoji=str(location.get("emoji") or "🌊"),
                style=discord.ButtonStyle.primary,
                row=row // 2,
            )

            async def callback(interaction: discord.Interaction, code: str = location_code):
                async with self._view_lock:
                    await self.cog.start_dive(interaction, self.user_id, self.guild_id, code)

            button.callback = callback
            self.add_item(button)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.render_dive(interaction, self.user_id, self.guild_id)


class DiveRunView(_AdventureBaseView):
    @discord.ui.button(label="Плыть глубже", style=discord.ButtonStyle.primary, row=0)
    async def descend_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dive_action(interaction, self.user_id, self.guild_id, "descend")

    @discord.ui.button(label="Осмотреть", style=discord.ButtonStyle.secondary, row=0)
    async def search_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dive_action(interaction, self.user_id, self.guild_id, "search")

    @discord.ui.button(label="Открыть находку", style=discord.ButtonStyle.secondary, row=0)
    async def open_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dive_action(interaction, self.user_id, self.guild_id, "open")

    @discord.ui.button(label="Всплыть", style=discord.ButtonStyle.success, row=1)
    async def surface_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dive_action(interaction, self.user_id, self.guild_id, "surface")

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.render_dive(interaction, self.user_id, self.guild_id)


class DigStartView(_AdventureBaseView):
    def __init__(self, cog: "AdventuresCog", user_id: int, guild_id: int):
        super().__init__(cog, user_id, guild_id)
        for row, zone_code in enumerate(DIG_ZONES.keys(), start=0):
            zone = DIG_ZONES[zone_code]
            button = discord.ui.Button(
                label=str(zone.get("name") or zone_code),
                emoji=str(zone.get("emoji") or "🏺"),
                style=discord.ButtonStyle.primary,
                row=row // 2,
            )

            async def callback(interaction: discord.Interaction, code: str = zone_code):
                async with self._view_lock:
                    await self.cog.start_dig(interaction, self.user_id, self.guild_id, code)

            button.callback = callback
            self.add_item(button)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.render_dig(interaction, self.user_id, self.guild_id)


class DigRunView(_AdventureBaseView):
    @discord.ui.button(label="Сканировать", style=discord.ButtonStyle.primary, row=0)
    async def scan_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dig_action(interaction, self.user_id, self.guild_id, "scan")

    @discord.ui.button(label="Копать глубже", style=discord.ButtonStyle.secondary, row=0)
    async def dig_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dig_action(interaction, self.user_id, self.guild_id, "excavate")

    @discord.ui.button(label="Извлечь", style=discord.ButtonStyle.secondary, row=0)
    async def extract_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dig_action(interaction, self.user_id, self.guild_id, "extract")

    @discord.ui.button(label="Сменить сектор", style=discord.ButtonStyle.secondary, row=1)
    async def shift_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dig_action(interaction, self.user_id, self.guild_id, "shift")

    @discord.ui.button(label="Завершить", style=discord.ButtonStyle.success, row=1)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.handle_dig_action(interaction, self.user_id, self.guild_id, "leave")

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            await self.cog.render_dig(interaction, self.user_id, self.guild_id)


class AdventuresCog(commands.Cog, name="Adventures"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _systems_cog(self):
        return self.bot.get_cog("Systems")

    def _world_snapshot(self, guild_id: int) -> dict[str, Any]:
        systems_cog = self._systems_cog()
        active_event = systems_cog.get_active_event(guild_id) if systems_cog is not None else None
        return build_world_snapshot(guild_id, active_event)

    async def _resolve_dive_timeout(self, user_id: int, guild_id: int) -> discord.Embed | None:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return None
            dive_state = _adventure_state(user, "dive")
            session = dive_state.get("session")
            if not _session_expired(session, timeout_hours=DIVE_TIMEOUT_HOURS):
                return None
            return await self._finish_dive_locked(user_id, guild_id, user, rescue=True, timed_out=True)

    async def _resolve_dig_timeout(self, user_id: int, guild_id: int) -> discord.Embed | None:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return None
            dig_state = _adventure_state(user, "dig")
            session = dig_state.get("session")
            if not _session_expired(session, timeout_hours=DIG_TIMEOUT_HOURS):
                return None
            return await self._finish_dig_locked(user_id, guild_id, user, timed_out=True)

    async def build_dive_panel(self, user_id: int, guild_id: int) -> tuple[discord.Embed, discord.ui.View]:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Погружение", description="Не удалось загрузить профиль.", color=COLORS["warning"]), DiveStartView(self, user_id, guild_id)

        state = _adventure_state(user, "dive")
        session = state.get("session")
        if isinstance(session, dict):
            return self._build_dive_run_panel(user, guild_id), DiveRunView(self, user_id, guild_id)
        return self._build_dive_start_panel(user, guild_id), DiveStartView(self, user_id, guild_id)

    def _build_dive_start_panel(self, user: dict[str, Any], guild_id: int) -> discord.Embed:
        dive_state = _adventure_state(user, "dive")
        snapshot = self._world_snapshot(guild_id)
        embed = discord.Embed(
            title="🤿 Подводные погружения",
            description=(
                "Рискованная вылазка за древним лутом. Бот автоматически использует **лучший доступный баллон**, "
                "а в глубинную зону не пустит без фонарика."
            ),
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        tank_lines = []
        for tank_code in ("scuba_basic", "scuba_reinforced", "scuba_titan"):
            tank = DIVE_TANKS[tank_code]
            tank_lines.append(
                f"{tank['emoji']} **{tank['name']}** • O2 {tank['oxygen']} • в инвентаре: **{_equipment_count(user, item_type='dive_tank', code=tank_code)}**"
            )
        embed.add_field(name="Снаряжение", value="\n".join(tank_lines), inline=False)
        embed.add_field(
            name="Редкое оборудование",
            value=(
                f"{DIVE_GEAR['abyss_lamp']['emoji']} **{DIVE_GEAR['abyss_lamp']['name']}** • "
                f"в наличии: **{_equipment_count(user, item_type='dive_gear', code='abyss_lamp')}**"
            ),
            inline=False,
        )

        for location_code, location in DIVE_LOCATIONS.items():
            status = "Открыто" if dive_state["level"] >= int(location.get("min_level", 1) or 1) else f"Нужен уровень {location.get('min_level', 1)}"
            requirement = ""
            if location.get("requires"):
                requirement = f"\nТребование: **{DIVE_GEAR['abyss_lamp']['name']}**"
            embed.add_field(
                name=f"{location.get('emoji', '🌊')} {location['name']}",
                value=(
                    f"{location['description']}\n"
                    f"Уровень дайвера: **{location['min_level']}+**\n"
                    f"Риск: **{int(float(location.get('risk', 0))*100)}%**\n"
                    f"Статус: **{status}**"
                    f"{requirement}"
                ),
                inline=False,
            )

        embed.add_field(
            name="Статус дайвера",
            value=(
                f"Уровень: **{dive_state['level']}**\n"
                f"XP: **{int(dive_state.get('xp', 0) or 0)}**\n"
                f"Ходок: **{int(dive_state.get('runs', 0) or 0)}**"
            ),
            inline=True,
        )
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=True)
        embed.set_footer(text="Нажми на нужную локацию ниже. При провале спасатели заберут большую часть добычи.")
        return embed

    def _build_dive_run_panel(self, user: dict[str, Any], guild_id: int) -> discord.Embed:
        snapshot = self._world_snapshot(guild_id)
        dive_state = _adventure_state(user, "dive")
        session = dive_state.get("session") or {}
        location = DIVE_LOCATIONS.get(str(session.get("location_code") or ""), {})
        loot_lines = _compact_loot_lines(list(session.get("loot", [])))
        embed = discord.Embed(
            title=f"🤿 {location.get('name', 'Погружение')}",
            description=(
                f"O2: **{int(session.get('oxygen_left', 0) or 0)}/{int(session.get('oxygen_max', 0) or 0)}**\n"
                f"Баллон: **{DIVE_TANKS.get(str(session.get('tank_code') or ''), {}).get('name', 'Неизвестно')}**\n"
                f"Шагов: **{int(session.get('steps', 0) or 0)}**\n"
                f"Оценка добычи: **{format_money(_session_value(session))}**"
            ),
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        if session.get("last_story"):
            embed.add_field(name="Последнее событие", value=str(session.get("last_story")), inline=False)
        embed.add_field(name="Добыча на руках", value="\n".join(loot_lines), inline=False)
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=False)
        embed.set_footer(text="Успей нажать «Всплыть» до того, как кислород уйдёт в ноль.")
        return embed

    async def render_dive(self, interaction: discord.Interaction, user_id: int, guild_id: int):
        timeout_embed = await self._resolve_dive_timeout(user_id, guild_id)
        if not await safe_defer(interaction):
            return
        embed, view = await self.build_dive_panel(user_id, guild_id)
        if timeout_embed is not None:
            embed.insert_field_at(0, name="Последний итог", value=timeout_embed.description or "Прошлая ходка завершилась.", inline=False)
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        await view._remember_message(interaction)

    async def start_dive(self, interaction: discord.Interaction, user_id: int, guild_id: int, location_code: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return

            dive_state = _adventure_state(user, "dive")
            if isinstance(dive_state.get("session"), dict):
                await interaction.response.send_message("У тебя уже есть активное погружение. Заверши его или всплывай.", ephemeral=True)
                return

            location = DIVE_LOCATIONS.get(location_code)
            if not location:
                await interaction.response.send_message("Такой локации погружения нет.", ephemeral=True)
                return
            if dive_state["level"] < int(location.get("min_level", 1) or 1):
                await interaction.response.send_message(
                    f"Для этой зоны нужен уровень дайвера **{location.get('min_level', 1)}**.",
                    ephemeral=True,
                )
                return
            if location.get("requires") and _equipment_count(user, item_type="dive_gear", code=str(location["requires"])) <= 0:
                await interaction.response.send_message("Для этой глубины нужен фонарик бездны из чёрного рынка.", ephemeral=True)
                return

            tank_pick = _pick_best_tank(user)
            if tank_pick is None:
                await interaction.response.send_message("Сначала купи акваланг на чёрном рынке.", ephemeral=True)
                return
            tank_code, tank = tank_pick
            if consume_general_item(user, item_type="dive_tank", code=tank_code, quantity=1) is None:
                await interaction.response.send_message("Не удалось подготовить баллон. Попробуй ещё раз.", ephemeral=True)
                return

            dive_state["session"] = {
                "location_code": location_code,
                "tank_code": tank_code,
                "oxygen_max": int(tank["oxygen"]),
                "oxygen_left": int(tank["oxygen"]),
                "steps": 0,
                "cash_found": 0,
                "loot": [],
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_action_at": datetime.now(timezone.utc).isoformat(),
                "last_story": f"Старт погружения: **{location['name']}**. Воздух свистит в баллоне, а под водой тихо.",
            }
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})

        await self.render_dive(interaction, user_id, guild_id)

    async def handle_dive_action(self, interaction: discord.Interaction, user_id: int, guild_id: int, action: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return
            dive_state = _adventure_state(user, "dive")
            session = dive_state.get("session")
            if not isinstance(session, dict):
                await interaction.response.send_message("Активного погружения сейчас нет.", ephemeral=True)
                return

            if _session_expired(session, timeout_hours=DIVE_TIMEOUT_HOURS):
                await self._finish_dive_locked(user_id, guild_id, user, rescue=True, timed_out=True)
            elif action == "surface":
                await self._finish_dive_locked(user_id, guild_id, user, rescue=False, timed_out=False)
            else:
                snapshot = self._world_snapshot(guild_id)
                result = _describe_dive_roll(str(session.get("location_code") or "coral_reef"), action, snapshot)
                oxygen_cost = int(result.get("oxygen_cost", 0) or 0) + int(result.get("danger_cost", 0) or 0)
                session["oxygen_left"] = max(0, int(session.get("oxygen_left", 0) or 0) - oxygen_cost)
                session["steps"] = int(session.get("steps", 0) or 0) + 1
                session["last_action_at"] = datetime.now(timezone.utc).isoformat()
                story_parts = [str(result.get("text") or "Под водой становится тревожно.")]
                if result.get("loot_code"):
                    appended = _append_loot(session, str(result["loot_code"]), int(result.get("loot_value", 0) or 0))
                    if appended is not None:
                        story_parts.append(
                            f"Найдена добыча: {appended.get('emoji', '🏺')} **{appended.get('name', 'Находка')}**."
                        )
                if int(result.get("cash_found", 0) or 0) > 0:
                    session["cash_found"] = int(session.get("cash_found", 0) or 0) + int(result["cash_found"])
                    story_parts.append(f"Поднято наличными: **{format_money(result['cash_found'])}**.")
                if result.get("danger_text"):
                    story_parts.append(str(result["danger_text"]))
                story_parts.append(f"Расход O2: **-{oxygen_cost}**.")
                session["last_story"] = " ".join(story_parts)
                await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
                if int(session.get("oxygen_left", 0) or 0) <= 0:
                    await self._finish_dive_locked(user_id, guild_id, user, rescue=True, timed_out=False)

        await self.render_dive(interaction, user_id, guild_id)

    async def _finish_dive_locked(
        self,
        user_id: int,
        guild_id: int,
        user: dict[str, Any],
        *,
        rescue: bool,
        timed_out: bool,
    ) -> discord.Embed:
        dive_state = _adventure_state(user, "dive")
        session = dive_state.get("session") or {}
        if not isinstance(session, dict):
            return discord.Embed(title="Погружение", description="Сессия уже завершена.", color=COLORS["warning"])

        location_code = str(session.get("location_code") or "coral_reef")
        location = DIVE_LOCATIONS.get(location_code, {})
        snapshot = self._world_snapshot(guild_id)
        payout_cash = int(session.get("cash_found", 0) or 0)
        payout_loot = list(session.get("loot", []))
        if rescue:
            payout_loot, payout_cash = _rescue_loot(session)

        if payout_cash > 0:
            user["balance"] = int(user.get("balance", 0) or 0) + payout_cash
        for entry in payout_loot:
            if not isinstance(entry, dict):
                continue
            _grant_antiquary_item(
                user,
                str(entry.get("code") or ""),
                quantity=max(1, int(entry.get("quantity", 1) or 1)),
                source="dive",
                source_zone=location_code,
            )

        xp_gain = 35 + int(session.get("steps", 0) or 0) * 8 + int(location.get("min_level", 1) or 1) * 24
        if rescue:
            xp_gain = max(18, int(round(xp_gain * 0.55)))
            dive_state["rescues"] = int(dive_state.get("rescues", 0) or 0) + 1
        else:
            dive_state["completed"] = int(dive_state.get("completed", 0) or 0) + 1
        dive_state["runs"] = int(dive_state.get("runs", 0) or 0) + 1
        dive_state["xp"] = int(dive_state.get("xp", 0) or 0) + xp_gain
        dive_state["level"] = _level_from_xp(int(dive_state.get("xp", 0) or 0))
        dive_state["session"] = None

        await db.update_user(
            user_id,
            guild_id,
            {
                "balance": user.get("balance", 0),
                "inventory": user.get("inventory"),
                "game_stats": user.get("game_stats", {}),
            },
        )

        state_text = "Спасатели успели вытащить тебя и вернуть часть добычи." if rescue else "Ты вовремя всплыл и сохранил всю добычу."
        if timed_out:
            state_text = "Сессия истекла по таймауту. Спасатели подняли тебя на поверхность и удержали большую часть добычи."

        loot_lines = _compact_loot_lines(payout_loot)
        embed = discord.Embed(
            title=f"🤿 Итог погружения • {location.get('name', 'Маршрут')}",
            description=(
                f"{state_text}\n\n"
                f"Наличные: **{format_money(payout_cash)}**\n"
                f"XP дайвера: **+{xp_gain}**\n"
                f"Текущий уровень: **{dive_state['level']}**"
            ),
            color=COLORS["success"] if not rescue else COLORS["warning"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Сохранённая добыча", value="\n".join(loot_lines), inline=False)
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=False)
        return embed

    async def build_dig_panel(self, user_id: int, guild_id: int) -> tuple[discord.Embed, discord.ui.View]:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Раскопки", description="Не удалось загрузить профиль.", color=COLORS["warning"]), DigStartView(self, user_id, guild_id)

        state = _adventure_state(user, "dig")
        session = state.get("session")
        if isinstance(session, dict):
            return self._build_dig_run_panel(user, guild_id), DigRunView(self, user_id, guild_id)
        return self._build_dig_start_panel(user, guild_id), DigStartView(self, user_id, guild_id)

    def _build_dig_start_panel(self, user: dict[str, Any], guild_id: int) -> discord.Embed:
        dig_state = _adventure_state(user, "dig")
        snapshot = self._world_snapshot(guild_id)
        embed = discord.Embed(
            title="⛏️ Раскопки",
            description=(
                "Экспедиция по секторам с поиском древних фрагментов. Для старта нужен **Набор археолога**, "
                "а **Сканер пустот** делает сигнал заметно лучше."
            ),
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Снаряжение",
            value=(
                f"{DIG_TOOLS['excavation_kit']['emoji']} **{DIG_TOOLS['excavation_kit']['name']}** • "
                f"в наличии: **{_equipment_count(user, item_type='dig_tool', code='excavation_kit')}**\n"
                f"{DIG_TOOLS['signal_scanner']['emoji']} **{DIG_TOOLS['signal_scanner']['name']}** • "
                f"в наличии: **{_equipment_count(user, item_type='dig_tool', code='signal_scanner')}**"
            ),
            inline=False,
        )
        for zone_code, zone in DIG_ZONES.items():
            status = "Открыто" if dig_state["level"] >= int(zone.get("min_level", 1) or 1) else f"Нужен уровень {zone.get('min_level', 1)}"
            embed.add_field(
                name=f"{zone.get('emoji', '🏺')} {zone['name']}",
                value=(
                    f"{zone['description']}\n"
                    f"Уровень копателя: **{zone['min_level']}+**\n"
                    f"Текущий статус: **{status}**"
                ),
                inline=False,
            )
        embed.add_field(
            name="Статус копателя",
            value=(
                f"Уровень: **{dig_state['level']}**\n"
                f"XP: **{int(dig_state.get('xp', 0) or 0)}**\n"
                f"Экспедиций: **{int(dig_state.get('runs', 0) or 0)}**"
            ),
            inline=True,
        )
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=True)
        embed.set_footer(text="Нажми на зону ниже. Таймаут не забирает уже извлечённый лут, но незавершённая точка пропадёт.")
        return embed

    def _build_dig_run_panel(self, user: dict[str, Any], guild_id: int) -> discord.Embed:
        snapshot = self._world_snapshot(guild_id)
        dig_state = _adventure_state(user, "dig")
        session = dig_state.get("session") or {}
        zone = DIG_ZONES.get(str(session.get("zone_code") or ""), {})
        target = session.get("target") if isinstance(session.get("target"), dict) else {}
        loot_lines = _compact_loot_lines(list(session.get("secured_loot", [])))
        secured_value = _session_value({"loot": session.get("secured_loot", []), "cash_found": session.get("cash_found", 0)})
        embed = discord.Embed(
            title=f"⛏️ {zone.get('name', 'Раскопки')}",
            description=(
                f"Сигнал: **{int(target.get('signal', 0) or 0)}%**\n"
                f"Прогресс точки: **{int(target.get('progress', 0) or 0)}/{int(target.get('threshold', 0) or 0)}**\n"
                f"Ходов: **{int(session.get('actions', 0) or 0)}**\n"
                f"Оценка добычи: **{format_money(secured_value)}**"
            ),
            color=COLORS["info"],
            timestamp=datetime.now(timezone.utc),
        )
        if session.get("last_story"):
            embed.add_field(name="Последнее событие", value=str(session.get("last_story")), inline=False)
        embed.add_field(name="Уже извлечено", value="\n".join(loot_lines), inline=False)
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=False)
        embed.set_footer(text="Сканируй, копай глубже и извлекай находку до ухода из экспедиции.")
        return embed

    async def render_dig(self, interaction: discord.Interaction, user_id: int, guild_id: int):
        timeout_embed = await self._resolve_dig_timeout(user_id, guild_id)
        if not await safe_defer(interaction):
            return
        embed, view = await self.build_dig_panel(user_id, guild_id)
        if timeout_embed is not None:
            embed.insert_field_at(0, name="Последний итог", value=timeout_embed.description or "Прошлая экспедиция завершена.", inline=False)
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        await view._remember_message(interaction)

    async def start_dig(self, interaction: discord.Interaction, user_id: int, guild_id: int, zone_code: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return
            dig_state = _adventure_state(user, "dig")
            if isinstance(dig_state.get("session"), dict):
                await interaction.response.send_message("У тебя уже идёт активная экспедиция.", ephemeral=True)
                return
            zone = DIG_ZONES.get(zone_code)
            if not zone:
                await interaction.response.send_message("Такой зоны раскопок нет.", ephemeral=True)
                return
            if dig_state["level"] < int(zone.get("min_level", 1) or 1):
                await interaction.response.send_message(
                    f"Для этой зоны нужен уровень копателя **{zone.get('min_level', 1)}**.",
                    ephemeral=True,
                )
                return
            if consume_general_item(user, item_type="dig_tool", code="excavation_kit", quantity=1) is None:
                await interaction.response.send_message("Для старта нужен Набор археолога из чёрного рынка.", ephemeral=True)
                return

            has_scanner = _equipment_count(user, item_type="dig_tool", code="signal_scanner") > 0
            dig_state["session"] = {
                "zone_code": zone_code,
                "scanner": has_scanner,
                "target": _new_dig_target(zone_code, scanner=has_scanner),
                "secured_loot": [],
                "cash_found": 0,
                "actions": 0,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "last_action_at": datetime.now(timezone.utc).isoformat(),
                "last_story": f"Ты разбил лагерь в зоне **{zone['name']}** и приготовился к первой точке.",
            }
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})

        await self.render_dig(interaction, user_id, guild_id)

    async def handle_dig_action(self, interaction: discord.Interaction, user_id: int, guild_id: int, action: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                await interaction.response.send_message("Не удалось загрузить профиль.", ephemeral=True)
                return
            dig_state = _adventure_state(user, "dig")
            session = dig_state.get("session")
            if not isinstance(session, dict):
                await interaction.response.send_message("Активной экспедиции сейчас нет.", ephemeral=True)
                return

            if _session_expired(session, timeout_hours=DIG_TIMEOUT_HOURS):
                await self._finish_dig_locked(user_id, guild_id, user, timed_out=True)
            elif action == "leave":
                await self._finish_dig_locked(user_id, guild_id, user, timed_out=False)
            else:
                target = session.get("target")
                if not isinstance(target, dict):
                    target = _new_dig_target(str(session.get("zone_code") or "dusty_fields"), scanner=bool(session.get("scanner")))
                    session["target"] = target
                snapshot = self._world_snapshot(guild_id)
                action_lines: list[str] = []
                session["actions"] = int(session.get("actions", 0) or 0) + 1
                session["last_action_at"] = datetime.now(timezone.utc).isoformat()
                if action == "scan":
                    scan_boost = random.randint(12, 26) + (10 if session.get("scanner") else 0)
                    target["signal"] = min(100, int(target.get("signal", 0) or 0) + scan_boost)
                    action_lines.append(f"Сканер поднимает сигнал до **{int(target['signal'])}%**.")
                elif action == "excavate":
                    target["progress"] = int(target.get("progress", 0) or 0) + 1
                    action_lines.append(f"Раскоп продвинулся: **{target['progress']}/{target['threshold']}**.")
                    if random.random() < 0.18:
                        target["progress"] = max(0, int(target.get("progress", 0) or 0) - 1)
                        action_lines.append("Стена осыпалась и один этап пришлось делать заново.")
                elif action == "extract":
                    if int(target.get("progress", 0) or 0) < int(target.get("threshold", 0) or 0):
                        action_lines.append("Точка ещё не готова к извлечению. Нужно копать глубже.")
                    else:
                        loot_code = str(target.get("loot_code") or "")
                        multiplier = category_multiplier(snapshot, "dig")
                        cash_found = int(target.get("cash_found", 0) or 0)
                        if loot_code:
                            definition = get_antiquary_definition(loot_code) or {}
                            base_price = int(snapshot.get("antiquary_prices", {}).get(loot_code, definition.get("base_value", 0)) or 0)
                            value = max(1, int(round(base_price * multiplier)))
                            secured = session.setdefault("secured_loot", [])
                            matched = None
                            for entry in secured:
                                if isinstance(entry, dict) and str(entry.get("code") or "") == loot_code:
                                    matched = entry
                                    break
                            if matched is None:
                                matched = {
                                    "code": loot_code,
                                    "name": str(definition.get("name") or loot_code),
                                    "emoji": str(definition.get("emoji") or "🏺"),
                                    "quantity": 0,
                                    "value": value,
                                    "item_type": str(definition.get("item_type") or "antiquary_loot"),
                                }
                                secured.append(matched)
                            matched["quantity"] = max(1, int(matched.get("quantity", 0) or 0) + 1)
                            action_lines.append(f"Извлечено: {matched['emoji']} **{matched['name']}**.")
                        if cash_found > 0:
                            cash_found = max(1, int(round(cash_found * multiplier)))
                            session["cash_found"] = int(session.get("cash_found", 0) or 0) + cash_found
                            action_lines.append(f"Найдено наличными: **{format_money(cash_found)}**.")
                        session["target"] = _new_dig_target(str(session.get("zone_code") or "dusty_fields"), scanner=bool(session.get("scanner")))
                elif action == "shift":
                    session["target"] = _new_dig_target(str(session.get("zone_code") or "dusty_fields"), scanner=bool(session.get("scanner")))
                    action_lines.append("Ты сменил сектор и поймал новый сигнал.")

                session["last_story"] = " ".join(action_lines) if action_lines else "Экспедиция продолжается."
                await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        await self.render_dig(interaction, user_id, guild_id)

    async def _finish_dig_locked(self, user_id: int, guild_id: int, user: dict[str, Any], *, timed_out: bool) -> discord.Embed:
        dig_state = _adventure_state(user, "dig")
        session = dig_state.get("session") or {}
        if not isinstance(session, dict):
            return discord.Embed(title="Раскопки", description="Сессия уже завершена.", color=COLORS["warning"])

        zone_code = str(session.get("zone_code") or "dusty_fields")
        zone = DIG_ZONES.get(zone_code, {})
        snapshot = self._world_snapshot(guild_id)
        payout_cash = int(session.get("cash_found", 0) or 0)
        payout_loot = list(session.get("secured_loot", []))

        if payout_cash > 0:
            user["balance"] = int(user.get("balance", 0) or 0) + payout_cash
        for entry in payout_loot:
            if not isinstance(entry, dict):
                continue
            _grant_antiquary_item(
                user,
                str(entry.get("code") or ""),
                quantity=max(1, int(entry.get("quantity", 1) or 1)),
                source="dig",
                source_zone=zone_code,
            )

        xp_gain = 28 + int(session.get("actions", 0) or 0) * 6 + int(zone.get("min_level", 1) or 1) * 22
        dig_state["runs"] = int(dig_state.get("runs", 0) or 0) + 1
        dig_state["completed"] = int(dig_state.get("completed", 0) or 0) + 1
        dig_state["xp"] = int(dig_state.get("xp", 0) or 0) + xp_gain
        dig_state["level"] = _level_from_xp(int(dig_state.get("xp", 0) or 0))
        dig_state["session"] = None

        await db.update_user(
            user_id,
            guild_id,
            {
                "balance": user.get("balance", 0),
                "inventory": user.get("inventory"),
                "game_stats": user.get("game_stats", {}),
            },
        )

        description = "Экспедиция завершена, а найденные трофеи уже отправлены в инвентарь."
        if timed_out:
            description = "Экспедиция завершилась по таймауту. Незавершённая точка потеряна, но уже извлечённые трофеи сохранены."

        embed = discord.Embed(
            title=f"⛏️ Итог раскопок • {zone.get('name', 'Маршрут')}",
            description=(
                f"{description}\n\n"
                f"Наличные: **{format_money(payout_cash)}**\n"
                f"XP копателя: **+{xp_gain}**\n"
                f"Текущий уровень: **{dig_state['level']}**"
            ),
            color=COLORS["success"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Сохранённая добыча", value="\n".join(_compact_loot_lines(payout_loot)), inline=False)
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=False)
        return embed

    async def build_antiquary_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Антиквар", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        snapshot = self._world_snapshot(guild_id)
        antiquary_prices = snapshot.get("antiquary_prices", {})
        general_items = get_general_items(user)
        antiquary_items = [
            item
            for item in general_items
            if str(item.get("item_type") or "").startswith("antiquary_")
        ]
        embed = discord.Embed(
            title="🏺 Антиквар",
            description=(
                "Сюда можно сбывать находки из `/dive` и `/dig`, а ещё собирать цельные реликвии из фрагментов.\n"
                "Продажа идёт по серверным ценам текущего дня."
            ),
            color=COLORS["warning"],
            timestamp=datetime.now(timezone.utc),
        )
        if not antiquary_items:
            embed.add_field(name="Инвентарь Антиквара", value="Пока пусто. Добудь что-нибудь в погружениях или раскопках.", inline=False)
        else:
            lines: list[str] = []
            for item in antiquary_items[:10]:
                code = str(item.get("code") or "")
                quantity = max(1, int(item.get("quantity", 1) or 1))
                price = int(antiquary_prices.get(code, 0) or 0)
                lines.append(
                    f"`#{item.get('id', '?')}` {item.get('emoji', '🏺')} **{item.get('name', code)}** x{quantity} • {format_money(price)} / шт"
                )
            embed.add_field(name="Что можно сдать", value="\n".join(lines), inline=False)

        recipe_lines: list[str] = []
        for relic_code, recipe in RELIC_RECIPES.items():
            ready = True
            for part_code in recipe.get("parts", []):
                if count_general_items(user, item_type="antiquary_fragment", code=str(part_code)) <= 0:
                    ready = False
            recipe_value = int(antiquary_prices.get(relic_code, 0) or 0)
            status = "Готово к сборке" if ready else "Нужны фрагменты"
            recipe_lines.append(f"**{recipe['name']}** • {format_money(recipe_value)} • {status}")
        embed.add_field(name="Сборка реликвий", value="\n".join(recipe_lines), inline=False)
        embed.add_field(name="Мир сервера", value="\n".join(build_world_lines(snapshot)), inline=False)
        embed.set_footer(text="Используй кнопки BlackMarket 2.0, чтобы продать предмет по ID или собрать реликвию.")
        return embed

    async def sell_antiquary_item(self, user_id: int, guild_id: int, item_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            general_items = get_general_items(user)
            target = next(
                (
                    item
                    for item in general_items
                    if int(item.get("id", 0) or 0) == int(item_id)
                    and str(item.get("item_type") or "").startswith("antiquary_")
                ),
                None,
            )
            if not isinstance(target, dict):
                return False, "Такого предмета для Антиквара не найдено."

            code = str(target.get("code") or "")
            quantity = max(1, int(target.get("quantity", 1) or 1))
            snapshot = self._world_snapshot(guild_id)
            price_each = int(snapshot.get("antiquary_prices", {}).get(code, 0) or 0)
            if price_each <= 0:
                return False, "Антиквар не может оценить этот предмет прямо сейчас."
            consumed = consume_general_item(user, item_type=str(target.get("item_type") or ""), code=code, quantity=quantity)
            if consumed is None:
                return False, "Не удалось списать предмет из инвентаря."
            total = price_each * quantity
            user["balance"] = int(user.get("balance", 0) or 0) + total
            await db.update_user(user_id, guild_id, {"balance": user.get("balance", 0), "inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="🏺 Сделка с Антикваром",
            description=(
                f"Сдано: **{target.get('name', code)}** x{quantity}\n"
                f"Цена за штуку: **{format_money(price_each)}**\n"
                f"Итого: **{format_money(total)}**"
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def assemble_relic(self, user_id: int, guild_id: int, relic_code: str) -> tuple[bool, discord.Embed | str]:
        recipe = RELIC_RECIPES.get(relic_code)
        if not recipe:
            return False, "Такой реликвии не существует."
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            missing = [
                part_code
                for part_code in recipe.get("parts", [])
                if count_general_items(user, item_type="antiquary_fragment", code=str(part_code)) <= 0
            ]
            if missing:
                return False, "Нужные фрагменты ещё не собраны."
            for part_code in recipe.get("parts", []):
                consume_general_item(user, item_type="antiquary_fragment", code=str(part_code), quantity=1)
            definition = get_antiquary_definition(relic_code)
            if not definition:
                return False, "Данные реликвии повреждены."
            relic_item = add_general_item(
                user,
                item_type=str(definition.get("item_type") or "antiquary_relic"),
                code=relic_code,
                name=str(definition.get("name") or relic_code),
                emoji=str(definition.get("emoji") or "🏺"),
                description=str(definition.get("description") or "Собранная реликвия."),
                quantity=1,
                payload={"assembled": True, "family": str(definition.get("family") or relic_code)},
                stackable=True,
            )
            await db.update_user(user_id, guild_id, {"inventory": user.get("inventory"), "game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="🏺 Реликвия собрана",
            description=(
                f"Ты собрал **{recipe['name']}**.\n"
                f"Предмет отправлен в инвентарь под ID **#{relic_item['id']}** и теперь может быть продан Антиквару по полной цене."
            ),
            color=COLORS["success"],
        )
        return True, embed

    @app_commands.command(name="dive", description="Отправиться в подводное погружение")
    async def dive(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        await self.render_dive(interaction, interaction.user.id, interaction.guild_id)

    @app_commands.command(name="dig", description="Начать археологическую экспедицию")
    async def dig(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        await self.render_dig(interaction, interaction.user.id, interaction.guild_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdventuresCog(bot))
