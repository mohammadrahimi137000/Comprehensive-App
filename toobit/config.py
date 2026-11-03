"""Environment-backed Toobit configuration. Secrets are never stored in source control."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ToobitConfig:
    api_key: str = ""
    api_secret: str = ""
    base_url: str = "https://api.toobit.com"
    symbol: str = "XAU-SWAP-USDT"
    recv_window_ms: int = 5000
    live_trading_enabled: bool = False
    max_leverage: int = 1
    risk_per_trade_usdt: float = 1.0
    max_notional_usdt: float = 25.0
    max_open_positions: int = 1

    @classmethod
    def from_env(cls) -> "ToobitConfig":
        return cls(
            api_key=os.getenv("TOOBIT_API_KEY", "").strip(),
            api_secret=os.getenv("TOOBIT_API_SECRET", "").strip(),
            base_url=os.getenv("TOOBIT_BASE_URL", "https://api.toobit.com").rstrip("/"),
            symbol=os.getenv("TOOBIT_SYMBOL", "XAU-SWAP-USDT").strip().upper(),
            recv_window_ms=int(os.getenv("TOOBIT_RECV_WINDOW_MS", "5000")),
            live_trading_enabled=os.getenv("TOOBIT_LIVE_TRADING", "false").lower() == "true",
            max_leverage=int(os.getenv("TOOBIT_MAX_LEVERAGE", "1")),
            risk_per_trade_usdt=float(os.getenv("TOOBIT_RISK_PER_TRADE_USDT", "1")),
            max_notional_usdt=float(os.getenv("TOOBIT_MAX_NOTIONAL_USDT", "25")),
            max_open_positions=int(os.getenv("TOOBIT_MAX_OPEN_POSITIONS", "1")),
        )

    def validate(self) -> None:
        if not self.symbol:
            raise ValueError("TOOBIT_SYMBOL cannot be empty")
        if not 1000 <= self.recv_window_ms <= 60000:
            raise ValueError("recv_window_ms must be between 1000 and 60000")
        if not 1 <= self.max_leverage <= 5:
            raise ValueError("Initial integration caps leverage at 5x")
        if self.risk_per_trade_usdt <= 0 or self.max_notional_usdt <= 0:
            raise ValueError("Risk and notional limits must be positive")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
