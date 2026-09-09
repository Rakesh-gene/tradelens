"""Process-owned scheduling for the unattended all-equities pipeline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from threading import Event, Thread


INDIA_STANDARD_TIME = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")


def parse_schedule_time(value: str) -> time:
    """Parse a 24-hour HH:MM schedule value."""
    try:
        parsed = time.fromisoformat(value.strip())
    except (AttributeError, ValueError) as error:
        raise ValueError("PIPELINE_SCHEDULE_TIME must use 24-hour HH:MM format") from error
    if parsed.tzinfo is not None or parsed.second or parsed.microsecond:
        raise ValueError("PIPELINE_SCHEDULE_TIME must use 24-hour HH:MM format")
    return parsed


class DailyPipelineScheduler:
    """Ensure one incremental all-equities run is started each IST day."""

    def __init__(
        self,
        pipeline_service,
        *,
        schedule_time: time = time(19, 0),
        batch_size: int = 25,
        poll_seconds: float = 60,
        now: Callable[[], datetime] | None = None,
        error_handler: Callable[[Exception], None] | None = None,
    ) -> None:
        if not 1 <= batch_size <= 100:
            raise ValueError("pipeline scheduler batch size must be between 1 and 100")
        if poll_seconds <= 0:
            raise ValueError("pipeline scheduler poll interval must be positive")
        self._pipeline_service = pipeline_service
        self._schedule_time = schedule_time
        self._batch_size = batch_size
        self._poll_seconds = poll_seconds
        self._now = now or (lambda: datetime.now(INDIA_STANDARD_TIME))
        self._error_handler = error_handler or (lambda error: print(
            f"Pipeline scheduler error: {error}", flush=True
        ))
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._satisfied_date = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run, name="daily-pipeline-scheduler", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def tick(self) -> str:
        """Evaluate the schedule once; public to support deterministic tests."""
        current = self._now().astimezone(INDIA_STANDARD_TIME)
        current_date = current.date()
        if current.time().replace(tzinfo=None) < self._schedule_time:
            return "NOT_DUE"
        if self._satisfied_date == current_date:
            return "ALREADY_SCHEDULED"
        outcome = self._pipeline_service.ensure_scheduled_run(
            current_date, batch_size=self._batch_size
        )
        if outcome in {"STARTED", "RESUMED", "ALREADY_SCHEDULED"}:
            self._satisfied_date = current_date
        return outcome

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception as error:  # a transient failure must not kill scheduling
                self._error_handler(error)
            self._stop_event.wait(self._poll_seconds)
