"""Stable, lazily loaded contracts for the positional pattern engine.

Keeping service exports lazy matters because repositories import the enum
module during startup, before services that depend on repositories are safe to
import.
"""

from importlib import import_module

from pattern_engine.configuration import (
    ConfigurationError,
    PatternEngineConfiguration,
    load_pattern_engine_configuration,
)

_LAZY_EXPORTS = {
    "FeatureService": ("features", "FeatureService"),
    "assign_relative_strength_percentiles": ("features", "assign_relative_strength_percentiles"),
    "compute_features": ("features", "compute_features"),
    "SwingZoneService": ("swings", "SwingZoneService"),
    "build_price_zones": ("swings", "build_price_zones"),
    "detect_swings": ("swings", "detect_swings"),
    "SupportingPatternService": ("supporting_detectors", "SupportingPatternService"),
    "detect_supporting_patterns": ("supporting_detectors", "detect_supporting_patterns"),
    "PrimaryBaseService": ("base_detectors", "PrimaryBaseService"),
    "detect_primary_bases": ("base_detectors", "detect_primary_bases"),
    "BreakoutService": ("breakout_detectors", "BreakoutService"),
    "detect_breakouts": ("breakout_detectors", "detect_breakouts"),
    "PullbackService": ("pullback_detectors", "PullbackService"),
    "detect_pullbacks": ("pullback_detectors", "detect_pullbacks"),
    "FailurePatternService": ("failure_detectors", "FailurePatternService"),
    "detect_failures": ("failure_detectors", "detect_failures"),
    "PatternLifecycleService": ("lifecycle", "PatternLifecycleService"),
    "bounded_component": ("scoring", "bounded_component"),
    "maturity_band": ("scoring", "maturity_band"),
    "score_candidate": ("scoring", "score_candidate"),
    "weighted_score": ("scoring", "weighted_score"),
    "PatternEngineRunner": ("runner", "PatternEngineRunner"),
    "PatternEngineVersions": ("runner", "PatternEngineVersions"),
    "PatternScanMode": ("runner", "PatternScanMode"),
    "BacktestService": ("research", "BacktestService"),
    "PatternReplayEvaluator": ("research", "PatternReplayEvaluator"),
    "calculate_outcomes": ("research", "calculate_outcomes"),
    "summarize_results": ("research", "summarize_results"),
}

__all__ = [
    "ConfigurationError",
    "PatternEngineConfiguration",
    "load_pattern_engine_configuration",
    *_LAZY_EXPORTS,
]


def __getattr__(name):
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute_name)
    globals()[name] = value
    return value
