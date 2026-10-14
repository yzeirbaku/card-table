"""Stop the dev stack started by dev_up.py."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

PIDS_PATH = Path(__file__).resolve().parent.parent / ".dev" / "pids.json"


def kill(pid: int, label: str) -> None:
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, text=True)
        print(f"  {label} (pid {pid}): {'stopped' if r.returncode == 0 else 'already gone'}")
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  {label} (pid {pid}): stopped")
        except ProcessLookupError:
            print(f"  {label} (pid {pid}): already gone")


def main() -> int:
    if not PIDS_PATH.exists():
        print("Nothing running (no .dev/pids.json).")
        return 0
    pids = json.loads(PIDS_PATH.read_text())
    kill(pids["backend_pid"], "backend")
    kill(pids["frontend_pid"], "frontend")
    PIDS_PATH.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
