import asyncio
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from config import SUPABASE_KEY, SUPABASE_URL
from inventory_system import ensure_inventory_state
from progression import extract_weekly_snapshot

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

user_locks: Dict[int, asyncio.Lock] = {}
active_commands = set()

HOUSE_NET_WORTH = {
    "studio": 80_000,
    "flat_one": 220_000,
    "flat_two": 520_000,
    "townhouse": 1_250_000,
    "country_house": 3_200_000,
    "penthouse": 7_500_000,
}

GPU_NET_WORTH = {
    "gtx_1060": 42_000,
    "rtx_2060": 112_000,
    "rtx_3060_ti": 245_000,
    "rtx_4080": 590_000,
    "rtx_5090": 1_380_000,
}

FURNITURE_NET_WORTH = {
    "gaming_chair": 120_000,
    "aquarium": 260_000,
    "plasma_tv": 410_000,
}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _gpu_entry_id(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("gpu_id", entry.get("id")) or "")
    return str(entry or "")


def _house_basement_upgrade_spend(house_id: str | None, basement_level: int) -> int:
    base_price = HOUSE_NET_WORTH.get(str(house_id or ""))
    if not base_price or basement_level <= 1:
        return 0
    total = 0
    for current_level in range(1, basement_level):
        total += max(35_000, int(base_price * (0.18 + current_level * 0.08)))
    return total


def _business_upgrade_spend(cost: int, upgrade_level: int) -> int:
    total = 0
    for previous_level in range(max(0, upgrade_level)):
        total += int(cost * 0.6 * (previous_level + 1))
    return total


def _house_net_worth(game_stats: Any) -> dict[str, int]:
    systems = game_stats.get("_systems") if isinstance(game_stats, dict) else None
    house = systems.get("house") if isinstance(systems, dict) else None
    if not isinstance(house, dict):
        return {
            "house_value": 0,
            "basement_value": 0,
            "gpu_value": 0,
            "furniture_value": 0,
        }

    house_id = str(house.get("owned_house_id") or "")
    basement_level = _safe_int(house.get("basement_level"), 0)
    installed_gpus = house.get("installed_gpus", [])
    furniture = house.get("furniture", [])

    house_value = HOUSE_NET_WORTH.get(house_id, 0)
    basement_value = _house_basement_upgrade_spend(house_id, basement_level)
    gpu_value = sum(
        GPU_NET_WORTH.get(_gpu_entry_id(gpu_entry), 0)
        for gpu_entry in installed_gpus
        if _gpu_entry_id(gpu_entry)
    )

    furniture_value = 0
    for item in furniture if isinstance(furniture, list) else []:
        if isinstance(item, dict):
            furniture_value += _safe_int(item.get("price"), 0)
        else:
            furniture_value += FURNITURE_NET_WORTH.get(str(item), 0)

    return {
        "house_value": house_value,
        "basement_value": basement_value,
        "gpu_value": gpu_value,
        "furniture_value": furniture_value,
    }


def _business_net_worth(raw_businesses: Any) -> dict[str, int]:
    from config import BUSINESSES

    if not isinstance(raw_businesses, dict):
        return {"business_value": 0, "business_upgrade_value": 0}

    purchase_value = 0
    upgrade_value = 0

    for raw_business_id, raw_entries in raw_businesses.items():
        try:
            business_id = int(raw_business_id)
        except (TypeError, ValueError):
            continue

        business = BUSINESSES.get(business_id)
        if business is None:
            continue

        entries = raw_entries if isinstance(raw_entries, list) else [raw_entries]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            purchase_value += _safe_int(business.get("cost"), 0)
            upgrade_value += _business_upgrade_spend(_safe_int(business.get("cost"), 0), _safe_int(entry.get("upgrade_level"), 0))

    return {"business_value": purchase_value, "business_upgrade_value": upgrade_value}


def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in user_locks:
        user_locks[user_id] = asyncio.Lock()
    return user_locks[user_id]


class Database:
    USER_FIELDS = {
        "user_id",
        "guild_id",
        "balance",
        "gems",
        "bank",
        "deposit_amount",
        "deposit_rate",
        "deposit_start",
        "deposit_days",
        "total_won",
        "total_lost",
        "games_played",
        "level",
        "xp",
        "inventory",
        "game_stats",
        "win_streak",
        "best_streak",
        "total_wagered",
        "vip_level",
        "achievements",
        "last_game",
        "last_bet",
        "daily_streak",
        "last_hourly",
        "last_daily",
        "last_work",
        "last_crime",
        "last_slut",
        "last_wheel",
        "last_fish",
        "last_mine",
        "last_steal",
        "last_daily_reset",
        "last_weekly_reset",
        "businesses",
        "business_autocollect",
        "quest_progress",
        "daily_quests",
        "weekly_quests",
        "buff_xp_until",
        "buff_money_until",
        "temp_vip_until",
        "shield_until",
        "fishing_rod",
    }

    USER_DEFAULTS = {
        "inventory": {
            "fish_items": [],
            "general_items": [],
            "next_item_id": 1,
        },
        "game_stats": {},
        "win_streak": 0,
        "best_streak": 0,
        "total_wagered": 0,
        "vip_level": 0,
        "last_game": None,
        "last_bet": 0,
        "daily_streak": 0,
        "level": 1,
        "last_hourly": None,
        "last_daily": None,
        "last_work": None,
        "last_crime": None,
        "last_slut": None,
        "last_wheel": None,
        "last_fish": None,
        "last_mine": None,
        "last_steal": None,
        "last_daily_reset": None,
        "last_weekly_reset": None,
        "businesses": {},
        "business_autocollect": {
            "owned": False,
            "enabled": False,
            "interval_hours": 6,
            "last_run": None,
            "total_collected": 0,
            "total_cycles": 0,
        },
        "quest_progress": {},
        "daily_quests": [],
        "weekly_quests": [],
        "achievements": [],
        "buff_xp_until": None,
        "buff_money_until": None,
        "temp_vip_until": None,
        "fishing_rod": "none",
        "shield_until": None,
    }

    NEW_USER_TEMPLATE = {
        "balance": 1000,
        "gems": 10,
        "bank": 0,
        "deposit_amount": 0,
        "deposit_rate": 0,
        "deposit_start": None,
        "deposit_days": 0,
        "total_won": 0,
        "total_lost": 0,
        "games_played": 0,
        "level": 1,
        "xp": 0,
        "inventory": {
            "fish_items": [],
            "general_items": [],
            "next_item_id": 1,
        },
        "game_stats": {},
        "win_streak": 0,
        "best_streak": 0,
        "total_wagered": 0,
        "vip_level": 0,
        "achievements": [],
        "last_game": None,
        "last_bet": 0,
        "daily_streak": 0,
        "last_hourly": None,
        "last_daily": None,
        "last_work": None,
        "last_crime": None,
        "last_slut": None,
        "last_wheel": None,
        "last_fish": None,
        "last_mine": None,
        "last_steal": None,
        "last_daily_reset": None,
        "last_weekly_reset": None,
        "businesses": {},
        "business_autocollect": {
            "owned": False,
            "enabled": False,
            "interval_hours": 6,
            "last_run": None,
            "total_collected": 0,
            "total_cycles": 0,
        },
        "quest_progress": {},
        "daily_quests": [],
        "weekly_quests": [],
        "buff_xp_until": None,
        "buff_money_until": None,
        "temp_vip_until": None,
        "fishing_rod": "none",
        "shield_until": None,
    }

    UNSUPPORTED_USER_FIELDS: set[str] = set()
    DISABLED_SYNC_FEATURES: Dict[str, str] = {}
    WARNED_KEYS: set[str] = set()
    SYNC_BACKOFF_UNTIL: Dict[str, datetime] = {}

    @classmethod
    def _warn_once(cls, key: str, message: str):
        if key in cls.WARNED_KEYS:
            return
        cls.WARNED_KEYS.add(key)
        print(message)

    @classmethod
    def _mark_user_field_unsupported(cls, field: str):
        cls.UNSUPPORTED_USER_FIELDS.add(field)
        cls._warn_once(
            f"user-field:{field}",
            f"Users column '{field}' is missing in Supabase. The related feature is disabled until the column is added.",
        )

    @classmethod
    def user_field_supported(cls, field: str) -> bool:
        return field in cls.USER_FIELDS and field not in cls.UNSUPPORTED_USER_FIELDS

    @classmethod
    def _disable_sync_feature(cls, feature: str, reason: str):
        cls.DISABLED_SYNC_FEATURES[feature] = reason
        cls._warn_once(f"sync-feature:{feature}", reason)

    @classmethod
    def sync_feature_enabled(cls, feature: str) -> bool:
        return feature not in cls.DISABLED_SYNC_FEATURES

    @classmethod
    def _sync_backoff_active(cls, feature: str) -> bool:
        until = cls.SYNC_BACKOFF_UNTIL.get(feature)
        if until is None:
            return False
        if datetime.now(timezone.utc) >= until:
            cls.SYNC_BACKOFF_UNTIL.pop(feature, None)
            return False
        return True

    @classmethod
    def _set_sync_backoff(cls, feature: str, seconds: int, message: str):
        until = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(seconds)))
        previous = cls.SYNC_BACKOFF_UNTIL.get(feature)
        if previous is not None and previous >= until:
            return
        cls.SYNC_BACKOFF_UNTIL[feature] = until
        print(message)

    @staticmethod
    def _is_transient_sync_error(error_msg: str) -> bool:
        lowered = error_msg.lower()
        transient_markers = (
            "json could not be generated",
            "bad gateway",
            "server disconnected",
            "connectionterminated",
            "connectionstate.closed",
            "streaminputs.send_headers",
            "connectioninputs.recv_data",
            "invalid input streaminputs.send_headers",
            "invalid input connectioninputs.recv_data",
        )
        return any(marker in lowered for marker in transient_markers)

    @staticmethod
    def _filter_user_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: value
            for key, value in payload.items()
            if key in Database.USER_FIELDS and key not in Database.UNSUPPORTED_USER_FIELDS
        }

    @staticmethod
    async def _safe_user_insert(payload: Dict[str, Any]):
        filtered = Database._filter_user_payload(payload)
        if not filtered:
            return None

        try:
            result = await asyncio.to_thread(lambda: supabase.table("users").insert(filtered).execute())
            return result.data[0] if result.data else None
        except Exception as insert_error:
            error_msg = str(insert_error)

            if "Could not find" in error_msg and "in the schema cache" in error_msg:
                match = re.search(r"'([^']+)' column", error_msg)
                if match:
                    problem_column = match.group(1)
                    Database._mark_user_field_unsupported(problem_column)
                    if problem_column in filtered:
                        filtered.pop(problem_column, None)
                        if filtered:
                            result = await asyncio.to_thread(lambda: supabase.table("users").insert(filtered).execute())
                            return result.data[0] if result.data else None
                        return None
            print(f"Database insert error: {error_msg}")
            return None

    @staticmethod
    async def _safe_user_update(user_id: int, guild_id: int, payload: Dict[str, Any]) -> bool:
        filtered = Database._filter_user_payload(payload)
        if not filtered:
            return True

        try:
            await asyncio.to_thread(
                lambda: supabase.table("users").update(filtered).eq("user_id", user_id).eq("guild_id", guild_id).execute()
            )
            return True
        except Exception as update_error:
            error_msg = str(update_error)

            if "Could not find" in error_msg and "in the schema cache" in error_msg:
                match = re.search(r"'([^']+)' column", error_msg)
                if match:
                    problem_column = match.group(1)
                    Database._mark_user_field_unsupported(problem_column)
                    if problem_column in filtered:
                        filtered.pop(problem_column, None)
                        if filtered:
                            await asyncio.to_thread(
                                lambda: supabase.table("users")
                                .update(filtered)
                                .eq("user_id", user_id)
                                .eq("guild_id", guild_id)
                                .execute()
                            )
                        return True
            print(f"Database update error: {error_msg}")
            return False

    @staticmethod
    async def get_user(user_id: int, guild_id: int) -> Dict[str, Any] | None:
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("users").select("*").eq("user_id", user_id).eq("guild_id", guild_id).execute()
            )
            if result.data:
                user_data = result.data[0]
                updates = {}
                original_inventory = deepcopy(user_data.get("inventory"))
                original_game_stats = deepcopy(user_data.get("game_stats"))
                for field, default_value in Database.USER_DEFAULTS.items():
                    if field not in user_data or user_data[field] is None:
                        user_data[field] = default_value
                        if Database.user_field_supported(field):
                            updates[field] = default_value

                normalized_inventory = ensure_inventory_state(user_data)
                if Database.user_field_supported("inventory") and original_inventory != normalized_inventory:
                    updates["inventory"] = normalized_inventory
                if user_data.get("game_stats") != original_game_stats:
                    updates["game_stats"] = user_data.get("game_stats", {})

                if updates:
                    await Database.update_user(user_id, guild_id, updates)
                return user_data

            new_user = {
                "user_id": user_id,
                "guild_id": guild_id,
                **Database.NEW_USER_TEMPLATE,
            }
            created = await Database._safe_user_insert(new_user)
            await Database.sync_global_leaderboard(user_id)
            return created or new_user
        except Exception as exc:
            print(f"Database error: {exc}")
            return None

    @staticmethod
    async def get_slots_jackpot(guild_id: int) -> int:
        try:
            result = await asyncio.to_thread(lambda: supabase.table("slots_jackpot").select("amount").eq("guild_id", guild_id).execute())
            if result.data:
                return int(result.data[0]["amount"])

            await asyncio.to_thread(lambda: supabase.table("slots_jackpot").insert({"guild_id": guild_id, "amount": 10000}).execute())
            return 10000
        except Exception:
            return 10000

    @staticmethod
    async def update_slots_jackpot(guild_id: int, amount: int):
        try:
            await asyncio.to_thread(
                lambda: supabase.table("slots_jackpot").update({"amount": amount}).eq("guild_id", guild_id).execute()
            )
        except Exception:
            pass

    @staticmethod
    async def update_user(user_id: int, guild_id: int, data: Dict[str, Any]):
        try:
            success = await Database._safe_user_update(user_id, guild_id, data)
            if success:
                game_stats = data.get("game_stats")
                if isinstance(game_stats, dict):
                    await Database.sync_house_state(user_id, guild_id, game_stats)
                    await Database.sync_battle_pass_state(user_id, guild_id, game_stats)
                await Database.sync_global_leaderboard(user_id)
        except Exception as exc:
            print(f"Update error: {exc}")

    @staticmethod
    async def sync_house_state(user_id: int, guild_id: int, game_stats: Dict[str, Any]) -> bool:
        if not Database.sync_feature_enabled("house_states_write"):
            return False

        systems = game_stats.get("_systems")
        if not isinstance(systems, dict):
            return False

        house = systems.get("house")
        if not isinstance(house, dict):
            return False

        base_payload = {
            "user_id": user_id,
            "guild_id": guild_id,
            "owned_house_id": house.get("owned_house_id"),
            "basement_level": int(house.get("basement_level", 0) or 0),
            "installed_gpus": house.get("installed_gpus", []),
            "last_mining_collect": house.get("last_mining_collect"),
            "mining_wallet": int(house.get("mining_wallet", 0) or 0),
            "active_rentals": house.get("active_rentals", []),
            "accepted_offers": house.get("accepted_offers", {"window": None, "keys": []}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        extended_payload = {
            **base_payload,
            "garden": house.get("garden", {}),
            "max_garden_level": int(house.get("max_garden_level", 0) or 0),
            "crypto_wallet": house.get("crypto_wallet", {}),
            "furniture": house.get("furniture", []),
            "legacy_mining_wallet": int(house.get("legacy_mining_wallet", 0) or 0),
        }

        try:
            await asyncio.to_thread(
                lambda: supabase.table("house_states").upsert(extended_payload, on_conflict="user_id,guild_id").execute()
            )
            return True
        except Exception as exc:
            error_msg = str(exc)
            lowered = error_msg.lower()
            if any(
                marker in lowered
                for marker in (
                    "garden",
                    "max_garden_level",
                    "crypto_wallet",
                    "furniture",
                    "legacy_mining_wallet",
                )
            ):
                try:
                    await asyncio.to_thread(
                        lambda: supabase.table("house_states").upsert(base_payload, on_conflict="user_id,guild_id").execute()
                    )
                    return True
                except Exception as fallback_exc:
                    exc = fallback_exc
                    error_msg = str(fallback_exc)
                    lowered = error_msg.lower()
            if "42p01" in lowered or "does not exist" in lowered or "schema cache" in lowered:
                Database._disable_sync_feature(
                    "house_states_write",
                    "House state sync is disabled for this runtime because public.house_states is not available yet.",
                )
            elif "42501" in lowered or "row-level security" in lowered:
                Database._disable_sync_feature(
                    "house_states_write",
                    "House state sync is disabled for this runtime because Supabase RLS blocks writes to public.house_states.",
                )
            else:
                print(f"House state sync error: {exc}")
            return False

    @staticmethod
    async def get_easter_guild_state(guild_id: int) -> Dict[str, Any]:
        if not Database.sync_feature_enabled("easter_guild_states_access"):
            return {"guild_id": guild_id}

        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("easter_guild_states").select("*").eq("guild_id", guild_id).limit(1).execute()
            )
            if result.data:
                return result.data[0]
            return {"guild_id": guild_id}
        except Exception as exc:
            error_msg = str(exc).lower()
            if "42p01" in error_msg or "does not exist" in error_msg or "schema cache" in error_msg:
                Database._disable_sync_feature(
                    "easter_guild_states_access",
                    "Easter guild state sync is disabled for this runtime because public.easter_guild_states is not available yet.",
                )
            elif "42501" in error_msg or "row-level security" in error_msg:
                Database._disable_sync_feature(
                    "easter_guild_states_access",
                    "Easter guild state sync is disabled for this runtime because Supabase RLS blocks access to public.easter_guild_states.",
                )
            else:
                print(f"Easter guild state fetch error: {exc}")
            return {"guild_id": guild_id}

    @staticmethod
    async def upsert_easter_guild_state(guild_id: int, payload: Dict[str, Any]) -> bool:
        if not Database.sync_feature_enabled("easter_guild_states_access"):
            return False

        data = {
            "guild_id": guild_id,
            "phase": payload.get("phase"),
            "active_rabbit_event_id": payload.get("active_rabbit_event_id"),
            "rabbit_active_until": payload.get("rabbit_active_until"),
            "rabbit_last_spawn_at": payload.get("rabbit_last_spawn_at"),
            "rabbit_last_announce_message_id": payload.get("rabbit_last_announce_message_id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await asyncio.to_thread(
                lambda: supabase.table("easter_guild_states").upsert(data, on_conflict="guild_id").execute()
            )
            return True
        except Exception as exc:
            error_msg = str(exc).lower()
            if "42p01" in error_msg or "does not exist" in error_msg or "schema cache" in error_msg:
                Database._disable_sync_feature(
                    "easter_guild_states_access",
                    "Easter guild state sync is disabled for this runtime because public.easter_guild_states is not available yet.",
                )
            elif "42501" in error_msg or "row-level security" in error_msg:
                Database._disable_sync_feature(
                    "easter_guild_states_access",
                    "Easter guild state sync is disabled for this runtime because Supabase RLS blocks access to public.easter_guild_states.",
                )
            else:
                print(f"Easter guild state upsert error: {exc}")
            return False

    @staticmethod
    async def get_market_guild_state(guild_id: int) -> Dict[str, Any]:
        if not Database.sync_feature_enabled("market_guild_states_access"):
            return {"guild_id": guild_id}

        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("market_guild_states").select("*").eq("guild_id", guild_id).limit(1).execute()
            )
            if result.data:
                return result.data[0]
            return {"guild_id": guild_id}
        except Exception as exc:
            error_msg = str(exc).lower()
            if "42p01" in error_msg or "does not exist" in error_msg or "schema cache" in error_msg:
                Database._disable_sync_feature(
                    "market_guild_states_access",
                    "Market guild state sync is disabled for this runtime because public.market_guild_states is not available yet.",
                )
            elif "42501" in error_msg or "row-level security" in error_msg:
                Database._disable_sync_feature(
                    "market_guild_states_access",
                    "Market guild state sync is disabled for this runtime because Supabase RLS blocks access to public.market_guild_states.",
                )
            else:
                print(f"Market guild state fetch error: {exc}")
            return {"guild_id": guild_id}

    @staticmethod
    async def upsert_market_guild_state(guild_id: int, payload: Dict[str, Any]) -> bool:
        if not Database.sync_feature_enabled("market_guild_states_access"):
            return False

        data = {
            "guild_id": guild_id,
            "active_event": payload.get("active_event"),
            "next_event_after": payload.get("next_event_after"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await asyncio.to_thread(
                lambda: supabase.table("market_guild_states").upsert(data, on_conflict="guild_id").execute()
            )
            return True
        except Exception as exc:
            error_msg = str(exc).lower()
            if "42p01" in error_msg or "does not exist" in error_msg or "schema cache" in error_msg:
                Database._disable_sync_feature(
                    "market_guild_states_access",
                    "Market guild state sync is disabled for this runtime because public.market_guild_states is not available yet.",
                )
            elif "42501" in error_msg or "row-level security" in error_msg:
                Database._disable_sync_feature(
                    "market_guild_states_access",
                    "Market guild state sync is disabled for this runtime because Supabase RLS blocks access to public.market_guild_states.",
                )
            else:
                print(f"Market guild state upsert error: {exc}")
            return False

    @staticmethod
    async def sync_battle_pass_state(user_id: int, guild_id: int, game_stats: Dict[str, Any]) -> bool:
        if not Database.sync_feature_enabled("battle_pass_states_write"):
            return False

        progression = game_stats.get("_progression")
        if not isinstance(progression, dict):
            return False

        battle_pass = progression.get("battle_pass")
        if not isinstance(battle_pass, dict):
            return False

        payload = {
            "user_id": user_id,
            "guild_id": guild_id,
            "season_id": str(battle_pass.get("season_id") or ""),
            "premium_unlocked": bool(battle_pass.get("premium_unlocked")),
            "xp": int(battle_pass.get("xp", 0) or 0),
            "claimed_free": battle_pass.get("claimed_free", []),
            "claimed_premium": battle_pass.get("claimed_premium", []),
            "daily_day": battle_pass.get("daily_day"),
            "daily_missions": battle_pass.get("daily_missions", []),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if not payload["season_id"]:
            return False

        try:
            await asyncio.to_thread(
                lambda: supabase.table("battle_pass_states").upsert(payload, on_conflict="user_id,guild_id,season_id").execute()
            )
            return True
        except Exception as exc:
            error_msg = str(exc)
            lowered = error_msg.lower()
            if "42p01" in lowered or "does not exist" in lowered or "schema cache" in lowered:
                Database._disable_sync_feature(
                    "battle_pass_states_write",
                    "Battle pass sync is disabled for this runtime because public.battle_pass_states is not available yet.",
                )
            elif "42501" in lowered or "row-level security" in lowered:
                Database._disable_sync_feature(
                    "battle_pass_states_write",
                    "Battle pass sync is disabled for this runtime because Supabase RLS blocks writes to public.battle_pass_states.",
                )
            else:
                print(f"Battle pass sync error: {exc}")
            return False

    @staticmethod
    async def sync_server_businesses(user_id: int, guild_id: int, businesses: Dict[str, List[Dict[str, Any]]]) -> bool:
        if not Database.sync_feature_enabled("server_businesses_write"):
            return False

        try:
            rows_by_business: Dict[str, Dict[str, Any]] = {}
            for raw_business_id, entries in businesses.items():
                business_id = str(raw_business_id)
                if not isinstance(entries, list):
                    continue

                last_collected: str | None = None
                instance_count = 0
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    instance_count += 1
                    collected_at = entry.get("last_collect") or entry.get("last_collected")
                    if collected_at and (last_collected is None or str(collected_at) > str(last_collected)):
                        last_collected = str(collected_at)

                if instance_count <= 0:
                    continue
                rows_by_business[business_id] = {
                    "guild_id": guild_id,
                    "owner_id": user_id,
                    "business_id": business_id,
                    "last_collected": last_collected,
                }

            rows = list(rows_by_business.values())
            if rows:
                await asyncio.to_thread(
                    lambda: supabase.table("server_businesses").upsert(rows, on_conflict="guild_id,business_id").execute()
                )
            else:
                await asyncio.to_thread(
                    lambda: supabase.table("server_businesses").delete().eq("guild_id", guild_id).eq("owner_id", user_id).execute()
                )

            return True
        except Exception as exc:
            error_msg = str(exc)
            if "42501" in error_msg or "row-level security" in error_msg.lower():
                Database._disable_sync_feature(
                    "server_businesses_write",
                    "Server businesses sync is disabled for this runtime because Supabase RLS blocks writes to public.server_businesses.",
                )
            else:
                print(f"Server businesses sync error: {exc}")
            return False

    @staticmethod
    async def sync_global_leaderboard(user_id: int, username: str | None = None) -> bool:
        if not Database.sync_feature_enabled("global_leaderboard_write"):
            return False
        if Database._sync_backoff_active("global_leaderboard_write"):
            return False

        try:
            users_result = await asyncio.to_thread(
                lambda: supabase.table("users").select("*").eq("user_id", user_id).execute()
            )
            user_rows = users_result.data or []
            if not user_rows:
                return False

            existing_result = await asyncio.to_thread(
                lambda: supabase.table("global_leaderboard").select("username").eq("user_id", user_id).limit(1).execute()
            )
            existing_username = None
            if existing_result.data:
                existing_username = existing_result.data[0].get("username")

            total_balance = 0
            gems_balance = 0
            vip_level = 0
            total_games_played = 0
            total_wins = 0
            fishing_caught = 0
            mining_blocks = 0
            businesses_owned = 0
            clan_id = None

            from utils import count_owned_businesses

            for row in user_rows:
                total_balance += int(row.get("balance", 0) or 0)
                total_balance += int(row.get("bank", 0) or 0)
                total_balance += int(row.get("deposit_amount", 0) or 0)
                gems_balance += int(row.get("gems", 0) or 0)
                vip_level = max(vip_level, int(row.get("vip_level", 0) or 0))
                total_games_played += int(row.get("games_played", 0) or 0)
                businesses_owned += count_owned_businesses(row.get("businesses", {}))
                clan_id = clan_id or row.get("clan_id")

                game_stats = row.get("game_stats") or {}
                if isinstance(game_stats, dict):
                    for stats in game_stats.values():
                        if isinstance(stats, dict):
                            total_wins += int(stats.get("won", 0) or 0)
                    systems = game_stats.get("_systems") or {}
                    if isinstance(systems, dict):
                        fishing = systems.get("fishing") or {}
                        if isinstance(fishing, dict):
                            fishing_caught += int(fishing.get("total_catches", 0) or 0)
                        house = systems.get("house") or {}
                        if isinstance(house, dict):
                            mining_blocks += int(house.get("mining_runs", 0) or 0)

            payload = {
                "user_id": user_id,
                "username": (username or existing_username or f"User {user_id}")[:255],
                "total_balance": total_balance,
                "gems_balance": gems_balance,
                "vip_level": vip_level,
                "total_games_played": total_games_played,
                "total_wins": total_wins,
                "fishing_caught": fishing_caught,
                "mining_blocks": mining_blocks,
                "businesses_owned": businesses_owned,
                "clan_id": clan_id,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

            await asyncio.to_thread(
                lambda: supabase.table("global_leaderboard").upsert(payload, on_conflict="user_id").execute()
            )
            return True
        except Exception as exc:
            error_msg = str(exc)
            if "42501" in error_msg or "row-level security" in error_msg.lower():
                Database._disable_sync_feature(
                    "global_leaderboard_write",
                    "Global leaderboard sync is disabled for this runtime because Supabase RLS blocks writes to public.global_leaderboard.",
                )
            elif Database._is_transient_sync_error(error_msg):
                Database._set_sync_backoff(
                    "global_leaderboard_write",
                    60,
                    f"Global leaderboard sync paused for 60s after transient Supabase error: {exc}",
                )
            else:
                print(f"Global leaderboard sync error: {exc}")
            return False

    @staticmethod
    async def sync_all_global_leaderboard() -> int:
        try:
            result = await asyncio.to_thread(lambda: supabase.table("users").select("user_id").execute())
            unique_user_ids = sorted({int(row["user_id"]) for row in (result.data or []) if row.get("user_id") is not None})
            synced = 0
            for user_id in unique_user_ids:
                if await Database.sync_global_leaderboard(user_id):
                    synced += 1
            return synced
        except Exception as exc:
            print(f"Global leaderboard backfill error: {exc}")
            return 0

    @staticmethod
    async def get_top_net_worth(limit: int = 10) -> List[Dict[str, Any]]:
        try:
            users_result = await asyncio.to_thread(lambda: supabase.table("users").select("*").execute())
            user_rows = users_result.data or []
        except Exception as exc:
            print(f"Top net worth fetch error: {exc}")
            return []

        username_map: Dict[int, str] = {}
        try:
            names_result = await asyncio.to_thread(
                lambda: supabase.table("global_leaderboard").select("user_id, username").execute()
            )
            for row in names_result.data or []:
                raw_user_id = row.get("user_id")
                if raw_user_id is None:
                    continue
                username = str(row.get("username") or "").strip()
                if username:
                    username_map[int(raw_user_id)] = username
        except Exception:
            pass

        aggregated: Dict[int, Dict[str, Any]] = {}
        for row in user_rows:
            raw_user_id = row.get("user_id")
            if raw_user_id is None:
                continue

            user_id = int(raw_user_id)
            entry = aggregated.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "username": username_map.get(user_id, str(row.get("username") or f"User {user_id}")),
                    "net_worth": 0,
                    "balance_value": 0,
                    "house_value": 0,
                    "basement_value": 0,
                    "gpu_value": 0,
                    "furniture_value": 0,
                    "business_value": 0,
                    "business_upgrade_value": 0,
                },
            )

            liquid_value = (
                int(row.get("balance", 0) or 0)
                + int(row.get("bank", 0) or 0)
                + int(row.get("deposit_amount", 0) or 0)
            )
            house_values = _house_net_worth(row.get("game_stats"))
            business_values = _business_net_worth(row.get("businesses"))
            row_total = liquid_value + sum(house_values.values()) + sum(business_values.values())

            entry["balance_value"] += liquid_value
            entry["house_value"] += house_values["house_value"]
            entry["basement_value"] += house_values["basement_value"]
            entry["gpu_value"] += house_values["gpu_value"]
            entry["furniture_value"] += house_values["furniture_value"]
            entry["business_value"] += business_values["business_value"]
            entry["business_upgrade_value"] += business_values["business_upgrade_value"]
            entry["net_worth"] += row_total

            if user_id in username_map:
                entry["username"] = username_map[user_id]

        entries = sorted(aggregated.values(), key=lambda item: int(item.get("net_worth", 0) or 0), reverse=True)
        for index, entry in enumerate(entries[: max(1, limit)], start=1):
            entry["rank"] = index
        return entries[: max(1, limit)]

    @staticmethod
    def _build_live_leaderboard_entries(
        user_rows: List[Dict[str, Any]],
        metric: str,
        limit: int,
        scope: str = "all",
    ) -> List[Dict[str, Any]]:
        from utils import count_owned_businesses

        aggregated: Dict[int, Dict[str, Any]] = {}
        for row in user_rows:
            raw_user_id = row.get("user_id")
            if raw_user_id is None:
                continue

            user_id = int(raw_user_id)
            entry = aggregated.setdefault(
                user_id,
                {
                    "user_id": user_id,
                    "username": str(row.get("username") or f"User {user_id}"),
                    "total_balance": 0,
                    "gems_balance": 0,
                    "vip_level": 0,
                    "total_games_played": 0,
                    "total_wins": 0,
                    "businesses_owned": 0,
                    "weekly_money": 0,
                    "weekly_gems": 0,
                    "weekly_games": 0,
                    "weekly_wins": 0,
                    "weekly_businesses": 0,
                },
            )

            entry["total_balance"] += int(row.get("balance", 0) or 0)
            entry["total_balance"] += int(row.get("bank", 0) or 0)
            entry["total_balance"] += int(row.get("deposit_amount", 0) or 0)
            entry["gems_balance"] += int(row.get("gems", 0) or 0)
            entry["vip_level"] = max(entry["vip_level"], int(row.get("vip_level", 0) or 0))
            entry["total_games_played"] += int(row.get("games_played", 0) or 0)
            entry["businesses_owned"] += count_owned_businesses(row.get("businesses", {}))

            game_stats = row.get("game_stats") or {}
            if isinstance(game_stats, dict):
                for stats in game_stats.values():
                    if isinstance(stats, dict):
                        entry["total_wins"] += int(stats.get("won", 0) or 0)

            weekly = extract_weekly_snapshot(row)
            entry["weekly_money"] += int(weekly.get("money_earned", 0) or 0)
            entry["weekly_gems"] += int(weekly.get("gems_earned", 0) or 0)
            entry["weekly_games"] += int(weekly.get("games_played", 0) or 0)
            entry["weekly_wins"] += int(weekly.get("games_won", 0) or 0)
            entry["weekly_businesses"] += int(weekly.get("business_cycles", 0) or 0)

        rows = list(aggregated.values())

        if scope == "weekly":
            if metric == "gems":
                rows.sort(key=lambda row: (int(row["weekly_gems"]), int(row["weekly_money"])), reverse=True)
            elif metric == "businesses":
                rows.sort(key=lambda row: (int(row["weekly_businesses"]), int(row["weekly_money"])), reverse=True)
            elif metric == "games":
                rows.sort(
                    key=lambda row: (
                        int(row["weekly_wins"]),
                        int(row["weekly_games"]),
                        int(row["weekly_money"]),
                    ),
                    reverse=True,
                )
            else:
                rows.sort(key=lambda row: (int(row["weekly_money"]), int(row["weekly_gems"])), reverse=True)
        else:
            if metric == "gems":
                rows.sort(key=lambda row: (int(row["gems_balance"]), int(row["total_balance"])), reverse=True)
            elif metric == "businesses":
                rows.sort(key=lambda row: (int(row["businesses_owned"]), int(row["total_balance"])), reverse=True)
            elif metric == "games":
                rows.sort(
                    key=lambda row: (
                        int(row["total_wins"]),
                        int(row["total_games_played"]),
                        int(row["total_balance"]),
                    ),
                    reverse=True,
                )
            else:
                rows.sort(key=lambda row: (int(row["total_balance"]), int(row["gems_balance"])), reverse=True)

        return [{**row, "rank": index} for index, row in enumerate(rows[:limit], start=1)]

    @staticmethod
    async def _decorate_live_usernames(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        user_ids = [int(entry["user_id"]) for entry in entries if entry.get("user_id") is not None]
        if not user_ids:
            return entries

        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("global_leaderboard").select("user_id, username").in_("user_id", user_ids).execute()
            )
            usernames = {
                int(row["user_id"]): str(row.get("username") or f"User {row['user_id']}")
                for row in (result.data or [])
                if row.get("user_id") is not None
            }
            for entry in entries:
                entry["username"] = usernames.get(int(entry.get("user_id", 0) or 0), entry.get("username"))
        except Exception:
            pass
        return entries

    @staticmethod
    async def _get_live_leaderboard(metric: str, limit: int, scope: str = "all") -> List[Dict[str, Any]]:
        result = await asyncio.to_thread(
            lambda: supabase.table("users")
            .select("user_id, balance, gems, bank, deposit_amount, vip_level, games_played, businesses, game_stats")
            .execute()
        )
        entries = Database._build_live_leaderboard_entries(result.data or [], metric, limit, scope=scope)
        return await Database._decorate_live_usernames(entries)

    @staticmethod
    async def get_leaderboard(metric: str = "money", limit: int = 10, scope: str = "all") -> List[Dict[str, Any]]:
        metric = (metric or "money").lower()
        scope = (scope or "all").lower()

        if scope != "all":
            try:
                return await Database._get_live_leaderboard(metric, limit, scope=scope)
            except Exception as exc:
                print(f"Weekly leaderboard fallback error: {exc}")
                return []

        if not Database.sync_feature_enabled("global_leaderboard_write"):
            try:
                return await Database._get_live_leaderboard(metric, limit, scope=scope)
            except Exception as exc:
                print(f"Live leaderboard fallback error: {exc}")
                return []

        if metric == "money":
            try:
                result = await asyncio.to_thread(
                    lambda: supabase.table("leaderboard_ranked").select("*").order("rank").limit(limit).execute()
                )
                if result.data:
                    return result.data
            except Exception as exc:
                print(f"Leaderboard error: {exc}")

        sort_column = {
            "money": "total_balance",
            "gems": "gems_balance",
            "businesses": "businesses_owned",
            "games": "total_wins",
        }.get(metric, "total_balance")

        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("global_leaderboard")
                .select(
                    "user_id, username, total_balance, gems_balance, vip_level, "
                    "total_games_played, total_wins, businesses_owned"
                )
                .order(sort_column, desc=True)
                .limit(limit)
                .execute()
            )
            rows = result.data or []
            if metric == "games":
                rows = sorted(
                    rows,
                    key=lambda row: (
                        int(row.get("total_wins", 0) or 0),
                        int(row.get("total_games_played", 0) or 0),
                    ),
                    reverse=True,
                )[:limit]

            if rows:
                return [
                    {
                        "rank": index,
                        "user_id": row.get("user_id"),
                        "username": row.get("username"),
                        "total_balance": row.get("total_balance", 0),
                        "gems_balance": row.get("gems_balance", 0),
                        "vip_level": row.get("vip_level", 0),
                        "total_games_played": row.get("total_games_played", 0),
                        "total_wins": row.get("total_wins", 0),
                        "businesses_owned": row.get("businesses_owned", 0),
                    }
                    for index, row in enumerate(rows, start=1)
                ]
        except Exception as exc:
            print(f"Leaderboard fallback error: {exc}")

        try:
            return await Database._get_live_leaderboard(metric, limit, scope=scope)
        except Exception as exc:
            print(f"Live leaderboard fallback error: {exc}")
            return []

    @staticmethod
    async def get_shop_items(guild_id: int) -> List[Dict[str, Any]]:
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("shop_items").select("*").eq("guild_id", guild_id).eq("active", True).execute()
            )
            return result.data or []
        except Exception as exc:
            print(f"Shop error: {exc}")
            return []

    @staticmethod
    async def add_shop_item(guild_id: int, item_data: Dict[str, Any]):
        try:
            existing_items = await asyncio.to_thread(
                lambda: supabase.table("shop_items").select("id").eq("guild_id", guild_id).execute()
            )
            if existing_items.data:
                max_id = max(int(item["id"]) for item in existing_items.data)
                next_id = max(max_id + 1, 10)
            else:
                next_id = 10

            payload = {**item_data, "id": next_id, "guild_id": guild_id, "active": True}
            result = await asyncio.to_thread(lambda: supabase.table("shop_items").insert(payload).execute())
            return result.data[0] if result.data else None
        except Exception as exc:
            print(f"Add shop item error: {exc}")
            return None

    @staticmethod
    async def buy_lottery_ticket(user_id: int, guild_id: int) -> Optional[int]:
        try:
            import random

            ticket_number = random.randint(100000, 999999)
            ticket_data = {"guild_id": guild_id, "user_id": user_id, "ticket_number": ticket_number}
            await asyncio.to_thread(lambda: supabase.table("lottery").insert(ticket_data).execute())

            jackpot = await asyncio.to_thread(
                lambda: supabase.table("lottery_jackpot").select("*").eq("guild_id", guild_id).execute()
            )
            if jackpot.data:
                new_amount = int(jackpot.data[0]["amount"]) + 100
                await asyncio.to_thread(
                    lambda: supabase.table("lottery_jackpot").update({"amount": new_amount}).eq("guild_id", guild_id).execute()
                )
            else:
                await asyncio.to_thread(
                    lambda: supabase.table("lottery_jackpot").insert({"guild_id": guild_id, "amount": 100}).execute()
                )
            return ticket_number
        except Exception as exc:
            print(f"Lottery ticket error: {exc}")
            return None

    @staticmethod
    async def get_lottery_jackpot(guild_id: int) -> int:
        try:
            result = await asyncio.to_thread(
                lambda: supabase.table("lottery_jackpot").select("amount").eq("guild_id", guild_id).execute()
            )
            return int(result.data[0]["amount"]) if result.data else 0
        except Exception:
            return 0

    @staticmethod
    async def draw_lottery(guild_id: int) -> Optional[Dict[str, Any]]:
        try:
            import random

            tickets = await asyncio.to_thread(lambda: supabase.table("lottery").select("*").eq("guild_id", guild_id).execute())
            if not tickets.data:
                return None

            winner_ticket = random.choice(tickets.data)
            jackpot_data = await asyncio.to_thread(
                lambda: supabase.table("lottery_jackpot").select("*").eq("guild_id", guild_id).execute()
            )
            jackpot = int(jackpot_data.data[0]["amount"]) if jackpot_data.data else 0

            await asyncio.to_thread(
                lambda: supabase.table("lottery_jackpot")
                .update(
                    {
                        "amount": 0,
                        "last_draw": datetime.now(timezone.utc).isoformat(),
                        "winner_id": winner_ticket["user_id"],
                    }
                )
                .eq("guild_id", guild_id)
                .execute()
            )
            await asyncio.to_thread(lambda: supabase.table("lottery").delete().eq("guild_id", guild_id).execute())

            return {
                "winner_id": winner_ticket["user_id"],
                "ticket_number": winner_ticket["ticket_number"],
                "jackpot": jackpot,
            }
        except Exception as exc:
            print(f"Lottery draw error: {exc}")
            return None


db = Database()
