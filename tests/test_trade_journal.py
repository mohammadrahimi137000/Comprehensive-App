from datetime import datetime, timezone

import pytest

from trade_journal import TradeJournal


def test_create_and_close_long_trade_calculates_r_multiple(tmp_path):
    journal = TradeJournal(tmp_path / "market.db")
    trade_id = journal.create_trade(
        "xauusd", "long", 2000, 1990, 2020,
        screenshot_path="charts/trade-1.png", notes="breakout retest",
        opened_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert journal.close_trade(
        trade_id, 2020, datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
    ) == 2.0
    row = journal.list_trades("XAUUSD")[0]
    assert row["status"] == "closed"
    assert row["outcome_r"] == 2.0
    assert row["screenshot_path"] == "charts/trade-1.png"


def test_short_trade_profit_and_loss_r_values(tmp_path):
    journal = TradeJournal(tmp_path / "market.db")
    profit = journal.create_trade("XAUUSD", "short", 2000, 2010)
    loss = journal.create_trade("XAUUSD", "short", 2000, 2010)
    assert journal.close_trade(profit, 1980) == 2.0
    assert journal.close_trade(loss, 2015) == -1.5


def test_rejects_invalid_trade_geometry_and_naive_timestamps(tmp_path):
    journal = TradeJournal(tmp_path / "market.db")
    with pytest.raises(ValueError, match="below entry"):
        journal.create_trade("XAUUSD", "long", 2000, 2010)
    with pytest.raises(ValueError, match="timezone-aware"):
        journal.create_trade("XAUUSD", "long", 2000, 1990,
                             opened_at=datetime(2026, 1, 1))


def test_cannot_close_trade_twice_or_close_unknown_trade(tmp_path):
    journal = TradeJournal(tmp_path / "market.db")
    trade_id = journal.create_trade("XAUUSD", "long", 2000, 1990)
    journal.close_trade(trade_id, 2010)
    with pytest.raises(ValueError, match="already closed"):
        journal.close_trade(trade_id, 2015)
    with pytest.raises(ValueError, match="not found"):
        journal.close_trade(999, 2010)
