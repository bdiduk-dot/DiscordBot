import asyncio
import discord
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from config import (
    BUSINESSES,
    COLORS,
    CRYPTO_TYPES,
    DAILY_QUESTS_POOL,
    EMOJI,
    FISH_RARITIES,
    WEEKLY_QUESTS_POOL,
)
from database import db, get_user_lock
from progression import change_reputation, progress_battle_pass, record_weekly_progress


def get_kyiv_timezone():
    """Return Europe/Kyiv when tzdata is available, otherwise fall back to fixed UTC+2."""
    try:
        return ZoneInfo("Europe/Kyiv")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=2), name="Europe/Kyiv")


KYIV_TZ = get_kyiv_timezone()
DAILY_QUEST_COUNT = 4
WEEKLY_QUEST_COUNT = 7
INACTIVE_MESSAGE_DELETE_DELAY = 120
_MESSAGE_CLEANUP_TASKS: dict[int, asyncio.Task[Any]] = {}
DEFAULT_USER_PREFERENCES: dict[str, Any] = {
    "smart_notifications": True,
    "notify_deposit": True,
    "notify_rent": True,
    "notify_business": True,
    "notify_harvest": True,
    "notify_daily_streak": True,
    "auto_casino_role": True,
}


def _parse_quest_timestamp(raw_value: str | None) -> Optional[datetime]:
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _roll_quests(pool: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    selected = random.sample(pool, min(count, len(pool)))
    return [{**quest, "completed": False} for quest in selected]


def _week_anchor(dt: datetime):
    return (dt - timedelta(days=dt.weekday())).date()


def _ensure_quest_rotation(user: dict[str, Any]) -> None:
    now_kyiv = datetime.now(KYIV_TZ)
    daily_reset = False
    weekly_reset = False

    last_daily_reset = _parse_quest_timestamp(user.get("last_daily_reset"))
    if not user.get("daily_quests") or last_daily_reset is None or last_daily_reset.astimezone(KYIV_TZ).date() != now_kyiv.date():
        user["daily_quests"] = _roll_quests(DAILY_QUESTS_POOL, DAILY_QUEST_COUNT)
        user["last_daily_reset"] = now_kyiv.astimezone(timezone.utc).isoformat()
        daily_reset = True

    last_weekly_reset = _parse_quest_timestamp(user.get("last_weekly_reset"))
    if (
        not user.get("weekly_quests")
        or last_weekly_reset is None
        or _week_anchor(last_weekly_reset.astimezone(KYIV_TZ)) != _week_anchor(now_kyiv)
    ):
        user["weekly_quests"] = _roll_quests(WEEKLY_QUESTS_POOL, WEEKLY_QUEST_COUNT)
        user["last_weekly_reset"] = now_kyiv.astimezone(timezone.utc).isoformat()
        weekly_reset = True

    old_progress = user.get("quest_progress") or {}
    new_progress: dict[str, int] = {}

    for quest in user.get("daily_quests", []):
        quest_id = quest["id"]
        new_progress[quest_id] = 0 if daily_reset else int(old_progress.get(quest_id, 0) or 0)
        quest["completed"] = False if daily_reset else bool(new_progress[quest_id] >= int(quest["target"]) or quest.get("completed"))

    for quest in user.get("weekly_quests", []):
        quest_id = quest["id"]
        new_progress[quest_id] = 0 if weekly_reset else int(old_progress.get(quest_id, 0) or 0)
        quest["completed"] = False if weekly_reset else bool(new_progress[quest_id] >= int(quest["target"]) or quest.get("completed"))

    user["quest_progress"] = new_progress


def normalize_datetime(value: datetime | str | None) -> Optional[datetime]:
    """Normalize datetimes or ISO strings to an aware UTC datetime."""
    if value is None:
        return None

    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def discord_timestamp(value: datetime | str | None, style: str = "R") -> str:
    normalized = normalize_datetime(value)
    if normalized is None:
        return "—"
    return f"<t:{int(normalized.timestamp())}:{style}>"


def format_discord_deadline(value: datetime | str | None) -> str:
    normalized = normalize_datetime(value)
    if normalized is None:
        return "—"
    return discord_timestamp(normalized, "R")


def get_user_preferences(user: Dict[str, Any]) -> Dict[str, Any]:
    game_stats = user.get("game_stats")
    if not isinstance(game_stats, dict):
        game_stats = {}
        user["game_stats"] = game_stats

    systems = game_stats.get("_systems")
    if not isinstance(systems, dict):
        systems = {}
        game_stats["_systems"] = systems

    preferences = systems.get("preferences")
    if not isinstance(preferences, dict):
        preferences = {}
        systems["preferences"] = preferences

    for key, default_value in DEFAULT_USER_PREFERENCES.items():
        preferences.setdefault(key, default_value)
    return preferences


def smart_notifications_enabled(user: Dict[str, Any]) -> bool:
    return bool(get_user_preferences(user).get("smart_notifications", True))


def notification_type_enabled(user: Dict[str, Any], key: str) -> bool:
    return bool(get_user_preferences(user).get(key, True))


def auto_casino_role_enabled(user: Dict[str, Any]) -> bool:
    return bool(get_user_preferences(user).get("auto_casino_role", True))


def _optional_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


async def get_guild_runtime_settings(guild_id: int | None) -> Dict[str, Any]:
    if guild_id is None:
        return {"allowed_channel_id": None, "activity_role_id": None}
    return await db.get_guild_settings(guild_id)


async def resolve_allowed_channel_id(guild: discord.Guild | None, guild_id: int | None) -> int | None:
    settings = await get_guild_runtime_settings(guild_id)
    configured_id = _optional_int(settings.get("allowed_channel_id"))
    if configured_id is not None:
        if guild is None:
            return configured_id
        channel = guild.get_channel(configured_id)
        return configured_id if isinstance(channel, discord.TextChannel) else None
    return None


async def resolve_activity_role_id(guild: discord.Guild | None, guild_id: int | None) -> int | None:
    settings = await get_guild_runtime_settings(guild_id)
    configured_id = _optional_int(settings.get("activity_role_id"))
    if configured_id is not None:
        if guild is None:
            return configured_id
        role = guild.get_role(configured_id)
        return configured_id if role is not None else None
    return None


async def get_preferred_guild_text_channel(bot: discord.Client, guild_id: int | None) -> discord.TextChannel | None:
    if guild_id is None:
        return None

    guild = bot.get_guild(guild_id)
    if guild is None:
        return None

    allowed_channel_id = await resolve_allowed_channel_id(guild, guild_id)
    if allowed_channel_id is not None:
        allowed_channel = guild.get_channel(allowed_channel_id)
        if isinstance(allowed_channel, discord.TextChannel):
            return allowed_channel

    me = guild.me
    if me is None and bot.user is not None:
        me = guild.get_member(bot.user.id)

    if isinstance(guild.system_channel, discord.TextChannel):
        if me is None or guild.system_channel.permissions_for(me).send_messages:
            return guild.system_channel

    for channel in guild.text_channels:
        if me is None or channel.permissions_for(me).send_messages:
            return channel
    return None

def create_embed(title: str, description: str, color: int = COLORS['info']) -> discord.Embed:
    """Создать красивый embed"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    return embed

async def check_channel(interaction: discord.Interaction) -> bool:
    """Fast channel check that doesn't block the interaction on role assignment."""
    allowed_channel_id = await resolve_allowed_channel_id(interaction.guild, interaction.guild_id)
    if allowed_channel_id is not None and interaction.channel_id != allowed_channel_id:
        return False

    try:
        user_data = None
        if interaction.guild_id is not None:
            user_data = await db.get_user(interaction.user.id, interaction.guild_id)
        if interaction.guild:
            activity_role_id = await resolve_activity_role_id(interaction.guild, interaction.guild_id)
            role = interaction.guild.get_role(activity_role_id) if activity_role_id is not None else None
            if (
                role
                and isinstance(interaction.user, discord.Member)
                and role not in interaction.user.roles
                and auto_casino_role_enabled(user_data or {})
            ):
                asyncio.create_task(interaction.user.add_roles(role, reason="Автовыдача роли казино"))
        asyncio.create_task(
            db.sync_global_leaderboard(
                interaction.user.id,
                username=getattr(interaction.user, "display_name", None) or interaction.user.name,
            )
        )
        if interaction.guild_id is not None:
            asyncio.create_task(process_business_autocollect(interaction.user.id, interaction.guild_id, bot=interaction.client))
    except Exception:
        pass

    return True

async def send_wrong_channel_message(interaction: discord.Interaction):
    """Отправить сообщение о неправильном канале."""
    allowed_channel_id = await resolve_allowed_channel_id(interaction.guild, interaction.guild_id)
    description = (
        f"⚠️ Вы можете играть только в:\n<#{allowed_channel_id}>"
        if allowed_channel_id is not None
        else "⚠️ Игровой канал для этого сервера пока не настроен."
    )
    embed = discord.Embed(
        title="❌ НЕПРАВИЛЬНЫЙ КАНАЛ",
        description=description,
        color=COLORS["error"],
    )
    if interaction.response.is_done():
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def safe_defer(interaction: discord.Interaction, *, ephemeral: bool = False, thinking: bool = False) -> bool:
    """Defer an interaction without surfacing 10062 errors to logs."""
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral, thinking=thinking)
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException:
        return False


async def safe_edit_original_response(interaction: discord.Interaction, **kwargs: Any) -> bool:
    """Edit the original interaction response, falling back to the current message when possible."""
    try:
        await interaction.edit_original_response(**kwargs)
        return True
    except discord.NotFound:
        message = interaction.message
        if message is None:
            return False
        try:
            await message.edit(**kwargs)
            return True
        except (discord.NotFound, discord.HTTPException):
            return False
    except discord.HTTPException:
        return False


async def delete_message_after_delay(message: discord.Message | None, delay_seconds: int = INACTIVE_MESSAGE_DELETE_DELAY) -> None:
    if message is None:
        return
    message_id = int(getattr(message, "id", 0) or 0)
    try:
        await asyncio.sleep(max(0, int(delay_seconds)))
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
    except asyncio.CancelledError:
        raise
    finally:
        current_task = _MESSAGE_CLEANUP_TASKS.get(message_id)
        if current_task is asyncio.current_task():
            _MESSAGE_CLEANUP_TASKS.pop(message_id, None)


def schedule_message_cleanup(message: discord.Message | None, delay_seconds: int = INACTIVE_MESSAGE_DELETE_DELAY) -> asyncio.Task | None:
    if message is None:
        return None
    message_id = int(getattr(message, "id", 0) or 0)
    existing_task = _MESSAGE_CLEANUP_TASKS.get(message_id)
    if existing_task is not None and not existing_task.done():
        existing_task.cancel()
    task = asyncio.create_task(delete_message_after_delay(message, delay_seconds=delay_seconds))
    _MESSAGE_CLEANUP_TASKS[message_id] = task
    return task


def has_active_shield(user: Dict[str, Any]) -> bool:
    """Return True if the temporary black-market shield is still active."""
    raw_value = user.get("shield_until")
    if not raw_value:
        return False

    try:
        shield_until = datetime.fromisoformat(raw_value)
    except ValueError:
        return False

    if shield_until.tzinfo is None:
        shield_until = shield_until.replace(tzinfo=timezone.utc)
    else:
        shield_until = shield_until.astimezone(timezone.utc)

    return shield_until > datetime.now(timezone.utc)

async def check_quest_progress(user_id: int, guild_id: int, quest_type: str, amount: int = 1):
    """Проверить прогресс квеста и выдать награды"""
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return None

        if "quest_progress" not in user:
            user["quest_progress"] = {}

        _ensure_quest_rotation(user)
        quest_progress = user["quest_progress"]
        completed_quests = []
    
        for quest in user.get("daily_quests", []):
            if quest.get("type") == quest_type and not quest.get("completed"):
                quest_id = quest["id"]
                current_progress = quest_progress.get(quest_id, 0)
                if quest_type == "streak":
                    current_progress = max(current_progress, amount)
                else:
                    current_progress += amount
                quest_progress[quest_id] = current_progress

                if current_progress >= quest["target"]:
                    quest["completed"] = True
                    user["balance"] += quest.get("reward_money", 0)
                    user["gems"] += quest.get("reward_gems", 0)
                    completed_quests.append(("daily", quest))

        for quest in user.get("weekly_quests", []):
            if quest.get("type") == quest_type and not quest.get("completed"):
                quest_id = quest["id"]
                current_progress = quest_progress.get(quest_id, 0)
                if quest_type == "streak":
                    current_progress = max(current_progress, amount)
                else:
                    current_progress += amount
                quest_progress[quest_id] = current_progress

                if current_progress >= quest["target"]:
                    quest["completed"] = True
                    user["balance"] += quest.get("reward_money", 0)
                    user["gems"] += quest.get("reward_gems", 0)
                    completed_quests.append(("weekly", quest))

        user["quest_progress"] = quest_progress
        await db.update_user(user_id, guild_id, user)

        return completed_quests if completed_quests else None

async def add_xp(user_id: int, guild_id: int, xp: int) -> Optional[str]:
    """Add XP and check for level up"""
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return None

        user['xp'] += xp

        level_up_messages = []
        while user['xp'] >= user['level'] * 100:
            user['xp'] -= user['level'] * 100
            user['level'] += 1
            bonus = user['level'] * 500
            gems = user['level']  # 1 gem per level
            user['balance'] += bonus
            user['gems'] += gems
            level_up_messages.append(f"\n{EMOJI['level']} **Level {user['level']}!** +${bonus:,} • +{gems}💎")

        await db.update_user(
            user_id,
            guild_id,
            {
                "xp": user["xp"],
                "level": user["level"],
                "balance": user["balance"],
                "gems": user["gems"],
            },
        )
        if level_up_messages:
            return ''.join(level_up_messages)
        return None

async def update_game_stats(user_id: int, guild_id: int, game_name: str, won: bool, bet: int, money_earned: int = 0):
    """Update game statistics and give gem rewards for streaks"""
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return

        if 'game_stats' not in user or user['game_stats'] is None:
            user['game_stats'] = {}

        if game_name not in user['game_stats']:
            user['game_stats'][game_name] = {'played': 0, 'won': 0}

        user['game_stats'][game_name]['played'] += 1
        if won:
            user['game_stats'][game_name]['won'] += 1

        if won:
            user['win_streak'] = user.get('win_streak', 0) + 1
            if user['win_streak'] > user.get('best_streak', 0):
                user['best_streak'] = user['win_streak']

            if user['win_streak'] == 5:
                user['gems'] += 5
            elif user['win_streak'] == 10:
                user['gems'] += 15
            elif user['win_streak'] == 25:
                user['gems'] += 50
            elif user['win_streak'] == 50:
                user['gems'] += 100
        else:
            user['win_streak'] = 0

        user['total_wagered'] = user.get('total_wagered', 0) + bet
        user['last_game'] = game_name
        user['last_bet'] = bet

        await db.update_user(
            user_id,
            guild_id,
            {
                "game_stats": user["game_stats"],
                "win_streak": user["win_streak"],
                "best_streak": user["best_streak"],
                "gems": user["gems"],
                "total_wagered": user["total_wagered"],
                "last_game": user["last_game"],
                "last_bet": user["last_bet"],
            },
        )
    await check_quest_progress(user_id, guild_id, 'play', 1)
    await record_player_progress(
        user_id,
        guild_id,
        action="play",
        amount=1,
        money=money_earned,
        games=1,
        wins=1 if won else 0,
    )
    if won:
        await check_quest_progress(user_id, guild_id, 'win', 1)
        await check_quest_progress(user_id, guild_id, 'streak', user.get('win_streak', 0))

def _crypto_seed(crypto_key: str, day_offset: int = 0) -> int:
    target_day = (datetime.now(timezone.utc) + timedelta(days=day_offset)).date()
    key_seed = sum((index + 1) * ord(char) for index, char in enumerate(crypto_key.upper()))
    return target_day.toordinal() * 97 + key_seed * 17


def get_crypto_price(crypto_key: str, user_id: Optional[int] = None, day_offset: int = 0) -> float:
    crypto = CRYPTO_TYPES[crypto_key]
    rng = random.Random(_crypto_seed(crypto_key, day_offset))
    change = rng.uniform(-crypto['volatility'], crypto['volatility'])
    return round(crypto['base_price'] * (1 + change), 2)


def get_crypto_history(crypto_key: str, days: int = 5) -> List[float]:
    history: List[float] = []
    for offset in range(-(days - 1), 1):
        history.append(get_crypto_price(crypto_key, day_offset=offset))
    return history


def get_random_crypto() -> Dict[str, Any]:
    mining_drop_table = {
        'DOGE': {'weight': 28, 'amount_min': 1400.0, 'amount_max': 6200.0},
        'XRP': {'weight': 24, 'amount_min': 260.0, 'amount_max': 1100.0},
        'LTC': {'weight': 20, 'amount_min': 2.0, 'amount_max': 7.5},
        'ETH': {'weight': 17, 'amount_min': 0.055, 'amount_max': 0.18},
        'BTC': {'weight': 11, 'amount_min': 0.003, 'amount_max': 0.011},
    }

    cryptos = [symbol for symbol in CRYPTO_TYPES.keys() if symbol in mining_drop_table]
    weights = [mining_drop_table[symbol]['weight'] for symbol in cryptos]
    crypto_key = random.choices(cryptos, weights=weights)[0]
    crypto_data = CRYPTO_TYPES[crypto_key]
    drop_data = mining_drop_table[crypto_key]
    amount = random.uniform(drop_data['amount_min'], drop_data['amount_max'])
    price = get_crypto_price(crypto_key)
    return {
        'symbol': crypto_key,
        'name': crypto_data['name'],
        'emoji': crypto_data['emoji'],
        'color': crypto_data['color'],
        'amount': round(amount, 8),
        'price': round(price, 2),
        'value': round(amount * price, 2)
    }

def get_crypto_chart(crypto_key: str, hours: int = 12) -> str:
    prices = []
    current_period = int(datetime.now(timezone.utc).timestamp() / 43200)
    for i in range(hours):
        seed_time = current_period - (hours - 1 - i)
        random.seed(seed_time + hash(crypto_key))
        crypto = CRYPTO_TYPES[crypto_key]
        change = random.uniform(-crypto['volatility'], crypto['volatility'])
        price = crypto['base_price'] * (1 + change)
        prices.append(price)
    random.seed()
    
    min_price = min(prices)
    max_price = max(prices)
    range_price = max_price - min_price if max_price != min_price else 1
    normalized = [int((p - min_price) / range_price * 10) for p in prices]
    
    chart_lines = []
    for level in range(10, -1, -1):
        line = ""
        for val in normalized[-12:]:
            if val >= level:
                line += "█"
            else:
                line += " "
        chart_lines.append(line)
    return "\n".join(chart_lines)

def get_random_fish(rod_bonus: float = 1.0):
    chances_mult = {'legendary': rod_bonus, 'epic': min(rod_bonus * 0.8, 2.0), 'rare': min(rod_bonus * 0.5, 1.5), 'uncommon': 1.0, 'common': 1.0}
    new_chances = {}
    total_chance = 0
    for k, v in FISH_RARITIES.items():
        mult = chances_mult.get(k, 1.0)
        new_chances[k] = v['chance'] * mult
        total_chance += new_chances[k]
    
    rand = random.uniform(0, total_chance)
    cumulative = 0
    
    for rarity_key, rarity_data in FISH_RARITIES.items():
        cumulative += new_chances[rarity_key]
        if rand <= cumulative:
            fish_name = random.choice(rarity_data['fish'])
            price = random.randint(rarity_data['price_min'], rarity_data['price_max'])
            return {'name': fish_name, 'rarity': rarity_key, 'rarity_name': rarity_data['name'], 'emoji': rarity_data['emoji'], 'color': rarity_data['color'], 'price': price}
    
    common = FISH_RARITIES['common']
    return {'name': random.choice(common['fish']), 'rarity': 'common', 'rarity_name': common['name'], 'emoji': common['emoji'], 'color': common['color'], 'price': random.randint(common['price_min'], common['price_max'])}

# ============================================================================
# СИСТЕМА ДОСТИЖЕНИЙ
# ============================================================================

def normalize_businesses(raw_businesses: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Normalize saved business data to {business_id: [instances...]}."""
    normalized: Dict[str, List[Dict[str, Any]]] = {}
    if not isinstance(raw_businesses, dict):
        return normalized

    for raw_business_id, raw_entry in raw_businesses.items():
        business_id = str(raw_business_id)
        entries: List[Dict[str, Any]] = []

        if isinstance(raw_entry, list):
            for item in raw_entry:
                if isinstance(item, dict):
                    entries.append(item.copy())
        elif isinstance(raw_entry, dict):
            entries.append(raw_entry.copy())

        if entries:
            normalized[business_id] = entries

    return normalized


def _safe_business_timestamp(value: Any) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.timestamp()


def collapse_business_duplicates(raw_businesses: Any) -> tuple[Dict[str, List[Dict[str, Any]]], int]:
    """Keep only one instance per business type and report how many duplicates were removed."""
    normalized = normalize_businesses(raw_businesses)
    collapsed: Dict[str, List[Dict[str, Any]]] = {}
    removed = 0

    for business_id, entries in normalized.items():
        if not entries:
            continue

        preferred = max(
            entries,
            key=lambda entry: (
                int(entry.get("total_earned", 0) or 0),
                _safe_business_timestamp(entry.get("last_collect") or entry.get("last_collected")),
                -_safe_business_timestamp(entry.get("bought_at")),
            ),
        ).copy()

        if "last_collected" in preferred and "last_collect" not in preferred:
            preferred["last_collect"] = preferred.pop("last_collected")

        collapsed[business_id] = [preferred]
        removed += max(0, len(entries) - 1)

    return collapsed, removed


async def ensure_unique_businesses(
    user_id: int,
    guild_id: int,
    user: Optional[Dict[str, Any]] = None,
    *,
    sync_table: bool = False,
) -> tuple[Optional[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], int]:
    """Normalize business storage to one entry per business type and optionally sync the mirror table."""
    user = user or await db.get_user(user_id, guild_id)
    if not user:
        return None, {}, 0

    normalized = normalize_businesses(user.get("businesses", {}))
    collapsed, removed = collapse_business_duplicates(normalized)
    changed = removed > 0 or normalized != collapsed

    if changed:
        await db.update_user(user_id, guild_id, {"businesses": collapsed})
        user = await db.get_user(user_id, guild_id)
    else:
        user["businesses"] = collapsed

    if sync_table:
        await db.sync_server_businesses(user_id, guild_id, collapsed)

    return user, collapsed, removed


def count_owned_businesses(raw_businesses: Any) -> int:
    """Count owned business types after collapsing legacy duplicates."""
    collapsed, _ = collapse_business_duplicates(raw_businesses)
    return len(collapsed)


def get_business_autocollect_state(user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw_state = user.get("business_autocollect", {}) if isinstance(user, dict) else {}
    if not isinstance(raw_state, dict):
        raw_state = {}

    interval_hours = int(raw_state.get("interval_hours", 6) or 6)
    interval_hours = max(1, min(24, interval_hours))

    return {
        "owned": bool(raw_state.get("owned", False)),
        "enabled": bool(raw_state.get("enabled", False)),
        "interval_hours": interval_hours,
        "last_run": raw_state.get("last_run"),
        "total_collected": int(raw_state.get("total_collected", 0) or 0),
        "total_cycles": int(raw_state.get("total_cycles", 0) or 0),
    }


async def process_business_autocollect(
    user_id: int,
    guild_id: int,
    user: Optional[Dict[str, Any]] = None,
    bot: Any | None = None,
) -> Dict[str, Any]:
    user = user or await db.get_user(user_id, guild_id)
    if not user:
        return {"collected": 0, "cycles": 0, "state": get_business_autocollect_state({})}

    state = get_business_autocollect_state(user)
    if not state["owned"] or not state["enabled"]:
        if user.get("business_autocollect") != state:
            user["business_autocollect"] = state
            await db.update_user(user_id, guild_id, {"business_autocollect": state})
        return {"collected": 0, "cycles": 0, "state": state}

    now = datetime.now(timezone.utc)
    last_run_raw = state.get("last_run")
    if last_run_raw:
        try:
            last_run = datetime.fromisoformat(str(last_run_raw))
        except ValueError:
            last_run = now - timedelta(hours=state["interval_hours"])
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=timezone.utc)
        else:
            last_run = last_run.astimezone(timezone.utc)
        if now - last_run < timedelta(hours=state["interval_hours"]):
            return {"collected": 0, "cycles": 0, "state": state}

    user, normalized_businesses, _ = await ensure_unique_businesses(user_id, guild_id, user=user, sync_table=False)
    if not user:
        return {"collected": 0, "cycles": 0, "state": state}

    total_collected = 0
    total_cycles = 0
    for business_id, instances in normalized_businesses.items():
        business = BUSINESSES.get(int(business_id))
        if business is None:
            continue

        for instance in instances:
            last_collect = instance.get("last_collect") or instance.get("last_collected")
            last_collect_dt = now
            if last_collect:
                try:
                    last_collect_dt = datetime.fromisoformat(str(last_collect))
                except ValueError:
                    last_collect_dt = now
            if last_collect_dt.tzinfo is None:
                last_collect_dt = last_collect_dt.replace(tzinfo=timezone.utc)
            else:
                last_collect_dt = last_collect_dt.astimezone(timezone.utc)

            if now - last_collect_dt >= timedelta(hours=business["time"]):
                total_cycles += 1
                total_collected += int(business["income"])
                instance["last_collect"] = now.isoformat()
                instance["total_earned"] = int(instance.get("total_earned", 0) or 0) + int(business["income"])

    state["last_run"] = now.isoformat()
    if total_collected > 0:
        user["balance"] = int(user.get("balance", 0) or 0) + total_collected
        user["businesses"] = normalized_businesses
        user.setdefault("quest_progress", {})
        user["quest_progress"]["collect_business"] = user["quest_progress"].get("collect_business", 0) + total_cycles
        state["total_collected"] += total_collected
        state["total_cycles"] += total_cycles
        user["business_autocollect"] = state
        await db.update_user(
            user_id,
            guild_id,
            {
                "balance": user["balance"],
                "businesses": normalized_businesses,
                "quest_progress": user["quest_progress"],
                "business_autocollect": state,
            },
        )
        await db.sync_server_businesses(user_id, guild_id, normalized_businesses)
        asyncio.create_task(check_quest_progress(user_id, guild_id, "collect_business", total_cycles))
        asyncio.create_task(check_quest_progress(user_id, guild_id, "earn", total_collected))
        asyncio.create_task(
            record_player_progress(
                user_id,
                guild_id,
                action="collect_business",
                amount=total_cycles,
                money=total_collected,
                business_cycles=total_cycles,
            )
        )
        systems_cog = bot.get_cog("Systems") if bot is not None and hasattr(bot, "get_cog") else None
        if systems_cog is not None:
            asyncio.create_task(systems_cog.progress_contracts(user_id, guild_id, "collect_business", total_cycles))
    else:
        user["business_autocollect"] = state
        await db.update_user(user_id, guild_id, {"business_autocollect": state})

    return {"collected": total_collected, "cycles": total_cycles, "state": state}

ACHIEVEMENTS = {
    'first_win': {
        'name': '🎉 Первая победа',
        'desc': 'Выиграйте первую игру',
        'check': lambda u: u.get('total_won', 0) > 0,
        'reward_money': 500,
        'reward_gems': 5,
        'emoji': '🎉'
    },
    'rich': {
        'name': '💰 Богач',
        'desc': 'Накопите $10,000',
        'check': lambda u: u.get('balance', 0) >= 10000,
        'reward_money': 1000,
        'reward_gems': 10,
        'emoji': '💰'
    },
    'millionaire': {
        'name': '🤑 Миллионер',
        'desc': 'Накопите $1,000,000',
        'check': lambda u: u.get('balance', 0) >= 1000000,
        'reward_money': 50000,
        'reward_gems': 100,
        'emoji': '🤑'
    },
    'gambler': {
        'name': '🎰 Игроман',
        'desc': 'Сыграйте 100 игр',
        'check': lambda u: u.get('games_played', 0) >= 100,
        'reward_money': 2000,
        'reward_gems': 20,
        'emoji': '🎰'
    },
    'veteran': {
        'name': '⚔️ Ветеран',
        'desc': 'Сыграйте 500 игр',
        'check': lambda u: u.get('games_played', 0) >= 500,
        'reward_money': 10000,
        'reward_gems': 50,
        'emoji': '⚔️'
    },
    'lucky_streak': {
        'name': '🍀 Везунчик',
        'desc': 'Выиграйте 10 игр подряд',
        'check': lambda u: u.get('best_streak', 0) >= 10,
        'reward_money': 5000,
        'reward_gems': 25,
        'emoji': '🍀'
    },
    'unstoppable': {
        'name': '🔥 Неудержимый',
        'desc': 'Выиграйте 25 игр подряд',
        'check': lambda u: u.get('best_streak', 0) >= 25,
        'reward_money': 25000,
        'reward_gems': 75,
        'emoji': '🔥'
    },
    'thief': {
        'name': '🦹 Вор',
        'desc': 'Успешно украдите 10 раз',
        'check': lambda u: u.get('game_stats', {}).get('steal', {}).get('won', 0) >= 10,
        'reward_money': 3000,
        'reward_gems': 15,
        'emoji': '🦹'
    },
    'level10': {
        'name': '⭐ Уровень 10',
        'desc': 'Достигните 10 уровня',
        'check': lambda u: u.get('level', 1) >= 10,
        'reward_money': 10000,
        'reward_gems': 30,
        'emoji': '⭐'
    },
    'level25': {
        'name': '🌟 Уровень 25',
        'desc': 'Достигните 25 уровня',
        'check': lambda u: u.get('level', 1) >= 25,
        'reward_money': 50000,
        'reward_gems': 100,
        'emoji': '🌟'
    },
    'high_roller': {
        'name': '💎 Хайроллер',
        'desc': 'Поставьте $100,000 за раз',
        'check': lambda u: u.get('last_bet', 0) >= 100000,
        'reward_money': 15000,
        'reward_gems': 40,
        'emoji': '💎'
    },
    'wagered_million': {
        'name': '📊 Оборот',
        'desc': 'Поставьте $1,000,000 всего',
        'check': lambda u: u.get('total_wagered', 0) >= 1000000,
        'reward_money': 20000,
        'reward_gems': 50,
        'emoji': '📊'
    },
    'gem_collector': {
        'name': '💎 Коллекционер',
        'desc': 'Накопите 500 гемов',
        'check': lambda u: u.get('gems', 0) >= 500,
        'reward_money': 5000,
        'reward_gems': 50,
        'emoji': '💎'
    },
    'business_mogul': {
        'name': '🏢 Магнат',
        'desc': 'Купите 5 бизнесов',
        'check': lambda u: count_owned_businesses(u.get('businesses', {})) >= 5,
        'reward_money': 30000,
        'reward_gems': 60,
        'emoji': '🏢'
    },
    'fisher': {
        'name': '🎣 Рыболов',
        'desc': 'Поймайте 20 рыб',
        'check': lambda u: int((((u.get('game_stats') or {}).get('_systems') or {}).get('fishing') or {}).get('total_catches', 0) or 0) >= 20,
        'reward_money': 3000,
        'reward_gems': 15,
        'emoji': '🎣'
    },
}

async def check_achievements(user_id: int, guild_id: int) -> list:
    """Проверить и выдать новые достижения"""
    user = await db.get_user(user_id, guild_id)
    if not user:
        return []
    
    if 'achievements' not in user or user['achievements'] is None:
        user['achievements'] = []
    
    new_achievements = []
    
    for ach_id, ach_data in ACHIEVEMENTS.items():
        if ach_id not in user['achievements']:
            try:
                if ach_data['check'](user):
                    user['achievements'].append(ach_id)
                    user['balance'] += ach_data['reward_money']
                    user['gems'] += ach_data['reward_gems']
                    new_achievements.append(ach_data)
            except Exception:
                pass
    
    if new_achievements:
        await db.update_user(user_id, guild_id, user)
    
    return new_achievements


async def record_player_progress(
    user_id: int,
    guild_id: int,
    *,
    action: str | None = None,
    amount: int = 1,
    money: int = 0,
    gems: int = 0,
    reputation: int = 0,
    games: int = 0,
    wins: int = 0,
    business_cycles: int = 0,
    crime_runs: int = 0,
):
    async with get_user_lock(user_id):
        user = await db.get_user(user_id, guild_id)
        if not user:
            return {}

        current_reputation = change_reputation(user, reputation) if reputation else 0
        record_weekly_progress(
            user,
            money=money,
            gems=gems,
            games=games,
            wins=wins,
            business_cycles=business_cycles,
            crime_runs=crime_runs,
        )
        completed_missions = progress_battle_pass(
            user,
            action=action,
            amount=amount,
            money=money,
            gems=gems,
        )
        await db.update_user(user_id, guild_id, {"game_stats": user.get("game_stats", {})})
        return {
            "reputation": current_reputation,
            "completed_missions": completed_missions,
        }
