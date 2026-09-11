"""Transparent sector rotation, using persisted benchmark-relative returns."""
from datetime import date, datetime, timezone

VERSION = "sector-rotation-v1"


def zone(strength, momentum):
    if strength is None or momentum is None:
        return "UNAVAILABLE"
    if strength >= 0:
        return "LEADING" if momentum >= 0 else "WEAKENING"
    return "IMPROVING" if momentum >= 0 else "LAGGING"


def rotation_payload(rows):
    items = []
    for row in rows:
        strength = row.get("rs_3m")
        baseline, short = row.get("baseline_rs"), row.get("short_rs")
        momentum = float(short) - float(baseline) if short is not None and baseline is not None else None
        count = int(row["member_count"])
        covered, pairs = int(row["covered_count"]), int(row["paired_count"])
        items.append({
            "code": row["sector_code"], "name": row["sector_name"],
            "rs1m": row.get("rs_1m"), "rs3m": strength,
            "rs6m": row.get("rs_6m"), "rs12m": row.get("rs_12m"),
            "momentum": momentum, "zone": zone(strength, momentum),
            "memberCount": count, "coveredCount": covered, "pairedCount": pairs,
            "coveragePct": covered / count * 100 if count else None,
            "isPartial": covered < count or pairs < count,
            "featureVersions": row.get("feature_versions") or [],
            "adjustmentVersions": row.get("adjustment_versions") or [],
        })
    as_of = rows[0].get("data_as_of") if rows else None
    return {
        "dataAsOf": as_of,
        "generatedAt": datetime.now(timezone.utc), "engineVersion": VERSION,
        "configurationVersion": VERSION, "isStale": as_of is None or (date.today() - as_of).days > 3,
        "items": items,
        "methodology": "Sector medians of stock returns minus the feature benchmark return (percentage points). X: 63-session RS. Y: median 21-session RS minus one-third of median 63-session RS, using constituents with both horizons on the same date. This is a short-versus-medium-term momentum proxy, not an observed sector-history change. Zero divides each axis. Membership is effective-dated; current EQ eligibility is used. Not a historical sector index, backtest, or forecast.",
    }
