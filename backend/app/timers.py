"""Wakes a room when its game has something timed to do (a reveal ending, the
pause countdown running out), so it happens without anyone sending a message."""

import asyncio
from collections.abc import Awaitable, Callable


class RoomTimer:
    """At most one pending wake-up; setting a new deadline replaces the old one."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._task: asyncio.Task | None = None
        self._deadline: float | None = None

    def set(self, deadline: float | None, wake: Callable[[], Awaitable[None]]) -> None:
        if deadline is not None and deadline == self._deadline and self._task is not None:
            return
        self.cancel()
        if deadline is None:
            return
        self._deadline = deadline
        self._task = asyncio.get_running_loop().create_task(self._run(deadline, wake))

    def cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self._task = None
        self._deadline = None

    async def _run(self, deadline: float, wake: Callable[[], Awaitable[None]]) -> None:
        await asyncio.sleep(max(0.0, deadline - self._clock()))
        # Done waiting: forget this task first, so a set() made during wake()
        # schedules the next wake-up instead of cancelling this one.
        self._task = None
        self._deadline = None
        await wake()
