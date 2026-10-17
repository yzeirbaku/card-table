"""Whole Murlan games between computer players, straight on the Game (no rooms,
no waiting). Each seat only ever sees its own view."""

import random

from app.murlan.bot import Bot
from app.murlan.combos import classify
from app.murlan.game import Game
from app.murlan.moves import legal_plays
from app.murlan.protocol import apply_action
from app.murlan.views import view_for
from tests.murlan_helpers import FakeClock


class Naive(Bot):
    """Plays its lowest legal play every time and passes only when it can't play."""

    def _play(self, view):
        pile = view["pile"]
        top = None if not pile or view["pile_won"] else classify(pile[-1]["cards"])
        legal = legal_plays(view["hand"], top, view["must_include"])
        return min(legal, key=lambda cards: (classify(cards).rank, -len(cards))) if legal else None


def play_game(players: int, seed: int, target: int | None = None, kinds=None, max_moves: int = 20000):
    """Plays one game out. `kinds` gives each seat's player class (default: all Bot).
    Returns the finished game and the results of every round."""
    rng = random.Random(seed)
    clock = FakeClock()
    seats = [f"p{i}" for i in range(players)]
    game = Game(seats, "p0", rng=rng, clock=clock)
    kinds = kinds or [Bot] * players
    bots = {p: kind(p, random.Random(seed * 10 + i)) for i, (p, kind) in enumerate(zip(seats, kinds))}
    game.choose_target("p0", target or game.targets()[0])  # default: the shortest race
    rounds = []
    seen_rounds = 0
    for _ in range(max_moves):
        if game.phase == "game_over":
            break
        for p, bot in bots.items():
            bot.observe(view_for(game, p))
        if game.rounds_played != seen_rounds:
            seen_rounds = game.rounds_played
            rounds.append(game.last_result)
        if game.phase == "playing" and game.reveal:  # no one plays while cards are up, as in a room
            clock.now = game.reveal.until
            game.tick()
            continue
        mover = next((p for p, bot in bots.items() if bot.needs_to_act(view_for(game, p))), None)
        assert mover is not None, f"nobody can move in phase {game.phase}"
        action = bots[mover].act(view_for(game, mover))
        apply_action(game, mover, action)  # a refused move raises Rejected: the test fails
        clock.now += 1
        game.tick()
    else:
        raise AssertionError("the game didn't end")
    if game.rounds_played != seen_rounds:
        rounds.append(game.last_result)
    return game, rounds
