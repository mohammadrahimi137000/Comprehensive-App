from datetime import datetime, timezone

import pytest

from trendo_position_journal import TrendoPositionJournal


def position(ticket="217396516", floating=1.20, swap=-0.05, commission=-0.06):
    return {
        "position_id": ticket,
        "symbol": "GOLD",
        "side": "SELL",
        "volume": 0.02,
        "opened_at": "2026/11/03 00:44:03",
        "open_price": 3947.28,
        "stop_loss": 3946.68,
        "take_profit": 0.0,
        "swap_usd": swap,
        "commission_usd": commission,
        "floating_profit_usd": floating,
        "net_pnl_usd": floating + swap + commission,
    }


def test_upsert_tracks_one_ticket_and_appends_pnl_history(tmp_path):
    journal = TrendoPositionJournal(tmp_path / "trades.db")
    t1 = datetime(2026, 11, 3, 1, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 3, 1, 0, 5, tzinfo=timezone.utc)

    assert journal.record_positions([position()], t1) == 1
    assert journal.record_positions([position(floating=1.80)], t2) == 1

    rows = journal.list_positions()
    assert len(rows) == 1
    assert rows[0]["position_id"] == "217396516"
    assert rows[0]["floating_profit_usd"] == pytest.approx(1.80)
    assert rows[0]["net_pnl_usd"] == pytest.approx(1.69)
    history = journal.pnl_history("217396516")
    assert len(history) == 2
    assert history[0]["net_pnl_usd"] == pytest.approx(1.69)


def test_rejects_inconsistent_net_pnl(tmp_path):
    journal = TrendoPositionJournal(tmp_path / "trades.db")
    item = position()
    item["net_pnl_usd"] = 99
    with pytest.raises(ValueError, match="Net P/L"):
        journal.record_positions([item])


def test_rejects_duplicate_ticket_in_one_snapshot(tmp_path):
    journal = TrendoPositionJournal(tmp_path / "trades.db")
    with pytest.raises(ValueError, match="Duplicate"):
        journal.record_positions([position(), position()])
