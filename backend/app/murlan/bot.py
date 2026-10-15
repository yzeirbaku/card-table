"""A computer player for Murlan. It decides from what its seat may see: the view
`views.view_for` gives it (the same one a browser gets), plus its memory of what
it has been shown this round (every play, every thrown hand). It never looks at
the game itself, so it can't know anyone else's cards.

How it plays: it splits its hand into as few plays as it can (straights, bombs,
triples, pairs, singles), each weighed by how likely it is to win its trick given
the cards it hasn't seen. Leading, it gets rid of straights and weak plays first
and keeps strong ones to win tricks back; following, it beats the pile when that
helps its plan without spending a strong card too early, fights harder when an
opponent is close to going out, and leaves its partner's plays alone."""

import random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .cards import DECK, JOKERS, RANKS, power, rank_of
from .combos import STRAIGHTS, Play, classify
from .moves import by_rank, legal_plays, straight_runs

UNIT_COST = 0.3  # each play the hand still needs, on top of how likely it is to lose its trick
WEAK = 0.9  # a play less likely than this to win its trick is one to get rid of
# Following with a strong card while the hand is still long costs this much of its strength. Not
# with 2 players: there a pass just hands the one opponent the lead. (Tuned in self-play.)
SAVE_EARLY = {2: 0.0, 3: 0.6, 4: 0.6}
SAVE_LATE = {2: 0.0, 3: 0.2, 4: 0.2}
BOMB_SAVE = 0.3  # a bomb is kept for when it matters
DANGER = 2  # an opponent with this many cards or fewer could go out any moment
_DEALT_4 = (14, 14, 13, 13)  # by dealing order


@dataclass
class Memory:
    """What this seat has seen of the current round."""

    played: dict[str, set[str]] = field(default_factory=dict)  # player id -> cards they've put down
    seen: set[str] = field(default_factory=set)  # every card played or thrown face up
    dealt: dict[str, int] = field(default_factory=dict)  # how many cards each player was dealt


class Bot:
    def __init__(self, player_id: str, rng: random.Random | None = None) -> None:
        self.id = player_id
        self.rng = rng or random.Random()
        self.memory = Memory()
        self._phase: str | None = None

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
        self.memory.played.setdefault(player, set()).update(cards)
        self.memory.seen.update(cards)

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
        judge = Judge(self._unseen(hand), self._held_share(view, hand))
        opponents = self._opponents_left(view)
        closest = min(opponents.values(), default=99)
        if leading:
            return self._lead(hand, legal, judge, closest, view["must_include"])
        return self._follow(hand, legal, judge, view, pile[-1]["player_id"], opponents, closest)

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
        if top_owner == self._partner(view):
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


def _key(hand: list[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    return tuple((r, tuple(cards)) for r, cards in sorted(by_rank(hand).items(), key=lambda kv: RANKS.index(kv[0])))


def _run_start(run: tuple[str, ...]) -> int:
    return classify([r + "S" for r in run]).rank


def _without(hand: list[str], cards: list[str]) -> list[str]:
    gone = set(cards)
    return [c for c in hand if c not in gone]
