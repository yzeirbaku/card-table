"""Wire format for player actions. Anything that doesn't validate is rejected."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, TypeAdapter

Id = Annotated[str, Field(min_length=1, max_length=64)]


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToPile(_Msg):
    kind: Literal["pile"]
    pile_id: Id


class ToTable(_Msg):
    kind: Literal["table"]
    x: FiniteFloat
    y: FiniteFloat


class ToHand(_Msg):
    kind: Literal["hand"]
    index: int | None = None


class ToPlayer(_Msg):
    kind: Literal["player"]
    player_id: Id


Destination = Annotated[ToPile | ToTable | ToHand | ToPlayer, Field(discriminator="kind")]


class MoveCard(_Msg):
    type: Literal["move_card"]
    card_id: Id
    to: Destination
    face_up: bool | None = None
    # Where the client saw the card: a pile id, or null for "my hand". When sent,
    # the move is rejected if the card has since moved (someone else got there first).
    from_pile_id: Id | None = None


class FlipCard(_Msg):
    type: Literal["flip_card"]
    card_id: Id


class MovePile(_Msg):
    type: Literal["move_pile"]
    pile_id: Id
    x: FiniteFloat
    y: FiniteFloat


class MergePile(_Msg):
    type: Literal["merge_pile"]
    pile_id: Id
    onto_pile_id: Id


class Shuffle(_Msg):
    type: Literal["shuffle"]
    pile_id: Id


class FlipPile(_Msg):
    type: Literal["flip_pile"]
    pile_id: Id


class SetLayout(_Msg):
    type: Literal["set_layout"]
    pile_id: Id
    layout: Literal["stack", "fan"]


class Deal(_Msg):
    type: Literal["deal"]
    pile_id: Id
    count: int = Field(ge=1, le=52)


class TakePile(_Msg):
    type: Literal["take_pile"]
    pile_id: Id


class Gather(_Msg):
    type: Literal["gather"]


class NewDeck(_Msg):
    type: Literal["new_deck"]
    jokers: int = Field(ge=0, le=2)


Action = Annotated[
    MoveCard
    | FlipCard
    | MovePile
    | MergePile
    | Shuffle
    | FlipPile
    | SetLayout
    | Deal
    | TakePile
    | Gather
    | NewDeck,
    Field(discriminator="type"),
]

ACTION_ADAPTER: TypeAdapter[Action] = TypeAdapter(Action)
