"""Bounded Phase 13 context and setup scoring, separate from detector geometry."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.models import DetectionContext, PatternCandidate


_D = Decimal


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    total: Decimal
    normalized_inputs: Mapping[str, Decimal]
    contributions: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        object.__setattr__(self, "normalized_inputs", MappingProxyType(dict(self.normalized_inputs)))
        object.__setattr__(self, "contributions", MappingProxyType(dict(self.contributions)))


@dataclass(frozen=True, slots=True)
class CandidateScoreResult:
    candidate: PatternCandidate
    context: ScoreBreakdown
    setup: ScoreBreakdown
    maturity_band: str


def bounded_component(value: object | None, weight: object) -> tuple[Decimal, Decimal]:
    """Return a normalized 0-100 input and its bounded weighted contribution."""

    normalized = _clamp(_decimal(value) if value is not None else _D("0"))
    component_weight = max(_D("0"), _decimal(weight))
    return normalized, normalized * component_weight / 100


def weighted_score(values: Mapping[str, object | None], weights: Mapping[str, object]) -> ScoreBreakdown:
    normalized: dict[str, Decimal] = {
        name: _clamp(_decimal(value) if value is not None else _D("0"))
        for name, value in values.items()
    }
    contributions: dict[str, Decimal] = {}
    for name, weight in weights.items():
        normalized[name], contributions[name] = bounded_component(values.get(name), weight)
    return ScoreBreakdown(_clamp(sum(contributions.values(), _D("0"))), normalized, contributions)


def maturity_band(score: object | None) -> str:
    if score is None:
        return "UNAVAILABLE"
    value = _clamp(_decimal(score))
    if value < 40:
        return "EARLY"
    if value < 65:
        return "FORMING"
    if value < 80:
        return "MATURE"
    if value < 90:
        return "READY"
    return "IMMINENT"


def score_candidate(
    candidate: PatternCandidate,
    feature: Mapping[str, object],
    context: DetectionContext,
    configuration: PatternEngineConfiguration,
    *,
    close_price: object | None = None,
    history_sessions: int | None = None,
) -> CandidateScoreResult:
    """Rank a detector result while preserving every geometry field and measurement."""

    context_inputs = _context_inputs(
        feature, context, configuration, close_price=close_price,
        history_sessions=history_sessions,
    )
    context_weights = configuration.section("context_weights")
    context_score = weighted_score(context_inputs, context_weights)
    setup_inputs = {
        "pattern_quality": candidate.quality_score,
        "pattern_maturity": candidate.maturity_score,
        "trend": context_inputs["trend"],
        "relative_strength": context_inputs["relative_strength"],
        "sector": context_inputs["sector_strength"],
        "volume": context_inputs["volume"],
    }
    setup_score = weighted_score(setup_inputs, configuration.section("setup_weights"))
    scored = replace(
        candidate,
        quality_score=_optional_bounded(candidate.quality_score),
        maturity_score=_optional_bounded(candidate.maturity_score),
        context_score=context_score.total,
        setup_score=setup_score.total,
    )
    return CandidateScoreResult(scored, context_score, setup_score, maturity_band(scored.maturity_score))


def _context_inputs(feature, context, configuration, *, close_price, history_sessions):
    benchmark = context.benchmark_snapshot
    sector = context.sector_snapshot or {}
    price = _optional_decimal(close_price)
    if price is None:
        price = _value(feature, "close_price")
    median_value = _value(feature, "median_traded_value_20")
    median_volume = _value(feature, "median_volume_20")
    liquidity_rules = configuration.section("liquidity")
    liquidity_conditions = (
        price is not None and price >= _decimal(liquidity_rules["minimum_close_price"]),
        history_sessions is not None and history_sessions >= int(liquidity_rules["minimum_history_sessions"]),
        median_value is not None and median_value >= _decimal(liquidity_rules["median_traded_value_20"]),
        median_volume is not None and median_volume >= _decimal(liquidity_rules["median_volume_20"]),
    )
    return {
        "market_regime": _snapshot_score(benchmark, "market_regime_score", "score"),
        "sector_strength": _snapshot_score(sector, "sector_strength_score", "score"),
        "trend": _trend_score(feature, price),
        "relative_strength": _value(feature, "relative_strength_percentile"),
        "volume": _ratio_score(_value(feature, "volume_ratio_20"), _D("1.2")),
        "liquidity": _D(sum(liquidity_conditions)) / len(liquidity_conditions) * 100,
    }


def _snapshot_score(snapshot, *keys):
    for key in keys:
        value = snapshot.get(key)
        if value is not None:
            return _clamp(_decimal(value))
    return _D("0")


def _trend_score(feature, close):
    ema20, sma50, sma200 = (_value(feature, key) for key in ("ema_20", "sma_50", "sma_200"))
    conditions = (
        close is not None and ema20 is not None and close > ema20,
        ema20 is not None and sma50 is not None and ema20 > sma50,
        sma50 is not None and sma200 is not None and sma50 > sma200,
        (_value(feature, "ema_20_slope") or _D("0")) > 0,
        (_value(feature, "sma_50_slope") or _D("0")) > 0,
    )
    return _D(sum(conditions)) / len(conditions) * 100


def _ratio_score(value, target):
    return _D("0") if value is None else _clamp(value / target * 100)
def _value(row, key):
    return None if row.get(key) is None else _decimal(row[key])
def _optional_decimal(value):
    return None if value is None else _decimal(value)
def _optional_bounded(value):
    return None if value is None else _clamp(_decimal(value))
def _decimal(value):
    return value if isinstance(value, Decimal) else _D(str(value))
def _clamp(value):
    return max(_D("0"), min(_D("100"), value))
