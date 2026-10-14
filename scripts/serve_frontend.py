"""Static server for frontend/ with explicit MIME types (Windows' registry can map
.js to text/plain, which breaks ES modules, and Python doesn't know .webp) and no
caching, so edits show up on reload.

Usage: py -3.12 scripts/serve_frontend.py [port]   (dev_up.py runs this for you)
"""

import functools
import http.server
import sys
from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".webmanifest": "application/manifest+json",
        ".webp": "image/webp",
        ".png": "image/png",
        ".svg": "image/svg+xml",
    }

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5520
    handler = functools.partial(Handler, directory=str(FRONTEND_DIR))
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
