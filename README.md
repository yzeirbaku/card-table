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
