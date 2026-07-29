"""
bot/strategy/orb.py — Opening Range Breakout Strategy

Logic:
  1. First 30 minutes (9:30–10:00 AM ET): track range high/low.
  2. After 10:00 AM: watch for a 1-min bar closing ABOVE range high (LONG signal)
     or BELOW range low (SHORT signal).
  3. Stop loss = opposite side of range (+ small buffer).
  4. Take profit = entry + 1.5× range width.
  5. One trade per symbol per day.
  6. Skip if opening range is wider than MAX_RANGE_PCT (volatile/gap day).
"""

from datetime import time, date as date_type
from typing import Optional, Dict
import pandas as pd


class ORBStrategy:
    """Opening Range Breakout — pure, mechanical, one trade per symbol per day."""

    RANGE_START  = time(9, 30)
    RANGE_END    = time(10, 0)

    def __init__(self, tp_multiplier: float = 1.5, max_range_pct: float = 0.005,
                 cutoff: time = time(14, 30)):
        """
        Args:
            tp_multiplier:  Take-profit = entry ± tp_multiplier × range_width
            max_range_pct:  Skip trade if range > this fraction of price (gap/news day)
            cutoff:         No new entries after this time (ET)
        """
        self.tp_multiplier = tp_multiplier
        self.max_range_pct = max_range_pct
        self.cutoff        = cutoff
        self._state: Dict[str, dict] = {}

    # ── Internal state helpers ────────────────────────────────────────────────

    def _get_state(self, symbol: str) -> dict:
        if symbol not in self._state:
            self._state[symbol] = self._blank_state()
        return self._state[symbol]

    @staticmethod
    def _blank_state() -> dict:
        return {
            "date":         None,
            "range_high":   None,
            "range_low":    None,
            "traded_today": False,
        }

    def reset(self, symbol: str) -> None:
        """Reset all state for a symbol (call between backtest runs)."""
        self._state[symbol] = self._blank_state()

    def reset_all(self) -> None:
        self._state.clear()

    # ── Core evaluation ───────────────────────────────────────────────────────

    def evaluate(self, bar: dict, symbol: str) -> Optional[Dict]:
        """
        Evaluate one 1-minute OHLCV bar.

        Args:
            bar:    Dict with keys: timestamp (tz-aware), open, high, low, close, volume
            symbol: Ticker symbol string

        Returns:
            Signal dict or None.
        """
        ts       = pd.Timestamp(bar["timestamp"])
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        ts_et    = ts.tz_convert("America/New_York")
        bar_time = ts_et.time()
        bar_date = ts_et.date()

        state = self._get_state(symbol)

        # ── New day reset ─────────────────────────────────────────────────────
        if state["date"] != bar_date:
            state["date"]         = bar_date
            state["range_high"]   = None
            state["range_low"]    = None
            state["traded_today"] = False

        # ── Building opening range (9:30–10:00 AM ET) ─────────────────────────
        if self.RANGE_START <= bar_time < self.RANGE_END:
            h = bar["high"]
            l = bar["low"]
            if state["range_high"] is None:
                state["range_high"] = h
                state["range_low"]  = l
            else:
                state["range_high"] = max(state["range_high"], h)
                state["range_low"]  = min(state["range_low"],  l)
            return None

        # ── Outside signal window ─────────────────────────────────────────────
        if bar_time < self.RANGE_END or bar_time > self.cutoff:
            return None

        # ── Range must be defined ─────────────────────────────────────────────
        if state["range_high"] is None or state["range_low"] is None:
            return None

        # ── Already traded today ──────────────────────────────────────────────
        if state["traded_today"]:
            return None

        range_width = state["range_high"] - state["range_low"]
        if range_width <= 0:
            return None

        price     = bar["close"]
        range_pct = range_width / price

        # ── Skip wide-range (gap/news) days ──────────────────────────────────
        if range_pct > self.max_range_pct:
            return None

        buf = range_width * 0.05  # 5% buffer beyond range on stop

        # ── LONG breakout ─────────────────────────────────────────────────────
        if price > state["range_high"]:
            state["traded_today"] = True
            stop_loss = state["range_low"] - buf
            target    = price + self.tp_multiplier * range_width
            risk      = price - stop_loss
            reward    = target - price
            if risk <= 0:
                return None
            return {
                "action":      "LONG",
                "entry":       round(price, 4),
                "stop_loss":   round(stop_loss, 4),
                "target":      round(target, 4),
                "range_high":  round(state["range_high"], 4),
                "range_low":   round(state["range_low"], 4),
                "range_width": round(range_width, 4),
                "risk":        round(risk, 4),
                "reward":      round(reward, 4),
                "rr":          round(reward / risk, 2),
                "timestamp":   ts_et,
                "symbol":      symbol,
            }

        # ── SHORT breakout ────────────────────────────────────────────────────
        if price < state["range_low"]:
            state["traded_today"] = True
            stop_loss = state["range_high"] + buf
            target    = price - self.tp_multiplier * range_width
            risk      = stop_loss - price
            reward    = price - target
            if risk <= 0:
                return None
            return {
                "action":      "SHORT",
                "entry":       round(price, 4),
                "stop_loss":   round(stop_loss, 4),
                "target":      round(target, 4),
                "range_high":  round(state["range_high"], 4),
                "range_low":   round(state["range_low"], 4),
                "range_width": round(range_width, 4),
                "risk":        round(risk, 4),
                "reward":      round(reward, 4),
                "rr":          round(reward / risk, 2),
                "timestamp":   ts_et,
                "symbol":      symbol,
            }

        return None
