from __future__ import annotations

from itertools import product

WORK_ACTIONS = [
    ("покрасил забор", 650, 1100),
    ("починил проводку", 750, 1250),
    ("настроил сайт", 900, 1550),
    ("разгрузил фуру", 800, 1400),
    ("развёз заказы", 700, 1200),
    ("собрал мебель", 780, 1320),
    ("починил ноутбуки", 950, 1600),
    ("настроил Wi-Fi", 720, 1180),
]

WORK_CONTEXTS = [
    "для местного кафе",
    "для торгового центра",
    "для дачного кооператива",
    "для стартапа у метро",
    "для сервера с мемами",
]

CRIME_ACTIONS = [
    ("взломал кассу", 0.62, 1800, 4200, 900, 1800),
    ("подменил чемодан", 0.48, 2400, 6000, 1100, 2400),
    ("вытащил сейф", 0.36, 4200, 9800, 1800, 4200),
    ("украл чипы", 0.58, 1600, 3900, 800, 1500),
    ("перехватил груз", 0.44, 2800, 7200, 1200, 2800),
    ("обнёс подсобку", 0.66, 1300, 3100, 700, 1300),
    ("провернул аферу", 0.41, 3200, 8400, 1500, 3200),
    ("стащил чемодан налички", 0.33, 5200, 12400, 2400, 5200),
]

CRIME_TARGETS = [
    "у букмекерской конторы",
    "у ночного клуба",
    "у ломбарда на рынке",
    "у мини-казино в подвале",
    "у офиса сомнительного стартапа",
]

SLUT_ACTS = [
    ("станцевал на сцене", "для толпы пенсионерок"),
    ("продал фотки ног", "арабскому шейху"),
    ("сыграл фальшивого экстрасенса", "на корпоративе бухгалтеров"),
    ("провёл вебинар по соблазнению", "для скучающих айтишников"),
    ("спел под фанеру", "в караоке-баре у вокзала"),
    ("снялся в кринж-рекламе", "для местного телеканала"),
    ("устроил приватный стрим", "для коллекционеров тапок"),
    ("работал фальшивым тарологом", "на ярмарке эзотерики"),
    ("продавал комплименты", "на вечеринке инфоцыган"),
    ("изображал богатого коуча", "на бизнес-форуме"),
]

SLUT_FAILURES = [
    "нарвался на полицию нравов",
    "вляпался в скандал и заплатил штраф",
    "попал на скрытую проверку и остался без денег",
    "сорвал выступление и оплатил разбитую колонку",
    "попался мошенникам и потерял весь гонорар",
]


def build_work_pool() -> list[dict]:
    pool: list[dict] = []
    for action, context in product(WORK_ACTIONS, WORK_CONTEXTS):
        action_text, min_reward, max_reward = action
        pool.append(
            {
                "title": f"{action_text.title()} {context}",
                "summary": f"Ты {action_text} {context}.",
                "reward_min": min_reward,
                "reward_max": max_reward,
            }
        )
    return pool


def build_crime_pool() -> list[dict]:
    pool: list[dict] = []
    for action, context in product(CRIME_ACTIONS, CRIME_TARGETS):
        action_text, success_rate, reward_min, reward_max, fine_min, fine_max = action
        pool.append(
            {
                "title": f"{action_text.title()} {context}",
                "summary": f"Ты {action_text} {context}.",
                "success_rate": success_rate,
                "reward_min": reward_min,
                "reward_max": reward_max,
                "fine_min": fine_min,
                "fine_max": fine_max,
                "success_text": f"Ты {action_text} {context} и тихо растворился в ночи.",
                "fail_text": f"Ты {action_text} {context}, но тревога сработала слишком рано.",
            }
        )
    return pool


def build_slut_pool() -> list[dict]:
    pool: list[dict] = []
    for success_act, audience in SLUT_ACTS:
        for failure in SLUT_FAILURES:
            pool.append(
                {
                    "success_text": f"Ты {success_act} {audience} и внезапно сорвал жирный гонорар.",
                    "fail_text": f"Ты {success_act} {audience}, но {failure}.",
                    "success_rate": 0.62,
                    "reward_min": 900,
                    "reward_max": 7200,
                    "loss_min": 250,
                    "loss_max": 2600,
                }
            )
    return pool


WORK_POOL = build_work_pool()
CRIME_POOL = build_crime_pool()
SLUT_POOL = build_slut_pool()
