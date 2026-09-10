"""Deterministic, browser-facing decisions derived from pattern evidence.

The score describes alignment and completeness of currently available evidence.
It is deliberately not a forecast probability and does not infer portfolio ownership.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation


METHODOLOGY_VERSION = "decision-intelligence-v1"

_STATE_DECISIONS = {
    "DETECTED": ("OBSERVE", "Observe", "neutral", "Let the structure develop; there is no entry signal yet."),
    "FORMING": ("WATCH", "Watch", "watch", "Keep it on the watchlist while the structure continues to tighten."),
    "MATURE": ("PREPARE", "Prepare", "watch", "Prepare the trade plan, but wait for the defined trigger."),
    "READY": ("WAIT_FOR_BREAKOUT", "Ready", "action", "Wait for a decisive close above the trigger; do not anticipate it."),
    "TRIGGERED": ("WAIT_FOR_CONFIRMATION", "Breakout triggered", "action", "The trigger has traded; require follow-through before treating the entry as confirmed."),
    "CONFIRMED": ("ENTRY_CONFIRMED", "Entry confirmed", "positive", "Entry conditions are confirmed. Hold only while the setup remains above its risk boundary."),
    "FAILED": ("EXIT_OR_AVOID", "Exit or avoid", "danger", "The setup has failed. Avoid a new entry and exit an existing position according to the risk plan."),
    "INVALIDATED": ("EXIT_OR_AVOID", "Exit or avoid", "danger", "The setup is invalidated. Its original trade thesis no longer applies."),
    "EXPIRED": ("IGNORE", "Ignore", "neutral", "The setup expired without a valid continuation signal."),
}

_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def build_decision(row: Mapping[str, object], setup: Mapping[str, object]) -> dict[str, object]:
    state = str(setup.get("state") or "DETECTED").upper()
    action, action_label, tone, next_step = _STATE_DECISIONS.get(state, _STATE_DECISIONS["DETECTED"])
    label = _pattern_label(setup.get("variant"), setup.get("patternType"))
    quality = _decimal(setup.get("qualityScore"))
    maturity = _decimal(setup.get("maturityScore"))
    context = _decimal(setup.get("contextScore"))
    liquidity = _decimal(setup.get("liquidityScore"))
    relative_strength = _decimal(row.get("relative_strength_percentile"))
    setup_score = _decimal(setup.get("setupScore"))
    distance = _decimal(setup.get("distanceToPivotPct"))
    pivot = _decimal(setup.get("pivotPrice"))
    support = _decimal(row.get("support_price"))
    invalidation = _decimal(row.get("invalidation_price"))

    strengths: list[str] = []
    cautions: list[str] = []
    missing: list[str] = []
    if quality is None: missing.append("pattern quality")
    elif quality >= 80: strengths.append("Pattern geometry and behaviour score highly")
    elif quality < 60: cautions.append("Pattern quality is below the preferred range")
    if maturity is None: missing.append("lifecycle maturity")
    elif maturity >= 80: strengths.append("The structure is mature enough for its current stage")
    if relative_strength is None: missing.append("relative-strength percentile")
    elif relative_strength >= 80: strengths.append("Relative strength is leading the peer universe")
    elif relative_strength < 50: cautions.append("Relative strength is below the middle of the peer universe")
    if context is None: missing.append("market and sector context")
    elif context >= 70: strengths.append("Market and sector context is constructive")
    elif context < 40: cautions.append("Market or sector context is weak")
    if liquidity is None: missing.append("liquidity")
    elif liquidity >= 75: strengths.append("Liquidity is within the preferred profile")
    else: cautions.append("Liquidity is below the preferred profile")
    if int(setup.get("evidenceCount") or 0) >= 3:
        strengths.append("Multiple independent signals support the setup")
    if distance is not None and distance > 8:
        cautions.append("Price is extended more than 8% above the trigger")
    elif distance is not None and distance < -12 and state in {"MATURE", "READY"}:
        cautions.append("Price remains well below the trigger")

    requires_trigger = state in {"MATURE", "READY", "TRIGGERED", "CONFIRMED"}
    requires_risk = state in {"READY", "TRIGGERED", "CONFIRMED"}
    if requires_trigger and pivot is None: missing.append("trigger price")
    if requires_risk and invalidation is None: missing.append("invalidation price")

    evidence = (
        (setup_score, Decimal("0.30")), (quality, Decimal("0.20")),
        (maturity, Decimal("0.15")), (context, Decimal("0.15")),
        (liquidity, Decimal("0.10")), (relative_strength, Decimal("0.10")),
    )
    available_weight = sum((weight for value, weight in evidence if value is not None), Decimal("0"))
    aligned = sum((value * weight for value, weight in evidence if value is not None), Decimal("0"))
    completeness = available_weight * 100
    confidence = None if not available_weight else aligned / available_weight * (Decimal("0.75") + completeness / 400)
    if confidence is not None:
        confidence = max(Decimal("0"), min(Decimal("100"), confidence)).quantize(Decimal("0.1"))
    band = "UNAVAILABLE" if confidence is None else "HIGH" if confidence >= 80 else "MODERATE" if confidence >= 65 else "LOW"

    adjective = "high-quality " if quality is not None and quality >= 80 else ""
    headline = _headline(state, action_label, adjective + label)
    tier = str((setup.get("bestFit") or {}).get("tier") or "").upper() if isinstance(setup.get("bestFit"), Mapping) else ""
    summary = _summary(state, label, tier)
    risk_pct = None
    if pivot not in (None, Decimal("0")) and invalidation is not None:
        risk_pct = ((pivot - invalidation) / pivot * 100).quantize(Decimal("0.01"))

    return {
        "methodologyVersion": METHODOLOGY_VERSION,
        "action": action, "actionLabel": action_label, "tone": tone,
        "headline": headline, "summary": summary, "nextStep": next_step,
        "holdingAction": "HOLD_WHILE_VALID" if state == "CONFIRMED" else None,
        "confidenceScore": confidence, "confidenceBand": band,
        "confidenceMeaning": "Evidence alignment and completeness, not historical probability.",
        "evidenceCompletenessPct": completeness.quantize(Decimal("0.1")),
        "strengths": strengths[:4], "cautions": cautions[:4], "missingEvidence": missing,
        "levels": {
            "triggerPrice": pivot, "supportPrice": support,
            "invalidationPrice": invalidation, "riskFromTriggerPct": risk_pct,
        },
    }


def _headline(state: str, action_label: str, label: str) -> str:
    if state == "TRIGGERED": return f"Breakout triggered — {label}"
    if state == "CONFIRMED": return f"Entry confirmed — {label}"
    if state in {"FAILED", "INVALIDATED", "EXPIRED"}: return f"{action_label} — {label}"
    return f"{action_label} — {label}"


def _summary(state: str, label: str, tier: str) -> str:
    stage = {
        "DETECTED": "has been detected but is still early",
        "FORMING": "is developing and has not reached entry readiness",
        "MATURE": "is structurally mature but has not produced a trigger",
        "READY": "is ready and waiting for a valid breakout",
        "TRIGGERED": "has crossed its trigger and now needs confirmation",
        "CONFIRMED": "has produced the required breakout follow-through",
        "FAILED": "has failed its validation rules",
        "INVALIDATED": "has broken the level that defined the trade thesis",
        "EXPIRED": "did not complete within its valid lifecycle window",
    }.get(state, "is being monitored")
    peer = " It ranks among the stronger setups in the same stage." if tier in {"LEADING", "STRONG"} else ""
    return f"The {label} {stage}.{peer}"


def _pattern_label(variant: object, pattern_type: object) -> str:
    variant_text = str(variant or "").upper()
    match = re.fullmatch(r"VCP-(\d+)C", variant_text)
    if match:
        count = int(match.group(1))
        count_label = _NUMBER_WORDS.get(count, str(count))
        return f"{count_label}-contraction VCP"
    labels = {
        "BASE-VCP": "volatility-contraction setup", "BASE-FLAT": "flat-base setup",
        "BASE-52WH": "52-week-high base", "BRK-RANGE": "range breakout",
        "BRK-MULTIY": "multi-year breakout", "PB-EMA20": "20-day EMA pullback",
        "PB-SMA50": "50-day SMA pullback", "PB-RETEST": "breakout retest",
    }
    return labels.get(str(pattern_type or "").upper(), str(variant or pattern_type or "pattern").replace("-", " ").lower())


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "": return None
    try: return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError): return None
