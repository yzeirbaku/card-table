import random

from app.murlan.game import Game


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
