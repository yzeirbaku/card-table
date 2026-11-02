"""Web Push: which phones want pushes for which account, and sending them. A
subscription belongs to the session that turned notifications on, so signing
out (or a password reset, which drops every session) ends it with the session.

Run once to make the VAPID keys for the server's .env:
    python -m app.push generate-keys"""

import asyncio
import base64
import json
import logging
import os
import sqlite3
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from .accounts import AccountError, User, session_key

log = logging.getLogger(__name__)

MAX_ENDPOINT = 1000
DEFAULT_SUBJECT = "mailto:yzeirbaku@hotmail.com"


@dataclass(frozen=True)
class PushKeys:
    public: str
    private: str
    subject: str


def keys_from_env() -> PushKeys | None:
    public, private = os.environ.get("VAPID_PUBLIC_KEY"), os.environ.get("VAPID_PRIVATE_KEY")
    if not public or not private:
        return None
    return PushKeys(public, private, os.environ.get("VAPID_SUBJECT") or DEFAULT_SUBJECT)


Sender = Callable[[dict, str, PushKeys], int]


def send_webpush(info: dict, data: str, keys: PushKeys) -> int:
    """Send one push; the HTTP status back, 0 if the push service couldn't be reached."""
    from pywebpush import WebPushException, webpush

    try:
        response = webpush(subscription_info=info, data=data, vapid_private_key=keys.private,
                           vapid_claims={"sub": keys.subject}, ttl=900, timeout=10)
    except WebPushException as e:
        return getattr(e.response, "status_code", 0) or 0
    return response.status_code


class Push:
    def __init__(self, conn: sqlite3.Connection, keys: PushKeys | None, send: Sender = send_webpush,
                 clock: Callable[[], float] = time.time) -> None:
        self.conn = conn
        self.keys = keys
        self.send = send
        self.clock = clock
        self.allowed: dict[tuple, float] = {}

    def subscribe(self, user: User, session_token: str, sub: dict) -> None:
        keys = sub.get("keys") if isinstance(sub, dict) else None
        endpoint = sub.get("endpoint") if isinstance(sub, dict) else None
        if not (isinstance(endpoint, str) and endpoint.startswith("https://") and len(endpoint) <= MAX_ENDPOINT
                and isinstance(keys, dict)
                and all(isinstance(keys.get(k), str) and keys[k] for k in ("p256dh", "auth"))):
            raise AccountError(400, "Bad subscription")
        self.conn.execute(
            "INSERT INTO push_subscriptions (endpoint, user_id, session, p256dh, auth, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(endpoint) DO UPDATE SET user_id = excluded.user_id,"
            " session = excluded.session, p256dh = excluded.p256dh, auth = excluded.auth,"
            " created_at = excluded.created_at",
            (endpoint, user.id, session_key(session_token), keys["p256dh"], keys["auth"], self.clock()))

    def unsubscribe(self, endpoint: str) -> None:
        self.conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))

    def is_on(self, session_token: str, endpoint: str) -> bool:
        return self.conn.execute("SELECT 1 FROM push_subscriptions WHERE endpoint = ? AND session = ?",
                                 (endpoint, session_key(session_token))).fetchone() is not None

    async def notify(self, user_id: int, payload: dict) -> None:
        """Push to each of the user's phones. Never raises: a push is a courtesy."""
        if self.keys is None:
            return
        try:
            rows = self.conn.execute(
                "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = ?", (user_id,)).fetchall()
            data = json.dumps(payload)
            for row in rows:
                info = {"endpoint": row["endpoint"], "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}}
                try:
                    status = await asyncio.to_thread(self.send, info, data, self.keys)
                except Exception:
                    log.exception("push to user %s failed", user_id)
                    continue
                if status in (404, 410):
                    self.unsubscribe(row["endpoint"])
                elif not 200 <= status < 300:
                    log.warning("push to user %s got status %s", user_id, status)
        except Exception:
            log.exception("push to user %s failed", user_id)

    def allow_once(self, key: tuple, seconds: float) -> bool:
        """True the first time within `seconds`: a throttle that lives in memory."""
        now = self.clock()
        if now - self.allowed.get(key, -seconds) < seconds:
            return False
        self.allowed = {k: t for k, t in self.allowed.items() if now - t < 86400}
        self.allowed[key] = now
        return True


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_keys() -> tuple[str, str]:
    """A new P-256 key as (public, private): the 65-byte point and the 32-byte value, base64url."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    public = key.public_key().public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    return _b64(public), _b64(key.private_numbers().private_value.to_bytes(32, "big"))


def main(argv: list[str]) -> int:
    if argv != ["generate-keys"]:
        print("usage: python -m app.push generate-keys", file=sys.stderr)
        return 2
    public, private = generate_keys()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
