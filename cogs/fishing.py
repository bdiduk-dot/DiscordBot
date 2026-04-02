import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from cogs.fishing_world import (
    CHISINAU_TZ,
    FISHING_BAITS as WORLD_FISHING_BAITS,
    FISHING_TACKLES as WORLD_FISHING_TACKLES,
    FISHING_ZONES as WORLD_FISHING_ZONES,
    current_event_window,
    describe_world_lines,
    get_world_state,
    next_event_window,
    roll_catch,
)
from cogs.cases import open_case_from_inventory
from config import ALLOWED_CHANNEL_ID, COLORS, FISH_RARITIES, FISHING_RODS, get_vip_level
from database import db, get_user_lock
from inventory_system import (
    add_fish_item,
    decrement_general_item,
    ensure_inventory_state,
    find_general_item,
    get_fish_items,
    get_general_items,
    sell_fish_by_id,
    sell_fish_items,
    toggle_fish_lock,
)
from progression import change_reputation, reward_text, unlock_theme, unlock_title
from utils import (
    check_channel,
    check_quest_progress,
    format_discord_deadline,
    get_random_crypto,
    record_player_progress,
    safe_defer,
    safe_edit_original_response,
    send_wrong_channel_message,
)

FISHING_TACKLES = WORLD_FISHING_TACKLES
FISHING_BAITS = WORLD_FISHING_BAITS
FISHING_ZONES = WORLD_FISHING_ZONES

FISHING_ROD_DESCRIPTIONS = {
    "none": "Простой крючок без бонусов, но рыбачить можно сразу.",
    "wooden": "Базовая удочка для уверенного старта и чуть лучшей удачи.",
    "fiberglass": "Надёжная удочка с хорошим бустом на редкую рыбу.",
    "carbon": "Сильная удочка для серьёзной рыбалки и дорогого улова.",
    "diamond": "Топовая удочка с лучшим шансом на редкий и легендарный улов.",
}

ROD_DISPLAY_NAMES = {
    "none": "Обычный крючок",
    "wooden": "Деревянная удочка",
    "fiberglass": "Стеклопластиковая удочка",
    "carbon": "Углепластиковая удочка",
    "diamond": "Алмазная удочка",
}

TACKLE_DISPLAY_NAMES = {
    "starter": "Базовая снасть",
    "spinner": "Блесна охотника",
    "titan_line": "Титановая леска",
    "abyss_reel": "Катушка Бездны",
}

BAIT_DISPLAY_NAMES = {
    "worms": "Черви",
    "shrimp": "Креветка",
    "glow": "Светящаяся приманка",
}

ZONE_DISPLAY_NAMES = {
    "river_bank": "Речной берег",
    "reed_swamp": "Тростниковая топь",
    "moon_lake": "Лунное озеро",
    "storm_coast": "Штормовой берег",
    "crystal_cove": "Кристальная бухта",
    "abyss_trench": "Бездна Левиафана",
}

TIME_PHASE_DISPLAY_NAMES = {
    "morning": "Утро",
    "day": "День",
    "evening": "Вечер",
    "night": "Ночь",
}

WEATHER_DISPLAY_NAMES = {
    "clear": "Ясно",
    "rain": "Дождь",
    "fog": "Туман",
    "storm": "Шторм",
    "moon_tide": "Лунный прилив",
}

EVENT_DISPLAY_NAMES = {
    "mist_bloom": "Туманный всплеск",
    "sun_flash": "Солнечная вспышка",
    "ember_tide": "Угольный прилив",
    "moon_hunt": "Лунная охота",
    "crystal_echo": "Эхо кристалла",
    "deep_alarm": "Тревога бездны",
}

RARITY_DISPLAY_NAMES = {
    "common": "Обычная",
    "uncommon": "Необычная",
    "rare": "Редкая",
    "epic": "Эпическая",
    "legendary": "Легендарная",
}

SPECIES_DISPLAY_NAMES = {
    "roach": "Плотва",
    "perch": "Окунь",
    "gudgeon": "Пескарь",
    "bleak": "Уклейка",
    "tench": "Линь",
    "mud_carp": "Топяной карась",
    "silver_carp": "Серебряный карп",
    "pike": "Щука",
    "bream": "Лещ",
    "eel": "Угорь",
    "amber_koi": "Янтарный кои",
    "mackerel": "Королевская скумбрия",
    "reef_snapper": "Рифовый луциан",
    "crystal_herring": "Кристальная сельдь",
    "river_zander": "Судак",
    "bog_catfish": "Болотный сом",
    "moon_trout": "Лунная форель",
    "glass_eel": "Стеклянный угорь",
    "storm_barracuda": "Штормовая барракуда",
    "prism_tuna": "Призматический тунец",
    "abyss_ling": "Глубинный налим",
    "star_ray": "Звёздный скат",
    "night_som": "Сом-полуночник",
    "tempest_marlin": "Штормовой марлин",
    "reef_hammer": "Рифовая акула",
    "crystal_manta": "Кристальная манта",
    "void_sword": "Клинок бездны",
    "ghost_whale": "Теневой кит",
    "moon_sturgeon": "Призрачный осётр",
    "prism_whale": "Призматический кит",
    "storm_leviathan": "Штормовой левиафан",
    "sun_sardine": "Солнечная сардина",
    "mist_koi": "Туманный кои",
    "ember_trout": "Искристая форель",
    "lunar_moray": "Лунная мурена",
    "crystal_seer": "Прозрачный оракул",
    "void_ray": "Луч бездны",
    "moon_queen": "Королева озера",
    "tempest_emperor": "Император шторма",
    "crystal_seraph": "Серафим бухты",
    "abyss_tyrant": "Тиран бездны",
}

SHOP_PAGE_SIZE = 3
INVENTORY_FISH_PAGE_SIZE = 6
INVENTORY_GENERAL_PAGE_SIZE = 5
WORLD_EVENT_PIN_FOOTER = "Рыболовное ивент-окно"
BAIT_SHOP_ROTATION_HOURS = 2
BAIT_SHOP_OFFER_COUNT = 6
BAIT_SHOP_ALWAYS_AVAILABLE = ("worms",)


def format_money(value: int | float) -> str:
    return f"${int(value):,}"


def _default_bait_stock() -> dict[str, int]:
    return {key: 0 for key in FISHING_BAITS}


def _normalize_bait_stock(stock: Any) -> dict[str, int]:
    normalized = _default_bait_stock()
    if not isinstance(stock, dict):
        return normalized
    for key, value in stock.items():
        if key not in FISHING_BAITS:
            continue
        try:
            normalized[key] = max(0, int(value or 0))
        except (TypeError, ValueError):
            normalized[key] = 0
    return normalized


def _bait_shop_rotation_start(now: datetime | None = None) -> datetime:
    local_now = now or datetime.now(timezone.utc)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=timezone.utc)
    local_now = local_now.astimezone(CHISINAU_TZ)
    start_hour = local_now.hour - (local_now.hour % BAIT_SHOP_ROTATION_HOURS)
    return local_now.replace(hour=start_hour, minute=0, second=0, microsecond=0)


def _bait_shop_rotation_key(now: datetime | None = None) -> str:
    return _bait_shop_rotation_start(now).strftime("%Y%m%d%H")


def _next_bait_shop_refresh(now: datetime | None = None) -> datetime:
    return (_bait_shop_rotation_start(now) + timedelta(hours=BAIT_SHOP_ROTATION_HOURS)).astimezone(timezone.utc)


def _bait_shop_offers(now: datetime | None = None) -> list[tuple[str, dict[str, Any]]]:
    rotation_start = _bait_shop_rotation_start(now)
    seed = int(rotation_start.strftime("%Y%m%d%H"))
    remaining_keys = [key for key in FISHING_BAITS if key not in BAIT_SHOP_ALWAYS_AVAILABLE]
    rng = random.Random(seed * 97 + 13)
    scored: list[tuple[float, int, str]] = []
    for index, key in enumerate(remaining_keys):
        weight = float(FISHING_BAITS[key].get("rotation_weight", 1.0))
        scored.append((rng.random() * weight, index, key))
    rotating_keys = [
        key
        for _, _, key in sorted(scored, reverse=True)[: max(0, BAIT_SHOP_OFFER_COUNT - len(BAIT_SHOP_ALWAYS_AVAILABLE))]
    ]
    selected = [*BAIT_SHOP_ALWAYS_AVAILABLE, *rotating_keys]
    offers: list[tuple[str, dict[str, Any]]] = []
    for key in selected:
        bait = dict(FISHING_BAITS[key])
        bait["shop_limit"] = int(bait.get("shop_limit", 3) or 3)
        offers.append((key, bait))
    return offers


def _bait_shop_offer_map(now: datetime | None = None) -> dict[str, dict[str, Any]]:
    return {key: item for key, item in _bait_shop_offers(now)}


def _bait_shop_state(fishing: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    rotation = _bait_shop_rotation_key(now)
    shop_state = fishing.get("bait_shop_state")
    if not isinstance(shop_state, dict):
        shop_state = {}
    purchases_raw = shop_state.get("purchases")
    purchases: dict[str, int] = {}
    if isinstance(purchases_raw, dict):
        for key, value in purchases_raw.items():
            if key not in FISHING_BAITS:
                continue
            try:
                purchases[key] = max(0, int(value or 0))
            except (TypeError, ValueError):
                purchases[key] = 0
    if shop_state.get("rotation") != rotation:
        purchases = {}
    normalized = {"rotation": rotation, "purchases": purchases}
    fishing["bait_shop_state"] = normalized
    return normalized


def _bait_shop_remaining_limit(fishing: dict[str, Any], bait_key: str, now: datetime | None = None) -> int:
    offer = _bait_shop_offer_map(now).get(bait_key)
    if offer is None:
        return 0
    purchases = _bait_shop_state(fishing, now).get("purchases", {})
    return max(0, int(offer.get("shop_limit", 0) or 0) - int(purchases.get(bait_key, 0) or 0))


def _truncate_button_label(text: str, limit: int = 80) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _inventory_state(user: dict[str, Any]) -> dict[str, Any]:
    return ensure_inventory_state(user)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _system_state(user: dict[str, Any]) -> dict[str, Any]:
    game_stats = user.get("game_stats")
    if not isinstance(game_stats, dict):
        game_stats = {}
        user["game_stats"] = game_stats
    systems = game_stats.get("_systems")
    if not isinstance(systems, dict):
        systems = {}
        game_stats["_systems"] = systems
    return systems


def _market_event_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _system_state(user)
    market_events = systems.get("market_events")
    if not isinstance(market_events, dict):
        market_events = {}
        systems["market_events"] = market_events
    return market_events


def _crypto_boom_bonus_id(event: dict[str, Any] | None) -> str | None:
    if not event or event.get("key") != "crypto_boom":
        return None
    expires_at = event.get("expires_at")
    if not isinstance(expires_at, datetime):
        return None
    return f"crypto_boom:{int(expires_at.timestamp())}"


def _fishing_state(user: dict[str, Any]) -> dict[str, Any]:
    systems = _system_state(user)
    fishing = systems.get("fishing")
    if not isinstance(fishing, dict):
        fishing = {}
    current_rod = str(user.get("fishing_rod", "none") or "none")
    owned_rods = fishing.get("owned_rods")
    if not isinstance(owned_rods, list):
        owned_rods = []
    if current_rod != "none" and current_rod not in owned_rods:
        owned_rods.append(current_rod)
    fishing["owned_rods"] = list(dict.fromkeys(owned_rods))
    fishing.setdefault("owned_tackles", ["starter"])
    fishing.setdefault("equipped_tackle", "starter")
    fishing["bait_stock"] = _normalize_bait_stock(fishing.get("bait_stock"))
    fishing.setdefault("equipped_bait", None)
    fishing.setdefault("unlocked_zones", ["river_bank"])
    fishing.setdefault("selected_zone", "river_bank")
    fishing.setdefault("total_catches", 0)
    fishing.setdefault("last_catch", None)
    _bait_shop_state(fishing)
    systems["fishing"] = fishing
    return fishing


def _rod_description(rod_key: str) -> str:
    return FISHING_ROD_DESCRIPTIONS.get(rod_key, "Надёжная удочка для уверенной рыбалки.")


def _display_rod_name(rod_key: str) -> str:
    return ROD_DISPLAY_NAMES.get(rod_key, FISHING_RODS.get(rod_key, {}).get("name", "Удочка"))


def _display_tackle_name(tackle_key: str) -> str:
    return TACKLE_DISPLAY_NAMES.get(tackle_key, FISHING_TACKLES.get(tackle_key, {}).get("name", "Снасть"))


def _display_bait_name(bait_key: str | None) -> str:
    if bait_key in (None, "none"):
        return "Без наживки"
    return BAIT_DISPLAY_NAMES.get(str(bait_key), FISHING_BAITS.get(str(bait_key), {}).get("name", "Наживка"))


def _display_zone_name(zone_key: str) -> str:
    return ZONE_DISPLAY_NAMES.get(zone_key, FISHING_ZONES.get(zone_key, {}).get("name", "Спот"))


def _display_time_phase_name(phase_key: str | None) -> str:
    return TIME_PHASE_DISPLAY_NAMES.get(str(phase_key), "Неизвестно")


def _display_weather_name(weather_key: str | None) -> str:
    return WEATHER_DISPLAY_NAMES.get(str(weather_key), "Неизвестно")


def _display_event_name(event_key: str | None) -> str:
    if not event_key:
        return "Нет ивента"
    return EVENT_DISPLAY_NAMES.get(str(event_key), str(event_key))


def _display_species_name(species_id: str | None, fallback: str | None = None) -> str:
    if species_id in SPECIES_DISPLAY_NAMES:
        return SPECIES_DISPLAY_NAMES[str(species_id)]
    return fallback or "Неизвестная рыба"


def _display_rarity_name(rarity_key: str | None) -> str:
    return RARITY_DISPLAY_NAMES.get(str(rarity_key), str(rarity_key or "Обычная"))


def _build_world_lines(world_state: dict[str, Any]) -> list[str]:
    lines = [
        f"Время суток: **{_display_time_phase_name(world_state.get('time_phase_key'))}**",
        f"Погода: **{_display_weather_name(world_state.get('weather', {}).get('key'))}**",
        f"Хот-спот: **{_display_zone_name(world_state.get('hotspot_key', 'river_bank'))}**",
    ]
    active_event = world_state.get("active_event")
    if active_event is None:
        lines.append("Ивент: **сейчас нет**")
    else:
        lines.append(f"Ивент: **{_display_event_name(active_event.get('key'))}**")
    return lines


def _fish_chances(rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, zone: dict[str, Any], event_name: str | None) -> dict[str, float]:
    chances_mult = {"legendary": rod_bonus, "epic": min(rod_bonus * 0.8, 2.2), "rare": min(rod_bonus * 0.5, 1.7), "uncommon": 1.0, "common": 1.0}
    chances: dict[str, float] = {}
    for rarity_key, rarity_data in FISH_RARITIES.items():
        multiplier = chances_mult.get(rarity_key, 1.0)
        multiplier *= float(tackle.get("chance_bonus", {}).get(rarity_key, 1.0))
        multiplier *= float(zone.get("chance_bonus", {}).get(rarity_key, 1.0))
        if bait is not None:
            multiplier *= float(bait.get("chance_bonus", {}).get(rarity_key, 1.0))
        if event_name == "fish_day":
            multiplier *= {"rare": 1.12, "epic": 1.22, "legendary": 1.35}.get(rarity_key, 1.0)
        chances[rarity_key] = float(rarity_data["chance"]) * multiplier
    return chances


def _roll_fish_drop(rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, zone: dict[str, Any], event_name: str | None) -> dict[str, Any]:
    chances = _fish_chances(rod_bonus, tackle, bait, zone, event_name)
    total_chance = sum(chances.values())
    roll = random.uniform(0, total_chance)
    cumulative = 0.0
    rarity_key = "common"
    for current_key, chance in chances.items():
        cumulative += chance
        if roll <= cumulative:
            rarity_key = current_key
            break
    rarity = FISH_RARITIES[rarity_key]
    fish_pool = list(rarity["fish"])
    fish_pool.extend(zone.get("fish_pool", {}).get(rarity_key, []))
    if rarity_key == "legendary":
        fish_pool.extend(zone.get("legendary_pool", []))
    value_bonus = float(tackle.get("value_bonus", 1.0)) * float(zone.get("value_bonus", 1.0))
    if bait is not None:
        value_bonus *= float(bait.get("value_bonus", 1.0))
    if event_name == "fish_day":
        value_bonus *= 1.30
    return {
        "name": random.choice(fish_pool),
        "rarity": rarity_key,
        "rarity_name": rarity["name"],
        "emoji": rarity["emoji"],
        "color": rarity["color"],
        "price": int(random.randint(int(rarity["price_min"]), int(rarity["price_max"])) * value_bonus),
    }


class FishShopView(discord.ui.View):
    def __init__(self, cog: "FishingCog", user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.active_tab = "rods"
        self.page = 0
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self._sync_buttons({})

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твой магазин рыбалки.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    def _items_for_tab(self) -> list[tuple[str, dict[str, Any]]]:
        if self.active_tab == "rods":
            return [(key, value) for key, value in FISHING_RODS.items() if key != "none"]
        if self.active_tab == "tackles":
            return [(key, value) for key, value in FISHING_TACKLES.items() if key != "starter"]
        if self.active_tab == "bait":
            return _bait_shop_offers()
        return [(key, value) for key, value in FISHING_ZONES.items() if key != "river_bank"]

    def _visible_items(self) -> list[tuple[str, dict[str, Any]]]:
        items = self._items_for_tab()
        start = self.page * SHOP_PAGE_SIZE
        return items[start:start + SHOP_PAGE_SIZE]

    def _max_page(self) -> int:
        items = self._items_for_tab()
        if not items:
            return 0
        return max(0, (len(items) - 1) // SHOP_PAGE_SIZE)

    def _sync_buttons(self, state: dict[str, Any]):
        self.rods_btn.style = discord.ButtonStyle.primary if self.active_tab == "rods" else discord.ButtonStyle.secondary
        self.tackles_btn.style = discord.ButtonStyle.primary if self.active_tab == "tackles" else discord.ButtonStyle.secondary
        self.bait_btn.style = discord.ButtonStyle.primary if self.active_tab == "bait" else discord.ButtonStyle.secondary
        self.zones_btn.style = discord.ButtonStyle.primary if self.active_tab == "zones" else discord.ButtonStyle.secondary
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self._max_page()
        visible_items = self._visible_items()
        buttons = [self.item_1, self.item_2, self.item_3]
        owned_tackles = set(state.get("owned_tackles", []))
        bait_stock = state.get("bait_stock", {})
        unlocked_zones = set(state.get("unlocked_zones", []))
        owned_rods = set(state.get("owned_rods", []))
        for index, button in enumerate(buttons):
            if index >= len(visible_items):
                button.disabled = True
                button.label = "Нет товара"
                button.style = discord.ButtonStyle.secondary
                continue
            item_key, item = visible_items[index]
            if self.active_tab == "rods":
                equipped = item_key == state.get("fishing_rod")
                display_number = self.page * SHOP_PAGE_SIZE + index + 1
                if equipped:
                    button.label = f"Экип. {item['name']}"
                    button.disabled = True
                    button.style = discord.ButtonStyle.secondary
                elif item_key in owned_rods:
                    button.label = f"Надеть"
                    button.disabled = False
                    button.style = discord.ButtonStyle.primary
                else:
                    button.label = f"Купить удочку {display_number}"
                    button.disabled = False
                    button.style = discord.ButtonStyle.success
            elif self.active_tab == "tackles":
                equipped = item_key == state.get("equipped_tackle")
                owned = item_key in owned_tackles
                button.label = f"Экип. {item['name']}" if equipped else f"{'Надеть' if owned else 'Купить'} {item['name']}"
                button.disabled = False
                button.style = discord.ButtonStyle.primary if owned else discord.ButtonStyle.success
            elif self.active_tab == "bait":
                count = int(bait_stock.get(item_key, 0) or 0)
                remaining = _bait_shop_remaining_limit(state, item_key)
                button.label = _truncate_button_label(f"{item['name']} • {remaining}/{item['shop_limit']} пак.")
                button.disabled = remaining <= 0
                button.style = discord.ButtonStyle.success if remaining > 0 else discord.ButtonStyle.secondary
            else:
                equipped = item_key == state.get("selected_zone")
                owned = item_key in unlocked_zones
                button.label = f"Экип. {item['name']}" if equipped else f"{'Надеть' if owned else 'Открыть'} {item['name']}"
                button.disabled = False
                button.style = discord.ButtonStyle.primary if owned else discord.ButtonStyle.success

    async def _refresh(self, interaction: discord.Interaction):
        state = await self.cog.get_fishing_profile(self.user_id, self.guild_id)
        self._sync_buttons(state)
        embed = await self.cog.build_fishshop_embed(self.user_id, self.guild_id, self.active_tab, self.page)
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)

    async def _switch_tab(self, interaction: discord.Interaction, tab: str):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            if self.active_tab != tab:
                self.page = 0
            self.active_tab = tab
            await self._refresh(interaction)

    async def _buy_slot(self, interaction: discord.Interaction, slot: int):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            visible_items = self._visible_items()
            if slot >= len(visible_items):
                await interaction.followup.send("На этой кнопке нет товара.", ephemeral=True)
                return
            item_key, _ = visible_items[slot]
            _, payload = await self.cog.handle_fishshop_action_v2(self.user_id, self.guild_id, self.active_tab, item_key)
            await self._refresh(interaction)
            if isinstance(payload, discord.Embed):
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.followup.send(str(payload), ephemeral=True)

    @discord.ui.button(label="Удочки", style=discord.ButtonStyle.primary, row=0)
    async def rods_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_tab(interaction, "rods")

    @discord.ui.button(label="Снасти", style=discord.ButtonStyle.secondary, row=0)
    async def tackles_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_tab(interaction, "tackles")

    @discord.ui.button(label="Наживки", style=discord.ButtonStyle.secondary, row=0)
    async def bait_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_tab(interaction, "bait")

    @discord.ui.button(label="Споты", style=discord.ButtonStyle.secondary, row=0)
    async def zones_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._switch_tab(interaction, "zones")

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.secondary, row=1)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.page = max(0, self.page - 1)
            await self._refresh(interaction)

    @discord.ui.button(label="Товар 1", style=discord.ButtonStyle.success, row=1)
    async def item_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 0)

    @discord.ui.button(label="Товар 2", style=discord.ButtonStyle.success, row=1)
    async def item_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 1)

    @discord.ui.button(label="Товар 3", style=discord.ButtonStyle.success, row=1)
    async def item_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._buy_slot(interaction, 2)

    @discord.ui.button(label="Дальше", style=discord.ButtonStyle.secondary, row=1)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            self.page = min(self._max_page(), self.page + 1)
            await self._refresh(interaction)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=2)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh(interaction)


class EnhancedFishShopView(FishShopView):
    def _sync_buttons(self, state: dict[str, Any]):
        self.rods_btn.style = discord.ButtonStyle.primary if self.active_tab == "rods" else discord.ButtonStyle.secondary
        self.tackles_btn.style = discord.ButtonStyle.primary if self.active_tab == "tackles" else discord.ButtonStyle.secondary
        self.bait_btn.style = discord.ButtonStyle.primary if self.active_tab == "bait" else discord.ButtonStyle.secondary
        self.zones_btn.style = discord.ButtonStyle.primary if self.active_tab == "zones" else discord.ButtonStyle.secondary
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self._max_page()
        visible_items = self._visible_items()
        buttons = [self.item_1, self.item_2, self.item_3]
        owned_rods = set(state.get("owned_rods", []))
        owned_tackles = set(state.get("owned_tackles", []))
        bait_stock = state.get("bait_stock", {})
        unlocked_zones = set(state.get("unlocked_zones", []))

        owned_rods = set(state.get("owned_rods", []))
        for index, button in enumerate(buttons):
            if index >= len(visible_items):
                button.disabled = True
                button.label = "Нет товара"
                button.style = discord.ButtonStyle.secondary
                continue

            item_key, item = visible_items[index]
            if self.active_tab == "rods":
                equipped = item_key == state.get("fishing_rod")
                owned = item_key in owned_rods
                display_number = self.page * SHOP_PAGE_SIZE + index + 1
                if equipped:
                    button.label = f"Экип. {item['name']}"
                    button.style = discord.ButtonStyle.primary
                elif owned:
                    button.label = "Надеть"
                    button.style = discord.ButtonStyle.primary
                else:
                    button.label = f"Купить удочку {display_number}"
                    button.style = discord.ButtonStyle.success
            elif self.active_tab == "tackles":
                equipped = item_key == state.get("equipped_tackle")
                owned = item_key in owned_tackles
                button.label = f"Экип. {item['name']}" if equipped else f"{'Надеть' if owned else 'Купить'} {item['name']}"
                button.style = discord.ButtonStyle.primary if owned else discord.ButtonStyle.success
            elif self.active_tab == "bait":
                count = int(bait_stock.get(item_key, 0) or 0)
                remaining = _bait_shop_remaining_limit(state, item_key)
                button.label = _truncate_button_label(f"{item['name']} • {remaining}/{item['shop_limit']} пак.")
                button.style = discord.ButtonStyle.success if remaining > 0 else discord.ButtonStyle.secondary
            else:
                equipped = item_key == state.get("selected_zone")
                owned = item_key in unlocked_zones
                button.label = f"Экип. {item['name']}" if equipped else f"{'Выбрать' if owned else 'Открыть'} {item['name']}"
                button.style = discord.ButtonStyle.primary if owned else discord.ButtonStyle.success
            if self.active_tab != "bait":
                button.disabled = False
            else:
                button.disabled = _bait_shop_remaining_limit(state, item_key) <= 0

    async def _refresh(self, interaction: discord.Interaction):
        state = await self.cog.get_fishing_profile(self.user_id, self.guild_id)
        self._sync_buttons(state)
        embed = await self.cog.build_fishshop_embed_v2(self.user_id, self.guild_id, self.active_tab, self.page)
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)


class FishingCastView(discord.ui.View):
    def __init__(self, cog: "FishingCog", user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это меню рыбалки открыто не тобой.", ephemeral=True)
            return False
        return True

    async def _remember_message(self, interaction: discord.Interaction):
        try:
            self.message = await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _refresh(self, interaction: discord.Interaction):
        embed = await self.cog.build_fishing_menu_embed(self.user_id, self.guild_id)
        state = await self.cog.get_fishing_profile(self.user_id, self.guild_id)
        current_zone = str(state.get("selected_zone", "river_bank") or "river_bank")
        self.zone_select.options = [
            discord.SelectOption(label=FISHING_ZONES[key]["name"][:100], value=key, default=key == current_zone)
            for key in state.get("unlocked_zones", ["river_bank"])
        ]
        if not await safe_edit_original_response(interaction, embed=embed, view=self):
            return
        await self._remember_message(interaction)

    @discord.ui.select(placeholder="Выбери спот перед рыбалкой", row=0, options=[discord.SelectOption(label="Речной берег", value="river_bank", default=True)])
    async def zone_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self.cog.select_fishing_zone(self.user_id, self.guild_id, select.values[0])
            await self._refresh(interaction)

    @discord.ui.button(label="Закинуть удочку", style=discord.ButtonStyle.success, row=1)
    async def cast(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            fishing_state = await self.cog.get_fishing_profile(self.user_id, self.guild_id)
            success, payload = await self.cog.perform_fishing_cast(self.user_id, self.guild_id)
            if not success:
                if isinstance(payload, discord.Embed):
                    await interaction.followup.send(embed=payload, ephemeral=True)
                else:
                    await interaction.followup.send(str(payload), ephemeral=True)
                await self._refresh(interaction)
                return
            await self.cog._play_cast_animation(interaction, fishing_state)
            await safe_edit_original_response(interaction, embed=payload, view=None)

    @discord.ui.button(label="Обновить", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._view_lock:
            if not await safe_defer(interaction):
                return
            await self._refresh(interaction)


class FishingCog(commands.Cog, name="Fishing"):
    def __init__(self, bot):
        self.bot = bot
        self.FISHING_RODS = FISHING_RODS
        self.FISHING_TACKLES = FISHING_TACKLES
        self.FISHING_BAITS = FISHING_BAITS
        self.FISHING_ZONES = FISHING_ZONES
        self._active_world_event_by_guild: dict[int, str | None] = {}
        self._latest_world_event_payload: dict[int, dict[str, Any]] = {}
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            if not self.fishing_event_window_loop.is_running():
                self.fishing_event_window_loop.start()

    def cog_unload(self):
        self.fishing_event_window_loop.cancel()

    async def _pin_message(self, message: discord.Message):
        try:
            await message.pin(reason="Pinned fishing world event window")
        except Exception:
            return

    async def _cleanup_old_world_event_pins(self, channel: discord.TextChannel, keep_message_id: int):
        try:
            pinned_messages = await channel.pins()
        except Exception:
            return

        for message in pinned_messages:
            if message.id == keep_message_id or message.author.id != self.bot.user.id:
                continue
            embed = message.embeds[0] if message.embeds else None
            footer_text = embed.footer.text if embed and embed.footer else ""
            if footer_text.startswith(WORLD_EVENT_PIN_FOOTER):
                try:
                    await message.unpin(reason="Refreshing fishing world event pin")
                except Exception:
                    pass

    async def _find_matching_world_event_message(self, channel: discord.TextChannel, event_key: str, ended: bool) -> discord.Message | None:
        target_footer = f"{WORLD_EVENT_PIN_FOOTER}:{event_key}:{'ended' if ended else 'active'}"
        async for message in channel.history(limit=40):
            if message.author.id != self.bot.user.id or not message.embeds:
                continue
            embed = message.embeds[0]
            footer_text = embed.footer.text if embed.footer else ""
            if footer_text == target_footer:
                return message
        return None

    async def _announce_world_event_window(self, guild: discord.Guild, event: dict[str, Any], *, ended: bool):
        channel = guild.get_channel(ALLOWED_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            return

        next_window = next_event_window()
        if ended:
            title = f"🌘 Ивент-окно завершено: {event['name']}"
            description = f"{event['description']}\n\nОкно рыбалки закончилось."
            color = COLORS["warning"]
        else:
            title = f"🌊 Ивент-окно рыбалки: {event['name']}"
            description = (
                f"{event['description']}\n\n"
                f"Активно до: {format_discord_deadline(event['end_at'].astimezone(timezone.utc))}."
            )
            color = COLORS["info"]

        if next_window is not None and ended:
            start_at = next_window.get("start_at")
            if isinstance(start_at, datetime):
                description += f"\nСледующее окно: {next_window.get('name', 'неизвестно')} {format_discord_deadline(start_at.astimezone(timezone.utc))}."

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"{WORLD_EVENT_PIN_FOOTER}:{event['key']}:{'ended' if ended else 'active'}")

        existing = await self._find_matching_world_event_message(channel, str(event["key"]), ended)
        if existing is not None:
            await self._pin_message(existing)
            await self._cleanup_old_world_event_pins(channel, keep_message_id=existing.id)
            return

        try:
            message = await channel.send(embed=embed)
        except Exception:
            return

        await self._pin_message(message)
        await self._cleanup_old_world_event_pins(channel, keep_message_id=message.id)

    @tasks.loop(minutes=1)
    async def fishing_event_window_loop(self):
        active_event = current_event_window()
        active_key = str(active_event["key"]) if active_event else None

        for guild in self.bot.guilds:
            previous_key = self._active_world_event_by_guild.get(guild.id)
            if previous_key == active_key:
                continue

            if previous_key is not None:
                previous_event = self._latest_world_event_payload.get(guild.id)
                if previous_event is not None:
                    await self._announce_world_event_window(guild, previous_event, ended=True)

            if active_event is not None:
                current_payload = dict(active_event)
                self._latest_world_event_payload[guild.id] = current_payload
                await self._announce_world_event_window(guild, current_payload, ended=False)
            else:
                self._latest_world_event_payload.pop(guild.id, None)

            self._active_world_event_by_guild[guild.id] = active_key

    @fishing_event_window_loop.before_loop
    async def before_fishing_event_window_loop(self):
        await self.bot.wait_until_ready()

    @staticmethod
    def display_rod_name(rod_key: str) -> str:
        return _display_rod_name(rod_key)

    @staticmethod
    def display_tackle_name(tackle_key: str) -> str:
        return _display_tackle_name(tackle_key)

    @staticmethod
    def display_bait_name(bait_key: str | None) -> str:
        return _display_bait_name(bait_key)

    @staticmethod
    def display_zone_name(zone_key: str) -> str:
        return _display_zone_name(zone_key)

    @staticmethod
    def display_species_name(species_id: str | None, fallback: str | None = None) -> str:
        return _display_species_name(species_id, fallback)

    async def _progress_contracts(self, user_id: int, guild_id: int, code: str, amount: int = 1):
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is not None:
            await systems_cog.progress_contracts(user_id, guild_id, code, amount)

    def _market_multiplier(self, guild_id: int, category: str) -> tuple[float, dict[str, Any] | None]:
        systems_cog = self.bot.get_cog("Systems")
        if systems_cog is None:
            return 1.0, None
        return systems_cog.get_reward_multiplier(guild_id, category)

    @staticmethod
    def _fish_cooldown_minutes(user: dict[str, Any]) -> int:
        current_rod = str(user.get("fishing_rod", "none") or "none")
        vip = get_vip_level(int(user.get("vip_level", 0) or 0))
        base_cd = {"none": 3, "wooden": 4, "fiberglass": 6, "carbon": 8, "diamond": 11}.get(current_rod, 3)
        reduced = int(round(base_cd * (1 - float(vip.get("cooldown_reduction", 0) or 0))))
        return max(2, reduced)

    @staticmethod
    def _format_weight(weight_kg: float | int) -> str:
        value = float(weight_kg or 0)
        if value >= 100:
            return f"{value:,.1f} кг"
        if value >= 10:
            return f"{value:,.2f} кг"
        return f"{value:.2f} кг"

    async def _play_cast_animation(self, interaction: discord.Interaction, fishing_state: dict[str, Any]):
        zone_name = self.display_zone_name(str(fishing_state.get("selected_zone", "river_bank") or "river_bank"))
        rod_name = self.display_rod_name(str(fishing_state.get("fishing_rod", "none") or "none"))
        bait_name = self.display_bait_name(fishing_state.get("equipped_bait"))
        frames = [
            (
                "🎣 Заброс",
                f"Ты забрасываешь снасть в **{zone_name}**.\nУдочка: **{rod_name}**\nНаживка: **{bait_name}**",
                COLORS["info"],
            ),
            (
                "🌊 Поклёвка",
                "Леска дрогнула, вода пошла кругами. Кто-то точно сел на крючок...",
                COLORS["warning"],
            ),
            (
                "💪 Подсечка",
                "Подтягиваем улов к берегу. Сейчас станет ясно, что именно попалось.",
                COLORS["gold"],
            ),
        ]

        for index, (title, description, color) in enumerate(frames):
            embed = discord.Embed(
                title=title,
                description=description,
                color=color,
                timestamp=datetime.now(timezone.utc),
            )
            if not await safe_edit_original_response(interaction, embed=embed, view=None):
                return
            await asyncio.sleep(0.45 + index * 0.15)

    async def get_fishing_profile(self, user_id: int, guild_id: int) -> dict[str, Any]:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return {
                "fishing_rod": "none",
                "owned_rods": [],
                "owned_tackles": ["starter"],
                "equipped_tackle": "starter",
                "bait_stock": _default_bait_stock(),
                "equipped_bait": None,
                "unlocked_zones": ["river_bank"],
                "selected_zone": "river_bank",
                "total_catches": 0,
                "last_catch": None,
            }
        state = _fishing_state(user)
        state["fishing_rod"] = user.get("fishing_rod", "none")
        return state

    async def equip_fishing_rod(self, user_id: int, guild_id: int, rod_key: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            if rod_key not in FISHING_RODS:
                return False, "Такой удочки нет."

            fishing = _fishing_state(user)
            owned_rods = set(fishing.get("owned_rods", []))
            current_rod = str(user.get("fishing_rod", "none") or "none")

            if rod_key != "none" and rod_key not in owned_rods:
                return False, "Эта удочка ещё не куплена."
            if current_rod == rod_key:
                return False, "Эта удочка уже выбрана."

            user["fishing_rod"] = rod_key
            await db.update_user(user_id, guild_id, {"fishing_rod": rod_key, "game_stats": user.get("game_stats", {})})

        return True, discord.Embed(
            title="Удочка выбрана",
            description=f"Теперь активна **{_display_rod_name(rod_key)}**.",
            color=COLORS["success"],
        )

    async def choose_fishing_rod(self, user_id: int, guild_id: int, rod_key: str):
        return await self.equip_fishing_rod(user_id, guild_id, rod_key)

    async def equip_tackle(self, user_id: int, guild_id: int, tackle_key: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fishing = _fishing_state(user)
            if tackle_key not in FISHING_TACKLES:
                return False, "Такой снасти нет."

            owned_tackles = set(fishing.get("owned_tackles", []))
            current_tackle = str(fishing.get("equipped_tackle", "starter") or "starter")
            if tackle_key != "starter" and tackle_key not in owned_tackles:
                return False, "Эта снасть ещё не куплена."
            if current_tackle == tackle_key:
                return False, "Эта снасть уже выбрана."

            fishing["equipped_tackle"] = tackle_key
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        return True, discord.Embed(
            title="Снасть выбрана",
            description=f"Теперь активна **{_display_tackle_name(tackle_key)}**.",
            color=COLORS["success"],
        )

    async def choose_tackle(self, user_id: int, guild_id: int, tackle_key: str):
        return await self.equip_tackle(user_id, guild_id, tackle_key)

    async def equip_bait(self, user_id: int, guild_id: int, bait_key: str | None):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fishing = _fishing_state(user)
            bait_stock = fishing.get("bait_stock", {})
            if bait_key in (None, "none"):
                fishing["equipped_bait"] = None
                await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
                return True, discord.Embed(
                    title="Наживка снята",
                    description="Теперь рыбалка идёт без наживки.",
                    color=COLORS["success"],
                )

            if bait_key not in FISHING_BAITS:
                return False, "Такой наживки нет."
            if int(bait_stock.get(bait_key, 0) or 0) <= 0:
                return False, "Этой наживки нет в запасе."

            fishing["equipped_bait"] = bait_key
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        return True, discord.Embed(
            title="Наживка выбрана",
            description=f"Теперь активна **{_display_bait_name(bait_key)}**.",
            color=COLORS["success"],
        )

    async def choose_bait(self, user_id: int, guild_id: int, bait_key: str | None):
        return await self.equip_bait(user_id, guild_id, bait_key)

    async def select_fishing_zone(self, user_id: int, guild_id: int, zone_key: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fishing = _fishing_state(user)
            unlocked_zones = set(fishing.get("unlocked_zones", ["river_bank"]))
            if zone_key not in FISHING_ZONES:
                return False, "Такого спота нет."
            if zone_key not in unlocked_zones and zone_key != "river_bank":
                return False, "Этот спот ещё не открыт."

            fishing["selected_zone"] = zone_key
            await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})

        return True, discord.Embed(
            title="Спот выбран",
            description=f"Следующая рыбалка пройдёт на споте **{_display_zone_name(zone_key)}**.",
            color=COLORS["success"],
        )

    async def choose_fishing_zone(self, user_id: int, guild_id: int, zone_key: str):
        return await self.select_fishing_zone(user_id, guild_id, zone_key)

    async def handle_fishshop_action_v2(self, user_id: int, guild_id: int, tab: str, item_key: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fishing = _fishing_state(user)
            user["fishing_rod"] = user.get("fishing_rod", "none")
            owned_rods = set(fishing.get("owned_rods", []))

            if tab == "rods":
                rod = FISHING_RODS.get(item_key)
                if not rod or item_key == "none":
                    return False, "Такой удочки нет."
                if item_key in owned_rods:
                    user["fishing_rod"] = item_key
                    await db.update_user(user_id, guild_id, {"fishing_rod": item_key, "game_stats": user.get("game_stats", {})})
                    return True, discord.Embed(title="Удочка выбрана", description=f"Теперь активна **{_display_rod_name(item_key)}**.", color=COLORS["success"])
                if int(user.get("balance", 0) or 0) < int(rod["price"]) or int(user.get("gems", 0) or 0) < int(rod["gems"]):
                    return False, "Не хватает денег или гемов."
                user["balance"] = int(user.get("balance", 0) or 0) - int(rod["price"])
                user["gems"] = int(user.get("gems", 0) or 0) - int(rod["gems"])
                owned_rods.add(item_key)
                fishing["owned_rods"] = list(owned_rods)
                user["fishing_rod"] = item_key
                await db.update_user(
                    user_id,
                    guild_id,
                    {"balance": user["balance"], "gems": user["gems"], "fishing_rod": item_key, "game_stats": user.get("game_stats", {})},
                )
                return True, discord.Embed(title="Удочка куплена", description=f"Куплена и экипирована **{_display_rod_name(item_key)}**.", color=COLORS["success"])

            if tab == "tackles":
                tackle = FISHING_TACKLES.get(item_key)
                if not tackle:
                    return False, "Такой снасти нет."
                owned_tackles = set(fishing.get("owned_tackles", []))
                if item_key in owned_tackles:
                    fishing["equipped_tackle"] = item_key
                    await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
                    return True, discord.Embed(title="Снасть выбрана", description=f"Теперь активна **{_display_tackle_name(item_key)}**.", color=COLORS["success"])
                if int(user.get("balance", 0) or 0) < int(tackle["price"]) or int(user.get("gems", 0) or 0) < int(tackle["gems"]):
                    return False, "Не хватает денег или гемов."
                user["balance"] = int(user.get("balance", 0) or 0) - int(tackle["price"])
                user["gems"] = int(user.get("gems", 0) or 0) - int(tackle["gems"])
                owned_tackles.add(item_key)
                fishing["owned_tackles"] = list(owned_tackles)
                fishing["equipped_tackle"] = item_key
                await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})})
                return True, discord.Embed(title="Снасть куплена", description=f"Куплена и выбрана **{_display_tackle_name(item_key)}**.", color=COLORS["success"])

            if tab == "bait":
                raw_key = str(item_key or "")
                bait_key = raw_key.partition(":")[0]
                bait = _bait_shop_offer_map().get(bait_key)
                if not bait:
                    return False, "Этой наживки нет в текущей ротации магазина."
                remaining_limit = _bait_shop_remaining_limit(fishing, bait_key)
                if remaining_limit <= 0:
                    return False, "Лимит покупок этой наживки на текущую ротацию уже исчерпан."
                total_price = int(bait["price"])
                total_gems = int(bait["gems"])
                total_bundle = int(bait["bundle"])
                if int(user.get("balance", 0) or 0) < total_price or int(user.get("gems", 0) or 0) < total_gems:
                    return False, "Не хватает денег или гемов."
                user["balance"] = int(user.get("balance", 0) or 0) - total_price
                user["gems"] = int(user.get("gems", 0) or 0) - total_gems
                bait_stock = fishing.setdefault("bait_stock", _default_bait_stock())
                bait_stock[bait_key] = int(bait_stock.get(bait_key, 0) or 0) + total_bundle
                fishing["equipped_bait"] = bait_key
                bait_shop_state = _bait_shop_state(fishing)
                purchases = bait_shop_state.setdefault("purchases", {})
                purchases[bait_key] = int(purchases.get(bait_key, 0) or 0) + 1
                await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})})
                return True, discord.Embed(
                    title="Наживка куплена",
                    description=(
                        f"Добавлено **{total_bundle}x {_display_bait_name(bait_key)}**.\n"
                        f"Удача наживки: **x{float(bait.get('luck_mult', 1.0)):.2f}**.\n"
                        f"До обновления магазина осталось покупок: **{_bait_shop_remaining_limit(fishing, bait_key)}**."
                    ),
                    color=COLORS["success"],
                )

            zone = FISHING_ZONES.get(item_key)
            if not zone:
                return False, "Такого спота нет."
            unlocked = set(fishing.get("unlocked_zones", []))
            if item_key in unlocked:
                fishing["selected_zone"] = item_key
                await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
                return True, discord.Embed(title="Спот выбран", description=f"Теперь активен **{_display_zone_name(item_key)}**.", color=COLORS["success"])
            if int(user.get("balance", 0) or 0) < int(zone["price"]) or int(user.get("gems", 0) or 0) < int(zone["gems"]):
                return False, "Не хватает денег или гемов."
            user["balance"] = int(user.get("balance", 0) or 0) - int(zone["price"])
            user["gems"] = int(user.get("gems", 0) or 0) - int(zone["gems"])
            unlocked.add(item_key)
            fishing["unlocked_zones"] = list(unlocked)
            fishing["selected_zone"] = item_key
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})})
            return True, discord.Embed(title="Спот открыт", description=f"Открыт и выбран **{_display_zone_name(item_key)}**.", color=COLORS["success"])

    async def build_fishshop_embed_v2(self, user_id: int, guild_id: int, active_tab: str = "rods", page: int = 0) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Рыболовный магазин", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        fishing = _fishing_state(user)
        current_rod = user.get("fishing_rod", "none")
        equipped_tackle = fishing.get("equipped_tackle", "starter")
        equipped_bait = fishing.get("equipped_bait")
        selected_zone = fishing.get("selected_zone", "river_bank")
        bait_text = FISHING_BAITS[equipped_bait]["name"] if equipped_bait in FISHING_BAITS else "Без наживки"
        owned_rods = set(fishing.get("owned_rods", []))

        embed = discord.Embed(
            title="Рыболовный магазин",
            description=(
                f"Удочка: **{FISHING_RODS[current_rod]['name']}**\n"
                f"Снасть: **{FISHING_TACKLES[equipped_tackle]['name']}**\n"
                f"Наживка: **{bait_text}**\n"
                f"Спот: **{FISHING_ZONES[selected_zone]['name']}**"
            ),
            color=COLORS["purple"],
        )

        if active_tab == "rods":
            items = [(key, value) for key, value in FISHING_RODS.items() if key != "none"]
            embed.add_field(name="Раздел", value="Удочки", inline=False)
        elif active_tab == "tackles":
            items = [(key, value) for key, value in FISHING_TACKLES.items() if key != "starter"]
            embed.add_field(name="Раздел", value="Снасти", inline=False)
        elif active_tab == "bait":
            items = _bait_shop_offers()
            embed.add_field(
                name="Раздел",
                value=f"Наживки\nОбновление ассортимента: каждые 2 часа\nСледующее обновление: {format_discord_deadline(_next_bait_shop_refresh())}",
                inline=False,
            )
        else:
            items = [(key, value) for key, value in FISHING_ZONES.items() if key != "river_bank"]
            embed.add_field(name="Раздел", value="Споты", inline=False)

        start = page * SHOP_PAGE_SIZE
        visible_items = items[start:start + SHOP_PAGE_SIZE]
        for item_key, item in visible_items:
            if active_tab == "rods":
                status = "Экипирована" if item_key == current_rod else "Куплена" if item_key in owned_rods else "Можно купить"
                extra = f"Удача: `x{item['bonus']}`\n{_rod_description(item_key)}"
            elif active_tab == "tackles":
                owned = item_key in set(fishing.get("owned_tackles", []))
                status = "Экипирована" if item_key == equipped_tackle else "Куплена" if owned else "Можно купить"
                extra = f"Цена улова: `x{item['value_bonus']:.2f}`\n{item['description']}"
            elif active_tab == "bait":
                stock = int(fishing.get("bait_stock", {}).get(item_key, 0) or 0)
                remaining_limit = _bait_shop_remaining_limit(fishing, item_key)
                status = "Активна" if item_key == equipped_bait and stock > 0 else f"В запасе: {stock}"
                if remaining_limit <= 0:
                    status += " • лимит исчерпан"
                extra = (
                    f"Пак: `{item['bundle']} шт.`\n"
                    f"Удача: `x{float(item.get('luck_mult', 1.0)):.2f}`\n"
                    f"Лимит ротации: `{remaining_limit}/{int(item.get('shop_limit', 0) or 0)}` пак.\n"
                    f"{item['description']}"
                )
            else:
                unlocked = item_key in set(fishing.get("unlocked_zones", []))
                status = "Активен" if item_key == selected_zone else "Открыт" if unlocked else "Закрыт"
                extra = f"Цена улова: `x{item['value_bonus']:.2f}`\n{item['description']}"

            embed.add_field(
                name=item["name"],
                value=f"Цена: `{format_money(item['price'])}` + `{item['gems']} гем.`\n{extra}\nСтатус: **{status}**",
                inline=False,
            )

        max_page = max(0, (len(items) - 1) // SHOP_PAGE_SIZE) if items else 0
        footer = f"Страница {page + 1}/{max_page + 1}. Покупка и экипировка идут кнопками ниже."
        if active_tab == "bait":
            footer += " Ротация наживок обновляется раз в 2 часа."
        embed.set_footer(text=footer)
        return embed

    async def build_fishing_menu_embed(self, user_id: int, guild_id: int) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="Рыбалка", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        fishing = _fishing_state(user)
        current_rod = str(user.get("fishing_rod", "none") or "none")
        bait_key = fishing.get("equipped_bait")
        zone_key = str(fishing.get("selected_zone", "river_bank") or "river_bank")
        zone = FISHING_ZONES.get(zone_key, FISHING_ZONES["river_bank"])
        tackle = FISHING_TACKLES.get(fishing.get("equipped_tackle", "starter"), FISHING_TACKLES["starter"])
        bait_text = FISHING_BAITS[bait_key]["name"] if bait_key in FISHING_BAITS else "Без наживки"
        world_state = get_world_state()

        embed = discord.Embed(
            title="Рыбалка",
            description=(
                f"Удочка: **{FISHING_RODS[current_rod]['name']}**\n"
                f"Снасть: **{tackle['name']}**\n"
                f"Наживка: **{bait_text}**\n"
                f"Спот: **{zone['name']}**"
            ),
            color=COLORS["info"],
        )
        embed.add_field(name="Особенности спота", value=zone["description"], inline=False)
        embed.add_field(name="Мир рыбалки", value="\n".join(describe_world_lines(world_state)), inline=False)
        event_multiplier, event = self._market_multiplier(guild_id, "fish")
        if event is not None:
            embed.add_field(name="Событие рынка", value=f"Сейчас действует **{event['name']}**.", inline=False)

        cooldown_minutes = self._fish_cooldown_minutes(user)
        if user.get("last_fish"):
            last_fish = datetime.fromisoformat(user["last_fish"]).replace(tzinfo=timezone.utc)
            ready_at = last_fish + timedelta(minutes=cooldown_minutes)
            if datetime.now(timezone.utc) < ready_at:
                embed.add_field(name="Следующий заброс", value=format_discord_deadline(ready_at), inline=False)
            else:
                embed.add_field(name="Следующий заброс", value="**Готово**", inline=False)
        else:
            embed.add_field(name="Следующий заброс", value="**Готово**", inline=False)
        return embed

    async def _legacy_perform_fishing_cast_autosell(self, user_id: int, guild_id: int):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fishing = _fishing_state(user)
            current_rod = str(user.get("fishing_rod", "none") or "none")
            rod = FISHING_RODS.get(current_rod, FISHING_RODS["none"])
            now = datetime.now(timezone.utc)
            bait_key = fishing.get("equipped_bait")
            bait_stock = fishing.get("bait_stock", {})
            if bait_key and int(bait_stock.get(bait_key, 0) or 0) <= 0:
                fishing["equipped_bait"] = None
                bait_key = None
            cooldown_minutes = self._fish_cooldown_minutes(user)
            if user.get("last_fish"):
                last_fish = datetime.fromisoformat(user["last_fish"]).replace(tzinfo=timezone.utc)
                if cooldown_minutes > 0 and now - last_fish < timedelta(minutes=cooldown_minutes):
                    next_fish_at = last_fish + timedelta(minutes=cooldown_minutes)
                    return False, discord.Embed(
                        title="Рыбалка",
                        description=f"Следующий заброс будет доступен {format_discord_deadline(next_fish_at)}.",
                        color=COLORS["warning"],
                    )

            tackle = FISHING_TACKLES.get(fishing.get("equipped_tackle", "starter"), FISHING_TACKLES["starter"])
            bait = FISHING_BAITS.get(bait_key) if bait_key else None
            zone_key = str(fishing.get("selected_zone", "river_bank") or "river_bank")
            zone = FISHING_ZONES.get(zone_key, FISHING_ZONES["river_bank"])
            fish_multiplier, event = self._market_multiplier(guild_id, "fish")
            fish_data = roll_catch(rod_bonus=float(rod["bonus"]), tackle=tackle, bait=bait, zone_key=zone_key, now=now)
            world_state = fish_data["world_state"]
            fish_name = _display_species_name(fish_data.get("species_id"), fish_data.get("name"))
            rarity_name = _display_rarity_name(fish_data.get("rarity"))

            if bait_key and bait is not None and int(bait_stock.get(bait_key, 0) or 0) > 0:
                bait_stock[bait_key] = int(bait_stock.get(bait_key, 0) or 0) - 1
                if bait_stock[bait_key] <= 0:
                    fishing["equipped_bait"] = None

            if fish_multiplier > 1:
                fish_data["price"] = int(fish_data["price"] * fish_multiplier)

            fish_item = {
                "species_id": fish_data["species_id"],
                "name": fish_name,
                "rarity": fish_data["rarity"],
                "rarity_name": rarity_name,
                "emoji": fish_data["emoji"],
                "price": fish_data["price"],
                "zone": _display_zone_name(fish_data["zone_key"]),
                "zone_key": fish_data["zone_key"],
                "weight_kg": fish_data["weight_kg"],
                "weight_mult": fish_data["weight_mult"],
                "time_phase": fish_data["time_phase"],
                "weather_key": fish_data["weather_key"],
                "event_key": fish_data["event_key"],
                "boss": fish_data["boss"],
                "hotspot_bonus_applied": fish_data["hotspot_bonus_applied"],
                "caught_at": now.isoformat(),
            }
            fishing["total_catches"] = int(fishing.get("total_catches", 0) or 0) + 1
            fishing["last_catch"] = fish_item
            user["balance"] = int(user.get("balance", 0) or 0) + int(fish_data["price"])
            user["last_fish"] = now.isoformat()
            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user["balance"],
                    "last_fish": user["last_fish"],
                    "game_stats": user.get("game_stats", {}),
                },
            )

        await check_quest_progress(user_id, guild_id, "fish", 1)
        if fish_data["rarity"] == "legendary" or fish_data["boss"]:
            await check_quest_progress(user_id, guild_id, "fish_legendary", 1)
        asyncio.create_task(self._progress_contracts(user_id, guild_id, "fish", 1))
        asyncio.create_task(record_player_progress(user_id, guild_id, action="fish", amount=1))

        result = discord.Embed(title="Поклёвка!", color=fish_data["color"])
        result.add_field(
            name=f"{fish_data['emoji']} {fish_name}",
            value=(
                f"Редкость: **{rarity_name}**\n"
                f"Вес: **{self._format_weight(fish_data['weight_kg'])}**\n"
                f"Цена: **{format_money(fish_data['price'])}**\n"
                f"Спот: **{_display_zone_name(fish_data['zone_key'])}**"
            ),
            inline=False,
        )
        bait_text = _display_bait_name(bait_key) if bait else "Без наживки"
        bait_left = int(bait_stock.get(bait_key, 0) or 0) if bait_key else 0
        result.add_field(
            name="Снаряжение",
            value=(
                f"Удочка: {self.display_rod_name(current_rod)}\n"
                f"Снасть: {self.display_tackle_name(fishing.get('equipped_tackle', 'starter'))}\n"
                f"Наживка: {bait_text}"
                + (f" ({bait_left} шт.)" if bait_key else "")
            ),
            inline=False,
        )
        result.add_field(name="Мир рыбалки", value="\n".join(_build_world_lines(world_state)), inline=False)
        if fish_data["event_name"]:
            result.add_field(name="Событие", value=f"Сейчас активно **{_display_event_name(fish_data['event_key'])}**.", inline=False)
        if event is not None:
            result.add_field(name="Событие рынка", value=f"Сейчас действует **{event['name']}**.", inline=False)
        result.set_footer(text="Улов сразу продан, а последний трофей можно поставить в профиль.")
        return True, result

    async def handle_fishshop_action(self, user_id: int, guild_id: int, tab: str, item_key: str):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."
            fishing = _fishing_state(user)
            user["fishing_rod"] = user.get("fishing_rod", "none")
            if tab == "rods":
                rod = FISHING_RODS.get(item_key)
                if not rod or item_key == "none":
                    return False, "Такой удочки нет."
                if user["fishing_rod"] == item_key:
                    return False, "Эта удочка уже надета."
                if int(user.get("balance", 0) or 0) < int(rod["price"]) or int(user.get("gems", 0) or 0) < int(rod["gems"]):
                    return False, "Не хватает денег или гемов."
                user["balance"] = int(user.get("balance", 0) or 0) - int(rod["price"])
                user["gems"] = int(user.get("gems", 0) or 0) - int(rod["gems"])
                user["fishing_rod"] = item_key
                await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "fishing_rod": item_key})
                return True, discord.Embed(title="Удочка куплена", description=f"Куплено и надето: **{rod['name']}**", color=COLORS["success"])
            if tab == "tackles":
                tackle = FISHING_TACKLES.get(item_key)
                if not tackle:
                    return False, "Такой снасти нет."
                owned = set(fishing.get("owned_tackles", []))
                if item_key in owned:
                    fishing["equipped_tackle"] = item_key
                    await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
                    return True, discord.Embed(title="Снасть надета", description=f"Теперь активна снасть **{tackle['name']}**.", color=COLORS["success"])
                if int(user.get("balance", 0) or 0) < int(tackle["price"]) or int(user.get("gems", 0) or 0) < int(tackle["gems"]):
                    return False, "Не хватает денег или гемов."
                user["balance"] = int(user.get("balance", 0) or 0) - int(tackle["price"])
                user["gems"] = int(user.get("gems", 0) or 0) - int(tackle["gems"])
                owned.add(item_key)
                fishing["owned_tackles"] = list(owned)
                fishing["equipped_tackle"] = item_key
                await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})})
                return True, discord.Embed(title="Снасть куплена", description=f"Куплена и надета: **{tackle['name']}**.", color=COLORS["success"])
            if tab == "bait":
                bait = FISHING_BAITS.get(item_key)
                if not bait:
                    return False, "Такой наживки нет."
                if int(user.get("balance", 0) or 0) < int(bait["price"]) or int(user.get("gems", 0) or 0) < int(bait["gems"]):
                    return False, "Не хватает денег или гемов."
                user["balance"] = int(user.get("balance", 0) or 0) - int(bait["price"])
                user["gems"] = int(user.get("gems", 0) or 0) - int(bait["gems"])
                bait_stock = fishing.setdefault("bait_stock", {})
                bait_stock[item_key] = int(bait_stock.get(item_key, 0) or 0) + int(bait["bundle"])
                fishing["equipped_bait"] = item_key
                await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})})
                return True, discord.Embed(title="Наживка куплена", description=f"Добавлено: **{bait['bundle']}x {bait['name']}**. Эта наживка теперь активна.", color=COLORS["success"])
            zone = FISHING_ZONES.get(item_key)
            if not zone:
                return False, "Такой зоны нет."
            unlocked = set(fishing.get("unlocked_zones", []))
            if item_key in unlocked:
                fishing["selected_zone"] = item_key
                await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
                return True, discord.Embed(title="Зона выбрана", description=f"Теперь активна зона **{zone['name']}**.", color=COLORS["success"])
            if int(user.get("balance", 0) or 0) < int(zone["price"]) or int(user.get("gems", 0) or 0) < int(zone["gems"]):
                return False, "Не хватает денег или гемов."
            user["balance"] = int(user.get("balance", 0) or 0) - int(zone["price"])
            user["gems"] = int(user.get("gems", 0) or 0) - int(zone["gems"])
            unlocked.add(item_key)
            fishing["unlocked_zones"] = list(unlocked)
            fishing["selected_zone"] = item_key
            await db.update_user(user_id, guild_id, {"balance": user["balance"], "gems": user["gems"], "game_stats": user.get("game_stats", {})})
            return True, discord.Embed(title="Зона открыта", description=f"Открыта и активирована зона **{zone['name']}**.", color=COLORS["success"])

    async def build_fishshop_embed(self, user_id: int, guild_id: int, active_tab: str = "rods", page: int = 0) -> discord.Embed:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return discord.Embed(title="🎣 Рыболовный магазин", description="Не удалось загрузить профиль.", color=COLORS["warning"])
        fishing = _fishing_state(user)
        current_rod = user.get("fishing_rod", "none")
        equipped_tackle = fishing.get("equipped_tackle", "starter")
        equipped_bait = fishing.get("equipped_bait")
        selected_zone = fishing.get("selected_zone", "river_bank")
        bait_text = FISHING_BAITS[equipped_bait]["name"] if equipped_bait else "нет"
        embed = discord.Embed(title="🎣 Рыболовный магазин", description=f"Удочка: **{FISHING_RODS[current_rod]['name']}**\nСнасть: **{FISHING_TACKLES[equipped_tackle]['name']}**\nНаживка: **{bait_text}**\nЗона: **{FISHING_ZONES[selected_zone]['name']}**", color=COLORS['purple'])
        if active_tab == "rods":
            items = [(key, value) for key, value in FISHING_RODS.items() if key != "none"]
            embed.add_field(name="Раздел", value="Удочки", inline=False)
        elif active_tab == "tackles":
            items = [(key, value) for key, value in FISHING_TACKLES.items() if key != "starter"]
            embed.add_field(name="Раздел", value="Снасти", inline=False)
        elif active_tab == "bait":
            items = list(FISHING_BAITS.items())
            embed.add_field(name="Раздел", value="Наживки", inline=False)
        else:
            items = [(key, value) for key, value in FISHING_ZONES.items() if key != "river_bank"]
            embed.add_field(name="Раздел", value="Легендарные зоны", inline=False)
        start = page * SHOP_PAGE_SIZE
        visible_items = items[start:start + SHOP_PAGE_SIZE]
        for item_key, item in visible_items:
            if active_tab == "rods":
                status = "Надета" if item_key == current_rod else "Можно купить"
                extra = f"Бонус удачи: `x{item['bonus']}`"
            elif active_tab == "tackles":
                owned = item_key in set(fishing.get("owned_tackles", []))
                status = "Надета" if item_key == equipped_tackle else "Есть" if owned else "Можно купить"
                extra = f"Цена улова: `x{item['value_bonus']:.2f}`"
            elif active_tab == "bait":
                stock = int(fishing.get("bait_stock", {}).get(item_key, 0) or 0)
                status = "Активна" if item_key == equipped_bait and stock > 0 else f"В запасе: {stock}"
                extra = f"Пак: `{item['bundle']} шт.`"
            else:
                unlocked = item_key in set(fishing.get("unlocked_zones", []))
                status = "Активна" if item_key == selected_zone else "Открыта" if unlocked else "Закрыта"
                extra = f"Цена улова: `x{item['value_bonus']:.2f}`"
            embed.add_field(name=item["name"], value=f"Цена: `{format_money(item['price'])}` + `{item['gems']} гем.`\n{extra}\n{item['description']}\nСтатус: **{status}**", inline=False)
        max_page = max(0, (len(items) - 1) // SHOP_PAGE_SIZE) if items else 0
        embed.set_footer(text=f"Страница {page + 1}/{max_page + 1}. Все покупки и экипировка идут кнопками ниже.")
        return embed

    @app_commands.command(name="fish", description="Пойти на рыбалку")
    async def fish(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return
        view = FishingCastView(self, interaction.user.id, interaction.guild_id)
        embed = await self.build_fishing_menu_embed(interaction.user.id, interaction.guild_id)
        state = await self.get_fishing_profile(interaction.user.id, interaction.guild_id)
        current_zone = str(state.get("selected_zone", "river_bank") or "river_bank")
        view.zone_select.options = [
            discord.SelectOption(label=FISHING_ZONES[key]["name"][:100], value=key, default=key == current_zone)
            for key in state.get("unlocked_zones", ["river_bank"])
        ]
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()
        return

    @app_commands.command(name="fishshop", description="Открыть рыболовный магазин")
    async def fishshop(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return
        view = EnhancedFishShopView(self, interaction.user.id, interaction.guild_id)
        state = await self.get_fishing_profile(interaction.user.id, interaction.guild_id)
        view._sync_buttons(state)
        embed = await self.build_fishshop_embed_v2(interaction.user.id, interaction.guild_id, view.active_tab, view.page)
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()

    async def _inventory_snapshot(self, user_id: int, guild_id: int) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        user = await db.get_user(user_id, guild_id)
        if not user:
            return None, {}, {}, [], []
        fishing = _fishing_state(user)
        inventory = _inventory_state(user)
        fish_items = sorted(get_fish_items(user), key=lambda item: int(item.get("id", 0) or 0), reverse=True)
        general_items = sorted(get_general_items(user), key=lambda item: int(item.get("id", 0) or 0), reverse=True)
        return user, fishing, inventory, fish_items, general_items

    async def build_inventory_embed(self, user_id: int, guild_id: int, tab: str = "general", page: int = 0) -> discord.Embed:
        user, fishing, _, fish_items, general_items = await self._inventory_snapshot(user_id, guild_id)
        if not user:
            return discord.Embed(title="Инвентарь", description="Не удалось загрузить профиль.", color=COLORS["warning"])

        world_state = get_world_state()
        active_window = current_event_window()
        next_window = next_event_window()
        systems_cog = self.bot.get_cog("Systems")
        market_event = systems_cog.get_active_event(guild_id) if systems_cog else None

        if tab == "fish":
            embed = discord.Embed(
                title="🐟 Инвентарь рыбы",
                description="Здесь можно продавать рыбу, лочить трофеи по ID и листать улов.",
                color=COLORS["info"],
                timestamp=datetime.now(timezone.utc),
            )
            if not fish_items:
                embed.add_field(name="Хранилище", value="Рыбы пока нет. Сначала используй `/fish`.", inline=False)
                embed.set_footer(text="Предметы и кейсы лежат во вкладке Общее.")
                return embed

            start = page * INVENTORY_FISH_PAGE_SIZE
            visible = fish_items[start:start + INVENTORY_FISH_PAGE_SIZE]
            lines = []
            for item in visible:
                lock_icon = "🔒" if item.get("locked") else "🔓"
                lines.append(
                    f"`#{item['id']}` {lock_icon} {item.get('emoji', '🐟')} **{item.get('name', 'Рыба')}**"
                    f"\n{item.get('rarity_name', 'Обычная')} • {self._format_weight(item.get('weight_kg', 0))} • **{format_money(item.get('price', 0))}** • {item.get('zone', 'Неизвестно')}"
                )
            embed.add_field(name="Склад рыбы", value="\n\n".join(lines), inline=False)
            max_page = max(0, (len(fish_items) - 1) // INVENTORY_FISH_PAGE_SIZE)
            embed.set_footer(text=f"Страница {page + 1}/{max_page + 1}. Все действия по рыбе доступны только на этой вкладке.")
            return embed

        if tab == "general":
            embed = discord.Embed(
                title="📦 Общий инвентарь",
                description="Кейсы, страховки, наборы наживки и прочие предметы, которые лежат у тебя в инвентаре.",
                color=COLORS["warning"],
                timestamp=datetime.now(timezone.utc),
            )
            if not general_items:
                embed.add_field(name="Хранилище", value="Пока пусто. Покупай кейсы, чёрный рынок и специальные предметы.", inline=False)
                embed.set_footer(text="Использование предметов по ID доступно на этой вкладке.")
                return embed

            start = page * INVENTORY_GENERAL_PAGE_SIZE
            visible_general = general_items[start:start + INVENTORY_GENERAL_PAGE_SIZE]
            lines = []
            for item in visible_general:
                emoji = f"{item.get('emoji', '')} " if item.get("emoji") else ""
                quantity = int(item.get("quantity", 1) or 1)
                description = str(item.get("description") or "Без описания.")
                if len(description) > 110:
                    description = description[:107].rstrip() + "..."
                lines.append(
                    f"`#{item['id']}` {emoji}**{item.get('name', 'Предмет')}** x{quantity}\n{description}"
                )
            embed.add_field(name="Содержимое", value="\n\n".join(lines), inline=False)
            general_max_page = max(0, (len(general_items) - 1) // INVENTORY_GENERAL_PAGE_SIZE)
            embed.set_footer(text=f"Страница {page + 1}/{general_max_page + 1}. Использование предметов по ID доступно только на этой вкладке.")
            return embed

        unlocked_value = sum(int(item.get("price", 0) or 0) for item in fish_items if not bool(item.get("locked")))
        locked_count = sum(1 for item in fish_items if bool(item.get("locked")))
        last_catch = fishing.get("last_catch") if isinstance(fishing.get("last_catch"), dict) else None
        rod_key = str(user.get("fishing_rod", "none") or "none")
        tackle_key = str(fishing.get("equipped_tackle", "starter") or "starter")
        bait_key = fishing.get("equipped_bait")
        bait_stock = fishing.get("bait_stock", {})
        selected_zone = str(fishing.get("selected_zone", "river_bank") or "river_bank")
        owned_rods = ", ".join(self.display_rod_name(key) for key in fishing.get("owned_rods", [])) or "Нет"
        owned_tackles = ", ".join(self.display_tackle_name(key) for key in fishing.get("owned_tackles", [])) or "Нет"
        unlocked_zones = ", ".join(_display_zone_name(key) for key in fishing.get("unlocked_zones", [])) or "Нет"
        bait_lines = []
        for bait_code, amount in fishing.get("bait_stock", {}).items():
            amount_int = int(amount or 0)
            if amount_int <= 0:
                continue
            bait_lines.append(f"{_display_bait_name(bait_code)}: **{amount_int}**")
        if not bait_lines:
            bait_lines.append("Наживки пока нет.")
        gear_embed = discord.Embed(
            title="🧰 Снаряжение рыбака",
            description="Текущее снаряжение, сводка по улову и состояние мира рыбалки.",
            color=COLORS["success"],
            timestamp=datetime.now(timezone.utc),
        )
        gear_embed.add_field(
            name="Текущий набор",
            value=(
                f"Удочка: **{self.display_rod_name(rod_key)}**\n"
                f"Снасть: **{self.display_tackle_name(tackle_key)}**\n"
                f"Наживка: **{_display_bait_name(bait_key)}**"
                + (f" (`{int(bait_stock.get(bait_key, 0) or 0)}` шт.)" if bait_key else "")
                + f"\nСпот: **{_display_zone_name(selected_zone)}**"
            ),
            inline=False,
        )
        gear_embed.add_field(
            name="🎣 Рыбное хранилище",
            value=(
                f"Рыб в хранилище: **{len(fish_items)}**\n"
                f"Стоимость незалоченной: **{format_money(unlocked_value)}**\n"
                f"Залочено: **{locked_count}**"
            ),
            inline=True,
        )
        if last_catch:
            catch_value = (
                f"`#{last_catch.get('id', '?')}` {last_catch.get('emoji', '🐟')} **{last_catch.get('name', 'Рыба')}**\n"
                f"{last_catch.get('rarity_name', 'Обычная')} • {self._format_weight(last_catch.get('weight_kg', 0))}\n"
                f"Стоимость: **{format_money(last_catch.get('price', 0))}**"
            )
        else:
            catch_value = "Пока ничего не поймано."
        gear_embed.add_field(name="🐠 Последний улов", value=catch_value, inline=True)
        gear_embed.add_field(name="Купленные удочки", value=owned_rods, inline=False)
        gear_embed.add_field(name="Купленные снасти", value=owned_tackles, inline=False)
        gear_embed.add_field(name="Открытые зоны", value=unlocked_zones, inline=False)
        gear_embed.add_field(name="Запас наживки", value="\n".join(bait_lines), inline=False)
        world_lines = [f"Текущий спот: **{_display_zone_name(selected_zone)}**", *_build_world_lines(world_state)]
        if next_window:
            starts_at = next_window.get("start_at")
            if isinstance(starts_at, datetime):
                world_lines.append(
                    f"Следующий ивент: **{next_window.get('name', 'Неизвестно')}** {format_discord_deadline(starts_at.astimezone(timezone.utc))}"
                )
        if market_event is not None:
            world_lines.append(f"Рыночное событие: **{market_event['name']}**")
        else:
            world_lines.append("Рыночное событие: **сейчас нет**")
        gear_embed.add_field(name="Мир рыбалки", value="\n".join(world_lines), inline=False)
        gear_embed.set_footer(text="Ниже можно сразу менять удочку, снасть, наживку и спот.")
        return gear_embed

    async def sell_inventory_fish(self, user_id: int, guild_id: int, mode: str, item_id: int | None = None) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            if mode == "id":
                if item_id is None:
                    return False, "Нужен ID рыбы."
                sold_item, total = sell_fish_by_id(user, item_id)
                if sold_item is None:
                    return False, "Рыба не найдена, уже продана или залочена."
                sold_count = 1
            else:
                if mode == "common_uncommon":
                    sold_items, total = sell_fish_items(user, lambda item: str(item.get("rarity")) in {"common", "uncommon"})
                else:
                    sold_items, total = sell_fish_items(user, lambda item: True)
                if not sold_items:
                    return False, "Для этого действия нет подходящей рыбы."
                sold_count = len(sold_items)
                sold_item = None

            user["balance"] = int(user.get("balance", 0) or 0) + int(total)
            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user["balance"],
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        await check_quest_progress(user_id, guild_id, "earn", int(total))
        if mode == "id" and sold_item is not None:
            description = (
                f"Продана `#{sold_item['id']}` {sold_item.get('emoji', '🐟')} **{sold_item.get('name', 'Fish')}**\n"
                f"Цена: **{format_money(total)}**\n"
                f"Баланс: **{format_money(user['balance'])}**"
            )
        else:
            description = (
                f"Продано рыб: **{sold_count}**\n"
                f"Сумма продажи: **{format_money(total)}**\n"
                f"Баланс: **{format_money(user['balance'])}**"
            )
        return True, discord.Embed(title="Рыба продана", description=description, color=COLORS["success"])

    async def toggle_inventory_fish_lock(self, user_id: int, guild_id: int, item_id: int) -> tuple[bool, discord.Embed | str]:
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fish_item = toggle_fish_lock(user, item_id)
            if fish_item is None:
                return False, "Рыба с таким ID не найдена."
            await db.update_user(
                user_id,
                guild_id,
                {
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        lock_state = "залочена" if fish_item.get("locked") else "разлочена"
        return True, discord.Embed(
            title="Статус рыбы обновлён",
            description=f"`#{fish_item['id']}` {fish_item.get('emoji', '🐟')} **{fish_item.get('name', 'Fish')}** теперь **{lock_state}**.",
            color=COLORS["info"],
        )

    async def use_inventory_general_item(
        self,
        interaction: discord.Interaction,
        user_id: int,
        guild_id: int,
        item_id: int,
    ) -> tuple[bool, discord.Embed | str | None]:
        preview_user = await db.get_user(user_id, guild_id)
        if not preview_user:
            return False, "Не удалось загрузить профиль."

        preview_item = find_general_item(preview_user, item_id)
        if preview_item is None:
            return False, "Предмет с таким ID не найден."

        item_type = str(preview_item.get("item_type") or "")
        if item_type == "case":
            success, message = await open_case_from_inventory(
                interaction,
                user_id=user_id,
                guild_id=guild_id,
                item_id=item_id,
                ephemeral=True,
            )
            return success, message

        if item_type not in {
            "bait_bundle",
            "shield_card",
            "cash_bundle",
            "house_wallet_cache",
            "crypto_cache",
            "cosmetic_pack",
        }:
            return False, "Этот предмет пока нельзя использовать."

        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            item = find_general_item(user, item_id)
            if item is None:
                return False, "Предмет с таким ID больше недоступен."

            consumed = decrement_general_item(user, item_id, 1)
            if consumed is None:
                return False, "Не удалось списать этот предмет."

            payload = consumed.get("payload") if isinstance(consumed.get("payload"), dict) else {}
            result_lines: list[str] = []
            now = datetime.now(timezone.utc)

            if item_type == "bait_bundle":
                fishing = _fishing_state(user)
                bait_stock = fishing.setdefault("bait_stock", {})
                bait_key = str(payload.get("bait") or "worms")
                amount = int(payload.get("amount", 0) or 0)
                bait_stock[bait_key] = int(bait_stock.get(bait_key, 0) or 0) + amount
                result_lines.append(f"Added **{amount}x {_display_bait_name(bait_key)}** to bait stock.")
            elif item_type == "shield_card":
                hours = int(payload.get("hours", 24) or 24)
                current_until = _parse_iso_datetime(user.get("shield_until"))
                base_time = current_until if current_until and current_until > now else now
                new_until = base_time + timedelta(hours=hours)
                user["shield_until"] = new_until.isoformat()
                result_lines.append(f"Shadow insurance is active until {format_discord_deadline(new_until)}.")
            elif item_type == "cash_bundle":
                amount = int(payload.get("amount", 0) or 0)
                user["balance"] = int(user.get("balance", 0) or 0) + amount
                result_lines.append(f"Received **{format_money(amount)}**.")
            elif item_type == "house_wallet_cache":
                amount = int(payload.get("amount", 0) or 0)
                systems = _system_state(user)
                house = systems.get("house")
                if not isinstance(house, dict):
                    house = {}
                    systems["house"] = house
                if house.get("owned_house_id"):
                    house["mining_wallet"] = int(house.get("mining_wallet", 0) or 0) + amount
                    result_lines.append(f"**{format_money(amount)}** отправлено в кошелёк подвала.")
                else:
                    user["balance"] = int(user.get("balance", 0) or 0) + amount
                    result_lines.append(f"Дома нет, поэтому **{format_money(amount)}** отправлено прямо на баланс.")
            elif item_type == "crypto_cache":
                amount = int(payload.get("amount", 0) or 0)
                crypto_name = str(payload.get("crypto_name") or "Crypto")
                crypto_amount = str(payload.get("crypto_amount") or "1")
                user["balance"] = int(user.get("balance", 0) or 0) + amount
                result_lines.append(f"Продано **{crypto_amount} {crypto_name}** на сумму **{format_money(amount)}**.")
            elif item_type == "cosmetic_pack":
                gems = int(payload.get("gems", 0) or 0)
                reputation_delta = int(payload.get("reputation", 0) or 0)
                if gems > 0:
                    user["gems"] = int(user.get("gems", 0) or 0) + gems
                    result_lines.append(f"Гемы: **+{gems}**")
                if reputation_delta:
                    new_rep = change_reputation(user, reputation_delta)
                    result_lines.append(f"Репутация: **{new_rep}**")
                title_key = payload.get("title")
                if title_key and unlock_title(user, str(title_key)):
                    result_lines.append(f"Открыт титул: **{reward_text({'type': 'title', 'key': title_key})}**")
                theme_key = payload.get("theme")
                if theme_key and unlock_theme(user, str(theme_key)):
                    result_lines.append(f"Открыта тема: **{reward_text({'type': 'theme', 'key': theme_key})}**")

            await db.update_user(
                user_id,
                guild_id,
                {
                    "balance": user.get("balance", 0),
                    "gems": user.get("gems", 0),
                    "vip_level": user.get("vip_level", 0),
                    "shield_until": user.get("shield_until"),
                    "buff_xp_until": user.get("buff_xp_until"),
                    "buff_money_until": user.get("buff_money_until"),
                    "temp_vip_until": user.get("temp_vip_until"),
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        return True, discord.Embed(
            title="Предмет использован",
            description="\n".join(result_lines) if result_lines else "Предмет был использован.",
            color=COLORS["success"],
        )

    async def perform_fishing_cast(self, user_id: int, guild_id: int):
        async with get_user_lock(user_id):
            user = await db.get_user(user_id, guild_id)
            if not user:
                return False, "Не удалось загрузить профиль."

            fishing = _fishing_state(user)
            current_rod = str(user.get("fishing_rod", "none") or "none")
            rod = FISHING_RODS.get(current_rod, FISHING_RODS["none"])
            now = datetime.now(timezone.utc)
            bait_key = fishing.get("equipped_bait")
            bait_stock = fishing.get("bait_stock", {})
            if bait_key and int(bait_stock.get(bait_key, 0) or 0) <= 0:
                fishing["equipped_bait"] = None
                bait_key = None
            cooldown_minutes = self._fish_cooldown_minutes(user)
            if user.get("last_fish"):
                last_fish = datetime.fromisoformat(user["last_fish"]).replace(tzinfo=timezone.utc)
                if cooldown_minutes > 0 and now - last_fish < timedelta(minutes=cooldown_minutes):
                    next_fish_at = last_fish + timedelta(minutes=cooldown_minutes)
                    return False, discord.Embed(
                        title="Рыбалка",
                        description=f"Следующий заброс будет доступен {format_discord_deadline(next_fish_at)}.",
                        color=COLORS["warning"],
                    )

            tackle = FISHING_TACKLES.get(fishing.get("equipped_tackle", "starter"), FISHING_TACKLES["starter"])
            bait = FISHING_BAITS.get(bait_key) if bait_key else None
            zone_key = str(fishing.get("selected_zone", "river_bank") or "river_bank")
            fish_multiplier, event = self._market_multiplier(guild_id, "fish")
            fish_data = roll_catch(rod_bonus=float(rod["bonus"]), tackle=tackle, bait=bait, zone_key=zone_key, now=now)
            world_state = fish_data["world_state"]
            fish_name = _display_species_name(fish_data.get("species_id"), fish_data.get("name"))
            rarity_name = _display_rarity_name(fish_data.get("rarity"))

            if bait_key and bait is not None and int(bait_stock.get(bait_key, 0) or 0) > 0:
                bait_stock[bait_key] = int(bait_stock.get(bait_key, 0) or 0) - 1
                if bait_stock[bait_key] <= 0:
                    fishing["equipped_bait"] = None

            if fish_multiplier > 1:
                fish_data["price"] = int(fish_data["price"] * fish_multiplier)

            fish_item = add_fish_item(
                user,
                species_id=str(fish_data["species_id"]),
                name=fish_name,
                emoji=str(fish_data["emoji"]),
                rarity=str(fish_data["rarity"]),
                rarity_name=rarity_name,
                price=int(fish_data["price"]),
                zone_key=str(fish_data["zone_key"]),
                zone=_display_zone_name(fish_data["zone_key"]),
                weight_kg=float(fish_data["weight_kg"]),
                caught_at=now.isoformat(),
                extra={
                    "weight_mult": fish_data["weight_mult"],
                    "time_phase": fish_data["time_phase"],
                    "weather_key": fish_data["weather_key"],
                    "event_key": fish_data["event_key"],
                    "boss": fish_data["boss"],
                    "hotspot_bonus_applied": fish_data["hotspot_bonus_applied"],
                },
            )
            fishing["total_catches"] = int(fishing.get("total_catches", 0) or 0) + 1
            fishing["last_catch"] = dict(fish_item)
            user["last_fish"] = now.isoformat()
            await db.update_user(
                user_id,
                guild_id,
                {
                    "last_fish": user["last_fish"],
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )

        await check_quest_progress(user_id, guild_id, "fish", 1)
        if fish_data["rarity"] == "legendary" or fish_data["boss"]:
            await check_quest_progress(user_id, guild_id, "fish_legendary", 1)
        asyncio.create_task(self._progress_contracts(user_id, guild_id, "fish", 1))
        asyncio.create_task(record_player_progress(user_id, guild_id, action="fish", amount=1))

        result = discord.Embed(title="🎣 Улов сохранён!", color=fish_data["color"])
        result.add_field(
            name=f"{fish_data['emoji']} {fish_name}",
            value=(
                f"ID: **#{fish_item['id']}**\n"
                f"Редкость: **{rarity_name}**\n"
                f"Вес: **{self._format_weight(fish_data['weight_kg'])}**\n"
                f"Цена: **{format_money(fish_data['price'])}**\n"
                f"Спот: **{_display_zone_name(fish_data['zone_key'])}**"
            ),
            inline=False,
        )
        bait_text = _display_bait_name(bait_key) if bait else "Без наживки"
        bait_left = int(bait_stock.get(bait_key, 0) or 0) if bait_key else 0
        result.add_field(
            name="Снаряжение",
            value=(
                f"Удочка: {self.display_rod_name(current_rod)}\n"
                f"Снасть: {self.display_tackle_name(fishing.get('equipped_tackle', 'starter'))}\n"
                f"Наживка: {bait_text}"
                + (f" ({bait_left} шт.)" if bait_key else "")
            ),
            inline=False,
        )
        result.add_field(name="Мир", value="\n".join(_build_world_lines(world_state)), inline=False)
        if fish_data["event_name"]:
            result.add_field(name="Ивент", value=f"Сейчас активно **{_display_event_name(fish_data['event_key'])}**.", inline=False)
        if event is not None and fish_multiplier != 1.0:
            result.add_field(name="Рынок", value=f"На рыбу сейчас действует бонус от события **{event['name']}**.", inline=False)
        result.set_footer(text=f"Улов сохранён в /inventory под ID #{fish_item['id']}. Там его можно продать или залочить.")
        return True, result

    @app_commands.command(name="inventory", description="Открыть инвентарь рыбалки и предметов")
    async def inventory(self, interaction: discord.Interaction):
        if not await check_channel(interaction):
            await send_wrong_channel_message(interaction)
            return
        if not await safe_defer(interaction):
            return

        view = InventoryView(self, interaction.user.id, interaction.guild_id)
        embed = await self.build_inventory_embed(interaction.user.id, interaction.guild_id, view.active_tab, view.page)
        user, _, _, fish_items, general_items = await self._inventory_snapshot(interaction.user.id, interaction.guild_id)
        view.sync_buttons(user, fish_items, general_items)
        if user is not None:
            await db.update_user(
                interaction.user.id,
                interaction.guild_id,
                {
                    "inventory": user.get("inventory"),
                    "game_stats": user.get("game_stats", {}),
                },
            )
        if not await safe_edit_original_response(interaction, embed=embed, view=view):
            return
        view.message = await interaction.original_response()

class InventoryIdModal(discord.ui.Modal):
    def __init__(self, view: "InventoryView", action: str):
        self.view = view
        self.action = action
        title_map = {
            "sell": "Продать по ID",
            "lock": "Лок по ID",
            "use": "Использовать по ID",
        }
        super().__init__(title=title_map.get(action, "Действие с инвентарём"))
        self.item_id = discord.ui.TextInput(
            label="ID предмета",
            placeholder="Например: 42",
            required=True,
            max_length=12,
        )
        self.add_item(self.item_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            item_id = int(str(self.item_id.value).strip())
        except ValueError:
            await interaction.response.send_message("ID должен быть числом.", ephemeral=True)
            return

        if self.action == "sell":
            success, payload = await self.view.cog.sell_inventory_fish(self.view.user_id, self.view.guild_id, "id", item_id=item_id)
        elif self.action == "lock":
            success, payload = await self.view.cog.toggle_inventory_fish_lock(self.view.user_id, self.view.guild_id, item_id)
        else:
            success, payload = await self.view.cog.use_inventory_general_item(interaction, self.view.user_id, self.view.guild_id, item_id)

        await self.view.refresh_direct()
        if isinstance(payload, discord.Embed):
            if interaction.response.is_done():
                await interaction.followup.send(embed=payload, ephemeral=True)
            else:
                await interaction.response.send_message(embed=payload, ephemeral=True)
            return
        if isinstance(payload, str) and payload:
            if interaction.response.is_done():
                await interaction.followup.send(payload, ephemeral=True)
            else:
                await interaction.response.send_message(payload, ephemeral=True)
            return
        if not success and not interaction.response.is_done():
            await interaction.response.send_message("Не удалось выполнить действие.", ephemeral=True)


class InventoryView(discord.ui.View):
    def __init__(self, cog: FishingCog, user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.active_tab = "general"
        self.page = 0
        self.message: discord.Message | None = None
        self._view_lock = asyncio.Lock()
        self._build_items()
        self._add_static_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это окно инвентаря открыто не для тебя.", ephemeral=True)
            return False
        return True

    def _build_items(self):
        self.general_btn = discord.ui.Button(label="Общее", style=discord.ButtonStyle.primary, row=0)
        self.general_btn.callback = self._on_general

        self.fish_btn = discord.ui.Button(label="Рыба", style=discord.ButtonStyle.secondary, row=0)
        self.fish_btn.callback = self._on_fish

        self.gear_btn = discord.ui.Button(label="Снаряжение", style=discord.ButtonStyle.secondary, row=0)
        self.gear_btn.callback = self._on_gear

        self.use_id_btn = discord.ui.Button(label="Исп. предмет", style=discord.ButtonStyle.success, row=1)
        self.use_id_btn.callback = self._on_use_id

        self.sell_all_btn = discord.ui.Button(label="Продать всё", style=discord.ButtonStyle.danger, row=1)
        self.sell_all_btn.callback = self._on_sell_all

        self.sell_common_btn = discord.ui.Button(label="Продать c/u", style=discord.ButtonStyle.danger, row=1)
        self.sell_common_btn.callback = self._on_sell_common

        self.sell_id_btn = discord.ui.Button(label="Продать по ID", style=discord.ButtonStyle.secondary, row=2)
        self.sell_id_btn.callback = self._on_sell_id

        self.lock_id_btn = discord.ui.Button(label="Лок по ID", style=discord.ButtonStyle.secondary, row=2)
        self.lock_id_btn.callback = self._on_lock_id

        self.rod_select = discord.ui.Select(
            placeholder="Удочка",
            row=1,
            options=[discord.SelectOption(label="Удочка: Обычный крючок", value="rod:none", default=True)],
        )
        self.rod_select.callback = self._on_rod_select

        self.tackle_select = discord.ui.Select(
            placeholder="Снасть",
            row=2,
            options=[discord.SelectOption(label="Снасть: Базовая снасть", value="starter", default=True)],
        )
        self.tackle_select.callback = self._on_tackle_select

        self.bait_select = discord.ui.Select(
            placeholder="Наживка",
            row=3,
            options=[discord.SelectOption(label="Без наживки", value="none", default=True)],
        )
        self.bait_select.callback = self._on_bait_select

        self.zone_select = discord.ui.Select(
            placeholder="Спот",
            row=4,
            options=[discord.SelectOption(label="Речной берег", value="river_bank", default=True)],
        )
        self.zone_select.callback = self._on_zone_select

        self.prev_btn = discord.ui.Button(label="Назад", style=discord.ButtonStyle.secondary, row=4)
        self.prev_btn.callback = self._on_prev

        self.refresh_btn = discord.ui.Button(label="Обновить", style=discord.ButtonStyle.secondary, row=4)
        self.refresh_btn.callback = self._on_refresh

        self.next_btn = discord.ui.Button(label="Дальше", style=discord.ButtonStyle.secondary, row=4)
        self.next_btn.callback = self._on_next

        self._static_items = (self.general_btn, self.fish_btn, self.gear_btn)
        self._dynamic_items = (
            self.use_id_btn,
            self.sell_all_btn,
            self.sell_common_btn,
            self.sell_id_btn,
            self.lock_id_btn,
            self.prev_btn,
            self.refresh_btn,
            self.next_btn,
            self.rod_select,
            self.tackle_select,
            self.bait_select,
            self.zone_select,
        )

    def _add_static_items(self):
        for item in self._static_items:
            if item not in self.children:
                self.add_item(item)

    def _toggle_item(self, item: discord.ui.Item[Any], visible: bool):
        if visible and item not in self.children:
            self.add_item(item)
        elif not visible and item in self.children:
            self.remove_item(item)

    async def _send_payload(self, interaction: discord.Interaction, payload: discord.Embed | str | None):
        if isinstance(payload, discord.Embed):
            await interaction.followup.send(embed=payload, ephemeral=True)
        elif payload:
            await interaction.followup.send(str(payload), ephemeral=True)

    @staticmethod
    def _selected_value(interaction: discord.Interaction, fallback: discord.ui.Select) -> str | None:
        data = interaction.data if isinstance(interaction.data, dict) else {}
        raw_values = data.get("values")
        if isinstance(raw_values, list) and raw_values:
            return str(raw_values[0])
        values = getattr(fallback, "values", None)
        if values:
            return str(values[0])
        return None

    def sync_buttons(self, user: dict[str, Any] | None, fish_items: list[dict[str, Any]], general_items: list[dict[str, Any]]):
        self.general_btn.style = discord.ButtonStyle.primary if self.active_tab == "general" else discord.ButtonStyle.secondary
        self.fish_btn.style = discord.ButtonStyle.primary if self.active_tab == "fish" else discord.ButtonStyle.secondary
        self.gear_btn.style = discord.ButtonStyle.primary if self.active_tab == "gear" else discord.ButtonStyle.secondary

        fishing = _fishing_state(user) if user else {}
        sellable_fish = [item for item in fish_items if not bool(item.get("locked"))]
        common_uncommon = [item for item in sellable_fish if str(item.get("rarity") or "") in {"common", "uncommon"}]

        self.use_id_btn.disabled = not bool(general_items)
        self.sell_all_btn.disabled = not bool(sellable_fish)
        self.sell_common_btn.disabled = not bool(common_uncommon)
        self.sell_id_btn.disabled = not bool(fish_items)
        self.lock_id_btn.disabled = not bool(fish_items)

        fish_max_page = max(0, (len(fish_items) - 1) // INVENTORY_FISH_PAGE_SIZE) if fish_items else 0
        general_max_page = max(0, (len(general_items) - 1) // INVENTORY_GENERAL_PAGE_SIZE) if general_items else 0
        if self.active_tab == "fish":
            max_page = fish_max_page
        elif self.active_tab == "general":
            max_page = general_max_page
        else:
            max_page = 0
        self.page = min(self.page, max_page)
        self.prev_btn.disabled = self.page <= 0
        self.next_btn.disabled = self.page >= max_page

        current_rod = str(user.get("fishing_rod", "none") or "none") if user else "none"
        current_tackle = str(fishing.get("equipped_tackle", "starter") or "starter")
        current_bait = fishing.get("equipped_bait")
        current_zone = str(fishing.get("selected_zone", "river_bank") or "river_bank")

        owned_rods = [key for key in fishing.get("owned_rods", []) if key in FISHING_RODS and key != "none"]
        rod_options = [
            discord.SelectOption(
                label=f"Удочка: {self.cog.display_rod_name('none')}"[:100],
                value="rod:none",
                default=current_rod == "none",
                description="Снять удочку"[:100],
            )
        ]
        for rod_key in owned_rods:
            rod_options.append(
                discord.SelectOption(
                    label=f"Удочка: {self.cog.display_rod_name(rod_key)}"[:100],
                    value=f"rod:{rod_key}",
                    default=current_rod == rod_key,
                    description=("Активна" if current_rod == rod_key else "Надеть")[:100],
                )
            )
        self.rod_select.options = rod_options[:25]
        self.rod_select.disabled = not bool(self.rod_select.options)

        owned_tackles = set(fishing.get("owned_tackles", []))
        tackle_keys = ["starter", *[key for key in FISHING_TACKLES if key != "starter" and key in owned_tackles]]
        tackle_options = []
        for tackle_key in tackle_keys:
            tackle_options.append(
                discord.SelectOption(
                    label=f"Снасть: {self.cog.display_tackle_name(tackle_key)}"[:100],
                    value=tackle_key,
                    default=current_tackle == tackle_key,
                    description=("Активна" if current_tackle == tackle_key else "Надеть")[:100],
                )
            )
        self.tackle_select.options = tackle_options[:25]
        self.tackle_select.disabled = not bool(self.tackle_select.options)

        bait_stock = fishing.get("bait_stock", {})
        bait_options = [
            discord.SelectOption(
                label="Без наживки",
                value="none",
                default=current_bait in (None, "none"),
                description="Ловить без наживки"[:100],
            )
        ]
        for bait_key in FISHING_BAITS:
            count = int(bait_stock.get(bait_key, 0) or 0)
            if count <= 0:
                continue
            bait_options.append(
                discord.SelectOption(
                    label=self.cog.display_bait_name(bait_key)[:100],
                    value=bait_key,
                    default=current_bait == bait_key,
                    description=f"В запасе: {count}"[:100],
                )
            )
        self.bait_select.options = bait_options[:25]
        self.bait_select.disabled = not bool(self.bait_select.options)

        unlocked_zones = set(fishing.get("unlocked_zones", ["river_bank"]))
        zone_options = []
        for zone_key in FISHING_ZONES:
            if zone_key != "river_bank" and zone_key not in unlocked_zones:
                continue
            zone_options.append(
                discord.SelectOption(
                    label=self.cog.display_zone_name(zone_key)[:100],
                    value=zone_key,
                    default=current_zone == zone_key,
                    description=("Выбран" if current_zone == zone_key else "Сделать активным")[:100],
                )
            )
        self.zone_select.options = zone_options[:25]
        self.zone_select.disabled = not bool(self.zone_select.options)

        for item in self._dynamic_items:
            self._toggle_item(item, False)

        if self.active_tab == "fish":
            self._toggle_item(self.sell_all_btn, True)
            self._toggle_item(self.sell_common_btn, True)
            self._toggle_item(self.sell_id_btn, True)
            self._toggle_item(self.lock_id_btn, True)
            self._toggle_item(self.prev_btn, True)
            self._toggle_item(self.refresh_btn, True)
            self._toggle_item(self.next_btn, True)
            return

        if self.active_tab == "general":
            self._toggle_item(self.use_id_btn, True)
            self._toggle_item(self.prev_btn, True)
            self._toggle_item(self.refresh_btn, True)
            self._toggle_item(self.next_btn, True)
            return

        self._toggle_item(self.rod_select, True)
        self._toggle_item(self.tackle_select, True)
        self._toggle_item(self.bait_select, True)
        self._toggle_item(self.zone_select, True)

    async def refresh(self, interaction: discord.Interaction | None = None):
        user, _, _, fish_items, general_items = await self.cog._inventory_snapshot(self.user_id, self.guild_id)
        self.sync_buttons(user, fish_items, general_items)
        embed = await self.cog.build_inventory_embed(self.user_id, self.guild_id, self.active_tab, self.page)
        if interaction is not None:
            if not await safe_edit_original_response(interaction, embed=embed, view=self):
                return
            try:
                self.message = await interaction.original_response()
            except Exception:
                self.message = interaction.message or self.message
            return
        if self.message is not None:
            try:
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass

    async def refresh_direct(self):
        await self.refresh(None)

    async def _edit_live_message(self, interaction: discord.Interaction):
        user, _, _, fish_items, general_items = await self.cog._inventory_snapshot(self.user_id, self.guild_id)
        self.sync_buttons(user, fish_items, general_items)
        embed = await self.cog.build_inventory_embed(self.user_id, self.guild_id, self.active_tab, self.page)

        async def _notify_refresh_error():
            message = "Не удалось обновить инвентарь. Попробуй ещё раз."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.response.send_message(message, ephemeral=True)
            except Exception:
                pass

        try:
            if not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.edit_original_response(embed=embed, view=self)
        except discord.NotFound:
            if interaction.message is None:
                await _notify_refresh_error()
                return
            try:
                await interaction.message.edit(embed=embed, view=self)
            except (discord.NotFound, discord.HTTPException):
                await _notify_refresh_error()
                return
        except discord.HTTPException:
            if interaction.message is None:
                await _notify_refresh_error()
                return
            try:
                await interaction.message.edit(embed=embed, view=self)
            except (discord.NotFound, discord.HTTPException):
                await _notify_refresh_error()
                return

        try:
            self.message = interaction.message or await interaction.original_response()
        except Exception:
            self.message = interaction.message or self.message

    async def _switch_tab(self, interaction: discord.Interaction, tab: str):
        async with self._view_lock:
            if self.active_tab != tab:
                self.page = 0
            self.active_tab = tab
            await self._edit_live_message(interaction)

    async def _on_general(self, interaction: discord.Interaction):
        await self._switch_tab(interaction, "general")

    async def _on_fish(self, interaction: discord.Interaction):
        await self._switch_tab(interaction, "fish")

    async def _on_gear(self, interaction: discord.Interaction):
        await self._switch_tab(interaction, "gear")

    async def _on_use_id(self, interaction: discord.Interaction):
        if self.active_tab != "general":
            await interaction.response.send_message("Использование предметов по ID доступно только во вкладке Общее.", ephemeral=True)
            return
        await interaction.response.send_modal(InventoryIdModal(self, "use"))

    async def _on_sell_all(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.active_tab != "fish":
                await interaction.response.send_message("Продажа доступна только во вкладке Рыба.", ephemeral=True)
                return
            if not await safe_defer(interaction):
                return
            _, payload = await self.cog.sell_inventory_fish(self.user_id, self.guild_id, "all")
            await self.refresh(interaction)
            await self._send_payload(interaction, payload)

    async def _on_sell_common(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.active_tab != "fish":
                await interaction.response.send_message("Эта продажа доступна только во вкладке Рыба.", ephemeral=True)
                return
            if not await safe_defer(interaction):
                return
            _, payload = await self.cog.sell_inventory_fish(self.user_id, self.guild_id, "common_uncommon")
            await self.refresh(interaction)
            await self._send_payload(interaction, payload)

    async def _on_sell_id(self, interaction: discord.Interaction):
        if self.active_tab != "fish":
            await interaction.response.send_message("Продажа по ID доступна только во вкладке Рыба.", ephemeral=True)
            return
        await interaction.response.send_modal(InventoryIdModal(self, "sell"))

    async def _on_lock_id(self, interaction: discord.Interaction):
        if self.active_tab != "fish":
            await interaction.response.send_message("Лок по ID доступен только во вкладке Рыба.", ephemeral=True)
            return
        await interaction.response.send_modal(InventoryIdModal(self, "lock"))

    async def _on_rod_select(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.active_tab != "gear":
                await interaction.response.send_message("Смена снаряжения доступна только во вкладке Снаряжение.", ephemeral=True)
                return
            if not await safe_defer(interaction):
                return
            selected = self._selected_value(interaction, self.rod_select)
            if not selected or ":" not in selected:
                await interaction.followup.send("Не удалось прочитать выбранную удочку. Попробуй ещё раз.", ephemeral=True)
                return
            action, key = selected.split(":", 1)
            if action != "rod":
                await interaction.followup.send("Не удалось определить выбранную удочку. Попробуй ещё раз.", ephemeral=True)
                return
            _, payload = await self.cog.choose_fishing_rod(self.user_id, self.guild_id, key)
            await self.refresh(interaction)
            await self._send_payload(interaction, payload)

    async def _on_tackle_select(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.active_tab != "gear":
                await interaction.response.send_message("Смена снасти доступна только во вкладке Снаряжение.", ephemeral=True)
                return
            if not await safe_defer(interaction):
                return
            tackle_key = self._selected_value(interaction, self.tackle_select)
            if tackle_key is None:
                await interaction.followup.send("Не удалось прочитать выбранную снасть. Попробуй ещё раз.", ephemeral=True)
                return
            _, payload = await self.cog.choose_tackle(self.user_id, self.guild_id, tackle_key)
            await self.refresh(interaction)
            await self._send_payload(interaction, payload)

    async def _on_bait_select(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.active_tab != "gear":
                await interaction.response.send_message("Смена наживки доступна только во вкладке Снаряжение.", ephemeral=True)
                return
            if not await safe_defer(interaction):
                return
            bait_key = self._selected_value(interaction, self.bait_select)
            if bait_key is None:
                await interaction.followup.send("Не удалось прочитать выбранную наживку. Попробуй ещё раз.", ephemeral=True)
                return
            _, payload = await self.cog.choose_bait(self.user_id, self.guild_id, None if bait_key == "none" else bait_key)
            await self.refresh(interaction)
            await self._send_payload(interaction, payload)

    async def _on_zone_select(self, interaction: discord.Interaction):
        async with self._view_lock:
            if self.active_tab != "gear":
                await interaction.response.send_message("Смена спота доступна только во вкладке Снаряжение.", ephemeral=True)
                return
            if not await safe_defer(interaction):
                return
            zone_key = self._selected_value(interaction, self.zone_select)
            if zone_key is None:
                await interaction.followup.send("Не удалось прочитать выбранный спот. Попробуй ещё раз.", ephemeral=True)
                return
            _, payload = await self.cog.choose_fishing_zone(self.user_id, self.guild_id, zone_key)
            await self.refresh(interaction)
            await self._send_payload(interaction, payload)

    async def _on_prev(self, interaction: discord.Interaction):
        async with self._view_lock:
            self.page = max(0, self.page - 1)
            await self._edit_live_message(interaction)

    async def _on_refresh(self, interaction: discord.Interaction):
        async with self._view_lock:
            await self._edit_live_message(interaction)

    async def _on_next(self, interaction: discord.Interaction):
        async with self._view_lock:
            self.page += 1
            await self._edit_live_message(interaction)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(FishingCog(bot))
