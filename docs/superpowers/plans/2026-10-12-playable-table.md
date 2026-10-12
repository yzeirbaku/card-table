# Playable Table (Plan 1 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Friends can create/join a room by 4-letter code on their phones and play freeform with one shared deck — drag, flip, stack, fan, shuffle, deal, pass, hidden hands — with the server keeping hands secret.

**Architecture:** A FastAPI backend holds live rooms in memory. A pure-Python engine applies actions to the table state and builds a per-player view that never contains hidden card identities; a thin WebSocket layer serializes actions per room and broadcasts views. The Expo app renders the server's view, turns gestures into actions, and re-renders from whatever the server sends back (no client-side game logic).

**Tech Stack:** Python 3.12, FastAPI 0.115, pydantic 2, pytest; Expo (latest SDK, TypeScript), react-native-gesture-handler, react-native-reanimated, expo-haptics, expo-secure-store, jest-expo.

**Spec:** `docs/superpowers/specs/2026-10-12-card-table-design.md`

**Scope of this plan:** spec sections *Table model*, *Room engine*, *Rooms*, and the Home + Table screens in freeform mode. **Plan 2** (separate) adds accounts, games library, setups, lobby game picker, rounds/stats, and the Library/Profile screens.

## Global Constraints

- Backend runs as a **single uvicorn worker** — live rooms live in process memory.
- **Hidden card identities never leave the server**: other players' hands are sent only as counts; face-down cards carry no rank/suit. All views are built by `view_for`.
- A card's `id` is re-issued whenever it enters a hand from somewhere other than the same hand, and whenever a pile is shuffled/gathered, so ids can't be used to track hidden cards.
- Room join code: 4 letters from `ABCDEFGHJKLMNPQRSTUVWXYZ`; 2–6 players (max 6); names 1–20 chars after trimming.
- Room expires **2 hours** after last activity.
- Positions are fractions 0–1 of the table size; the server clamps them.
- App uses only Expo Go–compatible libraries (no custom native code).
- Local git only — commit freely, **never push** / create a remote. Git identity is already set in the repo (`Yzeir Baku <yzeirbaku@hotmail.com>`).
- Keep it lean: no CI, no lint gates, no coverage thresholds, no health endpoints.

## Review Focus

1. **Two players grab the same card at once** → the second action is rejected with a message, nothing is duplicated, and the second player's phone snaps back to the server state. *(Task 2 test `test_second_grab_of_same_card_is_rejected`; Task 6 test `test_rejected_action_gets_error_and_fresh_state`)*
2. **A phone locks / switches app mid-game and comes back** → it reconnects to the same seat with the same hand. *(Task 6 test `test_reconnect_with_token_keeps_seat_and_hand`)*
3. **Dealing more cards than the pile has** → deals what's there round-robin, removes the empty pile, no crash. *(Task 3 test `test_deal_more_than_available_deals_what_is_there`)*
4. **7th player, empty name, or a wrong/expired code** → the socket closes with a clear reason the app shows. *(Task 5 tests `test_seventh_player_rejected`, `test_name_validation`; Task 6 tests `test_unknown_room_closes_4404`, `test_room_full_closes_4409`, `test_expired_room_is_gone`)*
5. **Garbage or hostile messages** (bad JSON, NaN coordinates, unknown types, another player's card id, absurd hand index) → error reply, connection stays usable, state unchanged. *(Task 2 tests `test_malformed_actions_rejected`, `test_cannot_move_another_players_hand_card`, `test_hand_index_is_clamped`; Task 6 test `test_malformed_messages_get_errors_and_connection_survives`)*

---

## File Structure

```
card-table/
├── .gitignore
├── CLAUDE.md                         orientation + invariants (Task 12)
├── README.md                         how to run (Task 12)
├── backend/
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml                pytest config
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   FastAPI app: POST /rooms, WS /rooms/{code}/ws
│   │   ├── rooms.py                  Room, Player, RoomManager (codes, seats, tokens, host, expiry)
│   │   └── engine/
│   │       ├── __init__.py
│   │       ├── cards.py              Card, make_deck, new_card_id
│   │       ├── state.py              Pile, TableState
│   │       ├── protocol.py           pydantic models for every action
│   │       ├── actions.py            new_table, add/remove_player, apply_action
│   │       └── views.py              view_for (the only way state leaves the server)
│   └── tests/
│       ├── __init__.py
│       ├── helpers.py
│       ├── test_cards_state.py
│       ├── test_card_actions.py
│       ├── test_pile_actions.py
│       ├── test_views.py
│       ├── test_rooms.py
│       └── test_websocket.py
└── app/                              Expo app (created by create-expo-app)
    ├── App.tsx
    ├── .env.example
    └── src/
        ├── config.ts                 server URL helpers
        ├── protocol.ts               wire types (mirror of backend protocol/views)
        ├── seat.ts                   SecureStore: seat token per room, last name
        ├── useRoom.ts                WebSocket hook: connect, reconnect, send, leave
        ├── theme.ts                  colors
        ├── screens/
        │   ├── HomeScreen.tsx
        │   └── TableScreen.tsx       layout, measuring, drag coordination
        └── table/
            ├── geometry.ts           pure: sizes, rects, hit-testing, resolveDrop
            ├── dropAction.ts         pure: drag + drop target → Action
            ├── __tests__/geometry.test.ts
            ├── __tests__/dropAction.test.ts
            ├── CardFace.tsx          card face / back rendering
            ├── PileView.tsx          one pile + its gestures
            ├── HandView.tsx          own hand + its gestures
            ├── PlayersBar.tsx        avatars (drop targets) with hand counts
            └── menus.tsx             pile menu, table menu, toast
```

---

### Task 1: Backend scaffold, cards, table state

**Files:**
- Create: `.gitignore`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pyproject.toml`, `backend/app/__init__.py`, `backend/app/engine/__init__.py`, `backend/app/engine/cards.py`, `backend/app/engine/state.py`, `backend/app/engine/actions.py`, `backend/tests/__init__.py`, `backend/tests/helpers.py`
- Test: `backend/tests/test_cards_state.py`

**Interfaces:**
- Produces:
  - `cards.Card(id: str, rank: str, suit: str | None, face_up: bool = False)` — rank `"A".."K"` or `"JOKER"`; suit `"S"|"H"|"D"|"C"` or `None` for jokers
  - `cards.make_deck(jokers: int = 0) -> list[Card]` (raises `ValueError` outside 0–2)
  - `cards.new_card_id() -> str`
  - `state.Pile(id, x, y, layout="stack", cards=[])` — `cards[-1]` is the top
  - `state.TableState(piles: dict[str, Pile], hands: dict[str, list[Card]], version: int)` — `hands` insertion order is seat order
  - `actions.ActionRejected(Exception)`, `actions.new_pile_id() -> str`, `actions.new_table(jokers=0) -> TableState`, `actions.add_player(state, player_id)`, `actions.remove_player(state, player_id)`
  - `tests/helpers.py`: `card(rank, suit, face_up=False) -> Card`, `put_pile(state, cards, x=0.5, y=0.5, layout="stack") -> Pile`

- [ ] **Step 1: Create scaffold files**

`.gitignore`:
```gitignore
.venv/
__pycache__/
.pytest_cache/
node_modules/
app/.env
```

`backend/requirements.txt`:
```text
fastapi==0.115.6
uvicorn[standard]==0.30.6
pydantic==2.9.2
```

`backend/requirements-dev.txt`:
```text
-r requirements.txt
pytest==8.3.3
httpx==0.27.2
```

`backend/pyproject.toml`:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

`backend/app/__init__.py`, `backend/app/engine/__init__.py`, `backend/tests/__init__.py`: empty files.

Create the venv and install:
```bash
cd backend && py -3.12 -m venv .venv && .venv/Scripts/python -m pip install -q -r requirements-dev.txt
```

- [ ] **Step 2: Write the failing tests**

`backend/tests/helpers.py`:
```python
from app.engine.actions import new_pile_id
from app.engine.cards import Card, new_card_id
from app.engine.state import Layout, Pile, TableState


def card(rank: str, suit: str | None, face_up: bool = False) -> Card:
    return Card(new_card_id(), rank, suit, face_up)


def put_pile(
    state: TableState,
    cards: list[Card],
    x: float = 0.5,
    y: float = 0.5,
    layout: Layout = "stack",
) -> Pile:
    pile = Pile(new_pile_id(), x, y, layout, cards)
    state.piles[pile.id] = pile
    return pile
```

`backend/tests/test_cards_state.py`:
```python
import pytest

from app.engine.actions import add_player, new_table, remove_player
from app.engine.cards import make_deck
from tests.helpers import card


def test_standard_deck_has_52_unique_cards():
    deck = make_deck()
    assert len(deck) == 52
    assert len({(c.rank, c.suit) for c in deck}) == 52
    assert len({c.id for c in deck}) == 52


def test_jokers_are_added():
    deck = make_deck(jokers=2)
    assert len(deck) == 54
    assert [c.rank for c in deck].count("JOKER") == 2


def test_joker_count_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_deck(jokers=3)


def test_new_table_is_one_face_down_deck_in_the_center():
    state = new_table()
    (pile,) = state.piles.values()
    assert (pile.x, pile.y) == (0.5, 0.5)
    assert len(pile.cards) == 52
    assert not any(c.face_up for c in pile.cards)
    assert state.hands == {}


def test_add_player_gives_an_empty_hand_in_seat_order():
    state = new_table()
    add_player(state, "ana")
    add_player(state, "ben")
    assert list(state.hands) == ["ana", "ben"]
    assert state.hands["ana"] == []


def test_removed_players_hand_returns_face_down_to_the_center():
    state = new_table()
    add_player(state, "ana")
    held = [card("A", "S", face_up=True), card("K", "H", face_up=True)]
    state.hands["ana"].extend(held)
    remove_player(state, "ana")
    assert "ana" not in state.hands
    returned = [p for p in state.piles.values() if len(p.cards) == 2]
    assert len(returned) == 1
    assert {(c.rank, c.suit) for c in returned[0].cards} == {("A", "S"), ("K", "H")}
    assert not any(c.face_up for c in returned[0].cards)


def test_removing_player_with_empty_hand_adds_no_pile():
    state = new_table()
    add_player(state, "ana")
    remove_player(state, "ana")
    assert len(state.piles) == 1
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: collection errors — `ModuleNotFoundError: No module named 'app.engine.actions'`

- [ ] **Step 4: Implement**

`backend/app/engine/cards.py`:
```python
"""Card identities and decks."""

import secrets
from dataclasses import dataclass

RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["S", "H", "D", "C"]  # spades, hearts, diamonds, clubs
JOKER = "JOKER"


def new_card_id() -> str:
    """Opaque id. Re-issued whenever a card enters a hand or is shuffled, so an
    id seen face up earlier can't be used to track the card once it's hidden."""
    return secrets.token_hex(6)


@dataclass
class Card:
    id: str
    rank: str
    suit: str | None  # None for jokers
    face_up: bool = False


def make_deck(jokers: int = 0) -> list[Card]:
    if not 0 <= jokers <= 2:
        raise ValueError("jokers must be 0, 1 or 2")
    cards = [Card(new_card_id(), rank, suit) for suit in SUITS for rank in RANKS]
    cards += [Card(new_card_id(), JOKER, None) for _ in range(jokers)]
    return cards
```

`backend/app/engine/state.py`:
```python
"""Table state. Everything on the table is a pile; a lone card is a pile of one."""

from dataclasses import dataclass, field
from typing import Literal

from .cards import Card

Layout = Literal["stack", "fan"]


@dataclass
class Pile:
    id: str
    x: float  # pile centre as a fraction (0-1) of table width
    y: float  # ... and of table height
    layout: Layout = "stack"
    cards: list[Card] = field(default_factory=list)  # cards[-1] is the top


@dataclass
class TableState:
    piles: dict[str, Pile] = field(default_factory=dict)
    # player_id -> hand. Insertion order is seat order (used for dealing).
    hands: dict[str, list[Card]] = field(default_factory=dict)
    version: int = 0
```

`backend/app/engine/actions.py`:
```python
"""Apply player actions to a table. Pure logic: no I/O, no clock."""

import secrets

from .cards import Card, make_deck, new_card_id
from .state import Pile, TableState

_rng = secrets.SystemRandom()
CENTER = (0.5, 0.5)


class ActionRejected(Exception):
    """The action is invalid or stale. The message is shown to the player."""


def new_pile_id() -> str:
    return secrets.token_hex(4)


def _shuffled_face_down(cards: list[Card]) -> list[Card]:
    for c in cards:
        c.face_up = False
        c.id = new_card_id()
    _rng.shuffle(cards)
    return cards


def _add_center_pile(state: TableState, cards: list[Card]) -> None:
    pile = Pile(new_pile_id(), *CENTER, cards=cards)
    state.piles[pile.id] = pile


def new_table(jokers: int = 0) -> TableState:
    state = TableState()
    _add_center_pile(state, _shuffled_face_down(make_deck(jokers)))
    return state


def add_player(state: TableState, player_id: str) -> None:
    state.hands.setdefault(player_id, [])
    state.version += 1


def remove_player(state: TableState, player_id: str) -> None:
    cards = state.hands.pop(player_id, [])
    if cards:
        _add_center_pile(state, _shuffled_face_down(cards))
    state.version += 1
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add .gitignore backend
git commit -m "feat(backend): scaffold, cards and table state"
```

---

### Task 2: Action protocol and card actions (move, flip)

**Files:**
- Create: `backend/app/engine/protocol.py`
- Modify: `backend/app/engine/actions.py` (add `apply_action` and card actions)
- Test: `backend/tests/test_card_actions.py`

**Interfaces:**
- Consumes: Task 1 `TableState`, `Pile`, `Card`, `new_card_id`, `new_pile_id`, `ActionRejected`, test helpers.
- Produces:
  - `protocol.py` models (wire format, snake_case JSON): destinations `{"kind":"pile","pile_id"}`, `{"kind":"table","x","y"}`, `{"kind":"hand","index"?}`, `{"kind":"player","player_id"}`; actions with `"type"`: `move_card{card_id,to,face_up?}`, `flip_card{card_id}`, `move_pile{pile_id,x,y}`, `merge_pile{pile_id,onto_pile_id}`, `shuffle{pile_id}`, `flip_pile{pile_id}`, `set_layout{pile_id,layout}`, `deal{pile_id,count 1-52}`, `take_pile{pile_id}`, `gather{}`, `new_deck{jokers 0-2}`
  - `actions.apply_action(state: TableState, player_id: str, raw: object) -> None` — validates, applies, bumps `state.version`; raises `ActionRejected` (state untouched) on anything invalid. Pile actions are added in Task 3; until then they raise `ActionRejected("Unsupported action")`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_card_actions.py`:
```python
import pytest

from app.engine.actions import ActionRejected, add_player, apply_action, new_table
from app.engine.state import TableState
from tests.helpers import card, put_pile


@pytest.fixture
def table() -> TableState:
    state = new_table()
    add_player(state, "ana")
    add_player(state, "ben")
    return state


def deck(state: TableState):
    return max(state.piles.values(), key=lambda p: len(p.cards))


def move(card_id: str, face_up: bool | None = None, **to) -> dict:
    action = {"type": "move_card", "card_id": card_id, "to": to}
    if face_up is not None:
        action["face_up"] = face_up
    return action


def test_top_card_to_empty_table_makes_a_new_pile(table):
    d = deck(table)
    top = d.cards[-1]
    apply_action(table, "ana", move(top.id, kind="table", x=0.2, y=0.3))
    (new,) = [p for p in table.piles.values() if p is not d]
    assert new.cards == [top]
    assert (new.x, new.y) == (0.2, 0.3)
    assert len(d.cards) == 51
    assert top.face_up is False  # table-to-table keeps orientation


def test_only_the_top_card_can_move(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(d.cards[0].id, kind="table", x=0.1, y=0.1))


def test_picking_up_into_hand_reissues_the_card_id(table):
    top = deck(table).cards[-1]
    old_id = top.id
    apply_action(table, "ana", move(old_id, kind="hand"))
    assert table.hands["ana"] == [top]
    assert top.id != old_id


def test_second_grab_of_same_card_is_rejected(table):
    top_id = deck(table).cards[-1].id
    apply_action(table, "ana", move(top_id, kind="hand"))
    with pytest.raises(ActionRejected):
        apply_action(table, "ben", move(top_id, kind="hand"))
    assert table.hands["ben"] == []
    assert len(table.hands["ana"]) == 1


def test_playing_from_hand_lands_face_up_by_default(table):
    c = card("A", "S")
    table.hands["ana"].append(c)
    apply_action(table, "ana", move(c.id, kind="table", x=0.5, y=0.2))
    assert c.face_up is True
    assert table.hands["ana"] == []


def test_playing_from_hand_face_down_on_request(table):
    c = card("A", "S")
    table.hands["ana"].append(c)
    apply_action(table, "ana", move(c.id, face_up=False, kind="table", x=0.5, y=0.2))
    assert c.face_up is False


def test_cannot_move_another_players_hand_card(table):
    c = card("A", "S")
    table.hands["ben"].append(c)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(c.id, kind="table", x=0.5, y=0.5))
    assert table.hands["ben"] == [c]


def test_move_onto_pile_and_emptied_source_pile_disappears(table):
    d = deck(table)
    lone = put_pile(table, [card("K", "H", face_up=True)], 0.2, 0.2)
    apply_action(table, "ana", move(lone.cards[-1].id, kind="pile", pile_id=d.id))
    assert lone.id not in table.piles
    assert d.cards[-1].rank == "K"
    assert len(d.cards) == 53


def test_dropping_onto_its_own_pile_is_rejected(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(d.cards[-1].id, kind="pile", pile_id=d.id))


def test_dropping_onto_a_vanished_pile_is_rejected_and_card_stays(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(d.cards[-1].id, kind="pile", pile_id="gone"))
    assert len(d.cards) == 52


def test_pass_card_to_another_player(table):
    c = card("Q", "D")
    table.hands["ana"].append(c)
    old_id = c.id
    apply_action(table, "ana", move(c.id, kind="player", player_id="ben"))
    assert table.hands["ana"] == []
    assert table.hands["ben"] == [c]
    assert c.id != old_id


def test_pass_to_unknown_player_is_rejected(table):
    c = card("Q", "D")
    table.hands["ana"].append(c)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", move(c.id, kind="player", player_id="zed"))
    assert table.hands["ana"] == [c]


def test_reorder_within_hand_keeps_ids(table):
    a, b, c = card("A", "S"), card("2", "S"), card("3", "S")
    table.hands["ana"].extend([a, b, c])
    ids = (a.id, b.id, c.id)
    apply_action(table, "ana", move(c.id, kind="hand", index=0))
    assert table.hands["ana"] == [c, a, b]
    assert (a.id, b.id, c.id) == ids


def test_hand_index_is_clamped(table):
    a, b = card("A", "S"), card("2", "S")
    table.hands["ana"].extend([a, b])
    apply_action(table, "ana", move(a.id, kind="hand", index=999))
    assert table.hands["ana"] == [b, a]
    apply_action(table, "ana", move(a.id, kind="hand", index=-5))
    assert table.hands["ana"] == [a, b]


def test_flip_top_card(table):
    d = deck(table)
    before = table.version
    apply_action(table, "ana", {"type": "flip_card", "card_id": d.cards[-1].id})
    assert d.cards[-1].face_up is True
    assert table.version == before + 1


def test_flip_non_top_card_is_rejected(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", {"type": "flip_card", "card_id": d.cards[0].id})


def test_coordinates_are_clamped(table):
    top = deck(table).cards[-1]
    apply_action(table, "ana", move(top.id, kind="table", x=5, y=-1))
    pile = next(p for p in table.piles.values() if p.cards == [top])
    assert (pile.x, pile.y) == (1.0, 0.0)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "move_card",
        {},
        {"type": "move_card"},
        {"type": "explode"},
        {"type": "move_card", "card_id": "x", "to": {"kind": "moon"}},
        {"type": "move_card", "card_id": "x", "to": {"kind": "table", "x": float("nan"), "y": 0}},
        {"type": "deal", "pile_id": "x", "count": 0},
    ],
)
def test_malformed_actions_rejected(table, bad):
    before = table.version
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", bad)
    assert table.version == before


def test_player_without_a_seat_is_rejected(table):
    with pytest.raises(ActionRejected):
        apply_action(table, "zed", {"type": "flip_card", "card_id": deck(table).cards[-1].id})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_card_actions.py -q`
Expected: `ImportError: cannot import name 'apply_action'`

- [ ] **Step 3: Implement**

`backend/app/engine/protocol.py`:
```python
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
```

Append to `backend/app/engine/actions.py` (and extend its imports to the block shown):
```python
from pydantic import ValidationError

from .protocol import ACTION_ADAPTER, FlipCard, MoveCard, ToHand, ToPile, ToPlayer, ToTable
```

```python
def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def _pile(state: TableState, pile_id: str) -> Pile:
    pile = state.piles.get(pile_id)
    if pile is None:
        raise ActionRejected("That pile is gone")
    return pile


def _locate(state: TableState, card_id: str) -> tuple[Pile | None, str | None]:
    """(pile, None) if the card is on the table, (None, owner) if in a hand."""
    for pile in state.piles.values():
        if any(c.id == card_id for c in pile.cards):
            return pile, None
    for owner, hand in state.hands.items():
        if any(c.id == card_id for c in hand):
            return None, owner
    return None, None


def apply_action(state: TableState, player_id: str, raw: object) -> None:
    if player_id not in state.hands:
        raise ActionRejected("You are not seated at this table")
    try:
        action = ACTION_ADAPTER.validate_python(raw)
    except ValidationError:
        raise ActionRejected("Invalid action") from None
    match action:
        case MoveCard():
            _move_card(state, player_id, action)
        case FlipCard():
            _flip_card(state, action)
        case _:
            raise ActionRejected("Unsupported action")
    state.version += 1


def _move_card(state: TableState, actor: str, a: MoveCard) -> None:
    source_pile, owner = _locate(state, a.card_id)
    if source_pile is not None:
        if source_pile.cards[-1].id != a.card_id:
            raise ActionRejected("Only the top card of a pile can be moved")
    elif owner != actor:
        # Covers "already gone" and "in someone else's hand" without revealing which.
        raise ActionRejected("That card is no longer there")

    to = a.to
    target: Pile | None = None
    if isinstance(to, ToPile):
        target = _pile(state, to.pile_id)
        if target is source_pile:
            raise ActionRejected("The card is already on that pile")
    elif isinstance(to, ToPlayer) and to.player_id not in state.hands:
        raise ActionRejected("That player has left")

    # Validation done; from here on nothing can fail.
    from_hand = source_pile is None
    if source_pile is not None:
        card = source_pile.cards.pop()
        if not source_pile.cards:
            del state.piles[source_pile.id]
    else:
        hand = state.hands[actor]
        card = hand.pop(next(i for i, c in enumerate(hand) if c.id == a.card_id))

    if isinstance(to, ToHand):
        if not from_hand:
            card.id = new_card_id()
        hand = state.hands[actor]
        index = len(hand) if to.index is None else max(0, min(to.index, len(hand)))
        hand.insert(index, card)
    elif isinstance(to, ToPlayer):
        if not (from_hand and to.player_id == actor):
            card.id = new_card_id()
        state.hands[to.player_id].append(card)
    else:
        if a.face_up is not None:
            card.face_up = a.face_up
        elif from_hand:
            card.face_up = True
        if target is not None:
            target.cards.append(card)
        else:
            assert isinstance(to, ToTable)
            pile = Pile(new_pile_id(), _clamp(to.x), _clamp(to.y), cards=[card])
            state.piles[pile.id] = pile


def _flip_card(state: TableState, a: FlipCard) -> None:
    pile, _ = _locate(state, a.card_id)
    if pile is None or pile.cards[-1].id != a.card_id:
        raise ActionRejected("Only the top card of a pile can be flipped")
    pile.cards[-1].face_up = not pile.cards[-1].face_up
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(engine): action protocol, move and flip cards"
```

---

### Task 3: Pile actions

**Files:**
- Modify: `backend/app/engine/actions.py`
- Test: `backend/tests/test_pile_actions.py`

**Interfaces:**
- Consumes: Task 2 `apply_action`, `_pile`, `_clamp`, `_shuffled_face_down`, `_add_center_pile`, protocol models.
- Produces: `apply_action` handles `move_pile`, `merge_pile`, `shuffle`, `flip_pile`, `set_layout`, `deal` (round-robin in seat order, one card at a time), `take_pile`, `gather` (everything → one shuffled face-down pile in the centre), `new_deck` (fresh deck, all hands emptied).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_pile_actions.py`:
```python
import pytest

from app.engine.actions import ActionRejected, add_player, apply_action, new_table
from app.engine.state import TableState
from tests.helpers import card, put_pile


@pytest.fixture
def table() -> TableState:
    state = new_table()
    add_player(state, "ana")
    add_player(state, "ben")
    return state


def deck(state: TableState):
    return max(state.piles.values(), key=lambda p: len(p.cards))


def test_move_pile_clamps(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "move_pile", "pile_id": d.id, "x": 0.3, "y": 1.7})
    assert (d.x, d.y) == (0.3, 1.0)


def test_merge_puts_pile_on_top_and_removes_it(table):
    d = deck(table)
    small = put_pile(table, [card("A", "S", True), card("K", "H", True)], 0.1, 0.1)
    apply_action(table, "ana", {"type": "merge_pile", "pile_id": small.id, "onto_pile_id": d.id})
    assert small.id not in table.piles
    assert [c.rank for c in d.cards[-2:]] == ["A", "K"]


def test_merge_onto_itself_is_rejected(table):
    d = deck(table)
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", {"type": "merge_pile", "pile_id": d.id, "onto_pile_id": d.id})


def test_shuffle_keeps_cards_turns_them_down_and_reissues_ids(table):
    d = deck(table)
    d.cards[-1].face_up = True
    before_cards = sorted((c.rank, c.suit or "") for c in d.cards)
    before_ids = {c.id for c in d.cards}
    apply_action(table, "ana", {"type": "shuffle", "pile_id": d.id})
    assert sorted((c.rank, c.suit or "") for c in d.cards) == before_cards
    assert not any(c.face_up for c in d.cards)
    assert before_ids.isdisjoint({c.id for c in d.cards})


def test_flip_pile_reverses_order_and_orientation(table):
    a, b = card("A", "S", face_up=True), card("B", "S", face_up=False)
    pile = put_pile(table, [a, b])
    apply_action(table, "ana", {"type": "flip_pile", "pile_id": pile.id})
    assert pile.cards == [b, a]
    assert (b.face_up, a.face_up) == (True, False)


def test_set_layout(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "set_layout", "pile_id": d.id, "layout": "fan"})
    assert d.layout == "fan"


def test_deal_round_robin_to_every_seat(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "deal", "pile_id": d.id, "count": 3})
    assert len(table.hands["ana"]) == 3
    assert len(table.hands["ben"]) == 3
    assert len(d.cards) == 46


def test_deal_reissues_ids(table):
    d = deck(table)
    top_ids = {c.id for c in d.cards[-2:]}
    apply_action(table, "ana", {"type": "deal", "pile_id": d.id, "count": 1})
    dealt = {c.id for hand in table.hands.values() for c in hand}
    assert top_ids.isdisjoint(dealt)


def test_deal_more_than_available_deals_what_is_there(table):
    small = put_pile(table, [card("2", "S"), card("3", "S"), card("4", "S")], 0.2, 0.2)
    apply_action(table, "ben", {"type": "deal", "pile_id": small.id, "count": 5})
    assert len(table.hands["ana"]) == 2
    assert len(table.hands["ben"]) == 1
    assert small.id not in table.piles


def test_take_pile_into_hand(table):
    small = put_pile(table, [card("2", "S"), card("3", "S")], 0.2, 0.2)
    apply_action(table, "ben", {"type": "take_pile", "pile_id": small.id})
    assert [c.rank for c in table.hands["ben"]] == ["2", "3"]
    assert small.id not in table.piles


def test_gather_collects_everything_into_one_face_down_pile(table):
    d = deck(table)
    apply_action(table, "ana", {"type": "deal", "pile_id": d.id, "count": 5})
    put_pile(table, [d.cards.pop()], 0.1, 0.9)
    table.piles[next(iter(table.piles))].cards[-1].face_up = True
    apply_action(table, "ana", {"type": "gather"})
    (pile,) = table.piles.values()
    assert len(pile.cards) == 52
    assert (pile.x, pile.y) == (0.5, 0.5)
    assert not any(c.face_up for c in pile.cards)
    assert all(hand == [] for hand in table.hands.values())


def test_new_deck_with_jokers_resets_table_and_hands(table):
    apply_action(table, "ana", {"type": "deal", "pile_id": deck(table).id, "count": 2})
    apply_action(table, "ana", {"type": "new_deck", "jokers": 2})
    (pile,) = table.piles.values()
    assert len(pile.cards) == 54
    assert all(hand == [] for hand in table.hands.values())
    assert list(table.hands) == ["ana", "ben"]


@pytest.mark.parametrize(
    "action",
    [
        {"type": "move_pile", "pile_id": "gone", "x": 0, "y": 0},
        {"type": "shuffle", "pile_id": "gone"},
        {"type": "deal", "pile_id": "gone", "count": 1},
        {"type": "take_pile", "pile_id": "gone"},
    ],
)
def test_actions_on_vanished_pile_are_rejected(table, action):
    with pytest.raises(ActionRejected):
        apply_action(table, "ana", action)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_pile_actions.py -q`
Expected: failures with `ActionRejected: Unsupported action`

- [ ] **Step 3: Implement**

In `backend/app/engine/actions.py`, extend the protocol import to:
```python
from .protocol import (
    ACTION_ADAPTER,
    Deal,
    FlipCard,
    FlipPile,
    Gather,
    MergePile,
    MoveCard,
    MovePile,
    NewDeck,
    SetLayout,
    Shuffle,
    TakePile,
    ToHand,
    ToPile,
    ToPlayer,
    ToTable,
)
```

Replace the `match` block in `apply_action` with:
```python
    match action:
        case MoveCard():
            _move_card(state, player_id, action)
        case FlipCard():
            _flip_card(state, action)
        case MovePile():
            pile = _pile(state, action.pile_id)
            pile.x, pile.y = _clamp(action.x), _clamp(action.y)
        case MergePile():
            _merge_pile(state, action)
        case Shuffle():
            _shuffled_face_down(_pile(state, action.pile_id).cards)
        case FlipPile():
            pile = _pile(state, action.pile_id)
            pile.cards.reverse()
            for c in pile.cards:
                c.face_up = not c.face_up
        case SetLayout():
            _pile(state, action.pile_id).layout = action.layout
        case Deal():
            _deal(state, action)
        case TakePile():
            pile = _pile(state, action.pile_id)
            for c in pile.cards:
                c.id = new_card_id()
            state.hands[player_id].extend(pile.cards)
            del state.piles[pile.id]
        case Gather():
            _gather(state)
        case NewDeck():
            state.piles.clear()
            for hand in state.hands.values():
                hand.clear()
            _add_center_pile(state, _shuffled_face_down(make_deck(action.jokers)))
    state.version += 1
```

Add below `_flip_card`:
```python
def _merge_pile(state: TableState, a: MergePile) -> None:
    if a.pile_id == a.onto_pile_id:
        raise ActionRejected("Can't stack a pile onto itself")
    source = _pile(state, a.pile_id)
    target = _pile(state, a.onto_pile_id)
    target.cards.extend(source.cards)
    del state.piles[source.id]


def _deal(state: TableState, a: Deal) -> None:
    pile = _pile(state, a.pile_id)
    for _ in range(a.count):
        for seat in state.hands:
            if not pile.cards:
                break
            card = pile.cards.pop()
            card.id = new_card_id()
            state.hands[seat].append(card)
    if not pile.cards:
        del state.piles[pile.id]


def _gather(state: TableState) -> None:
    cards = [c for pile in state.piles.values() for c in pile.cards]
    for hand in state.hands.values():
        cards.extend(hand)
        hand.clear()
    state.piles.clear()
    _add_center_pile(state, _shuffled_face_down(cards))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(engine): pile actions - move, merge, shuffle, flip, fan, deal, take, gather, new deck"
```

---

### Task 4: Per-player views and the hidden-information guarantee

**Files:**
- Create: `backend/app/engine/views.py`
- Test: `backend/tests/test_views.py`

**Interfaces:**
- Consumes: `TableState`, `apply_action`, `ActionRejected`, `new_table`, `add_player`.
- Produces: `views.view_for(state, player_id) -> dict` shaped as
  `{"version": int, "piles": [{"id","x","y","layout","cards":[CardView]}], "hand": [CardView]}` where `CardView` is `{"id","face_up":true,"rank","suit"}` when visible or `{"id","face_up":false}` when not. Own hand cards are always visible and sent with `face_up: true`. Other hands are not included (counts come from the room layer in Task 5).

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_views.py`:
```python
import random

from app.engine.actions import ActionRejected, add_player, apply_action, new_table
from app.engine.state import TableState
from app.engine.views import view_for
from tests.helpers import card, put_pile

PLAYERS = ["ana", "ben", "cai"]


def seated_table() -> TableState:
    state = new_table(jokers=2)
    for p in PLAYERS:
        add_player(state, p)
    return state


def all_card_dicts(view: dict) -> list[dict]:
    return [c for p in view["piles"] for c in p["cards"]] + view["hand"]


def test_face_down_cards_hide_rank_and_suit():
    state = seated_table()
    view = view_for(state, "ana")
    (pile,) = view["piles"]
    assert len(pile["cards"]) == 54
    assert all(set(c) == {"id", "face_up"} and c["face_up"] is False for c in pile["cards"])


def test_face_up_cards_are_visible_to_everyone():
    state = seated_table()
    put_pile(state, [card("Q", "H", face_up=True)], 0.2, 0.2)
    for p in PLAYERS:
        shown = [c for c in all_card_dicts(view_for(state, p)) if c.get("rank") == "Q"]
        assert shown == [{"id": shown[0]["id"], "face_up": True, "rank": "Q", "suit": "H"}]


def test_own_hand_is_visible_and_other_hands_are_absent():
    state = seated_table()
    mine, theirs = card("A", "S"), card("K", "D")
    state.hands["ana"].append(mine)
    state.hands["ben"].append(theirs)
    view = view_for(state, "ana")
    assert view["hand"] == [{"id": mine.id, "face_up": True, "rank": "A", "suit": "S"}]
    assert theirs.id not in {c["id"] for c in all_card_dicts(view)}


def test_view_shape():
    state = seated_table()
    view = view_for(state, "ana")
    assert set(view) == {"version", "piles", "hand"}
    assert set(view["piles"][0]) == {"id", "x", "y", "layout", "cards"}


def random_action(state: TableState, rng: random.Random, actor: str) -> dict:
    piles = list(state.piles.values())
    tops = [p.cards[-1].id for p in piles]
    hand = [c.id for c in state.hands[actor]]
    pile_id = rng.choice(piles).id if piles else "none"

    def dest() -> dict:
        kind = rng.choice(["pile", "table", "hand", "player"])
        if kind == "pile":
            return {"kind": "pile", "pile_id": pile_id}
        if kind == "player":
            return {"kind": "player", "player_id": rng.choice(PLAYERS)}
        if kind == "hand":
            return {"kind": "hand", "index": rng.randint(0, 5)}
        return {"kind": "table", "x": rng.random(), "y": rng.random()}

    options = [
        lambda: {"type": "move_card", "card_id": rng.choice(tops + hand or ["x"]), "to": dest()},
        lambda: {"type": "move_card", "card_id": rng.choice(hand or ["x"]), "to": dest(),
                 "face_up": rng.choice([True, False])},
        lambda: {"type": "flip_card", "card_id": rng.choice(tops or ["x"])},
        lambda: {"type": "flip_pile", "pile_id": pile_id},
        lambda: {"type": "shuffle", "pile_id": pile_id},
        lambda: {"type": "deal", "pile_id": pile_id, "count": rng.randint(1, 4)},
        lambda: {"type": "take_pile", "pile_id": pile_id},
        lambda: {"type": "merge_pile", "pile_id": pile_id, "onto_pile_id": rng.choice(piles).id},
        lambda: {"type": "set_layout", "pile_id": pile_id, "layout": rng.choice(["stack", "fan"])},
        lambda: {"type": "gather"},
    ]
    return rng.choice(options)()


def test_no_view_ever_leaks_hidden_cards():
    """Property test: whatever happens, a player's view only reveals face-up
    table cards and their own hand, and never mentions other hands' card ids."""
    for seed in range(20):
        rng = random.Random(seed)
        state = seated_table()
        for _ in range(150):
            actor = rng.choice(PLAYERS)
            try:
                apply_action(state, actor, random_action(state, rng, actor))
            except ActionRejected:
                pass
            total = sum(len(p.cards) for p in state.piles.values()) + sum(
                len(h) for h in state.hands.values()
            )
            assert total == 54, "cards were lost or duplicated"
            for viewer in PLAYERS:
                view = view_for(state, viewer)
                allowed = {c.id for p in state.piles.values() for c in p.cards if c.face_up}
                allowed |= {c.id for c in state.hands[viewer]}
                others = {c.id for p, h in state.hands.items() if p != viewer for c in h}
                for c in all_card_dicts(view):
                    assert c["id"] not in others
                    if "rank" in c or "suit" in c:
                        assert c["id"] in allowed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_views.py -q`
Expected: `ModuleNotFoundError: No module named 'app.engine.views'`

- [ ] **Step 3: Implement**

`backend/app/engine/views.py`:
```python
"""Per-player views. The ONLY way table state leaves the server: other
players' hands are omitted and face-down cards carry no rank or suit."""

from typing import Any

from .cards import Card
from .state import TableState


def _card(card: Card, visible: bool) -> dict[str, Any]:
    if not visible:
        return {"id": card.id, "face_up": False}
    return {"id": card.id, "face_up": True, "rank": card.rank, "suit": card.suit}


def view_for(state: TableState, player_id: str) -> dict[str, Any]:
    return {
        "version": state.version,
        "piles": [
            {
                "id": p.id,
                "x": p.x,
                "y": p.y,
                "layout": p.layout,
                "cards": [_card(c, c.face_up) for c in p.cards],
            }
            for p in state.piles.values()
        ],
        "hand": [_card(c, True) for c in state.hands.get(player_id, [])],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(engine): per-player views with hidden-information property test"
```

---

### Task 5: Rooms — codes, seats, reconnect tokens, host, expiry

**Files:**
- Create: `backend/app/rooms.py`
- Test: `backend/tests/test_rooms.py`

**Interfaces:**
- Consumes: `new_table`, `add_player`, `remove_player`, `TableState`.
- Produces:
  - `rooms.JoinRejected(code: int, message: str)` — close codes: `4400` bad name, `4409` full
  - `rooms.Player(id, name, token, socket=None)`
  - `rooms.Room` with `code`, `state`, `players: list[Player]`, `host_id`, `last_activity`, `lock: asyncio.Lock`; methods `join(name, token) -> Player`, `leave(player_id)`, `players_view() -> list[dict]` (each `{"id","name","connected","is_host","hand_count"}`)
  - `rooms.RoomManager(clock=time.monotonic)` with `create() -> Room`, `get(code) -> Room | None` (case-insensitive), `touch(room)`, `purge_expired() -> list[Room]`
  - constants `CODE_ALPHABET`, `MAX_PLAYERS = 6`, `IDLE_EXPIRY_SECONDS = 7200`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_rooms.py`:
```python
import pytest

from app.rooms import CODE_ALPHABET, IDLE_EXPIRY_SECONDS, JoinRejected, RoomManager


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_codes_are_four_letters_and_unique():
    manager = RoomManager()
    codes = [manager.create().code for _ in range(50)]
    assert len(set(codes)) == 50
    assert all(len(c) == 4 and set(c) <= set(CODE_ALPHABET) for c in codes)


def test_get_is_case_insensitive():
    manager = RoomManager()
    room = manager.create()
    assert manager.get(room.code.lower()) is room


def test_first_player_is_host_and_gets_a_hand():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    assert room.host_id == ana.id
    assert room.state.hands[ana.id] == []


def test_names_are_trimmed():
    room = RoomManager().create()
    assert room.join("  Ana  ", None).name == "Ana"


@pytest.mark.parametrize("name", ["", "   ", "x" * 21])
def test_name_validation(name):
    room = RoomManager().create()
    with pytest.raises(JoinRejected) as e:
        room.join(name, None)
    assert e.value.code == 4400


def test_reconnect_with_token_returns_the_same_seat():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    again = room.join("whatever", ana.token)
    assert again is ana
    assert len(room.players) == 1


def test_unknown_token_takes_a_new_seat():
    room = RoomManager().create()
    room.join("Ana", None)
    ben = room.join("Ben", "not-a-real-token")
    assert len(room.players) == 2
    assert ben.name == "Ben"


def test_seventh_player_rejected():
    room = RoomManager().create()
    for i in range(6):
        room.join(f"P{i}", None)
    with pytest.raises(JoinRejected) as e:
        room.join("Seventh", None)
    assert e.value.code == 4409


def test_reconnect_still_works_when_full():
    room = RoomManager().create()
    first = room.join("P0", None)
    for i in range(1, 6):
        room.join(f"P{i}", None)
    assert room.join("P0", first.token) is first


def test_leave_returns_hand_and_passes_host_on():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    ben = room.join("Ben", None)
    deck = next(iter(room.state.piles.values()))
    room.state.hands[ana.id].append(deck.cards.pop())
    room.leave(ana.id)
    assert [p.id for p in room.players] == [ben.id]
    assert room.host_id == ben.id
    assert ana.id not in room.state.hands
    assert sum(len(p.cards) for p in room.state.piles.values()) == 52


def test_last_player_leaving_clears_host():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    room.leave(ana.id)
    assert room.host_id is None


def test_players_view():
    room = RoomManager().create()
    ana = room.join("Ana", None)
    ben = room.join("Ben", None)
    room.state.hands[ben.id].append(next(iter(room.state.piles.values())).cards.pop())
    ana.socket = object()
    assert room.players_view() == [
        {"id": ana.id, "name": "Ana", "connected": True, "is_host": True, "hand_count": 0},
        {"id": ben.id, "name": "Ben", "connected": False, "is_host": False, "hand_count": 1},
    ]


def test_idle_rooms_expire_after_two_hours():
    clock = FakeClock()
    manager = RoomManager(clock)
    room = manager.create()
    clock.now += IDLE_EXPIRY_SECONDS
    assert manager.purge_expired() == []
    clock.now += 1
    assert manager.purge_expired() == [room]
    assert manager.get(room.code) is None


def test_activity_keeps_a_room_alive():
    clock = FakeClock()
    manager = RoomManager(clock)
    room = manager.create()
    clock.now += IDLE_EXPIRY_SECONDS - 10
    manager.touch(room)
    clock.now += IDLE_EXPIRY_SECONDS - 10
    assert manager.purge_expired() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_rooms.py -q`
Expected: `ModuleNotFoundError: No module named 'app.rooms'`

- [ ] **Step 3: Implement**

`backend/app/rooms.py`:
```python
"""Live rooms: join codes, seats, reconnect tokens, host, idle expiry.
In memory only - the backend must run as a single worker."""

import asyncio
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .engine.actions import add_player, new_table, remove_player
from .engine.state import TableState

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I/O: easy to read aloud
CODE_LENGTH = 4
MAX_PLAYERS = 6
MAX_NAME_LENGTH = 20
IDLE_EXPIRY_SECONDS = 2 * 60 * 60


class JoinRejected(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Player:
    id: str
    name: str
    token: str  # secret; lets the same phone reclaim this seat after a drop
    socket: Any = None  # the live WebSocket, or None while disconnected


@dataclass
class Room:
    code: str
    last_activity: float
    state: TableState = field(default_factory=new_table)
    players: list[Player] = field(default_factory=list)
    host_id: str | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def join(self, name: str, token: str | None) -> Player:
        if token:
            for p in self.players:
                if secrets.compare_digest(p.token, token):
                    return p
        name = name.strip()
        if not 1 <= len(name) <= MAX_NAME_LENGTH:
            raise JoinRejected(4400, f"Name must be 1-{MAX_NAME_LENGTH} characters")
        if len(self.players) >= MAX_PLAYERS:
            raise JoinRejected(4409, f"Room is full ({MAX_PLAYERS} players)")
        player = Player(id=secrets.token_hex(4), name=name, token=secrets.token_urlsafe(16))
        self.players.append(player)
        add_player(self.state, player.id)
        if self.host_id is None:
            self.host_id = player.id
        return player

    def leave(self, player_id: str) -> None:
        self.players = [p for p in self.players if p.id != player_id]
        remove_player(self.state, player_id)
        if self.host_id == player_id:
            self.host_id = self.players[0].id if self.players else None

    def players_view(self) -> list[dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "connected": p.socket is not None,
                "is_host": p.id == self.host_id,
                "hand_count": len(self.state.hands.get(p.id, [])),
            }
            for p in self.players
        ]


class RoomManager:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self.rooms: dict[str, Room] = {}

    def create(self) -> Room:
        while True:
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if code not in self.rooms:
                break
        room = Room(code=code, last_activity=self._clock())
        self.rooms[code] = room
        return room

    def get(self, code: str) -> Room | None:
        return self.rooms.get(code.upper())

    def touch(self, room: Room) -> None:
        room.last_activity = self._clock()

    def purge_expired(self) -> list[Room]:
        now = self._clock()
        expired = [r for r in self.rooms.values() if now - r.last_activity > IDLE_EXPIRY_SECONDS]
        for r in expired:
            del self.rooms[r.code]
        return expired
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend
git commit -m "feat(backend): rooms with codes, seats, reconnect tokens, host and expiry"
```

---

### Task 6: FastAPI app — create rooms, play over WebSocket

**Files:**
- Create: `backend/app/main.py`
- Test: `backend/tests/test_websocket.py`

**Interfaces:**
- Consumes: `RoomManager`, `Room`, `Player`, `JoinRejected`, `apply_action`, `ActionRejected`, `view_for`.
- Produces (the wire contract the app in Tasks 7–11 relies on):
  - `POST /rooms` → `{"code": "ABCD"}`
  - `WS /rooms/{code}/ws?name=<name>&token=<token?>`
  - Server → client: `{"type":"welcome","player_id","token","code"}` (once, first), then `{"type":"state","code","players":[PlayerView],"view":TableView}` on every change, and `{"type":"error","message"}` (always followed by a fresh `state` to that player when an action was rejected)
  - Client → server: `{"type":"action","action":{...}}`, `{"type":"leave"}`
  - Close codes: `4404` room not found, `4400` bad name, `4409` full, `4410` room expired, `4000` seat opened on another connection, `1000` left
  - `create_app(manager: RoomManager | None = None) -> FastAPI`; module-level `app = create_app()`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_websocket.py`:
```python
import contextlib

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.rooms import IDLE_EXPIRY_SECONDS, RoomManager


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock) -> TestClient:
    return TestClient(create_app(RoomManager(clock)))


def new_room(client: TestClient) -> str:
    res = client.post("/rooms")
    assert res.status_code == 200
    return res.json()["code"]


def join(ws) -> tuple[dict, dict]:
    welcome = ws.receive_json()
    state = ws.receive_json()
    assert welcome["type"] == "welcome"
    assert state["type"] == "state"
    return welcome, state


def deck_id(state: dict) -> str:
    return max(state["view"]["piles"], key=lambda p: len(p["cards"]))["id"]


def act(ws, action: dict) -> None:
    ws.send_json({"type": "action", "action": action})


def test_create_and_join(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        welcome, state = join(ws)
        assert welcome["code"] == code
        assert state["players"] == [
            {"id": welcome["player_id"], "name": "Ana", "connected": True, "is_host": True,
             "hand_count": 0}
        ]
        assert len(state["view"]["piles"]) == 1
        assert state["view"]["hand"] == []


def test_actions_are_broadcast_with_private_hands(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        _, state = join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            assert len(ana.receive_json()["players"]) == 2  # Ben arrived
            act(ana, {"type": "deal", "pile_id": deck_id(state), "count": 2})
            a, b = ana.receive_json(), ben.receive_json()
            assert len(a["view"]["hand"]) == 2
            assert len(b["view"]["hand"]) == 2
            assert {c["id"] for c in a["view"]["hand"]}.isdisjoint(
                {c["id"] for c in b["view"]["hand"]}
            )
            assert [p["hand_count"] for p in a["players"]] == [2, 2]


def test_rejected_action_gets_error_and_fresh_state(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        _, state = join(ws)
        act(ws, {"type": "flip_card", "card_id": "nope"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "top card" in error["message"]
        fresh = ws.receive_json()
        assert fresh["type"] == "state"
        assert fresh["view"]["version"] == state["view"]["version"]


def test_malformed_messages_get_errors_and_connection_survives(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        _, state = join(ws)
        ws.send_text("not json")
        assert ws.receive_json() == {"type": "error", "message": "Malformed message"}
        ws.send_json({"type": "dance"})
        assert ws.receive_json() == {"type": "error", "message": "Unknown message type"}
        ws.send_text('{"type":"action","action":{"type":"move_pile","pile_id":"x","x":NaN,"y":0}}')
        assert ws.receive_json()["type"] == "error"
        ws.receive_json()  # fresh state after rejection
        act(ws, {"type": "shuffle", "pile_id": deck_id(state)})
        assert ws.receive_json()["type"] == "state"


def test_unknown_room_closes_4404(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect("/rooms/ZZZZ/ws?name=Ana") as ws:
            ws.receive_json()
    assert e.value.code == 4404


def test_bad_name_closes_4400(client):
    code = new_room(client)
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/rooms/{code}/ws?name=") as ws:
            ws.receive_json()
    assert e.value.code == 4400


def test_room_full_closes_4409(client):
    code = new_room(client)
    with contextlib.ExitStack() as stack:
        for i in range(6):
            ws = stack.enter_context(client.websocket_connect(f"/rooms/{code}/ws?name=P{i}"))
            join(ws)
        with pytest.raises(WebSocketDisconnect) as e:
            with client.websocket_connect(f"/rooms/{code}/ws?name=Seventh") as ws:
                ws.receive_json()
        assert e.value.code == 4409


def test_reconnect_with_token_keeps_seat_and_hand(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
        welcome, state = join(ws)
        act(ws, {"type": "deal", "pile_id": deck_id(state), "count": 3})
        hand = ws.receive_json()["view"]["hand"]
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana&token={welcome['token']}") as ws:
        again, state = join(ws)
        assert again["player_id"] == welcome["player_id"]
        assert state["view"]["hand"] == hand
        assert len(state["players"]) == 1


def test_disconnected_player_shows_as_not_connected(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()
        update = ana.receive_json()
        assert [p["connected"] for p in update["players"]] == [True, False]


def test_leave_frees_the_seat_and_returns_cards(client):
    code = new_room(client)
    with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ana:
        _, state = join(ana)
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ben") as ben:
            join(ben)
            ana.receive_json()
            act(ana, {"type": "deal", "pile_id": deck_id(state), "count": 2})
            ana.receive_json()
            ben.receive_json()
            ben.send_json({"type": "leave"})
            update = ana.receive_json()
            assert [p["name"] for p in update["players"]] == ["Ana"]
            on_table = sum(len(p["cards"]) for p in update["view"]["piles"])
            assert on_table == 52 - 2  # only Ana's 2 cards are off the table


def test_expired_room_is_gone(client, clock):
    code = new_room(client)
    clock.now += IDLE_EXPIRY_SECONDS + 1
    new_room(client)  # creating a room purges expired ones
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/rooms/{code}/ws?name=Ana") as ws:
            ws.receive_json()
    assert e.value.code == 4404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_websocket.py -q`
Expected: `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Implement**

`backend/app/main.py`:
```python
"""HTTP to create rooms, one WebSocket per player to play. Every action and
broadcast for a room runs under that room's lock, so all players see changes
in the same order."""

import json
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .engine.actions import ActionRejected, apply_action
from .engine.views import view_for
from .rooms import JoinRejected, Player, Room, RoomManager


def create_app(manager: RoomManager | None = None) -> FastAPI:
    rooms = manager or RoomManager()
    app = FastAPI(title="Card Table")

    async def send_state(room: Room, player: Player) -> None:
        if player.socket is None:
            return
        message: dict[str, Any] = {
            "type": "state",
            "code": room.code,
            "players": room.players_view(),
            "view": view_for(room.state, player.id),
        }
        try:
            await player.socket.send_json(message)
        except Exception:  # a dead socket must not break the broadcast
            player.socket = None

    async def broadcast(room: Room) -> None:
        for p in list(room.players):
            await send_state(room, p)

    async def close_expired() -> None:
        for room in rooms.purge_expired():
            for p in room.players:
                if p.socket is not None:
                    with suppress(Exception):
                        await p.socket.close(4410, "Room expired")

    async def handle(room: Room, player: Player, ws: WebSocket, text: str) -> bool:
        """Process one client message. Returns True when the player left."""
        try:
            msg = json.loads(text)
        except ValueError:
            msg = None
        if not isinstance(msg, dict):
            await ws.send_json({"type": "error", "message": "Malformed message"})
            return False
        rooms.touch(room)
        if msg.get("type") == "action":
            try:
                apply_action(room.state, player.id, msg.get("action"))
            except ActionRejected as e:
                await ws.send_json({"type": "error", "message": str(e)})
                await send_state(room, player)
                return False
            await broadcast(room)
            return False
        if msg.get("type") == "leave":
            room.leave(player.id)
            player.socket = None
            with suppress(Exception):
                await ws.close(1000, "Left the room")
            await broadcast(room)
            return True
        await ws.send_json({"type": "error", "message": "Unknown message type"})
        return False

    @app.post("/rooms")
    async def create_room() -> dict[str, str]:
        await close_expired()
        return {"code": rooms.create().code}

    @app.websocket("/rooms/{code}/ws")
    async def room_socket(
        ws: WebSocket, code: str, name: str = "", token: str | None = None
    ) -> None:
        await ws.accept()
        await close_expired()
        room = rooms.get(code)
        if room is None:
            await ws.close(4404, "Room not found")
            return
        async with room.lock:
            try:
                player = room.join(name, token)
            except JoinRejected as e:
                await ws.close(e.code, e.message)
                return
            old, player.socket = player.socket, ws
            if old is not None:
                with suppress(Exception):
                    await old.close(4000, "Opened on another connection")
            rooms.touch(room)
            await ws.send_json(
                {"type": "welcome", "player_id": player.id, "token": player.token,
                 "code": room.code}
            )
            await broadcast(room)
        try:
            while True:
                text = await ws.receive_text()
                async with room.lock:
                    if await handle(room, player, ws, text):
                        break
        except WebSocketDisconnect:
            pass
        finally:
            if player.socket is ws:
                player.socket = None
                async with room.lock:
                    await broadcast(room)

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python -m pytest -q`
Expected: all pass. If `test_disconnected_player_shows_as_not_connected` hangs, the `finally` broadcast isn't running — check the `player.socket is ws` guard.

- [ ] **Step 5: Smoke-run the server**

Run (background): `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
Then: `curl -s -X POST http://localhost:8000/rooms`
Expected: `{"code":"XXXX"}`. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add backend
git commit -m "feat(backend): HTTP room creation and WebSocket play"
```

---

### Task 7: Expo app scaffold, connection, Home screen

**Files:**
- Create (via template): `app/` (blank TypeScript Expo app)
- Create: `app/.env.example`, `app/src/config.ts`, `app/src/protocol.ts`, `app/src/seat.ts`, `app/src/useRoom.ts`, `app/src/theme.ts`, `app/src/screens/HomeScreen.tsx`, `app/src/screens/TableScreen.tsx` (temporary debug version)
- Modify: `app/App.tsx`, `app/package.json` (jest config + test script)

**Interfaces:**
- Consumes: the Task 6 wire contract.
- Produces:
  - `protocol.ts` types: `Suit`, `CardView`, `Layout`, `PileView`, `TableView`, `PlayerView`, `Destination`, `Action`, `ServerMessage` (snake_case fields, matching the backend exactly)
  - `config.ts`: `httpUrl(path)`, `wsUrl(path)`
  - `seat.ts`: `loadSeat(code)`, `saveSeat(code, token)`, `clearSeat(code)`, `loadName()`, `saveName(name)`
  - `useRoom(code, name)` → `{ playerId, players, view, status, fatal, lastError, send(action), leave() }`, `RoomStatus = 'connecting'|'open'|'reconnecting'|'closed'`, `lastError: {message, at} | null`; `send` and `leave` are stable across renders
  - `theme.ts`: `colors`
  - `HomeScreen({ onEnter(code, name) })`, `TableScreen({ code, name, onExit() })`

- [ ] **Step 1: Create the app and install dependencies**

From the repo root:
```bash
npx create-expo-app@latest app --template blank-typescript
```
If `app/.git` was created, delete it (the repo root's git is used). Then:
```bash
cd app
npx expo install react-native-gesture-handler react-native-reanimated react-native-worklets react-native-safe-area-context expo-haptics expo-secure-store
npx expo install jest-expo jest @types/jest -- --save-dev
```

Add to `app/package.json`: in `"scripts"` add `"test": "jest"`, and add a top-level key `"jest": { "preset": "jest-expo" }`.

- [ ] **Step 2: Write config, protocol, seat storage, theme**

`app/.env.example`:
```bash
# Your PC's LAN IP (run `ipconfig`, look for IPv4 Address). Copy to .env.
# Restart `npx expo start` after changing it.
EXPO_PUBLIC_SERVER_URL=http://192.168.1.50:8000
```

`app/src/config.ts`:
```ts
const SERVER_URL = process.env.EXPO_PUBLIC_SERVER_URL ?? 'http://localhost:8000';

export const httpUrl = (path: string) => `${SERVER_URL}${path}`;
export const wsUrl = (path: string) => `${SERVER_URL.replace(/^http/, 'ws')}${path}`;
```

`app/src/protocol.ts`:
```ts
// Mirror of backend/app/engine/protocol.py and views.py. Keep in sync.

export type Suit = 'S' | 'H' | 'D' | 'C';

/** rank/suit are present only when the card is visible to you. */
export type CardView = { id: string; face_up: boolean; rank?: string; suit?: Suit | null };

export type Layout = 'stack' | 'fan';

export type PileView = { id: string; x: number; y: number; layout: Layout; cards: CardView[] };

export type TableView = { version: number; piles: PileView[]; hand: CardView[] };

export type PlayerView = {
  id: string;
  name: string;
  connected: boolean;
  is_host: boolean;
  hand_count: number;
};

export type Destination =
  | { kind: 'pile'; pile_id: string }
  | { kind: 'table'; x: number; y: number }
  | { kind: 'hand'; index?: number }
  | { kind: 'player'; player_id: string };

export type Action =
  | { type: 'move_card'; card_id: string; to: Destination; face_up?: boolean }
  | { type: 'flip_card'; card_id: string }
  | { type: 'move_pile'; pile_id: string; x: number; y: number }
  | { type: 'merge_pile'; pile_id: string; onto_pile_id: string }
  | { type: 'shuffle'; pile_id: string }
  | { type: 'flip_pile'; pile_id: string }
  | { type: 'set_layout'; pile_id: string; layout: Layout }
  | { type: 'deal'; pile_id: string; count: number }
  | { type: 'take_pile'; pile_id: string }
  | { type: 'gather' }
  | { type: 'new_deck'; jokers: number };

export type ServerMessage =
  | { type: 'welcome'; player_id: string; token: string; code: string }
  | { type: 'state'; code: string; players: PlayerView[]; view: TableView }
  | { type: 'error'; message: string };
```

`app/src/seat.ts`:
```ts
import * as SecureStore from 'expo-secure-store';

// Storage failures are never fatal: worst case you rejoin as a new seat.
const seatKey = (code: string) => `seat_${code}`;

export async function loadSeat(code: string): Promise<string | null> {
  try { return await SecureStore.getItemAsync(seatKey(code)); } catch { return null; }
}
export async function saveSeat(code: string, token: string): Promise<void> {
  try { await SecureStore.setItemAsync(seatKey(code), token); } catch { /* ignore */ }
}
export async function clearSeat(code: string): Promise<void> {
  try { await SecureStore.deleteItemAsync(seatKey(code)); } catch { /* ignore */ }
}
export async function loadName(): Promise<string | null> {
  try { return await SecureStore.getItemAsync('name'); } catch { return null; }
}
export async function saveName(name: string): Promise<void> {
  try { await SecureStore.setItemAsync('name', name); } catch { /* ignore */ }
}
```

`app/src/theme.ts`:
```ts
export const colors = {
  felt: '#1f5c3a',
  feltDark: '#143d27',
  text: '#f4f1e8',
  muted: '#a9c2b2',
  accent: '#e8b84a',
  danger: '#d9534f',
  cardFace: '#fbfaf6',
  cardRed: '#c0392b',
  cardBlack: '#1b1b1b',
  cardBack: '#2d4f8a',
  cardBackInner: '#4169a8',
  sheet: '#22332a',
};
```

- [ ] **Step 3: Write the room hook**

`app/src/useRoom.ts`:
```ts
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { wsUrl } from './config';
import type { Action, PlayerView, ServerMessage, TableView } from './protocol';
import { clearSeat, loadSeat, saveSeat } from './seat';

export type RoomStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

/** Close codes after which retrying is pointless (see backend/app/main.py). */
const isFatalClose = (code: number) => code === 4000 || (code >= 4400 && code < 4500);

export function useRoom(code: string, name: string) {
  const [playerId, setPlayerId] = useState<string | null>(null);
  const [players, setPlayers] = useState<PlayerView[]>([]);
  const [view, setView] = useState<TableView | null>(null);
  const [status, setStatus] = useState<RoomStatus>('connecting');
  const [fatal, setFatal] = useState<string | null>(null);
  const [lastError, setLastError] = useState<{ message: string; at: number } | null>(null);

  const socket = useRef<WebSocket | null>(null);
  const attempt = useRef(0);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stopped = useRef(false);

  const connect = useCallback(async () => {
    if (stopped.current) return;
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
    const token = await loadSeat(code);
    if (stopped.current) return;
    const query = `name=${encodeURIComponent(name)}${token ? `&token=${encodeURIComponent(token)}` : ''}`;
    const ws = new WebSocket(wsUrl(`/rooms/${code}/ws?${query}`));
    socket.current = ws;

    ws.onopen = () => {
      attempt.current = 0;
      setStatus('open');
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(String(event.data)) as ServerMessage;
      if (msg.type === 'welcome') {
        setPlayerId(msg.player_id);
        void saveSeat(code, msg.token);
      } else if (msg.type === 'state') {
        setPlayers(msg.players);
        setView(msg.view);
      } else {
        setLastError({ message: msg.message, at: Date.now() });
      }
    };
    ws.onclose = (event) => {
      if (socket.current !== ws) return; // a newer connection replaced this one
      socket.current = null;
      if (stopped.current) return;
      if (isFatalClose(event.code)) {
        setFatal(event.reason || 'Disconnected from the room');
        setStatus('closed');
        return;
      }
      setStatus('reconnecting');
      const delay = Math.min(1000 * 2 ** attempt.current, 10_000);
      attempt.current += 1;
      retryTimer.current = setTimeout(() => void connect(), delay);
    };
  }, [code, name]);

  useEffect(() => {
    stopped.current = false;
    void connect();
    // Phones drop sockets when locked; reconnect as soon as we're back.
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && socket.current === null && !stopped.current) {
        attempt.current = 0;
        void connect();
      }
    });
    return () => {
      stopped.current = true;
      sub.remove();
      if (retryTimer.current) clearTimeout(retryTimer.current);
      socket.current?.close();
      socket.current = null;
    };
  }, [connect]);

  const send = useCallback((action: Action) => {
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'action', action }));
    } else {
      setLastError({ message: 'Not connected - reconnecting…', at: Date.now() });
    }
  }, []);

  const leave = useCallback(() => {
    stopped.current = true;
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'leave' }));
    ws?.close();
    socket.current = null;
    void clearSeat(code);
  }, [code]);

  return { playerId, players, view, status, fatal, lastError, send, leave };
}
```

- [ ] **Step 4: Write the Home screen, a temporary Table screen, and App**

`app/src/screens/HomeScreen.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { httpUrl } from '../config';
import { loadName, saveName } from '../seat';
import { colors } from '../theme';

export default function HomeScreen({ onEnter }: { onEnter: (code: string, name: string) => void }) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadName().then((n) => n && setName(n));
  }, []);

  const trimmed = name.trim();
  const nameOk = trimmed.length >= 1 && trimmed.length <= 20;
  const codeOk = /^[A-Za-z]{4}$/.test(code);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(httpUrl('/rooms'), { method: 'POST' });
      if (!res.ok) throw new Error(String(res.status));
      const body = (await res.json()) as { code: string };
      await saveName(trimmed);
      onEnter(body.code, trimmed);
    } catch {
      setError("Couldn't reach the server. Is it running, and is your phone on the same Wi-Fi?");
    } finally {
      setBusy(false);
    }
  }

  async function join() {
    await saveName(trimmed);
    onEnter(code.toUpperCase(), trimmed);
  }

  return (
    <SafeAreaView style={styles.screen}>
      <Text style={styles.title}>Card Table</Text>
      <TextInput
        style={styles.input}
        placeholder="Your name"
        placeholderTextColor={colors.muted}
        value={name}
        onChangeText={setName}
        maxLength={20}
        autoCorrect={false}
      />
      <Pressable
        style={[styles.button, !(nameOk && !busy) && styles.disabled]}
        disabled={!nameOk || busy}
        onPress={create}
      >
        {busy ? <ActivityIndicator color={colors.feltDark} /> : <Text style={styles.buttonText}>Create room</Text>}
      </Pressable>
      <Text style={styles.or}>or join one</Text>
      <View style={styles.row}>
        <TextInput
          style={[styles.input, styles.codeInput]}
          placeholder="CODE"
          placeholderTextColor={colors.muted}
          value={code}
          onChangeText={(t) => setCode(t.toUpperCase())}
          maxLength={4}
          autoCapitalize="characters"
          autoCorrect={false}
        />
        <Pressable
          style={[styles.button, styles.joinButton, !(nameOk && codeOk) && styles.disabled]}
          disabled={!nameOk || !codeOk}
          onPress={join}
        >
          <Text style={styles.buttonText}>Join</Text>
        </Pressable>
      </View>
      {error && <Text style={styles.error}>{error}</Text>}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.feltDark, padding: 24, justifyContent: 'center', gap: 14 },
  title: { color: colors.text, fontSize: 36, fontWeight: '800', textAlign: 'center', marginBottom: 24 },
  input: {
    backgroundColor: colors.felt, color: colors.text, fontSize: 18,
    borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14,
  },
  codeInput: { flex: 1, letterSpacing: 6, textAlign: 'center', fontWeight: '700' },
  button: { backgroundColor: colors.accent, borderRadius: 12, paddingVertical: 16, alignItems: 'center' },
  joinButton: { paddingHorizontal: 28 },
  buttonText: { color: colors.feltDark, fontSize: 18, fontWeight: '700' },
  disabled: { opacity: 0.4 },
  or: { color: colors.muted, textAlign: 'center', marginTop: 12 },
  row: { flexDirection: 'row', gap: 10 },
  error: { color: colors.danger, textAlign: 'center', marginTop: 8 },
});
```

`app/src/screens/TableScreen.tsx` (temporary — replaced in Task 9):
```tsx
import { Pressable, ScrollView, Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRoom } from '../useRoom';
import { colors } from '../theme';

export default function TableScreen({ code, name, onExit }: { code: string; name: string; onExit: () => void }) {
  const room = useRoom(code, name);
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.feltDark, padding: 16 }}>
      <Text style={{ color: colors.text, fontSize: 28, fontWeight: '800' }}>{code}</Text>
      <Text style={{ color: colors.muted }}>{room.fatal ?? room.status}</Text>
      <ScrollView>
        <Text style={{ color: colors.text, fontFamily: 'Courier' }}>
          {JSON.stringify({ players: room.players, piles: room.view?.piles.length, hand: room.view?.hand }, null, 2)}
        </Text>
      </ScrollView>
      <Pressable onPress={() => { room.leave(); onExit(); }}>
        <Text style={{ color: colors.accent, fontSize: 18 }}>Leave</Text>
      </Pressable>
    </SafeAreaView>
  );
}
```

`app/App.tsx` (replace template content):
```tsx
import { useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import TableScreen from './src/screens/TableScreen';

type Seat = { code: string; name: string };

export default function App() {
  const [seat, setSeat] = useState<Seat | null>(null);
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        {seat ? (
          <TableScreen code={seat.code} name={seat.name} onExit={() => setSeat(null)} />
        ) : (
          <HomeScreen onEnter={(code, name) => setSeat({ code, name })} />
        )}
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
```

- [ ] **Step 5: Type-check**

Run: `cd app && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual check on the phone**

1. Find the PC's LAN IP (`ipconfig` → IPv4), copy `app/.env.example` to `app/.env` with that IP.
2. Start the backend: `cd backend && .venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` (allow Python through Windows Firewall on private networks if prompted).
3. `cd app && npx expo start`, scan the QR with the iPhone camera → opens in Expo Go.
4. Enter a name, tap **Create room** → debug screen shows the code, `open`, one player, `piles: 1`.
5. Lock the phone 30 s, unlock → status returns to `open`, still one player (same seat).
6. Tap **Leave** → back on Home.

- [ ] **Step 7: Commit**

```bash
git add app .gitignore
git commit -m "feat(app): Expo scaffold, room connection hook, home screen"
```

---

### Task 8: Table geometry and drop logic (pure, tested)

**Files:**
- Create: `app/src/table/geometry.ts`, `app/src/table/dropAction.ts`
- Test: `app/src/table/__tests__/geometry.test.ts`, `app/src/table/__tests__/dropAction.test.ts`

**Interfaces:**
- Consumes: `protocol.ts` types.
- Produces:
  - `geometry.ts`: types `Rect {x,y,width,height}`, `Point {x,y}`, `Size {width,height}`, `Regions {table: Rect; hand: Rect; avatars: {playerId: string; rect: Rect}[]}`, `DropTarget`, `DragSource`; constants `HAND_PADDING = 8`, `HAND_TOP = 12`; functions `contains(r, p)`, `cardSize(tableWidth): Size`, `fanStep(pile, tableWidth, card): number`, `pileOffset(pile, table: Size, card): Rect` (relative to table), `pileRect(pile, table: Rect, card): Rect` (window coords), `toTableFraction(p, table: Rect, card): Point`, `handStep(count, handWidth, card): number`, `handIndexAt(px, count, hand: Rect, card): number`, `resolveDrop(p, source, regions, piles, selfId, card): DropTarget`
  - `DragSource = { kind: 'card'; cardId: string; fromPileId: string | null } | { kind: 'pile'; pileId: string }` (`fromPileId: null` = from own hand)
  - `DropTarget = { kind: 'hand' } | { kind: 'player'; playerId: string } | { kind: 'pile'; pileId: string } | { kind: 'table'; x: number; y: number } | null`
  - `dropAction.ts`: `toAction(source: DragSource, target: DropTarget, piles: PileView[], handIndex: number): Action | null`

- [ ] **Step 1: Write the failing tests**

`app/src/table/__tests__/geometry.test.ts`:
```ts
import {
  cardSize, contains, fanStep, handIndexAt, handStep, pileRect, resolveDrop, toTableFraction,
  type Regions,
} from '../geometry';
import type { PileView } from '../../protocol';

const table = { x: 10, y: 100, width: 360, height: 400 };
const card = { width: 60, height: 84 };
const pile = (id: string, x: number, y: number, n = 1, layout: 'stack' | 'fan' = 'stack'): PileView => ({
  id, x, y, layout, cards: Array.from({ length: n }, (_, i) => ({ id: `${id}-${i}`, face_up: false })),
});
const regions: Regions = {
  table,
  hand: { x: 0, y: 520, width: 380, height: 110 },
  avatars: [
    { playerId: 'me', rect: { x: 0, y: 50, width: 80, height: 40 } },
    { playerId: 'ben', rect: { x: 90, y: 50, width: 80, height: 40 } },
  ],
};

test('contains is inclusive', () => {
  expect(contains(table, { x: 10, y: 100 })).toBe(true);
  expect(contains(table, { x: 9, y: 100 })).toBe(false);
});

test('cardSize scales with table width within bounds', () => {
  expect(cardSize(360)).toEqual({ width: 60, height: 84 });
  expect(cardSize(1000).width).toBe(64);
  expect(cardSize(100).width).toBe(40);
});

test('fanStep is 0 for stacks and keeps a fan on the table', () => {
  expect(fanStep(pile('a', 0.5, 0.5, 5), 360, card)).toBe(0);
  expect(fanStep(pile('a', 0.2, 0.5, 3, 'fan'), 360, card)).toBeCloseTo(60 * 0.28);
  const wide = pile('a', 0.5, 0.5, 52, 'fan');
  const step = fanStep(wide, 360, card);
  expect(0.5 * 360 - 30 + 60 + step * 51).toBeLessThanOrEqual(360 + 0.001);
});

test('pileRect is centred on the pile position in window coordinates', () => {
  expect(pileRect(pile('a', 0.5, 0.5), table, card)).toEqual({ x: 160, y: 258, width: 60, height: 84 });
});

test('toTableFraction keeps the card fully on the table', () => {
  expect(toTableFraction({ x: 190, y: 300 }, table, card)).toEqual({ x: 0.5, y: 0.5 });
  const corner = toTableFraction({ x: 0, y: 0 }, table, card);
  expect(corner.x).toBeCloseTo(30 / 360);
  expect(corner.y).toBeCloseTo(42 / 400);
});

test('hand layout and index', () => {
  expect(handStep(1, 380, card)).toBe(0);
  expect(handStep(3, 380, card)).toBe(54); // 0.9 * 60 fits
  expect(handStep(40, 380, card)).toBeCloseTo((380 - 16 - 60) / 39);
  const hand = regions.hand;
  expect(handIndexAt(0, 3, hand, card)).toBe(0);
  expect(handIndexAt(8 + 30 + 54, 3, hand, card)).toBe(1);
  expect(handIndexAt(9999, 3, hand, card)).toBe(2);
  expect(handIndexAt(50, 1, hand, card)).toBe(0);
});

describe('resolveDrop', () => {
  const piles = [pile('deck', 0.5, 0.5, 40), pile('other', 0.2, 0.2, 1)];
  const fromDeck = { kind: 'card' as const, cardId: 'deck-39', fromPileId: 'deck' };

  test('hand region wins', () => {
    expect(resolveDrop({ x: 100, y: 560 }, fromDeck, regions, piles, 'me', card)).toEqual({ kind: 'hand' });
  });
  test('other players avatar, never your own', () => {
    expect(resolveDrop({ x: 120, y: 70 }, fromDeck, regions, piles, 'me', card)).toEqual({ kind: 'player', playerId: 'ben' });
    expect(resolveDrop({ x: 20, y: 70 }, fromDeck, regions, piles, 'me', card)).toBeNull();
  });
  test('onto another pile', () => {
    const p = { x: 10 + 0.2 * 360, y: 100 + 0.2 * 400 };
    expect(resolveDrop(p, fromDeck, regions, piles, 'me', card)).toEqual({ kind: 'pile', pileId: 'other' });
  });
  test('card dropped back on its own pile cancels', () => {
    expect(resolveDrop({ x: 190, y: 300 }, fromDeck, regions, piles, 'me', card)).toBeNull();
  });
  test('pile dragged over itself moves instead', () => {
    const t = resolveDrop({ x: 200, y: 310 }, { kind: 'pile', pileId: 'deck' }, regions, piles, 'me', card);
    expect(t?.kind).toBe('table');
  });
  test('empty table spot', () => {
    expect(resolveDrop({ x: 300, y: 450 }, fromDeck, regions, piles, 'me', card)).toEqual({
      kind: 'table', x: (300 - 10) / 360, y: (450 - 100) / 400,
    });
  });
  test('outside everything cancels', () => {
    expect(resolveDrop({ x: 500, y: 10 }, fromDeck, regions, piles, 'me', card)).toBeNull();
  });
});
```

`app/src/table/__tests__/dropAction.test.ts`:
```ts
import { toAction } from '../dropAction';
import type { PileView } from '../../protocol';

const piles: PileView[] = [
  { id: 'deck', x: 0.5, y: 0.5, layout: 'stack', cards: [{ id: 'a', face_up: false }, { id: 'b', face_up: false }] },
  { id: 'one', x: 0.2, y: 0.2, layout: 'stack', cards: [{ id: 'c', face_up: true, rank: 'A', suit: 'S' }] },
];
const card = { kind: 'card' as const, cardId: 'b', fromPileId: 'deck' };
const deck = { kind: 'pile' as const, pileId: 'deck' };
const single = { kind: 'pile' as const, pileId: 'one' };

test('null target means no action', () => {
  expect(toAction(card, null, piles, 0)).toBeNull();
});

test('card drops', () => {
  expect(toAction(card, { kind: 'hand' }, piles, 2)).toEqual({ type: 'move_card', card_id: 'b', to: { kind: 'hand', index: 2 } });
  expect(toAction(card, { kind: 'player', playerId: 'ben' }, piles, 0)).toEqual({ type: 'move_card', card_id: 'b', to: { kind: 'player', player_id: 'ben' } });
  expect(toAction(card, { kind: 'pile', pileId: 'one' }, piles, 0)).toEqual({ type: 'move_card', card_id: 'b', to: { kind: 'pile', pile_id: 'one' } });
  expect(toAction(card, { kind: 'table', x: 0.1, y: 0.9 }, piles, 0)).toEqual({ type: 'move_card', card_id: 'b', to: { kind: 'table', x: 0.1, y: 0.9 } });
});

test('pile drops', () => {
  expect(toAction(deck, { kind: 'hand' }, piles, 0)).toEqual({ type: 'take_pile', pile_id: 'deck' });
  expect(toAction(deck, { kind: 'player', playerId: 'ben' }, piles, 0)).toBeNull();
  expect(toAction(deck, { kind: 'pile', pileId: 'one' }, piles, 0)).toEqual({ type: 'merge_pile', pile_id: 'deck', onto_pile_id: 'one' });
  expect(toAction(deck, { kind: 'table', x: 0.3, y: 0.4 }, piles, 0)).toEqual({ type: 'move_pile', pile_id: 'deck', x: 0.3, y: 0.4 });
});

test('a single-card pile behaves like its card for hand and players', () => {
  expect(toAction(single, { kind: 'hand' }, piles, 1)).toEqual({ type: 'move_card', card_id: 'c', to: { kind: 'hand', index: 1 } });
  expect(toAction(single, { kind: 'player', playerId: 'ben' }, piles, 0)).toEqual({ type: 'move_card', card_id: 'c', to: { kind: 'player', player_id: 'ben' } });
});

test('vanished pile means no action', () => {
  expect(toAction({ kind: 'pile', pileId: 'gone' }, { kind: 'hand' }, piles, 0)).toBeNull();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd app && npx jest`
Expected: FAIL — `Cannot find module '../geometry'`

- [ ] **Step 3: Implement**

`app/src/table/geometry.ts`:
```ts
import type { Layout } from '../protocol';

export type Rect = { x: number; y: number; width: number; height: number };
export type Point = { x: number; y: number };
export type Size = { width: number; height: number };
export type Regions = { table: Rect; hand: Rect; avatars: { playerId: string; rect: Rect }[] };

/** fromPileId null = dragging a card from your own hand. */
export type DragSource =
  | { kind: 'card'; cardId: string; fromPileId: string | null }
  | { kind: 'pile'; pileId: string };

export type DropTarget =
  | { kind: 'hand' }
  | { kind: 'player'; playerId: string }
  | { kind: 'pile'; pileId: string }
  | { kind: 'table'; x: number; y: number }
  | null;

type PileShape = { id: string; x: number; y: number; layout: Layout; cards: unknown[] };

export const HAND_PADDING = 8;
export const HAND_TOP = 12;

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function contains(r: Rect, p: Point): boolean {
  return p.x >= r.x && p.x <= r.x + r.width && p.y >= r.y && p.y <= r.y + r.height;
}

export function cardSize(tableWidth: number): Size {
  const width = Math.round(clamp(tableWidth / 6, 40, 64));
  return { width, height: Math.round(width * 1.4) };
}

/** Horizontal offset between fanned cards, shrunk so the fan stays on the table. */
export function fanStep(pile: PileShape, tableWidth: number, card: Size): number {
  if (pile.layout !== 'fan' || pile.cards.length < 2) return 0;
  const left = pile.x * tableWidth - card.width / 2;
  const room = tableWidth - left - card.width;
  return clamp(room / (pile.cards.length - 1), 2, card.width * 0.28);
}

/** Pile bounds relative to the table's top-left corner. (x, y) is the first card's centre. */
export function pileOffset(pile: PileShape, table: Size, card: Size): Rect {
  const step = fanStep(pile, table.width, card);
  return {
    x: pile.x * table.width - card.width / 2,
    y: pile.y * table.height - card.height / 2,
    width: card.width + step * Math.max(0, pile.cards.length - 1),
    height: card.height,
  };
}

export function pileRect(pile: PileShape, table: Rect, card: Size): Rect {
  const o = pileOffset(pile, table, card);
  return { ...o, x: o.x + table.x, y: o.y + table.y };
}

export function toTableFraction(p: Point, table: Rect, card: Size): Point {
  const hx = card.width / 2 / table.width;
  const hy = card.height / 2 / table.height;
  return {
    x: clamp((p.x - table.x) / table.width, hx, 1 - hx),
    y: clamp((p.y - table.y) / table.height, hy, 1 - hy),
  };
}

export function handStep(count: number, handWidth: number, card: Size): number {
  if (count < 2) return 0;
  return Math.min(card.width * 0.9, (handWidth - 2 * HAND_PADDING - card.width) / (count - 1));
}

/** Which of `count` hand slots the point is over. */
export function handIndexAt(px: number, count: number, hand: Rect, card: Size): number {
  if (count < 2) return 0;
  const step = handStep(count, hand.width, card);
  const i = Math.round((px - hand.x - HAND_PADDING - card.width / 2) / step);
  return clamp(i, 0, count - 1);
}

export function resolveDrop(
  p: Point,
  source: DragSource,
  regions: Regions,
  piles: PileShape[],
  selfId: string | null,
  card: Size,
): DropTarget {
  if (contains(regions.hand, p)) return { kind: 'hand' };
  const avatar = regions.avatars.find((a) => contains(a.rect, p));
  if (avatar) return avatar.playerId === selfId ? null : { kind: 'player', playerId: avatar.playerId };
  if (!contains(regions.table, p)) return null;
  // Later piles render on top, so hit-test from the end.
  for (let i = piles.length - 1; i >= 0; i--) {
    const pile = piles[i];
    if (source.kind === 'pile' && pile.id === source.pileId) continue;
    if (contains(pileRect(pile, regions.table, card), p)) {
      if (source.kind === 'card' && pile.id === source.fromPileId) return null;
      return { kind: 'pile', pileId: pile.id };
    }
  }
  const f = toTableFraction(p, regions.table, card);
  return { kind: 'table', x: f.x, y: f.y };
}
```

`app/src/table/dropAction.ts`:
```ts
import type { Action, PileView } from '../protocol';
import type { DragSource, DropTarget } from './geometry';

/** Translate a finished drag into the action to send, or null to snap back. */
export function toAction(
  source: DragSource,
  target: DropTarget,
  piles: PileView[],
  handIndex: number,
): Action | null {
  if (!target) return null;

  if (source.kind === 'card') {
    const card_id = source.cardId;
    switch (target.kind) {
      case 'hand':
        return { type: 'move_card', card_id, to: { kind: 'hand', index: handIndex } };
      case 'player':
        return { type: 'move_card', card_id, to: { kind: 'player', player_id: target.playerId } };
      case 'pile':
        return { type: 'move_card', card_id, to: { kind: 'pile', pile_id: target.pileId } };
      case 'table':
        return { type: 'move_card', card_id, to: { kind: 'table', x: target.x, y: target.y } };
    }
  }

  const pile = piles.find((p) => p.id === source.pileId);
  if (!pile) return null;
  // Dragging a lone card is a pile drag; for hand/player it should act like the card.
  const lone = pile.cards.length === 1 ? pile.cards[0].id : null;
  switch (target.kind) {
    case 'hand':
      return lone
        ? { type: 'move_card', card_id: lone, to: { kind: 'hand', index: handIndex } }
        : { type: 'take_pile', pile_id: pile.id };
    case 'player':
      return lone ? { type: 'move_card', card_id: lone, to: { kind: 'player', player_id: target.playerId } } : null;
    case 'pile':
      return { type: 'merge_pile', pile_id: pile.id, onto_pile_id: target.pileId };
    case 'table':
      return { type: 'move_pile', pile_id: pile.id, x: target.x, y: target.y };
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && npx jest && npx tsc --noEmit`
Expected: all tests pass, no type errors.

- [ ] **Step 5: Commit**

```bash
git add app/src/table
git commit -m "feat(app): table geometry and drop-to-action logic"
```

---

### Task 9: Render the table — cards, piles, hand, players

**Files:**
- Create: `app/src/table/CardFace.tsx`, `app/src/table/PileView.tsx`, `app/src/table/HandView.tsx`, `app/src/table/PlayersBar.tsx`
- Modify: `app/src/screens/TableScreen.tsx` (replace the debug screen)

**Interfaces:**
- Consumes: `geometry.ts` (`cardSize`, `pileOffset`, `fanStep`, `handStep`, `HAND_PADDING`, `HAND_TOP`, `Rect`, `Size`), `useRoom`, `colors`, protocol types.
- Produces:
  - `CardFace({ card: CardView; size: Size })` — face if `face_up && rank`, else back
  - `PileView(props: PileViewProps)` where
    `PileViewProps = { pile: PileView; table: Size; card: Size; hidden: boolean; hiddenCardId: string | null; topSlot?: (top: ReactNode) => ReactNode }` — `topSlot` lets Task 10 wrap the top card in a gesture detector without changing the render structure
  - `HandView({ cards, width, card, hiddenCardId, wrapCard? })` where `wrapCard?: (c: CardView, node: ReactNode) => ReactNode`
  - `PlayersBar({ players, selfId, onAvatarRect(playerId, rect) })`
  - `measure(ref, cb)` helper exported from `PlayersBar.tsx`: `measure(ref: RefObject<View | null>, cb: (r: Rect) => void)`
  - Hidden elements are rendered with `opacity: 0` (never unmounted) so a gesture in progress is not cancelled.

- [ ] **Step 1: CardFace**

`app/src/table/CardFace.tsx`:
```tsx
import { StyleSheet, Text, View } from 'react-native';
import type { CardView } from '../protocol';
import { colors } from '../theme';
import type { Size } from './geometry';

const SUIT_SYMBOL = { S: '♠', H: '♥', D: '♦', C: '♣' } as const;

export function CardFace({ card, size }: { card: CardView; size: Size }) {
  const box = { width: size.width, height: size.height, borderRadius: size.width * 0.1 };
  if (!card.face_up || !card.rank) {
    return (
      <View style={[styles.back, box]}>
        <View style={[styles.backInner, { borderRadius: size.width * 0.07 }]} />
      </View>
    );
  }
  const joker = card.rank === 'JOKER';
  const red = card.suit === 'H' || card.suit === 'D';
  const color = joker ? colors.accent : red ? colors.cardRed : colors.cardBlack;
  const symbol = card.suit ? SUIT_SYMBOL[card.suit] : '★';
  return (
    <View style={[styles.face, box]}>
      <Text style={[styles.corner, { color, fontSize: size.width * 0.26 }]}>{joker ? 'JKR' : card.rank}</Text>
      <Text style={[styles.center, { color, fontSize: size.width * 0.45 }]}>{symbol}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  face: {
    backgroundColor: colors.cardFace, padding: 4,
    borderWidth: StyleSheet.hairlineWidth, borderColor: '#0003',
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  corner: { fontWeight: '700' },
  center: { position: 'absolute', alignSelf: 'center', top: '35%' },
  back: {
    backgroundColor: colors.cardBack, padding: 4,
    borderWidth: 2, borderColor: colors.cardFace,
    shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 2, shadowOffset: { width: 0, height: 1 },
  },
  backInner: { flex: 1, backgroundColor: colors.cardBackInner },
});
```

- [ ] **Step 2: PileView, HandView, PlayersBar**

`app/src/table/PileView.tsx`:
```tsx
import type { ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { PileView as Pile } from '../protocol';
import { colors } from '../theme';
import { CardFace } from './CardFace';
import { fanStep, pileOffset, type Size } from './geometry';

export type PileViewProps = {
  pile: Pile;
  table: Size;
  card: Size;
  hidden: boolean; // whole pile is being dragged
  hiddenCardId: string | null; // top card is being dragged
  topSlot?: (top: ReactNode) => ReactNode;
};

export function PileView({ pile, table, card, hidden, hiddenCardId, topSlot }: PileViewProps) {
  const box = pileOffset(pile, table, card);
  const step = fanStep(pile, table.width, card);
  const topIndex = pile.cards.length - 1;
  const top = pile.cards[topIndex];

  const topNode = (
    <View style={{ position: 'absolute', left: topIndex * step, opacity: hiddenCardId === top.id ? 0 : 1 }}>
      <CardFace card={top} size={card} />
    </View>
  );

  return (
    <View
      pointerEvents="box-none"
      style={{ position: 'absolute', left: box.x, top: box.y, width: box.width, height: box.height, opacity: hidden ? 0 : 1 }}
    >
      {pile.layout === 'fan'
        ? pile.cards.slice(0, -1).map((c, i) => (
            <View key={c.id} style={{ position: 'absolute', left: i * step }}>
              <CardFace card={c} size={card} />
            </View>
          ))
        : topIndex > 0 && (
            <View style={{ position: 'absolute', left: 2, top: 2 }}>
              <CardFace card={pile.cards[topIndex - 1]} size={card} />
            </View>
          )}
      {topSlot ? topSlot(topNode) : topNode}
      {pile.layout === 'stack' && pile.cards.length > 1 && (
        <Text pointerEvents="none" style={styles.count}>{pile.cards.length}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  count: {
    position: 'absolute', right: -6, bottom: -6, minWidth: 22, textAlign: 'center',
    backgroundColor: colors.feltDark, color: colors.text, fontSize: 12, fontWeight: '700',
    borderRadius: 11, paddingHorizontal: 4, overflow: 'hidden',
  },
});
```

`app/src/table/HandView.tsx`:
```tsx
import type { ReactNode } from 'react';
import { View } from 'react-native';
import type { CardView } from '../protocol';
import { CardFace } from './CardFace';
import { HAND_PADDING, HAND_TOP, handStep, type Size } from './geometry';

type Props = {
  cards: CardView[];
  width: number;
  card: Size;
  hiddenCardId: string | null;
  wrapCard?: (c: CardView, node: ReactNode) => ReactNode;
};

export function HandView({ cards, width, card, hiddenCardId, wrapCard }: Props) {
  const step = handStep(cards.length, width, card);
  return (
    <>
      {cards.map((c, i) => {
        const node = (
          <View
            key={c.id}
            style={{ position: 'absolute', left: HAND_PADDING + i * step, top: HAND_TOP, opacity: c.id === hiddenCardId ? 0 : 1 }}
          >
            <CardFace card={c} size={card} />
          </View>
        );
        return wrapCard ? <View key={c.id}>{wrapCard(c, node)}</View> : node;
      })}
    </>
  );
}
```

`app/src/table/PlayersBar.tsx`:
```tsx
import { useRef, type RefObject } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { PlayerView } from '../protocol';
import { colors } from '../theme';
import type { Rect } from './geometry';

export function measure(ref: RefObject<View | null>, cb: (r: Rect) => void) {
  ref.current?.measureInWindow((x, y, width, height) => cb({ x, y, width, height }));
}

function Avatar({ player, self, onRect }: { player: PlayerView; self: boolean; onRect: (r: Rect) => void }) {
  const ref = useRef<View>(null);
  return (
    <View
      ref={ref}
      onLayout={() => measure(ref, onRect)}
      style={[styles.chip, !player.connected && styles.away, self && styles.self]}
    >
      <Text style={styles.name} numberOfLines={1}>
        {player.is_host ? '👑 ' : ''}{self ? 'You' : player.name}
      </Text>
      <Text style={styles.count}>🂠 {player.hand_count}</Text>
    </View>
  );
}

export function PlayersBar({
  players, selfId, onAvatarRect,
}: { players: PlayerView[]; selfId: string | null; onAvatarRect: (playerId: string, r: Rect) => void }) {
  return (
    <View style={styles.bar}>
      {players.map((p) => (
        <Avatar key={p.id} player={p} self={p.id === selfId} onRect={(r) => onAvatarRect(p.id, r)} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingHorizontal: 8, paddingVertical: 6 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, maxWidth: 160,
    backgroundColor: colors.felt, borderRadius: 16, paddingHorizontal: 10, paddingVertical: 8,
  },
  self: { borderWidth: 1, borderColor: colors.accent },
  away: { opacity: 0.4 },
  name: { color: colors.text, fontWeight: '600', flexShrink: 1 },
  count: { color: colors.muted, fontSize: 12 },
});
```

- [ ] **Step 3: TableScreen (rendering + measuring only)**

Replace `app/src/screens/TableScreen.tsx`:
```tsx
import { useCallback, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { colors } from '../theme';
import { useRoom } from '../useRoom';
import { cardSize, HAND_TOP, type Rect } from '../table/geometry';
import { HandView } from '../table/HandView';
import { PileView } from '../table/PileView';
import { measure, PlayersBar } from '../table/PlayersBar';

export default function TableScreen({ code, name, onExit }: { code: string; name: string; onExit: () => void }) {
  const room = useRoom(code, name);
  const { view, players, playerId } = room;

  const tableRef = useRef<View>(null);
  const handRef = useRef<View>(null);
  const regions = useRef<{ table: Rect | null; hand: Rect | null; avatars: Map<string, Rect> }>({
    table: null, hand: null, avatars: new Map(),
  });
  const [tableSize, setTableSize] = useState({ width: 0, height: 0 });
  const [handWidth, setHandWidth] = useState(0);
  const card = cardSize(tableSize.width || 360);

  const onAvatarRect = useCallback((id: string, r: Rect) => regions.current.avatars.set(id, r), []);

  if (room.fatal) {
    return (
      <SafeAreaView style={[styles.screen, styles.centered]}>
        <Text style={styles.fatal}>{room.fatal}</Text>
        <Pressable onPress={onExit}><Text style={styles.link}>Back</Text></Pressable>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Text style={styles.code}>{code}</Text>
        <Text style={styles.status}>{room.status === 'reconnecting' ? 'Reconnecting…' : ''}</Text>
        <Pressable onPress={() => { room.leave(); onExit(); }}>
          <Text style={styles.link}>Leave</Text>
        </Pressable>
      </View>
      <PlayersBar players={players} selfId={playerId} onAvatarRect={onAvatarRect} />
      <View
        ref={tableRef}
        style={styles.table}
        onLayout={(e) => {
          setTableSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height });
          measure(tableRef, (r) => { regions.current.table = r; });
        }}
      >
        {tableSize.width > 0 &&
          view?.piles.map((p) => (
            <PileView key={p.id} pile={p} table={tableSize} card={card} hidden={false} hiddenCardId={null} />
          ))}
      </View>
      <View
        ref={handRef}
        style={[styles.hand, { height: card.height + HAND_TOP * 2 }]}
        onLayout={(e) => {
          setHandWidth(e.nativeEvent.layout.width);
          measure(handRef, (r) => { regions.current.hand = r; });
        }}
      >
        <HandView cards={view?.hand ?? []} width={handWidth} card={card} hiddenCardId={null} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.feltDark },
  centered: { alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingTop: 4, gap: 12 },
  code: { color: colors.text, fontSize: 26, fontWeight: '800', letterSpacing: 4 },
  status: { flex: 1, color: colors.accent },
  link: { color: colors.accent, fontSize: 17, fontWeight: '600' },
  fatal: { color: colors.text, fontSize: 18, textAlign: 'center' },
  table: { flex: 1, backgroundColor: colors.felt, marginHorizontal: 8, borderRadius: 16 },
  hand: { marginHorizontal: 8, marginTop: 8 },
});
```

- [ ] **Step 4: Type-check and test**

Run: `cd app && npx tsc --noEmit && npx jest`
Expected: no type errors; Task 8 tests still pass.

- [ ] **Step 5: Manual check on the phone**

With backend + `npx expo start` running: create a room → the deck appears as a face-down stack in the middle of the green table with a "52" badge; your avatar chip shows "👑 You 🂠 0". Join from a second device (or Expo Go on a friend's phone, or a second simulator) with the code → both see two avatars.

- [ ] **Step 6: Commit**

```bash
git add app/src
git commit -m "feat(app): render table, piles, hand and players"
```

---

### Task 10: Gestures — drag, drop, flip, pile drag, haptics

**Files:**
- Modify: `app/src/screens/TableScreen.tsx`
- Create: `app/src/table/gestures.tsx`

**Interfaces:**
- Consumes: `resolveDrop`, `handIndexAt`, `toAction`, `PileView` (`topSlot`), `HandView` (`wrapCard`), `useRoom().send`.
- Produces:
  - `gestures.tsx`: `DragHandlers = { dragX: SharedValue<number>; dragY: SharedValue<number>; onCardStart(pileId: string | null, cardId: string): void; onPileStart(pileId: string): void; onEnd(kind: 'card' | 'pile', x: number, y: number, success: boolean, moved: number): void; onFlip(cardId: string): void }`
  - `TopCardGestures({ pileId, cardId, h, children })` — Race(long-press pile pan, card pan, tap)
  - `HandCardGestures({ cardId, h, children })` — card pan
  - TableScreen state `menuPileId: string | null` (set on a long-press without movement; the menu itself is rendered in Task 11)

- [ ] **Step 1: Gesture wrappers**

`app/src/table/gestures.tsx`:
```tsx
import { useMemo, type ReactNode } from 'react';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { runOnJS, type SharedValue } from 'react-native-reanimated';

export type DragHandlers = {
  dragX: SharedValue<number>;
  dragY: SharedValue<number>;
  onCardStart: (pileId: string | null, cardId: string) => void;
  onPileStart: (pileId: string) => void;
  onEnd: (kind: 'card' | 'pile', x: number, y: number, success: boolean, moved: number) => void;
  onFlip: (cardId: string) => void;
};

const LONG_PRESS_MS = 350;

function cardPan(h: DragHandlers, pileId: string | null, cardId: string) {
  const { dragX, dragY, onCardStart, onEnd } = h;
  return Gesture.Pan()
    .minDistance(6)
    .onStart((e) => {
      dragX.value = e.absoluteX;
      dragY.value = e.absoluteY;
      runOnJS(onCardStart)(pileId, cardId);
    })
    .onUpdate((e) => {
      dragX.value = e.absoluteX;
      dragY.value = e.absoluteY;
    })
    .onEnd((e, success) => {
      runOnJS(onEnd)('card', e.absoluteX, e.absoluteY, success, Math.hypot(e.translationX, e.translationY));
    });
}

export function TopCardGestures({
  pileId, cardId, h, children,
}: { pileId: string; cardId: string; h: DragHandlers; children: ReactNode }) {
  const gesture = useMemo(() => {
    const { dragX, dragY, onPileStart, onEnd, onFlip } = h;
    // Long-press then drag moves the whole pile; long-press without moving opens its menu.
    const pilePan = Gesture.Pan()
      .activateAfterLongPress(LONG_PRESS_MS)
      .onStart((e) => {
        dragX.value = e.absoluteX;
        dragY.value = e.absoluteY;
        runOnJS(onPileStart)(pileId);
      })
      .onUpdate((e) => {
        dragX.value = e.absoluteX;
        dragY.value = e.absoluteY;
      })
      .onEnd((e, success) => {
        runOnJS(onEnd)('pile', e.absoluteX, e.absoluteY, success, Math.hypot(e.translationX, e.translationY));
      });
    const tap = Gesture.Tap()
      .maxDuration(250)
      .onEnd((_e, success) => {
        if (success) runOnJS(onFlip)(cardId);
      });
    return Gesture.Race(pilePan, cardPan(h, pileId, cardId), tap);
  }, [pileId, cardId, h]);
  return <GestureDetector gesture={gesture}>{children}</GestureDetector>;
}

export function HandCardGestures({ cardId, h, children }: { cardId: string; h: DragHandlers; children: ReactNode }) {
  const gesture = useMemo(() => cardPan(h, null, cardId), [cardId, h]);
  return <GestureDetector gesture={gesture}>{children}</GestureDetector>;
}
```

- [ ] **Step 2: Wire drag state, drop handling and the drag overlay into TableScreen**

In `app/src/screens/TableScreen.tsx`:

Replace the imports block with:
```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import Animated, { useAnimatedStyle, useSharedValue } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { Action, CardView } from '../protocol';
import { colors } from '../theme';
import { useRoom } from '../useRoom';
import { CardFace } from '../table/CardFace';
import { toAction } from '../table/dropAction';
import { cardSize, HAND_TOP, handIndexAt, resolveDrop, type DragSource, type Rect } from '../table/geometry';
import { HandCardGestures, TopCardGestures, type DragHandlers } from '../table/gestures';
import { HandView } from '../table/HandView';
import { PileView } from '../table/PileView';
import { measure, PlayersBar } from '../table/PlayersBar';

type Drag = { gesture: 'card' | 'pile'; source: DragSource; card: CardView; settling: boolean };
```

Inside the component, after `const onAvatarRect = ...`, add:
```tsx
  const rootRef = useRef<View>(null);
  const rootX = useSharedValue(0);
  const rootY = useSharedValue(0);
  const dragX = useSharedValue(0);
  const dragY = useSharedValue(0);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [menuPileId, setMenuPileId] = useState<string | null>(null);

  // Gesture callbacks must be stable (they're captured by memoized gestures), so
  // they read the latest values through refs.
  const latest = useRef({ view, playerId, players, drag, send: room.send });
  latest.current = { view, playerId, players, drag, send: room.send };

  const send = useCallback((action: Action) => latest.current.send(action), []);

  // A dropped card stays where it landed until the server's answer arrives.
  useEffect(() => {
    setDrag((d) => (d?.settling ? null : d));
  }, [view]);
  useEffect(() => {
    if (!drag?.settling) return;
    const t = setTimeout(() => setDrag(null), 800);
    return () => clearTimeout(t);
  }, [drag?.settling]);

  const handlers: DragHandlers = useMemo(() => ({
    dragX,
    dragY,
    onCardStart: (pileId, cardId) => {
      const v = latest.current.view;
      if (!v || latest.current.drag) return;
      if (pileId === null) {
        const c = v.hand.find((h) => h.id === cardId);
        if (!c) return;
        setDrag({ gesture: 'card', source: { kind: 'card', cardId, fromPileId: null }, card: c, settling: false });
      } else {
        const pile = v.piles.find((p) => p.id === pileId);
        if (!pile) return;
        const top = pile.cards[pile.cards.length - 1];
        // A lone card moves as its pile, so nudging it doesn't count as "dropped on itself".
        const source: DragSource = pile.cards.length === 1
          ? { kind: 'pile', pileId }
          : { kind: 'card', cardId, fromPileId: pileId };
        setDrag({ gesture: 'card', source, card: top, settling: false });
      }
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    },
    onPileStart: (pileId) => {
      const v = latest.current.view;
      const pile = v?.piles.find((p) => p.id === pileId);
      if (!pile || latest.current.drag) return;
      setDrag({ gesture: 'pile', source: { kind: 'pile', pileId }, card: pile.cards[pile.cards.length - 1], settling: false });
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    },
    onEnd: (kind, x, y, success, moved) => {
      const { drag: d, view: v, playerId: self, players: ps } = latest.current;
      const { table, hand, avatars } = regions.current;
      if (!d || d.settling || d.gesture !== kind) return;
      if (!success || !v || !table || !hand) {
        setDrag(null);
        return;
      }
      if (kind === 'pile' && moved < 10 && d.source.kind === 'pile') {
        setDrag(null);
        setMenuPileId(d.source.pileId);
        return;
      }
      const card = cardSize(table.width);
      const liveAvatars = ps.flatMap((p) => {
        const rect = avatars.get(p.id);
        return rect ? [{ playerId: p.id, rect }] : [];
      });
      const target = resolveDrop({ x, y }, d.source, { table, hand, avatars: liveAvatars }, v.piles, self, card);
      const fromHand = d.source.kind === 'card' && d.source.fromPileId === null;
      const slots = v.hand.length + (fromHand ? 0 : 1);
      const action = toAction(d.source, target, v.piles, handIndexAt(x, slots, hand, card));
      if (!action) {
        setDrag(null);
        return;
      }
      send(action);
      void Haptics.selectionAsync();
      dragX.value = x;
      dragY.value = y;
      setDrag({ ...d, settling: true });
    },
    onFlip: (cardId) => {
      send({ type: 'flip_card', card_id: cardId });
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    },
  }), [dragX, dragY, send]);

  const overlayStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: dragX.value - rootX.value - card.width / 2 },
      { translateY: dragY.value - rootY.value - card.height / 2 },
      { scale: 1.08 },
    ],
  }), [card.width, card.height]);

  const hiddenCardId = drag?.source.kind === 'card' ? drag.source.cardId : null;
  const hiddenPileId = drag?.source.kind === 'pile' ? drag.source.pileId : null;
```

Wrap the screen content so the overlay is positioned relative to a measured root: change the `return (...)` for the normal (non-fatal) case to:
```tsx
  return (
    <SafeAreaView style={styles.screen} edges={['top', 'bottom']}>
      <View
        ref={rootRef}
        style={styles.root}
        onLayout={() => measure(rootRef, (r) => { rootX.value = r.x; rootY.value = r.y; })}
      >
        <View style={styles.header}>
          <Text style={styles.code}>{code}</Text>
          <Text style={styles.status}>{room.status === 'reconnecting' ? 'Reconnecting…' : ''}</Text>
          <Pressable onPress={() => { room.leave(); onExit(); }}>
            <Text style={styles.link}>Leave</Text>
          </Pressable>
        </View>
        <PlayersBar players={players} selfId={playerId} onAvatarRect={onAvatarRect} />
        <View
          ref={tableRef}
          style={styles.table}
          onLayout={(e) => {
            setTableSize({ width: e.nativeEvent.layout.width, height: e.nativeEvent.layout.height });
            measure(tableRef, (r) => { regions.current.table = r; });
          }}
        >
          {tableSize.width > 0 &&
            view?.piles.map((p) => (
              <PileView
                key={p.id}
                pile={p}
                table={tableSize}
                card={card}
                hidden={p.id === hiddenPileId}
                hiddenCardId={hiddenCardId}
                topSlot={(top) => (
                  <TopCardGestures pileId={p.id} cardId={p.cards[p.cards.length - 1].id} h={handlers}>
                    {top}
                  </TopCardGestures>
                )}
              />
            ))}
        </View>
        <View
          ref={handRef}
          style={[styles.hand, { height: card.height + HAND_TOP * 2 }]}
          onLayout={(e) => {
            setHandWidth(e.nativeEvent.layout.width);
            measure(handRef, (r) => { regions.current.hand = r; });
          }}
        >
          <HandView
            cards={view?.hand ?? []}
            width={handWidth}
            card={card}
            hiddenCardId={hiddenCardId}
            wrapCard={(c, node) => <HandCardGestures cardId={c.id} h={handlers}>{node}</HandCardGestures>}
          />
        </View>
        {drag && (
          <Animated.View pointerEvents="none" style={[styles.overlay, overlayStyle]}>
            <CardFace card={drag.card} size={card} />
          </Animated.View>
        )}
      </View>
    </SafeAreaView>
  );
```

Add to `styles`:
```tsx
  root: { flex: 1 },
  overlay: {
    position: 'absolute', left: 0, top: 0,
    shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 8, shadowOffset: { width: 0, height: 6 },
  },
```

(`menuPileId` is set here and consumed in Task 11; until then add `void menuPileId;` after its declaration to keep the linter-free type-check clean.)

- [ ] **Step 3: Type-check and test**

Run: `cd app && npx tsc --noEmit && npx jest`
Expected: no errors, tests pass.

- [ ] **Step 4: Manual check on the phone (two devices)**

1. Drag the top card of the deck onto empty felt → a face-down card lands there; deck badge shows 51; the other phone sees it move.
2. Tap that card → flips face up on both phones; light haptic.
3. Drag the lone card a little → it moves (not cancelled).
4. Drag a card from the deck into your hand → it appears face up in your hand; the other phone shows your avatar's count go up and **never** sees its face.
5. Drag a hand card to the table → lands face up. Drag one within your hand → reorders.
6. Drop a hand card on the other player's avatar → it moves to their hand.
7. Long-press the deck ~0.4 s (medium haptic), then drag → whole deck moves. Drop it on another pile → merges.
8. Both players drag the deck's top card at the same moment → one wins, the other's card slides back and a rejection happens silently (toast arrives in Task 11).

- [ ] **Step 5: Commit**

```bash
git add app/src
git commit -m "feat(app): drag, drop, flip and pile gestures with haptics"
```

---

### Task 11: Menus, error toast, reconnect banner

**Files:**
- Create: `app/src/table/menus.tsx`
- Modify: `app/src/screens/TableScreen.tsx`

**Interfaces:**
- Consumes: `Action`, `PileView`, `colors`, TableScreen `menuPileId`, `room.send`, `room.leave`, `room.lastError`, `room.status`.
- Produces:
  - `PileMenu({ pile: PileView | null; onAction(a: Action): void; onClose(): void })`
  - `TableMenu({ visible: boolean; onAction(a: Action): void; onLeave(): void; onClose(): void })`
  - `Toast({ error: { message: string; at: number } | null })` — shows each new error for 2 s

- [ ] **Step 1: Menus and toast**

`app/src/table/menus.tsx`:
```tsx
import { useEffect, useState, type ReactNode } from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';
import type { Action, PileView } from '../protocol';
import { colors } from '../theme';

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <Modal transparent animationType="fade" visible onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet}>
          <Text style={styles.title}>{title}</Text>
          {children}
          <MenuButton label="Cancel" subtle onPress={onClose} />
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function MenuButton({ label, onPress, subtle, danger }: { label: string; onPress: () => void; subtle?: boolean; danger?: boolean }) {
  return (
    <Pressable style={({ pressed }) => [styles.button, subtle && styles.subtle, pressed && styles.pressed]} onPress={onPress}>
      <Text style={[styles.buttonText, danger && { color: colors.danger }]}>{label}</Text>
    </Pressable>
  );
}

export function PileMenu({ pile, onAction, onClose }: { pile: PileView | null; onAction: (a: Action) => void; onClose: () => void }) {
  const [deal, setDeal] = useState(1);
  if (!pile) return null;
  const run = (a: Action) => {
    onAction(a);
    onClose();
  };
  return (
    <Sheet title={`Pile · ${pile.cards.length} card${pile.cards.length === 1 ? '' : 's'}`} onClose={onClose}>
      <MenuButton
        label="Shuffle"
        onPress={() => {
          void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
          run({ type: 'shuffle', pile_id: pile.id });
        }}
      />
      <MenuButton label="Flip pile over" onPress={() => run({ type: 'flip_pile', pile_id: pile.id })} />
      <MenuButton
        label={pile.layout === 'stack' ? 'Fan out' : 'Stack up'}
        onPress={() => run({ type: 'set_layout', pile_id: pile.id, layout: pile.layout === 'stack' ? 'fan' : 'stack' })}
      />
      <View style={styles.row}>
        <Pressable style={styles.step} onPress={() => setDeal((d) => Math.max(1, d - 1))}><Text style={styles.buttonText}>−</Text></Pressable>
        <View style={{ flex: 1 }}>
          <MenuButton label={`Deal ${deal} to each`} onPress={() => run({ type: 'deal', pile_id: pile.id, count: deal })} />
        </View>
        <Pressable style={styles.step} onPress={() => setDeal((d) => Math.min(26, d + 1))}><Text style={styles.buttonText}>+</Text></Pressable>
      </View>
      <MenuButton label="Take all into hand" onPress={() => run({ type: 'take_pile', pile_id: pile.id })} />
    </Sheet>
  );
}

export function TableMenu({
  visible, onAction, onLeave, onClose,
}: { visible: boolean; onAction: (a: Action) => void; onLeave: () => void; onClose: () => void }) {
  if (!visible) return null;
  const run = (a: Action) => {
    onAction(a);
    onClose();
  };
  return (
    <Sheet title="Table" onClose={onClose}>
      <MenuButton label="Gather everything & shuffle" onPress={() => run({ type: 'gather' })} />
      <MenuButton label="New deck (no jokers)" onPress={() => run({ type: 'new_deck', jokers: 0 })} />
      <MenuButton label="New deck (+2 jokers)" onPress={() => run({ type: 'new_deck', jokers: 2 })} />
      <MenuButton label="Leave room" danger onPress={onLeave} />
    </Sheet>
  );
}

export function Toast({ error }: { error: { message: string; at: number } | null }) {
  const [shown, setShown] = useState<string | null>(null);
  useEffect(() => {
    if (!error) return;
    setShown(error.message);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
    const t = setTimeout(() => setShown(null), 2000);
    return () => clearTimeout(t);
  }, [error]);
  if (!shown) return null;
  return (
    <View pointerEvents="none" style={styles.toast}>
      <Text style={styles.toastText}>{shown}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: '#0008', justifyContent: 'flex-end' },
  sheet: { backgroundColor: colors.sheet, padding: 16, paddingBottom: 32, gap: 8, borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  title: { color: colors.muted, textAlign: 'center', marginBottom: 4 },
  button: { backgroundColor: colors.felt, borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  subtle: { backgroundColor: 'transparent' },
  pressed: { opacity: 0.6 },
  buttonText: { color: colors.text, fontSize: 17, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  step: { backgroundColor: colors.felt, borderRadius: 12, width: 48, paddingVertical: 14, alignItems: 'center' },
  toast: {
    position: 'absolute', top: 60, alignSelf: 'center', maxWidth: '85%',
    backgroundColor: '#000c', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10,
  },
  toastText: { color: colors.text, textAlign: 'center' },
});
```

- [ ] **Step 2: Wire into TableScreen**

In `app/src/screens/TableScreen.tsx`:
- Import: `import { PileMenu, TableMenu, Toast } from '../table/menus';`
- Remove the temporary `void menuPileId;`.
- Add state: `const [tableMenu, setTableMenu] = useState(false);`
- Add a leave handler: `const leaveRoom = () => { room.leave(); onExit(); };`
- In the header, replace the `Leave` pressable with a menu button:
```tsx
          <Pressable onPress={() => setTableMenu(true)} hitSlop={12}>
            <Text style={styles.link}>☰</Text>
          </Pressable>
```
- Make the status text also show the connection state on first connect:
```tsx
          <Text style={styles.status}>
            {room.status === 'reconnecting' ? 'Reconnecting…' : room.status === 'connecting' ? 'Connecting…' : ''}
          </Text>
```
- Just before the closing `</View>` of `root` (after the drag overlay), add:
```tsx
        <Toast error={room.lastError} />
        <PileMenu
          pile={view?.piles.find((p) => p.id === menuPileId) ?? null}
          onAction={send}
          onClose={() => setMenuPileId(null)}
        />
        <TableMenu visible={tableMenu} onAction={send} onLeave={leaveRoom} onClose={() => setTableMenu(false)} />
```

- [ ] **Step 3: Type-check and test**

Run: `cd app && npx tsc --noEmit && npx jest`
Expected: no errors, tests pass.

- [ ] **Step 4: Manual check on the phone (two devices)**

1. Long-press the deck without moving → pile menu opens. **Shuffle** → success haptic. **Fan out** → cards spread (face down) and stay on the table. **Stack up** → back.
2. **Deal 5 to each** → each phone gets 5 in hand; avatars show 🂠 5.
3. **Flip pile over** on a small pile → order and faces invert.
4. **Take all into hand** on a small pile → cards go to your hand.
5. ☰ → **Gather everything & shuffle** → one face-down deck of 52 in the middle, hands empty. **New deck (+2 jokers)** → badge shows 54; jokers render as gold ★ JKR when flipped.
6. Both grab the same top card at once → loser sees a toast and their card slides back.
7. Stop the backend briefly → banner says "Reconnecting…"; restart it → room is gone (expected for a restart), app shows "Room not found" with a Back button.
8. Lock a phone for a minute mid-game, unlock → same seat and hand.
9. ☰ → **Leave room** → back on Home; the other phone sees you gone and your hand cards back on the table.

- [ ] **Step 5: Commit**

```bash
git add app/src
git commit -m "feat(app): pile and table menus, error toast, connection status"
```

---

### Task 12: README, CLAUDE.md, end-to-end game-night check

**Files:**
- Create: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Write README.md**

````markdown
# Card Table

A shared deck of cards for friends. No rules engine: you play whatever you want,
like a real table. Expo app + FastAPI backend.

## Run locally

Backend (Python 3.12):

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

App:

```bash
cd app
cp .env.example .env     # set your PC's LAN IP
npm install
npx expo start           # scan the QR with the iPhone camera (Expo Go)
```

Phone and PC must be on the same Wi-Fi; allow Python through Windows Firewall
(private networks). Friends elsewhere: `npx expo start --tunnel` loads the app,
but the backend still has to be reachable from their phone.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd app && npx jest
```

## How to play

- Drag a card: top of a pile, or from your hand. Drop on felt (new pile), a pile,
  your hand, or a player's name (gives it to them).
- Tap a pile's top card to flip it.
- Long-press a pile: drag to move it, or let go for the menu (shuffle, flip,
  fan, deal, take).
- ☰: gather & shuffle, new deck, leave.
````

- [ ] **Step 2: Write CLAUDE.md**

```markdown
# card-table — Claude guide

Personal project: shared-deck card app for friends. Spec:
`docs/superpowers/specs/2026-10-12-card-table-design.md`. Plan 1 (playable
table) is done; Plan 2 adds accounts, games library, setups, stats.

## Invariants (don't undo)

- **Server is authoritative; the app has no game logic.** The app turns gestures
  into actions and renders whatever state the server sends back.
- **Hidden info never leaves the server.** All state goes out through
  `backend/app/engine/views.py::view_for`. Card ids are re-issued when a card
  enters a hand or a pile is shuffled/gathered, so ids can't track hidden cards.
  `tests/test_views.py::test_no_view_ever_leaks_hidden_cards` guards this.
- **Single uvicorn worker.** Live rooms are in memory; a restart drops them.
- `app/src/protocol.ts` mirrors `backend/app/engine/protocol.py` + `views.py` by
  hand. Change both together.
- Dragged cards/piles are hidden with `opacity: 0`, never unmounted — unmounting
  a GestureDetector mid-drag cancels the gesture.

## Git

Local only — no remote yet. Commit as `Yzeir Baku <yzeirbaku@hotmail.com>`
(set in local config). Never push without asking.
```

- [ ] **Step 3: Full test run**

Run: `cd backend && .venv/Scripts/python -m pytest -q && cd ../app && npx jest && npx tsc --noEmit`
Expected: everything passes.

- [ ] **Step 4: Game-night rehearsal (manual, 2–3 phones)**

Play a short real round end to end: create room, others join by code, deal 7 each, play cards to a discard pile, draw from the deck, pass a card, gather & shuffle, play again. Note anything that feels fiddly for the next iteration (no fixing in this task).

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: README and CLAUDE.md for card-table"
```
