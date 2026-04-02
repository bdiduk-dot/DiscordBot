import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# ============================================================================
# КОНФИГУРАЦИЯ
# ============================================================================

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Проверка переменных окружения
if not DISCORD_TOKEN or DISCORD_TOKEN == 'YOUR_TOKEN_HERE':
    raise ValueError("ERROR: DISCORD_BOT_TOKEN not set! Add it to environment variables.")

if not SUPABASE_URL or SUPABASE_URL == 'YOUR_SUPABASE_URL':
    raise ValueError("ERROR: SUPABASE_URL not set! Add it to environment variables.")

if not SUPABASE_KEY or SUPABASE_KEY == 'YOUR_SUPABASE_KEY':
    raise ValueError("ERROR: SUPABASE_KEY not set! Add it to environment variables.")

# ADMIN USER IDs
ADMIN_IDS = [
    936219001628028979,
    979455847849664543,
    1069594347676385301
]

# ALLOWED CHANNEL ID - канал где можно играть
ALLOWED_CHANNEL_ID = 1486032811809964243
CASINO_ROLE_ID = 1486391112330379304

# ============================================================================
# ЭМОДЗИ И КОНСТАНТЫ
# ============================================================================

EMOJI = {
    'money': '💰',
    'coin': '🪙',
    'gem': '💎',
    'trophy': '🏆',
    'fire': '🔥',
    'star': '⭐',
    'level': '📊',
    'gift': '🎁',
    'work': '💼',
    'steal': '🎭',
    'cards': '🃏',
    'roulette': '🎰',
    'slots': '🎰',
    'dice': '🎲',
    'win': '🎉',
    'lose': '😢',
    'jackpot': '🎊',
    'shop': '🛒',
    'crown': '👑',
    'vip': '💳'
}

# Цвета для embed
COLORS = {
    'success': 0x00ff00,
    'error': 0xff0000,
    'info': 0x3498db,
    'warning': 0xffa500,
    'gold': 0xffd700,
    'purple': 0x9b59b6,
    'bronze': 0xcd7f32,
    'silver': 0xc0c0c0,
    'platinum': 0xe5e4e2,
    'diamond': 0xb9f2ff,
    'master': 0xff0080
}

# Система рангов
RANKS = {
    'Bronze': {'min': 0, 'max': 999, 'emoji': '🥉', 'bonus': 1.0, 'color': COLORS['bronze']},
    'Silver': {'min': 1000, 'max': 4999, 'emoji': '🥈', 'bonus': 1.1, 'color': COLORS['silver']},
    'Gold': {'min': 5000, 'max': 9999, 'emoji': '🥇', 'bonus': 1.25, 'color': COLORS['gold']},
    'Platinum': {'min': 10000, 'max': 24999, 'emoji': '💎', 'bonus': 1.5, 'color': COLORS['platinum']},
    'Diamond': {'min': 25000, 'max': 49999, 'emoji': '💠', 'bonus': 2.0, 'color': COLORS['diamond']},
    'Master': {'min': 50000, 'max': 999999, 'emoji': '👑', 'bonus': 3.0, 'color': COLORS['master']}
}

# VIP система
VIP_LEVELS = {
    0: {'name': 'None', 'emoji': '', 'cost': 0, 'daily_bonus': 1.0, 'cooldown_reduction': 0},
    1: {'name': 'Bronze VIP', 'emoji': '🥉', 'cost': 500, 'daily_bonus': 1.1, 'cooldown_reduction': 0.1},
    2: {'name': 'Silver VIP', 'emoji': '🥈', 'cost': 1500, 'daily_bonus': 1.25, 'cooldown_reduction': 0.25},
    3: {'name': 'Gold VIP', 'emoji': '🥇', 'cost': 3000, 'daily_bonus': 1.5, 'cooldown_reduction': 0.5},
    4: {'name': 'Diamond VIP', 'emoji': '💎', 'cost': 5000, 'daily_bonus': 2.0, 'cooldown_reduction': 0.75}
}

# Криптовалюты для майнинга
CRYPTO_TYPES = {
    'BTC': {'name': 'Bitcoin', 'emoji': '₿', 'color': 0xf7931a, 'base_price': 50000, 'volatility': 0.15, 'mine_amount_min': 0.0001, 'mine_amount_max': 0.001, 'chance': 0.15},
    'ETH': {'name': 'Ethereum', 'emoji': 'Ξ', 'color': 0x627eea, 'base_price': 3000, 'volatility': 0.20, 'mine_amount_min': 0.001, 'mine_amount_max': 0.01, 'chance': 0.20},
    'DOGE': {'name': 'Dogecoin', 'emoji': 'Ð', 'color': 0xc2a633, 'base_price': 0.15, 'volatility': 0.30, 'mine_amount_min': 10, 'mine_amount_max': 100, 'chance': 0.30},
    'LTC': {'name': 'Litecoin', 'emoji': 'Ł', 'color': 0x345d9d, 'base_price': 100, 'volatility': 0.18, 'mine_amount_min': 0.01, 'mine_amount_max': 0.1, 'chance': 0.20},
    'XRP': {'name': 'Ripple', 'emoji': '✕', 'color': 0x23292f, 'base_price': 0.50, 'volatility': 0.25, 'mine_amount_min': 5, 'mine_amount_max': 50, 'chance': 0.15}
}

# Бизнесы
BUSINESSES = {
    1: {'name': '🍋 Lemonade Stand', 'cost': 1000, 'income': 50, 'time': 1},
    2: {'name': '🌭 Hot Dog Cart', 'cost': 2500, 'income': 120, 'time': 1},
    3: {'name': '☕ Coffee Shop', 'cost': 5000, 'income': 250, 'time': 2},
    4: {'name': '🍕 Pizza Place', 'cost': 10000, 'income': 500, 'time': 2},
    5: {'name': '🍔 Burger Joint', 'cost': 15000, 'income': 750, 'time': 2},
    6: {'name': '🎮 Gaming Cafe', 'cost': 25000, 'income': 1200, 'time': 3},
    7: {'name': '🏪 Convenience Store', 'cost': 35000, 'income': 1700, 'time': 3},
    8: {'name': '💇 Barbershop', 'cost': 50000, 'income': 2500, 'time': 4},
    9: {'name': '🏋️ Gym', 'cost': 75000, 'income': 3800, 'time': 4},
    10: {'name': '🎬 Movie Theater', 'cost': 100000, 'income': 5000, 'time': 5},
    11: {'name': '🏨 Small Hotel', 'cost': 150000, 'income': 7500, 'time': 5},
    12: {'name': '🏪 Supermarket', 'cost': 200000, 'income': 10000, 'time': 6},
    13: {'name': '🏭 Factory', 'cost': 300000, 'income': 15000, 'time': 6},
    14: {'name': '🏢 Office Building', 'cost': 500000, 'income': 25000, 'time': 7},
    15: {'name': '🏬 Shopping Mall', 'cost': 750000, 'income': 38000, 'time': 8},
    16: {'name': '🏦 Bank Branch', 'cost': 1000000, 'income': 50000, 'time': 8},
    17: {'name': '🏥 Hospital', 'cost': 1500000, 'income': 75000, 'time': 9},
    18: {'name': '🏰 Casino', 'cost': 2500000, 'income': 125000, 'time': 10},
    19: {'name': '✈️ Airport', 'cost': 5000000, 'income': 250000, 'time': 12, 'unique': False},
    20: {'name': '🌆 Skyscraper', 'cost': 10000000, 'income': 500000, 'time': 14, 'unique': True}
}

# Квесты - ежедневные (простые)
BUSINESSES.update({
    21: {'name': '🚁 Drone Delivery Hub', 'cost': 15000000, 'income': 700000, 'time': 14},
    22: {'name': '🏝 Luxury Resort', 'cost': 25000000, 'income': 1200000, 'time': 16},
    23: {'name': '🖥 Data Center', 'cost': 40000000, 'income': 2000000, 'time': 18},
    24: {'name': '🚀 Space Port', 'cost': 65000000, 'income': 3200000, 'time': 20},
    25: {'name': '🧠 AI Lab', 'cost': 90000000, 'income': 4500000, 'time': 22},
    26: {'name': '🛳 Cruise Fleet', 'cost': 125000000, 'income': 6500000, 'time': 24},
    27: {'name': '🏟 Mega Stadium', 'cost': 175000000, 'income': 9000000, 'time': 26},
    28: {'name': '🤖 Robotics Plant', 'cost': 250000000, 'income': 13000000, 'time': 28},
    29: {'name': '🛰 Orbital Shipyard', 'cost': 400000000, 'income': 21000000, 'time': 32},
    30: {'name': '🌆 Quantum Megacity', 'cost': 750000000, 'income': 40000000, 'time': 36},
})

BUSINESSES.update({
    21: {'name': 'Drone Delivery Hub', 'cost': 15000000, 'income': 700000, 'time': 14},
    22: {'name': 'Luxury Resort', 'cost': 25000000, 'income': 1200000, 'time': 16},
    23: {'name': 'Data Center', 'cost': 40000000, 'income': 2000000, 'time': 18},
    24: {'name': 'Space Port', 'cost': 65000000, 'income': 3200000, 'time': 20},
    25: {'name': 'AI Lab', 'cost': 90000000, 'income': 4500000, 'time': 22},
    26: {'name': 'Cruise Fleet', 'cost': 125000000, 'income': 6500000, 'time': 24},
    27: {'name': 'Mega Stadium', 'cost': 175000000, 'income': 9000000, 'time': 26},
    28: {'name': 'Robotics Plant', 'cost': 250000000, 'income': 13000000, 'time': 28},
    29: {'name': 'Orbital Shipyard', 'cost': 400000000, 'income': 21000000, 'time': 32},
    30: {'name': 'Quantum Megacity', 'cost': 750000000, 'income': 40000000, 'time': 36},
})

DAILY_QUESTS_POOL = [
    {'id': 'earn_1k', 'name': 'Заработок новичка', 'desc': 'Заработай $1,000', 'type': 'earn', 'target': 1000, 'reward_money': 500, 'reward_gems': 3},
    {'id': 'play_5_games', 'name': 'Игрок', 'desc': 'Сыграй 5 игр', 'type': 'play', 'target': 5, 'reward_money': 800, 'reward_gems': 5},
    {'id': 'win_3_games', 'name': 'Победитель', 'desc': 'Выиграй 3 игры', 'type': 'win', 'target': 3, 'reward_money': 1000, 'reward_gems': 7},
    {'id': 'fish_3_times', 'name': 'Рыбак', 'desc': 'Поймай 3 рыбы', 'type': 'fish', 'target': 3, 'reward_money': 600, 'reward_gems': 4},
    {'id': 'mine_2_times', 'name': 'Майнер', 'desc': 'Намайнь 2 раза', 'type': 'mine', 'target': 2, 'reward_money': 1200, 'reward_gems': 8},
    {'id': 'collect_hourly', 'name': 'Активный', 'desc': 'Собери hourly бонус 3 раза', 'type': 'hourly', 'target': 3, 'reward_money': 700, 'reward_gems': 5},
    {'id': 'work_3_times', 'name': 'Работяга', 'desc': 'Поработай 3 раза', 'type': 'work', 'target': 3, 'reward_money': 900, 'reward_gems': 6},
    {'id': 'spin_wheel', 'name': 'Удачливый', 'desc': 'Крути колесо 1 раз', 'type': 'wheel', 'target': 1, 'reward_money': 1500, 'reward_gems': 10}
]

# Квесты - еженедельные (сложные)
WEEKLY_QUESTS_POOL = [
    {'id': 'earn_50k', 'name': 'Богач', 'desc': 'Заработай $50,000', 'type': 'earn', 'target': 50000, 'reward_money': 4500, 'reward_gems': 25},
    {'id': 'play_50_games', 'name': 'Игроман', 'desc': 'Сыграй 50 игр', 'type': 'play', 'target': 50, 'reward_money': 6000, 'reward_gems': 35},
    {'id': 'win_25_games', 'name': 'Чемпион', 'desc': 'Выиграй 25 игр', 'type': 'win', 'target': 25, 'reward_money': 7000, 'reward_gems': 40},
    {'id': 'fish_20_times', 'name': 'Мастер рыбалки', 'desc': 'Поймай 20 рыб', 'type': 'fish', 'target': 20, 'reward_money': 5000, 'reward_gems': 30},
    {'id': 'mine_15_times', 'name': 'Крипто магнат', 'desc': 'Намайнь 15 раз', 'type': 'mine', 'target': 15, 'reward_money': 8000, 'reward_gems': 45},
    {'id': 'catch_legendary', 'name': 'Легенда', 'desc': 'Поймай легендарную рыбу', 'type': 'fish_legendary', 'target': 1, 'reward_money': 9000, 'reward_gems': 50},
    {'id': 'win_streak_10', 'name': 'Серия побед', 'desc': 'Набери серию из 10 побед', 'type': 'streak', 'target': 10, 'reward_money': 10000, 'reward_gems': 55},
    {'id': 'buy_business', 'name': 'Предприниматель', 'desc': 'Купи любой бизнес', 'type': 'business', 'target': 1, 'reward_money': 6000, 'reward_gems': 35},
    {'id': 'collect_business_10', 'name': 'Бизнесмен', 'desc': 'Собери доход с бизнеса 10 раз', 'type': 'collect_business', 'target': 10, 'reward_money': 5500, 'reward_gems': 30},
    {'id': 'mine_btc', 'name': 'Bitcoin майнер', 'desc': 'Намайнь Bitcoin', 'type': 'mine_btc', 'target': 1, 'reward_money': 12000, 'reward_gems': 70}
]

# Рыбалка - Удочки
FISHING_RODS = {
    'none': {'name': '🪝 Обычный крючок', 'bonus': 1.0, 'price': 0, 'gems': 0},
    'wooden': {'name': '🎣 Деревянная удочка', 'bonus': 1.12, 'price': 5000, 'gems': 0},
    'fiberglass': {'name': '🥈 Стеклопластиковая удочка', 'bonus': 1.35, 'price': 25000, 'gems': 10},
    'carbon': {'name': '🥇 Углепластиковая удочка', 'bonus': 1.7, 'price': 100000, 'gems': 50},
    'diamond': {'name': '💎 Алмазная удочка', 'bonus': 2.2, 'price': 500000, 'gems': 250}
}

# Рыбалка - редкости рыб
FISH_RARITIES = {
    'common': {'name': 'Обычная', 'emoji': '🐟', 'color': 0x808080, 'chance': 0.50, 'price_min': 50, 'price_max': 150, 'fish': ['Карась', 'Окунь', 'Плотва', 'Ёрш', 'Уклейка']},
    'uncommon': {'name': 'Необычная', 'emoji': '🐠', 'color': 0x00ff00, 'chance': 0.30, 'price_min': 200, 'price_max': 500, 'fish': ['Щука', 'Судак', 'Карп', 'Лещ', 'Сом']},
    'rare': {'name': 'Редкая', 'emoji': '🐡', 'color': 0x0080ff, 'chance': 0.15, 'price_min': 600, 'price_max': 1200, 'fish': ['Осётр', 'Форель', 'Сёмга', 'Угорь', 'Налим']},
    'epic': {'name': 'Эпическая', 'emoji': '🦈', 'color': 0x9b59b6, 'chance': 0.04, 'price_min': 1500, 'price_max': 3000, 'fish': ['Акула', 'Марлин', 'Тунец', 'Рыба-меч', 'Скат']},
    'legendary': {'name': 'Легендарная', 'emoji': '🐋', 'color': 0xffd700, 'chance': 0.01, 'price_min': 5000, 'price_max': 10000, 'fish': ['Золотая рыбка', 'Кит', 'Дельфин', 'Мегалодон', 'Левиафан']}
}

# Квесты под новую систему домов
for quest in DAILY_QUESTS_POOL:
    if quest["type"] == "mine":
        quest["name"] = "Подвал работает"
        quest["desc"] = "Собери доход из подвала 2 раза"

for quest in WEEKLY_QUESTS_POOL:
    if quest["id"] == "mine_15_times":
        quest["name"] = "Хозяин подвала"
        quest["desc"] = "Собери доход из подвала 15 раз"
    elif quest["id"] == "mine_btc":
        quest["id"] = "rent_5_times"
        quest["name"] = "Арендодатель"
        quest["desc"] = "Собери аренду 5 раз"
        quest["type"] = "rent"
        quest["target"] = 5

# Вспомогательные функции
def get_rank(xp: int) -> dict:
    """Получить информацию о ранге по количеству XP"""
    for rank_name, rank_data in sorted(RANKS.items(), key=lambda x: x[1]['min'], reverse=True):
        if xp >= rank_data['min']:
            return {'name': rank_name, **rank_data}
    return {'name': 'Bronze', **RANKS['Bronze']}

def get_vip_level(level: int) -> dict:
    """Получить информацию о VIP уровне"""
    return VIP_LEVELS.get(level, VIP_LEVELS[0])
