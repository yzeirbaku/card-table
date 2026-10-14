import random

from app.murlan.game import Game, RoundResult


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Rotate(random.Random):
    """'Shuffles' by moving the top card to the bottom: 3S ends up last."""

    def shuffle(self, x) -> None:  # type: ignore[override]
        x.append(x.pop(0))


class Reverse(random.Random):
    """'Shuffles' by reversing the deck: jokers first, spades last."""

    def shuffle(self, x) -> None:  # type: ignore[override]
        x.reverse()


def new_game(n: int = 4, rng: random.Random | None = None, clock: FakeClock | None = None) -> Game:
    """Players p0..p{n-1}, p0 created the room."""
    return Game([f"p{i}" for i in range(n)], "p0", rng=rng or random.Random(7),
                clock=clock or FakeClock())


def rig(game: Game, hands: dict[str, list[str]], turn: str, target: int = 13) -> None:
    """Jump into the middle of a round: these hands, `turn` leads."""
    game.target = target
    for p in game.seats:
        game.hands[p] = list(hands.get(p, []))
    game._start_play(turn)


def later_round(n: int = 4, places: list[str] | None = None, rng: random.Random | None = None,
                clock: FakeClock | None = None) -> Game:
    """A game at the start of a later round (phase cutting). The last round
    finished in `places` order; by default p0 won and the last seat lost."""
    game = new_game(n, rng=rng, clock=clock)
    game.target = 13
    game.last_result = RoundResult(list(places or game.seats), [0] * game.side_count)
    game._start_round()
    return game


def swap_ready(hands: dict[str, list[str]], n: int = 4, places: list[str] | None = None) -> Game:
    """A later round just after the deal: these hands, the swap about to start."""
    game = later_round(n, places)
    game.deck = []
    for p in game.seats:
        game.hands[p] = list(hands.get(p, []))
    game._after_deal()
    return game
