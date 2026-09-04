"""Stable domain contracts for the positional trading pattern engine."""

from pattern_engine.configuration import (
    ConfigurationError,
    PatternEngineConfiguration,
    load_pattern_engine_configuration,
)

__all__ = [
    "ConfigurationError",
    "PatternEngineConfiguration",
    "load_pattern_engine_configuration",
]
from .features import FeatureService, assign_relative_strength_percentiles, compute_features
from .swings import SwingZoneService, build_price_zones, detect_swings

__all__ = ["FeatureService", "SwingZoneService", "assign_relative_strength_percentiles", "build_price_zones", "compute_features", "detect_swings"]
