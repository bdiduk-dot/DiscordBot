import random


class Games:
    @staticmethod
    def blackjack(bet: int) -> tuple[str, int, str]:
        cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"] * 4
        random.shuffle(cards)

        def card_value(card: str) -> int:
            if card in {"J", "Q", "K"}:
                return 10
            if card == "A":
                return 11
            return int(card)

        def hand_value(hand: list[str]) -> int:
            value = sum(card_value(card) for card in hand)
            aces = hand.count("A")
            while value > 21 and aces:
                value -= 10
                aces -= 1
            return value

        player_hand = [cards.pop(), cards.pop()]
        dealer_hand = [cards.pop(), cards.pop()]
        player_value = hand_value(player_hand)
        dealer_value = hand_value(dealer_hand)

        while dealer_value < 17:
            dealer_hand.append(cards.pop())
            dealer_value = hand_value(dealer_hand)

        desc = (
            f"**Твои карты:** {' '.join(player_hand)} = {player_value}\n"
            f"**Карты дилера:** {' '.join(dealer_hand)} = {dealer_value}\n\n"
        )

        if player_value > 21:
            return "lose", 0, desc + f"❌ Перебор. Ты проиграл {bet:,}$."
        if dealer_value > 21 or player_value > dealer_value:
            return "win", 2, desc + f"✅ Победа. Ты выиграл {bet * 2:,}$."
        if player_value == dealer_value:
            return "draw", 1, desc + "🤝 Ничья. Ставка возвращена."
        return "lose", 0, desc + f"❌ Проигрыш. Ты потерял {bet:,}$."

    @staticmethod
    def roulette(bet: int, bet_type: str, value: str = None) -> tuple[str, int, str]:
        number = random.randint(0, 36)
        color = "green" if number == 0 else ("red" if number in [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36] else "black")
        color_label = {"red": "красное", "black": "чёрное", "green": "зелёное"}[color]

        desc = f"🎡 Выпало: **{number} ({color_label})**\n\n"

        won = False
        multiplier = 0
        if bet_type == "number" and value and int(value) == number:
            multiplier = 35
            won = True
        elif bet_type == "color" and value and value.lower() == color:
            multiplier = 2
            won = True
        elif bet_type == "even" and number % 2 == 0 and number != 0:
            multiplier = 2
            won = True
        elif bet_type == "odd" and number % 2 == 1:
            multiplier = 2
            won = True
        elif bet_type == "low" and 1 <= number <= 18:
            multiplier = 2
            won = True
        elif bet_type == "high" and 19 <= number <= 36:
            multiplier = 2
            won = True

        if won:
            return "win", multiplier, desc + f"✅ Победа. Выигрыш: {bet * multiplier:,}$ (x{multiplier})."
        return "lose", 0, desc + f"❌ Проигрыш. Потеряно: {bet:,}$."

    @staticmethod
    def slots(bet: int) -> tuple[str, int, str]:
        symbols = ["🍒", "🍋", "🔔", "💎", "✨", "💰", "7️⃣"]
        weights = [30, 25, 20, 15, 7, 2, 1]
        reels = random.choices(symbols, weights=weights, k=3)
        desc = f"**[ {reels[0]} | {reels[1]} | {reels[2]} ]**\n\n"

        if reels[0] == reels[1] == reels[2]:
            if reels[0] == "7️⃣":
                return "jackpot", 0, desc + "🎰 СУПЕР-ДЖЕКПОТ! Ты сорвал главный куш."
            multipliers = {"🍒": 5, "🍋": 7, "🔔": 10, "💎": 15, "✨": 25, "💰": 50}
            multiplier = multipliers[reels[0]]
            return "win", multiplier, desc + f"🎉 Джекпот! Выигрыш: {bet * multiplier:,}$."

        if reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
            return "win", 2, desc + f"✅ Два совпадения. Выигрыш: {bet * 2:,}$."

        return "lose", 0, desc + f"❌ Не повезло. Потеряно: {bet:,}$."

    @staticmethod
    def dice(bet: int, prediction: int) -> tuple[str, int, str]:
        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        total = dice1 + dice2
        desc = f"🎲 Кости: **[{dice1}] [{dice2}] = {total}**\n🎯 Твой прогноз: **{prediction}**\n\n"

        if total == prediction:
            return "win", 10, desc + f"✅ Точное попадание. Выигрыш: {bet * 10:,}$ (x10)."
        if abs(total - prediction) == 1:
            return "win", 2, desc + f"✅ Очень близко. Выигрыш: {bet * 2:,}$ (x2)."
        return "lose", 0, desc + f"❌ Мимо. Потеряно: {bet:,}$."

    @staticmethod
    def coinflip(bet: int, choice: str) -> tuple[str, int, str]:
        result = random.choice(["heads", "tails"])
        result_label = "орёл" if result == "heads" else "решка"
        choice_label = "орёл" if choice == "heads" else "решка"
        desc = f"Твой выбор: **{choice_label}**\nВыпало: **{result_label}**\n\n"

        if result == choice:
            return "win", 2, desc + f"✅ Победа. Выигрыш: {bet * 2:,}$."
        return "lose", 0, desc + f"❌ Проигрыш. Потеряно: {bet:,}$."


games = Games()
