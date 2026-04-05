from __future__ import annotations

import asyncio
import random
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import ALLOWED_CHANNEL_ID, COLORS
from database import db, get_user_lock
from inventory_system import add_general_item
from progression import (
    black_market_discount_multiplier,
    change_reputation,
    contract_rerolls_for_vip,
    contract_slots_for_vip,
    get_reputation,
    reputation_label,
    legendary_market_roll_chance,
    reputation_contract_bonus,
    reward_text,
    unlock_theme,
    unlock_title,
)
from utils import (
    check_channel,
    check_quest_progress,
    format_discord_deadline,
    get_kyiv_timezone,
    get_random_crypto,
    record_player_progress,
    safe_defer,
    schedule_message_cleanup,
    send_wrong_channel_message,
)

KYIV_TZ = get_kyiv_timezone()
EVENT_PING_ROLE_ID = 1486391112330379304
BLACK_MARKET_OFFER_COUNT = 5
BLACK_MARKET_ROTATION_HOURS = 12
MARKET_EVENT_COOLDOWN_HOURS = 2
MARKET_EVENT_SPAWN_CHANCE = 0.18

MARKET_EVENTS: dict[str, dict[str, Any]] = {
    "happy_hour": {
        "name": "Счастливый час",
        "description": "Все активные способы заработка дают больше денег.",
        "duration_hours": 2,
        "color": COLORS["gold"],
        "multipliers": {"economy": 1.25},
    },
    "crypto_boom": {
        "name": "Бум крипты",
        "description": "Доход из подвала и видеокарт растёт, а курс крипты в подвале становится горячее.",
        "duration_hours": 3,
        "color": COLORS["info"],
        "multipliers": {"mine": 1.35},
    },
    "fish_day": {
        "name": "Рыбный день",
        "description": "Шанс на редкий улов и цена рыбы немного выше обычного.",
        "duration_hours": 3,
        "color": COLORS["success"],
        "multipliers": {"fish": 1.18},
    },
    "tax_audit": {
        "name": "Налоговая проверка бизнесов",
        "description": "Доход с бизнесов режется, пока идёт проверка.",
        "duration_hours": 2,
        "color": COLORS["warning"],
        "multipliers": {"business": 0.8},
    },
}

CONTRACT_TEMPLATES = [
    {
        "code": "fish",
        "name": "Рыбный заказ",
        "description": "Поймай {target} рыб(ы).",
        "target_range": (3, 6),
        "reward_money_range": (1800, 3200),
        "reward_gems_range": (2, 5),
    },
    {
        "code": "mine",
        "name": "Шахтёрская смена",
        "description": "Отправься в майнинг {target} раз(а).",
        "target_range": (2, 4),
        "reward_money_range": (2200, 4200),
        "reward_gems_range": (2, 5),
    },
    {
        "code": "work",
        "name": "Трудовой контракт",
        "description": "Отработай {target} смен(ы).",
        "target_range": (2, 4),
        "reward_money_range": (1500, 2800),
        "reward_gems_range": (2, 4),
    },
    {
        "code": "crime",
        "name": "Тёмное дело",
        "description": "Сходи на crime {target} раз(а).",
        "target_range": (1, 2),
        "reward_money_range": (2400, 4000),
        "reward_gems_range": (3, 5),
    },
    {
        "code": "slut",
        "name": "Ночная подработка",
        "description": "Используй slut {target} раз(а).",
        "target_range": (1, 2),
        "reward_money_range": (1800, 3200),
        "reward_gems_range": (2, 4),
    },
    {
        "code": "play",
        "name": "Казино-план",
        "description": "Сыграй {target} игр(ы) в казино.",
        "target_range": (3, 5),
        "reward_money_range": (1800, 3600),
        "reward_gems_range": (2, 5),
    },
    {
        "code": "collect_business",
        "name": "Касса бизнеса",
        "description": "Собери доход с бизнесов {target} раз(а).",
        "target_range": (2, 4),
        "reward_money_range": (2600, 4600),
        "reward_gems_range": (3, 6),
    },
]

CONTRACT_DIFFICULTIES: dict[str, dict[str, Any]] = {
    "easy": {
        "name": "Лёгкий",
        "badge": "EASY",
        "target_multiplier": 0.85,
        "reward_multiplier": 0.9,
        "reward_gems_bonus": 0,
        "base_weight": 50,
        "min_reputation": -100,
    },
    "medium": {
        "name": "Средний",
        "badge": "MID",
        "target_multiplier": 1.0,
        "reward_multiplier": 1.1,
        "reward_gems_bonus": 1,
        "base_weight": 34,
        "min_reputation": -100,
    },
    "hard": {
        "name": "Редкий",
        "badge": "RARE",
        "target_multiplier": 1.25,
        "reward_multiplier": 1.55,
        "reward_gems_bonus": 3,
        "base_weight": 16,
        "min_reputation": 20,
    },
}

SCHEDULED_RARE_EVENTS: list[dict[str, Any]] = [
    {
        "key": "shadow_auction",
        "days": {4, 5},
        "hour": 21,
        "minute": 0,
        "window_minutes": 45,
        "name": "Shadow Auction",
        "description": "Редкая подпольная аукционная волна: рынок, crime и контракты становятся жирнее.",
        "duration_hours": 3,
        "color": COLORS["purple"],
        "multipliers": {"blackmarket": 0.9, "crime": 1.18, "contracts": 1.25},
    },
    {
        "key": "golden_rush",
        "days": {6},
        "hour": 18,
        "minute": 0,
        "window_minutes": 45,
        "name": "Golden Rush",
        "description": "Плановый редкий ивент с усиленной экономикой и премиями за активность.",
        "duration_hours": 2,
        "color": COLORS["gold"],
        "multipliers": {"economy": 1.4, "business": 1.15, "mine": 1.2},
    },
]

LEGENDARY_BLACK_MARKET_ITEMS: list[dict[str, Any]] = [
    {
        "code": "void_relic",
        "name": "Void Relic",
        "description": "Легендарный контрабандный тайник: титул, тема профиля, гемы и репутация.",
        "price": 85000,
        "currency": "money",
        "legendary": True,
        "grant": {
            "type": "cosmetic_pack",
            "gems": 60,
            "title": "void_monarch",
            "theme": "abyss",
            "reputation": 25,
        },
    }
]

BLACK_MARKET_ITEMS = [
    {
        "code": "worms_bundle",
        "name": "Ящик червей",
        "description": "Добавляет 5 обычных наживок для рыбалки.",
        "price": 2400,
        "currency": "money",
        "grant": {"type": "bait", "bait": "worms", "amount": 5},
    },
    {
        "code": "shrimp_bundle",
        "name": "Пакет креветок",
        "description": "Добавляет 4 наживки для охоты на редкую рыбу.",
        "price": 8,
        "currency": "gems",
        "grant": {"type": "bait", "bait": "shrimp", "amount": 4},
    },
    {
        "code": "glow_bundle",
        "name": "Светящаяся приманка",
        "description": "Добавляет 3 сильные наживки для ночных и дорогих спотов.",
        "price": 16,
        "currency": "gems",
        "grant": {"type": "bait", "bait": "glow", "amount": 3},
    },
    {
        "code": "dirty_cash",
        "name": "Грязный кеш",
        "description": "Мгновенно выдаёт пачку наличных.",
        "price": 12,
        "currency": "gems",
        "grant": {"type": "money", "amount": 15000},
    },
    {
        "code": "shield_card",
        "name": "Теневая страховка",
        "description": "Даёт защиту от рисковых систем на 24 часа.",
        "price": 20,
        "currency": "gems",
        "grant": {"type": "shield", "hours": 24},
    },
]


MARKET_EVENTS["happy_hour"]["name"] = "Счастливый час"
MARKET_EVENTS["happy_hour"]["description"] = "Все активные способы заработка дают больше денег."
MARKET_EVENTS["crypto_boom"]["name"] = "Бум крипты"
MARKET_EVENTS["crypto_boom"]["description"] = "Доход из подвала и видеокарт растёт, а курс крипты в подвале становится горячее."
MARKET_EVENTS["fish_day"]["name"] = "Рыбный день"
MARKET_EVENTS["fish_day"]["description"] = "Шанс на редкий улов и цена рыбы заметно выше."
MARKET_EVENTS["tax_audit"]["name"] = "Налоговая проверка бизнесов"
MARKET_EVENTS["tax_audit"]["description"] = "Доход с бизнесов режется, пока идёт проверка."

for template in CONTRACT_TEMPLATES:
    if template["code"] == "fish":
        template["name"] = "Рыбный заказ"
        template["description"] = "Поймай {target} рыб(ы)."
    elif template["code"] == "mine":
        template["name"] = "Доход из подвала"
        template["description"] = "Собери доход из подвала {target} раз(а)."
        template["reward_money_range"] = (2400, 4200)
    elif template["code"] == "work":
        template["name"] = "Трудовой контракт"
        template["description"] = "Отработай {target} смен(ы)."
    elif template["code"] == "crime":
        template["name"] = "Тёмное дело"
        template["description"] = "Сходи на crime {target} раз(а)."
    elif template["code"] == "slut":
        template["name"] = "Ночная подработка"
        template["description"] = "Используй slut {target} раз(а)."
    elif template["code"] == "play":
        template["name"] = "Казино-план"
        template["description"] = "Сыграй {target} игр(ы) в казино."
    elif template["code"] == "collect_business":
        template["name"] = "Касса бизнеса"
        template["description"] = "Собери доход с бизнесов {target} раз(а)."

if not any(template.get("code") == "rent" for template in CONTRACT_TEMPLATES):
    CONTRACT_TEMPLATES.append(
        {
            "code": "rent",
            "name": "Арендный поток",
            "description": "Закрой аренду {target} раз(а).",
            "target_range": (1, 3),
            "reward_money_range": (2600, 4800),
            "reward_gems_range": (3, 6),
        }
    )

for item in BLACK_MARKET_ITEMS:
    if item["code"] == "worms_bundle":
        item["name"] = "Ящик червей"
        item["description"] = "Добавляет 5 обычных наживок для рыбалки."
    elif item["code"] == "shrimp_bundle":
        item["name"] = "Пакет креветок"
        item["description"] = "Добавляет 4 наживки для охоты на редкую рыбу."
    elif item["code"] == "glow_bundle":
        item["name"] = "Светящаяся приманка"
        item["description"] = "Добавляет 3 сильные наживки для ночных и дорогих спотов."
    elif item["code"] == "dirty_cash":
        item["name"] = "Грязный кэш"
        item["description"] = "Мгновенно выдаёт пачку наличных."
    elif item["code"] == "shield_card":
        item["name"] = "Теневая страховка"
        item["description"] = "Даёт защиту от рискованных систем на 24 часа."

if not any(item.get("code") == "basement_cache" for item in BLACK_MARKET_ITEMS):
    BLACK_MARKET_ITEMS.insert(
        3,
        {
            "code": "basement_cache",
            "name": "Сейф подвала",
            "description": "Сразу добавляет наличные в кошелёк подвала. Если дома ещё нет, деньги упадут на баланс.",
            "price": 6800,
            "currency": "money",
            "grant": {"type": "house_wallet", "amount": 18000},
        },
    )


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


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


def _fishing_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _systems_state(user)
    fishing = systems.get("fishing")
    if not isinstance(fishing, dict):
        fishing = {}
    fishing.setdefault("owned_tackles", ["starter"])
    fishing.setdefault("equipped_tackle", "starter")
    fishing.setdefault("bait_stock", {"worms": 0, "shrimp": 0, "glow": 0})
    fishing.setdefault("equipped_bait", None)
    fishing.setdefault("unlocked_zones", ["river_bank"])
    fishing.setdefault("selected_zone", "river_bank")
    fishing.setdefault("total_catches", 0)
    fishing.setdefault("last_catch", None)
    systems["fishing"] = fishing
    return fishing


def _contract_day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(KYIV_TZ)
    return now.astimezone(KYIV_TZ).strftime("%Y-%m-%d")


def _contract_rng_seed(user_id: int, day_key: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(f"{user_id}:{day_key}"))


def _black_market_rotation_start(now: datetime | None = None) -> datetime:
    local_now = now or datetime.now(KYIV_TZ)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=timezone.utc)
    local_now = local_now.astimezone(KYIV_TZ)
    start_hour = local_now.hour - (local_now.hour % BLACK_MARKET_ROTATION_HOURS)
    return local_now.replace(hour=start_hour, minute=0, second=0, microsecond=0)


def _black_market_rotation_key(now: datetime | None = None) -> str:
    return _black_market_rotation_start(now).strftime("%Y%m%d%H")


def _next_black_market_refresh(now: datetime | None = None) -> datetime:
    return (_black_market_rotation_start(now) + timedelta(hours=BLACK_MARKET_ROTATION_HOURS)).astimezone(timezone.utc)


def _black_market_rep_bucket(reputation: int) -> int:
    return max(-4, min(4, int(reputation) // 25))


def _black_market_offers_for_user(user_id: int, rotation_key: str, reputation: int = 0) -> list[dict[str, Any]]:
    seed_key = f"blackmarket:{rotation_key}:{_black_market_rep_bucket(reputation)}"
    rng = random.Random(_contract_rng_seed(int(user_id or 0), seed_key))
    normal_slots = BLACK_MARKET_OFFER_COUNT
    offers: list[dict[str, Any]] = []
    legendary_roll = rng.random() < legendary_market_roll_chance(reputation)

    if legendary_roll and LEGENDARY_BLACK_MARKET_ITEMS:
        normal_slots -= 1
        offers.append(deepcopy(rng.choice(LEGENDARY_BLACK_MARKET_ITEMS)))

    offers.extend(rng.sample(BLACK_MARKET_ITEMS, k=min(normal_slots, len(BLACK_MARKET_ITEMS))))
    return [deepcopy(offer) for offer in offers]


def _roll_contract_difficulty(rng: random.Random, reputation: int) -> tuple[str, dict[str, Any]]:
    eligible = []
    for key, payload in CONTRACT_DIFFICULTIES.items():
        if reputation < int(payload.get("min_reputation", -100)):
            continue
        weight = int(payload.get("base_weight", 1))
        if key == "hard":
            weight = int(round(weight * (1 + reputation_contract_bonus(reputation) * 3)))
        eligible.append((key, payload, max(1, weight)))

    if not eligible:
        return "easy", CONTRACT_DIFFICULTIES["easy"]

    selected = rng.choices(
        eligible,
        weights=[item[2] for item in eligible],
        k=1,
    )[0]
    return selected[0], selected[1]


def _generate_contracts(
    user_id: int,
    day_key: str,
    *,
    slot_count: int = 3,
    reputation: int = 0,
) -> list[dict[str, Any]]:
    rng = random.Random(_contract_rng_seed(user_id, day_key))
    templates = rng.sample(CONTRACT_TEMPLATES, k=min(slot_count, len(CONTRACT_TEMPLATES)))
    contracts: list[dict[str, Any]] = []
    for index, template in enumerate(templates, start=1):
        difficulty_key, difficulty = _roll_contract_difficulty(rng, reputation)
        target = max(1, int(round(rng.randint(*template["target_range"]) * float(difficulty["target_multiplier"]))))
        reward_money = int(round(rng.randint(*template["reward_money_range"]) * float(difficulty["reward_multiplier"])))
        reward_gems = int(rng.randint(*template["reward_gems_range"]) + int(difficulty.get("reward_gems_bonus", 0)))
        contracts.append(
            {
                "id": f"{template['code']}_{index}",
                "code": template["code"],
                "name": template["name"],
                "difficulty": difficulty_key,
                "difficulty_name": str(difficulty["name"]),
                "difficulty_badge": str(difficulty["badge"]),
                "description": template["description"].format(target=target),
                "target": target,
                "progress": 0,
                "claimed": False,
                "reward_money": reward_money,
                "reward_gems": reward_gems,
            }
        )
    return contracts


def _ensure_contracts(user: dict[str, Any]) -> dict[str, Any]:
    systems = _systems_state(user)
    contracts = systems.get("contracts")
    today = _contract_day_key()
    vip_level = int(user.get("vip_level", 0) or 0)
    reputation = get_reputation(user)
    slot_count = contract_slots_for_vip(vip_level)
    if not isinstance(contracts, dict) or contracts.get("day") != today:
        contracts = {
            "day": today,
            "rerolls_used": 0,
            "items": _generate_contracts(
                int(user.get("user_id", 0) or 0),
                today,
                slot_count=slot_count,
                reputation=reputation,
            ),
        }
        systems["contracts"] = contracts
    contracts.setdefault("rerolls_used", 0)
    contracts.setdefault("items", [])
    current_items = list(contracts.get("items", []))
    if len(current_items) < slot_count:
        extra_items = _generate_contracts(
            int(user.get("user_id", 0) or 0),
            today,
            slot_count=slot_count,
            reputation=reputation,
        )
        used_ids = {item.get("id") for item in current_items}
        for item in extra_items:
            if item.get("id") in used_ids:
                continue
            current_items.append(item)
            used_ids.add(item.get("id"))
            if len(current_items) >= slot_count:
                break
        contracts["items"] = current_items
    return contracts


def _ensure_black_market_state(
    user: dict[str, Any],
    user_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    systems = _systems_state(user)
    state = systems.get("black_market")
    rotation = _black_market_rotation_key(now)
    resolved_user_id = int(user_id or user.get("user_id", 0) or 0)
    reputation = get_reputation(user)
    if not isinstance(state, dict) or state.get("rotation") != rotation:
        state = {
            "rotation": rotation,
            "purchased": [],
            "offers": _black_market_offers_for_user(resolved_user_id, rotation, reputation),
        }
        systems["black_market"] = state
        return state

    purchased_raw = state.get("purchased")
    purchased = [str(code) for code in purchased_raw if code] if isinstance(purchased_raw, list) else []
    offers_raw = state.get("offers")
    offers = [deepcopy(offer) for offer in offers_raw if isinstance(offer, dict)] if isinstance(offers_raw, list) else []
    if not offers:
        offers = _black_market_offers_for_user(resolved_user_id, rotation, reputation)

    normalized = {
        "rotation": rotation,
        "purchased": purchased,
        "offers": offers,
    }
    systems["black_market"] = normalized
    return normalized


def _daily_black_market_offers(day_key: str, reputation: int = 0) -> list[dict[str, Any]]:
    return _black_market_offers_for_user(0, day_key, reputation)


class ContractsView(discord.ui.View):
    def __init__(self, cog: "SystemsCog", user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню контрактов открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _refresh(self, interaction: discord.Interaction):
        embed = await self.cog.build_contracts_embed(self.user_id, self.guild_id)
        self._sync_buttons(await self.cog.get_contracts(self.user_id, self.guild_id))
        await interaction.edit_original_response(embed=embed, view=self)
        await self._remember_message(interaction)

    def _sync_buttons(self, contracts: list[dict[str, Any]]):
        buttons = [self.claim_1, self.claim_2, self.claim_3]
        for index, button in enumerate(buttons):
            if index >= len(contracts):
                button.disabled = True
                button.label = "Нет контракта"
                continue
            item = contracts[index]
            done = int(item.get("progress", 0) or 0) >= int(item.get("target", 0) or 0)
            claimed = bool(item.get("claimed"))
            button.disabled = not done or claimed
            button.label = "Забрано" if claimed else f"Забрать #{index + 1}"

    async def _claim(self, interaction: discord.Interaction, slot: int):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            _, payload = await self.cog.claim_contract_reward(self.user_id, self.guild_id, slot)
            await self._refresh(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="Забрать #1", style=discord.ButtonStyle.success, row=0)
    async def claim_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 0)

    @discord.ui.button(label="Забрать #2", style=discord.ButtonStyle.success, row=0)
    async def claim_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 1)

    @discord.ui.button(label="Забрать #3", style=discord.ButtonStyle.success, row=0)
    async def claim_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 2)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh(interaction)

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


class ContractsViewV2(discord.ui.View):
    def __init__(self, cog: "SystemsCog", user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню контрактов открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _refresh(self, interaction: discord.Interaction):
        embed = await self.cog.build_contracts_embed(self.user_id, self.guild_id)
        self._sync_buttons(await self.cog.get_contracts(self.user_id, self.guild_id))
        await interaction.edit_original_response(embed=embed, view=self)
        await self._remember_message(interaction)

    def _sync_buttons(self, contracts: list[dict[str, Any]]):
        buttons = [self.claim_1, self.claim_2, self.claim_3, self.claim_4, self.claim_5]
        for index, button in enumerate(buttons):
            if index >= len(contracts):
                button.disabled = True
                button.label = "Нет контракта"
                continue
            item = contracts[index]
            done = int(item.get("progress", 0) or 0) >= int(item.get("target", 0) or 0)
            claimed = bool(item.get("claimed"))
            badge = str(item.get("difficulty_badge", ""))
            button.disabled = not done or claimed
            button.label = "Забрано" if claimed else f"{badge} #{index + 1}".strip()

        rerolls_left, rerolls_total = self.cog.get_contract_rerolls_left_sync(self.user_id, self.guild_id)
        self.reroll_btn.disabled = rerolls_left <= 0
        self.reroll_btn.label = f"Обновить {rerolls_left}/{rerolls_total}"

    async def _claim(self, interaction: discord.Interaction, slot: int):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            _, payload = await self.cog.claim_contract_reward(self.user_id, self.guild_id, slot)
            await self._refresh(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="Забрать #1", style=discord.ButtonStyle.success, row=0)
    async def claim_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 0)

    @discord.ui.button(label="Забрать #2", style=discord.ButtonStyle.success, row=0)
    async def claim_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 1)

    @discord.ui.button(label="Забрать #3", style=discord.ButtonStyle.success, row=0)
    async def claim_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 2)

    @discord.ui.button(label="Забрать #4", style=discord.ButtonStyle.success, row=1)
    async def claim_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 3)

    @discord.ui.button(label="Забрать #5", style=discord.ButtonStyle.success, row=1)
    async def claim_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._claim(interaction, 4)

    @discord.ui.button(label="Обновить список", style=discord.ButtonStyle.primary, row=2)
    async def reroll_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            _, payload = await self.cog.reroll_contracts(self.user_id, self.guild_id)
            await self._refresh(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh(interaction)

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


class BlackMarketView(discord.ui.View):
    def __init__(self, cog: "SystemsCog", user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню чёрного рынка открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    def _sync_buttons(self, offers: list[dict[str, Any]], purchased: set[str]):
        buttons = [self.buy_1, self.buy_2, self.buy_3, self.buy_4, self.buy_5]
        for index, button in enumerate(buttons):
            if index >= len(offers):
                button.disabled = True
                button.label = "Нет лота"
                continue
            offer = offers[index]
            already = offer["code"] in purchased
            button.disabled = already
            button.label = "Куплено" if already else f"Купить #{index + 1}"

    async def _refresh(self, interaction: discord.Interaction):
        offers, purchased = await self.cog.get_black_market_offers(self.user_id, self.guild_id)
        self._sync_buttons(offers, purchased)
        embed = await self.cog.build_black_market_embed(self.user_id, self.guild_id)
        await interaction.edit_original_response(embed=embed, view=self)
        await self._remember_message(interaction)

    async def _buy(self, interaction: discord.Interaction, slot: int):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            _, payload = await self.cog.buy_black_market_offer(self.user_id, self.guild_id, slot)
            await self._refresh(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="Купить #1", style=discord.ButtonStyle.danger, row=0)
    async def buy_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy(interaction, 0)

    @discord.ui.button(label="Купить #2", style=discord.ButtonStyle.danger, row=0)
    async def buy_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy(interaction, 1)

    @discord.ui.button(label="Купить #3", style=discord.ButtonStyle.danger, row=0)
    async def buy_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy(interaction, 2)

    @discord.ui.button(label="Купить #4", style=discord.ButtonStyle.danger, row=1)
    async def buy_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy(interaction, 3)

    @discord.ui.button(label="Купить #5", style=discord.ButtonStyle.danger, row=1)
    async def buy_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy(interaction, 4)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh(interaction)

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


class SystemsCog(commands.Cog, name="Systems"):
    def __init__(self, bot):
        self.bot = bot
        self.active_events: dict[int, dict[str, Any]] = {}
        self.next_event_after: dict[int, datetime] = {}
        self._contract_reroll_cache: dict[tuple[int, int], tuple[int, int]] = {}
        self._scheduled_event_runs: set[str] = set()

    def get_contract_rerolls_left_sync(self, user_id: int, guild_id: int) -> tuple[int, int]:
        return self._contract_reroll_cache.get((int(user_id), int(guild_id)), (1, 1))

    @staticmethod
    def _build_event_payload(event_key: str, template: dict[str, Any], now: datetime) -> dict[str, Any]:
        return {
            "key": event_key,
            "name": template["name"],
            "description": template["description"],
            "color": template["color"],
            "multipliers": dict(template["multipliers"]),
            "expires_at": now + timedelta(hours=int(template["duration_hours"])),
        }

    @staticmethod
    def _normalize_market_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not value:
            return None
        try:
            text = str(value).strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    @classmethod
    def _serialize_market_event(cls, event: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        expires_at = cls._normalize_market_datetime(event.get("expires_at"))
        if expires_at is None:
            return None
        return {
            "key": str(event.get("key") or ""),
            "name": str(event.get("name") or ""),
            "description": str(event.get("description") or ""),
            "color": int(event.get("color") or COLORS["info"]),
            "multipliers": dict(event.get("multipliers") or {}),
            "expires_at": expires_at.isoformat(),
        }

    @classmethod
    def _deserialize_market_event(cls, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        expires_at = cls._normalize_market_datetime(payload.get("expires_at"))
        if expires_at is None:
            return None
        return {
            "key": str(payload.get("key") or ""),
            "name": str(payload.get("name") or ""),
            "description": str(payload.get("description") or ""),
            "color": int(payload.get("color") or COLORS["info"]),
            "multipliers": dict(payload.get("multipliers") or {}),
            "expires_at": expires_at,
        }

    async def _persist_market_state(self, guild_id: int) -> None:
        guild_key = int(guild_id)
        active_event = self.active_events.get(guild_key)
        next_event_after = self.next_event_after.get(guild_key)
        await db.upsert_market_guild_state(
            guild_key,
            {
                "active_event": self._serialize_market_event(active_event),
                "next_event_after": next_event_after.isoformat() if isinstance(next_event_after, datetime) else None,
            },
        )

    async def _restore_market_states(self) -> None:
        now = datetime.now(timezone.utc)
        for guild in self.bot.guilds:
            state = await db.get_market_guild_state(guild.id)
            restored_event = self._deserialize_market_event(state.get("active_event"))
            next_event_after = self._normalize_market_datetime(state.get("next_event_after"))
            changed = False

            if restored_event is not None and now >= restored_event["expires_at"]:
                cooldown_until = restored_event["expires_at"] + timedelta(hours=MARKET_EVENT_COOLDOWN_HOURS)
                if next_event_after is None or cooldown_until > next_event_after:
                    next_event_after = cooldown_until
                restored_event = None
                changed = True

            if restored_event is not None:
                self.active_events[guild.id] = restored_event
            else:
                self.active_events.pop(guild.id, None)

            if next_event_after is not None and next_event_after > now:
                self.next_event_after[guild.id] = next_event_after
            else:
                if next_event_after is not None:
                    changed = True
                self.next_event_after.pop(guild.id, None)

            if changed:
                await self._persist_market_state(guild.id)

    def _pick_scheduled_event(self, guild_id: int, now: datetime) -> dict[str, Any] | None:
        kyiv_now = now.astimezone(KYIV_TZ)
        for template in SCHEDULED_RARE_EVENTS:
            if kyiv_now.weekday() not in set(template.get("days", set())):
                continue

            start = kyiv_now.replace(
                hour=int(template["hour"]),
                minute=int(template.get("minute", 0)),
                second=0,
                microsecond=0,
            )
            end = start + timedelta(minutes=int(template.get("window_minutes", 30)))
            if not (start <= kyiv_now <= end):
                continue

            signature = f"{guild_id}:{template['key']}:{start.isoformat()}"
            if signature in self._scheduled_event_runs:
                continue

            self._scheduled_event_runs.add(signature)
            return self._build_event_payload(str(template["key"]), template, now)
        return None

    @staticmethod
    def _is_event_message(message: discord.Message) -> bool:
        if not message.author.bot or not message.embeds:
            return False
        embed = message.embeds[0]
        return isinstance(embed.title, str) and embed.title.startswith("📣 Рыночное событие:")

    @staticmethod
    def _event_embed_signature(event: dict[str, Any]) -> tuple[str, str]:
        title = f"📣 Рыночное событие: {event['name']}"
        description = f"{event['description']}\n\nЗакончится: {format_discord_deadline(event['expires_at'])}."
        return title, description

    async def _pin_message(self, message: discord.Message):
        try:
            if not message.pinned:
                await message.pin(reason="Активное рыночное событие")
        except Exception:
            pass

    async def _cleanup_old_event_pins(self, channel: discord.TextChannel, keep_message_id: int | None = None):
        try:
            pinned_messages = await channel.pins()
        except Exception:
            return

        for pinned in pinned_messages:
            if pinned.id == keep_message_id or not self._is_event_message(pinned):
                continue
            try:
                await pinned.unpin(reason="Оставляем только актуальное событие")
            except Exception:
                continue

    async def _find_matching_event_message(self, channel: discord.TextChannel, event: dict[str, Any]) -> discord.Message | None:
        expected_title, expected_description = self._event_embed_signature(event)

        try:
            pinned_messages = await channel.pins()
        except Exception:
            pinned_messages = []

        for message in pinned_messages:
            if not self._is_event_message(message):
                continue
            embed = message.embeds[0]
            if embed.title == expected_title and embed.description == expected_description:
                return message

        async for message in channel.history(limit=20):
            if not self._is_event_message(message):
                continue
            embed = message.embeds[0]
            if embed.title == expected_title and embed.description == expected_description:
                return message
        return None

    async def cog_load(self):
        if not self.market_events_loop.is_running():
            self.market_events_loop.start()

    def cog_unload(self):
        self.market_events_loop.cancel()

    def get_active_event(self, guild_id: int | None) -> dict[str, Any] | None:
        if guild_id is None:
            return None
        event = self.active_events.get(int(guild_id))
        if not event:
            return None
        if datetime.now(timezone.utc) >= event["expires_at"]:
            self.active_events.pop(int(guild_id), None)
            cooldown_until = event["expires_at"] + timedelta(hours=MARKET_EVENT_COOLDOWN_HOURS)
            existing = self.next_event_after.get(int(guild_id))
            if existing is None or cooldown_until > existing:
                self.next_event_after[int(guild_id)] = cooldown_until
            asyncio.create_task(self._persist_market_state(int(guild_id)))
            return None
        return event

    def get_reward_multiplier(self, guild_id: int | None, category: str) -> tuple[float, dict[str, Any] | None]:
        event = self.get_active_event(guild_id)
        if not event:
            return 1.0, None
        return float(event["multipliers"].get(category, 1.0)), event

    async def progress_contracts(self, user_id: int, guild_id: int, contract_type: str, amount: int = 1):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return

            contracts_state = _ensure_contracts(user)
            changed = False
            for item in contracts_state.get("items", []):
                if item.get("code") != contract_type or item.get("claimed"):
                    continue
                target = int(item.get("target", 0) or 0)
                current = int(item.get("progress", 0) or 0)
                new_value = min(target, current + amount)
                if new_value != current:
                    item["progress"] = new_value
                    changed = True

            if changed:
                await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

    async def reroll_contracts(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            contracts_state = _ensure_contracts(user)
            max_rerolls = contract_rerolls_for_vip(int(user.get("vip_level", 0) or 0))
            used_rerolls = int(contracts_state.get("rerolls_used", 0) or 0)
            if used_rerolls >= max_rerolls:
                self._contract_reroll_cache[(int(user_id), int(guild_id))] = (0, max_rerolls)
                return False, "Сегодня рероллы контрактов уже закончились."

            slot_count = contract_slots_for_vip(int(user.get("vip_level", 0) or 0))
            reroll_seed = f"{contracts_state['day']}:reroll:{used_rerolls + 1}"
            contracts_state["items"] = _generate_contracts(
                user_id,
                reroll_seed,
                slot_count=slot_count,
                reputation=get_reputation(user),
            )
            contracts_state["rerolls_used"] = used_rerolls + 1
            rerolls_left = max(0, max_rerolls - contracts_state["rerolls_used"])
            self._contract_reroll_cache[(int(user_id), int(guild_id))] = (rerolls_left, max_rerolls)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        embed = discord.Embed(
            title="Контракты обновлены",
            description=(
                "Список контрактов пересобран.\n"
                f"Осталось рероллов на сегодня: **{rerolls_left}/{max_rerolls}**"
            ),
            color=COLORS["info"],
        )
        if active_event is not None and multiplier != 1.0:
            embed.add_field(name="Событие", value=f"Бонус от ивента **{active_event['name']}** уже учтён.", inline=False)
        return True, embed

    async def claim_contract_reward(self, user_id: int, guild_id: int, slot: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            contracts_state = _ensure_contracts(user)
            items = contracts_state.get("items", [])
            if slot >= len(items):
                return False, "Такого контракта нет."

            item = items[slot]
            if item.get("claimed"):
                return False, "Награда по этому контракту уже забрана."
            if int(item.get("progress", 0) or 0) < int(item.get("target", 0) or 0):
                return False, "Этот контракт ещё не выполнен."

            money = int(item.get("reward_money", 0) or 0)
            gems = int(item.get("reward_gems", 0) or 0)
            multiplier, active_event = self.get_reward_multiplier(guild_id, "contracts")
            if multiplier != 1.0:
                money = max(1, int(round(money * multiplier)))
                if multiplier > 1:
                    gems += max(1, int(round((multiplier - 1) * 5)))
            item["claimed"] = True
            user["balance"] = int(user.get("balance", 0) or 0) + money
            user["gems"] = int(user.get("gems", 0) or 0) + gems
            await db.update_user(
                user_id,
                guild_id,
                {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})},
            )
            asyncio.create_task(check_quest_progress(user_id, guild_id, "contracts", 1))
            asyncio.create_task(check_quest_progress(user_id, guild_id, "earn", money))

        embed = discord.Embed(
            title="Контракт закрыт",
            description=(
                f"**{item['name']}** выполнен.\n"
                f"Награда: **{format_money(money)}** и **{gems} гем.**\n"
                f"Баланс: **{format_money(user['balance'])}**"
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def build_contracts_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Контракты", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        contracts_state = _ensure_contracts(user)
        items = contracts_state.get("items", [])
        tomorrow = datetime.now(KYIV_TZ).date() + timedelta(days=1)
        reset_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KYIV_TZ)
        embed = discord.Embed(
            title="📋 Контракты дня",
            description=f"Новые заказы появятся {format_discord_deadline(reset_at)}.",
            color=COLORS["info"],
        )
        for index, item in enumerate(items, start=1):
            progress = int(item.get("progress", 0) or 0)
            target = int(item.get("target", 0) or 0)
            status = "Забрано" if item.get("claimed") else "Готово" if progress >= target else "В процессе"
            embed.add_field(
                name=f"{index}. {item['name']}",
                value=(
                    f"{item['description']}\n"
                    f"Прогресс: **{progress}/{target}**\n"
                    f"Награда: **{format_money(item['reward_money'])}** + **{item['reward_gems']} гем.**\n"
                    f"Статус: **{status}**"
                ),
                inline=False,
            )
        embed.set_footer(text="Выполняй контракты обычными командами бота и забирай награду кнопками ниже.")
        return embed

    async def get_black_market_offers(self, user_id: int, guild_id: int) -> tuple[list[dict[str, Any]], set[str]]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return [], set()
            state = _ensure_black_market_state(user)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
            offers = _daily_black_market_offers(state["day"])
            return offers, set(state.get("purchased", []))

    async def buy_black_market_offer(self, user_id: int, guild_id: int, slot: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            state = _ensure_black_market_state(user)
            offers = _daily_black_market_offers(state["day"])
            if slot >= len(offers):
                return False, "Такого лота нет."

            offer = offers[slot]
            if offer["code"] in set(state.get("purchased", [])):
                return False, "Этот лот уже куплен сегодня."

            price = int(offer["price"])
            currency = str(offer["currency"]).lower()
            if currency == "gems":
                if int(user.get("gems", 0) or 0) < price:
                    return False, f"Не хватает гемов. Нужно: **{price}**."
                user["gems"] = int(user.get("gems", 0) or 0) - price
            else:
                if int(user.get("balance", 0) or 0) < price:
                    return False, f"Не хватает денег. Нужно: **{format_money(price)}**."
                user["balance"] = int(user.get("balance", 0) or 0) - price

            result_lines: list[str] = []
            grant = offer["grant"]
            if grant["type"] == "bait":
                fishing = _fishing_state(user)
                bait_stock = fishing.setdefault("bait_stock", {})
                bait_key = grant["bait"]
                bait_stock[bait_key] = int(bait_stock.get(bait_key, 0) or 0) + int(grant["amount"])
                if not fishing.get("equipped_bait"):
                    fishing["equipped_bait"] = bait_key
                result_lines.append(f"Добавлено: **{grant['amount']}x {offer['name']}**")
            elif grant["type"] == "house_wallet":
                amount = int(grant["amount"])
                systems = _systems_state(user)
                house = systems.get("house")
                if not isinstance(house, dict):
                    house = {}
                    systems["house"] = house
                if house.get("owned_house_id"):
                    house["mining_wallet"] = int(house.get("mining_wallet", 0) or 0) + amount
                    result_lines.append(f"В подвал добавлено: **{format_money(amount)}**")
                else:
                    user["balance"] = int(user.get("balance", 0) or 0) + amount
                    result_lines.append(f"Дома ещё нет, поэтому на баланс зачислено: **{format_money(amount)}**")
            elif grant["type"] == "crypto":
                crypto = get_random_crypto()
                payout = int(round(float(crypto.get("value", 0) or 0)))
                user["balance"] = int(user.get("balance", 0) or 0) + payout
                result_lines.append(f"Получено: **{crypto['emoji']} {crypto['name']} {crypto['amount']}**, позиция сразу продана за **{format_money(payout)}**")
            elif grant["type"] == "money":
                amount = int(grant["amount"])
                user["balance"] = int(user.get("balance", 0) or 0) + amount
                result_lines.append(f"Получено: **{format_money(amount)}**")
            elif grant["type"] == "shield":
                hours = int(grant["hours"])
                user["shield_until"] = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
                result_lines.append(f"Щит активирован на **{hours} ч**")

            purchased = list(state.get("purchased", []))
            purchased.append(offer["code"])
            state["purchased"] = purchased

            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user.get("balance", 0),
                    "gems": user.get("gems", 0),
                    "shield_until": user.get("shield_until"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        embed = discord.Embed(
            title="Сделка завершена",
            description=(
                f"Куплено: **{offer['name']}**\n"
                f"Цена: **{format_money(price) if currency == 'money' else f'{price} гем.'}**\n"
                + "\n".join(result_lines)
            ),
            color=COLORS["success"],
        )
        return True, embed

    async def build_black_market_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Чёрный рынок", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        state = _ensure_black_market_state(user)
        offers = _daily_black_market_offers(state["day"])
        purchased = set(state.get("purchased", []))
        tomorrow = datetime.now(KYIV_TZ).date() + timedelta(days=1)
        reset_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KYIV_TZ)

        embed = discord.Embed(
            title="🕶 Чёрный рынок",
            description=f"Общий рынок на сегодня. Обновление: {format_discord_deadline(reset_at)}.",
            color=COLORS["warning"],
        )
        embed.add_field(
            name="Кошелёк",
            value=(
                f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
            ),
            inline=False,
        )
        embed.add_field(name="Обновление рынка", value=format_discord_deadline(reset_at), inline=False)
        for index, offer in enumerate(offers, start=1):
            status = "Куплено" if offer["code"] in purchased else "Доступно"
            price = format_money(offer["price"]) if offer["currency"] == "money" else f"{offer['price']} гем."
            embed.add_field(
                name=f"{index}. {offer['name']}",
                value=f"{offer['description']}\nЦена: **{price}**\nСтатус: **{status}**",
                inline=False,
            )
        return embed

    async def get_contracts(self, user_id: int, guild_id: int) -> list[dict[str, Any]]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                self._contract_reroll_cache[(int(user_id), int(guild_id))] = (1, 1)
                return []

            contracts_state = _ensure_contracts(user)
            max_rerolls = contract_rerolls_for_vip(int(user.get("vip_level", 0) or 0))
            used_rerolls = int(contracts_state.get("rerolls_used", 0) or 0)
            self._contract_reroll_cache[(int(user_id), int(guild_id))] = (max(0, max_rerolls - used_rerolls), max_rerolls)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
            return list(contracts_state.get("items", []))

    async def reroll_contracts(self, user_id: int, guild_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            contracts_state = _ensure_contracts(user)
            max_rerolls = contract_rerolls_for_vip(int(user.get("vip_level", 0) or 0))
            used_rerolls = int(contracts_state.get("rerolls_used", 0) or 0)
            if used_rerolls >= max_rerolls:
                self._contract_reroll_cache[(int(user_id), int(guild_id))] = (0, max_rerolls)
                return False, "Сегодня рероллы контрактов уже закончились."

            contracts_state["rerolls_used"] = used_rerolls + 1
            contracts_state["items"] = _generate_contracts(
                user_id,
                f"{contracts_state['day']}:reroll:{contracts_state['rerolls_used']}",
                slot_count=contract_slots_for_vip(int(user.get("vip_level", 0) or 0)),
                reputation=get_reputation(user),
            )
            rerolls_left = max(0, max_rerolls - contracts_state["rerolls_used"])
            self._contract_reroll_cache[(int(user_id), int(guild_id))] = (rerolls_left, max_rerolls)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        return True, discord.Embed(
            title="Контракты обновлены",
            description=f"Список контрактов пересобран. Осталось рероллов: **{rerolls_left}/{max_rerolls}**",
            color=COLORS["info"],
        )

    async def claim_contract_reward(self, user_id: int, guild_id: int, slot: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            contracts_state = _ensure_contracts(user)
            items = list(contracts_state.get("items", []))
            if slot >= len(items):
                return False, "Такого контракта нет."

            item = items[slot]
            if bool(item.get("claimed")):
                return False, "Награда по этому контракту уже забрана."
            if int(item.get("progress", 0) or 0) < int(item.get("target", 0) or 0):
                return False, "Этот контракт ещё не выполнен."

            reward_money = int(item.get("reward_money", 0) or 0)
            reward_gems = int(item.get("reward_gems", 0) or 0)
            multiplier, active_event = self.get_reward_multiplier(guild_id, "contracts")
            if multiplier != 1.0:
                reward_money = max(1, int(round(reward_money * multiplier)))
                if multiplier > 1:
                    reward_gems += max(1, int(round((multiplier - 1) * 5)))

            item["claimed"] = True
            user["balance"] = int(user.get("balance", 0) or 0) + reward_money
            user["gems"] = int(user.get("gems", 0) or 0) + reward_gems
            await db.update_user(
                user_id,
                guild_id,
                {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})},
            )
            asyncio.create_task(check_quest_progress(user_id, guild_id, "contracts", 1))
            asyncio.create_task(check_quest_progress(user_id, guild_id, "earn", reward_money))
            asyncio.create_task(
                record_player_progress(
                    user_id,
                    guild_id,
                    action="contracts",
                    amount=1,
                    money=reward_money,
                    gems=reward_gems,
                )
            )

        embed = discord.Embed(
            title="Контракт закрыт",
            description=(
                f"**{item['name']}** выполнен.\n"
                f"Награда: **{format_money(reward_money)}** и **{reward_gems} гем.**\n"
                f"Баланс: **{format_money(user['balance'])}**"
            ),
            color=COLORS["success"],
        )
        if active_event is not None and multiplier != 1.0:
            embed.add_field(name="Событие", value=f"Бонус ивента **{active_event['name']}** уже учтён.", inline=False)
        return True, embed

    async def build_contracts_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Контракты", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        contracts_state = _ensure_contracts(user)
        items = list(contracts_state.get("items", []))
        tomorrow = datetime.now(KYIV_TZ).date() + timedelta(days=1)
        reset_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KYIV_TZ)
        reputation = get_reputation(user)
        max_rerolls = contract_rerolls_for_vip(int(user.get("vip_level", 0) or 0))
        used_rerolls = int(contracts_state.get("rerolls_used", 0) or 0)
        rerolls_left = max(0, max_rerolls - used_rerolls)
        self._contract_reroll_cache[(int(user_id), int(guild_id))] = (rerolls_left, max_rerolls)

        embed = discord.Embed(
            title="📋 Контракты дня",
            description=f"Новые заказы появятся {format_discord_deadline(reset_at)}.",
            color=COLORS["info"],
        )
        embed.add_field(
            name="Репутация и лимиты",
            value=(
                f"Репутация: **{reputation}** ({reputation_label(reputation)})\n"
                f"Слотов: **{len(items)}**\n"
                f"Обновления: **{rerolls_left}/{max_rerolls}**"
            ),
            inline=False,
        )

        for index, item in enumerate(items, start=1):
            progress = int(item.get("progress", 0) or 0)
            target = int(item.get("target", 0) or 0)
            status = "Забрано" if item.get("claimed") else "Готово" if progress >= target else "В процессе"
            embed.add_field(
                name=f"{index}. [{item.get('difficulty_badge', 'TASK')}] {item['name']}",
                value=(
                    f"{item['description']}\n"
                    f"Сложность: **{item.get('difficulty_name', 'Обычный')}**\n"
                    f"Прогресс: **{progress}/{target}**\n"
                    f"Награда: **{format_money(item['reward_money'])}** + **{item['reward_gems']} гем.**\n"
                    f"Статус: **{status}**"
                ),
                inline=False,
            )

        multiplier, active_event = self.get_reward_multiplier(guild_id, "contracts")
        if active_event is not None and multiplier != 1.0:
            embed.add_field(
                name="Событие",
                value=f"Сейчас действует **{active_event['name']}**. Награды контрактов усилены до **x{multiplier:.2f}**.",
                inline=False,
            )
        embed.set_footer(text="Выполняй контракты обычными командами бота и забирай награду кнопками ниже.")
        return embed

    def _market_offer_price(self, user: dict[str, Any], guild_id: int, offer: dict[str, Any]) -> tuple[int, float, float, dict[str, Any] | None]:
        base_price = int(offer.get("price", 0) or 0)
        rep_discount = black_market_discount_multiplier(get_reputation(user))
        event_multiplier, active_event = self.get_reward_multiplier(guild_id, "blackmarket")
        final_price = max(1, int(round(base_price * rep_discount * event_multiplier)))
        return final_price, rep_discount, event_multiplier, active_event

    async def get_black_market_offers(self, user_id: int, guild_id: int) -> tuple[list[dict[str, Any]], set[str]]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return [], set()
            state = _ensure_black_market_state(user, user_id)
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
            return list(state.get("offers", [])), set(state.get("purchased", []))

    async def buy_black_market_offer(self, user_id: int, guild_id: int, slot: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            state = _ensure_black_market_state(user)
            offers = list(state.get("offers", []))
            if slot >= len(offers):
                return False, "Такого лота нет."

            offer = offers[slot]
            purchased = set(state.get("purchased", []))
            if offer["code"] in purchased:
                return False, "Этот лот уже куплен сегодня."

            price, rep_discount, event_multiplier, active_event = self._market_offer_price(user, guild_id, offer)
            currency = str(offer["currency"]).lower()
            if currency == "gems":
                if int(user.get("gems", 0) or 0) < price:
                    return False, f"Не хватает гемов. Нужно: **{price}**."
                user["gems"] = int(user.get("gems", 0) or 0) - price
            else:
                if int(user.get("balance", 0) or 0) < price:
                    return False, f"Не хватает денег. Нужно: **{format_money(price)}**."
                user["balance"] = int(user.get("balance", 0) or 0) - price

            result_lines: list[str] = []
            grant = dict(offer.get("grant", {}))
            grant_type = grant.get("type")

            if grant_type == "bait":
                fishing = _fishing_state(user)
                bait_stock = fishing.setdefault("bait_stock", {})
                bait_key = str(grant["bait"])
                bait_stock[bait_key] = int(bait_stock.get(bait_key, 0) or 0) + int(grant["amount"])
                if not fishing.get("equipped_bait"):
                    fishing["equipped_bait"] = bait_key
                result_lines.append(f"Добавлено: **{grant['amount']}x {offer['name']}**")
            elif grant_type == "house_wallet":
                amount = int(grant["amount"])
                systems = _systems_state(user)
                house = systems.get("house")
                if not isinstance(house, dict):
                    house = {}
                    systems["house"] = house
                if house.get("owned_house_id"):
                    house["mining_wallet"] = int(house.get("mining_wallet", 0) or 0) + amount
                    result_lines.append(f"В подвал добавлено: **{format_money(amount)}**")
                else:
                    user["balance"] = int(user.get("balance", 0) or 0) + amount
                    result_lines.append(f"Дома ещё нет, поэтому на баланс зачислено: **{format_money(amount)}**")
            elif grant_type == "crypto":
                crypto = get_random_crypto()
                payout = int(round(float(crypto.get("value", 0) or 0)))
                user["balance"] = int(user.get("balance", 0) or 0) + payout
                result_lines.append(f"Получено: **{crypto['emoji']} {crypto['name']} {crypto['amount']}**, позиция сразу продана за **{format_money(payout)}**")
            elif grant_type == "money":
                amount = int(grant["amount"])
                user["balance"] = int(user.get("balance", 0) or 0) + amount
                result_lines.append(f"Получено: **{format_money(amount)}**")
            elif grant_type == "shield":
                hours = int(grant["hours"])
                user["shield_until"] = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
                result_lines.append(f"Щит активирован на **{hours} ч**")
            elif grant_type == "cosmetic_pack":
                if int(grant.get("gems", 0) or 0) > 0:
                    user["gems"] = int(user.get("gems", 0) or 0) + int(grant["gems"])
                    result_lines.append(f"Получено гемов: **+{int(grant['gems'])}**")
                if int(grant.get("reputation", 0) or 0) != 0:
                    new_reputation = change_reputation(user, int(grant["reputation"]))
                    result_lines.append(f"Репутация: **{new_reputation}**")
                if grant.get("title") and unlock_title(user, str(grant["title"])):
                    result_lines.append(f"Разблокирован титул: **{reward_text({'type': 'title', 'key': grant['title']})}**")
                if grant.get("theme") and unlock_theme(user, str(grant["theme"])):
                    result_lines.append(f"Разблокирована тема: **{reward_text({'type': 'theme', 'key': grant['theme']})}**")

            purchased.add(str(offer["code"]))
            state["purchased"] = sorted(purchased)
            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user.get("balance", 0),
                    "gems": user.get("gems", 0),
                    "shield_until": user.get("shield_until"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        embed = discord.Embed(
            title="Сделка завершена",
            description=(
                f"Куплено: **{offer['name']}**\n"
                f"Цена: **{format_money(price) if currency == 'money' else f'{price} гем.'}**\n"
                + "\n".join(result_lines)
            ),
            color=COLORS["success"],
        )
        if offer.get("legendary"):
            embed.add_field(name="Редкость", value="Легендарный лот чёрного рынка", inline=False)
        if rep_discount < 1.0:
            embed.add_field(name="Скидка за репутацию", value=f"Коэффициент цены: **x{rep_discount:.2f}**", inline=False)
        if active_event is not None and event_multiplier != 1.0:
            embed.add_field(name="Событие", value=f"Цены изменены ивентом **{active_event['name']}**.", inline=False)
        return True, embed

    async def build_black_market_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Чёрный рынок", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        state = _ensure_black_market_state(user)
        offers = list(state.get("offers", []))
        purchased = set(state.get("purchased", []))
        tomorrow = datetime.now(KYIV_TZ).date() + timedelta(days=1)
        reset_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=KYIV_TZ)
        reputation = get_reputation(user)
        rep_discount = black_market_discount_multiplier(reputation)
        embed = discord.Embed(
            title="🕶 Чёрный рынок",
            description=f"Редкие предложения на сегодня. Обновление: {format_discord_deadline(reset_at)}.",
            color=COLORS["warning"],
        )
        embed.add_field(
            name="Кошелёк",
            value=(
                f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Репутация",
            value=(
                f"Счёт: **{reputation}** ({reputation_label(reputation)})\n"
                f"Скидка: **x{rep_discount:.2f}**"
            ),
            inline=True,
        )

        legendary_present = any(bool(offer.get("legendary")) for offer in offers)
        embed.add_field(
            name="Легендарный слот",
            value="Сегодня легендарный товар доступен." if legendary_present else "Сегодня легендарный слот не открылся.",
            inline=False,
        )

        for index, offer in enumerate(offers, start=1):
            price, _, event_multiplier, active_event = self._market_offer_price(user, guild_id, offer)
            status = "Куплено" if offer["code"] in purchased else "Доступно"
            price_text = format_money(price) if offer["currency"] == "money" else f"{price} гем."
            title_prefix = "LEGENDARY " if offer.get("legendary") else ""
            extra_line = ""
            if active_event is not None and event_multiplier != 1.0:
                extra_line = f"\nСобытие: **{active_event['name']}**"
            embed.add_field(
                name=f"{index}. {title_prefix}{offer['name']}",
                value=(
                    f"{offer['description']}\n"
                    f"Цена: **{price_text}**\n"
                    f"Статус: **{status}**"
                    f"{extra_line}"
                ),
                inline=False,
            )
        embed.set_footer(text="Репутация влияет на скидки и шанс легендарного слота.")
        return embed

    async def buy_black_market_offer(self, user_id: int, guild_id: int, slot: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            state = _ensure_black_market_state(user, user_id)
            offers = list(state.get("offers", []))
            if slot >= len(offers):
                return False, "Такого слота на чёрном рынке нет."

            offer = offers[slot]
            purchased = set(state.get("purchased", []))
            if offer["code"] in purchased:
                return False, "Этот лот уже куплен в текущей ротации."

            price, rep_discount, event_multiplier, active_event = self._market_offer_price(user, guild_id, offer)
            currency = str(offer["currency"]).lower()
            if currency == "gems":
                if int(user.get("gems", 0) or 0) < price:
                    return False, f"Не хватает гемов. Нужно: **{price}**."
                user["gems"] = int(user.get("gems", 0) or 0) - price
            else:
                if int(user.get("balance", 0) or 0) < price:
                    return False, f"Не хватает денег. Нужно: **{format_money(price)}**."
                user["balance"] = int(user.get("balance", 0) or 0) - price

            grant = dict(offer.get("grant", {}))
            grant_type = str(grant.get("type") or "")
            if grant_type == "bait":
                bait_key = str(grant.get("bait") or "worms")
                inventory_item = add_general_item(
                    user,
                    item_type="bait_bundle",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji={"worms": "🪱", "shrimp": "🦐", "glow": "✨"}.get(bait_key, "🎣"),
                    description=f"{offer['description']} Активируй предмет через /inventory.",
                    payload={"bait": bait_key, "amount": int(grant.get("amount", 0) or 0)},
                    stackable=True,
                )
            elif grant_type == "house_wallet":
                inventory_item = add_general_item(
                    user,
                    item_type="house_wallet_cache",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji="🏚️",
                    description=f"{offer['description']} Активируй предмет через /inventory.",
                    payload={"amount": int(grant.get("amount", 0) or 0)},
                    stackable=True,
                )
            elif grant_type == "crypto":
                crypto = get_random_crypto()
                inventory_item = add_general_item(
                    user,
                    item_type="crypto_cache",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji=str(crypto.get("emoji") or "🪙"),
                    description=f"{offer['description']} Активируй предмет через /inventory.",
                    payload={
                        "amount": int(round(float(crypto.get("value", 0) or 0))),
                        "crypto_name": str(crypto.get("name") or "Crypto"),
                        "crypto_amount": str(crypto.get("amount") or "1"),
                    },
                    stackable=True,
                )
            elif grant_type == "money":
                inventory_item = add_general_item(
                    user,
                    item_type="cash_bundle",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji="💵",
                    description=f"{offer['description']} Активируй предмет через /inventory.",
                    payload={"amount": int(grant.get("amount", 0) or 0)},
                    stackable=True,
                )
            elif grant_type == "shield":
                inventory_item = add_general_item(
                    user,
                    item_type="shield_card",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji="🛡️",
                    description=f"{offer['description']} Активируй страховку через /inventory.",
                    payload={"hours": int(grant.get("hours", 24) or 24)},
                    stackable=True,
                )
            elif grant_type == "cosmetic_pack":
                inventory_item = add_general_item(
                    user,
                    item_type="cosmetic_pack",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji="🌀",
                    description=f"{offer['description']} Активируй предмет через /inventory.",
                    payload=grant,
                    stackable=False,
                )
            else:
                inventory_item = add_general_item(
                    user,
                    item_type="black_market_item",
                    code=str(offer["code"]),
                    name=str(offer["name"]),
                    emoji="🕶️",
                    description=f"{offer['description']} Активируй предмет через /inventory.",
                    payload=grant,
                    stackable=False,
                )

            purchased.add(str(offer["code"]))
            state["purchased"] = sorted(purchased)
            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user.get("balance", 0),
                    "gems": user.get("gems", 0),
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        embed = discord.Embed(
            title="Сделка чёрного рынка завершена",
            description=(
                f"Куплен лот **{offer['name']}** за **{format_money(price) if currency == 'money' else f'{price} гем.'}**.\n"
                f"Предмет отправлен в инвентарь под ID **#{inventory_item['id']}**.\n"
                "Используй `/inventory`, чтобы активировать его в удобный момент."
            ),
            color=COLORS["success"],
        )
        if offer.get("legendary"):
            embed.add_field(name="Лот", value="Легендарный слот чёрного рынка", inline=False)
        if rep_discount < 1.0:
            embed.add_field(name="Скидка за репутацию", value=f"Множитель цены: **x{rep_discount:.2f}**", inline=False)
        if active_event is not None and event_multiplier != 1.0:
            embed.add_field(name="Событие рынка", value=f"Цена была изменена событием **{active_event['name']}**.", inline=False)
        return True, embed

    async def build_black_market_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Чёрный рынок", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        state = _ensure_black_market_state(user, user_id)
        offers = list(state.get("offers", []))
        purchased = set(state.get("purchased", []))
        reset_at = _next_black_market_refresh()
        reputation = get_reputation(user)
        rep_discount = black_market_discount_multiplier(reputation)

        embed = discord.Embed(
            title="🕶️ Чёрный рынок",
            description=(
                "Персональные предложения на 12 часов.\n"
                f"Следующая ротация: {format_discord_deadline(reset_at)}."
            ),
            color=COLORS["warning"],
        )
        embed.add_field(
            name="Кошелёк",
            value=(
                f"Наличные: **{format_money(user.get('balance', 0))}**\n"
                f"Гемы: **{int(user.get('gems', 0) or 0):,}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Репутация",
            value=(
                f"Счёт: **{reputation}** ({reputation_label(reputation)})\n"
                f"Скидка: **x{rep_discount:.2f}**"
            ),
            inline=True,
        )
        embed.add_field(
            name="Особенность",
            value="У каждого игрока свой набор лотов. Все покупки сначала отправляются в `/inventory`.",
            inline=False,
        )

        for index, offer in enumerate(offers, start=1):
            price, _, event_multiplier, active_event = self._market_offer_price(user, guild_id, offer)
            status = "Куплено" if offer["code"] in purchased else "Доступно"
            price_text = format_money(price) if offer["currency"] == "money" else f"{price} гем."
            title_prefix = "ЛЕГЕНДАРНЫЙ " if offer.get("legendary") else ""
            extra_line = ""
            if active_event is not None and event_multiplier != 1.0:
                extra_line = f"\nСобытие: **{active_event['name']}**"
            embed.add_field(
                name=f"{index}. {title_prefix}{offer['name']}",
                value=(
                    f"{offer['description']}\n"
                    f"Цена: **{price_text}**\n"
                    "Куда уйдёт: **в инвентарь**\n"
                    f"Статус: **{status}**"
                    f"{extra_line}"
                ),
                inline=False,
            )

        embed.set_footer(text="Рынок обновляется раз в 12 часов. Покупай здесь, используй предметы позже через /inventory.")
        return embed

    async def _announce_event(self, guild: discord.Guild, event: dict[str, Any]):
        channel = guild.get_channel(ALLOWED_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return
        mention = f"<@&{EVENT_PING_ROLE_ID}>"
        description = (
            f"{event['description']}\n\n"
            f"Закончится: {format_discord_deadline(event['expires_at'])}."
        )
        embed = discord.Embed(
            title=f"📣 Рыночное событие: {event['name']}",
            description=description,
            color=event["color"],
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Следи за /contracts, /blackmarket, /fish, /house и /mybusinesses.")

        existing = await self._find_matching_event_message(channel, event)
        if existing is not None:
            await self._pin_message(existing)
            await self._cleanup_old_event_pins(channel, keep_message_id=existing.id)
            return

        try:
            message = await channel.send(mention, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True))
        except Exception:
            return

        await self._pin_message(message)
        await self._cleanup_old_event_pins(channel, keep_message_id=message.id)

    @tasks.loop(minutes=20)
    async def market_events_loop(self):
        now = datetime.now(timezone.utc)

        expired_guilds = [guild_id for guild_id, event in self.active_events.items() if now >= event["expires_at"]]
        for guild_id in expired_guilds:
            event = self.active_events.pop(guild_id, None)
            if event is None:
                continue
            cooldown_until = event["expires_at"] + timedelta(hours=MARKET_EVENT_COOLDOWN_HOURS)
            existing = self.next_event_after.get(guild_id)
            if existing is None or cooldown_until > existing:
                self.next_event_after[guild_id] = cooldown_until
            await self._persist_market_state(guild_id)

        for guild in self.bot.guilds:
            if guild.id in self.active_events:
                continue
            next_event_after = self.next_event_after.get(guild.id)
            if next_event_after is not None and now < next_event_after:
                continue

            scheduled_event = self._pick_scheduled_event(guild.id, now)
            if scheduled_event is not None:
                self.active_events[guild.id] = scheduled_event
                self.next_event_after[guild.id] = scheduled_event["expires_at"] + timedelta(hours=MARKET_EVENT_COOLDOWN_HOURS)
                await self._persist_market_state(guild.id)
                await self._announce_event(guild, scheduled_event)
                continue

            if random.random() > MARKET_EVENT_SPAWN_CHANCE:
                continue

            event_key = random.choice(list(MARKET_EVENTS.keys()))
            template = MARKET_EVENTS[event_key]
            event = self._build_event_payload(event_key, template, now)
            self.active_events[guild.id] = event
            self.next_event_after[guild.id] = event["expires_at"] + timedelta(hours=MARKET_EVENT_COOLDOWN_HOURS)
            await self._persist_market_state(guild.id)
            await self._announce_event(guild, event)

    @market_events_loop.before_loop
    async def before_market_events_loop(self):
        await self.bot.wait_until_ready()
        await self._restore_market_states()

    @app_commands.command(name="contracts", description="Посмотреть ежедневные контракты")
    async def contracts(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return
        view = ContractsViewV2(self, interaction.user.id, interaction.guild_id)
        view._sync_buttons(await self.get_contracts(interaction.user.id, interaction.guild_id))
        embed = await self.build_contracts_embed(interaction.user.id, interaction.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="blackmarket", description="Открыть чёрный рынок")
    async def blackmarket(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return

        if not await safe_defer(interaction):
            return
        offers, purchased = await self.get_black_market_offers(interaction.user.id, interaction.guild_id)
        view = BlackMarketView(self, interaction.user.id, interaction.guild_id)
        view._sync_buttons(offers, purchased)
        embed = await self.build_black_market_embed(interaction.user.id, interaction.guild_id)
        await interaction.edit_original_response(embed=embed, view=view)
        view.message = await interaction.original_response()


async def setup(bot):
    await bot.add_cog(SystemsCog(bot))
