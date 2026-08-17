from __future__ import annotations

from datetime import date, datetime
import threading
import time
from typing import Callable


class DailyScheduler:
    def __init__(self, daily_hour: int, task: Callable[[], None]):
        self.daily_hour = daily_hour
        self.task = task
        self._last_run: date | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="auto-paper-daily", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now()
            if now.hour >= self.daily_hour and self._last_run != now.date():
                self.task()
                self._last_run = now.date()
            self._stop.wait(60)

