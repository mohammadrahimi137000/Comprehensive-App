from datetime import datetime, timezone

from biquote_stream import BiQuoteSignalRClient


class FakeConnection:
    def __init__(self):
        self.handlers = {}
        self.sent = []
        self.started = False
        self.stopped = False
        self.open_callback = None

    def on(self, name, callback):
        self.handlers[name] = callback

    def on_open(self, callback):
        self.open_callback = callback

    def on_close(self, callback):
        self.close_callback = callback

    def on_error(self, callback):
        self.error_callback = callback

    def send(self, method, args):
        self.sent.append((method, args))

    def start(self):
        self.started = True
        self.open_callback()

    def stop(self):
        self.stopped = True


def test_signalr_client_subscribes_and_receives_fresh_tick():
    connection = FakeConnection()
    received = []
    client = BiQuoteSignalRClient(
        symbols=("XAUUSD",), on_quote=received.append,
        connection_factory=lambda: connection,
    )
    client.start()
    assert connection.started is True
    assert connection.sent[0] == ("Subscribe", [["XAUUSD"]])

    connection.handlers["ReceiveTick"]({
        "symbol": "XAUUSD", "timestamp": "2026-11-01T10:00:00Z",
        "bid": 3999.5, "ask": 3999.7, "source": "test-feed",
    })
    quote = client.get_latest_quote()
    assert quote is received[0]
    assert quote.bid == 3999.5
    assert quote.timestamp.tzinfo == timezone.utc
    client.stop()
    assert connection.sent[-1] == ("Unsubscribe", [["XAUUSD"]])
    assert connection.stopped is True


def test_signalr_client_ignores_stale_and_malformed_ticks():
    connection = FakeConnection()
    client = BiQuoteSignalRClient(connection_factory=lambda: connection)
    client.start()
    handler = connection.handlers["ReceiveTick"]
    handler({"symbol": "XAUUSD", "stale": True})
    handler({"symbol": "XAUUSD", "timestamp": "bad", "bid": 10, "ask": 11})
    handler({"symbol": "EURUSD", "timestamp": "2026-11-01T10:00:00Z", "bid": 1, "ask": 2})
    assert client.get_latest_quote() is None
    client.stop()


def test_signalr_client_requires_at_least_one_symbol():
    import pytest
    with pytest.raises(ValueError):
        BiQuoteSignalRClient(symbols=())
