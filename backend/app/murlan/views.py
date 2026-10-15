"""What one player may see of a Murlan game: the ONLY way game state leaves the
server. Other players' hands (not even how many cards they hold), the face-down
deck and out-of-play cards are never included. A card code reaches a player only
if it's in their own hand, on the pile, in a public reveal that is still running,
or the cut card shown to the cutter."""

import math
from typing import Any

from .game import Game


def view_for(game: Game, player_id: str) -> dict[str, Any]:
    view: dict[str, Any] = {
        "phase": game.phase,
        "target": game.target,
        "round": game.rounds_played + 1,
        "seats": list(game.seats),
        "creator": game.creator,
        "decider": game.decider(),
        "sides": [{"players": game.side_players(i), "score": score}
                  for i, score in enumerate(game.scores)],
        "hand": list(game.hands.get(player_id, [])),
        "turn": game.turn,
        "pile": [{"player_id": p, "cards": list(cards), "kind": play.kind}
                 for p, cards, play in game.trick],
        "pile_won": game.trick_won,  # the pile is a won trick: the next play leads
        "passed": list(game.passed),
        "places": list(game.places),
        "must_include": game.must_include if game.turn == player_id else None,
        "last_round": None,
        "winner_side": game.winner_side,
        "cut": None,
        "swap": None,
        "agree": None,
        "reveal": None,
        "pause": None,
    }
    if game.last_result:
        view["last_round"] = {"places": list(game.last_result.places),
                              "points": list(game.last_result.points),
                              "out": game.last_result.out,
                              # the round's last trick: it was face up on the pile
                              "pile": [{"player_id": p, "cards": list(cards)}
                                       for p, cards in game.last_result.pile]}
    if game.phase == "cutting":
        cutter = game.last_result.loser
        shown = player_id == cutter and game.cut_index is not None
        view["cut"] = {
            "cutter": cutter,
            "deck_size": len(game.deck),
            "index": game.cut_index,
            "card": game.deck[game.cut_index] if shown else None,
        }
    giver = game.swap_giver()
    if giver is not None:
        result = game.last_result
        view["swap"] = {
            "giver": giver,
            "receiver": result.winner if giver == result.loser else result.loser,
            "choices": game.swap_choices(player_id),
        }
    if game.phase == "agreeing_loser":
        view["agree"] = {"voters": game.loser_voters(), "picks": dict(game.agree_picks)}
    if game.reveal and game.clock() < game.reveal.until:
        view["reveal"] = {"kind": game.reveal.kind,
                          "cards": {p: list(codes) for p, codes in game.reveal.cards.items()}}
    if game.pause:
        deadline = game.pause.deadline
        view["pause"] = {
            "waiting_for": list(game.disconnected),
            "seconds_left": None if deadline is None else max(0, math.ceil(deadline - game.clock())),
            "timed_out": game.pause.timed_out,
            "keep_waiting": game.pause.keep_waiting,
        }
    return view
