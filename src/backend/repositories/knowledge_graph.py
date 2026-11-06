"""Read-only Ontop persistence boundary; only registered SPARQL is executable."""
import json
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from chat.errors import ChatError
from chat.http_json import post_json

SEMANTIC = Path(__file__).resolve().parent / "semantic"
SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9._&-]{0,30}", re.ASCII)


def validated_symbol(value):
    if not isinstance(value, str):
        raise ValueError("Choose an NSE equity symbol.")
    value = value.strip().upper()
    if not SYMBOL.fullmatch(value) or re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
        raise ValueError("Choose a valid NSE equity symbol, not an ISIN.")
    return value


def current_setup_query(symbol):
    # The validated alphabet cannot introduce RDF syntax. JSON supplies a quoted
    # string literal; no arbitrary query fragments or client IRIs are accepted.
    symbol = validated_symbol(symbol)
    return (SEMANTIC / "queries/equity_setup_today.rq").read_text(encoding="utf-8").replace(
        "__SYMBOL__", json.dumps(symbol)
    )


class OntopKnowledgeGraphRepository:
    def __init__(self, endpoint: str, timeout: float = 10):
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ONTOP_URL must be an HTTP(S) endpoint without credentials or query parameters")
        self.endpoint, self.timeout = endpoint, timeout

    def current_setups(self, symbol):
        payload = post_json(
            self.endpoint, urlencode({"query": current_setup_query(symbol)}).encode("utf-8"),
            {"Accept": "application/sparql-results+json", "Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout, upstream="The ontology service",
        )
        results = payload.get("results")
        bindings = results.get("bindings") if isinstance(results, dict) else None
        if not isinstance(bindings, list) or len(bindings) > 26:
            raise ChatError("ONTOLOGY_INVALID_EVIDENCE", "The ontology service returned invalid evidence.")
        rows = []
        for binding in bindings:
            if not isinstance(binding, dict) or any(
                not isinstance(term, dict) or not isinstance(term.get("value"), str)
                for term in binding.values()
            ):
                raise ChatError("ONTOLOGY_INVALID_EVIDENCE", "The ontology service returned invalid evidence.")
            rows.append({key: term["value"] for key, term in binding.items()})
        return rows
