"""Read-only RSS/Atom headline ingestion and transparent keyword-based tagging."""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse


DEFAULT_FEEDS = [
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC%3DF&region=US&lang=en-US",
]
POSITIVE = {"rally", "surge", "gains", "higher", "strong", "eases", "cooling", "optimism"}
NEGATIVE = {"plunge", "fall", "drops", "lower", "weak", "inflation", "war", "risk", "hawkish", "crisis"}
MACRO = {"fed", "federal reserve", "fomc", "inflation", "cpi", "ppi", "jobs", "payroll",
         "unemployment", "interest rate", "central bank", "gdp", "powell", "treasury"}


def _tag_text(element: ET.Element, *names: str) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return unescape(re.sub(r"<[^>]+>", " ", found.text)).strip()
    return ""


def _date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None


def classify_headline(title: str, summary: str = "") -> dict:
    text = f"{title} {summary}".lower()
    words = set(re.findall(r"[a-z]+", text))
    positive = sorted(words & POSITIVE)
    negative = sorted(words & NEGATIVE)
    macro = sorted(term for term in MACRO if term in text)
    score = len(positive) - len(negative)
    return {
        "sentiment_score": score,
        "tone": "positive" if score > 0 else "negative" if score < 0 else "neutral_or_unclear",
        "positive_terms": positive, "negative_terms": negative,
        "macro_topics": macro,
        "potential_macro_relevance": bool(macro),
        "method": "transparent_keyword_heuristic",
    }


class RssNewsClient:
    def __init__(self, timeout: float = 8.0, max_bytes: int = 2_000_000):
        self.timeout = timeout
        self.max_bytes = max_bytes

    def fetch(self, urls: list[str] | None = None, limit_per_feed: int = 30) -> dict:
        feeds = urls or DEFAULT_FEEDS
        items, errors = [], []
        for url in feeds:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                errors.append({"url": url, "error": "Only HTTPS RSS sources are allowed."})
                continue
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": "Comprehensive-App/1.0", "Accept": "application/rss+xml, application/atom+xml, application/xml"}
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read(self.max_bytes + 1)
                if len(raw) > self.max_bytes:
                    raise ValueError("Feed exceeds configured response size limit.")
                root = ET.fromstring(raw)
                entries = root.findall(".//item") or root.findall(".//{*}entry")
                for entry in entries[:max(1, min(100, limit_per_feed))]:
                    title = _tag_text(entry, "title", "{*}title")
                    summary = _tag_text(entry, "description", "summary", "{*}summary", "{*}content")
                    link = _tag_text(entry, "link", "{*}link")
                    if not link:
                        link_node = entry.find("{*}link")
                        if link_node is not None:
                            link = link_node.attrib.get("href", "")
                    published = (_tag_text(entry, "pubDate", "published", "updated",
                                            "{*}pubDate", "{*}published", "{*}updated"))
                    if title:
                        items.append({
                            "title": title, "summary": summary[:1200], "url": link,
                            "published_at": _date(published), "feed": url,
                            "analysis": classify_headline(title, summary),
                        })
            except Exception as exc:
                errors.append({"url": url, "error": f"{type(exc).__name__}: {exc}"})
        unique = {}
        for item in items:
            unique.setdefault((item["title"].lower(), item["url"]), item)
        return {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "items": list(unique.values()),
            "errors": errors,
            "limitations": [
                "Headline tone and macro relevance use keyword heuristics, not a language model.",
                "News headlines are context only; verify the original source and publication time.",
                "RSS feeds may be delayed, incomplete, or unavailable.",
            ],
        }


def assess_event_risk(events: list[dict], now: datetime | None = None,
                      horizon_minutes: int = 15, after_minutes: int = 5) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    start = now.timestamp() - after_minutes * 60
    end = now.timestamp() + horizon_minutes * 60
    relevant, uncertain = [], []
    for event in events:
        if str(event.get("importance", "")).lower() != "high":
            continue
        if event.get("time_mode") != "exact":
            uncertain.append({"name": event.get("name"), "time": event.get("time"),
                              "reason": "calendar_time_is_not_exact"})
            continue
        try:
            event_time = datetime.fromisoformat(str(event["time"]).replace("Z", "+00:00"))
            if event_time.tzinfo is not None and start <= event_time.timestamp() <= end:
                relevant.append({"name": event.get("name"), "time": event.get("time"),
                                 "country": event.get("country"), "currency": event.get("currency"),
                                 "importance": "high"})
        except (KeyError, TypeError, ValueError):
            continue
    return {
        "status": "high_impact_event_window" if relevant else "no_exact_high_impact_event_in_window",
        "events": relevant, "uncertain_events": uncertain,
        "window_minutes_before": after_minutes, "window_minutes_after": horizon_minutes,
        "warning": "Event proximity is a caution flag, not a directional prediction.",
    }

class BiQuoteContextClient:
    """Official BiQuote market-news and economic-calendar read-only endpoints."""

    def __init__(self, getter=None, timeout: float = 10.0):
        if getter is None:
            from provider_clients import _get_json
            getter = _get_json
        self.getter = getter
        self.timeout = timeout

    def fetch(self, symbol: str = "XAUUSD", countries: tuple[str, ...] = ("US", "EU", "GB"),
              importance: str = "high", news_limit: int = 20,
              calendar_limit: int = 100) -> dict:
        from urllib.parse import urlencode

        if importance not in {"low", "medium", "high"}:
            raise ValueError("importance must be low, medium or high")
        news_url = "https://biquote.io/api/news/market?" + urlencode({
            "symbol": symbol.strip().upper(), "language": "en",
            "country": "US", "maxResults": max(1, min(50, news_limit)),
        })
        calendar_url = "https://biquote.io/api/calendar/upcoming?" + urlencode({
            "countries": ",".join(countries),
            "importance": importance,
            "limit": max(1, min(500, calendar_limit)),
        })
        errors = []
        try:
            news_payload = self.getter(news_url, self.timeout)
            if not isinstance(news_payload, list):
                raise RuntimeError("BiQuote news response is not a list")
            news = [{
                "title": str(item.get("title") or ""),
                "description": str(item.get("description") or ""),
                "url": str(item.get("url") or ""),
                "publisher": str(item.get("publisher") or ""),
                "published_at": item.get("publishedDate"),
                "analysis": classify_headline(
                    str(item.get("title") or ""), str(item.get("description") or "")
                ),
            } for item in news_payload if isinstance(item, dict)]
        except Exception as exc:
            news = []
            errors.append({"source": "BiQuote market news", "error": f"{type(exc).__name__}: {exc}"})
        try:
            calendar_payload = self.getter(calendar_url, self.timeout)
            if not isinstance(calendar_payload, list):
                raise RuntimeError("BiQuote calendar response is not a list")
            events = []
            for item in calendar_payload:
                if not isinstance(item, dict):
                    continue
                actual = item.get("actual")
                forecast = item.get("forecast")
                surprise = None
                if actual is not None and forecast is not None:
                    try:
                        surprise = float(actual) - float(forecast)
                    except (TypeError, ValueError):
                        pass
                events.append({
                    "id": item.get("id"), "time": item.get("time"),
                    "country": item.get("countryCode"), "currency": item.get("currency"),
                    "name": item.get("name"), "importance": item.get("importance"),
                    "type": item.get("type"), "sector": item.get("sector"),
                    "actual": actual, "forecast": forecast,
                    "previous": item.get("previous"),
                    "revised_previous": item.get("revisedPrevious"),
                    "surprise_actual_minus_forecast": surprise,
                    "time_mode": item.get("timeMode"),
                    "source": item.get("source"), "source_url": item.get("sourceUrl"),
                })
            events.sort(key=lambda row: row.get("time") or "")
        except Exception as exc:
            events = []
            errors.append({"source": "BiQuote economic calendar", "error": f"{type(exc).__name__}: {exc}"})
        return {
            "symbol": symbol.strip().upper(),
            "news": news, "economic_calendar": events,
            "event_risk": assess_event_risk(events), "errors": errors,
            "limitations": [
                "News headline tone is a keyword heuristic, not a causal market-impact model.",
                "Calendar actual/forecast values are kept null when unpublished; null is never treated as zero.",
                "Non-exact calendar time modes are date/tentative placeholders, not precise release times.",
                "Confirm important releases with the linked original publisher before acting.",
            ],
        }
