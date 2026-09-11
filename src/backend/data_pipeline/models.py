"""Validated DTOs returned by exchange-specific data clients."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, TypeAlias


JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]


def freeze_json_value(value: object) -> JsonValue:
    """Recursively freeze source payloads retained for auditability."""

    if isinstance(value, Mapping):
        return MappingProxyType({str(key): freeze_json_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item) for item in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass(frozen=True, slots=True)
class NseEquityHistoryRecord:
    """One validated NSE daily equity bar; it has not been persisted."""

    symbol: str
    source_isin: str | None
    series: str
    trading_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    deliverable_quantity: int | None
    delivery_percentage: Decimal | None
    source_checksum: str
    source_payload: Mapping[str, JsonValue]
    previous_close_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NseCorporateActionRecord:
    """One normalized NSE corporate-action announcement without persistence."""

    source_event_key: str
    symbol: str
    source_isin: str | None
    action_type: str
    ex_date: date
    record_date: date | None
    announcement_date: date | None
    numerator: Decimal | None
    denominator: Decimal | None
    cash_value: Decimal | None
    currency: str | None
    raw_description: str
    source_checksum: str
    source_payload: Mapping[str, JsonValue]
    face_value: Decimal | None = None
    issue_price: Decimal | None = None
    old_face_value: Decimal | None = None
    new_face_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class NseIndexHistoryRecord:
    """One validated NSE index daily bar without persistence."""

    index_name: str
    trading_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int | None
    source_checksum: str
    source_payload: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class NseEquityClassification:
    """Validated NSE four-level industry classification for one equity."""

    symbol: str
    isin: str
    macro_sector: str
    sector: str
    industry: str
    basic_industry: str
    source_checksum: str
    source_payload: Mapping[str, JsonValue]
