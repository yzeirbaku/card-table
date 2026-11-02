"""Invites to a lobby, kept in memory like the rooms they point at (spec 2026-11-02-friends-and-invites)."""

from collections.abc import Callable
from dataclasses import dataclass

INVITE_SECONDS = 900  # an invite lasts 15 minutes
REINVITE_SECONDS = 30  # the same friend to the same room, at most this often


@dataclass
class Invite:
    code: str
    from_name: str
    to_id: int
    game: str  # the display name, "Murlan"
    players: int
    sent_at: float


class Invites:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.sent: dict[tuple[str, int], Invite] = {}

    def add(self, invite: Invite) -> bool:
        """False if the same friend was invited to the same room just now."""
        old = self.sent.get((invite.code, invite.to_id))
        if old is not None and invite.sent_at - old.sent_at < REINVITE_SECONDS:
            return False
        self.sent[(invite.code, invite.to_id)] = invite
        return True

    def pending(self, user_id: int, is_open: Callable[[str, int], bool]) -> list[Invite]:
        """Their invites, newest first. Expired ones and those to a table that is no longer open are dropped for good."""
        now = self.clock()
        for key, inv in list(self.sent.items()):
            if now - inv.sent_at >= INVITE_SECONDS or (inv.to_id == user_id and not is_open(inv.code, user_id)):
                del self.sent[key]
        mine = [i for i in self.sent.values() if i.to_id == user_id]
        return sorted(mine, key=lambda i: i.sent_at, reverse=True)

    def dismiss(self, user_id: int, code: str) -> None:
        self.sent.pop((code, user_id), None)

    def prune(self, code: str, keep: Callable[[int], bool]) -> None:
        """Drop the invites to this room whose friend `keep` refuses."""
        for key, inv in list(self.sent.items()):
            if inv.code == code and not keep(inv.to_id):
                del self.sent[key]
