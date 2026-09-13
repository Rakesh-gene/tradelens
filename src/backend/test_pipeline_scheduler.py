from datetime import datetime, time
import unittest

from operations.pipeline_scheduler import DailyPipelineScheduler, INDIA_STANDARD_TIME, parse_schedule_time


class RecordingPipelineService:
    def __init__(self, outcomes=("STARTED",)):
        self.outcomes = list(outcomes)
        self.calls = []

    def ensure_scheduled_run(self, scheduled_for, *, batch_size):
        self.calls.append((scheduled_for, batch_size))
        return self.outcomes.pop(0)


class DailyPipelineSchedulerTestCase(unittest.TestCase):
    def test_does_not_run_before_7pm_ist(self):
        service = RecordingPipelineService()
        scheduler = DailyPipelineScheduler(
            service, now=lambda: datetime(2026, 9, 9, 18, 59, tzinfo=INDIA_STANDARD_TIME)
        )

        self.assertEqual("NOT_DUE", scheduler.tick())
        self.assertEqual([], service.calls)

    def test_runs_at_7pm_and_only_once_per_process_day(self):
        service = RecordingPipelineService()
        scheduler = DailyPipelineScheduler(
            service,
            schedule_time=time(19, 0),
            batch_size=40,
            now=lambda: datetime(2026, 9, 9, 19, 0, tzinfo=INDIA_STANDARD_TIME),
        )

        self.assertEqual("STARTED", scheduler.tick())
        self.assertEqual("ALREADY_SCHEDULED", scheduler.tick())
        self.assertEqual([(datetime(2026, 9, 9).date(), 40)], service.calls)

    def test_retries_after_an_active_run_finishes(self):
        service = RecordingPipelineService(("ACTIVE_RUN", "STARTED"))
        scheduler = DailyPipelineScheduler(
            service, now=lambda: datetime(2026, 9, 9, 20, 0, tzinfo=INDIA_STANDARD_TIME)
        )

        self.assertEqual("ACTIVE_RUN", scheduler.tick())
        self.assertEqual("STARTED", scheduler.tick())
        self.assertEqual(2, len(service.calls))

    def test_a_resumed_run_satisfies_the_schedule(self):
        service = RecordingPipelineService(("RESUMED",))
        scheduler = DailyPipelineScheduler(
            service, now=lambda: datetime(2026, 9, 9, 20, 0, tzinfo=INDIA_STANDARD_TIME)
        )

        self.assertEqual("RESUMED", scheduler.tick())
        self.assertEqual("ALREADY_SCHEDULED", scheduler.tick())
        self.assertEqual(1, len(service.calls))

    def test_skips_an_nse_market_holiday(self):
        service = RecordingPipelineService()
        scheduler = DailyPipelineScheduler(
            service, now=lambda: datetime(2026, 1, 26, 20, 0, tzinfo=INDIA_STANDARD_TIME),
            is_trading_day=lambda market_date: False,
        )

        self.assertEqual("MARKET_HOLIDAY", scheduler.tick())
        self.assertEqual("ALREADY_SCHEDULED", scheduler.tick())
        self.assertEqual([], service.calls)

    def test_parses_only_hour_and_minute(self):
        self.assertEqual(time(19, 0), parse_schedule_time("19:00"))
        for invalid in ("7 PM", "19:00:30", ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_schedule_time(invalid)


if __name__ == "__main__":
    unittest.main()
