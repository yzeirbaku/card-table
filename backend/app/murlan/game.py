"""One game of Murlan as a state machine. Pure Python: shuffling comes from an
injected RNG and time from an injected clock, so tests drive it without
sleeping. Every move takes the acting player's id and either changes the state
or raises Rejected with a message for that player.

Phases: choosing_target, then per round cutting -> swapping -> playing (the
first round of a game goes straight to playing), agreeing_loser when a
4-player round ends early, game_over at the end. round_cancelled after a pause
runs out. A pause (someone disconnected) sits on top of any phase except
game_over and blocks every move."""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from .cards import DECK, card_name, sort_cards, sort_key, suit_of
from .combos import KIND_NAMES, STRAIGHTS, Play, beats, classify

TARGETS = (13, 21)
# Points for 1st, 2nd, ... place. In 4-player games a team adds its two players,
# so one team taking 1st and 2nd scores 5 against 1 (and the round ends early).
PLACE_POINTS = {2: (1, 0), 3: (2, 1, 0), 4: (3, 2, 1, 0)}
DEALT = {2: 36, 3: 54, 4: 54}  # 2 players: 18 each, the other 18 are out of play

Phase = Literal[
    "choosing_target", "cutting", "swapping", "playing", "agreeing_loser",
    "round_cancelled", "game_over",
]


class Rejected(Exception):
    """A move that isn't allowed. The message is shown to the player who tried it."""


@dataclass
class RoundResult:
    places: list[str]  # player ids, 1st place first; the last one is the loser
    points: list[int]  # what each side scored this round

    @property
    def winner(self) -> str:
        return self.places[0]

    @property
    def loser(self) -> str:
        return self.places[-1]


class Game:
    def __init__(
        self,
        seats: list[str],
        creator: str,
        *,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if len(seats) not in PLACE_POINTS:
            raise ValueError("Murlan is for 2 to 4 players")
        if creator not in seats:
            raise ValueError("The creator must have a seat")
        self.seats = list(seats)  # clockwise
        self.creator = creator
        self.rng = rng or random.SystemRandom()
        self.clock = clock
        self.phase: Phase = "choosing_target"
        self.target: int | None = None
        self.scores = [0] * self.side_count
        self.rounds_played = 0
        self.last_result: RoundResult | None = None
        self.winner_side: int | None = None
        self.disconnected: list[str] = []
        self.pause = None  # set while someone is disconnected
        self.reveal = None  # cards everyone may see for a few seconds
        self._clear_round()

    def _clear_round(self) -> None:
        self.hands: dict[str, list[str]] = {p: [] for p in self.seats}
        self.deck: list[str] = []  # face down, waiting for the cut
        self.cut_index: int | None = None
        self.swap_step: Literal["loser", "winner"] | None = None
        self.swap_given: dict[str, str] = {}  # giver -> the card they gave
        self.turn: str | None = None
        self.trick: list[tuple[str, list[str], Play]] = []  # this trick's plays, oldest first
        self.passed: list[str] = []  # who passed since the last play
        self.places: list[str] = []  # who's out this round, in order
        self.must_include: str | None = None  # the first lead of a game must include this
        self.agree_picks: dict[str, str] = {}

    # ---- sides: teams of partners across in 4-player games, else each player ----

    @property
    def side_count(self) -> int:
        return 2 if len(self.seats) == 4 else len(self.seats)

    def side_of(self, player_id: str) -> int:
        i = self.seats.index(player_id)
        return i % 2 if len(self.seats) == 4 else i

    def side_players(self, side: int) -> list[str]:
        return [p for p in self.seats if self.side_of(p) == side]

    @property
    def top(self) -> Play | None:
        return self.trick[-1][2] if self.trick else None

    def loser_voters(self) -> list[str]:
        """The two players who must agree who's last after a 4-player early end."""
        return [p for p in self.seats if p not in self.places]

    # ---- moves ----

    def choose_target(self, player_id: str, target: int) -> None:
        self._check_can_move(player_id)
        if self.phase != "choosing_target":
            raise Rejected("The target is already set")
        if player_id != self.creator:
            raise Rejected("The room creator picks the target")
        if target not in TARGETS:
            raise Rejected("The target is 13 or 21")
        self.target = target
        self._start_round()

    def play(self, player_id: str, cards: list[str]) -> None:
        self._check_turn(player_id)
        hand = self.hands[player_id]
        if len(set(cards)) != len(cards) or not all(c in hand for c in cards):
            raise Rejected("Those cards aren't in your hand")
        play = classify(cards)
        if play is None:
            raise Rejected("Those cards don't make a play")
        if self.must_include and self.must_include not in cards:
            raise Rejected(f"The first play must include the {card_name(self.must_include)}")
        top = self.top
        if top is not None and not beats(play, top):
            raise Rejected(_why_not(play, top))
        for c in cards:
            hand.remove(c)
        self.must_include = None
        self.trick.append((player_id, sort_cards(cards), play))
        self.passed = []
        if not hand:
            self.places.append(player_id)
            if self._round_over():
                self._end_round()
                return
        self._advance()

    def pass_turn(self, player_id: str) -> None:
        self._check_turn(player_id)
        if self.top is None:
            raise Rejected("You lead: play something")
        self.passed.append(player_id)
        self._advance()

    def pick_loser(self, player_id: str, choice: str) -> None:
        self._check_can_move(player_id)
        if self.phase != "agreeing_loser":
            raise Rejected("There's nothing to agree on right now")
        voters = self.loser_voters()
        if player_id not in voters:
            raise Rejected("The other team chooses who's last")
        if choice not in voters:
            raise Rejected("Pick one of the two of you")
        self.agree_picks[player_id] = choice
        if len(self.agree_picks) == 2 and len(set(self.agree_picks.values())) == 1:
            other = next(p for p in voters if p != choice)
            self._finish_round(self.places + [other, choice])

    # ---- checks ----

    def _check_can_move(self, player_id: str) -> None:
        if player_id not in self.seats:
            raise Rejected("You're not playing in this game")
        if self.phase == "game_over":
            raise Rejected("The game is over")
        if self.pause:
            raise Rejected("The game is paused")

    def _check_turn(self, player_id: str) -> None:
        self._check_can_move(player_id)
        if self.phase != "playing":
            raise Rejected("It's not time to play cards")
        if player_id != self.turn:
            raise Rejected("It's not your turn")

    # ---- rounds ----

    def _start_round(self) -> None:
        self._clear_round()
        self.deck = list(DECK)
        self.rng.shuffle(self.deck)
        if self.last_result is None:  # first round of the game: no cut, no swap
            self._deal(self.seats[0])
            self.deck = []
            card = self._first_lead_card()
            self._start_play(next(p for p in self.seats if card in self.hands[p]))
            self.must_include = card
        else:
            self.phase = "cutting"

    def _deal(self, first: str) -> list[str]:
        """Deal the deck clockwise starting with `first`. Returns the dealing order."""
        i = self.seats.index(first)
        order = self.seats[i:] + self.seats[:i]
        for k, card in enumerate(self.deck[: DEALT[len(self.seats)]]):
            self.hands[order[k % len(order)]].append(card)
        for p in self.seats:
            self.hands[p] = sort_cards(self.hands[p])
        return order

    def _first_lead_card(self) -> str:
        """3♠, or with 2 players the lowest spade dealt (3♠ may be out of play).
        If no spade was dealt at all, the lowest card dealt."""
        dealt = [c for hand in self.hands.values() for c in hand]
        spades = [c for c in dealt if suit_of(c) == "S"]
        return min(spades or dealt, key=sort_key)

    def _start_play(self, leader: str) -> None:
        self.phase = "playing"
        self.swap_step = None
        self.turn = leader
        self.trick = []
        self.passed = []
        self.places = []
        self.must_include = None

    def _advance(self) -> None:
        """Next player clockwise. When the turn gets back to whoever made the last
        play (everyone else passed), the pile clears and they lead; if they're
        already out, the next player clockwise who still has cards leads."""
        n = len(self.seats)
        i = self.seats.index(self.turn)
        last = self.trick[-1][0] if self.trick else None
        for _ in range(2 * n):
            i = (i + 1) % n
            player = self.seats[i]
            if player == last:
                self.trick = []
                self.passed = []
                last = None
            if self.hands[player]:
                self.turn = player
                return
        raise AssertionError("nobody has cards left")

    def _round_over(self) -> bool:
        n = len(self.seats)
        if n == 4 and len(self.places) == 2:
            return self.side_of(self.places[0]) == self.side_of(self.places[1])
        return len(self.places) == n - 1

    def _end_round(self) -> None:
        self.turn = None
        if len(self.places) < len(self.seats) - 1:  # 4 players: one team took 1st and 2nd
            self.phase = "agreeing_loser"
            self.agree_picks = {}
            return
        rest = [p for p in self.seats if p not in self.places]
        self._finish_round(self.places + rest)

    def _finish_round(self, order: list[str]) -> None:
        points = [0] * self.side_count
        for place, player in enumerate(order):
            points[self.side_of(player)] += PLACE_POINTS[len(self.seats)][place]
        self.scores = [s + p for s, p in zip(self.scores, points)]
        self.rounds_played += 1
        self.last_result = RoundResult(order, points)
        best = max(self.scores)
        if best >= self.target and self.scores.count(best) == 1:
            self._clear_round()
            self.phase = "game_over"
            self.winner_side = self.scores.index(best)
        else:
            self._start_round()  # also a tie for the lead at the target: one more round


def _why_not(play: Play, top: Play) -> str:
    if top.kind == "bomb":
        return "Only a higher bomb beats a bomb"
    if play.kind != top.kind:
        return f"Play {KIND_NAMES[top.kind]} or a bomb"
    if play.kind in STRAIGHTS:
        return "It must be the same length and exactly one step higher"
    return "That doesn't beat the pile"
