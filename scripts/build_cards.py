"""Build frontend/cards/*.webp and frontend/icons/icon-*.png from Byron Knoll's public-domain Vector Playing Cards.

Run once (output is committed); re-run only if the art changes:
    py -3.12 -m pip install resvg-py==0.5.0 pillow==12.3.0
    py -3.12 scripts/build_cards.py

Source SVGs are downloaded from a pinned commit of the public-domain mirror and
cached in .dev/card-src/. Two cards are our own: the ace of spades (the deck's
has unclear provenance, so it is rebuilt from the ace of hearts with a spade)
and the two jester jokers (the deck's jokers are text only).
"""

from __future__ import annotations

import re
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / ".dev" / "card-src"
OUT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO_ROOT / "frontend"
SOURCE = ("https://raw.githubusercontent.com/notpeter/Vector-Playing-Cards/"
          "861b338eb931d635c442b568071e3829e552f383/cards-svg/{name}.svg")
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
SUITS = ["C", "D", "H", "S"]
WIDTH = 320  # px; cards show at most ~110 CSS px wide, so this covers 3x screens

# The heart shape used by AH.svg (indices and centre), in a -8..8 x -9..9 box.
HEART = ("M 3.676,-9 C 0.433,-9 0,-5.523 0,-5.523 0,-5.523 -0.433,-9 -3.676,-9 "
         "-5.946,-9 -8,-7.441 -8,-4.5 -8,-0.614 -1.4208493,3.2938141 0,9 "
         "1.35201,3.2985969 8,-0.614 8,-4.5 8,-7.441 5.946,-9 3.676,-9 z")
# A spade drawn in the same box, so it drops into the same transforms.
SPADE = ("M 0,-9 C -1.5,-5.5 -8,-2.5 -8,1.6 -8,4.3 -6,5.8 -4,5.8 -2.3,5.8 -1,5 "
         "-0.4,3.8 -0.6,6.2 -1.8,8 -3.5,9 L 3.5,9 C 1.8,8 0.6,6.2 0.4,3.8 "
         "1,5 2.3,5.8 4,5.8 6,5.8 8,4.3 8,1.6 8,-2.5 1.5,-5.5 0,-9 z")

CARD_W, CARD_H = 167.0869141, 242.6669922


def fetch(name: str) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{name}.svg"
    if not cached.exists():
        with urllib.request.urlopen(SOURCE.format(name=name), timeout=60) as res:
            cached.write_bytes(res.read())
    return cached.read_text(encoding="utf-8")


def strip_pt(svg: str) -> str:
    # The source gives width/height in pt, which resvg rejects; the viewBox keeps proportions.
    return re.sub(r'(width|height)="([\d.]+)pt"', r'\1="\2"', svg, count=2)


def ace_of_spades() -> str:
    svg = fetch("AH")
    if svg.count(HEART) != 3:
        raise SystemExit("AH.svg changed: expected the heart path 3 times")
    # Drop the heart's two shine highlights: they sit where the heart's lobes were.
    svg, shines = re.subn(r'<path[^>]*?id="path3762[^"]*"[^>]*/>', "", svg, flags=re.S)
    if shines != 2:
        raise SystemExit(f"AH.svg changed: expected 2 shine paths, found {shines}")
    # The centre spade inherits the heart's radial gradient; make it plain solid black.
    if svg.count("fill:url(#radialGradient3776)") != 1:
        raise SystemExit("AH.svg changed: expected the radialGradient3776 fill exactly once")
    svg = svg.replace("fill:url(#radialGradient3776)", "fill:#000000")
    return svg.replace(HEART, SPADE).replace("#df0000", "#000000")


def joker(cap: str, accent: str) -> str:
    """Jester joker: `cap` colours the two side points and the corner letters,
    `accent` the middle point."""
    letters = "".join(
        f'<text x="15" y="{30 + i * 21}" text-anchor="middle">{c}</text>' for i, c in enumerate("JOKER")
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}">
  <rect x="0.25" y="0.25" width="{CARD_W - 0.5}" height="{CARD_H - 0.5}" rx="6.9" fill="#fff" stroke="#000" stroke-width="0.5"/>
  <g font-family="Arial" font-size="19" font-weight="bold" fill="{cap}">{letters}</g>
  <g font-family="Arial" font-size="19" font-weight="bold" fill="{cap}" transform="rotate(180 {CARD_W / 2} {CARD_H / 2})">{letters}</g>
  <g transform="translate({CARD_W / 2 - 57.5} {CARD_H / 2 - 57.5}) scale(1.15)">
    <path d="M36 66 C40 42 46 24 50 9 C54 24 60 42 64 66 Z" fill="{accent}"/>
    <path d="M22 68 C14 52 4 44 7 29 C19 34 33 45 41 64 Z" fill="{cap}"/>
    <path d="M59 64 C67 45 81 34 93 29 C96 44 86 52 78 68 Z" fill="{cap}"/>
    <rect x="18" y="64" width="64" height="13" rx="4" fill="#d4a640" stroke="#8a6a1f" stroke-width="1"/>
    <g fill="{cap}"><path d="M26 70.5l4-4 4 4-4 4z"/><path d="M42 70.5l4-4 4 4-4 4z"/><path d="M58 70.5l4-4 4 4-4 4z"/><path d="M74 70.5l3-3 3 3-3 3z"/></g>
    <g fill="#f0c75e" stroke="#8a6a1f" stroke-width="1.2"><circle cx="7" cy="29" r="5"/><circle cx="50" cy="9" r="5"/><circle cx="93" cy="29" r="5"/></g>
    <g fill="#8a6a1f"><circle cx="7" cy="31" r="1.2"/><circle cx="50" cy="11" r="1.2"/><circle cx="93" cy="31" r="1.2"/></g>
    <text x="50" y="94" text-anchor="middle" font-family="Georgia, serif" font-size="11" fill="#1a1a1a">★ ★ ★</text>
  </g>
</svg>"""


def render(svg: str, width: int = WIDTH) -> Image.Image:
    png = resvg_py.svg_to_bytes(svg_string=strip_pt(svg), width=width)
    return Image.open(BytesIO(bytes(png))).convert("RGBA")


def icon(ace: str, size: int) -> Image.Image:
    """App icon: the ace of hearts, slightly tilted, on green felt."""
    img = Image.new("RGBA", (size, size), "#1d5a37")
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    for r in range(size // 2, 0, -max(1, size // 64)):  # soft lighter centre, like the felt
        alpha = int(70 * (1 - r / (size / 2)))
        ImageDraw.Draw(glow).ellipse([size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r], fill=(60, 150, 95, alpha))
    img = Image.alpha_composite(img, glow)
    card = render(ace, width=int(size * 0.5)).rotate(-8, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(card, ((size - card.width) // 2, (size - card.height) // 2))
    return img.convert("RGB")


def main() -> None:
    cards_dir, icons_dir = OUT_DIR / "cards", OUT_DIR / "icons"
    cards_dir.mkdir(parents=True, exist_ok=True)
    icons_dir.mkdir(parents=True, exist_ok=True)
    cards: dict[str, str] = {}
    for rank in RANKS:
        for suit in SUITS:
            name = f"{rank}{suit}"
            cards[name] = ace_of_spades() if name == "AS" else fetch(name)
    cards["joker-red"] = joker("#c8102e", "#1a1a1a")
    cards["joker-black"] = joker("#1a1a1a", "#c8102e")
    for name, svg in cards.items():
        render(svg).save(cards_dir / f"{name}.webp", "WEBP", quality=85, method=6)
    for size in (192, 512):
        icon(cards["AH"], size).save(icons_dir / f"icon-{size}.png", optimize=True)
    total = sum(p.stat().st_size for p in cards_dir.glob("*.webp"))
    print(f"wrote {len(cards)} cards ({total // 1024} KB) and 2 icons under {OUT_DIR}")


if __name__ == "__main__":
    main()
