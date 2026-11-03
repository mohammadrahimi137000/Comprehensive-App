"""Small Toobit REST client with documented HMAC-SHA256 signing."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import requests


class ToobitAPIError(RuntimeError):
    pass


class ToobitClient:
    def __init__(self, api_key: str = "", api_secret: str = "", base_url: str = "https://api.toobit.com", recv_window_ms: int = 5000, session=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window_ms = recv_window_ms
        self.session = session or requests.Session()

    def _signature(self, payload: str) -> str:
        if not self.api_secret:
            raise ToobitAPIError("TOOBIT_API_SECRET is required for signed requests")
        return hmac.new(self.api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    def request(self, method: str, path: str, params: dict | None = None, body: dict | None = None, signed: bool = False):
        method = method.upper()
        items = list((params or {}).items())
        if signed:
            if not self.api_key or not self.api_secret:
                raise ToobitAPIError("Toobit API credentials are not configured")
            items.extend([("timestamp", int(time.time() * 1000)), ("recvWindow", self.recv_window_ms)])
        query = urlencode(items)
        body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
        if signed:
            query += ("" if not query else "")
            signature = self._signature(query + body_text)
            query += ("&" if query else "") + "signature=" + signature
        url = self.base_url + path + (("?" + query) if query else "")
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-BB-APIKEY"] = self.api_key
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            response = self.session.request(method, url, data=body_text if body is not None else None, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise ToobitAPIError(f"Toobit network error: {exc}") from exc
        if response.status_code >= 400:
            # A server-side 5xx can have an unknown order outcome; never retry an order blindly.
            raise ToobitAPIError(f"Toobit HTTP {response.status_code}: {response.text[:500]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ToobitAPIError("Toobit returned invalid JSON") from exc
        if isinstance(payload, dict) and payload.get("code") not in (None, 200, "200"):
            raise ToobitAPIError(f"Toobit API error {payload.get('code')}: {payload.get('msg', '')}")
        return payload

    def server_time(self):
        return self.request("GET", "/api/v1/time")

    def exchange_info(self):
        return self.request("GET", "/api/v1/exchangeInfo")

    def mark_price(self, symbol: str):
        return self.request("GET", "/quote/v1/markPrice", params={"symbol": symbol})

    def place_futures_market_order(self, *, symbol: str, side: str, position_side: str, quantity: str, client_order_id: str):
        body = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side,
            "type": "MARKET",
            "quantity": quantity,
            "newClientOrderId": client_order_id,
        }
        return self.request("POST", "/api/v2/futures/order", body=body, signed=True)
