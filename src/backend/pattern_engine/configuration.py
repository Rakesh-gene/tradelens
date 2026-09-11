"""Loading and validation for the versioned pattern-engine TOML configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping
import tomllib


class ConfigurationError(ValueError):
    """Raised when engine configuration cannot safely be used."""


REQUIRED_SECTIONS = frozenset(
    {
        "engine",
        "data",
        "operations",
        "adjustments",
        "swings",
        "zones",
        "liquidity",
        "vcp",
        "flat_base",
        "base_52wh",
        "breakout",
        "breakout_retest",
        "ema20_pullback",
        "sma50_pullback",
        "trend",
        "compression",
        "momentum",
        "volume",
        "failure",
        "quality_weights",
        "maturity_weights",
        "context_weights",
        "setup_weights",
    }
)

WEIGHT_SECTIONS = (
    "quality_weights",
    "maturity_weights",
    "context_weights",
    "setup_weights",
)

MIN_MAX_RULES = (
    ("vcp", "min_duration_sessions", "max_duration_sessions"),
    ("vcp", "min_depth_pct", "max_depth_pct"),
    ("vcp", "min_contractions", "max_contractions"),
    ("flat_base", "min_duration_sessions", "max_duration_sessions"),
    ("flat_base", "min_depth_pct", "max_depth_pct"),
    ("base_52wh", "min_duration_sessions", "max_duration_sessions"),
    ("base_52wh", "min_depth_pct", "max_depth_pct"),
    ("breakout", "lookback_min_sessions", "lookback_max_sessions"),
    ("breakout_retest", "min_sessions_after_breakout", "max_sessions_after_breakout"),
    ("breakout_retest", "preferred_min_sessions", "preferred_max_sessions"),
    ("ema20_pullback", "min_depth_pct", "max_depth_pct"),
    ("ema20_pullback", "min_duration_sessions", "max_duration_sessions"),
    ("sma50_pullback", "min_depth_pct", "max_depth_pct"),
    ("sma50_pullback", "min_duration_sessions", "max_duration_sessions"),
)


@dataclass(frozen=True, slots=True)
class PatternEngineConfiguration:
    """Validated configuration with immutable nested section mappings."""

    version: str
    sections: Mapping[str, Mapping[str, object]]

    def section(self, name: str) -> Mapping[str, object]:
        try:
            return self.sections[name]
        except KeyError as exc:
            raise ConfigurationError(f"Configuration section '{name}' is not defined") from exc


def default_configuration_path() -> Path:
    return Path(__file__).resolve().parents[1] / "configuration" / "pattern_engine.toml"


def load_pattern_engine_configuration(path: Path | str | None = None) -> PatternEngineConfiguration:
    """Load the default configuration or a supplied TOML file and validate it."""

    configuration_path = Path(path) if path is not None else default_configuration_path()
    try:
        with configuration_path.open("rb") as file_handle:
            raw_configuration = tomllib.load(file_handle)
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Pattern-engine configuration was not found: {configuration_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Pattern-engine configuration is invalid TOML: {exc}") from exc

    _validate_configuration(raw_configuration)
    sections = {
        section_name: _freeze_mapping(section_values)
        for section_name, section_values in raw_configuration.items()
    }
    engine = raw_configuration["engine"]
    return PatternEngineConfiguration(
        version=str(engine["version"]).strip(),
        sections=MappingProxyType(sections),
    )


def _validate_configuration(configuration: Mapping[str, Any]) -> None:
    missing_sections = sorted(REQUIRED_SECTIONS - configuration.keys())
    if missing_sections:
        raise ConfigurationError(
            f"Pattern-engine configuration is missing sections: {', '.join(missing_sections)}"
        )

    for section_name in REQUIRED_SECTIONS:
        if not isinstance(configuration[section_name], Mapping):
            raise ConfigurationError(f"Configuration section '{section_name}' must be a table")

    version = configuration["engine"].get("version")
    if not isinstance(version, str) or not version.strip():
        raise ConfigurationError("Configuration engine.version must be a non-empty string")

    _validate_min_max_rules(configuration)
    _validate_positive_lookbacks(configuration)
    _validate_percentage_bounds(configuration)
    _validate_weights(configuration)
    _validate_adjustment_policy(configuration)


def _validate_min_max_rules(configuration: Mapping[str, Any]) -> None:
    for section_name, minimum_name, maximum_name in MIN_MAX_RULES:
        section = configuration[section_name]
        minimum = section.get(minimum_name)
        maximum = section.get(maximum_name)
        if not _is_number(minimum) or not _is_number(maximum):
            raise ConfigurationError(
                f"Configuration {section_name}.{minimum_name} and {maximum_name} must be numeric"
            )
        if minimum > maximum:
            raise ConfigurationError(
                f"Configuration {section_name}.{minimum_name} cannot exceed {maximum_name}"
            )


def _validate_positive_lookbacks(configuration: Mapping[str, Any]) -> None:
    positive_name_fragments = (
        "lookback",
        "sessions",
        "duration",
        "window",
        "history",
        "period",
        "bars",
        "tests",
        "touches",
        "contractions",
        "pairs",
    )
    for section_name, section in configuration.items():
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            if any(fragment in key for fragment in positive_name_fragments):
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise ConfigurationError(
                        f"Configuration {section_name}.{key} must be a positive integer"
                    )


def _validate_percentage_bounds(configuration: Mapping[str, Any]) -> None:
    for section_name, section in configuration.items():
        if not isinstance(section, Mapping):
            continue
        for key, value in section.items():
            if key.endswith("_pct") or key.endswith("_percent") or key.endswith("_tolerance"):
                if not _is_number(value) or value < 0 or value > 100:
                    raise ConfigurationError(
                        f"Configuration {section_name}.{key} must be between 0 and 100"
                    )


def _validate_weights(configuration: Mapping[str, Any]) -> None:
    for section_name in WEIGHT_SECTIONS:
        section = configuration[section_name]
        if not section:
            raise ConfigurationError(f"Configuration {section_name} must not be empty")
        if not all(_is_number(value) and value >= 0 for value in section.values()):
            raise ConfigurationError(f"Configuration {section_name} values must be non-negative numbers")
        total = sum(section.values())
        if abs(total - 100) > 0.000001:
            raise ConfigurationError(
                f"Configuration {section_name} weights must sum to 100; received {total}"
            )


def _validate_adjustment_policy(configuration: Mapping[str, Any]) -> None:
    adjustments = configuration["adjustments"]
    version = adjustments.get("methodology_version")
    if not isinstance(version, str) or not version.strip():
        raise ConfigurationError("Configuration adjustments.methodology_version must be non-empty")
    if adjustments.get("source_mode") not in {"NSE_SOURCE", "TRADELENS_REBUILT"}:
        raise ConfigurationError("Configuration adjustments.source_mode is invalid")
    if adjustments.get("cash_dividend_policy") not in {"ignore", "adjust_price"}:
        raise ConfigurationError("Configuration adjustments.cash_dividend_policy is invalid")
    maximum_jump = adjustments.get("maximum_adjusted_ex_date_jump_pct")
    if not _is_number(maximum_jump) or maximum_jump <= 0:
        raise ConfigurationError(
            "Configuration adjustments.maximum_adjusted_ex_date_jump_pct must be positive"
        )


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen_values: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            frozen_values[key] = _freeze_mapping(item)
        elif isinstance(item, list):
            frozen_values[key] = tuple(item)
        else:
            frozen_values[key] = item
    return MappingProxyType(frozen_values)
