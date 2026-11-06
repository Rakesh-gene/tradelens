"""Versioned Overview selection policy, independent of detector configuration."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import tomllib

STATES = ("READY", "TRIGGERED", "CONFIRMED")


def number(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


@dataclass(frozen=True)
class OverviewQualification:
    policy_version: str
    configuration_version: str
    minimum_peer_percentile: Decimal
    minimum_best_fit: Decimal
    minimum_quality: Decimal
    minimum_context: Decimal
    required_liquidity: Decimal

    def parameters(self):
        return {name: getattr(self, name) for name in (
            "minimum_peer_percentile", "minimum_best_fit", "minimum_quality", "minimum_context", "required_liquidity")}

    def metadata(self, candidate_count, qualified_count, as_of):
        p = self.parameters()
        return {"policyVersion": self.policy_version, "configurationVersion": self.configuration_version,
                "candidateCount": candidate_count, "qualifiedCount": qualified_count,
                "dataAsOf": as_of, "peerScope": "eligibleOverviewEquitiesWithinLifecycleState",
                "thresholds": {"minimumPeerPercentile": self.minimum_peer_percentile, "minimumBestFitScore": self.minimum_best_fit,
                               "minimumQualityScore": self.minimum_quality, "minimumContextScore": self.minimum_context,
                               "requiredLiquidityScore": self.required_liquidity}, "states": list(STATES),
                "summary": (f"Top {100 - p['minimum_peer_percentile']}% within each lifecycle state; "
                            f"best fit ≥ {p['minimum_best_fit']}, quality ≥ {p['minimum_quality']}, "
                            f"context ≥ {p['minimum_context']}; all liquidity checks pass, "
                            "with current evidence and valid risk levels. Scores rank evidence, not probability.")}

    def accepts(self, row, as_of):
        checks = (("best_fit_percentile_raw", self.minimum_peer_percentile),
                  ("best_fit_score", self.minimum_best_fit), ("quality_score", self.minimum_quality),
                  ("context_score", self.minimum_context))
        if any(number(row.get(key)) is None or not minimum <= number(row[key]) <= 100 for key, minimum in checks):
            return False
        if not all(number(row.get(key)) is not None and 0 <= number(row[key]) <= 100 for key in ("setup_score",)):
            return False
        if number(row.get("liquidity_score")) != self.required_liquidity:
            return False
        if row.get("last_updated_date") != as_of or row.get("feature_date") != as_of or row.get("price_date") != as_of:
            return False
        if not all(row.get(key) for key in ("engine_version", "configuration_version", "feature_version", "adjustment_version")):
            return False
        prices = [number(row.get(key)) for key in ("last_close", "pivot_price", "invalidation_price")]
        return all(value is not None and value > 0 for value in prices) and prices[0] > prices[2]

    def evidence(self, row):
        return {"policyVersion": self.policy_version, "configurationVersion": self.configuration_version,
                "values": {"bestFit": row["best_fit_score"], "peerPercentile": row["best_fit_percentile"],
                           "quality": row["quality_score"], "context": row["context_score"],
                           "liquidity": row["liquidity_score"]},
                "evaluationDate": row["last_updated_date"], "featureDate": row["feature_date"],
                "priceDate": row["price_date"], "riskValid": True}


def load_overview_qualification(path=None):
    content = (Path(path) if path else Path(__file__).resolve().parents[1] / "configuration/overview.toml").read_bytes()
    values = tomllib.loads(content.decode("utf-8"))
    if values.get("policy_version") != "overview-qualified-v1":
        raise ValueError("Unsupported Overview qualification policy")
    for key in ("minimum_peer_percentile", "minimum_best_fit", "minimum_quality", "minimum_context", "required_liquidity"):
        value = number(values.get(key))
        if value is None or isinstance(values[key], bool) or not 0 <= value <= 100:
            raise ValueError(f"Invalid Overview qualification setting: {key}")
        values[key] = value
    if values["required_liquidity"] != 100:
        raise ValueError("Overview requires all configured liquidity checks to pass")
    return OverviewQualification(configuration_version=sha256(content).hexdigest()[:16], **values)
