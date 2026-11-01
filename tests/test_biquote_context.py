from news_engine import BiQuoteContextClient


def test_biquote_news_and_calendar_keep_unpublished_values_null():
    def getter(url, timeout):
        if "/news/" in url:
            return [{
                "title": "Fed holds rates as inflation cools",
                "description": "Markets await the next release",
                "url": "https://example.com/news", "publisher": "Example",
                "publishedDate": "2026-11-01T10:00:00Z",
            }]
        return [{
            "id": "event-1", "time": "2026-11-02T13:30:00Z",
            "countryCode": "US", "currency": "USD",
            "name": "CPI", "importance": "high", "type": "indicator",
            "actual": None, "forecast": 3.1, "previous": 3.2,
            "timeMode": "exact", "source": "test",
        }]
    result = BiQuoteContextClient(getter=getter).fetch()
    assert result["news"][0]["publisher"] == "Example"
    assert result["news"][0]["analysis"]["potential_macro_relevance"] is True
    event = result["economic_calendar"][0]
    assert event["actual"] is None
    assert event["surprise_actual_minus_forecast"] is None
    assert event["importance"] == "high"


def test_biquote_context_reports_news_and_calendar_errors_independently():
    def getter(url, timeout):
        raise RuntimeError("offline")
    result = BiQuoteContextClient(getter=getter).fetch()
    assert result["news"] == []
    assert result["economic_calendar"] == []
    assert len(result["errors"]) == 2
