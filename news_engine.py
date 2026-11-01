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
