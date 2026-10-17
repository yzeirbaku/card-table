"""A computer player for Murlan. It decides from what its seat may see: the view
`views.view_for` gives it (the same one a browser gets), plus its memory of what
it has been shown this round (every play, every thrown hand). It never looks at
the game itself, so it can't know anyone else's cards.

How it plays: it splits its hand into as few plays as it can (straights, bombs,
triples, pairs, singles), each weighed by how likely it is to win its trick given
the cards it hasn't seen. Leading, it gets rid of straights and weak plays first
and keeps strong ones to win tricks back; following, it beats the pile when that
helps its plan without spending a strong card too early, fights harder when an
opponent is close to going out, and leaves its partner's plays alone.

At the end, when only it and one opponent still hold cards at a table of 3 or 4,
it knows the opponent's hand (every card it hasn't seen) and plays it out in its head.

That is how it plays at "hard". Its level makes it slip: "medium" and "easy" now and
then make a worse play than their best, forget some of the cards they saw, and
"easy" also misses an opponent about to go out, now and then beats its partner, and
gives any card it may in the swap."""

import random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .cards import DECK, JOKERS, RANKS, power, rank_of
from .combos import STRAIGHTS, Play, classify
from .moves import by_rank, legal_plays, straight_runs

ENDGAME_CARDS = 14  # it plays the end out in its head once the two hands hold this many cards or fewer
ENDGAME_BUDGET = 3000  # new positions it may look at for one move (about 0.04 s a thousand here): past that it plays as usual
UNIT_COST = 0.3  # each play the hand still needs, on top of how likely it is to lose its trick
WEAK = 0.99  # a play less likely than this to win its trick is one to get rid of
# Following with a strong card while the hand is still long costs this much of its strength. Not
# with 2 players: there a pass just hands the one opponent the lead. (Tuned in self-play.)
SAVE_EARLY = {2: 0.0, 3: 0.6, 4: 0.6}
SAVE_LATE = {2: 0.0, 3: 0.2, 4: 0.2}
BOMB_SAVE = 0.3  # a bomb is kept for when it matters
DANGER = 2  # an opponent with this many cards or fewer could go out any moment
REACT_CHANCE = 0.35  # an emoji now and then at something it saw, not every time
_DEALT_4 = (14, 14, 13, 13)  # by dealing order


@dataclass(frozen=True)
class Level:
    mistakes: float  # how often a play is a worse option than its best
    memory: float  # the share of the cards it sees played that it remembers
    watchful: bool  # plays harder when an opponent is close to going out
    loyal: float  # how often it leaves its partner's trick alone
    careful_give: bool  # in the swap, gives the card its hand misses least (else any it may)
    solves_endgames: bool  # with one opponent left, it plays the end out in its head


LEVELS = {
    "easy": Level(mistakes=0.15, memory=0.4, watchful=False, loyal=0.9, careful_give=False, solves_endgames=False),
    "medium": Level(mistakes=0.12, memory=0.6, watchful=True, loyal=1.0, careful_give=True, solves_endgames=False),
    "hard": Level(mistakes=0.0, memory=1.0, watchful=True, loyal=1.0, careful_give=True, solves_endgames=True),
}


@dataclass
class Memory:
    """What this seat has seen of the current round."""

    played: dict[str, set[str]] = field(default_factory=dict)  # player id -> cards they've put down
    seen: set[str] = field(default_factory=set)  # every card played or thrown face up that it remembers
    forgot: set[str] = field(default_factory=set)  # the ones it saw and forgot
    dealt: dict[str, int] = field(default_factory=dict)  # how many cards each player was dealt


class Bot:
    def __init__(self, player_id: str, rng: random.Random | None = None, level: str = "hard") -> None:
        self.id = player_id
        self.rng = rng or random.Random()
        self.level = LEVELS[level]
        self.memory = Memory()
        self._phase: str | None = None
        self._top: tuple | None = None  # the newest play on the pile at the last reaction check
        self._round: int | None = None  # the round at the last reaction check
        self._reacted_in: int | None = None  # the round it last sent an emoji in: one a round at most
        self._solver: tuple[int, "_Solver"] | None = None  # the round, and the endgame it has worked out in it
        self._mood = random.Random(player_id)  # its own dice for emojis: they never change how it plays

    # ---- memory ----

    def observe(self, view: dict[str, Any]) -> None:
        """Take in a new view: what's been played since the last one."""
        phase = view["phase"]
        if phase in ("swapping", "playing") and self._phase not in ("swapping", "playing"):
            self._new_round(view)  # a new deal
        self._phase = phase
        if phase != "playing":
            return
        for entry in view["pile"]:
            self._saw(entry["player_id"], entry["cards"])
        for player, cards in view["thrown"].items():
            self._saw(player, cards)

    def _new_round(self, view: dict[str, Any]) -> None:
        seats = view["seats"]
        last = view["last_round"]
        first = last["places"][-1] if last else seats[0]  # the deal starts with the last round's loser
        i = seats.index(first)
        order = seats[i:] + seats[:i]
        dealt = _DEALT_4 if len(seats) == 4 else (18,) * len(seats)
        self.memory = Memory(dealt=dict(zip(order, dealt)))

    def _saw(self, player: str, cards: list[str]) -> None:
        self.memory.played.setdefault(player, set()).update(cards)  # how many: it keeps count
        for card in cards:  # which: it may forget
            if card not in self.memory.seen and card not in self.memory.forgot:
                remembers = self.level.memory >= 1 or self.rng.random() < self.level.memory
                (self.memory.seen if remembers else self.memory.forgot).add(card)

    # ---- emojis ----

    def reaction(self, view: dict[str, Any]) -> str | None:
        """Now and then an emoji at something that just happened: its own bomb landing, its
        play being bombed, winning or losing the round. At most one a round."""
        pile = view["pile"]
        top = (view["round"], len(pile), pile[-1]["player_id"], tuple(pile[-1]["cards"])) if pile else None
        new_top, self._top = top != self._top and top is not None, top
        if self._round is not None and view["round"] < self._round:  # a new game
            self._reacted_in = None
        ended = self._round is not None and view["round"] > self._round and view["last_round"]
        self._round = view["round"]
        kind = None
        if ended:
            places = view["last_round"]["places"]
            kind = "laughing" if places[0] == self.id else "angry" if places[-1] == self.id else None
        elif new_top and pile[-1].get("kind") == "bomb":
            if pile[-1]["player_id"] == self.id:
                kind = "laughing"
            elif len(pile) > 1 and pile[-2]["player_id"] == self.id:
                kind = "shocked"
        if kind is None or self._reacted_in == view["round"] - bool(ended) or self._mood.random() >= REACT_CHANCE:
            return None
        self._reacted_in = view["round"] - bool(ended)  # a round's end counts for that round
        return kind

    # ---- what to do ----

    def needs_to_act(self, view: dict[str, Any]) -> bool:
        """Whether this seat has a move to make now (cheap: no thinking)."""
        if view["pause"]:
            return False
        phase = view["phase"]
        if phase == "cutting":
            return view["cut"]["cutter"] == self.id
        if phase == "swapping":
            return bool(view["swap"] and view["swap"]["choices"])
        if phase == "playing":
            return view["turn"] == self.id
        if phase == "agreeing_loser":
            return self._loser_pick(view) is not None
        return False

    def act(self, view: dict[str, Any]) -> dict[str, Any] | None:
        """The move to send now (as a client would), or None if there's nothing to do."""
        if not self.needs_to_act(view):
            return None
        phase = view["phase"]
        if phase == "cutting":
            cut = view["cut"]
            if cut["index"] is None:
                return {"type": "cut", "index": self.rng.randrange(cut["deck_size"])}
            return {"type": "take_cut", "take": cut["card"] in JOKERS}  # a joker might make two: no swap
        if phase == "swapping":
            return {"type": "give", "card": self._give(view)}
        if phase == "agreeing_loser":
            return {"type": "pick_loser", "player_id": self._loser_pick(view)}
        cards = self._play(view)
        return {"type": "pass"} if cards is None else {"type": "play", "cards": cards}

    def _loser_pick(self, view: dict[str, Any]) -> str | None:
        """Go along with the partner's pick; if they haven't picked, offer to be last."""
        agree = view["agree"]
        if not agree or self.id not in agree["voters"]:
            return None
        partner = next(p for p in agree["voters"] if p != self.id)
        pick = agree["picks"].get(partner, self.id)
        return None if agree["picks"].get(self.id) == pick else pick

    def _give(self, view: dict[str, Any]) -> str:
        """Of the cards allowed, the one the hand misses least."""
        hand = view["hand"]
        choices = view["swap"]["choices"]
        if not self.level.careful_give:
            return self.rng.choice(sorted(choices))
        judge = Judge(self._unseen(hand), 1.0)
        return min(choices, key=lambda c: (judge.plan_cost(_without(hand, [c])), power(c)))

    # ---- playing ----

    def _play(self, view: dict[str, Any]) -> list[str] | None:
        hand = view["hand"]
        pile = view["pile"]
        leading = not pile or view["pile_won"]
        top = None if leading else classify(pile[-1]["cards"])
        legal = legal_plays(hand, top, view["must_include"])
        if not legal:
            return None
        for cards in legal:
            if len(cards) == len(hand):
                return cards  # out
        if self.level.solves_endgames:
            solved = self._endgame(view, hand, leading)
            if solved is not _OPEN:
                return solved
        judge = Judge(self._unseen(hand), self._held_share(view, hand))
        opponents = self._opponents_left(view) if self.level.watchful else {}
        closest = min(opponents.values(), default=99)
        if leading:
            best = self._lead(hand, legal, judge, closest, view["must_include"])
        else:
            best = self._follow(hand, legal, judge, view, pile[-1]["player_id"], opponents, closest)
        partners = not leading and best is None and pile[-1]["player_id"] == self._partner(view)
        if partners and self.level.loyal >= 1:
            return best  # leaving the partner's trick alone is no slip to make
        if self.level.mistakes and self.rng.random() < self.level.mistakes:
            return self._slip(hand, legal, judge, leading, best)
        return best

    def _slip(self, hand, legal, judge, leading, best) -> list[str] | None:
        """A worse option than its best, but not a silly one: of the others, one of the three
        that leave its hand plainest, the plainest the likeliest."""
        options = [cards for cards in legal if cards != best] + ([] if leading or best is None else [None])
        if not options:
            return best
        options.sort(key=lambda cards: judge.plan_cost(hand if cards is None else _without(hand, cards)))
        options = options[:3]
        return self.rng.choices(options, weights=(3, 2, 1)[:len(options)])[0]

    def _lead(self, hand, legal, judge, closest, must_include) -> list[str]:
        if must_include:  # the first lead: whatever with that card leaves the best hand
            return min(legal, key=lambda cards: judge.plan_cost(_without(hand, cards)) - 0.01 * len(cards))
        plan = judge.plan(hand)
        if len(plan) == 1:
            return plan[0].cards
        weak = [u for u in plan if u.strength < WEAK]
        if len(weak) <= 1:  # winners and one more: cash the winners, then go out
            return max(plan, key=lambda u: (u.strength >= WEAK, u.strength, len(u.cards))).cards
        straights = [u for u in plan if u.play.kind in STRAIGHTS]
        if straights:  # many cards at once, and rarely beaten
            return max(straights, key=lambda u: (len(u.cards), -u.play.rank)).cards
        avoid = {"single"} if closest <= 1 else {"pair"} if closest == 2 else set()
        options = [u for u in weak if u.play.kind not in avoid]
        if options:
            return min(options, key=lambda u: (u.strength, -len(u.cards), u.play.rank)).cards
        others = [u for u in plan if u.play.kind not in avoid]  # nothing weak they can't answer: play it safe
        return max(others or plan, key=lambda u: u.strength).cards

    def _follow(self, hand, legal, judge, view, top_owner, opponents, closest) -> list[str] | None:
        if top_owner == self._partner(view) and (self.level.loyal >= 1 or self.rng.random() < self.level.loyal):
            return None  # the partner's trick: let them have it
        danger = opponents.get(top_owner, 99) <= DANGER + 1 or closest <= DANGER
        now = judge.plan_cost(hand)
        long_hand = len(judge.plan(hand)) >= 4
        players = len(view["seats"])
        save = 0 if danger else SAVE_EARLY[players] if long_hand else SAVE_LATE[players]
        best, best_value = None, -1.0 if danger else 0.0
        for cards in legal:
            play = classify(cards)
            gain = now - judge.plan_cost(_without(hand, cards))
            spend = judge.strength(play, cards) * save + (BOMB_SAVE if play.kind == "bomb" and not danger else 0)
            value = gain - spend
            if value > best_value:
                best, best_value = cards, value
        return best

    def _endgame(self, view, hand, leading):
        """Only it and one opponent still hold cards, at a table of 3 or 4: every card it
        hasn't seen is in their hand, so it plays the rest out in its head. A play (or None,
        a pass) that wins either way; _OPEN when it can't tell, or it makes no difference."""
        rest = [p for p in view["seats"] if p != self.id and self._cards_left(view, p) > 0]
        if len(view["seats"]) == 2 or len(rest) != 1 or rest[0] == self._partner(view):
            return _OPEN  # with 2 players a third of the deck sits out: their hand isn't known
        pile = view["pile"]
        top = None if leading else tuple(sorted(pile[-1]["cards"]))
        if top is not None and pile[-1]["player_id"] != rest[0]:
            return _OPEN  # the trick is someone's who's out: who leads after it is another story
        theirs = tuple(sorted(self._unseen(hand)))
        if len(theirs) != self._cards_left(view, rest[0]) or len(theirs) + len(hand) > ENDGAME_CARDS:
            return _OPEN
        mine = tuple(sorted(hand))
        if self._solver is None or self._solver[0] != view["round"]:
            self._solver = (view["round"], _Solver())  # what it worked out holds for the rest of the round
        solver = self._solver[1]
        solver.budget = len(solver.memo) + ENDGAME_BUDGET
        win, loses = None, False
        try:
            for move in _moves(mine, top):
                if solver.wins(theirs, *_after(mine, move)):
                    loses = True
                elif win is None:
                    win = (move,)
                if win and loses:  # one that wins and one that doesn't: enough to know it matters
                    return None if win[0] is None else list(win[0])
        except _OutOfTime:
            pass
        return _OPEN  # can't tell in time, every move wins, or none does

    # ---- what it knows ----

    def _unseen(self, hand: list[str]) -> frozenset[str]:
        """Cards that could be in someone else's hand (or, with 2 players, out of play)."""
        return frozenset(DECK) - set(hand) - self.memory.seen

    def _cards_left(self, view: dict[str, Any], player: str) -> int:
        if player in view["places"] or player in view["thrown"]:
            return 0
        return self.memory.dealt.get(player, 18) - len(self.memory.played.get(player, ()))

    def _opponents_left(self, view: dict[str, Any]) -> dict[str, int]:
        partner = self._partner(view)
        return {p: n for p in view["seats"] if p not in (self.id, partner)
                if (n := self._cards_left(view, p)) > 0}

    def _held_share(self, view: dict[str, Any], hand: list[str]) -> float:
        """How likely an unseen card is in an opponent's hand (with 2 players, 18 cards sit out)."""
        unseen = len(self._unseen(hand))
        held = sum(self._cards_left(view, p) for p in view["seats"] if p != self.id)
        return min(1.0, held / unseen) if unseen else 1.0

    def _partner(self, view: dict[str, Any]) -> str | None:
        seats = view["seats"]
        return seats[(seats.index(self.id) + 2) % 4] if len(seats) == 4 else None


@dataclass(frozen=True)
class Unit:
    play: Play
    cards: list[str]
    strength: float  # how likely it is to win its trick


class Judge:
    """Weighs plays against the cards still unseen, and plans a hand into plays."""

    def __init__(self, unseen: frozenset[str], held_share: float) -> None:
        self.unseen = Counter(rank_of(c) for c in unseen if c not in JOKERS)
        self.unseen_jokers = [j for j in JOKERS if j in unseen]
        self.share = held_share
        self._cost = lru_cache(maxsize=None)(self._plan_counts)
        self._runs: dict[tuple[int, tuple[str, ...]], float] = {}

    def strength(self, play: Play, cards: list[str]) -> float:
        p = self.share
        if play.kind == "single":
            higher = sum(n for r, n in self.unseen.items() if power(r + "S") > play.rank)
            higher += sum(1 for j in self.unseen_jokers if power(j) > play.rank)
            return 1 / (1 + higher * p)
        if play.kind in ("pair", "triple", "bomb"):
            size = {"pair": 2, "triple": 3, "bomb": 4}[play.kind]
            chance = {2: {2: .5, 3: .8, 4: 1.0}, 3: {3: .25, 4: .6}, 4: {4: .3}}[size]
            threat = sum(chance.get(n, 0) for r, n in self.unseen.items() if power(r + "S") > play.rank)
            return 1 / (1 + threat * p ** size)
        multiple = STRAIGHTS.index(play.kind) + 1  # only the same length, one step higher, beats it
        answer = any(len(run) == play.length and _run_start(run) == play.rank + 1
                     for run in straight_runs(self.unseen, multiple))
        return 0.7 if answer else 0.97

    def plan(self, hand: list[str]) -> list[Unit]:
        return self._cost(_key(hand), tuple(j for j in JOKERS if j in hand))[1]

    def plan_cost(self, hand: list[str]) -> float:
        return self._cost(_key(hand), tuple(j for j in JOKERS if j in hand))[0] if hand else 0.0

    def _plan_counts(self, key: tuple[tuple[str, tuple[str, ...]], ...], jokers: tuple[str, ...]):
        groups = {r: list(cards) for r, cards in key}
        counts = {r: len(cards) for r, cards in groups.items()}
        runs = [(m, run) for m in (1, 2, 3) for run in straight_runs(counts, m)]
        best = self._best(counts, runs, 0, {})
        units = [self._unit([j]) for j in jokers]
        used = Counter()
        for m, run in best[1]:
            cards = []
            for r in run:
                cards += groups[r][used[r]:used[r] + m]
                used[r] += m
            units.append(self._unit(cards))
        for r, cards in groups.items():
            rest = cards[used[r]:]
            if rest:
                units.append(self._unit(rest))
        return sum(UNIT_COST + 1 - u.strength for u in units), units

    def _best(self, counts: dict[str, int], runs, start: int, memo) -> tuple[float, list]:
        """Cheapest way to take straights out of these counts (the rest goes as same-rank plays)."""
        key = (tuple(sorted((r, n) for r, n in counts.items() if n)), start)
        if key in memo:
            return memo[key]
        best = (self._groups_cost(counts), [])
        for i in range(start, len(runs)):
            m, run = runs[i]
            if all(counts.get(r, 0) >= m for r in run):
                rest = dict(counts)
                for r in run:
                    rest[r] -= m
                cost, chosen = self._best(rest, runs, i, memo)
                cost += UNIT_COST + 1 - self._run_strength(m, run)
                if cost < best[0]:
                    best = (cost, [(m, run)] + chosen)
        memo[key] = best
        return best

    def _groups_cost(self, counts: dict[str, int]) -> float:
        kinds = {1: "single", 2: "pair", 3: "triple", 4: "bomb"}
        return sum(UNIT_COST + 1 - self.strength(Play(kinds[n], power(r + "S"), 1), [])
                   for r, n in counts.items() if n)

    def _run_strength(self, m: int, run: tuple[str, ...]) -> float:
        if (m, run) not in self._runs:
            self._runs[m, run] = self.strength(Play(STRAIGHTS[m - 1], _run_start(run), len(run)), [])
        return self._runs[m, run]

    def _unit(self, cards: list[str]) -> Unit:
        play = classify(cards)
        return Unit(play, cards, self.strength(play, cards))


_OPEN = object()  # the endgame gives no answer


def _moves(hand: tuple[str, ...], top: tuple[str, ...] | None) -> list[tuple[str, ...] | None]:
    """Every play from `hand` on `top` (sorted card tuples), and None (a pass) when there's a top."""
    plays = [tuple(sorted(c)) for c in legal_plays(list(hand), None if top is None else classify(list(top)))]
    return plays + ([None] if top is not None else [])


def _after(hand, move):
    """After `move`, for the other player: (the mover's hand now, the top they face)."""
    if move is None:
        return hand, None  # a pass: the trick is theirs and they lead
    return tuple(c for c in hand if c not in move), move


class _OutOfTime(Exception):
    """The endgame is too big to work out for this move."""


class _Solver:
    """Two open hands, two players: does the one to move go out first? It looks at no more
    positions than `budget` allows in all (it raises _OutOfTime past that); the ones it has
    worked out stay worked out."""

    def __init__(self) -> None:
        self.memo: dict = {}
        self.budget = 0

    def wins(self, mover, other, top) -> bool:
        if not other:
            return False  # the other one just went out
        key = (mover, other, top)
        if key not in self.memo:
            if len(self.memo) >= self.budget:
                raise _OutOfTime
            self.memo[key] = any(not self.wins(other, *_after(mover, move)) for move in _moves(mover, top))
        return self.memo[key]


def _key(hand: list[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((r, tuple(cards)) for r, cards in sorted(by_rank(hand).items(), key=lambda kv: RANKS.index(kv[0])))


def _run_start(run: tuple[str, ...]) -> int:
    return classify([r + "S" for r in run]).rank


def _without(hand: list[str], cards: list[str]) -> list[str]:
    gone = set(cards)
    return [c for c in hand if c not in gone]
