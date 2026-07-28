"""Watchdog (rule #7): a background monitor for the whole system.

If the main loop stops emitting heartbeats past the threshold, the watchdog
persists state and performs a controlled shutdown instead of a silent hang.
``check()`` is synchronous and fully testable; ``start()`` wraps it in a thread.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

ALIVE = "ALIVE"
SHUTDOWN = "SHUTDOWN"


class Watchdog:
    def __init__(self, *, timeout_sec: float, on_freeze: Callable[[], None],
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.timeout_sec = timeout_sec
        self.on_freeze = on_freeze
        self._clock = clock
        self._last_beat = clock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.fired = False

    def beat(self) -> None:
        self._last_beat = self._clock()

    def check(self) -> str:
        if self._clock() - self._last_beat > self.timeout_sec and not self.fired:
            self.fired = True
            self.on_freeze()  # persist state + controlled shutdown
            return SHUTDOWN
        return SHUTDOWN if self.fired else ALIVE

    def start(self, interval_sec: float = 1.0) -> None:
        def loop() -> None:
            while not self._stop.wait(interval_sec):
                if self.check() == SHUTDOWN:
                    return

        self._thread = threading.Thread(target=loop, name="watchdog", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
