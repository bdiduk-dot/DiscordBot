import asyncio
import random

import discord

from config import COLORS
from database import db, get_user_lock
from utils import add_xp, record_player_progress, schedule_message_cleanup


def format_money(value: int) -> str:
    return f"${int(value):,}"


class BlackjackGame:
    CARD_EMOJI = {
        "A": "<:Ace_Card:1486059838403383429>",
        "2": "<:2_Card:1486059993491832942>",
        "3": "<:3_Card:1486060030947102874>",
        "4": "<:4_Card:1486060077759725688>",
        "5": "<:5_Card:1486060145573232783>",
        "6": "<:6_Card:1486060183108190279>",
        "7": "<:7_Card:1486060305841786960>",
        "8": "<:8_Card:1486060362062233610>",
        "9": "<:9_Card:1486060403858346069>",
        "10": "<:10_Card:1486060440651042907>",
        "J": "<:Joker_Card:1486060575212572703>",
        "Q": "<:Queen_Card:1486060536885153842>",
        "K": "<:King_Card:1486060624399302870>",
    }

    def __init__(self, user_id: int, guild_id: int, bet: int, multiplayer: bool = False):
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet = bet
        self.multiplayer = multiplayer
        self.deck = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"] * 4
        random.shuffle(self.deck)
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.finished = False

    def hand_value(self, hand: list[str]) -> int:
        value = sum(11 if card == "A" else 10 if card in "JQK" else int(card) for card in hand)
        aces = hand.count("A")
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def is_natural_blackjack(self, hand: list[str]) -> bool:
        return len(hand) == 2 and self.hand_value(hand) == 21

    def _cards_line(self, hand: list[str]) -> str:
        return " ".join(self.CARD_EMOJI.get(card, "[CARD]") for card in hand)

    def get_game_embed(self, show_dealer: bool = False) -> discord.Embed:
        player_value = self.hand_value(self.player_hand)
        player_cards = self._cards_line(self.player_hand)
        player_faces = " ".join(self.player_hand)
        dealer_visible = self.dealer_hand[0]
        dealer_visible_card = self.CARD_EMOJI.get(dealer_visible, "[CARD]")

        if show_dealer:
            dealer_cards = self._cards_line(self.dealer_hand)
            dealer_faces = " ".join(self.dealer_hand)
            dealer_total = str(self.hand_value(self.dealer_hand))
            dealer_hint = "Карты дилера открыты."
        else:
            dealer_cards = f"{dealer_visible_card} 🂠"
            dealer_faces = f"{dealer_visible} + скрытая"
            dealer_total = "?"
            dealer_hint = f"Открыта первая карта дилера: **{dealer_visible}**"

        embed = discord.Embed(
            title="🃏 БЛЭКДЖЕК",
            description=f"Ставка: **{format_money(self.bet)}**\n{dealer_hint}",
            color=COLORS["info"],
        )
        embed.add_field(
            name="Дилер",
            value=f"{dealer_cards}\nКарты: **{dealer_faces}**\nСумма: **{dealer_total}**",
            inline=False,
        )
        embed.add_field(
            name="Ты",
            value=f"{player_cards}\nКарты: **{player_faces}**\nСумма: **{player_value}**",
            inline=False,
        )
        embed.set_footer(text="Нужно набрать больше дилера, но не перебрать 21.")
        return embed


class MinesGame:
    def __init__(self, user_id: int, bet: int, mines_count: int = 5):
        self.user_id = user_id
        self.bet = bet
        self.mines_count = mines_count
        self.mines = random.sample(range(25), mines_count)
        self.revealed: list[int] = []
        self.active = True
        self.multiplier = 1.0


class BlackjackView(discord.ui.View):
    def __init__(self, game: BlackjackGame):
        super().__init__(timeout=180)
        self.game = game
        self.message: discord.Message | None = None
        self._lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.game.user_id:
            await interaction.response.send_message("Это не твоя игра в блэкджек.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def on_timeout(self):
        if self.game.finished or self.message is None:
            return
        self._disable_buttons()
        try:
            await self.message.edit(view=self)
        except Exception:
            pass
        schedule_message_cleanup(self.message)

    async def _finish_game(self, interaction: discord.Interaction):
        if self.game.finished:
            return

        self.game.finished = True
        self._disable_buttons()
        await interaction.response.defer()

        while self.game.hand_value(self.game.dealer_hand) < 17:
            self.game.dealer_hand.append(self.game.deck.pop())

        user = await db.get_user(self.game.user_id, self.game.guild_id)
        if not user:
            await interaction.followup.send("Не удалось загрузить профиль.", ephemeral=True)
            return

        user.setdefault("game_stats", {})
        user["game_stats"].setdefault("blackjack", {"played": 0, "won": 0})
        user["game_stats"]["blackjack"]["played"] += 1
        user["games_played"] = user.get("games_played", 0) + 1
        user["total_wagered"] = user.get("total_wagered", 0) + self.game.bet
        user["last_game"] = "blackjack"
        user["last_bet"] = self.game.bet

        player_value = self.game.hand_value(self.game.player_hand)
        dealer_value = self.game.hand_value(self.game.dealer_hand)
        player_blackjack = self.game.is_natural_blackjack(self.game.player_hand)
        dealer_blackjack = self.game.is_natural_blackjack(self.game.dealer_hand)
        payout_amount = 0

        if player_value > 21:
            result_text = "Поражение"
            color = COLORS["error"]
            user["total_lost"] = user.get("total_lost", 0) + self.game.bet
            user["win_streak"] = 0
        elif player_blackjack and not dealer_blackjack:
            result_text = "Блэкджек"
            color = COLORS["gold"]
            payout = int(self.game.bet * 2.5)
            payout_amount = payout
            user["balance"] += payout
            user["total_won"] = user.get("total_won", 0) + payout
            user["game_stats"]["blackjack"]["won"] += 1
            user["win_streak"] = user.get("win_streak", 0) + 1
            user["best_streak"] = max(user.get("best_streak", 0), user["win_streak"])

            if user["win_streak"] == 5:
                user["gems"] += 5
            elif user["win_streak"] == 10:
                user["gems"] += 15
            elif user["win_streak"] == 25:
                user["gems"] += 50
            elif user["win_streak"] == 50:
                user["gems"] += 100
        elif dealer_value > 21 or player_value > dealer_value:
            result_text = "Победа"
            color = COLORS["success"]
            payout = self.game.bet * 2
            payout_amount = payout
            user["balance"] += payout
            user["total_won"] = user.get("total_won", 0) + payout
            user["game_stats"]["blackjack"]["won"] += 1
            user["win_streak"] = user.get("win_streak", 0) + 1
            user["best_streak"] = max(user.get("best_streak", 0), user["win_streak"])

            if user["win_streak"] == 5:
                user["gems"] += 5
            elif user["win_streak"] == 10:
                user["gems"] += 15
            elif user["win_streak"] == 25:
                user["gems"] += 50
            elif user["win_streak"] == 50:
                user["gems"] += 100
        elif player_value == dealer_value:
            result_text = "Ничья"
            color = COLORS["info"]
            user["balance"] += self.game.bet
        else:
            result_text = "Поражение"
            color = COLORS["error"]
            user["total_lost"] = user.get("total_lost", 0) + self.game.bet
            user["win_streak"] = 0

        await db.update_user(self.game.user_id, self.game.guild_id, user)
        asyncio.create_task(
            record_player_progress(
                self.game.user_id,
                self.game.guild_id,
                action="play",
                amount=1,
                money=payout_amount,
                games=1,
                wins=1 if result_text in {"Победа", "Блэкджек"} else 0,
            )
        )

        if result_text in {"Победа", "Блэкджек"}:
            await add_xp(self.game.user_id, self.game.guild_id, 20)
            fresh_user = await db.get_user(self.game.user_id, self.game.guild_id)
            if fresh_user:
                user = fresh_user

        embed = self.game.get_game_embed(show_dealer=True)
        embed.color = color
        embed.description = (
            f"Ставка: **{format_money(self.game.bet)}**\n"
            f"Итог: **{result_text}**\n"
            f"Баланс: **{format_money(int(user.get('balance', 0)))}**"
        )
        await interaction.edit_original_response(embed=embed, view=self)
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)

    @discord.ui.button(label="Ещё карту", style=discord.ButtonStyle.success, row=0)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._lock:
            if self.game.finished:
                await interaction.response.send_message("Эта игра уже завершена.", ephemeral=True)
                return

            self.game.player_hand.append(self.game.deck.pop())
            if self.game.hand_value(self.game.player_hand) >= 21:
                await self._finish_game(interaction)
            else:
                await interaction.response.edit_message(embed=self.game.get_game_embed(), view=self)

    @discord.ui.button(label="Стоп", style=discord.ButtonStyle.primary, row=0)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._lock:
            if self.game.finished:
                await interaction.response.send_message("Эта игра уже завершена.", ephemeral=True)
                return
            await self._finish_game(interaction)


class BlackjackPvpGame:
    def __init__(self, challenger: discord.Member, opponent: discord.Member, guild_id: int, bet: int):
        self.guild_id = guild_id
        self.bet = bet
        self.finished = False
        self.deck = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"] * 4
        random.shuffle(self.deck)
        self.players = [
            {
                "id": challenger.id,
                "name": challenger.display_name,
                "mention": challenger.mention,
                "hand": [self.deck.pop(), self.deck.pop()],
                "stood": False,
                "busted": False,
            },
            {
                "id": opponent.id,
                "name": opponent.display_name,
                "mention": opponent.mention,
                "hand": [self.deck.pop(), self.deck.pop()],
                "stood": False,
                "busted": False,
            },
        ]
        self.turn_index = 0

    def hand_value(self, hand: list[str]) -> int:
        value = sum(11 if card == "A" else 10 if card in "JQK" else int(card) for card in hand)
        aces = hand.count("A")
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value

    def current_player(self) -> dict:
        return self.players[self.turn_index]

    def get_player(self, user_id: int):
        for player in self.players:
            if player["id"] == user_id:
                return player
        return None

    def advance_turn(self):
        for _ in range(len(self.players)):
            self.turn_index = (self.turn_index + 1) % len(self.players)
            candidate = self.players[self.turn_index]
            if not candidate["stood"] and not candidate["busted"]:
                return

    def all_locked(self) -> bool:
        return all(player["stood"] or player["busted"] for player in self.players)

    def determine_winner(self):
        valid_players = []
        for player in self.players:
            total = self.hand_value(player["hand"])
            if total <= 21:
                valid_players.append((player, total))

        if not valid_players:
            return None
        if len(valid_players) == 1:
            return valid_players[0][0]
        if valid_players[0][1] == valid_players[1][1]:
            return None
        return max(valid_players, key=lambda item: item[1])[0]

    def get_embed(self, description: str | None = None) -> discord.Embed:
        embed = discord.Embed(
            title="🃏 МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
            description=description
            or (
                f"Ставка с каждого: **{format_money(self.bet)}**\n"
                f"Общий банк: **{format_money(self.bet * 2)}**\n"
                f"Сейчас ходит: **{self.current_player()['name']}**"
            ),
            color=COLORS["info"],
        )

        for index, player in enumerate(self.players, start=1):
            cards = " ".join(BlackjackGame.CARD_EMOJI.get(card, "[CARD]") for card in player["hand"])
            faces = " ".join(player["hand"])
            total = self.hand_value(player["hand"])
            if player["busted"]:
                status = "Перебор"
            elif player["stood"]:
                status = "Остановился"
            elif player["id"] == self.current_player()["id"] and not self.finished:
                status = "Ходит сейчас"
            else:
                status = "Ожидает"

            embed.add_field(
                name=f"Игрок {index} — {player['name']}",
                value=(
                    f"Упоминание: {player['mention']}\n"
                    f"{cards}\n"
                    f"Карты: **{faces}**\n"
                    f"Сумма: **{total}**\n"
                    f"Статус: **{status}**"
                ),
                inline=False,
            )

        embed.set_footer(text="Игроки ходят по очереди. Побеждает тот, кто ближе к 21 без перебора.")
        return embed


class BlackjackPvpInviteView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member, guild_id: int, bet: int):
        super().__init__(timeout=120)
        self.challenger = challenger
        self.opponent = opponent
        self.guild_id = guild_id
        self.bet = bet
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Принять или отклонить вызов может только приглашённый игрок.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        if self.message is not None:
            try:
                embed = discord.Embed(
                    title="🃏 МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
                    description=f"{self.opponent.mention} не ответил на вызов от {self.challenger.mention}.",
                    color=COLORS["warning"],
                )
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass
            schedule_message_cleanup(self.message)

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        first_id, second_id = sorted([self.challenger.id, self.opponent.id])
        async with get_user_lock(first_id):
            async with get_user_lock(second_id):
                challenger_user = await db.get_user(self.challenger.id, self.guild_id)
                opponent_user = await db.get_user(self.opponent.id, self.guild_id)

                if not challenger_user or not opponent_user:
                    for child in self.children:
                        if isinstance(child, discord.ui.Button):
                            child.disabled = True
                    await interaction.response.edit_message(
                        embed=discord.Embed(
                            title="🃏 МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
                            description="Не удалось загрузить профили игроков. Вызов закрыт.",
                            color=COLORS["error"],
                        ),
                        view=self,
                    )
                    return
                if challenger_user.get("balance", 0) < self.bet:
                    for child in self.children:
                        if isinstance(child, discord.ui.Button):
                            child.disabled = True
                    await interaction.response.edit_message(
                        embed=discord.Embed(
                            title="🃏 МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
                            description=f"У {self.challenger.mention} уже не хватает денег на ставку. Вызов закрыт.",
                            color=COLORS["warning"],
                        ),
                        view=self,
                    )
                    return
                if opponent_user.get("balance", 0) < self.bet:
                    for child in self.children:
                        if isinstance(child, discord.ui.Button):
                            child.disabled = True
                    await interaction.response.edit_message(
                        embed=discord.Embed(
                            title="🃏 МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
                            description=f"У {self.opponent.mention} уже не хватает денег на ставку. Вызов закрыт.",
                            color=COLORS["warning"],
                        ),
                        view=self,
                    )
                    return

                challenger_user["balance"] -= self.bet
                opponent_user["balance"] -= self.bet
                await db.update_user(self.challenger.id, self.guild_id, challenger_user)
                await db.update_user(self.opponent.id, self.guild_id, opponent_user)

        game = BlackjackPvpGame(self.challenger, self.opponent, self.guild_id, self.bet)
        view = BlackjackPvpView(game)
        embed = game.get_embed(
            description=(
                f"Игрок 1: {self.challenger.mention}\n"
                f"Игрок 2: {self.opponent.mention}\n"
                f"Ставка с каждого: **{format_money(self.bet)}**\n"
                f"Общий банк: **{format_money(self.bet * 2)}**\n"
                f"Первым ходит: **{game.current_player()['name']}**"
            )
        )
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🃏 МУЛЬТИПЛЕЕР-БЛЭКДЖЕК",
            description=f"{self.opponent.mention} отклонил вызов от {self.challenger.mention}.",
            color=COLORS["warning"],
        )
        await interaction.response.edit_message(embed=embed, view=None)
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)


class BlackjackPvpView(discord.ui.View):
    def __init__(self, game: BlackjackPvpGame):
        super().__init__(timeout=180)
        self.game = game
        self.message: discord.Message | None = None
        self._lock = asyncio.Lock()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in {player["id"] for player in self.game.players}:
            await interaction.response.send_message("Это не твоя дуэль в блэкджек.", ephemeral=True)
            return False
        if self.game.finished:
            await interaction.response.send_message("Эта дуэль уже завершена.", ephemeral=True)
            return False
        if interaction.user.id != self.game.current_player()["id"]:
            await interaction.response.send_message(f"Сейчас ход игрока {self.game.current_player()['name']}.", ephemeral=True)
            return False
        return True

    def _disable_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    def _update_player_stats(self, user: dict, game_name: str, bet: int, *, won: bool = False, draw: bool = False):
        user.setdefault("game_stats", {})
        user["game_stats"].setdefault(game_name, {"played": 0, "won": 0})
        user["game_stats"][game_name]["played"] += 1
        if won:
            user["game_stats"][game_name]["won"] += 1

        user["games_played"] = user.get("games_played", 0) + 1
        user["total_wagered"] = user.get("total_wagered", 0) + bet
        user["last_game"] = game_name
        user["last_bet"] = bet

        if won:
            user["win_streak"] = user.get("win_streak", 0) + 1
            user["best_streak"] = max(user.get("best_streak", 0), user["win_streak"])
            if user["win_streak"] == 5:
                user["gems"] += 5
            elif user["win_streak"] == 10:
                user["gems"] += 15
            elif user["win_streak"] == 25:
                user["gems"] += 50
            elif user["win_streak"] == 50:
                user["gems"] += 100
        elif not draw:
            user["win_streak"] = 0

    async def _refund_players(self, reason: str):
        first_id, second_id = sorted([player["id"] for player in self.game.players])
        async with get_user_lock(first_id):
            async with get_user_lock(second_id):
                for player in self.game.players:
                    user = await db.get_user(player["id"], self.game.guild_id)
                    if not user:
                        continue
                    user["balance"] += self.game.bet
                    await db.update_user(player["id"], self.game.guild_id, user)

        self.game.finished = True
        self._disable_buttons()
        if self.message is not None:
            embed = self.game.get_embed(description=reason)
            embed.color = COLORS["warning"]
            await self.message.edit(embed=embed, view=self)
            schedule_message_cleanup(self.message)

    async def on_timeout(self):
        if self.game.finished:
            return
        try:
            await self._refund_players("Дуэль завершилась по таймауту. Ставки возвращены обоим игрокам.")
        except Exception:
            pass

    async def _finish_game(self, interaction: discord.Interaction):
        if self.game.finished:
            return

        winner = self.game.determine_winner()
        players_by_id = {player["id"]: player for player in self.game.players}
        first_id, second_id = sorted(players_by_id.keys())

        async with get_user_lock(first_id):
            async with get_user_lock(second_id):
                users = {player_id: await db.get_user(player_id, self.game.guild_id) for player_id in players_by_id.keys()}
                if not all(users.values()):
                    await interaction.response.send_message("Не удалось завершить игру: профиль не найден.", ephemeral=True)
                    return

                if winner is None:
                    for player_id, user in users.items():
                        user["balance"] += self.game.bet
                        self._update_player_stats(user, "blackjack_pvp", self.game.bet, draw=True)
                        await db.update_user(player_id, self.game.guild_id, user)
                        asyncio.create_task(
                            record_player_progress(
                                player_id,
                                self.game.guild_id,
                                action="play",
                                amount=1,
                                games=1,
                            )
                        )

                    description = (
                        f"{self.game.players[0]['mention']} vs {self.game.players[1]['mention']}\n"
                        f"Итог: **ничья**\n"
                        f"Обе ставки по **{format_money(self.game.bet)}** возвращены."
                    )
                    color = COLORS["info"]
                else:
                    loser = next(player for player in self.game.players if player["id"] != winner["id"])
                    winner_user = users[winner["id"]]
                    loser_user = users[loser["id"]]

                    winner_user["balance"] += self.game.bet * 2
                    winner_user["total_won"] = winner_user.get("total_won", 0) + self.game.bet * 2
                    loser_user["total_lost"] = loser_user.get("total_lost", 0) + self.game.bet

                    self._update_player_stats(winner_user, "blackjack_pvp", self.game.bet, won=True)
                    self._update_player_stats(loser_user, "blackjack_pvp", self.game.bet, won=False)

                    await db.update_user(winner["id"], self.game.guild_id, winner_user)
                    await db.update_user(loser["id"], self.game.guild_id, loser_user)
                    asyncio.create_task(
                        record_player_progress(
                            winner["id"],
                            self.game.guild_id,
                            action="play",
                            amount=1,
                            money=self.game.bet * 2,
                            games=1,
                            wins=1,
                        )
                    )
                    asyncio.create_task(
                        record_player_progress(
                            loser["id"],
                            self.game.guild_id,
                            action="play",
                            amount=1,
                            games=1,
                        )
                    )
                    await add_xp(winner["id"], self.game.guild_id, 30)

                    description = (
                        f"{winner['mention']} победил в дуэли против {loser['mention']}.\n"
                        f"Выигрыш: **{format_money(self.game.bet * 2)}**\n"
                        f"Банк забран полностью."
                    )
                    color = COLORS["success"]

        self.game.finished = True
        self._disable_buttons()
        embed = self.game.get_embed(description=description)
        embed.color = color
        await interaction.response.edit_message(embed=embed, view=self)
        self.message = interaction.message or self.message
        schedule_message_cleanup(self.message)

    @discord.ui.button(label="Ещё карту", style=discord.ButtonStyle.success, row=0)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._lock:
            player = self.game.get_player(interaction.user.id)
            if player is None:
                await interaction.response.send_message("Игрок не найден в этой дуэли.", ephemeral=True)
                return

            player["hand"].append(self.game.deck.pop())
            total = self.game.hand_value(player["hand"])
            if total > 21:
                player["busted"] = True
            elif total == 21:
                player["stood"] = True

            if player["busted"] or player["stood"]:
                self.game.advance_turn()

            if self.game.all_locked():
                await self._finish_game(interaction)
                return

            await interaction.response.edit_message(embed=self.game.get_embed(), view=self)

    @discord.ui.button(label="Стоп", style=discord.ButtonStyle.primary, row=0)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self._lock:
            player = self.game.get_player(interaction.user.id)
            if player is None:
                await interaction.response.send_message("Игрок не найден в этой дуэли.", ephemeral=True)
                return

            player["stood"] = True
            self.game.advance_turn()

            if self.game.all_locked():
                await self._finish_game(interaction)
                return

            await interaction.response.edit_message(embed=self.game.get_embed(), view=self)


class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Профиль", style=discord.ButtonStyle.primary, custom_id="m_prof")
    async def profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.economy import EconomyCog

        cog = EconomyCog(interaction.client)
        await cog.profile(interaction)


class GamesMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Блэкджек", style=discord.ButtonStyle.success, custom_id="m_bj")
    async def bj(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Используй `/blackjack <ставка|всё>` или `/bj <ставка|всё>`.", ephemeral=True)


class BetModal(discord.ui.Modal):
    def __init__(self, game_type: str):
        super().__init__(title=f"Ставка для {game_type.capitalize()}")
        self.bet = discord.ui.TextInput(label="Сумма", placeholder="100", required=True)
        self.add_item(self.bet)
        self.game_type = game_type

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet.value)
            if bet <= 0:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Введи корректную ставку.", ephemeral=True)
            return

        if self.game_type == "slots":
            from cogs.games_core import GamesCoreCog

            cog = GamesCoreCog(interaction.client)
            await cog.slots(interaction, bet)
