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

from .cards import DECK, JOKERS, card_name, power, rank_of, sort_cards, sort_key, suit_of
from .combos import KIND_NAMES, STRAIGHTS, Play, beats, can_beat, classify

TARGETS = (13, 21)
# Points for 1st, 2nd, ... place. In 4-player games a team adds its two players,
# so one team taking 1st and 2nd scores 5 against 1 (and the round ends early).
PLACE_POINTS = {2: (1, 0), 3: (2, 1, 0), 4: (3, 2, 1, 0)}
DEALT = {2: 36, 3: 54, 4: 54}  # 2 players: 18 each, the other 18 are out of play
REVEAL_SECONDS = 5  # how long public reveals (first cards, partners' swap) stay up
PAUSE_SECONDS = 120  # how long a dropped player has to come back before the round is cancelled
SWAP_BACK_RANKS = frozenset({"3", "4", "5", "6", "7", "8", "9", "10"})

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


@dataclass
class Reveal:
    """Cards everyone may see for a few seconds."""

    kind: Literal["first_cards", "swap"]
    cards: dict[str, str]  # player id -> their first card, or the card they gave
    until: float


@dataclass
class Pause:
    deadline: float | None  # None once the countdown has run out
    timed_out: bool = False  # the round was cancelled; the decider picks what's next
    keep_waiting: bool = False  # decided: wait with no countdown


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
        self.pause: Pause | None = None  # set while someone is disconnected
        self.reveal: Reveal | None = None  # cards everyone may see for a few seconds
        self.next_reveal: Reveal | None = None  # waits for the running reveal to end
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
        self.next_reveal = None

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

    def cut(self, player_id: str, index: int) -> None:
        self._check_can_move(player_id)
        self._check_cutter(player_id)
        if self.cut_index is not None:
            raise Rejected("You've already picked a card")
        if not 0 <= index < len(self.deck):
            raise Rejected("Pick a card in the deck")
        self.cut_index = index

    def take_cut(self, player_id: str, take: bool) -> None:
        self._check_can_move(player_id)
        self._check_cutter(player_id)
        if self.cut_index is None:
            raise Rejected("Pick a card first")
        if take:
            i = self.cut_index
            self.deck = self.deck[i:] + self.deck[:i]  # the cut card is dealt first, to the loser
            order = self._deal(player_id)
            first = {p: self.deck[k] for k, p in enumerate(order)}
            self.reveal = Reveal("first_cards", first, self.clock() + REVEAL_SECONDS)
        else:
            self.rng.shuffle(self.deck)  # the loser saw a card: hide where it goes
            self._deal(player_id)
        self.deck = []
        self.cut_index = None
        self._after_deal()

    def give(self, player_id: str, card: str) -> None:
        self._check_can_move(player_id)
        giver = self.swap_giver()
        if giver is None:
            raise Rejected("There's no swap right now")
        if player_id != giver:
            raise Rejected("It's not your turn to give a card")
        if card not in self.swap_choices(player_id):
            if self.swap_step == "loser":
                raise Rejected("Give your highest card")
            raise Rejected("Give back a card from 3 to 10, or your lowest card if you have none")
        self._give(card)
        self._auto_give()

    # ---- disconnects and time ----

    def disconnect(self, player_id: str) -> None:
        if player_id not in self.seats or player_id in self.disconnected:
            return
        self.disconnected.append(player_id)
        if self.phase == "game_over":
            return
        if self.pause is None:
            self.pause = Pause(deadline=self.clock() + PAUSE_SECONDS)
        elif not self.pause.timed_out:  # every new drop gets a full countdown
            self.pause.deadline = self.clock() + PAUSE_SECONDS

    def reconnect(self, player_id: str) -> None:
        if player_id not in self.disconnected:
            return
        self.disconnected.remove(player_id)
        if self.disconnected or self.pause is None:
            return
        timed_out = self.pause.timed_out
        self.pause = None
        if timed_out:  # the round was cancelled: start a fresh one
            if self.target is None:
                self.phase = "choosing_target"
            else:
                self._start_round()

    def decide(self, player_id: str, choice: str) -> None:
        if player_id not in self.seats:
            raise Rejected("You're not playing in this game")
        if not (self.pause and self.pause.timed_out):
            raise Rejected("There's nothing to decide right now")
        if choice == "keep_waiting" and self.pause.keep_waiting:
            raise Rejected("There's nothing to decide right now")
        if player_id != self.decider():
            raise Rejected("The room creator decides")
        if choice == "keep_waiting":
            self.pause.keep_waiting = True
        elif choice == "end_game":
            self.pause = None
            self.phase = "game_over"
            best = max(self.scores)
            self.winner_side = self.scores.index(best) if self.scores.count(best) == 1 else None
        else:
            raise Rejected("Keep waiting or end the game")

    def decider(self) -> str | None:
        """Who chooses for the table: the creator, or if they're away the next
        connected player clockwise."""
        start = self.seats.index(self.creator)
        for k in range(len(self.seats)):
            player = self.seats[(start + k) % len(self.seats)]
            if player not in self.disconnected:
                return player
        return None

    def deadline(self) -> float | None:
        """When tick() next has something to do."""
        times = [self.reveal.until if self.reveal else None,
                 self.next_reveal.until if self.next_reveal else None,
                 self.pause.deadline if self.pause else None]
        return min((t for t in times if t is not None), default=None)

    def tick(self) -> None:
        now = self.clock()
        while self.reveal and now >= self.reveal.until:
            self.reveal, self.next_reveal = self.next_reveal, None
        if self.pause and self.pause.deadline is not None and now >= self.pause.deadline:
            self.pause.deadline = None
            self.pause.timed_out = True
            self._clear_round()  # the round is cancelled; scores stay as they were
            self.reveal = None
            self.phase = "round_cancelled"

    # ---- checks ----

    def _check_can_move(self, player_id: str) -> None:
        if player_id not in self.seats:
            raise Rejected("You're not playing in this game")
        if self.phase == "game_over":
            raise Rejected("The game is over")
        if self.pause:
            raise Rejected("The game is paused")

    def _check_cutter(self, player_id: str) -> None:
        if self.phase != "cutting":
            raise Rejected("There's no cut right now")
        if player_id != self.last_result.loser:
            raise Rejected("Only the loser cuts")

    def _check_turn(self, player_id: str) -> None:
        self._check_can_move(player_id)
        if self.phase != "playing":
            raise Rejected("It's not time to play cards")
        if player_id != self.turn:
            raise Rejected("It's not your turn")

    # ---- the swap: loser gives the winner their highest card, winner gives one back ----

    def teammates(self, a: str, b: str) -> bool:
        return len(self.seats) == 4 and a != b and self.side_of(a) == self.side_of(b)

    def swap_giver(self) -> str | None:
        if self.phase != "swapping":
            return None
        result = self.last_result
        return result.loser if self.swap_step == "loser" else result.winner

    def swap_choices(self, player_id: str) -> list[str]:
        """The cards `player_id` may give right now; empty unless it's their turn to give."""
        if player_id != self.swap_giver():
            return []
        hand = self.hands[player_id]
        if self.swap_step == "loser":
            best = max(power(c) for c in hand)
            return [c for c in hand if power(c) == best]
        back = [c for c in hand if rank_of(c) in SWAP_BACK_RANKS]
        if back:
            return back
        lowest = min(power(c) for c in hand)
        return [c for c in hand if power(c) == lowest]

    def _after_deal(self) -> None:
        result = self.last_result
        if all(j in self.hands[result.loser] for j in JOKERS):
            self._start_play(result.winner)  # no swap, and the winner leads
            return
        self.phase = "swapping"
        self.swap_step = "loser"
        self._auto_give()

    def _auto_give(self) -> None:
        """A giver with only one allowed card gives it without being asked."""
        while (giver := self.swap_giver()) is not None:
            choices = self.swap_choices(giver)
            if len(choices) != 1:
                return
            self._give(choices[0])

    def _give(self, card: str) -> None:
        result = self.last_result
        if self.swap_step == "loser":
            giver, receiver = result.loser, result.winner
        else:
            giver, receiver = result.winner, result.loser
        self.hands[giver].remove(card)
        self.hands[receiver] = sort_cards(self.hands[receiver] + [card])
        self.swap_given[giver] = card
        if self.swap_step == "loser":
            self.swap_step = "winner"
            return
        if self.teammates(result.winner, result.loser):
            now = self.clock()
            if self.reveal and now < self.reveal.until:  # the first cards are still up: wait
                self.next_reveal = Reveal("swap", dict(self.swap_given),
                                          self.reveal.until + REVEAL_SECONDS)
            else:
                self.reveal = Reveal("swap", dict(self.swap_given), now + REVEAL_SECONDS)
        self._start_play(result.loser)

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
        already out, the next player clockwise who still has cards leads. A player
        with nothing that beats the pile passes without being asked."""
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
                top = self.top
                if top is not None and not can_beat(self.hands[player], top):
                    self.passed.append(player)
                    continue
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
