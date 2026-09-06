"""Immutable value objects passed between pattern-engine stages."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, TypeAlias
from uuid import UUID

from pattern_engine.enums import PatternClass, PatternEventType, PatternState, SwingType, ZoneType


ScalarValue: TypeAlias = str | int | float | bool | None
SerializableValue: TypeAlias = (
    ScalarValue
    | Decimal
    | date
    | datetime
    | Enum
    | UUID
    | tuple["SerializableValue", ...]
    | Mapping[str, "SerializableValue"]
)


def serialize_value(value: SerializableValue | object) -> object:
    """Convert a domain value to JSON-compatible primitives without mutation."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serialize_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: serialize_value(getattr(value, field.name)) for field in fields(value)}
    return value


def _freeze_value(value: SerializableValue | object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class DailyBar:
    isin: str
    symbol: str
    trading_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    data_version: str
    delivery_quantity: int | None = None
    delivery_percentage: Decimal | None = None

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class CorporateAction:
    source_key: str
    isin: str
    action_type: str
    ex_date: date
    record_date: date | None
    ratio: Decimal | None
    value: Decimal | None
    source_announcement_date: date | None
    raw_source_attributes: Mapping[str, SerializableValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw_source_attributes", _freeze_value(self.raw_source_attributes))

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class TechnicalFeatureSnapshot:
    isin: str
    as_of_date: date
    data_version: str
    true_range: Decimal | None = None
    atr_5: Decimal | None = None
    atr_10: Decimal | None = None
    atr_14: Decimal | None = None
    atr_20: Decimal | None = None
    atr_50: Decimal | None = None
    natr_14: Decimal | None = None
    ema_10: Decimal | None = None
    ema_20: Decimal | None = None
    ema_50: Decimal | None = None
    sma_50: Decimal | None = None
    sma_100: Decimal | None = None
    sma_150: Decimal | None = None
    sma_200: Decimal | None = None
    ema_20_slope: Decimal | None = None
    ema_50_slope: Decimal | None = None
    sma_50_slope: Decimal | None = None
    sma_200_slope: Decimal | None = None
    range_5: Decimal | None = None
    range_10: Decimal | None = None
    range_20: Decimal | None = None
    range_50: Decimal | None = None
    high_52_week: Decimal | None = None
    low_52_week: Decimal | None = None
    range_position_52_week: Decimal | None = None
    distance_to_52_week_high_pct: Decimal | None = None
    all_time_high: Decimal | None = None
    distance_to_all_time_high_pct: Decimal | None = None
    average_volume_5: Decimal | None = None
    average_volume_20: Decimal | None = None
    average_volume_50: Decimal | None = None
    median_volume_5: Decimal | None = None
    median_volume_10: Decimal | None = None
    median_volume_20: Decimal | None = None
    median_volume_50: Decimal | None = None
    volume_ratio_5_to_50: Decimal | None = None
    volume_contraction_ratio: Decimal | None = None
    median_traded_value_20: Decimal | None = None
    close_location_value: Decimal | None = None
    return_1_month: Decimal | None = None
    return_3_month: Decimal | None = None
    return_6_month: Decimal | None = None
    return_12_month: Decimal | None = None
    relative_strength_1m: Decimal | None = None
    relative_strength_3m: Decimal | None = None
    relative_strength_6m: Decimal | None = None
    relative_strength_12m: Decimal | None = None
    relative_strength_percentile: Decimal | None = None
    relative_strength_composite: Decimal | None = None
    delivery_percentage: Decimal | None = None
    median_delivery_percentage_5: Decimal | None = None
    median_delivery_percentage_20: Decimal | None = None
    delivery_expansion_ratio: Decimal | None = None
    volume_ratio_20: Decimal | None = None
    distance_to_ema_20_pct: Decimal | None = None
    distance_to_sma_50_pct: Decimal | None = None
    distance_to_sma_200_pct: Decimal | None = None
    deliverable_volume: Decimal | None = None

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class SwingPoint:
    swing_id: str | None
    isin: str
    pivot_date: date
    confirmation_date: date
    swing_type: SwingType
    price: Decimal
    natr: Decimal | None
    move_size_pct: Decimal | None
    is_meaningful: bool

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PriceZone:
    zone_id: str | None
    isin: str
    zone_type: ZoneType
    start_date: date
    end_date: date
    median_price: Decimal
    tolerance_pct: Decimal
    dispersion_pct: Decimal
    source_swing_ids: tuple[str, ...]
    test_count: int
    breakout_buffer_pct: Decimal = Decimal("0")
    last_test_date: date | None = None
    confirmation_date: date | None = None

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class DetectionContext:
    as_of_date: date
    benchmark_snapshot: Mapping[str, SerializableValue]
    sector_snapshot: Mapping[str, SerializableValue] | None
    supporting_pattern_identifiers: tuple[str, ...]
    configuration_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_snapshot", _freeze_value(self.benchmark_snapshot))
        if self.sector_snapshot is not None:
            object.__setattr__(self, "sector_snapshot", _freeze_value(self.sector_snapshot))

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PatternCandidate:
    isin: str
    pattern_class: PatternClass
    pattern_type: str
    variant: str | None
    start_date: date
    end_date: date
    detected_date: date
    state: PatternState
    quality_score: Decimal | None
    maturity_score: Decimal | None
    context_score: Decimal | None
    setup_score: Decimal | None
    pivot_price: Decimal | None
    support_price: Decimal | None
    invalidation_price: Decimal | None
    measurements: Mapping[str, SerializableValue]
    supporting_pattern_identifiers: tuple[str, ...]
    invalidation_rule: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "measurements", _freeze_value(self.measurements))

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PatternInstance:
    pattern_instance_id: str
    isin: str
    pattern_class: PatternClass
    pattern_type: str
    variant: str | None
    start_date: date
    detected_date: date
    last_updated_date: date
    state: PatternState
    quality_score: Decimal | None
    maturity_score: Decimal | None
    context_score: Decimal | None
    setup_score: Decimal | None
    pivot_price: Decimal | None
    support_price: Decimal | None
    invalidation_price: Decimal | None
    configuration_version: str
    engine_version: str
    data_version: str
    end_date: date | None = None
    trigger_date: date | None = None
    confirmation_date: date | None = None
    terminal_date: date | None = None
    state_version: int = 1
    source_pattern_id: str | None = None
    measurements: Mapping[str, SerializableValue] = field(default_factory=dict)
    supporting_pattern_identifiers: tuple[str, ...] = ()
    adjustment_version: str = ""
    feature_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "measurements", _freeze_value(self.measurements))

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class PatternEvent:
    event_id: str
    pattern_instance_id: str
    event_type: PatternEventType
    state_version: int
    previous_state: PatternState | None
    new_state: PatternState
    previous_values: Mapping[str, SerializableValue]
    new_values: Mapping[str, SerializableValue]
    effective_date: date
    recorded_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "previous_values", _freeze_value(self.previous_values))
        object.__setattr__(self, "new_values", _freeze_value(self.new_values))

    def to_dict(self) -> dict[str, object]:
        return serialize_value(self)  # type: ignore[return-value]
