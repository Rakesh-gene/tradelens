"""Pattern instance matching, lifecycle validation, eventing, and expiry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Protocol

from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import PatternClass, PatternEventType, PatternState
from pattern_engine.models import PatternCandidate, serialize_value


_D = Decimal
_TERMINAL = frozenset({PatternState.FAILED, PatternState.INVALIDATED, PatternState.EXPIRED})
_RANK = {
    PatternState.DETECTED: 0, PatternState.FORMING: 1, PatternState.MATURE: 2,
    PatternState.READY: 3, PatternState.TRIGGERED: 4, PatternState.CONFIRMED: 5,
}


class PatternLifecycleRepository(Protocol):
    def load_active_patterns(self, isin: str, pattern_type: str | None = None) -> list[dict[str, object]]: ...
    def create_pattern(self, values: Mapping[str, object], event: Mapping[str, object]) -> dict[str, object]: ...
    def update_pattern(
        self, pattern_id: str, expected_state_version: int,
        values: Mapping[str, object], event: Mapping[str, object] | None,
    ) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    action: str
    instance: Mapping[str, object]
    event_type: PatternEventType | None


class PatternLifecycleService:
    def __init__(
        self, repository: PatternLifecycleRepository,
        configuration: PatternEngineConfiguration,
        *, pivot_tolerance_pct: Decimal = Decimal("2"),
    ) -> None:
        self._repository = repository
        self._configuration = configuration
        self._pivot_tolerance_pct = pivot_tolerance_pct

    def apply_candidate(
        self,
        candidate: PatternCandidate,
        *,
        engine_version: str,
        feature_version: str,
        adjustment_version: str,
    ) -> LifecycleResult:
        self._validate_detector_state(candidate)
        active = self._repository.load_active_patterns(candidate.isin, candidate.pattern_type)
        match = self._match(candidate, active)
        if match is None:
            values = self._new_values(
                candidate, engine_version, feature_version, adjustment_version
            )
            event = self._event(
                PatternEventType.PATTERN_DETECTED, None, candidate.state, 1,
                {}, values, candidate.detected_date,
            )
            instance = self._repository.create_pattern(values, event)
            return LifecycleResult("created", instance, PatternEventType.PATTERN_DETECTED)
        current_state = PatternState(str(_field(match, "state")))
        candidate = self._retain_forward_state(current_state, candidate)
        self._validate_transition(current_state, candidate.state)
        values = self._update_values(candidate, match)
        event_type = self._meaningful_event(match, values, candidate.state)
        event = None
        if event_type is not None:
            event = self._event(
                event_type, current_state, candidate.state,
                int(_field(match, "state_version") or 1) + 1,
                self._event_values(match), self._event_values(values),
                candidate.detected_date,
            )
        instance = self._repository.update_pattern(
            str(_field(match, "id")),
            int(_field(match, "state_version") or 1),
            values,
            event,
        )
        return LifecycleResult("updated", instance, event_type)

    def invalidate_adjustment_mismatches(
        self, isin: str, adjustment_version: str, as_of_date: date
    ) -> list[LifecycleResult]:
        """Close active instances whose price levels belong to another scale."""

        results = []
        for instance in self._repository.load_active_patterns(isin):
            previous_version = str(_field(instance, "adjustment_version") or "")
            if previous_version == adjustment_version:
                continue
            state = PatternState(str(_field(instance, "state")))
            measurements = dict(_field(instance, "measurements") or {})
            measurements["invalidation_reason"] = "ADJUSTMENT_VERSION_CHANGED"
            measurements["replacement_adjustment_version"] = adjustment_version
            values = {
                **dict(instance),
                "state": PatternState.INVALIDATED.value,
                "terminal_date": as_of_date,
                "last_updated_date": as_of_date,
                "measurements": measurements,
            }
            previous_values = {
                **self._event_values(instance),
                "adjustment_version": previous_version,
            }
            new_values = {
                **self._event_values(values),
                "adjustment_version": previous_version,
                "replacement_adjustment_version": adjustment_version,
                "invalidation_reason": "ADJUSTMENT_VERSION_CHANGED",
            }
            event = self._event(
                PatternEventType.INVALIDATED, state, PatternState.INVALIDATED,
                int(_field(instance, "state_version") or 1) + 1,
                previous_values, new_values, as_of_date,
            )
            updated = self._repository.update_pattern(
                str(_field(instance, "id")),
                int(_field(instance, "state_version") or 1),
                values,
                event,
            )
            results.append(LifecycleResult(
                "invalidated", updated, PatternEventType.INVALIDATED
            ))
        return results

    def invalidate_lineage_mismatches(
        self,
        isin: str,
        as_of_date: date,
        *,
        engine_version: str,
        feature_version: str,
        adjustment_version: str,
    ) -> list[LifecycleResult]:
        """Close active instances calculated from superseded engine inputs."""

        expected = (
            ("adjustment_version", adjustment_version, "ADJUSTMENT_VERSION_CHANGED"),
            ("engine_version", engine_version, "ENGINE_VERSION_CHANGED"),
            ("configuration_version", self._configuration.version, "CONFIGURATION_VERSION_CHANGED"),
            ("feature_version", feature_version, "FEATURE_VERSION_CHANGED"),
        )
        results = []
        for instance in self._repository.load_active_patterns(isin):
            mismatch = next(
                (
                    (field, replacement, reason)
                    for field, replacement, reason in expected
                    if str(_field(instance, field) or "") != replacement
                ),
                None,
            )
            if mismatch is None:
                continue
            field, replacement, reason = mismatch
            results.append(self._terminalize(
                instance,
                PatternState.INVALIDATED,
                as_of_date,
                reason,
                replacement_field=f"replacement_{field}",
                replacement_value=replacement,
            ))
        return results

    def invalidate_active(
        self, isin: str, as_of_date: date, reason: str
    ) -> list[LifecycleResult]:
        """Quarantine live instances when their source price history is unsafe."""

        results = []
        for instance in self._repository.load_active_patterns(isin):
            state = PatternState(str(_field(instance, "state")))
            measurements = dict(_field(instance, "measurements") or {})
            measurements["invalidation_reason"] = reason
            values = {
                **dict(instance), "state": PatternState.INVALIDATED.value,
                "terminal_date": as_of_date, "last_updated_date": as_of_date,
                "measurements": measurements,
            }
            event = self._event(
                PatternEventType.INVALIDATED, state, PatternState.INVALIDATED,
                int(_field(instance, "state_version") or 1) + 1,
                self._event_values(instance),
                {**self._event_values(values), "invalidation_reason": reason},
                as_of_date,
            )
            updated = self._repository.update_pattern(
                str(_field(instance, "id")),
                int(_field(instance, "state_version") or 1), values, event,
            )
            results.append(LifecycleResult(
                "invalidated", updated, PatternEventType.INVALIDATED
            ))
        return results

    def reconcile_unobserved(
        self,
        isin: str,
        as_of_date: date,
        observed_pattern_ids: Sequence[str],
        scanned_timeframes: Sequence[str],
    ) -> list[LifecycleResult]:
        """Terminalize active structures absent from a completed detector pass.

        Confirmed and recently triggered breakouts have their own retention
        windows and are handled by ``expire_stale``. Other families must be
        observed again in the current scan to remain active.
        """

        observed = frozenset(str(value) for value in observed_pattern_ids)
        timeframes = frozenset(str(value) for value in scanned_timeframes)
        transient_classes = {
            PatternClass.TREND.value,
            PatternClass.COMPRESSION.value,
            PatternClass.MOMENTUM.value,
            PatternClass.FAILURE.value,
        }
        results = []
        for instance in self._repository.load_active_patterns(isin):
            instance_id = str(_field(instance, "id") or _field(instance, "pattern_instance_id") or "")
            if instance_id in observed:
                continue
            pattern_class = str(_field(instance, "pattern_class") or "")
            timeframe = str(_field(instance, "timeframe") or "1D")
            scanned = (
                timeframe in timeframes
                if pattern_class in {PatternClass.REVERSAL.value, PatternClass.HARMONIC.value}
                else timeframe == "1D"
            )
            if not scanned or pattern_class == PatternClass.BREAKOUT.value:
                continue
            terminal_state = (
                PatternState.EXPIRED
                if pattern_class in transient_classes
                else PatternState.INVALIDATED
            )
            reason = (
                "NOT_OBSERVED_IN_COMPLETED_SCAN"
                if terminal_state is PatternState.INVALIDATED
                else "CONDITION_NOT_PRESENT_IN_COMPLETED_SCAN"
            )
            results.append(self._terminalize(instance, terminal_state, as_of_date, reason))
        return results

    def expire_stale(
        self,
        isin: str,
        as_of_date: date,
        trading_dates: Sequence[date],
        *,
        observed_pattern_ids: Sequence[str] | None = None,
    ) -> list[LifecycleResult]:
        ordered_dates = sorted(day for day in trading_dates if day <= as_of_date)
        index = {day: position for position, day in enumerate(ordered_dates)}
        if as_of_date not in index:
            return []
        observed = (
            None
            if observed_pattern_ids is None
            else frozenset(str(value) for value in observed_pattern_ids)
        )
        results = []
        for instance in self._repository.load_active_patterns(isin):
            instance_id = str(_field(instance, "id") or _field(instance, "pattern_instance_id") or "")
            if observed is not None and instance_id in observed:
                continue
            if observed is None and _as_date(_field(instance, "last_updated_date")) >= as_of_date:
                continue
            maximum = self._maximum_duration(instance)
            start_value = (
                _field(instance, "trigger_date") or _field(instance, "start_date")
                if str(_field(instance, "pattern_class")) == PatternClass.BREAKOUT.value
                else _field(instance, "start_date")
            )
            start = _as_date(start_value)
            if maximum is None or start not in index or index[as_of_date] - index[start] <= maximum:
                continue
            state = PatternState(str(_field(instance, "state")))
            values = {
                **dict(instance), "state": PatternState.EXPIRED.value,
                "terminal_date": as_of_date, "last_updated_date": as_of_date,
            }
            event = self._event(
                PatternEventType.EXPIRED, state, PatternState.EXPIRED,
                int(_field(instance, "state_version") or 1) + 1,
                self._event_values(instance), self._event_values(values), as_of_date,
            )
            updated = self._repository.update_pattern(
                str(_field(instance, "id")),
                int(_field(instance, "state_version") or 1),
                values,
                event,
            )
            results.append(LifecycleResult("expired", updated, PatternEventType.EXPIRED))
        return results

    def _match(self, candidate, active):
        deduplication_key = _deduplication_key(candidate)
        exact = [
            instance for instance in active
            if _field(instance, "active_deduplication_key") == deduplication_key
        ]
        if exact:
            return max(
                exact,
                key=lambda row: _as_date(_field(row, "last_updated_date")),
            )
        matches = []
        for instance in active:
            if str(_field(instance, 'timeframe') or '1D') != candidate.timeframe:
                continue
            state = PatternState(str(_field(instance, "state")))
            if state in _TERMINAL:
                continue
            start = _as_date(_field(instance, "start_date"))
            end = _as_date(_field(instance, "last_updated_date"))
            overlaps = start <= candidate.end_date and candidate.start_date <= end
            existing_pivot = _optional_decimal(_field(instance, "pivot_price"))
            similar = (
                existing_pivot is None or candidate.pivot_price is None
                or abs(existing_pivot - candidate.pivot_price) / existing_pivot * 100 <= self._pivot_tolerance_pct
            )
            if overlaps and similar:
                matches.append(instance)
        return max(matches, key=lambda row: _as_date(_field(row, "last_updated_date")), default=None)

    @staticmethod
    def _retain_forward_state(previous, candidate):
        """Keep lifecycle progression monotonic while refreshing daily evidence."""
        new = candidate.state
        if previous not in _RANK or new not in _RANK or _RANK[new] >= _RANK[previous]:
            return candidate
        return replace(
            candidate,
            state=previous,
            measurements={
                **dict(candidate.measurements),
                "observed_state": new.value,
                "lifecycle_state_retained": previous.value,
            },
        )

    def _validate_detector_state(self, candidate):
        allowed = {
            PatternClass.FAILURE: {PatternState.DETECTED},
            PatternClass.BREAKOUT: {PatternState.TRIGGERED, PatternState.CONFIRMED, PatternState.FAILED},
            PatternClass.PULLBACK: {PatternState.FORMING, PatternState.READY, PatternState.TRIGGERED, PatternState.INVALIDATED},
            PatternClass.BASE: {
                PatternState.DETECTED, PatternState.FORMING, PatternState.MATURE,
                PatternState.READY, PatternState.TRIGGERED, PatternState.CONFIRMED,
                PatternState.INVALIDATED,
            },
            PatternClass.TREND: {PatternState.DETECTED},
            PatternClass.COMPRESSION: {PatternState.DETECTED},
            PatternClass.MOMENTUM: {PatternState.DETECTED},
            PatternClass.REVERSAL: {
                PatternState.DETECTED, PatternState.FORMING, PatternState.READY,
                PatternState.TRIGGERED, PatternState.CONFIRMED, PatternState.INVALIDATED,
            },
            PatternClass.HARMONIC: {
                PatternState.DETECTED, PatternState.FORMING, PatternState.READY,
                PatternState.TRIGGERED, PatternState.CONFIRMED, PatternState.INVALIDATED,
            },
        }
        states = allowed.get(candidate.pattern_class)
        if states is not None and candidate.state not in states:
            raise ValueError(f"{candidate.pattern_type} cannot emit state {candidate.state.value}")

    def _validate_transition(self, previous, new):
        if previous in _TERMINAL:
            raise ValueError(f"Terminal pattern state {previous.value} cannot transition")
        if new == previous or new in _TERMINAL:
            return
        if previous in _RANK and new in _RANK and _RANK[new] >= _RANK[previous]:
            return
        raise ValueError(f"Backward lifecycle transition {previous.value} -> {new.value}")

    def _new_values(self, candidate, engine_version, feature_version, adjustment_version):
        source_id = candidate.measurements.get("source_pattern_instance_id")
        terminal = candidate.detected_date if candidate.state in _TERMINAL else None
        trigger_date = _candidate_trigger_date(candidate)
        return {
            "isin": candidate.isin, "pattern_class": candidate.pattern_class.value,
            "pattern_type": candidate.pattern_type, "variant": candidate.variant,
            "start_date": candidate.start_date, "detected_date": candidate.detected_date,
            "trigger_date": trigger_date if candidate.state in {PatternState.TRIGGERED, PatternState.CONFIRMED} else None,
            "confirmation_date": candidate.detected_date if candidate.state is PatternState.CONFIRMED else None,
            "last_updated_date": candidate.detected_date, "terminal_date": terminal,
            "state": candidate.state.value, "state_version": 1,
            "quality_score": candidate.quality_score, "maturity_score": candidate.maturity_score,
            "context_score": candidate.context_score, "setup_score": candidate.setup_score,
            "pivot_price": candidate.pivot_price, "support_price": candidate.support_price,
            "invalidation_price": candidate.invalidation_price,
            "source_pattern_id": str(source_id) if source_id else None,
            "timeframe": candidate.timeframe,
            "pattern_group": candidate.pattern_group,
            "direction": candidate.direction,
            "interval_complete": candidate.interval_complete,
            "measurements": serialize_value(candidate.measurements),
            "supporting_patterns": serialize_value(candidate.supporting_pattern_identifiers),
            "configuration_version": self._configuration.version,
            "engine_version": engine_version, "feature_version": feature_version,
            "adjustment_version": adjustment_version,
            "active_deduplication_key": _deduplication_key(candidate),
        }

    def _update_values(self, candidate, match):
        values = {
            "variant": candidate.variant, "last_updated_date": candidate.detected_date,
            "state": candidate.state.value, "quality_score": candidate.quality_score,
            "maturity_score": candidate.maturity_score, "context_score": candidate.context_score,
            "setup_score": candidate.setup_score, "pivot_price": candidate.pivot_price,
            "support_price": candidate.support_price, "invalidation_price": candidate.invalidation_price,
            "measurements": serialize_value(candidate.measurements),
            "supporting_patterns": serialize_value(candidate.supporting_pattern_identifiers),
            "timeframe": candidate.timeframe,
            "pattern_group": candidate.pattern_group,
            "direction": candidate.direction,
            "interval_complete": candidate.interval_complete,
            "terminal_date": candidate.detected_date if candidate.state in _TERMINAL else None,
        }
        if candidate.state in {PatternState.TRIGGERED, PatternState.CONFIRMED} and not _field(match, "trigger_date"):
            values["trigger_date"] = _candidate_trigger_date(candidate)
        if candidate.state is PatternState.CONFIRMED and not _field(match, "confirmation_date"):
            values["confirmation_date"] = candidate.detected_date
        return values

    def _meaningful_event(self, previous, values, state):
        old_state = PatternState(str(_field(previous, "state")))
        if old_state != state:
            return {
                PatternState.TRIGGERED: PatternEventType.TRIGGERED,
                PatternState.CONFIRMED: PatternEventType.CONFIRMED,
                PatternState.FAILED: PatternEventType.FAILED,
                PatternState.INVALIDATED: PatternEventType.INVALIDATED,
                PatternState.EXPIRED: PatternEventType.EXPIRED,
            }.get(state, PatternEventType.STATE_CHANGED)
        if _changed(previous, values, "pivot_price"):
            return PatternEventType.PIVOT_UPDATED
        threshold = _D(str(self._configuration.section("engine")["score_event_minimum_delta"]))
        if any(_score_changed(previous, values, key, threshold) for key in ("quality_score", "context_score", "setup_score")):
            return PatternEventType.QUALITY_CHANGED
        if _score_changed(previous, values, "maturity_score", threshold):
            return PatternEventType.MATURITY_CHANGED
        return None

    def _event(self, event_type, previous_state, new_state, version, previous_values, new_values, effective_date):
        return {
            "event_type": event_type.value, "state_version": version,
            "previous_state": previous_state.value if previous_state else None,
            "new_state": new_state.value, "previous_values": previous_values,
            "new_values": new_values, "effective_date": effective_date,
        }

    def _terminalize(
        self,
        instance,
        terminal_state,
        as_of_date,
        reason,
        *,
        replacement_field=None,
        replacement_value=None,
    ):
        previous_state = PatternState(str(_field(instance, "state")))
        reason_field = (
            "expiration_reason"
            if terminal_state is PatternState.EXPIRED
            else "invalidation_reason"
        )
        measurements = {**dict(_field(instance, "measurements") or {}), reason_field: reason}
        if replacement_field is not None:
            measurements[replacement_field] = replacement_value
        values = {
            **dict(instance),
            "state": terminal_state.value,
            "terminal_date": as_of_date,
            "last_updated_date": as_of_date,
            "measurements": measurements,
        }
        event_type = (
            PatternEventType.EXPIRED
            if terminal_state is PatternState.EXPIRED
            else PatternEventType.INVALIDATED
        )
        new_event_values = {**self._event_values(values), reason_field: reason}
        if replacement_field is not None:
            new_event_values[replacement_field] = replacement_value
        event = self._event(
            event_type,
            previous_state,
            terminal_state,
            int(_field(instance, "state_version") or 1) + 1,
            self._event_values(instance),
            new_event_values,
            as_of_date,
        )
        updated = self._repository.update_pattern(
            str(_field(instance, "id")),
            int(_field(instance, "state_version") or 1),
            values,
            event,
        )
        return LifecycleResult(
            "expired" if terminal_state is PatternState.EXPIRED else "invalidated",
            updated,
            event_type,
        )

    def _event_values(self, values):
        keys = ("state", "variant", "pivot_price", "support_price", "invalidation_price", "quality_score", "maturity_score", "context_score", "setup_score", "terminal_date")
        return {key: serialize_value(_field(values, key)) for key in keys}

    def _maximum_duration(self, instance):
        pattern_type = str(_field(instance, "pattern_type"))
        if (
            str(_field(instance, "pattern_class")) == PatternClass.BREAKOUT.value
            and str(_field(instance, "state")) == PatternState.TRIGGERED.value
        ):
            return int(self._configuration.section("breakout")["failure_window_sessions"])
        if (
            str(_field(instance, "pattern_class")) == PatternClass.BREAKOUT.value
            and str(_field(instance, "state")) == PatternState.CONFIRMED.value
        ):
            return int(self._configuration.section("breakout_retest")["max_sessions_after_breakout"])
        if pattern_type == "PB-BRKRET":
            return int(self._configuration.section("breakout_retest")["max_sessions_after_breakout"])
        if pattern_type == "PB-EMA20":
            return int(self._configuration.section("ema20_pullback")["max_duration_sessions"])
        if pattern_type == "PB-SMA50":
            return int(self._configuration.section("sma50_pullback")["max_duration_sessions"])
        if pattern_type == "BASE-VCP":
            return int(self._configuration.section("vcp")["max_duration_sessions"])
        if pattern_type == "BASE-FLAT":
            return int(self._configuration.section("flat_base")["max_duration_sessions"])
        if pattern_type == "BASE-52WH":
            return int(self._configuration.section("base_52wh")["max_duration_sessions"])
        timeframe = str(_field(instance, 'timeframe') or '1D')
        multiplier = {'1D': 1, '1W': 5, '1M': 21}.get(timeframe, 1)
        if pattern_type.startswith('REV-'):
            return int(self._configuration.section('reversal')['maximum_pattern_bars']) * multiplier
        if pattern_type.startswith('HARM-'):
            return int(self._configuration.section('harmonic')['maximum_pattern_bars']) * multiplier
        return None


def _deduplication_key(candidate):
    pivot = (
        format(candidate.pivot_price.normalize(), "f")
        if isinstance(candidate.pivot_price, Decimal) else str(candidate.pivot_price)
    )
    raw = f"{candidate.isin}|{candidate.timeframe}|{candidate.pattern_type}|{candidate.start_date.isoformat()}|{pivot}"
    return sha256(raw.encode("utf-8")).hexdigest()


def _candidate_trigger_date(candidate):
    value = (
        candidate.measurements.get("trigger_date")
        or candidate.measurements.get("breakout_date")
        or candidate.detected_date
    )
    return _as_date(value)


def _changed(previous, values, key):
    return _field(previous, key) != values.get(key)
def _score_changed(previous, values, key, threshold):
    before, after = _optional_decimal(_field(previous, key)), _optional_decimal(values.get(key))
    if before is None or after is None:
        return before != after
    return abs(after - before) >= threshold
def _field(value, name):
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)
def _as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))
def _optional_decimal(value):
    return None if value is None else value if isinstance(value, Decimal) else _D(str(value))
