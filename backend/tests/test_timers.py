import asyncio
import time

from app.timers import RoomTimer


def test_wakes_at_the_deadline():
    async def main():
        fired = []

        async def wake():
            fired.append(time.monotonic())

        timer = RoomTimer(time.monotonic)
        start = time.monotonic()
        timer.set(start + 0.05, wake)
        await asyncio.sleep(0.2)
        return start, fired

    start, fired = asyncio.run(main())
    assert len(fired) == 1 and fired[0] >= start + 0.04


def test_a_new_deadline_replaces_the_old_one():
    async def main():
        fired = []

        def waker(name):
            async def wake():
                fired.append(name)
            return wake

        now = time.monotonic()
        timer = RoomTimer(time.monotonic)
        timer.set(now + 0.03, waker("first"))
        timer.set(now + 0.06, waker("second"))
        other = RoomTimer(time.monotonic)
        other.set(now + 0.03, waker("cancelled"))
        other.set(None, waker("never"))
        await asyncio.sleep(0.2)
        return fired

    assert asyncio.run(main()) == ["second"]


def test_a_wake_can_set_the_next_deadline():
    async def main():
        fired = []
        timer = RoomTimer(time.monotonic)

        async def wake():
            fired.append(len(fired))
            if len(fired) < 3:
                timer.set(time.monotonic() + 0.01, wake)

        timer.set(time.monotonic() + 0.01, wake)
        await asyncio.sleep(0.3)
        return fired

    assert asyncio.run(main()) == [0, 1, 2]
