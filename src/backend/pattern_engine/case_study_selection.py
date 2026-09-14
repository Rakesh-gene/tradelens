"""Stable, non-cherry-picked representative case selection."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Mapping


SELECTION_POLICY_VERSION = "case-study-selection-v2"


def select_representative_cases(cases: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    """Return high, median, low, and incomplete forward-performance examples.

    Callers provide already simulated cases.  The stable tie-break is entry
    date, ISIN, then replay fingerprint, so re-running the same source facts
    never changes a catalogue merely because database row order changes.
    """
    strata = defaultdict(list)
    for case in cases:
        strata[_stratum(case)].append(dict(case))
    selected = []
    for key in sorted(strata):
        rows = sorted(strata[key], key=_tie_key)
        ranked = sorted(rows, key=lambda row: (_forward_return(row), *_tie_key(row)))
        picks = [ranked[-1], ranked[(len(ranked) - 1) // 2], ranked[0]]
        incomplete = next((row for row in rows if row.get("forward_return_pct") is None), None)
        seen = set()
        for label, row in zip(("HIGHEST_FORWARD_RETURN", "MEDIAN_FORWARD_RETURN", "LOWEST_FORWARD_RETURN"), picks):
            if _identity(row) not in seen:
                selected.append({**row, "selection_policy_version": SELECTION_POLICY_VERSION, "selection_reason": label})
                seen.add(_identity(row))
        if incomplete is not None and _identity(incomplete) not in seen:
            selected.append({**incomplete, "selection_policy_version": SELECTION_POLICY_VERSION, "selection_reason": "FIRST_INCOMPLETE_FORWARD_WINDOW"})
    return selected


def _stratum(row):
    values = tuple(str(row.get(key) or "UNKNOWN") for key in ("pattern_type", "variant", "timeframe", "direction", "market_regime", "sector_context"))
    return values
def _forward_return(row): return Decimal(str(row.get("forward_return_pct"))) if row.get("forward_return_pct") is not None else Decimal("-Infinity")
def _tie_key(row): return (str(row.get("entry_date") or "9999-12-31"), str(row.get("isin") or ""), str(row.get("replay_fingerprint") or ""))
def _identity(row): return str(row.get("id") or row.get("replay_fingerprint") or (row.get("isin"), row.get("entry_date"), row.get("pattern_type")))
