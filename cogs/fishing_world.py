from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import FISH_RARITIES


try:
    CHISINAU_TZ = ZoneInfo("Europe/Chisinau")
except ZoneInfoNotFoundError:
    CHISINAU_TZ = timezone.utc

TIME_PHASES = {
    "morning": {"name": "Утро"},
    "day": {"name": "День"},
    "evening": {"name": "Вечер"},
    "night": {"name": "Ночь"},
}

WEATHER_TYPES: dict[str, dict[str, Any]] = {
    "clear": {"name": "Ясно", "description": "Ровный клёв без резких бонусов.", "rarity_bonus": {}, "boss_bonus": 1.0, "value_bonus": 1.0, "weight_bonus": 1.0},
    "rain": {"name": "Дождь", "description": "В дождь редкая рыба выходит ближе к поверхности.", "rarity_bonus": {"uncommon": 1.04, "rare": 1.15, "epic": 1.08}, "boss_bonus": 1.0, "value_bonus": 1.02, "weight_bonus": 1.03},
    "fog": {"name": "Туман", "description": "Туман усиливает странный улов и event-пулы.", "rarity_bonus": {"rare": 1.08, "epic": 1.10, "legendary": 1.05}, "boss_bonus": 1.05, "value_bonus": 1.04, "weight_bonus": 1.04},
    "storm": {"name": "Шторм", "description": "Тяжёлый и дорогой улов клюёт лучше.", "rarity_bonus": {"epic": 1.18, "legendary": 1.32}, "boss_bonus": 1.22, "value_bonus": 1.10, "weight_bonus": 1.08},
    "moon_tide": {"name": "Лунный прилив", "description": "Редкое состояние воды для глубины и ночи.", "rarity_bonus": {"rare": 1.06, "epic": 1.16, "legendary": 1.22}, "boss_bonus": 1.15, "value_bonus": 1.08, "weight_bonus": 1.06},
}

FISHING_TACKLES: dict[str, dict[str, Any]] = {
    "starter": {"name": "Базовая снасть", "price": 0, "gems": 0, "rarity_bonus": {}, "chance_bonus": {}, "value_bonus": 1.0, "weight_bonus": 1.0, "boss_bonus": 1.0, "description": "Надёжный старт без бонусов."},
    "spinner": {"name": "Охотничья блесна", "price": 11000, "gems": 0, "rarity_bonus": {"rare": 1.08, "epic": 1.04}, "chance_bonus": {"rare": 1.08, "epic": 1.04}, "value_bonus": 1.05, "weight_bonus": 1.03, "boss_bonus": 1.0, "description": "Лёгкий апгрейд для дорогой рыбы."},
    "titan_line": {"name": "Титановая леска", "price": 42000, "gems": 12, "rarity_bonus": {"rare": 1.12, "epic": 1.10, "legendary": 1.06}, "chance_bonus": {"rare": 1.12, "epic": 1.10, "legendary": 1.06}, "value_bonus": 1.10, "weight_bonus": 1.06, "boss_bonus": 1.05, "description": "Лучше держит тяжёлую рыбу."},
    "abyss_reel": {"name": "Катушка бездны", "price": 125000, "gems": 40, "rarity_bonus": {"epic": 1.16, "legendary": 1.20}, "chance_bonus": {"epic": 1.16, "legendary": 1.20}, "value_bonus": 1.16, "weight_bonus": 1.10, "boss_bonus": 1.10, "description": "Премиум-снасть для глубины и боссов."},
}

FISHING_BAITS: dict[str, dict[str, Any]] = {
    "worms": {"name": "Черви", "price": 1200, "gems": 0, "bundle": 5, "rarity_bonus": {"uncommon": 1.06, "rare": 1.04}, "chance_bonus": {"uncommon": 1.06, "rare": 1.04}, "value_bonus": 1.01, "weight_bonus": 1.01, "description": "Дешёвая наживка без долгого кд."},
    "shrimp": {"name": "Креветка", "price": 5200, "gems": 0, "bundle": 4, "rarity_bonus": {"rare": 1.10, "epic": 1.08}, "chance_bonus": {"rare": 1.10, "epic": 1.08}, "value_bonus": 1.05, "weight_bonus": 1.03, "description": "Средний вариант для дорогой рыбы."},
    "glow": {"name": "Светящаяся приманка", "price": 17500, "gems": 8, "bundle": 3, "rarity_bonus": {"epic": 1.16, "legendary": 1.18}, "chance_bonus": {"epic": 1.16, "legendary": 1.18}, "value_bonus": 1.10, "weight_bonus": 1.06, "description": "Топовая наживка для ночи и событий."},
}

FISHING_ZONES: dict[str, dict[str, Any]] = {
    "river_bank": {"name": "Речной берег", "price": 0, "gems": 0, "tag": "river", "boss_enabled": False, "value_bonus": 1.0, "weight_bonus": 1.0, "chance_bonus": {}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 66.0, "uncommon": 23.0, "rare": 8.5, "epic": 2.1, "legendary": 0.4}, "description": "Стартовая зона со спокойным клёвом."},
    "reed_swamp": {"name": "Тростниковая топь", "price": 18000, "gems": 6, "tag": "swamp", "boss_enabled": False, "value_bonus": 1.05, "weight_bonus": 1.03, "chance_bonus": {"rare": 1.05}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 58.0, "uncommon": 25.0, "rare": 11.0, "epic": 5.0, "legendary": 1.0}, "description": "Болотная зона с туманными окнами."},
    "moon_lake": {"name": "Лунное озеро", "price": 48000, "gems": 15, "tag": "lake", "boss_enabled": True, "value_bonus": 1.10, "weight_bonus": 1.05, "chance_bonus": {"rare": 1.08, "epic": 1.12, "legendary": 1.10}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 51.0, "uncommon": 25.0, "rare": 14.0, "epic": 7.5, "legendary": 2.5}, "description": "Ночной спот с редкими озёрными видами."},
    "storm_coast": {"name": "Штормовой берег", "price": 92000, "gems": 28, "tag": "coast", "boss_enabled": True, "value_bonus": 1.14, "weight_bonus": 1.07, "chance_bonus": {"rare": 1.08, "epic": 1.12, "legendary": 1.12}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 45.0, "uncommon": 26.0, "rare": 16.0, "epic": 9.0, "legendary": 4.0}, "description": "Сильный морской спот под ивенты."},
    "crystal_cove": {"name": "Кристальная бухта", "price": 155000, "gems": 48, "tag": "crystal", "boss_enabled": True, "value_bonus": 1.20, "weight_bonus": 1.10, "chance_bonus": {"rare": 1.10, "epic": 1.14, "legendary": 1.14}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 39.0, "uncommon": 25.0, "rare": 18.0, "epic": 12.0, "legendary": 6.0}, "description": "Дорогой спот для тяжёлой переливчатой рыбы."},
    "abyss_trench": {"name": "Бездна Левиафана", "price": 220000, "gems": 65, "tag": "abyss", "boss_enabled": True, "value_bonus": 1.28, "weight_bonus": 1.14, "chance_bonus": {"rare": 1.10, "epic": 1.15, "legendary": 1.18}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 32.0, "uncommon": 24.0, "rare": 19.0, "epic": 15.0, "legendary": 10.0}, "description": "Самый опасный и прибыльный спот."},
}

TIME_PHASES = {
    "morning": {"name": "Утро"},
    "day": {"name": "День"},
    "evening": {"name": "Вечер"},
    "night": {"name": "Ночь"},
}

WEATHER_TYPES = {
    "clear": {"name": "Ясно", "description": "Ровный клёв без резких бонусов.", "rarity_bonus": {}, "boss_bonus": 1.0, "value_bonus": 1.0, "weight_bonus": 1.0},
    "rain": {"name": "Дождь", "description": "Под дождём редкая рыба подходит ближе к поверхности.", "rarity_bonus": {"uncommon": 1.04, "rare": 1.15, "epic": 1.08}, "boss_bonus": 1.0, "value_bonus": 1.02, "weight_bonus": 1.03},
    "fog": {"name": "Туман", "description": "Туман усиливает странный улов и event-пулы.", "rarity_bonus": {"rare": 1.08, "epic": 1.10, "legendary": 1.05}, "boss_bonus": 1.05, "value_bonus": 1.04, "weight_bonus": 1.04},
    "storm": {"name": "Шторм", "description": "Тяжёлый и дорогой улов клюёт лучше.", "rarity_bonus": {"epic": 1.18, "legendary": 1.32}, "boss_bonus": 1.22, "value_bonus": 1.10, "weight_bonus": 1.08},
    "moon_tide": {"name": "Лунный прилив", "description": "Редкое состояние воды для глубины и ночи.", "rarity_bonus": {"rare": 1.06, "epic": 1.16, "legendary": 1.22}, "boss_bonus": 1.15, "value_bonus": 1.08, "weight_bonus": 1.06},
}

FISHING_TACKLES = {
    "starter": {"name": "Базовая снасть", "price": 0, "gems": 0, "rarity_bonus": {}, "chance_bonus": {}, "value_bonus": 1.0, "weight_bonus": 1.0, "boss_bonus": 1.0, "description": "Надёжный старт без бонусов."},
    "spinner": {"name": "Охотничья блесна", "price": 11000, "gems": 0, "rarity_bonus": {"rare": 1.08, "epic": 1.04}, "chance_bonus": {"rare": 1.08, "epic": 1.04}, "value_bonus": 1.05, "weight_bonus": 1.03, "boss_bonus": 1.0, "description": "Лёгкий апгрейд для дорогой рыбы."},
    "titan_line": {"name": "Титановая леска", "price": 42000, "gems": 12, "rarity_bonus": {"rare": 1.12, "epic": 1.10, "legendary": 1.06}, "chance_bonus": {"rare": 1.12, "epic": 1.10, "legendary": 1.06}, "value_bonus": 1.10, "weight_bonus": 1.06, "boss_bonus": 1.05, "description": "Лучше держит тяжёлую рыбу."},
    "abyss_reel": {"name": "Катушка бездны", "price": 125000, "gems": 40, "rarity_bonus": {"epic": 1.16, "legendary": 1.20}, "chance_bonus": {"epic": 1.16, "legendary": 1.20}, "value_bonus": 1.16, "weight_bonus": 1.10, "boss_bonus": 1.10, "description": "Премиум-снасть для глубины и боссов."},
}

FISHING_BAITS = {
    "worms": {"name": "Черви", "price": 1200, "gems": 0, "bundle": 5, "rarity_bonus": {"uncommon": 1.10, "rare": 1.08}, "chance_bonus": {"uncommon": 1.12, "rare": 1.10}, "value_bonus": 1.03, "weight_bonus": 1.02, "boss_bonus": 1.0, "description": "Дешёвая наживка, но теперь заметно помогает по редкости улова."},
    "shrimp": {"name": "Креветка", "price": 5200, "gems": 0, "bundle": 4, "rarity_bonus": {"rare": 1.16, "epic": 1.12}, "chance_bonus": {"rare": 1.18, "epic": 1.14, "legendary": 1.04}, "value_bonus": 1.08, "weight_bonus": 1.05, "boss_bonus": 1.06, "description": "Сильнее тянет редкую и эпическую рыбу."},
    "glow": {"name": "Светящаяся приманка", "price": 17500, "gems": 8, "bundle": 3, "rarity_bonus": {"rare": 1.10, "epic": 1.24, "legendary": 1.28}, "chance_bonus": {"rare": 1.12, "epic": 1.26, "legendary": 1.34}, "value_bonus": 1.14, "weight_bonus": 1.08, "boss_bonus": 1.14, "description": "Топовая наживка для ночи, ивентов и легендарного улова."},
}

FISHING_ZONES = {
    "river_bank": {"name": "Речной берег", "price": 0, "gems": 0, "tag": "river", "boss_enabled": False, "value_bonus": 1.0, "weight_bonus": 1.0, "chance_bonus": {}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 66.0, "uncommon": 23.0, "rare": 8.5, "epic": 2.1, "legendary": 0.4}, "description": "Стартовая зона со спокойным клёвом."},
    "reed_swamp": {"name": "Тростниковая топь", "price": 18000, "gems": 6, "tag": "swamp", "boss_enabled": False, "value_bonus": 1.05, "weight_bonus": 1.03, "chance_bonus": {"rare": 1.05}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 58.0, "uncommon": 25.0, "rare": 11.0, "epic": 5.0, "legendary": 1.0}, "description": "Болотная зона с туманными окнами и хищным ночным клёвом."},
    "moon_lake": {"name": "Лунное озеро", "price": 48000, "gems": 15, "tag": "lake", "boss_enabled": True, "value_bonus": 1.10, "weight_bonus": 1.05, "chance_bonus": {"rare": 1.08, "epic": 1.12, "legendary": 1.10}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 51.0, "uncommon": 25.0, "rare": 14.0, "epic": 7.5, "legendary": 2.5}, "description": "Ночной спот с редкими озёрными видами и боссами."},
    "storm_coast": {"name": "Штормовой берег", "price": 92000, "gems": 28, "tag": "coast", "boss_enabled": True, "value_bonus": 1.14, "weight_bonus": 1.07, "chance_bonus": {"rare": 1.08, "epic": 1.12, "legendary": 1.12}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 45.0, "uncommon": 26.0, "rare": 16.0, "epic": 9.0, "legendary": 4.0}, "description": "Сильный морской спот под ивенты и тяжёлый улов."},
    "crystal_cove": {"name": "Кристальная бухта", "price": 155000, "gems": 48, "tag": "crystal", "boss_enabled": True, "value_bonus": 1.20, "weight_bonus": 1.10, "chance_bonus": {"rare": 1.10, "epic": 1.14, "legendary": 1.14}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 39.0, "uncommon": 25.0, "rare": 18.0, "epic": 12.0, "legendary": 6.0}, "description": "Дорогой спот для тяжёлой и переливчатой рыбы."},
    "abyss_trench": {"name": "Бездна Левиафана", "price": 220000, "gems": 65, "tag": "abyss", "boss_enabled": True, "value_bonus": 1.28, "weight_bonus": 1.14, "chance_bonus": {"rare": 1.10, "epic": 1.15, "legendary": 1.18}, "legendary_pool": [], "fish_pool": {}, "rarity_weights": {"common": 32.0, "uncommon": 24.0, "rare": 19.0, "epic": 15.0, "legendary": 10.0}, "description": "Самый опасный и самый прибыльный рыболовный спот."},
}

SPECIES: list[dict[str, Any]] = [
    {"id": "roach", "name": "Плотва", "emoji": "🐟", "rarity": "common", "zones": ["river_bank"], "phases": ["morning", "day"], "min_weight_kg": 0.2, "max_weight_kg": 1.0, "price_mult": 0.95},
    {"id": "perch", "name": "Окунь", "emoji": "🐟", "rarity": "common", "zones": ["river_bank", "reed_swamp"], "phases": ["morning", "day", "evening"], "min_weight_kg": 0.3, "max_weight_kg": 1.6, "price_mult": 1.0},
    {"id": "gudgeon", "name": "Пескарь", "emoji": "🐟", "rarity": "common", "zones": ["river_bank"], "phases": ["day"], "min_weight_kg": 0.1, "max_weight_kg": 0.5, "price_mult": 0.9},
    {"id": "bleak", "name": "Уклейка", "emoji": "🐟", "rarity": "common", "zones": ["river_bank"], "phases": ["morning", "day"], "min_weight_kg": 0.1, "max_weight_kg": 0.4, "price_mult": 0.85},
    {"id": "tench", "name": "Линь", "emoji": "🐟", "rarity": "common", "zones": ["reed_swamp"], "phases": ["evening", "night"], "min_weight_kg": 0.4, "max_weight_kg": 2.2, "price_mult": 1.0},
    {"id": "mud_carp", "name": "Топяной карась", "emoji": "🐟", "rarity": "common", "zones": ["reed_swamp"], "phases": ["day", "evening"], "min_weight_kg": 0.3, "max_weight_kg": 1.8, "price_mult": 1.0},
    {"id": "silver_carp", "name": "Серебряный карп", "emoji": "🐠", "rarity": "uncommon", "zones": ["river_bank", "moon_lake"], "phases": ["day", "evening"], "min_weight_kg": 1.0, "max_weight_kg": 5.0, "price_mult": 1.0},
    {"id": "pike", "name": "Щука", "emoji": "🐠", "rarity": "uncommon", "zones": ["river_bank", "reed_swamp"], "phases": ["morning", "evening"], "min_weight_kg": 1.2, "max_weight_kg": 6.5, "price_mult": 1.05},
    {"id": "bream", "name": "Лещ", "emoji": "🐠", "rarity": "uncommon", "zones": ["river_bank", "moon_lake"], "phases": ["day", "evening"], "min_weight_kg": 0.8, "max_weight_kg": 4.0, "price_mult": 1.0},
    {"id": "eel", "name": "Угорь", "emoji": "🐠", "rarity": "uncommon", "zones": ["reed_swamp", "moon_lake"], "phases": ["night"], "min_weight_kg": 0.9, "max_weight_kg": 4.5, "price_mult": 1.08},
    {"id": "amber_koi", "name": "Янтарный кои", "emoji": "🐠", "rarity": "uncommon", "zones": ["moon_lake"], "phases": ["day"], "min_weight_kg": 1.0, "max_weight_kg": 3.2, "price_mult": 1.10},
    {"id": "mackerel", "name": "Королевская скумбрия", "emoji": "🐠", "rarity": "uncommon", "zones": ["storm_coast"], "phases": ["day", "evening"], "min_weight_kg": 1.4, "max_weight_kg": 4.8, "price_mult": 1.10},
    {"id": "reef_snapper", "name": "Рифовый луциан", "emoji": "🐠", "rarity": "uncommon", "zones": ["storm_coast", "crystal_cove"], "phases": ["day"], "min_weight_kg": 1.3, "max_weight_kg": 5.5, "price_mult": 1.14},
    {"id": "crystal_herring", "name": "Кристальная сельдь", "emoji": "🐠", "rarity": "uncommon", "zones": ["crystal_cove"], "phases": ["morning", "day"], "min_weight_kg": 0.7, "max_weight_kg": 2.6, "price_mult": 1.15},
    {"id": "river_zander", "name": "Судак", "emoji": "🐡", "rarity": "rare", "zones": ["river_bank"], "phases": ["evening", "night"], "min_weight_kg": 1.8, "max_weight_kg": 7.0, "price_mult": 1.0},
    {"id": "bog_catfish", "name": "Болотный сом", "emoji": "🐡", "rarity": "rare", "zones": ["reed_swamp"], "phases": ["night"], "min_weight_kg": 3.0, "max_weight_kg": 11.0, "price_mult": 1.05},
    {"id": "moon_trout", "name": "Лунная форель", "emoji": "🐡", "rarity": "rare", "zones": ["moon_lake"], "phases": ["evening", "night"], "min_weight_kg": 1.4, "max_weight_kg": 5.0, "price_mult": 1.12},
    {"id": "glass_eel", "name": "Стеклянный угорь", "emoji": "🐡", "rarity": "rare", "zones": ["moon_lake", "crystal_cove"], "phases": ["night"], "min_weight_kg": 0.9, "max_weight_kg": 3.3, "price_mult": 1.18},
    {"id": "storm_barracuda", "name": "Штормовая барракуда", "emoji": "🐡", "rarity": "rare", "zones": ["storm_coast"], "phases": ["evening", "night"], "min_weight_kg": 2.2, "max_weight_kg": 8.5, "price_mult": 1.16},
    {"id": "prism_tuna", "name": "Призматический тунец", "emoji": "🐡", "rarity": "rare", "zones": ["crystal_cove"], "phases": ["day"], "min_weight_kg": 3.5, "max_weight_kg": 12.0, "price_mult": 1.20},
    {"id": "abyss_ling", "name": "Глубинный налим", "emoji": "🐡", "rarity": "rare", "zones": ["abyss_trench"], "phases": ["night"], "min_weight_kg": 2.0, "max_weight_kg": 9.5, "price_mult": 1.20},
    {"id": "star_ray", "name": "Звёздный скат", "emoji": "🦑", "rarity": "epic", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 4.0, "max_weight_kg": 14.0, "price_mult": 1.10},
    {"id": "night_som", "name": "Сом-полуночник", "emoji": "🦑", "rarity": "epic", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 6.0, "max_weight_kg": 18.0, "price_mult": 1.12},
    {"id": "tempest_marlin", "name": "Штормовой марлин", "emoji": "🦑", "rarity": "epic", "zones": ["storm_coast"], "phases": ["day", "evening"], "min_weight_kg": 8.0, "max_weight_kg": 26.0, "price_mult": 1.16},
    {"id": "reef_hammer", "name": "Рифовая акула", "emoji": "🦑", "rarity": "epic", "zones": ["storm_coast"], "phases": ["evening", "night"], "min_weight_kg": 10.0, "max_weight_kg": 32.0, "price_mult": 1.18},
    {"id": "crystal_manta", "name": "Кристальная манта", "emoji": "🦑", "rarity": "epic", "zones": ["crystal_cove"], "phases": ["evening", "night"], "min_weight_kg": 9.0, "max_weight_kg": 28.0, "price_mult": 1.20},
    {"id": "void_sword", "name": "Клинок бездны", "emoji": "🦑", "rarity": "epic", "zones": ["abyss_trench"], "phases": ["night"], "min_weight_kg": 12.0, "max_weight_kg": 34.0, "price_mult": 1.22},
    {"id": "ghost_whale", "name": "Теневой кит", "emoji": "🐋", "rarity": "legendary", "zones": ["abyss_trench"], "phases": ["night"], "min_weight_kg": 40.0, "max_weight_kg": 120.0, "price_mult": 1.08},
    {"id": "moon_sturgeon", "name": "Призрачный осётр", "emoji": "🐋", "rarity": "legendary", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 12.0, "max_weight_kg": 42.0, "price_mult": 1.06},
    {"id": "prism_whale", "name": "Призматический кит", "emoji": "🐋", "rarity": "legendary", "zones": ["crystal_cove"], "phases": ["evening", "night"], "min_weight_kg": 26.0, "max_weight_kg": 88.0, "price_mult": 1.12},
    {"id": "storm_leviathan", "name": "Штормовой левиафан", "emoji": "🐋", "rarity": "legendary", "zones": ["storm_coast", "abyss_trench"], "phases": ["night"], "min_weight_kg": 30.0, "max_weight_kg": 110.0, "price_mult": 1.14},
    {"id": "rudd", "name": "Краснопёрка", "emoji": "🐟", "rarity": "common", "zones": ["river_bank", "reed_swamp"], "phases": ["morning", "day"], "min_weight_kg": 0.2, "max_weight_kg": 0.9, "price_mult": 0.92},
    {"id": "stone_loach", "name": "Каменный голец", "emoji": "🐟", "rarity": "common", "zones": ["river_bank"], "phases": ["day", "evening"], "min_weight_kg": 0.1, "max_weight_kg": 0.6, "price_mult": 0.90},
    {"id": "willow_crucian", "name": "Ивовый карась", "emoji": "🐟", "rarity": "common", "zones": ["river_bank", "reed_swamp"], "phases": ["evening"], "min_weight_kg": 0.3, "max_weight_kg": 1.7, "price_mult": 0.96},
    {"id": "marsh_loach", "name": "Топяной вьюн", "emoji": "🐟", "rarity": "common", "zones": ["reed_swamp"], "phases": ["morning", "night"], "min_weight_kg": 0.2, "max_weight_kg": 1.1, "price_mult": 0.97},
    {"id": "dawn_fry", "name": "Рассветный малёк", "emoji": "🐟", "rarity": "common", "zones": ["river_bank", "moon_lake"], "phases": ["morning"], "min_weight_kg": 0.1, "max_weight_kg": 0.3, "price_mult": 0.82},
    {"id": "reed_runner", "name": "Тростниковый бегунок", "emoji": "🐟", "rarity": "common", "zones": ["reed_swamp"], "phases": ["day"], "min_weight_kg": 0.2, "max_weight_kg": 0.8, "price_mult": 0.88},
    {"id": "lake_sprat", "name": "Озёрная тюлька", "emoji": "🐟", "rarity": "common", "zones": ["moon_lake"], "phases": ["morning", "day"], "min_weight_kg": 0.1, "max_weight_kg": 0.5, "price_mult": 0.89},
    {"id": "foam_minnow", "name": "Прибойная килька", "emoji": "🐟", "rarity": "common", "zones": ["storm_coast"], "phases": ["day"], "min_weight_kg": 0.2, "max_weight_kg": 0.7, "price_mult": 0.94},
    {"id": "storm_skipper", "name": "Штормовой прыгун", "emoji": "🐟", "rarity": "common", "zones": ["storm_coast"], "phases": ["morning"], "min_weight_kg": 0.3, "max_weight_kg": 1.0, "price_mult": 0.95},
    {"id": "cove_goby", "name": "Бухтовый бычок", "emoji": "🐟", "rarity": "common", "zones": ["crystal_cove"], "phases": ["day", "evening"], "min_weight_kg": 0.3, "max_weight_kg": 1.2, "price_mult": 0.97},
    {"id": "trench_sculpin", "name": "Глубинный бычок", "emoji": "🐟", "rarity": "common", "zones": ["abyss_trench"], "phases": ["evening", "night"], "min_weight_kg": 0.4, "max_weight_kg": 1.5, "price_mult": 0.99},
    {"id": "abyss_lanternfish", "name": "Фонарь бездны", "emoji": "🐟", "rarity": "common", "zones": ["abyss_trench"], "phases": ["morning", "night"], "min_weight_kg": 0.5, "max_weight_kg": 1.9, "price_mult": 1.02},
    {"id": "bronze_barbel", "name": "Бронзовый усач", "emoji": "🐠", "rarity": "uncommon", "zones": ["river_bank", "reed_swamp"], "phases": ["evening", "night"], "min_weight_kg": 1.2, "max_weight_kg": 5.5, "price_mult": 1.04},
    {"id": "dawn_carp", "name": "Зоревой сазан", "emoji": "🐠", "rarity": "uncommon", "zones": ["river_bank", "moon_lake"], "phases": ["morning"], "min_weight_kg": 1.6, "max_weight_kg": 6.0, "price_mult": 1.06},
    {"id": "moon_whitefish", "name": "Лунный сиг", "emoji": "🐠", "rarity": "uncommon", "zones": ["moon_lake"], "phases": ["morning", "day"], "min_weight_kg": 1.1, "max_weight_kg": 4.4, "price_mult": 1.08},
    {"id": "reed_asp", "name": "Тростниковый жерех", "emoji": "🐠", "rarity": "uncommon", "zones": ["reed_swamp", "river_bank"], "phases": ["day", "evening"], "min_weight_kg": 1.5, "max_weight_kg": 5.8, "price_mult": 1.07},
    {"id": "coast_mullet", "name": "Прибрежная кефаль", "emoji": "🐠", "rarity": "uncommon", "zones": ["storm_coast"], "phases": ["day", "evening"], "min_weight_kg": 1.2, "max_weight_kg": 4.9, "price_mult": 1.09},
    {"id": "salt_garfish", "name": "Серебристый сарган", "emoji": "🐠", "rarity": "uncommon", "zones": ["storm_coast"], "phases": ["morning", "day"], "min_weight_kg": 0.9, "max_weight_kg": 3.8, "price_mult": 1.11},
    {"id": "pearl_sardine", "name": "Жемчужная сардина", "emoji": "🐠", "rarity": "uncommon", "zones": ["crystal_cove"], "phases": ["morning", "day"], "min_weight_kg": 0.8, "max_weight_kg": 2.8, "price_mult": 1.12},
    {"id": "crystal_dawnfin", "name": "Кристальный рассветник", "emoji": "🐠", "rarity": "uncommon", "zones": ["crystal_cove"], "phases": ["morning"], "min_weight_kg": 1.0, "max_weight_kg": 3.6, "price_mult": 1.13},
    {"id": "mirror_bream", "name": "Зеркальный лещ", "emoji": "🐠", "rarity": "uncommon", "zones": ["crystal_cove", "moon_lake"], "phases": ["evening"], "min_weight_kg": 1.3, "max_weight_kg": 5.1, "price_mult": 1.10},
    {"id": "trench_pollock", "name": "Бездонная сайда", "emoji": "🐠", "rarity": "uncommon", "zones": ["abyss_trench"], "phases": ["day", "evening"], "min_weight_kg": 1.8, "max_weight_kg": 6.8, "price_mult": 1.13},
    {"id": "dusk_herring", "name": "Сумеречная сельдь", "emoji": "🐠", "rarity": "uncommon", "zones": ["crystal_cove", "storm_coast"], "phases": ["evening"], "min_weight_kg": 0.9, "max_weight_kg": 3.3, "price_mult": 1.11},
    {"id": "king_chub", "name": "Королевский голавль", "emoji": "🐡", "rarity": "rare", "zones": ["river_bank"], "phases": ["day", "evening"], "min_weight_kg": 1.9, "max_weight_kg": 7.6, "price_mult": 1.08},
    {"id": "willow_pike", "name": "Ивовая щука", "emoji": "🐡", "rarity": "rare", "zones": ["reed_swamp"], "phases": ["morning", "night"], "min_weight_kg": 2.2, "max_weight_kg": 8.8, "price_mult": 1.10},
    {"id": "blue_catfish", "name": "Синий сом", "emoji": "🐡", "rarity": "rare", "zones": ["reed_swamp", "abyss_trench"], "phases": ["night"], "min_weight_kg": 3.8, "max_weight_kg": 13.5, "price_mult": 1.14},
    {"id": "lunar_zander", "name": "Лунный судак", "emoji": "🐡", "rarity": "rare", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 1.7, "max_weight_kg": 6.4, "price_mult": 1.13},
    {"id": "crystal_pike", "name": "Хрустальная щука", "emoji": "🐡", "rarity": "rare", "zones": ["crystal_cove"], "phases": ["evening", "night"], "min_weight_kg": 2.1, "max_weight_kg": 8.1, "price_mult": 1.18},
    {"id": "thunder_cod", "name": "Грозовая треска", "emoji": "🐡", "rarity": "rare", "zones": ["storm_coast"], "phases": ["day", "night"], "min_weight_kg": 2.8, "max_weight_kg": 10.5, "price_mult": 1.17},
    {"id": "trench_grouper", "name": "Бездонный групер", "emoji": "🐡", "rarity": "rare", "zones": ["abyss_trench"], "phases": ["evening", "night"], "min_weight_kg": 4.0, "max_weight_kg": 14.8, "price_mult": 1.19},
    {"id": "black_moray", "name": "Чёрная мурена", "emoji": "🐡", "rarity": "rare", "zones": ["abyss_trench"], "phases": ["morning", "day"], "min_weight_kg": 2.6, "max_weight_kg": 9.9, "price_mult": 1.18},
    {"id": "ember_zander", "name": "Угольный судак", "emoji": "🐡", "rarity": "rare", "zones": ["river_bank", "storm_coast"], "phases": ["evening"], "min_weight_kg": 1.9, "max_weight_kg": 7.1, "price_mult": 1.12},
    {"id": "mirror_eel", "name": "Зеркальный угорь", "emoji": "🐡", "rarity": "rare", "zones": ["moon_lake", "crystal_cove"], "phases": ["night"], "min_weight_kg": 1.1, "max_weight_kg": 4.0, "price_mult": 1.16},
    {"id": "black_sturgeon", "name": "Чёрный осётр", "emoji": "🐡", "rarity": "rare", "zones": ["moon_lake", "abyss_trench"], "phases": ["night"], "min_weight_kg": 3.5, "max_weight_kg": 12.5, "price_mult": 1.20},
    {"id": "moon_arowana", "name": "Лунная арована", "emoji": "🦑", "rarity": "epic", "zones": ["moon_lake"], "phases": ["evening", "night"], "min_weight_kg": 5.5, "max_weight_kg": 17.0, "price_mult": 1.14},
    {"id": "swamp_hydra", "name": "Гидра топи", "emoji": "🦑", "rarity": "epic", "zones": ["reed_swamp"], "phases": ["night"], "min_weight_kg": 7.0, "max_weight_kg": 20.0, "price_mult": 1.16},
    {"id": "storm_sailfish", "name": "Парусник шторма", "emoji": "🦑", "rarity": "epic", "zones": ["storm_coast"], "phases": ["day", "evening"], "min_weight_kg": 8.5, "max_weight_kg": 27.5, "price_mult": 1.20},
    {"id": "crystal_dragonet", "name": "Кристальный драконет", "emoji": "🦑", "rarity": "epic", "zones": ["crystal_cove"], "phases": ["day", "evening"], "min_weight_kg": 7.5, "max_weight_kg": 22.0, "price_mult": 1.22},
    {"id": "abyss_goliath", "name": "Голиаф бездны", "emoji": "🦑", "rarity": "epic", "zones": ["abyss_trench"], "phases": ["night"], "min_weight_kg": 14.0, "max_weight_kg": 38.0, "price_mult": 1.24},
    {"id": "river_phantom", "name": "Речной фантом", "emoji": "🦑", "rarity": "epic", "zones": ["river_bank"], "phases": ["evening", "night"], "min_weight_kg": 4.8, "max_weight_kg": 14.5, "price_mult": 1.13},
    {"id": "prism_shark", "name": "Призматическая акула", "emoji": "🦑", "rarity": "epic", "zones": ["crystal_cove"], "phases": ["evening", "night"], "min_weight_kg": 10.0, "max_weight_kg": 29.0, "price_mult": 1.23},
    {"id": "thunder_sting", "name": "Грозовой скат", "emoji": "🦑", "rarity": "epic", "zones": ["storm_coast"], "phases": ["night"], "min_weight_kg": 9.0, "max_weight_kg": 25.0, "price_mult": 1.19},
    {"id": "moon_serpent", "name": "Змей лунного озера", "emoji": "🦑", "rarity": "epic", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 8.0, "max_weight_kg": 24.0, "price_mult": 1.18},
    {"id": "void_halibut", "name": "Палтус пустоты", "emoji": "🦑", "rarity": "epic", "zones": ["abyss_trench"], "phases": ["evening", "night"], "min_weight_kg": 11.0, "max_weight_kg": 33.0, "price_mult": 1.25},
    {"id": "aurora_sturgeon", "name": "Сияющий осётр", "emoji": "🐋", "rarity": "legendary", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 16.0, "max_weight_kg": 55.0, "price_mult": 1.08},
    {"id": "river_colossus", "name": "Речной колосс", "emoji": "🐋", "rarity": "legendary", "zones": ["river_bank"], "phases": ["night"], "min_weight_kg": 18.0, "max_weight_kg": 62.0, "price_mult": 1.05},
    {"id": "bog_behemoth", "name": "Бегемот топи", "emoji": "🐋", "rarity": "legendary", "zones": ["reed_swamp"], "phases": ["night"], "min_weight_kg": 22.0, "max_weight_kg": 70.0, "price_mult": 1.07},
    {"id": "crown_koi", "name": "Коронный кои", "emoji": "🐋", "rarity": "legendary", "zones": ["moon_lake"], "phases": ["evening", "night"], "min_weight_kg": 14.0, "max_weight_kg": 46.0, "price_mult": 1.07},
    {"id": "storm_colossus", "name": "Колосс шторма", "emoji": "🐋", "rarity": "legendary", "zones": ["storm_coast"], "phases": ["night"], "min_weight_kg": 34.0, "max_weight_kg": 118.0, "price_mult": 1.10},
    {"id": "crystal_oracle", "name": "Кристальный оракул", "emoji": "🐋", "rarity": "legendary", "zones": ["crystal_cove"], "phases": ["day", "night"], "min_weight_kg": 22.0, "max_weight_kg": 74.0, "price_mult": 1.13},
    {"id": "abyss_monarch", "name": "Монарх бездны", "emoji": "🐋", "rarity": "legendary", "zones": ["abyss_trench"], "phases": ["night"], "min_weight_kg": 44.0, "max_weight_kg": 132.0, "price_mult": 1.12},
    {"id": "ivory_whale", "name": "Кит-альбинос", "emoji": "🐋", "rarity": "legendary", "zones": ["crystal_cove", "abyss_trench"], "phases": ["evening", "night"], "min_weight_kg": 38.0, "max_weight_kg": 126.0, "price_mult": 1.11},
    {"id": "lunar_leviathan", "name": "Лунный левиафан", "emoji": "🐋", "rarity": "legendary", "zones": ["moon_lake", "abyss_trench"], "phases": ["night"], "min_weight_kg": 36.0, "max_weight_kg": 124.0, "price_mult": 1.14},
    {"id": "sun_dragonfish", "name": "Солнечный дракон", "emoji": "🐋", "rarity": "legendary", "zones": ["storm_coast"], "phases": ["day"], "min_weight_kg": 24.0, "max_weight_kg": 82.0, "price_mult": 1.09},
]

SPECIES.extend(
    [
        {"id": "river_dace", "name": "Елец", "emoji": "🐟", "rarity": "common", "zones": ["river_bank"], "phases": ["morning", "day"], "min_weight_kg": 0.2, "max_weight_kg": 0.8, "price_mult": 0.93},
        {"id": "marsh_goby", "name": "Болотный бычок", "emoji": "🐟", "rarity": "common", "zones": ["reed_swamp"], "phases": ["day", "evening"], "min_weight_kg": 0.2, "max_weight_kg": 0.9, "price_mult": 0.95},
        {"id": "moon_smelt", "name": "Лунная корюшка", "emoji": "🐟", "rarity": "common", "zones": ["moon_lake"], "phases": ["morning", "evening"], "min_weight_kg": 0.2, "max_weight_kg": 0.7, "price_mult": 0.94},
        {"id": "crystal_gourami", "name": "Кристальный гурами", "emoji": "🐟", "rarity": "common", "zones": ["crystal_cove"], "phases": ["day", "evening"], "min_weight_kg": 0.3, "max_weight_kg": 1.1, "price_mult": 0.98},
        {"id": "river_ide", "name": "Язь", "emoji": "🐠", "rarity": "uncommon", "zones": ["river_bank"], "phases": ["day", "evening"], "min_weight_kg": 1.1, "max_weight_kg": 4.8, "price_mult": 1.05},
        {"id": "swamp_rudd", "name": "Болотная краснопёрка", "emoji": "🐠", "rarity": "uncommon", "zones": ["reed_swamp"], "phases": ["morning", "day"], "min_weight_kg": 0.9, "max_weight_kg": 3.4, "price_mult": 1.07},
        {"id": "moon_perch", "name": "Лунный окунь", "emoji": "🐠", "rarity": "uncommon", "zones": ["moon_lake"], "phases": ["evening", "night"], "min_weight_kg": 1.0, "max_weight_kg": 4.2, "price_mult": 1.09},
        {"id": "coast_seabass", "name": "Прибрежный сибас", "emoji": "🐠", "rarity": "uncommon", "zones": ["storm_coast"], "phases": ["day", "evening"], "min_weight_kg": 1.5, "max_weight_kg": 5.6, "price_mult": 1.11},
        {"id": "river_catfish", "name": "Речной сом", "emoji": "🐡", "rarity": "rare", "zones": ["river_bank"], "phases": ["night"], "min_weight_kg": 2.8, "max_weight_kg": 10.8, "price_mult": 1.12},
        {"id": "swamp_gar", "name": "Топяная панцирница", "emoji": "🐡", "rarity": "rare", "zones": ["reed_swamp"], "phases": ["night"], "min_weight_kg": 2.4, "max_weight_kg": 9.4, "price_mult": 1.14},
        {"id": "moon_char", "name": "Лунный голец", "emoji": "🐡", "rarity": "rare", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 1.6, "max_weight_kg": 6.1, "price_mult": 1.15},
        {"id": "crystal_zander", "name": "Кристальный судак", "emoji": "🐡", "rarity": "rare", "zones": ["crystal_cove"], "phases": ["evening", "night"], "min_weight_kg": 2.0, "max_weight_kg": 7.9, "price_mult": 1.18},
        {"id": "river_warlord", "name": "Речной воевода", "emoji": "🦈", "rarity": "epic", "zones": ["river_bank"], "phases": ["night"], "min_weight_kg": 5.0, "max_weight_kg": 15.0, "price_mult": 1.15},
        {"id": "swamp_hammer", "name": "Топяной молот", "emoji": "🦈", "rarity": "epic", "zones": ["reed_swamp"], "phases": ["night"], "min_weight_kg": 7.5, "max_weight_kg": 21.0, "price_mult": 1.18},
        {"id": "coast_mako", "name": "Штормовой мако", "emoji": "🦈", "rarity": "epic", "zones": ["storm_coast"], "phases": ["evening", "night"], "min_weight_kg": 9.0, "max_weight_kg": 28.0, "price_mult": 1.21},
        {"id": "abyss_moonblade", "name": "Лунный клинок бездны", "emoji": "🦈", "rarity": "epic", "zones": ["abyss_trench"], "phases": ["night"], "min_weight_kg": 12.0, "max_weight_kg": 36.0, "price_mult": 1.25},
        {"id": "river_tsar_fish", "name": "Речная царь-рыба", "emoji": "🐋", "rarity": "legendary", "zones": ["river_bank"], "phases": ["night"], "min_weight_kg": 17.0, "max_weight_kg": 60.0, "price_mult": 1.07},
        {"id": "bog_kraken", "name": "Топяной кракен", "emoji": "🐋", "rarity": "legendary", "zones": ["reed_swamp"], "phases": ["night"], "min_weight_kg": 24.0, "max_weight_kg": 76.0, "price_mult": 1.09},
        {"id": "moon_crown_ray", "name": "Луч короны озера", "emoji": "🐋", "rarity": "legendary", "zones": ["moon_lake"], "phases": ["night"], "min_weight_kg": 18.0, "max_weight_kg": 58.0, "price_mult": 1.10},
        {"id": "storm_juggernaut", "name": "Штормовой джаггернаут", "emoji": "🐋", "rarity": "legendary", "zones": ["storm_coast"], "phases": ["night"], "min_weight_kg": 38.0, "max_weight_kg": 122.0, "price_mult": 1.13},
    ]
)

EVENT_SPECIES: list[dict[str, Any]] = [
    {"id": "sun_sardine", "name": "Солнечная сардина", "emoji": "✨", "rarity": "uncommon", "zones": ["storm_coast"], "phases": ["day"], "event_keys": ["sun_flash"], "min_weight_kg": 0.8, "max_weight_kg": 2.0, "price_mult": 1.08},
    {"id": "mist_koi", "name": "Туманный кои", "emoji": "✨", "rarity": "rare", "zones": ["moon_lake", "reed_swamp"], "phases": ["morning", "night"], "event_keys": ["mist_bloom"], "min_weight_kg": 1.4, "max_weight_kg": 4.2, "price_mult": 1.14},
    {"id": "ember_trout", "name": "Искристая форель", "emoji": "✨", "rarity": "rare", "zones": ["river_bank", "storm_coast"], "phases": ["evening"], "event_keys": ["ember_tide"], "min_weight_kg": 1.2, "max_weight_kg": 4.6, "price_mult": 1.16},
    {"id": "lunar_moray", "name": "Лунная мурена", "emoji": "✨", "rarity": "epic", "zones": ["moon_lake", "crystal_cove"], "phases": ["night"], "event_keys": ["moon_hunt"], "min_weight_kg": 5.0, "max_weight_kg": 16.0, "price_mult": 1.20},
    {"id": "crystal_seer", "name": "Прозрачный оракул", "emoji": "✨", "rarity": "epic", "zones": ["crystal_cove"], "phases": ["day", "evening"], "event_keys": ["crystal_echo"], "min_weight_kg": 6.0, "max_weight_kg": 18.0, "price_mult": 1.24},
    {"id": "void_ray", "name": "Луч бездны", "emoji": "✨", "rarity": "legendary", "zones": ["abyss_trench"], "phases": ["night"], "event_keys": ["deep_alarm"], "min_weight_kg": 18.0, "max_weight_kg": 60.0, "price_mult": 1.22},
]

EVENT_SPECIES.extend(
    [
        {"id": "bloom_pikelet", "name": "Туманный щурёнок", "emoji": "✨", "rarity": "uncommon", "zones": ["reed_swamp"], "phases": ["morning", "night"], "event_keys": ["mist_bloom"], "min_weight_kg": 0.9, "max_weight_kg": 2.6, "price_mult": 1.11},
        {"id": "sunflare_mullet", "name": "Солнечная кефаль", "emoji": "✨", "rarity": "rare", "zones": ["storm_coast"], "phases": ["day"], "event_keys": ["sun_flash"], "min_weight_kg": 1.5, "max_weight_kg": 5.1, "price_mult": 1.17},
        {"id": "ember_eel", "name": "Угольный угорь", "emoji": "✨", "rarity": "epic", "zones": ["river_bank", "storm_coast"], "phases": ["evening", "night"], "event_keys": ["ember_tide"], "min_weight_kg": 5.5, "max_weight_kg": 18.0, "price_mult": 1.23},
        {"id": "moon_glass_ray", "name": "Лунный стеклянный скат", "emoji": "✨", "rarity": "legendary", "zones": ["moon_lake", "crystal_cove"], "phases": ["night"], "event_keys": ["moon_hunt", "crystal_echo"], "min_weight_kg": 20.0, "max_weight_kg": 68.0, "price_mult": 1.28},
    ]
)

BOSS_SPECIES: list[dict[str, Any]] = [
    {"id": "moon_queen", "name": "Королева озера", "emoji": "👑", "zones": ["moon_lake"], "event_keys": ["moon_hunt", "mist_bloom"], "min_weight_kg": 40.0, "max_weight_kg": 120.0, "price_mult": 1.35},
    {"id": "tempest_emperor", "name": "Император шторма", "emoji": "👑", "zones": ["storm_coast"], "event_keys": ["ember_tide", "sun_flash"], "min_weight_kg": 55.0, "max_weight_kg": 145.0, "price_mult": 1.38},
    {"id": "crystal_seraph", "name": "Серафим бухты", "emoji": "👑", "zones": ["crystal_cove"], "event_keys": ["crystal_echo", "moon_hunt"], "min_weight_kg": 50.0, "max_weight_kg": 138.0, "price_mult": 1.42},
    {"id": "abyss_tyrant", "name": "Тиран бездны", "emoji": "👑", "zones": ["abyss_trench"], "event_keys": ["deep_alarm"], "min_weight_kg": 80.0, "max_weight_kg": 200.0, "price_mult": 1.50},
]

EVENT_TEMPLATES: list[dict[str, Any]] = [
    {"key": "mist_bloom", "name": "Туманный всплеск", "description": "Туман вытаскивает странную рыбу ближе к поверхности.", "bonus_zone_tags": {"lake", "swamp"}, "rarity_bonus": {"rare": 1.06, "epic": 1.05}, "boss_bonus": 1.02},
    {"key": "sun_flash", "name": "Солнечная вспышка", "description": "Яркое окно активности на прибрежных спотах.", "bonus_zone_tags": {"coast", "river"}, "rarity_bonus": {"uncommon": 1.05, "rare": 1.06}, "boss_bonus": 1.0},
    {"key": "ember_tide", "name": "Угольный прилив", "description": "Вечерний жар поднимает дорогую хищную рыбу.", "bonus_zone_tags": {"coast", "river"}, "rarity_bonus": {"rare": 1.05, "epic": 1.08, "legendary": 1.03}, "boss_bonus": 1.04},
    {"key": "moon_hunt", "name": "Лунная охота", "description": "Ночной охотничий час в лунных и кристальных водах.", "bonus_zone_tags": {"lake", "crystal"}, "rarity_bonus": {"epic": 1.08, "legendary": 1.10}, "boss_bonus": 1.06},
    {"key": "crystal_echo", "name": "Эхо кристалла", "description": "Чистая вода усиливает редкие переливчатые виды.", "bonus_zone_tags": {"crystal"}, "rarity_bonus": {"rare": 1.05, "epic": 1.09, "legendary": 1.06}, "boss_bonus": 1.05},
    {"key": "deep_alarm", "name": "Тревога бездны", "description": "Бездна шевелится: появляется шанс на самую опасную рыбу.", "bonus_zone_tags": {"abyss"}, "rarity_bonus": {"epic": 1.10, "legendary": 1.12}, "boss_bonus": 1.08},
]

FISHING_BAITS.update(
    {
        "worms": {
            "name": "Черви",
            "price": 1200,
            "gems": 0,
            "bundle": 5,
            "luck_mult": 1.02,
            "shop_limit": 8,
            "rotation_weight": 1.0,
            "rarity_bonus": {"uncommon": 1.05, "rare": 1.03},
            "chance_bonus": {"uncommon": 1.05, "rare": 1.03},
            "value_bonus": 1.01,
            "weight_bonus": 1.01,
            "boss_bonus": 1.0,
            "description": "Бюджетная наживка с лёгким бонусом к более стабильному улову.",
        },
        "shrimp": {
            "name": "Креветка",
            "price": 5200,
            "gems": 0,
            "bundle": 4,
            "luck_mult": 1.08,
            "shop_limit": 5,
            "rotation_weight": 0.95,
            "rarity_bonus": {"rare": 1.10, "epic": 1.06},
            "chance_bonus": {"rare": 1.10, "epic": 1.07, "legendary": 1.02},
            "value_bonus": 1.04,
            "weight_bonus": 1.03,
            "boss_bonus": 1.03,
            "description": "Средняя наживка для редкой рыбы без сильного перекоса в топ-дроп.",
        },
        "glow": {
            "name": "Светящаяся приманка",
            "price": 17500,
            "gems": 8,
            "bundle": 3,
            "luck_mult": 1.15,
            "shop_limit": 3,
            "rotation_weight": 0.72,
            "rarity_bonus": {"rare": 1.05, "epic": 1.12, "legendary": 1.11},
            "chance_bonus": {"rare": 1.05, "epic": 1.13, "legendary": 1.12},
            "value_bonus": 1.08,
            "weight_bonus": 1.05,
            "boss_bonus": 1.06,
            "description": "Сильная ночная наживка, но уже без разгона легендарок до нормы.",
        },
        "bread": {
            "name": "Тесто с отрубями",
            "price": 2200,
            "gems": 0,
            "bundle": 5,
            "luck_mult": 1.04,
            "shop_limit": 7,
            "rotation_weight": 0.94,
            "rarity_bonus": {"common": 1.02, "uncommon": 1.06, "rare": 1.03},
            "chance_bonus": {"uncommon": 1.06, "rare": 1.03},
            "value_bonus": 1.02,
            "weight_bonus": 1.01,
            "boss_bonus": 1.0,
            "description": "Стабильная наживка для озёр и спокойных спотов.",
        },
        "beetle": {
            "name": "Жук-бронзовик",
            "price": 4100,
            "gems": 0,
            "bundle": 4,
            "luck_mult": 1.07,
            "shop_limit": 6,
            "rotation_weight": 0.92,
            "rarity_bonus": {"uncommon": 1.07, "rare": 1.07, "epic": 1.02},
            "chance_bonus": {"rare": 1.07, "epic": 1.03},
            "value_bonus": 1.03,
            "weight_bonus": 1.02,
            "boss_bonus": 1.01,
            "description": "Хорошо работает на речной и болотной рыбе.",
        },
        "minnow": {
            "name": "Живец",
            "price": 8400,
            "gems": 0,
            "bundle": 4,
            "luck_mult": 1.10,
            "shop_limit": 4,
            "rotation_weight": 0.88,
            "rarity_bonus": {"rare": 1.12, "epic": 1.07},
            "chance_bonus": {"rare": 1.12, "epic": 1.08, "legendary": 1.03},
            "value_bonus": 1.05,
            "weight_bonus": 1.03,
            "boss_bonus": 1.03,
            "description": "Хищники на такую приманку реагируют заметно чаще.",
        },
        "squid": {
            "name": "Кальмаровая полоска",
            "price": 13000,
            "gems": 4,
            "bundle": 3,
            "luck_mult": 1.13,
            "shop_limit": 4,
            "rotation_weight": 0.82,
            "rarity_bonus": {"rare": 1.08, "epic": 1.11, "legendary": 1.06},
            "chance_bonus": {"rare": 1.09, "epic": 1.12, "legendary": 1.08},
            "value_bonus": 1.07,
            "weight_bonus": 1.04,
            "boss_bonus": 1.05,
            "description": "Морская наживка для тяжёлой и дорогой рыбы.",
        },
        "moon_moth": {
            "name": "Лунный мотылёк",
            "price": 26000,
            "gems": 6,
            "bundle": 3,
            "luck_mult": 1.17,
            "shop_limit": 3,
            "rotation_weight": 0.70,
            "rarity_bonus": {"epic": 1.13, "legendary": 1.14},
            "chance_bonus": {"rare": 1.05, "epic": 1.14, "legendary": 1.15},
            "value_bonus": 1.09,
            "weight_bonus": 1.06,
            "boss_bonus": 1.08,
            "description": "Сильная ночная наживка для элитного клёва без перегрева экономики.",
        },
        "abyss_pearl": {
            "name": "Осколок бездной жемчужины",
            "price": 48000,
            "gems": 12,
            "bundle": 3,
            "luck_mult": 1.21,
            "shop_limit": 2,
            "rotation_weight": 0.55,
            "rarity_bonus": {"epic": 1.15, "legendary": 1.18},
            "chance_bonus": {"rare": 1.06, "epic": 1.16, "legendary": 1.20},
            "value_bonus": 1.11,
            "weight_bonus": 1.07,
            "boss_bonus": 1.10,
            "description": "Лучшая наживка бездны: премиум-буст для дорогой рыбы, но без автофарма легендарок.",
        },
    }
)

_GENERATED_ZONE_PREFIXES = {
    "river_bank": ["Речной", "Ивовый", "Быстрый", "Прибрежный", "Тиховодный", "Каменный", "Рассветный", "Заливной"],
    "reed_swamp": ["Тростниковый", "Топяной", "Болотный", "Мшистый", "Илистый", "Туманный", "Лягушачий", "Камышовый"],
    "moon_lake": ["Лунный", "Серебристый", "Звёздный", "Зеркальный", "Сумеречный", "Ночной", "Холодный", "Лазурный"],
    "storm_coast": ["Штормовой", "Приливный", "Солёный", "Грозовой", "Яростный", "Ветряной", "Рифовый", "Буревой"],
    "crystal_cove": ["Кристальный", "Призменный", "Сияющий", "Стеклянный", "Радужный", "Чистый", "Искристый", "Гранистый"],
    "abyss_trench": ["Бездонный", "Тёмный", "Глубинный", "Разломный", "Эхо-бездны", "Левиафанов", "Сумрачный", "Тенепадный"],
}

_GENERATED_RARITY_NOUNS = {
    "common": ["пескарь", "окунёк", "бычок", "плавник", "верховка", "краснопёрка"],
    "uncommon": ["карп", "голавль", "линь", "щукарь", "язь", "подлещик"],
    "rare": ["судак", "сом", "угорь", "форель", "скат", "барракуда"],
    "epic": ["драконет", "парусник", "молот", "фантом", "химероид", "пожиратель"],
    "legendary": ["монарх", "оракул", "колосс", "архонт", "бегемот", "титан"],
}

_GENERATED_RARITY_SUFFIXES = {
    "common": ["", "", "бродяга"],
    "uncommon": ["", "страж", "ловец"],
    "rare": ["", "охотник", "коготь"],
    "epic": ["", "бури", "разлома"],
    "legendary": ["", "вечности", "трона"],
}

_GENERATED_RARITY_PHASES = {
    "common": [["morning", "day"], ["day"], ["day", "evening"], ["morning", "evening"]],
    "uncommon": [["day", "evening"], ["morning", "evening"], ["day"], ["night"]],
    "rare": [["evening", "night"], ["night"], ["day", "night"], ["evening"]],
    "epic": [["evening", "night"], ["night"], ["day", "evening"]],
    "legendary": [["night"], ["evening", "night"], ["day", "night"]],
}

_GENERATED_RARITY_SETTINGS = {
    "common": {"count": 40, "emoji": "🐟", "min_weight": 0.18, "max_weight": 1.35, "price_mult": 0.92},
    "uncommon": {"count": 40, "emoji": "🐠", "min_weight": 0.75, "max_weight": 5.0, "price_mult": 1.00},
    "rare": {"count": 35, "emoji": "🐡", "min_weight": 1.45, "max_weight": 10.5, "price_mult": 1.06},
    "epic": {"count": 28, "emoji": "🦑", "min_weight": 5.5, "max_weight": 29.0, "price_mult": 1.13},
    "legendary": {"count": 20, "emoji": "🐋", "min_weight": 15.0, "max_weight": 95.0, "price_mult": 1.07},
}

_GENERATED_ZONE_WEIGHT_FACTOR = {
    "river_bank": 1.00,
    "reed_swamp": 1.08,
    "moon_lake": 1.16,
    "storm_coast": 1.30,
    "crystal_cove": 1.42,
    "abyss_trench": 1.70,
}

_GENERATED_ZONE_PRICE_FACTOR = {
    "river_bank": 1.00,
    "reed_swamp": 1.03,
    "moon_lake": 1.06,
    "storm_coast": 1.09,
    "crystal_cove": 1.12,
    "abyss_trench": 1.16,
}

_GENERATED_EVENT_FLAVORS = {
    "mist_bloom": ("Туманный", ["плеск", "карп", "лист", "ловец"]),
    "sun_flash": ("Солнечный", ["резак", "луциан", "луч", "бриз"]),
    "ember_tide": ("Угольный", ["клык", "жарник", "скат", "хищник"]),
    "moon_hunt": ("Лунный", ["охотник", "призрак", "страж", "венец"]),
    "crystal_echo": ("Кристальный", ["эхолист", "оракул", "блик", "шёпот"]),
    "deep_alarm": ("Бездонный", ["зов", "разлом", "титан", "предвестник"]),
}


def _generated_name(prefix: str, noun: str, suffix: str) -> str:
    return f"{prefix} {noun}" if not suffix else f"{prefix} {noun} {suffix}"


def _build_generated_species() -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    existing_ids = {str(item.get("id")) for item in SPECIES}
    for zone_key, prefixes in _GENERATED_ZONE_PREFIXES.items():
        zone_weight = _GENERATED_ZONE_WEIGHT_FACTOR[zone_key]
        zone_price = _GENERATED_ZONE_PRICE_FACTOR[zone_key]
        for rarity, settings in _GENERATED_RARITY_SETTINGS.items():
            nouns = _GENERATED_RARITY_NOUNS[rarity]
            suffixes = _GENERATED_RARITY_SUFFIXES[rarity]
            phase_sets = _GENERATED_RARITY_PHASES[rarity]
            for index in range(settings["count"]):
                prefix = prefixes[index % len(prefixes)]
                noun = nouns[(index // len(prefixes)) % len(nouns)]
                suffix = suffixes[(index // (len(prefixes) * len(nouns))) % len(suffixes)]
                species_id = f"gen_{zone_key}_{rarity}_{index + 1}"
                if species_id in existing_ids:
                    continue
                min_weight = round(settings["min_weight"] * zone_weight * (0.94 + 0.02 * (index % 4)), 2)
                max_weight = round(settings["max_weight"] * zone_weight * (1.00 + 0.03 * (index % 6)), 2)
                generated.append(
                    {
                        "id": species_id,
                        "name": _generated_name(prefix, noun, suffix),
                        "emoji": settings["emoji"],
                        "rarity": rarity,
                        "zones": [zone_key],
                        "phases": phase_sets[index % len(phase_sets)],
                        "min_weight_kg": min_weight,
                        "max_weight_kg": max(max_weight, round(min_weight + 0.25, 2)),
                        "price_mult": round(settings["price_mult"] * zone_price * (1.00 + 0.006 * (index % 9)), 2),
                    }
                )
                existing_ids.add(species_id)
    return generated


def _build_generated_event_species() -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    existing_ids = {str(item.get("id")) for item in EVENT_SPECIES}
    zones_by_tag: dict[str, list[str]] = {}
    for zone_key, zone in FISHING_ZONES.items():
        zones_by_tag.setdefault(str(zone.get("tag")), []).append(zone_key)
    rarity_cycle = ("uncommon", "rare", "epic", "legendary")
    weight_ranges = {
        "uncommon": (0.9, 3.4, 1.12),
        "rare": (1.6, 6.8, 1.18),
        "epic": (5.5, 18.5, 1.24),
        "legendary": (18.0, 70.0, 1.30),
    }
    rarity_emoji = {"uncommon": "✨", "rare": "✨", "epic": "✨", "legendary": "✨"}
    for template in EVENT_TEMPLATES:
        prefix, nouns = _GENERATED_EVENT_FLAVORS[template["key"]]
        template_zones: list[str] = []
        for tag in template.get("bonus_zone_tags", set()):
            template_zones.extend(zones_by_tag.get(str(tag), []))
        template_zones = list(dict.fromkeys(template_zones)) or ["river_bank"]
        for index in range(4):
            rarity = rarity_cycle[index]
            min_weight, max_weight, price_mult = weight_ranges[rarity]
            species_id = f"event_{template['key']}_{index + 1}"
            if species_id in existing_ids:
                continue
            zone_key = template_zones[index % len(template_zones)]
            generated.append(
                {
                    "id": species_id,
                    "name": f"{prefix} {nouns[index % len(nouns)]}",
                    "emoji": rarity_emoji[rarity],
                    "rarity": rarity,
                    "zones": [zone_key],
                    "phases": _GENERATED_RARITY_PHASES[rarity][index % len(_GENERATED_RARITY_PHASES[rarity])],
                    "event_keys": [template["key"]],
                    "min_weight_kg": round(min_weight * _GENERATED_ZONE_WEIGHT_FACTOR[zone_key], 2),
                    "max_weight_kg": round(max_weight * _GENERATED_ZONE_WEIGHT_FACTOR[zone_key], 2),
                    "price_mult": round(price_mult * _GENERATED_ZONE_PRICE_FACTOR[zone_key], 2),
                }
            )
            existing_ids.add(species_id)
    return generated


def _build_generated_boss_species() -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    existing_ids = {str(item.get("id")) for item in BOSS_SPECIES}
    boss_payloads = [
        ("river_bank", "river_overlord", "Речной владыка", ["sun_flash", "ember_tide"], 30.0, 110.0, 1.31),
        ("reed_swamp", "swamp_ancient", "Древний топи", ["mist_bloom"], 34.0, 118.0, 1.33),
        ("moon_lake", "moon_patriarch", "Лунный патриарх", ["moon_hunt", "mist_bloom"], 44.0, 126.0, 1.37),
        ("storm_coast", "storm_kraken", "Кракен шторма", ["sun_flash", "ember_tide"], 60.0, 155.0, 1.40),
        ("crystal_cove", "crystal_archon", "Кристальный архонт", ["crystal_echo", "moon_hunt"], 54.0, 146.0, 1.43),
        ("abyss_trench", "abyss_emperor", "Император разлома", ["deep_alarm"], 88.0, 220.0, 1.52),
    ]
    for zone_key, species_id, name, event_keys, min_weight, max_weight, price_mult in boss_payloads:
        if species_id in existing_ids:
            continue
        generated.append(
            {
                "id": species_id,
                "name": name,
                "emoji": "👑",
                "zones": [zone_key],
                "event_keys": event_keys,
                "min_weight_kg": min_weight,
                "max_weight_kg": max_weight,
                "price_mult": price_mult,
            }
        )
    return generated


SPECIES.extend(_build_generated_species())
EVENT_SPECIES.extend(_build_generated_event_species())
BOSS_SPECIES.extend(_build_generated_boss_species())


def get_local_now(now: datetime | None = None) -> datetime:
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(CHISINAU_TZ)


def get_time_phase_key(now: datetime | None = None) -> str:
    hour = get_local_now(now).hour
    if 6 <= hour <= 11:
        return "morning"
    if 12 <= hour <= 17:
        return "day"
    if 18 <= hour <= 21:
        return "evening"
    return "night"


def get_time_phase_name(now: datetime | None = None) -> str:
    return TIME_PHASES[get_time_phase_key(now)]["name"]


def next_time_phase_change(now: datetime | None = None) -> datetime:
    local_now = get_local_now(now)
    for hour in (6, 12, 18, 22, 30):
        if local_now.hour < hour % 24 or (hour == 30 and local_now.hour >= 22):
            day_shift = 1 if hour >= 24 else 0
            target = (local_now + timedelta(days=day_shift)).replace(hour=hour % 24, minute=0, second=0, microsecond=0)
            return target.astimezone(timezone.utc)
    return local_now.astimezone(timezone.utc)


def current_weather(now: datetime | None = None) -> dict[str, Any]:
    local_now = get_local_now(now)
    slot = local_now.hour // 3
    seed = int(local_now.strftime("%Y%m%d")) * 100 + slot
    key = list(WEATHER_TYPES.keys())[seed % len(WEATHER_TYPES)]
    return {"key": key, **WEATHER_TYPES[key]}


def next_weather_change(now: datetime | None = None) -> datetime:
    local_now = get_local_now(now)
    next_hour = ((local_now.hour // 3) + 1) * 3
    if next_hour >= 24:
        target = (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        target = local_now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
    return target.astimezone(timezone.utc)


def current_hotspot(now: datetime | None = None) -> tuple[str, dict[str, Any]]:
    local_now = get_local_now(now)
    slot = local_now.hour // 2
    seed = int(local_now.strftime("%Y%m%d")) * 100 + slot
    zone_key = list(FISHING_ZONES.keys())[seed % len(FISHING_ZONES)]
    return zone_key, FISHING_ZONES[zone_key]


def next_hotspot_change(now: datetime | None = None) -> datetime:
    local_now = get_local_now(now)
    next_hour = ((local_now.hour // 2) + 1) * 2
    if next_hour >= 24:
        target = (local_now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        target = local_now.replace(hour=next_hour, minute=0, second=0, microsecond=0)
    return target.astimezone(timezone.utc)


def _event_windows_for_date(now: datetime) -> list[dict[str, Any]]:
    local_day = get_local_now(now).replace(hour=0, minute=0, second=0, microsecond=0)
    day_seed = int(local_day.strftime("%Y%m%d"))
    rng = random.Random(day_seed * 31 + 7)
    indices = list(range(len(EVENT_TEMPLATES)))
    rng.shuffle(indices)
    windows = []
    for idx, base_hour in enumerate((8, 14, 20)):
        template = dict(EVENT_TEMPLATES[indices[idx % len(indices)]])
        start_at = local_day.replace(hour=base_hour, minute=rng.choice([0, 10, 20, 30, 40]))
        template["start_at"] = start_at
        template["end_at"] = start_at + timedelta(minutes=rng.choice([50, 60, 70, 80]))
        windows.append(template)
    return windows


def iter_event_windows(now: datetime | None = None) -> list[dict[str, Any]]:
    local_now = get_local_now(now)
    return _event_windows_for_date(local_now) + _event_windows_for_date(local_now + timedelta(days=1))


def current_event_window(now: datetime | None = None) -> dict[str, Any] | None:
    local_now = get_local_now(now)
    return next((window for window in iter_event_windows(local_now) if window["start_at"] <= local_now < window["end_at"]), None)


def next_event_window(now: datetime | None = None) -> dict[str, Any] | None:
    local_now = get_local_now(now)
    return next((window for window in iter_event_windows(local_now) if window["start_at"] > local_now), None)


def get_world_state(now: datetime | None = None) -> dict[str, Any]:
    local_now = get_local_now(now)
    hotspot_key, hotspot = current_hotspot(local_now)
    return {
        "now_local": local_now,
        "time_phase_key": get_time_phase_key(local_now),
        "time_phase_name": get_time_phase_name(local_now),
        "weather": current_weather(local_now),
        "hotspot_key": hotspot_key,
        "hotspot": hotspot,
        "active_event": current_event_window(local_now),
        "next_event_window": next_event_window(local_now),
        "next_phase_change_at": next_time_phase_change(local_now),
        "next_weather_change_at": next_weather_change(local_now),
        "next_hotspot_change_at": next_hotspot_change(local_now),
    }


def _weight_multiplier(species: dict[str, Any], weight_kg: float, boss: bool) -> float:
    low = float(species["min_weight_kg"])
    high = float(species["max_weight_kg"])
    ratio = 0.0 if high <= low else max(0.0, min(1.0, (weight_kg - low) / (high - low)))
    if boss:
        return round(1.10 + ratio * 0.32, 3)
    if species["rarity"] == "legendary":
        return round(0.98 + ratio * 0.28, 3)
    return round(0.88 + ratio * 0.24, 3)


def _roll_weight(species: dict[str, Any], zone: dict[str, Any], tackle: dict[str, Any], bait: dict[str, Any] | None, weather: dict[str, Any], hotspot_bonus: bool) -> float:
    weight = random.uniform(float(species["min_weight_kg"]), float(species["max_weight_kg"]))
    weight *= float(zone.get("weight_bonus", 1.0)) * float(tackle.get("weight_bonus", 1.0)) * float(weather.get("weight_bonus", 1.0))
    if bait is not None:
        weight *= float(bait.get("weight_bonus", 1.0))
    if hotspot_bonus:
        weight *= 1.04
    return round(weight, 2)


def _rarity_weights(zone: dict[str, Any], rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, weather: dict[str, Any], hotspot_bonus: bool, active_event: dict[str, Any] | None) -> dict[str, float]:
    weights = {rarity: float(value) for rarity, value in zone["rarity_weights"].items()}
    tackle_bonus = tackle.get("rarity_bonus", {})
    bait_bonus = (bait or {}).get("rarity_bonus", {})
    weather_bonus = weather.get("rarity_bonus", {})
    event_bonus = active_event.get("rarity_bonus", {}) if active_event else {}
    for rarity in list(weights):
        factor = 1.0 + max(0.0, rod_bonus - 1.0) * {"common": -0.18, "uncommon": -0.05, "rare": 0.12, "epic": 0.18, "legendary": 0.24}.get(rarity, 0.0)
        factor *= float(tackle_bonus.get(rarity, 1.0))
        if bait is not None:
            factor *= float(bait_bonus.get(rarity, 1.0))
        factor *= float(weather_bonus.get(rarity, 1.0))
        factor *= float(event_bonus.get(rarity, 1.0))
        if hotspot_bonus and rarity in {"rare", "epic", "legendary"}:
            factor *= {"rare": 1.08, "epic": 1.10, "legendary": 1.12}[rarity]
        weights[rarity] = max(0.1, weights[rarity] * factor)
    return weights


def _weighted_choice(weights: dict[str, float]) -> str:
    total = sum(weights.values())
    roll = random.uniform(0.0, total)
    current = 0.0
    for key, value in weights.items():
        current += value
        if roll <= current:
            return key
    return next(iter(weights))


def _species_candidates(zone_key: str, phase_key: str, active_event: dict[str, Any] | None) -> list[dict[str, Any]]:
    base = [species for species in SPECIES if zone_key in species["zones"] and phase_key in species["phases"]]
    if active_event is None:
        return base
    bonus = [species for species in EVENT_SPECIES if active_event["key"] in species["event_keys"] and zone_key in species["zones"] and phase_key in species["phases"]]
    return base + bonus


def _roll_boss(zone_key: str, active_event: dict[str, Any] | None, rod_bonus: float, tackle: dict[str, Any], weather: dict[str, Any], hotspot_bonus: bool) -> dict[str, Any] | None:
    if active_event is None or not FISHING_ZONES[zone_key].get("boss_enabled"):
        return None
    candidates = [boss for boss in BOSS_SPECIES if zone_key in boss["zones"] and active_event["key"] in boss["event_keys"]]
    if not candidates:
        return None
    chance = 0.010 * max(1.0, rod_bonus) * float(tackle.get("boss_bonus", 1.0)) * float(weather.get("boss_bonus", 1.0)) * float(active_event.get("boss_bonus", 1.0))
    if hotspot_bonus:
        chance *= 1.08
    if random.random() <= min(chance, 0.18):
        return random.choice(candidates)
    return None


def roll_catch(rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, zone_key: str, now: datetime | None = None) -> dict[str, Any]:
    world_state = get_world_state(now)
    zone = FISHING_ZONES[zone_key]
    weather = world_state["weather"]
    phase_key = world_state["time_phase_key"]
    active_event = world_state["active_event"]
    hotspot_bonus = world_state["hotspot_key"] == zone_key

    boss_species = _roll_boss(zone_key, active_event, rod_bonus, tackle, weather, hotspot_bonus)
    if boss_species is not None:
        weight_kg = _roll_weight({"rarity": "legendary", **boss_species}, zone, tackle, bait, weather, hotspot_bonus)
        weight_mult = _weight_multiplier({"rarity": "legendary", **boss_species}, weight_kg, True)
        base_price = random.randint(FISH_RARITIES["legendary"]["price_min"], FISH_RARITIES["legendary"]["price_max"])
        price = base_price * float(boss_species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
        if bait is not None:
            price *= float(bait.get("value_bonus", 1.0))
        return {"species_id": boss_species["id"], "name": boss_species["name"], "emoji": boss_species["emoji"], "rarity": "legendary", "rarity_name": FISH_RARITIES["legendary"]["name"], "color": FISH_RARITIES["legendary"]["color"], "price": max(1, int(price)), "weight_kg": weight_kg, "weight_mult": weight_mult, "time_phase": phase_key, "weather_key": weather["key"], "event_key": active_event["key"], "event_name": active_event["name"], "boss": True, "hotspot_bonus_applied": hotspot_bonus, "world_state": world_state, "zone_key": zone_key, "zone_name": zone["name"]}

    candidates = _species_candidates(zone_key, phase_key, active_event) or [species for species in SPECIES if zone_key in species["zones"]]
    rarity = _weighted_choice({key: value for key, value in _rarity_weights(zone, rod_bonus, tackle, bait, weather, hotspot_bonus, active_event).items() if any(species["rarity"] == key for species in candidates)} or {"common": 1.0})
    pool = [species for species in candidates if species["rarity"] == rarity] or candidates
    species = random.choice(pool)
    weight_kg = _roll_weight(species, zone, tackle, bait, weather, hotspot_bonus)
    weight_mult = _weight_multiplier(species, weight_kg, False)
    rarity_data = FISH_RARITIES[species["rarity"]]
    price = random.randint(int(rarity_data["price_min"]), int(rarity_data["price_max"])) * float(species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
    if bait is not None:
        price *= float(bait.get("value_bonus", 1.0))
    if active_event is not None and active_event["key"] in species.get("event_keys", []):
        price *= 1.06
    return {"species_id": species["id"], "name": species["name"], "emoji": species["emoji"], "rarity": species["rarity"], "rarity_name": rarity_data["name"], "color": rarity_data["color"], "price": max(1, int(price)), "weight_kg": weight_kg, "weight_mult": weight_mult, "time_phase": phase_key, "weather_key": weather["key"], "event_key": active_event["key"] if active_event and "event_keys" in species else None, "event_name": active_event["name"] if active_event and active_event["key"] in species.get("event_keys", []) else None, "boss": False, "hotspot_bonus_applied": hotspot_bonus, "world_state": world_state, "zone_key": zone_key, "zone_name": zone["name"]}


def describe_world_lines(world_state: dict[str, Any]) -> list[str]:
    lines = [f"Время суток: **{world_state['time_phase_name']}**", f"Погода: **{world_state['weather']['name']}**", f"Hot spot: **{world_state['hotspot']['name']}**"]
    if world_state.get("active_event") is None:
        lines.append("Ивент: **сейчас нет**")
    else:
        lines.append(f"Ивент: **{world_state['active_event']['name']}**")
    return lines


def _source_bonus_factor(source: dict[str, Any], rarity: str) -> float:
    rarity_bonus = float(source.get("rarity_bonus", {}).get(rarity, 1.0))
    chance_bonus = float(source.get("chance_bonus", {}).get(rarity, 1.0))
    return rarity_bonus * (1.0 + max(0.0, chance_bonus - 1.0) * 0.75)


def _pick_species_from_pool(
    pool: list[dict[str, Any]],
    bait: dict[str, Any] | None,
    active_event: dict[str, Any] | None,
    hotspot_bonus: bool,
) -> dict[str, Any]:
    if len(pool) <= 1:
        return pool[0]

    weights: dict[str, float] = {}
    for index, species in enumerate(pool):
        weight = 1.0
        if active_event is not None and active_event["key"] in species.get("event_keys", []):
            weight *= 1.18
        if hotspot_bonus and species["rarity"] in {"rare", "epic", "legendary"}:
            weight *= 1.03
        if bait is not None:
            weight *= 1.0 + max(0.0, float(bait.get("chance_bonus", {}).get(species["rarity"], 1.0)) - 1.0) * 0.28
            if species["rarity"] in {"epic", "legendary"}:
                weight *= 1.0 + max(0.0, float(bait.get("boss_bonus", 1.0)) - 1.0) * 0.10
        weights[str(index)] = weight
    return pool[int(_weighted_choice(weights))]


def _rarity_weights(
    zone: dict[str, Any],
    rod_bonus: float,
    tackle: dict[str, Any],
    bait: dict[str, Any] | None,
    weather: dict[str, Any],
    hotspot_bonus: bool,
    active_event: dict[str, Any] | None,
) -> dict[str, float]:
    weights = {rarity: float(value) for rarity, value in zone["rarity_weights"].items()}
    event_bonus = active_event.get("rarity_bonus", {}) if active_event else {}
    has_real_bait = bait is not None and not bool(bait.get("_synthetic"))
    for rarity in list(weights):
        factor = 1.0 + max(0.0, rod_bonus - 1.0) * {"common": -0.18, "uncommon": -0.05, "rare": 0.12, "epic": 0.18, "legendary": 0.24}.get(rarity, 0.0)
        factor *= _source_bonus_factor(zone, rarity)
        factor *= _source_bonus_factor(tackle, rarity)
        if bait is not None:
            factor *= _source_bonus_factor(bait, rarity)
            luck_mult = float(bait.get("luck_mult", 1.0))
            if rarity in {"uncommon", "rare", "epic", "legendary"}:
                factor *= 1.0 + max(0.0, luck_mult - 1.0) * {
                    "uncommon": 0.30,
                    "rare": 0.55,
                    "epic": 0.82,
                    "legendary": 1.00,
                }[rarity]
        factor *= float(weather.get("rarity_bonus", {}).get(rarity, 1.0))
        factor *= float(event_bonus.get(rarity, 1.0))
        if hotspot_bonus and rarity in {"uncommon", "rare", "epic", "legendary"}:
            factor *= {"uncommon": 1.04, "rare": 1.10, "epic": 1.14, "legendary": 1.18}[rarity]
        weights[rarity] = max(0.1, weights[rarity] * factor)
    return weights


def _roll_boss(
    zone_key: str,
    active_event: dict[str, Any] | None,
    rod_bonus: float,
    tackle: dict[str, Any],
    bait: dict[str, Any] | None,
    weather: dict[str, Any],
    hotspot_bonus: bool,
) -> dict[str, Any] | None:
    if active_event is None or not FISHING_ZONES[zone_key].get("boss_enabled"):
        return None
    candidates = [boss for boss in BOSS_SPECIES if zone_key in boss["zones"] and active_event["key"] in boss["event_keys"]]
    if not candidates:
        return None
    chance = 0.011 * max(1.0, rod_bonus) * float(tackle.get("boss_bonus", 1.0)) * float(weather.get("boss_bonus", 1.0)) * float(active_event.get("boss_bonus", 1.0))
    if bait is not None:
        chance *= float(bait.get("boss_bonus", 1.0))
    if hotspot_bonus:
        chance *= 1.10
    if random.random() <= min(chance, 0.20):
        return random.choice(candidates)
    return None


def roll_catch(rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, zone_key: str, now: datetime | None = None) -> dict[str, Any]:
    world_state = get_world_state(now)
    zone = FISHING_ZONES[zone_key]
    weather = world_state["weather"]
    phase_key = world_state["time_phase_key"]
    active_event = world_state["active_event"]
    hotspot_bonus = world_state["hotspot_key"] == zone_key

    boss_species = _roll_boss(zone_key, active_event, rod_bonus, tackle, bait, weather, hotspot_bonus)
    if boss_species is not None:
        weight_kg = _roll_weight({"rarity": "legendary", **boss_species}, zone, tackle, bait, weather, hotspot_bonus)
        weight_mult = _weight_multiplier({"rarity": "legendary", **boss_species}, weight_kg, True)
        base_price = random.randint(FISH_RARITIES["legendary"]["price_min"], FISH_RARITIES["legendary"]["price_max"])
        price = base_price * float(boss_species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
        if bait is not None:
            price *= float(bait.get("value_bonus", 1.0))
        return {
            "species_id": boss_species["id"],
            "name": boss_species["name"],
            "emoji": boss_species["emoji"],
            "rarity": "legendary",
            "rarity_name": FISH_RARITIES["legendary"]["name"],
            "color": FISH_RARITIES["legendary"]["color"],
            "price": max(1, int(price)),
            "weight_kg": weight_kg,
            "weight_mult": weight_mult,
            "time_phase": phase_key,
            "weather_key": weather["key"],
            "event_key": active_event["key"],
            "event_name": active_event["name"],
            "boss": True,
            "hotspot_bonus_applied": hotspot_bonus,
            "world_state": world_state,
            "zone_key": zone_key,
            "zone_name": zone["name"],
        }

    candidates = _species_candidates(zone_key, phase_key, active_event) or [species for species in SPECIES if zone_key in species["zones"]]
    rarity_weights = _rarity_weights(zone, rod_bonus, tackle, bait, weather, hotspot_bonus, active_event)
    rarity = _weighted_choice({key: value for key, value in rarity_weights.items() if any(species["rarity"] == key for species in candidates)} or {"common": 1.0})
    pool = [species for species in candidates if species["rarity"] == rarity] or candidates
    species = _pick_species_from_pool(pool, bait, active_event, hotspot_bonus)
    weight_kg = _roll_weight(species, zone, tackle, bait, weather, hotspot_bonus)
    weight_mult = _weight_multiplier(species, weight_kg, False)
    rarity_data = FISH_RARITIES[species["rarity"]]
    price = random.randint(int(rarity_data["price_min"]), int(rarity_data["price_max"])) * float(species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
    if bait is not None:
        price *= float(bait.get("value_bonus", 1.0))
    if active_event is not None and active_event["key"] in species.get("event_keys", []):
        price *= 1.08
    return {
        "species_id": species["id"],
        "name": species["name"],
        "emoji": species["emoji"],
        "rarity": species["rarity"],
        "rarity_name": rarity_data["name"],
        "color": rarity_data["color"],
        "price": max(1, int(price)),
        "weight_kg": weight_kg,
        "weight_mult": weight_mult,
        "time_phase": phase_key,
        "weather_key": weather["key"],
        "event_key": active_event["key"] if active_event and active_event["key"] in species.get("event_keys", []) else None,
        "event_name": active_event["name"] if active_event and active_event["key"] in species.get("event_keys", []) else None,
        "boss": False,
        "hotspot_bonus_applied": hotspot_bonus,
        "world_state": world_state,
        "zone_key": zone_key,
        "zone_name": zone["name"],
    }


def _source_bonus_factor(source: dict[str, Any], rarity: str) -> float:
    rarity_bonus = float(source.get("rarity_bonus", {}).get(rarity, 1.0))
    chance_bonus = float(source.get("chance_bonus", {}).get(rarity, 1.0))
    return rarity_bonus * (1.0 + max(0.0, chance_bonus - 1.0) * 0.75)


def _pick_species_from_pool(
    pool: list[dict[str, Any]],
    bait: dict[str, Any] | None,
    active_event: dict[str, Any] | None,
    hotspot_bonus: bool,
) -> dict[str, Any]:
    if len(pool) <= 1:
        return pool[0]

    weights: dict[str, float] = {}
    for index, species in enumerate(pool):
        weight = 1.0
        if active_event is not None and active_event["key"] in species.get("event_keys", []):
            weight *= 1.18
        if hotspot_bonus and species["rarity"] in {"rare", "epic", "legendary"}:
            weight *= 1.03
        if bait is not None:
            weight *= 1.0 + max(0.0, float(bait.get("chance_bonus", {}).get(species["rarity"], 1.0)) - 1.0) * 0.28
            if species["rarity"] in {"epic", "legendary"}:
                weight *= 1.0 + max(0.0, float(bait.get("boss_bonus", 1.0)) - 1.0) * 0.10
        weights[str(index)] = weight
    return pool[int(_weighted_choice(weights))]


def _rarity_weights(
    zone: dict[str, Any],
    rod_bonus: float,
    tackle: dict[str, Any],
    bait: dict[str, Any] | None,
    weather: dict[str, Any],
    hotspot_bonus: bool,
    active_event: dict[str, Any] | None,
) -> dict[str, float]:
    weights = {rarity: float(value) for rarity, value in zone["rarity_weights"].items()}
    event_bonus = active_event.get("rarity_bonus", {}) if active_event else {}
    has_real_bait = bait is not None and not bool(bait.get("_synthetic"))
    for rarity in list(weights):
        factor = 1.0 + max(0.0, rod_bonus - 1.0) * {"common": -0.18, "uncommon": -0.05, "rare": 0.12, "epic": 0.18, "legendary": 0.24}.get(rarity, 0.0)
        factor *= _source_bonus_factor(zone, rarity)
        factor *= _source_bonus_factor(tackle, rarity)
        if bait is not None:
            factor *= _source_bonus_factor(bait, rarity)
            luck_mult = float(bait.get("luck_mult", 1.0))
            if rarity in {"uncommon", "rare", "epic", "legendary"}:
                factor *= 1.0 + max(0.0, luck_mult - 1.0) * {
                    "uncommon": 0.12,
                    "rare": 0.20,
                    "epic": 0.28,
                    "legendary": 0.34,
                }[rarity]
        factor *= float(weather.get("rarity_bonus", {}).get(rarity, 1.0))
        factor *= float(event_bonus.get(rarity, 1.0))
        if hotspot_bonus and rarity in {"uncommon", "rare", "epic", "legendary"}:
            factor *= {"uncommon": 1.02, "rare": 1.06, "epic": 1.08, "legendary": 1.10}[rarity]
        if rarity == "legendary" and not has_real_bait:
            weights[rarity] = 0.0
            continue
        weights[rarity] = max(0.1, weights[rarity] * factor)
    return weights


def _roll_boss(
    zone_key: str,
    active_event: dict[str, Any] | None,
    rod_bonus: float,
    tackle: dict[str, Any],
    bait: dict[str, Any] | None,
    weather: dict[str, Any],
    hotspot_bonus: bool,
) -> dict[str, Any] | None:
    if active_event is None or not FISHING_ZONES[zone_key].get("boss_enabled"):
        return None
    if bait is None or bool(bait.get("_synthetic")):
        return None
    candidates = [boss for boss in BOSS_SPECIES if zone_key in boss["zones"] and active_event["key"] in boss["event_keys"]]
    if not candidates:
        return None
    chance = 0.0065 * max(1.0, rod_bonus) * float(tackle.get("boss_bonus", 1.0)) * float(weather.get("boss_bonus", 1.0)) * float(active_event.get("boss_bonus", 1.0))
    if bait is not None:
        chance *= float(bait.get("boss_bonus", 1.0))
    if hotspot_bonus:
        chance *= 1.05
    if random.random() <= min(chance, 0.10):
        return random.choice(candidates)
    return None


def roll_catch(rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, zone_key: str, now: datetime | None = None) -> dict[str, Any]:
    world_state = get_world_state(now)
    zone = FISHING_ZONES[zone_key]
    weather = world_state["weather"]
    phase_key = world_state["time_phase_key"]
    active_event = world_state["active_event"]
    hotspot_bonus = world_state["hotspot_key"] == zone_key

    boss_species = _roll_boss(zone_key, active_event, rod_bonus, tackle, bait, weather, hotspot_bonus)
    if boss_species is not None:
        weight_kg = _roll_weight({"rarity": "legendary", **boss_species}, zone, tackle, bait, weather, hotspot_bonus)
        weight_mult = _weight_multiplier({"rarity": "legendary", **boss_species}, weight_kg, True)
        base_price = random.randint(FISH_RARITIES["legendary"]["price_min"], FISH_RARITIES["legendary"]["price_max"])
        price = base_price * float(boss_species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
        if bait is not None:
            price *= float(bait.get("value_bonus", 1.0))
        return {
            "species_id": boss_species["id"],
            "name": boss_species["name"],
            "emoji": boss_species["emoji"],
            "rarity": "legendary",
            "rarity_name": FISH_RARITIES["legendary"]["name"],
            "color": FISH_RARITIES["legendary"]["color"],
            "price": max(1, int(price)),
            "weight_kg": weight_kg,
            "weight_mult": weight_mult,
            "time_phase": phase_key,
            "weather_key": weather["key"],
            "event_key": active_event["key"],
            "event_name": active_event["name"],
            "boss": True,
            "hotspot_bonus_applied": hotspot_bonus,
            "world_state": world_state,
            "zone_key": zone_key,
            "zone_name": zone["name"],
        }

    candidates = _species_candidates(zone_key, phase_key, active_event) or [species for species in SPECIES if zone_key in species["zones"]]
    rarity_weights = _rarity_weights(zone, rod_bonus, tackle, bait, weather, hotspot_bonus, active_event)
    rarity = _weighted_choice({key: value for key, value in rarity_weights.items() if any(species["rarity"] == key for species in candidates)} or {"common": 1.0})
    pool = [species for species in candidates if species["rarity"] == rarity] or candidates
    species = _pick_species_from_pool(pool, bait, active_event, hotspot_bonus)
    weight_kg = _roll_weight(species, zone, tackle, bait, weather, hotspot_bonus)
    weight_mult = _weight_multiplier(species, weight_kg, False)
    rarity_data = FISH_RARITIES[species["rarity"]]
    price = random.randint(int(rarity_data["price_min"]), int(rarity_data["price_max"])) * float(species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
    if bait is not None:
        price *= float(bait.get("value_bonus", 1.0))
    if active_event is not None and active_event["key"] in species.get("event_keys", []):
        price *= 1.04
    return {
        "species_id": species["id"],
        "name": species["name"],
        "emoji": species["emoji"],
        "rarity": species["rarity"],
        "rarity_name": rarity_data["name"],
        "color": rarity_data["color"],
        "price": max(1, int(price)),
        "weight_kg": weight_kg,
        "weight_mult": weight_mult,
        "time_phase": phase_key,
        "weather_key": weather["key"],
        "event_key": active_event["key"] if active_event and active_event["key"] in species.get("event_keys", []) else None,
        "event_name": active_event["name"] if active_event and active_event["key"] in species.get("event_keys", []) else None,
        "boss": False,
        "hotspot_bonus_applied": hotspot_bonus,
        "world_state": world_state,
        "zone_key": zone_key,
        "zone_name": zone["name"],
    }


def describe_world_lines(world_state: dict[str, Any]) -> list[str]:
    lines = [
        f"Время суток: **{world_state['time_phase_name']}**",
        f"Погода: **{world_state['weather']['name']}**",
        f"Хот-спот: **{world_state['hotspot']['name']}**",
    ]
    if world_state.get("active_event") is None:
        lines.append("Ивент: **сейчас нет**")
    else:
        lines.append(f"Ивент: **{world_state['active_event']['name']}**")
    return lines


# --- Codex fishing rebalance overrides ---
def _source_bonus_factor(source: dict[str, Any], rarity: str) -> float:
    rarity_bonus = float(source.get("rarity_bonus", {}).get(rarity, 1.0))
    chance_bonus = float(source.get("chance_bonus", {}).get(rarity, 1.0))
    return rarity_bonus * (1.0 + max(0.0, chance_bonus - 1.0) * 0.75)


def _pick_species_from_pool(
    pool: list[dict[str, Any]],
    bait: dict[str, Any] | None,
    active_event: dict[str, Any] | None,
    hotspot_bonus: bool,
) -> dict[str, Any]:
    if len(pool) <= 1:
        return pool[0]

    weights: dict[str, float] = {}
    for index, species in enumerate(pool):
        weight = 1.0
        if active_event is not None and active_event["key"] in species.get("event_keys", []):
            weight *= 1.18
        if hotspot_bonus and species["rarity"] in {"rare", "epic", "legendary"}:
            weight *= 1.03
        if bait is not None:
            weight *= 1.0 + max(0.0, float(bait.get("chance_bonus", {}).get(species["rarity"], 1.0)) - 1.0) * 0.28
            if species["rarity"] in {"epic", "legendary"}:
                weight *= 1.0 + max(0.0, float(bait.get("boss_bonus", 1.0)) - 1.0) * 0.10
        weights[str(index)] = weight
    return pool[int(_weighted_choice(weights))]


def _rarity_weights(
    zone: dict[str, Any],
    rod_bonus: float,
    tackle: dict[str, Any],
    bait: dict[str, Any] | None,
    weather: dict[str, Any],
    hotspot_bonus: bool,
    active_event: dict[str, Any] | None,
) -> dict[str, float]:
    weights = {rarity: float(value) for rarity, value in zone["rarity_weights"].items()}
    event_bonus = active_event.get("rarity_bonus", {}) if active_event else {}
    has_real_bait = bait is not None and not bool(bait.get("_synthetic"))
    for rarity in list(weights):
        factor = 1.0 + max(0.0, rod_bonus - 1.0) * {"common": -0.18, "uncommon": -0.05, "rare": 0.12, "epic": 0.18, "legendary": 0.24}.get(rarity, 0.0)
        factor *= _source_bonus_factor(zone, rarity)
        factor *= _source_bonus_factor(tackle, rarity)
        if bait is not None:
            factor *= _source_bonus_factor(bait, rarity)
            luck_mult = float(bait.get("luck_mult", 1.0))
            if rarity in {"uncommon", "rare", "epic", "legendary"}:
                factor *= 1.0 + max(0.0, luck_mult - 1.0) * {
                    "uncommon": 0.12,
                    "rare": 0.20,
                    "epic": 0.28,
                    "legendary": 0.34,
                }[rarity]
        factor *= float(weather.get("rarity_bonus", {}).get(rarity, 1.0))
        factor *= float(event_bonus.get(rarity, 1.0))
        if hotspot_bonus and rarity in {"uncommon", "rare", "epic", "legendary"}:
            factor *= {"uncommon": 1.02, "rare": 1.06, "epic": 1.08, "legendary": 1.10}[rarity]
        if rarity == "legendary" and not has_real_bait:
            weights[rarity] = 0.0
            continue
        weights[rarity] = max(0.1, weights[rarity] * factor)
    return weights


def _roll_boss(
    zone_key: str,
    active_event: dict[str, Any] | None,
    rod_bonus: float,
    tackle: dict[str, Any],
    bait: dict[str, Any] | None,
    weather: dict[str, Any],
    hotspot_bonus: bool,
) -> dict[str, Any] | None:
    if active_event is None or not FISHING_ZONES[zone_key].get("boss_enabled"):
        return None
    if bait is None or bool(bait.get("_synthetic")):
        return None
    candidates = [boss for boss in BOSS_SPECIES if zone_key in boss["zones"] and active_event["key"] in boss["event_keys"]]
    if not candidates:
        return None
    chance = 0.0065 * max(1.0, rod_bonus) * float(tackle.get("boss_bonus", 1.0)) * float(weather.get("boss_bonus", 1.0)) * float(active_event.get("boss_bonus", 1.0))
    if bait is not None:
        chance *= float(bait.get("boss_bonus", 1.0))
    if hotspot_bonus:
        chance *= 1.05
    if random.random() <= min(chance, 0.10):
        return random.choice(candidates)
    return None


def roll_catch(rod_bonus: float, tackle: dict[str, Any], bait: dict[str, Any] | None, zone_key: str, now: datetime | None = None) -> dict[str, Any]:
    world_state = get_world_state(now)
    zone = FISHING_ZONES[zone_key]
    weather = world_state["weather"]
    phase_key = world_state["time_phase_key"]
    active_event = world_state["active_event"]
    hotspot_bonus = world_state["hotspot_key"] == zone_key

    boss_species = _roll_boss(zone_key, active_event, rod_bonus, tackle, bait, weather, hotspot_bonus)
    if boss_species is not None:
        weight_kg = _roll_weight({"rarity": "legendary", **boss_species}, zone, tackle, bait, weather, hotspot_bonus)
        weight_mult = _weight_multiplier({"rarity": "legendary", **boss_species}, weight_kg, True)
        base_price = random.randint(FISH_RARITIES["legendary"]["price_min"], FISH_RARITIES["legendary"]["price_max"])
        price = base_price * float(boss_species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
        if bait is not None:
            price *= float(bait.get("value_bonus", 1.0))
        return {
            "species_id": boss_species["id"],
            "name": boss_species["name"],
            "emoji": boss_species["emoji"],
            "rarity": "legendary",
            "rarity_name": FISH_RARITIES["legendary"]["name"],
            "color": FISH_RARITIES["legendary"]["color"],
            "price": max(1, int(price)),
            "weight_kg": weight_kg,
            "weight_mult": weight_mult,
            "time_phase": phase_key,
            "weather_key": weather["key"],
            "event_key": active_event["key"],
            "event_name": active_event["name"],
            "boss": True,
            "hotspot_bonus_applied": hotspot_bonus,
            "world_state": world_state,
            "zone_key": zone_key,
            "zone_name": zone["name"],
        }

    candidates = _species_candidates(zone_key, phase_key, active_event) or [species for species in SPECIES if zone_key in species["zones"]]
    rarity_weights = _rarity_weights(zone, rod_bonus, tackle, bait, weather, hotspot_bonus, active_event)
    rarity = _weighted_choice({key: value for key, value in rarity_weights.items() if any(species["rarity"] == key for species in candidates)} or {"common": 1.0})
    pool = [species for species in candidates if species["rarity"] == rarity] or candidates
    species = _pick_species_from_pool(pool, bait, active_event, hotspot_bonus)
    weight_kg = _roll_weight(species, zone, tackle, bait, weather, hotspot_bonus)
    weight_mult = _weight_multiplier(species, weight_kg, False)
    rarity_data = FISH_RARITIES[species["rarity"]]
    price = random.randint(int(rarity_data["price_min"]), int(rarity_data["price_max"])) * float(species["price_mult"]) * float(zone["value_bonus"]) * float(tackle["value_bonus"]) * float(weather["value_bonus"]) * weight_mult * (1.05 if hotspot_bonus else 1.0)
    if bait is not None:
        price *= float(bait.get("value_bonus", 1.0))
    if active_event is not None and active_event["key"] in species.get("event_keys", []):
        price *= 1.04
    return {
        "species_id": species["id"],
        "name": species["name"],
        "emoji": species["emoji"],
        "rarity": species["rarity"],
        "rarity_name": rarity_data["name"],
        "color": rarity_data["color"],
        "price": max(1, int(price)),
        "weight_kg": weight_kg,
        "weight_mult": weight_mult,
        "time_phase": phase_key,
        "weather_key": weather["key"],
        "event_key": active_event["key"] if active_event and active_event["key"] in species.get("event_keys", []) else None,
        "event_name": active_event["name"] if active_event and active_event["key"] in species.get("event_keys", []) else None,
        "boss": False,
        "hotspot_bonus_applied": hotspot_bonus,
        "world_state": world_state,
        "zone_key": zone_key,
        "zone_name": zone["name"],
    }


def describe_world_lines(world_state: dict[str, Any]) -> list[str]:
    lines = [
        f"Время суток: **{world_state['time_phase_name']}**",
        f"Погода: **{world_state['weather']['name']}**",
        f"Хот-спот: **{world_state['hotspot']['name']}**",
    ]
    if world_state.get("active_event") is None:
        lines.append("Ивент: **сейчас нет**")
    else:
        lines.append(f"Ивент: **{world_state['active_event']['name']}**")
    return lines
