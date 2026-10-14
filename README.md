# Card Table

Card games with friends, one game at a time: create a table, share the 4-letter
code, and play on your phones. Vanilla-JS PWA + FastAPI backend. Murlan is the
first game (in progress).

## Run locally

One-time backend setup (Python 3.12):

```bash
cd backend
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
```

Then from the repo root:

```bash
py -3.12 scripts/dev_up.py     # backend :8020 + frontend :5520, opens the browser
py -3.12 scripts/dev_down.py   # stop both
```

`dev_up.py` also prints a `http://<your-pc-ip>:5520` address: open it on a phone on
the same Wi-Fi. Allow Python through Windows Firewall (private networks).
The Copy button and installing to the home screen work best on `localhost` or
https; on the plain-http LAN address you can still long-press to paste a code.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && node --test
```

## Card art

Faces are Byron Knoll's public-domain *Vector Playing Cards* (English pattern),
with our own ace of spades and jester jokers. `scripts/build_cards.py`
regenerates `frontend/cards/` and `frontend/icons/` (see the script's docstring);
the output is committed.
