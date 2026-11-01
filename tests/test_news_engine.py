from news_engine import classify_headline, RssNewsClient


def test_headline_macro_tags_are_explainable():
    result = classify_headline("Fed signals higher interest rates amid inflation risk")
    assert result["potential_macro_relevance"] is True
    assert "fed" in result["macro_topics"]
    assert result["tone"] == "negative"
    assert result["method"] == "transparent_keyword_heuristic"


def test_rejects_non_https_feed_urls():
    result = RssNewsClient().fetch(["http://example.com/feed.xml"])
    assert result["items"] == []
    assert "Only HTTPS" in result["errors"][0]["error"]
