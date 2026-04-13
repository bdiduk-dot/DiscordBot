from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from inventory_system import add_case_item, case_display_name


def _kyiv_timezone():
    try:
        return ZoneInfo("Europe/Kyiv")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=2), name="Europe/Kyiv")


KYIV_TZ = _kyiv_timezone()

SEASON_ID = "spring_2026"
SEASON_NAME = "Весенний сезон 2026"
SEASON_PREMIUM_COST = 100_000
SEASON_MAX_TIERS = 20
SEASON_XP_PER_TIER = 100
DEFAULT_TITLE = "rookie"
DEFAULT_THEME = "classic"

PROFILE_TITLES: dict[str, dict[str, Any]] = {
    "rookie": {"name": "Новичок", "display": ""},
    "neon_runner": {"name": "Неоновый бегун", "display": "< NEON RUNNER >"},
    "shadow_broker": {"name": "Теневой брокер", "display": "{ SHADOW BROKER }"},
    "tideborn": {"name": "Дитя прилива", "display": "~ TIDEBORN ~"},
    "vault_lord": {"name": "Хозяин хранилища", "display": "[[ VAULT LORD ]]"},
    "astral_angler": {"name": "Астральный рыбак", "display": "<< ASTRAL ANGLER >>"},
    "royal_vip": {"name": "Королевский VIP", "display": "[ ROYAL VIP ]"},
    "void_monarch": {"name": "Монарх пустоты", "display": "< VOID MONARCH >"},
    "glitch_master": {"name": "Мастер сбоя", "display": "{ GLITCH MASTER }"},
    "wallet_destroyer": {"name": "Убийца зарплат", "display": "[ WALLET DESTROYER ]"},
    "lord_of_memes": {"name": "Лорд мемов", "display": "< LORD OF MEMES >"},
    "pro_afk": {"name": "Профессиональный АФК", "display": "{ PRO AFK }"},
    "fish_psychic": {"name": "Рыбный телепат", "display": "<< FISH PSYCHIC >>"},
    "panic_investor": {"name": "Паник-инвестор", "display": "[ PANIC INVESTOR ]"},
    "sofa_tycoon": {"name": "Диванный магнат", "display": "< SOFA TYCOON >"},
    "easter_hunter": {"name": "Охотник за яйцами", "display": "{ EASTER HUNTER }"},
    "spring_chronicler": {"name": "Летописец весны", "display": "[ SPRING CHRONICLER ]"},
    "easter_secret_keeper": {"name": "Хранитель пасхальных тайн", "display": "{ EASTER KEEPER }"},
    "spring_archivist": {"name": "Архивариус весны", "display": "<< SPRING ARCHIVIST >>"},
}

PROFILE_THEMES: dict[str, dict[str, Any]] = {
    "classic": {"name": "Классика", "color": 0x3498DB},
    "neon": {
        "name": "Frost",
        "color": 0xCFEAFF,
        "image_url": "https://i.pinimg.com/originals/fa/ae/65/faae656df5906380cdd8323b4b42145a.gif",
    },
    "ember": {
        "name": "Bloom",
        "color": 0xF3A7D6,
        "image_url": "https://i.pinimg.com/originals/28/c4/1f/28c41f4bffc8cb5f711d2474006ca5bb.gif",
    },
    "royal": {
        "name": "Mist",
        "color": 0x9BE3DC,
        "image_url": "https://i.pinimg.com/originals/fc/20/f7/fc20f7d47033b4f56538842a0a350ddd.gif",
    },
    "abyss": {
        "name": "Abyss",
        "color": 0x26305F,
        "image_url": "https://i.pinimg.com/736x/df/75/6f/df756fd3fe216c16dcf4a183e55dc840.jpg",
    },
    "void": {
        "name": "Void",
        "color": 0x2E1A47,
        "image_url": "https://i.pinimg.com/originals/dd/3d/40/dd3d40b02db42630c4952fe1c6b819ba.gif",
    },
    "mint_bunny": {
        "name": "Mint Bunny",
        "color": 0xA8E6CF,
        "image_url": "https://i.pinimg.com/originals/7d/b3/89/7db389786b7754560cb38796784295b4.gif",
    },
    "moon_hare": {
        "name": "Moon Hare",
        "color": 0xC7C3FF,
        "image_url": "https://i.pinimg.com/originals/44/16/b0/4416b0ca2b067c5a4fa5dc1d1cfa17cf.gif",
    },
    "sakura": {
        "name": "Sakura",
        "color": 0xFFB6C1,
        "image_url": "https://i.pinimg.com/736x/e3/d9/a9/e3d9a9830de5dce351cfeeeec52b7b46.jpg",
    },
}

SEASON_FREE_REWARDS: list[dict[str, Any]] = [
    {"type": "money", "amount": 5_000},
    {"type": "gems", "amount": 8},
    {"type": "buff_xp", "hours": 1},
    {"type": "money", "amount": 10_000},
    {"type": "title", "key": "neon_runner"},
    {"type": "case", "case_type": "common", "quantity": 1},
    {"type": "buff_money", "hours": 1},
    {"type": "money", "amount": 15_000},
    {"type": "reputation", "amount": 6},
    {"type": "case", "case_type": "rare", "quantity": 1},
    {"type": "money", "amount": 20_000},
    {"type": "buff_xp", "hours": 2},
    {"type": "title", "key": "tideborn"},
    {"type": "gems", "amount": 20},
    {"type": "case", "case_type": "epic", "quantity": 1},
    {"type": "money", "amount": 30_000},
    {"type": "reputation", "amount": 10},
    {"type": "gems", "amount": 25},
    {"type": "title", "key": "astral_angler"},
    {"type": "case", "case_type": "legendary", "quantity": 1},
]

SEASON_PREMIUM_REWARDS: list[dict[str, Any]] = [
    {"type": "money", "amount": 12_000},
    {"type": "case", "case_type": "common", "quantity": 1},
    {"type": "buff_xp", "hours": 2},
    {"type": "money", "amount": 18_000},
    {"type": "reputation", "amount": 10},
    {"type": "gems", "amount": 24},
    {"type": "buff_money", "hours": 2},
    {"type": "case", "case_type": "rare", "quantity": 1},
    {"type": "money", "amount": 28_000},
    {"type": "gems", "amount": 30},
    {"type": "buff_xp", "hours": 4},
    {"type": "title", "key": "vault_lord"},
    {"type": "money", "amount": 40_000},
    {"type": "case", "case_type": "epic", "quantity": 1},
    {"type": "buff_money", "hours": 4},
    {"type": "reputation", "amount": 14},
    {"type": "money", "amount": 55_000},
    {"type": "title", "key": "glitch_master"},
    {"type": "case", "case_type": "legendary", "quantity": 1},
    {"type": "title", "key": "void_monarch"},
]

SEASON_DAILY_MISSIONS: list[dict[str, Any]] = [
    {
        "code": "work",
        "name": "Рабочие смены",
        "description": "Используй /work {target} раз.",
        "target_range": (2, 4),
        "xp_range": (35, 55),
    },
    {
        "code": "crime",
        "name": "Уличная жара",
        "description": "Используй /crime {target} раз.",
        "target_range": (1, 2),
        "xp_range": (45, 70),
    },
    {
        "code": "fish",
        "name": "Удачный улов",
        "description": "Поймай рыбу {target} раз.",
        "target_range": (2, 5),
        "xp_range": (35, 60),
    },
    {
        "code": "play",
        "name": "Казино-забег",
        "description": "Сыграй в казино {target} раз.",
        "target_range": (3, 6),
        "xp_range": (40, 65),
    },
    {
        "code": "mine",
        "name": "Работа подвала",
        "description": "Собери доход из подвала {target} раз.",
        "target_range": (1, 3),
        "xp_range": (45, 70),
    },
    {
        "code": "collect_business",
        "name": "Сбор портфеля",
        "description": "Собери доход с бизнесов {target} раз.",
        "target_range": (2, 4),
        "xp_range": (40, 65),
    },
    {
        "code": "rent",
        "name": "День арендодателя",
        "description": "Собери аренду {target} раз.",
        "target_range": (1, 3),
        "xp_range": (45, 70),
    },
    {
        "code": "earn",
        "name": "Денежный поток",
        "description": "Заработай ${target:,}.",
        "target_range": (15_000, 45_000),
        "xp_range": (50, 80),
    },
]


def _game_stats(user: dict[str, Any]) -> dict[str, Any]:
    game_stats = user.get("game_stats")
    if not isinstance(game_stats, dict):
        game_stats = {}
        user["game_stats"] = game_stats
    return game_stats


def _progress_state(user: dict[str, Any]) -> dict[str, Any]:
    game_stats = _game_stats(user)
    progress = game_stats.get("_progression")
    if not isinstance(progress, dict):
        progress = {}
        game_stats["_progression"] = progress
    progress.setdefault("reputation", 0)
    return progress


def current_day_key(now: datetime | None = None) -> str:
    now = now or datetime.now(KYIV_TZ)
    return now.astimezone(KYIV_TZ).strftime("%Y-%m-%d")


def current_week_key(now: datetime | None = None) -> str:
    now = now or datetime.now(KYIV_TZ)
    anchor = now.astimezone(KYIV_TZ) - timedelta(days=now.astimezone(KYIV_TZ).weekday())
    return anchor.strftime("%Y-W%W")


def get_profile_state(user: dict[str, Any]) -> dict[str, Any]:
    progress = _progress_state(user)
    profile = progress.get("profile")
    if not isinstance(profile, dict):
        profile = {}
        progress["profile"] = profile

    owned_titles = profile.get("owned_titles")
    if not isinstance(owned_titles, list):
        owned_titles = [DEFAULT_TITLE]
    if DEFAULT_TITLE not in owned_titles:
        owned_titles.insert(0, DEFAULT_TITLE)

    owned_themes = profile.get("owned_themes")
    if not isinstance(owned_themes, list):
        owned_themes = [DEFAULT_THEME]
    if DEFAULT_THEME not in owned_themes:
        owned_themes.insert(0, DEFAULT_THEME)

    profile["owned_titles"] = list(dict.fromkeys(str(item) for item in owned_titles if item in PROFILE_TITLES))
    profile["owned_themes"] = list(dict.fromkeys(str(item) for item in owned_themes if item in PROFILE_THEMES))
    profile.setdefault("active_title", DEFAULT_TITLE)
    profile.setdefault("active_theme", DEFAULT_THEME)
    profile.setdefault("favorite_catch", None)

    if profile["active_title"] not in profile["owned_titles"]:
        profile["active_title"] = DEFAULT_TITLE
    if profile["active_theme"] not in profile["owned_themes"]:
        profile["active_theme"] = DEFAULT_THEME

    return profile


def get_reputation(user: dict[str, Any]) -> int:
    progress = _progress_state(user)
    return int(progress.get("reputation", 0) or 0)


def change_reputation(user: dict[str, Any], delta: int) -> int:
    progress = _progress_state(user)
    current = int(progress.get("reputation", 0) or 0)
    current = max(-100, min(100, current + int(delta)))
    progress["reputation"] = current
    return current


def reputation_label(score: int) -> str:
    if score >= 80:
        return "Легенда"
    if score >= 40:
        return "Связной"
    if score >= 10:
        return "На слуху"
    if score <= -60:
        return "Сожжён"
    if score <= -20:
        return "Подозрительный"
    return "Нейтральный"


def reputation_contract_bonus(score: int) -> float:
    return max(0.0, min(0.35, max(0, score) / 220))


def reputation_crime_bonus(score: int) -> float:
    return max(-0.12, min(0.18, score / 400))


def black_market_discount_multiplier(score: int) -> float:
    bonus = max(0.0, min(0.18, max(0, score) / 500))
    return round(1.0 - bonus, 2)


def legendary_market_roll_chance(score: int) -> float:
    return max(0.08, min(0.32, 0.11 + max(0, score) / 500))


def contract_slots_for_vip(vip_level: int) -> int:
    slots = 3
    if vip_level >= 2:
        slots += 1
    if vip_level >= 4:
        slots += 1
    return slots


def contract_rerolls_for_vip(vip_level: int) -> int:
    rerolls = 1
    if vip_level >= 3:
        rerolls += 1
    return rerolls


def ensure_weekly_state(user: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    progress = _progress_state(user)
    weekly = progress.get("weekly")
    target_week = current_week_key(now)
    if not isinstance(weekly, dict) or weekly.get("week") != target_week:
        weekly = {
            "week": target_week,
            "money_earned": 0,
            "gems_earned": 0,
            "games_played": 0,
            "games_won": 0,
            "business_cycles": 0,
            "crime_runs": 0,
        }
        progress["weekly"] = weekly
    return weekly


def record_weekly_progress(
    user: dict[str, Any],
    *,
    money: int = 0,
    gems: int = 0,
    games: int = 0,
    wins: int = 0,
    business_cycles: int = 0,
    crime_runs: int = 0,
) -> dict[str, Any]:
    weekly = ensure_weekly_state(user)
    weekly["money_earned"] = int(weekly.get("money_earned", 0) or 0) + max(0, int(money))
    weekly["gems_earned"] = int(weekly.get("gems_earned", 0) or 0) + max(0, int(gems))
    weekly["games_played"] = int(weekly.get("games_played", 0) or 0) + max(0, int(games))
    weekly["games_won"] = int(weekly.get("games_won", 0) or 0) + max(0, int(wins))
    weekly["business_cycles"] = int(weekly.get("business_cycles", 0) or 0) + max(0, int(business_cycles))
    weekly["crime_runs"] = int(weekly.get("crime_runs", 0) or 0) + max(0, int(crime_runs))
    return weekly


def extract_weekly_snapshot(row: dict[str, Any], now: datetime | None = None) -> dict[str, int]:
    game_stats = row.get("game_stats")
    if not isinstance(game_stats, dict):
        return {
            "money_earned": 0,
            "gems_earned": 0,
            "games_played": 0,
            "games_won": 0,
            "business_cycles": 0,
            "crime_runs": 0,
        }

    progress = game_stats.get("_progression")
    if not isinstance(progress, dict):
        return {
            "money_earned": 0,
            "gems_earned": 0,
            "games_played": 0,
            "games_won": 0,
            "business_cycles": 0,
            "crime_runs": 0,
        }

    weekly = progress.get("weekly")
    if not isinstance(weekly, dict) or weekly.get("week") != current_week_key(now):
        return {
            "money_earned": 0,
            "gems_earned": 0,
            "games_played": 0,
            "games_won": 0,
            "business_cycles": 0,
            "crime_runs": 0,
        }

    return {
        "money_earned": int(weekly.get("money_earned", 0) or 0),
        "gems_earned": int(weekly.get("gems_earned", 0) or 0),
        "games_played": int(weekly.get("games_played", 0) or 0),
        "games_won": int(weekly.get("games_won", 0) or 0),
        "business_cycles": int(weekly.get("business_cycles", 0) or 0),
        "crime_runs": int(weekly.get("crime_runs", 0) or 0),
    }


def _mission_seed(user_id: int, day_key: str) -> int:
    return sum((index + 1) * ord(char) for index, char in enumerate(f"{user_id}:{day_key}:pass"))


def _generate_daily_missions(user_id: int, day_key: str) -> list[dict[str, Any]]:
    rng = random.Random(_mission_seed(user_id, day_key))
    templates = rng.sample(SEASON_DAILY_MISSIONS, k=min(3, len(SEASON_DAILY_MISSIONS)))
    missions: list[dict[str, Any]] = []
    for index, template in enumerate(templates, start=1):
        target = rng.randint(*template["target_range"])
        xp_reward = rng.randint(*template["xp_range"])
        missions.append(
            {
                "id": f"{template['code']}_{index}",
                "code": template["code"],
                "name": template["name"],
                "description": template["description"].format(target=target),
                "target": target,
                "progress": 0,
                "xp_reward": xp_reward,
                "completed": False,
            }
        )
    return missions


def ensure_battle_pass_state(user: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    progress = _progress_state(user)
    battle_pass = progress.get("battle_pass")
    today = current_day_key(now)
    user_id = int(user.get("user_id", 0) or 0)
    if not isinstance(battle_pass, dict) or battle_pass.get("season_id") != SEASON_ID:
        battle_pass = {
            "season_id": SEASON_ID,
            "premium_unlocked": False,
            "xp": 0,
            "claimed_free": [],
            "claimed_premium": [],
            "daily_day": today,
            "daily_missions": _generate_daily_missions(user_id, today),
        }
        progress["battle_pass"] = battle_pass

    if battle_pass.get("daily_day") != today:
        battle_pass["daily_day"] = today
        battle_pass["daily_missions"] = _generate_daily_missions(user_id, today)

    for key in ("claimed_free", "claimed_premium"):
        values = battle_pass.get(key)
        if not isinstance(values, list):
            battle_pass[key] = []

    battle_pass.setdefault("premium_unlocked", False)
    battle_pass.setdefault("xp", 0)
    return battle_pass


def battle_pass_tier(user: dict[str, Any]) -> int:
    state = ensure_battle_pass_state(user)
    xp = max(0, int(state.get("xp", 0) or 0))
    return min(SEASON_MAX_TIERS, xp // SEASON_XP_PER_TIER)


def battle_pass_progress_to_next(user: dict[str, Any]) -> tuple[int, int]:
    state = ensure_battle_pass_state(user)
    xp = max(0, int(state.get("xp", 0) or 0))
    if xp >= SEASON_MAX_TIERS * SEASON_XP_PER_TIER:
        return SEASON_XP_PER_TIER, SEASON_XP_PER_TIER
    return xp % SEASON_XP_PER_TIER, SEASON_XP_PER_TIER


def unlock_title(user: dict[str, Any], title_key: str) -> bool:
    if title_key not in PROFILE_TITLES:
        return False
    profile = get_profile_state(user)
    owned = set(profile.get("owned_titles", []))
    if title_key in owned:
        return False
    owned.add(title_key)
    profile["owned_titles"] = sorted(owned, key=lambda item: list(PROFILE_TITLES).index(item) if item in PROFILE_TITLES else 999)
    return True


def unlock_theme(user: dict[str, Any], theme_key: str) -> bool:
    if theme_key not in PROFILE_THEMES:
        return False
    profile = get_profile_state(user)
    owned = set(profile.get("owned_themes", []))
    if theme_key in owned:
        return False
    owned.add(theme_key)
    profile["owned_themes"] = sorted(owned, key=lambda item: list(PROFILE_THEMES).index(item) if item in PROFILE_THEMES else 999)
    return True


def set_active_title(user: dict[str, Any], title_key: str) -> bool:
    profile = get_profile_state(user)
    if title_key not in profile.get("owned_titles", []):
        return False
    profile["active_title"] = title_key
    return True


def set_active_theme(user: dict[str, Any], theme_key: str) -> bool:
    profile = get_profile_state(user)
    if theme_key not in profile.get("owned_themes", []):
        return False
    profile["active_theme"] = theme_key
    return True


def set_favorite_catch(user: dict[str, Any], fish_item: dict[str, Any] | None):
    profile = get_profile_state(user)
    if not fish_item:
        profile["favorite_catch"] = None
        return
    profile["favorite_catch"] = {
        "name": str(fish_item.get("name", "Неизвестный улов")),
        "emoji": str(fish_item.get("emoji", "")),
        "rarity": str(fish_item.get("rarity", "common")),
        "rarity_name": str(fish_item.get("rarity_name", "Обычная")),
        "price": int(fish_item.get("price", 0) or 0),
    }


def get_profile_title_text(user: dict[str, Any]) -> str:
    profile = get_profile_state(user)
    title_key = str(profile.get("active_title", DEFAULT_TITLE) or DEFAULT_TITLE)
    if title_key == DEFAULT_TITLE:
        return ""
    return str(PROFILE_TITLES.get(title_key, PROFILE_TITLES[DEFAULT_TITLE]).get("display") or "").strip()


def get_profile_theme_color(user: dict[str, Any], fallback: int) -> int:
    profile = get_profile_state(user)
    theme_key = str(profile.get("active_theme", DEFAULT_THEME) or DEFAULT_THEME)
    return int(PROFILE_THEMES.get(theme_key, PROFILE_THEMES[DEFAULT_THEME])["color"] or fallback)


def get_profile_theme_image(user: dict[str, Any]) -> str | None:
    profile = get_profile_state(user)
    theme_key = str(profile.get("active_theme", DEFAULT_THEME) or DEFAULT_THEME)
    theme = PROFILE_THEMES.get(theme_key, PROFILE_THEMES[DEFAULT_THEME])
    image_url = theme.get("image_url")
    if not image_url:
        return None
    return str(image_url)


def reward_text(reward: dict[str, Any]) -> str:
    reward_type = reward.get("type")
    if reward_type == "money":
        return f"${int(reward['amount']):,}"
    if reward_type == "gems":
        return f"{int(reward['amount'])} гем."
    if reward_type == "buff_xp":
        return f"Буст опыта на {int(reward['hours'])}ч"
    if reward_type == "buff_money":
        return f"Буст денег на {int(reward['hours'])}ч"
    if reward_type == "title":
        title = PROFILE_TITLES.get(str(reward["key"]), {"name": "Титул"})
        return f"Титул: {title['name']}"
    if reward_type == "theme":
        theme = PROFILE_THEMES.get(str(reward["key"]), {"name": "Тема"})
        return f"Тема: {theme['name']}"
    if reward_type == "reputation":
        return f"Репутация +{int(reward['amount'])}"
    if reward_type == "case":
        quantity = max(1, int(reward.get("quantity", 1) or 1))
        return f"{case_display_name(str(reward.get('case_type') or 'common'))} x{quantity}"
    return "Награда"


def _extend_timer(raw_value: str | None, *, hours: int = 0) -> str:
    now = datetime.now(timezone.utc)
    base = now
    if raw_value:
        try:
            parsed = datetime.fromisoformat(str(raw_value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            if parsed > now:
                base = parsed
        except ValueError:
            base = now
    return (base + timedelta(hours=hours)).isoformat()


def apply_season_reward(user: dict[str, Any], reward: dict[str, Any]):
    reward_type = reward.get("type")
    if reward_type == "money":
        user["balance"] = int(user.get("balance", 0) or 0) + int(reward["amount"])
    elif reward_type == "gems":
        user["gems"] = int(user.get("gems", 0) or 0) + int(reward["amount"])
    elif reward_type == "buff_xp":
        user["buff_xp_until"] = _extend_timer(user.get("buff_xp_until"), hours=int(reward["hours"]))
    elif reward_type == "buff_money":
        user["buff_money_until"] = _extend_timer(user.get("buff_money_until"), hours=int(reward["hours"]))
    elif reward_type == "title":
        unlock_title(user, str(reward["key"]))
    elif reward_type == "theme":
        unlock_theme(user, str(reward["key"]))
    elif reward_type == "reputation":
        change_reputation(user, int(reward["amount"]))
    elif reward_type == "case":
        add_case_item(
            user,
            str(reward.get("case_type") or "common"),
            quantity=max(1, int(reward.get("quantity", 1) or 1)),
            source=f"battle_pass:{SEASON_ID}",
        )


def progress_battle_pass(
    user: dict[str, Any],
    *,
    action: str | None = None,
    amount: int = 1,
    money: int = 0,
    gems: int = 0,
) -> list[dict[str, Any]]:
    state = ensure_battle_pass_state(user)
    completed: list[dict[str, Any]] = []

    for mission in state.get("daily_missions", []):
        if mission.get("completed"):
            continue

        code = str(mission.get("code", ""))
        delta = 0
        if code == "earn":
            delta = max(0, int(money))
        elif code == "gems":
            delta = max(0, int(gems))
        elif action and code == action:
            delta = max(0, int(amount))

        if delta <= 0:
            continue

        mission["progress"] = min(int(mission.get("target", 0) or 0), int(mission.get("progress", 0) or 0) + delta)
        if int(mission.get("progress", 0) or 0) >= int(mission.get("target", 0) or 0):
            mission["completed"] = True
            state["xp"] = min(
                SEASON_MAX_TIERS * SEASON_XP_PER_TIER,
                int(state.get("xp", 0) or 0) + int(mission.get("xp_reward", 0) or 0),
            )
            completed.append(mission)

    return completed


def claim_battle_pass_reward(user: dict[str, Any], tier: int, *, premium: bool = False) -> tuple[bool, str | dict[str, Any]]:
    if tier < 1 or tier > SEASON_MAX_TIERS:
        return False, "Такого уровня не существует."

    state = ensure_battle_pass_state(user)
    unlocked_tier = battle_pass_tier(user)
    if unlocked_tier < tier:
        return False, "Этот уровень ещё не открыт."

    claimed_key = "claimed_premium" if premium else "claimed_free"
    claimed_values = {int(value) for value in state.get(claimed_key, []) if str(value).isdigit()}
    if tier in claimed_values:
        return False, "Эта награда уже получена."

    if premium and not bool(state.get("premium_unlocked")):
        return False, "Платная ветка ещё не открыта."

    rewards = SEASON_PREMIUM_REWARDS if premium else SEASON_FREE_REWARDS
    reward = rewards[tier - 1]
    apply_season_reward(user, reward)
    claimed_values.add(tier)
    state[claimed_key] = sorted(claimed_values)
    return True, reward


def buy_premium_pass(user: dict[str, Any]) -> tuple[bool, str]:
    state = ensure_battle_pass_state(user)
    if bool(state.get("premium_unlocked")):
        return False, "Платная ветка уже открыта."
    if int(user.get("balance", 0) or 0) < SEASON_PREMIUM_COST:
        return False, f"Не хватает денег. Нужно ${SEASON_PREMIUM_COST:,}."
    user["balance"] = int(user.get("balance", 0) or 0) - SEASON_PREMIUM_COST
    state["premium_unlocked"] = True
    unlock_title(user, "royal_vip")
    unlock_theme(user, "royal")
    return True, "Платная ветка открыта."
