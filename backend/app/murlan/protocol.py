"""Murlan moves on the wire. Anything that doesn't validate is rejected."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from .game import Game, Rejected

CardCode = Annotated[str, Field(min_length=2, max_length=3)]
Id = Annotated[str, Field(min_length=1, max_length=64)]


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChooseTarget(_Msg):
    type: Literal["choose_target"]
    target: Literal[13, 21]


class Cut(_Msg):
    type: Literal["cut"]
    index: int = Field(ge=0, le=53)


class TakeCut(_Msg):
    type: Literal["take_cut"]
    take: bool


class Give(_Msg):
    type: Literal["give"]
    card: CardCode


class PlayCards(_Msg):
    type: Literal["play"]
    cards: list[CardCode] = Field(min_length=1, max_length=54)


class Pass(_Msg):
    type: Literal["pass"]


class PickLoser(_Msg):
    type: Literal["pick_loser"]
    player_id: Id


class Decide(_Msg):
    type: Literal["decide"]
    choice: Literal["keep_waiting", "end_game"]


Action = Annotated[
    ChooseTarget | Cut | TakeCut | Give | PlayCards | Pass | PickLoser | Decide,
    Field(discriminator="type"),
]
ACTION_ADAPTER: TypeAdapter[Action] = TypeAdapter(Action)


def apply_action(game: Game, player_id: str, raw: object) -> None:
    try:
        action = ACTION_ADAPTER.validate_python(raw)
    except ValidationError:
        raise Rejected("Malformed action") from None
    match action:
        case ChooseTarget():
            game.choose_target(player_id, action.target)
        case Cut():
            game.cut(player_id, action.index)
        case TakeCut():
            game.take_cut(player_id, action.take)
        case Give():
            game.give(player_id, action.card)
        case PlayCards():
            game.play(player_id, action.cards)
        case Pass():
            game.pass_turn(player_id)
        case PickLoser():
            game.pick_loser(player_id, action.player_id)
        case Decide():
            game.decide(player_id, action.choice)
