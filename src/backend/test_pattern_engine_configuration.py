from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from pattern_engine.configuration import ConfigurationError, load_pattern_engine_configuration
from pattern_engine.enums import (
    ImportJobType,
    ImportStatus,
    PatternClass,
    PatternEventType,
    PatternState,
    SwingType,
    ZoneType,
)
from pattern_engine.models import PatternCandidate


class PatternEngineEnumTestCase(unittest.TestCase):
    def test_enums_serialize_to_canonical_identifiers(self) -> None:
        self.assertEqual([item.value for item in PatternClass], [
            "TREND", "BASE", "BREAKOUT", "PULLBACK", "COMPRESSION", "MOMENTUM", "FAILURE"
        ])
        self.assertEqual([item.value for item in PatternState], [
            "DETECTED", "FORMING", "MATURE", "READY", "TRIGGERED", "CONFIRMED", "FAILED",
            "INVALIDATED", "EXPIRED"
        ])
        self.assertEqual([item.value for item in PatternEventType], [
            "PATTERN_DETECTED", "STATE_CHANGED", "PIVOT_UPDATED", "QUALITY_CHANGED",
            "MATURITY_CHANGED", "TRIGGERED", "CONFIRMED", "FAILED", "INVALIDATED", "EXPIRED"
        ])
        self.assertEqual([item.value for item in SwingType], ["HIGH", "LOW"])
        self.assertEqual([item.value for item in ZoneType], ["RESISTANCE", "SUPPORT"])
        self.assertEqual([item.value for item in ImportJobType], [
            "EQUITY_MASTER", "HISTORY_BACKFILL", "CORPORATE_ACTION_BACKFILL", "DAILY_DELTA",
            "ADJUSTMENT_REBUILD", "FEATURE_REBUILD", "PATTERN_SCAN"
        ])
        self.assertEqual([item.value for item in ImportStatus], [
            "PENDING", "RUNNING", "COMPLETED", "PARTIAL", "FAILED", "CANCELLED"
        ])


class PatternEngineConfigurationTestCase(unittest.TestCase):
    def test_default_configuration_loads_with_immutable_sections(self) -> None:
        configuration = load_pattern_engine_configuration()

        self.assertEqual(configuration.version, "v1")
        self.assertEqual(configuration.section("setup_weights")["pattern_quality"], 35.0)
        self.assertEqual(configuration.section("adjustments")["cash_dividend_policy"], "ignore")
        self.assertEqual(configuration.section("operations")["daily_processing_window_minutes"], 120)
        with self.assertRaises(TypeError):
            configuration.section("setup_weights")["pattern_quality"] = 0.0  # type: ignore[index]

    def test_invalid_weight_total_fails_with_clear_message(self) -> None:
        self._assert_invalid_configuration(
            '[setup_weights]\npattern_quality = 1.0\npattern_maturity = 1.0\ntrend = 1.0\nrelative_strength = 1.0\nsector = 1.0\nvolume = 1.0\n',
            "setup_weights weights must sum to 100",
        )

    def test_invalid_minimum_maximum_range_fails_with_clear_message(self) -> None:
        self._assert_invalid_configuration(
            '[vcp]\nmin_duration_sessions = 91\nmax_duration_sessions = 90\n',
            "vcp.min_duration_sessions cannot exceed max_duration_sessions",
        )

    def test_invalid_percentage_fails_with_clear_message(self) -> None:
        self._assert_invalid_configuration(
            '[zones]\ntolerance_pct = 101.0\nmaximum_dispersion_pct = 3.0\nminimum_tests = 2\nlookback_sessions = 120\n',
            "zones.tolerance_pct must be between 0 and 100",
        )

    def test_empty_configuration_version_fails_with_clear_message(self) -> None:
        self._assert_invalid_configuration(
            '[engine]\nversion = ""\nminimum_history_sessions = 250\n',
            "engine.version must be a non-empty string",
        )

    def _assert_invalid_configuration(self, replacement: str, expected_message: str) -> None:
        source = Path(__file__).resolve().parent / "configuration" / "pattern_engine.toml"
        original = source.read_text(encoding="utf-8")
        section_name = replacement.split("\n", 1)[0]
        start = original.index(section_name)
        next_section = original.find("\n[", start + len(section_name))
        modified = original[:start] + replacement + ("\n" + original[next_section + 1 :] if next_section != -1 else "")

        with tempfile.NamedTemporaryFile("w", suffix=".toml", encoding="utf-8", delete=False) as file_handle:
            file_handle.write(modified)
            temporary_path = Path(file_handle.name)
        try:
            with self.assertRaisesRegex(ConfigurationError, expected_message):
                load_pattern_engine_configuration(temporary_path)
        finally:
            temporary_path.unlink(missing_ok=True)


class PatternEngineModelTestCase(unittest.TestCase):
    def test_candidate_serialization_preserves_measurements_lists_and_optional_values(self) -> None:
        candidate = PatternCandidate(
            isin="INE000000001",
            pattern_class=PatternClass.BASE,
            pattern_type="BASE-VCP",
            variant="VCP-3C",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 9, 4),
            detected_date=date(2026, 9, 4),
            state=PatternState.READY,
            quality_score=Decimal("92.0"),
            maturity_score=Decimal("88.0"),
            context_score=None,
            setup_score=Decimal("89.0"),
            pivot_price=Decimal("500.00"),
            support_price=Decimal("462.00"),
            invalidation_price=None,
            measurements={
                "contractions_pct": (Decimal("14.8"), Decimal("8.3"), Decimal("4.7")),
                "volume_compression": Decimal("0.51"),
                "optional_note": None,
            },
            supporting_pattern_identifiers=("TREND-S2", "VOL-DRY"),
            invalidation_rule=None,
        )

        payload = candidate.to_dict()

        self.assertEqual(payload["pattern_class"], "BASE")
        self.assertEqual(payload["state"], "READY")
        self.assertEqual(payload["measurements"]["contractions_pct"], ["14.8", "8.3", "4.7"])
        self.assertEqual(payload["measurements"]["optional_note"], None)
        self.assertEqual(payload["supporting_pattern_identifiers"], ["TREND-S2", "VOL-DRY"])
        self.assertIsNone(payload["invalidation_price"])
        with self.assertRaises(TypeError):
            candidate.measurements["volume_compression"] = Decimal("0.60")  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
