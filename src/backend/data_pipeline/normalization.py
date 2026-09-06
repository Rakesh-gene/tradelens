"""NSE response parsers and source-to-repository normalization helpers."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
import csv
import io
import zipfile
from typing import Any, Mapping, Sequence

from data_pipeline.models import (
    NseCorporateActionRecord,
    NseEquityHistoryRecord,
    NseIndexHistoryRecord,
    freeze_json_value,
)


class NseDataValidationError(ValueError):
    """A response field cannot be safely normalized into market data."""

    def __init__(self, symbol: str, field: str, reason: str, trading_date: object = None) -> None:
        location = f" for symbol {symbol}" if symbol else ""
        when = f" on {trading_date}" if trading_date else ""
        super().__init__(f"NSE validation failed{location}{when}: {field} {reason}")
        self.symbol = symbol
        self.field = field
        self.trading_date = trading_date


DATE_FORMATS = (
    "%d-%b-%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d %b %Y",
)
NULL_VALUES = frozenset({"", "-", "na", "n/a", "null", "none", "nan"})
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
RATIO_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*[:/]\s*(\d+(?:\.\d+)?)")
CASH_PATTERN = re.compile(r"(?:rs\.?|inr|₹)\s*(\d+(?:,\d{3})*(?:\.\d+)?)", re.IGNORECASE)


def parse_equity_history_response(
    payload: object, expected_symbol: str
) -> list[NseEquityHistoryRecord]:
    """Parse one NSE historical-response payload into validated equity DTOs."""

    records: list[NseEquityHistoryRecord] = []
    for raw_record in _extract_records(payload, expected_symbol):
        fields = _normalized_fields(raw_record)
        symbol = _required_text(fields, ("ch_symbol", "symbol"), expected_symbol, "symbol")
        trading_date = _required_date(
            fields, ("ch_timestamp", "mtimestamp", "timestamp", "trading_date", "date"), symbol
        )
        open_price = _required_positive_decimal(fields, ("ch_opening_price", "open", "open_price"), symbol, trading_date)
        high_price = _required_positive_decimal(fields, ("ch_trade_high_price", "high", "high_price"), symbol, trading_date)
        low_price = _required_positive_decimal(fields, ("ch_trade_low_price", "low", "low_price"), symbol, trading_date)
        close_price = _required_positive_decimal(fields, ("ch_closing_price", "close", "close_price"), symbol, trading_date)
        _validate_ohlc(symbol, trading_date, open_price, high_price, low_price, close_price)
        volume = _required_non_negative_int(
            fields,
            ("ch_tot_traded_qty", "total_traded_volume", "volume", "tottrdqty"),
            symbol,
            trading_date,
        )
        delivery_quantity = _optional_non_negative_int(
            fields,
            ("cop_deliv_qty", "deliverable_quantity", "delivery_quantity"),
            symbol,
            trading_date,
        )
        delivery_percentage = _optional_decimal(
            fields,
            ("cop_deliv_per", "delivery_percentage", "delivery_percent"),
            symbol,
            trading_date,
        )
        if delivery_percentage is not None and not Decimal("0") <= delivery_percentage <= Decimal("100"):
            raise NseDataValidationError(symbol, "delivery_percentage", "must be between 0 and 100", trading_date)

        records.append(
            NseEquityHistoryRecord(
                symbol=symbol,
                source_isin=_optional_text(fields, ("ch_isin", "isin")),
                series=_normalize_series(_optional_text(fields, ("ch_series", "series")) or "EQ"),
                trading_date=trading_date,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                deliverable_quantity=delivery_quantity,
                delivery_percentage=delivery_percentage,
                source_checksum=_checksum(raw_record),
                source_payload=freeze_json_value(raw_record),
            )
        )
    return records


def parse_corporate_actions_response(
    payload: object, expected_symbol: str
) -> list[NseCorporateActionRecord]:
    """Parse NSE corporate actions, retaining raw payload and a stable event key."""

    records: list[NseCorporateActionRecord] = []
    expected = _normalize_symbol(expected_symbol)
    for raw_record in _extract_records(payload, expected):
        fields = _normalized_fields(raw_record)
        symbol = _required_text(fields, ("symbol", "ch_symbol"), expected, "symbol")
        if symbol != expected:
            continue
        ex_date = _required_date(fields, ("exdate", "ex_date"), symbol)
        raw_description = _required_text(fields, ("subject", "purpose", "description"), symbol, "subject")
        action_type = _classify_action_type(raw_description)
        numerator, denominator = _parse_ratio(raw_description)
        cash_value = _parse_cash_value(raw_description) if action_type == "DIVIDEND" else None
        source_checksum = _checksum(raw_record)
        source_event_key = _corporate_action_key(symbol, ex_date, action_type, raw_description)
        records.append(
            NseCorporateActionRecord(
                source_event_key=source_event_key,
                symbol=symbol,
                source_isin=_optional_text(fields, ("isin", "ch_isin")),
                action_type=action_type,
                ex_date=ex_date,
                record_date=_optional_date(fields, ("recdate", "recorddate", "record_date"), symbol),
                announcement_date=_optional_date(
                    fields, ("bcstartdate", "announcementdate", "announcement_date"), symbol
                ),
                numerator=numerator,
                denominator=denominator,
                cash_value=cash_value,
                currency="INR" if cash_value is not None else None,
                raw_description=raw_description,
                source_checksum=source_checksum,
                source_payload=freeze_json_value(raw_record),
            )
        )
    return records


def parse_index_history_response(payload: object, index_name: str) -> list[NseIndexHistoryRecord]:
    """Parse a historical index response into the common validated shape."""

    normalized_index = " ".join(index_name.strip().upper().split())
    records: list[NseIndexHistoryRecord] = []
    for raw_record in _extract_records(payload, normalized_index):
        fields = _normalized_fields(raw_record)
        trading_date = _required_date(fields, ("timestamp", "date", "historicaldate", "ch_timestamp"), normalized_index)
        open_price = _required_positive_decimal(fields, ("open", "open_price", "ch_opening_price"), normalized_index, trading_date)
        high_price = _required_positive_decimal(fields, ("high", "high_price", "ch_trade_high_price"), normalized_index, trading_date)
        low_price = _required_positive_decimal(fields, ("low", "low_price", "ch_trade_low_price"), normalized_index, trading_date)
        close_price = _required_positive_decimal(fields, ("close", "close_price", "ch_closing_price"), normalized_index, trading_date)
        _validate_ohlc(normalized_index, trading_date, open_price, high_price, low_price, close_price)
        records.append(
            NseIndexHistoryRecord(
                index_name=normalized_index,
                trading_date=trading_date,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=_optional_non_negative_int(fields, ("volume", "total_traded_volume"), normalized_index, trading_date),
                source_checksum=_checksum(raw_record),
                source_payload=freeze_json_value(raw_record),
            )
        )
    return records


def parse_eod_report(
    payload: bytes, securities: Mapping[str, Mapping[str, object]]
) -> dict[str, NseEquityHistoryRecord]:
    """Parse a NSE EOD CSV/ZIP into bars keyed by stable ISIN.

    NSE has published both plain CSV and ZIP-wrapped BhavCopy files over time;
    the parser accepts either and never treats an HTML error page as data.
    """

    if not payload or payload.lstrip().lower().startswith((b"<html", b"<!doctype html")):
        raise NseDataValidationError("", "eod_report", "is empty or an HTML error page")
    csv_bytes = payload
    if payload[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not names:
                    raise ValueError("ZIP contains no CSV")
                csv_bytes = archive.read(names[0])
        except (zipfile.BadZipFile, KeyError, ValueError) as error:
            raise NseDataValidationError("", "eod_report", "contains an invalid ZIP/CSV payload") from error
    try:
        reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as error:
        raise NseDataValidationError("", "eod_report", "is not valid UTF-8 CSV") from error
    result: dict[str, NseEquityHistoryRecord] = {}
    for row in rows:
        fields = _normalized_fields(row)
        isin = (_optional_text(fields, ("isin", "ch_isin", "isin number")) or "").upper()
        if isin not in securities:
            continue
        symbol = str(securities[isin].get("symbol") or isin)
        normalized = dict(row)
        normalized.update({
            "CH_SYMBOL": symbol,
            "CH_ISIN": isin,
            "CH_SERIES": _optional_text(fields, ("series", "ch_series")) or "EQ",
            "CH_TIMESTAMP": _optional_text(fields, ("traddt", "trad_dt", "ch_timestamp", "date")),
            "CH_OPENING_PRICE": _optional_text(fields, ("opnpric", "open", "opening_price")),
            "CH_TRADE_HIGH_PRICE": _optional_text(fields, ("hghpric", "high", "trade_high_price")),
            "CH_TRADE_LOW_PRICE": _optional_text(fields, ("lwpric", "low", "trade_low_price")),
            "CH_CLOSING_PRICE": _optional_text(fields, ("clspric", "close", "closing_price")),
            "CH_TOT_TRADED_QTY": _optional_text(fields, ("ttltrdqty", "tottrdqty", "volume", "total_traded_volume")),
        })
        try:
            parsed = parse_equity_history_response({"data": [normalized]}, symbol)
        except NseDataValidationError:
            # Missing/rejected rows are intentionally left out so the daily
            # importer can fall back to per-security history for that ISIN.
            continue
        if parsed:
            result[isin] = parsed[0]
    return result


def raw_bar_record(
    record: NseEquityHistoryRecord,
    isin: str,
    import_run_id: str | None = None,
    *,
    expected_symbol: str | None = None,
) -> dict[str, object]:
    """Map a validated DTO to Phase 1's repository record without NSE field names."""

    normalized_isin = isin.strip().upper()
    if not normalized_isin:
        raise NseDataValidationError(record.symbol, "isin", "is required")
    source_isin = _validate_source_security_identity(
        record.symbol, record.source_isin, normalized_isin, expected_symbol, record.trading_date
    )
    return {
        "isin": normalized_isin,
        "source_isin": source_isin,
        "trading_date": record.trading_date,
        "open_price": record.open_price,
        "high_price": record.high_price,
        "low_price": record.low_price,
        "close_price": record.close_price,
        "volume": record.volume,
        "deliverable_quantity": record.deliverable_quantity,
        "delivery_percentage": record.delivery_percentage,
        "nse_series": record.series,
        "source_name": "NSE",
        "source_checksum": record.source_checksum,
        "source_published_at": None,
        "import_run_id": import_run_id,
    }


def corporate_action_record(
    record: NseCorporateActionRecord,
    isin: str,
    import_run_id: str | None = None,
    *,
    expected_symbol: str | None = None,
) -> dict[str, object]:
    """Map a validated corporate-action DTO to Phase 1 repository values."""

    normalized_isin = isin.strip().upper()
    if not normalized_isin:
        raise NseDataValidationError(record.symbol, "isin", "is required")
    source_isin = _validate_source_security_identity(
        record.symbol, record.source_isin, normalized_isin, expected_symbol, record.ex_date
    )
    return {
        "source_event_key": record.source_event_key,
        "isin": normalized_isin,
        "source_isin": source_isin,
        "symbol": record.symbol,
        "action_type": record.action_type,
        "ex_date": record.ex_date,
        "record_date": record.record_date,
        "announcement_date": record.announcement_date,
        "numerator": record.numerator,
        "denominator": record.denominator,
        "cash_value": record.cash_value,
        "currency": record.currency,
        "raw_description": record.raw_description,
        "raw_payload": record.source_payload,
        "source_checksum": record.source_checksum,
        "import_run_id": import_run_id,
    }


def _validate_source_security_identity(
    source_symbol: str,
    source_isin: str | None,
    stable_isin: str,
    expected_symbol: str | None,
    effective_date: date,
) -> str | None:
    """Allow a historical ISIN version only for the same symbol and issuer."""

    if not source_isin:
        return None
    normalized_source_isin = source_isin.strip().upper()
    if normalized_source_isin == stable_isin:
        return normalized_source_isin

    same_symbol = bool(expected_symbol) and (
        _normalize_symbol(source_symbol) == _normalize_symbol(expected_symbol or "")
    )
    # The first seven ISIN characters identify the Indian issuer. A corporate
    # action can change the security code and checksum without changing issuer.
    same_issuer = (
        bool(ISIN_PATTERN.fullmatch(normalized_source_isin))
        and bool(ISIN_PATTERN.fullmatch(stable_isin))
        and normalized_source_isin[:7] == stable_isin[:7]
    )
    if same_symbol and same_issuer:
        return normalized_source_isin
    raise NseDataValidationError(
        source_symbol,
        "isin",
        "does not match the stable security ISIN or a validated historical version",
        effective_date,
    )


def _extract_records(payload: object, symbol: str) -> Sequence[Mapping[str, object]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, Mapping):
        records = payload.get("data", payload.get("records", []))
    else:
        raise NseDataValidationError(symbol, "response", "must be an object or list")
    if records is None:
        return ()
    if not isinstance(records, list):
        raise NseDataValidationError(symbol, "response.data", "must be a list")
    if not all(isinstance(record, Mapping) for record in records):
        raise NseDataValidationError(symbol, "response.data", "must contain objects")
    return records


def _normalized_fields(record: Mapping[str, object]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for key, value in record.items():
        normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key).strip())
        normalized = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
        fields[normalized] = value
        fields.setdefault(normalized.replace("_", ""), value)
    return fields


def _required_text(
    fields: Mapping[str, object], aliases: Sequence[str], symbol: str, field_name: str
) -> str:
    value = _optional_text(fields, aliases)
    if not value:
        raise NseDataValidationError(symbol, field_name, "is required")
    return _normalize_symbol(value) if field_name == "symbol" else value.strip()


def _optional_text(fields: Mapping[str, object], aliases: Sequence[str]) -> str | None:
    for alias in aliases:
        value = fields.get(alias)
        if value is None:
            continue
        text = str(value).strip()
        if text.lower() not in NULL_VALUES:
            return text
    return None


def _required_date(fields: Mapping[str, object], aliases: Sequence[str], symbol: str) -> date:
    value = _optional_text(fields, aliases)
    if value is None:
        raise NseDataValidationError(symbol, aliases[0], "is required")
    return _parse_date(value, symbol, aliases[0])


def _optional_date(fields: Mapping[str, object], aliases: Sequence[str], symbol: str) -> date | None:
    value = _optional_text(fields, aliases)
    return _parse_date(value, symbol, aliases[0]) if value is not None else None


def _parse_date(value: str, symbol: str, field: str) -> date:
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), date_format).date()
        except ValueError:
            continue
    raise NseDataValidationError(symbol, field, f"has unsupported date {value!r}")


def _required_positive_decimal(
    fields: Mapping[str, object], aliases: Sequence[str], symbol: str, trading_date: date
) -> Decimal:
    value = _optional_decimal(fields, aliases, symbol, trading_date)
    if value is None:
        raise NseDataValidationError(symbol, aliases[0], "is required", trading_date)
    if value <= 0:
        raise NseDataValidationError(symbol, aliases[0], "must be positive", trading_date)
    return value


def _optional_decimal(
    fields: Mapping[str, object], aliases: Sequence[str], symbol: str, trading_date: date
) -> Decimal | None:
    for alias in aliases:
        value = fields.get(alias)
        if value is None or str(value).strip().lower() in NULL_VALUES:
            continue
        try:
            return Decimal(str(value).replace(",", "").replace("%", "").strip())
        except InvalidOperation as exc:
            raise NseDataValidationError(symbol, alias, f"has invalid decimal {value!r}", trading_date) from exc
    return None


def _required_non_negative_int(
    fields: Mapping[str, object], aliases: Sequence[str], symbol: str, trading_date: date
) -> int:
    value = _optional_non_negative_int(fields, aliases, symbol, trading_date)
    if value is None:
        raise NseDataValidationError(symbol, aliases[0], "is required", trading_date)
    return value


def _optional_non_negative_int(
    fields: Mapping[str, object], aliases: Sequence[str], symbol: str, trading_date: date
) -> int | None:
    decimal_value = _optional_decimal(fields, aliases, symbol, trading_date)
    if decimal_value is None:
        return None
    if decimal_value < 0 or decimal_value != decimal_value.to_integral_value():
        raise NseDataValidationError(symbol, aliases[0], "must be a non-negative integer", trading_date)
    return int(decimal_value)


def _validate_ohlc(
    symbol: str, trading_date: date, open_price: Decimal, high_price: Decimal,
    low_price: Decimal, close_price: Decimal,
) -> None:
    if high_price < low_price:
        raise NseDataValidationError(symbol, "high_price", "cannot be below low_price", trading_date)
    tolerance = max(Decimal("0.01"), high_price * Decimal("0.001"))
    for field, value in (("open_price", open_price), ("close_price", close_price)):
        if value < low_price - tolerance or value > high_price + tolerance:
            raise NseDataValidationError(
                symbol, field, "falls materially outside the high/low range", trading_date
            )


def _normalize_symbol(value: str) -> str:
    return " ".join(value.strip().upper().split())


def _normalize_series(value: str) -> str:
    return " ".join(value.strip().upper().split())


def _checksum(record: Mapping[str, object]) -> str:
    encoded = json.dumps(record, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _classify_action_type(description: str) -> str:
    text = description.upper()
    for keyword, action_type in (
        ("DIVIDEND", "DIVIDEND"),
        ("BONUS", "BONUS"),
        ("SPLIT", "SPLIT"),
        ("RIGHT", "RIGHTS"),
        ("CONSOLIDAT", "CONSOLIDATION"),
        ("BUYBACK", "BUYBACK"),
    ):
        if keyword in text:
            return action_type
    return "OTHER"


def _parse_ratio(description: str) -> tuple[Decimal | None, Decimal | None]:
    match = RATIO_PATTERN.search(description)
    if match is None:
        return None, None
    return Decimal(match.group(1)), Decimal(match.group(2))


def _parse_cash_value(description: str) -> Decimal | None:
    match = CASH_PATTERN.search(description)
    return Decimal(match.group(1).replace(",", "")) if match is not None else None


def _corporate_action_key(symbol: str, ex_date: date, action_type: str, description: str) -> str:
    """Return a stable natural event key; payload revisions only update its checksum."""

    material = f"{symbol}|{ex_date.isoformat()}|{action_type}|{description.strip()}"
    return f"NSE:{sha256(material.encode('utf-8')).hexdigest()}"
