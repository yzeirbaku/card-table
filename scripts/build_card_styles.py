"""Build the Atlas and Modern card styles (frontend/cards/atlas/, frontend/cards/modern/) from Aisleriot's decks.

Run once (output is committed); re-run only if the art changes:
    py -3.12 -m pip install resvg-py==0.5.0 pillow==12.3.0
    py -3.12 scripts/build_card_styles.py

Each Aisleriot deck is one SVG sheet: 13 columns (A, 2-10, J, Q, K), rows clubs, diamonds,
hearts, spades, then black joker, red joker and the back. The sheet is rendered once at twice
the size, each card is cut out along its own edges and scaled to 320 x 466, the size of the
Traditional cards, so every style fits the same frames. Sources are cached in .dev/card-src/.
Credits and licences: frontend/cards/CREDITS.txt.
"""

from __future__ import annotations

import sys
import urllib.request
from io import BytesIO
from pathlib import Path

import resvg_py
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".dev" / "card-src"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "frontend"
SOURCE = ("https://gitlab.gnome.org/GNOME/aisleriot/-/raw/"
          "51e1d770ceddfa7ee0fd775f7d59bbe4858ab87a/cards/{name}.svg")
DECKS = {"atlas": "atlasnye", "modern": "neoclassical"}  # style -> Aisleriot deck
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = ["C", "D", "H", "S"]
SIZE = (320, 466)


def fetch(name: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"aisleriot-{name}.svg"
    if not cached.exists():
        with urllib.request.urlopen(SOURCE.format(name=name), timeout=60) as res:
            cached.write_bytes(res.read())
    return cached.read_text(encoding="utf-8")


def cards(deck: str) -> dict[str, Image.Image]:
    sheet = Image.open(BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=fetch(deck), width=13 * SIZE[0] * 2))))
    sheet = sheet.convert("RGBA")
    cw, ch = sheet.width / 13, sheet.height / 5

    def cut(col: int, row: int) -> Image.Image:
        cell = sheet.crop((round(col * cw), round(row * ch), round((col + 1) * cw), round((row + 1) * ch)))
        box = cell.getbbox()
        if box is None:
            raise SystemExit(f"{deck}.svg changed: nothing at column {col}, row {row}")
        return cell.crop(box).resize(SIZE, Image.LANCZOS)

    out = {f"{rank}{suit}": cut(c, r) for r, suit in enumerate(SUITS) for c, rank in enumerate(RANKS)}
    out["joker-black"], out["joker-red"] = cut(0, 4), cut(1, 4)
    return out


def main() -> None:
    for style, deck in DECKS.items():
        out_dir = OUT_DIR / "cards" / style
        out_dir.mkdir(parents=True, exist_ok=True)
        made = cards(deck)
        for name, img in made.items():
            img.save(out_dir / f"{name}.webp", "WEBP", quality=85, method=6)
        total = sum(p.stat().st_size for p in out_dir.glob("*.webp"))
        print(f"{style}: wrote {len(made)} cards ({total // 1024} KB) under {out_dir}")


if __name__ == "__main__":
    main()
