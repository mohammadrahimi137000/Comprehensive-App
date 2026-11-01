"""Compare broker Bid/Ask midpoint with independent indicative spot references."""
from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

from feed_router import Quote
from provider_clients import SpotReference


def compare_reference_prices(
    broker_quote: Quote, references: list[SpotReference],
    now: datetime | None = None, max_age_seconds: float = 180.0,
    outlier_threshold_bps: float = 35.0,
) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    eligible = []
    rejected = []
    for reference in references:
        age = (now - reference.timestamp).total_seconds()
        if reference.instrument.upper() != broker_quote.instrument.upper():
            rejected.append({"source": reference.source, "reason": "instrument_mismatch"})
        elif reference.state != "fresh":
            rejected.append({"source": reference.source, "reason": "reference_not_fresh"})
        elif age < -2 or age > max_age_seconds:
            rejected.append({"source": reference.source, "reason": "reference_out_of_age"})
        elif reference.price <= 0:
            rejected.append({"source": reference.source, "reason": "invalid_reference_price"})
        else:
            eligible.append(reference)

    if not eligible:
        return {
            "status": "insufficient_reference_data", "broker_mid": broker_quote.mid,
            "comparisons": [], "rejected": rejected, "outlier_sources": [],
        }

    reference_median = median(item.price for item in eligible)
    comparisons = []
    outliers = []
    for item in eligible:
        diff_bps = (broker_quote.mid - item.price) / item.price * 10000
        peer_diff_bps = (item.price - reference_median) / reference_median * 10000
        outlier = abs(peer_diff_bps) > outlier_threshold_bps
        if outlier:
            outliers.append(item.source)
        comparisons.append({
            "source": item.source,
            "reference_price": item.price,
            "broker_minus_reference_bps": round(diff_bps, 2),
            "peer_deviation_bps": round(peer_diff_bps, 2),
            "outlier": outlier,
            "indicative_only": True,
            "attribution_text": item.attribution_text,
            "attribution_url": item.attribution_url,
        })
    return {
        "status": "compared",
        "broker_mid": broker_quote.mid,
        "reference_median": reference_median,
        "comparisons": comparisons,
        "rejected": rejected,
        "outlier_sources": outliers,
        "note": "Indicative spot references are diagnostics only; they are not substituted for broker Bid/Ask.",
    }
