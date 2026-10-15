"""Start the local dev stack: backend on :8020, frontend on :5520.

Usage from the repo root:
    py -3.12 scripts/dev_up.py      # start, open the browser
    py -3.12 scripts/dev_down.py    # stop

Both listen on all interfaces, so a phone on the same Wi-Fi can open the LAN URL
printed at the end (allow Python through Windows Firewall on private networks).
Pids go to .dev/pids.json, logs to .dev/backend.log and .dev/frontend.log.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
DEV_STATE_DIR = REPO_ROOT / ".dev"
PIDS_PATH = DEV_STATE_DIR / "pids.json"
BACKEND_PORT = 8020
FRONTEND_PORT = 5520


def venv_python() -> str:
    for candidate in (BACKEND_DIR / ".venv" / "Scripts" / "python.exe", BACKEND_DIR / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    raise SystemExit(
        "No backend venv. Create it with:\n"
        "  cd backend && py -3.12 -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt"
    )


def lan_ip() -> str | None:
    # Connecting a UDP socket sends nothing; it just picks the outgoing interface.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def start(cmd: list[str], cwd: Path, log_name: str) -> int:
    log = (DEV_STATE_DIR / log_name).open("w")
    return subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT).pid


def wait_for(url: str, what: str) -> None:
    for _ in range(40):
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return
        except Exception:  # noqa: BLE001 - not up yet
            time.sleep(0.5)
    raise SystemExit(f"{what} did not start; see .dev/ logs, then run scripts/dev_down.py")


def main() -> int:
    if PIDS_PATH.exists():
        print("Dev stack already running (.dev/pids.json exists). Run scripts/dev_down.py first.")
        return 1
    DEV_STATE_DIR.mkdir(exist_ok=True)
    backend = start(
        # --reload: a code change restarts the backend (live rooms drop), so it never runs stale code
        [venv_python(), "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
         "--reload", "--reload-dir", "app"],
        BACKEND_DIR,
        "backend.log",
    )
    frontend = start(
        [sys.executable, str(REPO_ROOT / "scripts" / "serve_frontend.py"), str(FRONTEND_PORT)],
        REPO_ROOT,
        "frontend.log",
    )
    PIDS_PATH.write_text(json.dumps({"backend_pid": backend, "frontend_pid": frontend}))
    wait_for(f"http://127.0.0.1:{BACKEND_PORT}/games", "Backend")
    wait_for(f"http://127.0.0.1:{FRONTEND_PORT}/", "Frontend")

    local = f"http://localhost:{FRONTEND_PORT}"
    print(f"Card Table is up:\n  This PC:            {local}")
    ip = lan_ip()
    if ip:
        print(f"  Phone (same Wi-Fi): http://{ip}:{FRONTEND_PORT}")
    webbrowser.open(local)
    return 0


if __name__ == "__main__":
    sys.exit(main())
