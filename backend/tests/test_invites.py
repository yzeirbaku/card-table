"""Invites in memory (spec 2026-11-02-friends-and-invites)."""

from app.invites import INVITE_SECONDS, REINVITE_SECONDS, Invite, Invites
from tests.murlan_helpers import FakeClock


def new_clock() -> FakeClock:
    clock = FakeClock()
    clock.now = 0.0
    return clock


def make(code="ABCD", to_id=2, at=0.0) -> Invite:
    return Invite(code, "Sebi", to_id, "Murlan", 4, at)


def open_always(code, uid) -> bool:
    return True


def test_reinvite_throttled_then_replaced():
    clock = new_clock()
    invites = Invites(clock)
    assert invites.add(make(at=0))
    assert not invites.add(make(at=REINVITE_SECONDS - 1))
    assert invites.add(make(at=REINVITE_SECONDS))
    assert [i.sent_at for i in invites.pending(2, open_always)] == [REINVITE_SECONDS]
    assert invites.add(make(code="WXYZ", at=REINVITE_SECONDS))  # another room is another key


def test_expires_after_15_minutes():
    clock = new_clock()
    invites = Invites(clock)
    invites.add(make(at=0))
    clock.now = INVITE_SECONDS - 1
    assert len(invites.pending(2, open_always)) == 1
    clock.now = INVITE_SECONDS
    assert invites.pending(2, open_always) == []


def test_pending_newest_first_and_only_open_ones():
    invites = Invites(new_clock())
    invites.add(make("AAAA", at=1))
    invites.add(make("BBBB", at=2))
    invites.add(make("CCCC", at=3))
    invites.add(make("DDDD", to_id=9, at=4))
    assert [i.code for i in invites.pending(2, lambda c, u: c != "BBBB")] == ["CCCC", "AAAA"]
    assert [i.code for i in invites.pending(2, open_always)] == ["CCCC", "AAAA"]  # BBBB is gone for good


def test_dismiss():
    invites = Invites(new_clock())
    invites.add(make("AAAA"))
    invites.add(make("BBBB"))
    invites.dismiss(2, "AAAA")
    assert [i.code for i in invites.pending(2, open_always)] == ["BBBB"]
    invites.dismiss(2, "AAAA")  # nothing to dismiss: no error


def test_prune():
    invites = Invites(new_clock())
    invites.add(make("AAAA", to_id=2))
    invites.add(make("AAAA", to_id=3))
    invites.add(make("BBBB", to_id=2))
    invites.prune("AAAA", lambda uid: uid == 3)
    assert [i.code for i in invites.pending(2, open_always)] == ["BBBB"]
    assert [i.code for i in invites.pending(3, open_always)] == ["AAAA"]
    invites.prune("AAAA", lambda _: False)
    assert invites.pending(3, open_always) == []
