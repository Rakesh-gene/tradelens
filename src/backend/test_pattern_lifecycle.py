from __future__ import annotations

from datetime import date, timedelta
from dataclasses import replace
from decimal import Decimal
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.enums import PatternClass, PatternEventType, PatternState
from pattern_engine.lifecycle import PatternLifecycleService
from pattern_engine.models import DetectionContext, PatternCandidate
from pattern_engine.scoring import bounded_component, maturity_band, score_candidate
from repositories.patterns import InMemoryPatternRepository


_D = Decimal
_ISIN = "INE000000001"


def _candidate(
    state=PatternState.FORMING, *, detected=date(2026, 9, 1),
    start=date(2026, 8, 1), pattern_type="BASE-VCP",
    pattern_class=PatternClass.BASE, quality=_D("80"), maturity=_D("70"),
):
    return PatternCandidate(
        _ISIN, pattern_class, pattern_type, "VCP-3C" if pattern_type == "BASE-VCP" else None,
        start, detected, detected, state, quality, maturity, None, None,
        _D("120"), _D("100"), _D("98"), {"depth": _D("12")},
        ("TREND-S2",), "structure_break",
    )


class ScoringTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()

    def test_bounded_component_and_maturity_boundaries(self):
        self.assertEqual((_D("100"), _D("20")), bounded_component(120, 20))
        self.assertEqual((_D("0"), _D("0")), bounded_component(-5, 20))
        self.assertEqual("EARLY", maturity_band(39))
        self.assertEqual("FORMING", maturity_band(40))
        self.assertEqual("MATURE", maturity_band(65))
        self.assertEqual("READY", maturity_band(80))
        self.assertEqual("IMMINENT", maturity_band(90))

    def test_context_and_setup_scores_do_not_change_geometry(self):
        candidate = _candidate()
        feature = {
            "ema_20": _D("105"), "sma_50": _D("100"), "sma_200": _D("90"),
            "ema_20_slope": _D("1"), "sma_50_slope": _D("1"),
            "relative_strength_percentile": _D("90"), "volume_ratio_20": _D("1.2"),
            "median_traded_value_20": _D("25000000"), "median_volume_20": _D("1000"),
        }
        context = DetectionContext(
            candidate.detected_date, {"market_regime_score": _D("60")},
            {"sector_strength_score": _D("80")}, (), "v1",
        )

        result = score_candidate(
            candidate, feature, context, self.configuration,
            close_price=_D("110"), history_sessions=300,
        )

        self.assertEqual(_D("83"), result.context.total)
        self.assertEqual(_D("83.5"), result.setup.total)
        self.assertEqual(_D("100"), result.context.normalized_inputs["volume"])
        self.assertEqual("MATURE", result.maturity_band)
        self.assertEqual(candidate.start_date, result.candidate.start_date)
        self.assertEqual(candidate.pivot_price, result.candidate.pivot_price)
        self.assertEqual(candidate.measurements, result.candidate.measurements)
        self.assertEqual(_D("83"), result.candidate.context_score)
        self.assertEqual(_D("83.5"), result.candidate.setup_score)


class LifecycleTestCase(unittest.TestCase):
    def setUp(self):
        self.configuration = load_pattern_engine_configuration()
        self.repository = InMemoryPatternRepository()
        self.service = PatternLifecycleService(self.repository, self.configuration)

    def _apply(self, candidate):
        return self.service.apply_candidate(
            candidate, engine_version="v1", feature_version="features-v1",
            adjustment_version="adjusted-v1",
        )

    def test_daily_candidates_update_one_instance_and_emit_only_meaningful_events(self):
        first = self._apply(_candidate())
        second_day = date(2026, 9, 2)
        second = self._apply(_candidate(PatternState.READY, detected=second_day))
        third = self._apply(_candidate(PatternState.READY, detected=date(2026, 9, 3)))

        self.assertEqual("created", first.action)
        self.assertEqual("updated", second.action)
        self.assertEqual(first.instance["id"], second.instance["id"])
        self.assertEqual(first.instance["id"], third.instance["id"])
        self.assertEqual(1, len(self.repository.instances))
        self.assertEqual(
            [PatternEventType.PATTERN_DETECTED.value, PatternEventType.STATE_CHANGED.value],
            [event["event_type"] for event in self.repository.events],
        )
        self.assertEqual(2, third.instance["state_version"])

    def test_weaker_daily_evidence_retains_forward_state_and_terminal_history(self):
        self._apply(_candidate(PatternState.READY))
        retained = self._apply(
            _candidate(
                PatternState.FORMING, detected=date(2026, 9, 2),
                quality=_D("62"), maturity=_D("54"),
            )
        )

        self.assertEqual(PatternState.READY.value, retained.instance["state"])
        self.assertEqual(_D("62"), retained.instance["quality_score"])
        self.assertEqual("FORMING", retained.instance["measurements"]["observed_state"])
        self.assertEqual("READY", retained.instance["measurements"]["lifecycle_state_retained"])

        terminal = self._apply(
            _candidate(PatternState.INVALIDATED, detected=date(2026, 9, 2))
        )
        self.assertEqual(PatternEventType.INVALIDATED, terminal.event_type)
        self.assertEqual(date(2026, 9, 2), terminal.instance["terminal_date"])
        self.assertEqual(
            [PatternEventType.PATTERN_DETECTED.value, PatternEventType.INVALIDATED.value],
            [
                event["event_type"]
                for event in self.repository.load_events(terminal.instance["id"])
                if event["event_type"] in {
                    PatternEventType.PATTERN_DETECTED.value,
                    PatternEventType.INVALIDATED.value,
                }
            ],
        )

    def test_exact_deduplication_key_wins_over_newer_approximate_match(self):
        exact = self._apply(_candidate(detected=date(2026, 9, 1)))
        exact_key = exact.instance["active_deduplication_key"]
        self.repository.instances["newer-approximate"] = {
            **exact.instance,
            "id": "newer-approximate",
            "start_date": date(2026, 8, 2),
            "last_updated_date": date(2026, 9, 3),
            "pivot_price": _D("121"),
            "active_deduplication_key": "different-key",
        }

        result = self._apply(_candidate(PatternState.READY, detected=date(2026, 9, 4)))

        self.assertEqual(exact_key, result.instance["active_deduplication_key"])
        self.assertEqual(exact.instance["id"], result.instance["id"])

    def test_score_and_pivot_changes_emit_one_reconstructable_event(self):
        first = self._apply(_candidate())
        changed = replace(
            _candidate(detected=date(2026, 9, 2)),
            quality_score=_D("85"),
            pivot_price=_D("121"),
        )
        result = self._apply(changed)

        self.assertEqual(PatternEventType.PIVOT_UPDATED, result.event_type)
        event = self.repository.events[-1]
        self.assertEqual("120", event["previous_values"]["pivot_price"])
        self.assertEqual("121", event["new_values"]["pivot_price"])
        self.assertEqual(first.instance["id"], result.instance["id"])

    def test_adjustment_rebase_invalidates_old_price_scale_before_new_detection(self):
        old = self._apply(_candidate(PatternState.READY))

        invalidated = self.service.invalidate_adjustment_mismatches(
            _ISIN, "adjusted-v2", date(2026, 9, 2)
        )
        replacement = self.service.apply_candidate(
            replace(
                _candidate(PatternState.FORMING, detected=date(2026, 9, 2)),
                pivot_price=_D("24"), support_price=_D("20"),
                invalidation_price=_D("19.6"),
            ),
            engine_version="v1", feature_version="features-v1",
            adjustment_version="adjusted-v2",
        )

        self.assertEqual(1, len(invalidated))
        self.assertEqual(PatternState.INVALIDATED.value, invalidated[0].instance["state"])
        self.assertEqual(date(2026, 9, 2), invalidated[0].instance["terminal_date"])
        self.assertEqual(
            "ADJUSTMENT_VERSION_CHANGED",
            invalidated[0].instance["measurements"]["invalidation_reason"],
        )
        self.assertNotEqual(old.instance["id"], replacement.instance["id"])
        self.assertEqual("adjusted-v2", replacement.instance["adjustment_version"])

    def test_confirmed_candidate_preserves_breakout_trigger_date(self):
        breakout_date = date(2026, 8, 29)
        candidate = replace(
            _candidate(
                PatternState.CONFIRMED, pattern_type="BRK-RANGE",
                pattern_class=PatternClass.BREAKOUT,
            ),
            measurements={"breakout_date": breakout_date},
        )

        created = self._apply(candidate)

        self.assertEqual(breakout_date, created.instance["trigger_date"])
        self.assertEqual(candidate.detected_date, created.instance["confirmation_date"])

    def test_stale_base_and_each_pullback_family_expire_by_trading_sessions(self):
        start = date(2026, 1, 1)
        trading_dates = [start + timedelta(days=index) for index in range(100)]
        base = _candidate(
            detected=trading_dates[90], start=trading_dates[0],
            pattern_type="BASE-VCP", pattern_class=PatternClass.BASE,
        )
        created = self._apply(base)
        pullback = _candidate(
            detected=trading_dates[90], start=trading_dates[80],
            pattern_type="PB-EMA20", pattern_class=PatternClass.PULLBACK,
        )
        pullback_created = self._apply(pullback)
        retest = _candidate(
            detected=trading_dates[90], start=trading_dates[60],
            pattern_type="PB-BRKRET", pattern_class=PatternClass.PULLBACK,
        )
        self._apply(retest)
        sma50_pullback = _candidate(
            detected=trading_dates[90], start=trading_dates[70],
            pattern_type="PB-SMA50", pattern_class=PatternClass.PULLBACK,
        )
        self._apply(sma50_pullback)

        expired = self.service.expire_stale(_ISIN, trading_dates[91], trading_dates)

        self.assertEqual(4, len(expired))
        self.assertTrue(all(item.instance["state"] == PatternState.EXPIRED.value for item in expired))
        self.assertTrue(all(item.event_type is PatternEventType.EXPIRED for item in expired))
        self.assertEqual(
            [PatternEventType.PATTERN_DETECTED.value, PatternEventType.EXPIRED.value],
            [event["event_type"] for event in self.repository.load_events(created.instance["id"])],
        )
        self.assertEqual(
            [PatternEventType.PATTERN_DETECTED.value, PatternEventType.EXPIRED.value],
            [event["event_type"] for event in self.repository.load_events(pullback_created.instance["id"])],
        )


if __name__ == "__main__":
    unittest.main()
