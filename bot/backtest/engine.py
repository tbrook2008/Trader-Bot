"""
bot/backtest/engine.py — Backtesting Engine

Fetches 1-min historical bars via yfinance (free, no API key needed),
simulates the ORB strategy trade by trade, and generates a full report.

Usage:
    engine = BacktestEngine(strategy=ORBStrategy(), capital=100_000)
    data   = engine.load_data(["SPY", "QQQ"], days=365)
    report = engine.run(data)
    engine.print_report(report)
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import bot.config as cfg

warnings.filterwarnings("ignore")


class BacktestEngine:
    """
    Event-driven backtester for intraday 1-minute strategies.

    Position sizing: risk-based (risk_pct of capital per trade).
    Execution model: next-bar open after signal bar closes.
    Exit model: checks each subsequent bar for SL or TP hit (conservative:
        SL assumed to fill first if both hit within the same bar).
    """

    def __init__(self, strategy, capital: float = 100_000,
                 risk_pct: float = 0.01, commission_per_share: float = 0.005):
        """
        Args:
            strategy:              Any strategy with evaluate(bar, symbol) -> signal | None
            capital:               Starting account balance
            risk_pct:              Fraction of account to risk per trade (default 1%)
            commission_per_share:  Round-trip commission per share (default $0.005)
        """
        self.strategy             = strategy
        self.initial_capital      = capital
        self.risk_pct             = risk_pct
        self.commission           = commission_per_share
        self._trades: List[dict]  = []

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_data(self, symbols: List[str], start: Optional[datetime] = None, end: Optional[datetime] = None, days: int = 365,
                  interval: str = "1m") -> Dict[str, pd.DataFrame]:
        """
        Download historical bars from Alpaca API.
        """
        if not cfg.ALPACA_API_KEY or not cfg.ALPACA_SECRET_KEY:
            raise ValueError("Alpaca API keys missing in .env")

        client = StockHistoricalDataClient(cfg.ALPACA_API_KEY, cfg.ALPACA_SECRET_KEY)
        if end is None:
            end = datetime.now()
        if start is None:
            start = end - timedelta(days=days)
            
        data: Dict[str, pd.DataFrame] = {}

        # Chunk into 30-day blocks to avoid Alpaca limits
        chunk_days = 30

        for symbol in symbols:
            print(f"[data] Fetching 1m bars from Alpaca for {symbol} ({start.date()} to {end.date()}) ...", flush=True)
            frames = []
            chunk_end = end
            
            while chunk_end > start:
                chunk_start = max(start, chunk_end - timedelta(days=chunk_days))
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Minute,
                    start=chunk_start,
                    end=chunk_end
                )
                try:
                    bars = client.get_stock_bars(request)
                    if bars and bars.df is not None and not bars.df.empty:
                        df = bars.df.copy()
                        # Alpaca MultiIndex format: (symbol, timestamp)
                        if isinstance(df.index, pd.MultiIndex):
                            df = df.xs(symbol, level=0)
                        frames.append(df)
                except Exception as e:
                    print(f"  [warn] chunk failed: {e}")
                
                chunk_end = chunk_start

            if not frames:
                print(f"  [warn] No data returned for {symbol}")
                continue

            full = pd.concat(frames).sort_index()
            full = full[~full.index.duplicated(keep="first")]

            # Ensure timezone awareness (ET)
            if full.index.tzinfo is None:
                full.index = full.index.tz_localize("UTC")
            full.index = full.index.tz_convert("America/New_York")

            data[symbol] = full
            print(f"  → {len(full):,} bars  ({full.index[0].date()} – {full.index[-1].date()})", flush=True)

        return data

    # ── Core backtest loop ────────────────────────────────────────────────────

    def run(self, data: Dict[str, pd.DataFrame]) -> dict:
        """Run the backtest and return a results dict."""
        self._trades = []
        capital      = self.initial_capital

        for symbol, df in data.items():
            self.strategy.reset(symbol)
            bars = df.reset_index()  # make timestamp a column

            for i, row in bars.iterrows():
                bar = {
                    "timestamp": row.get("timestamp", row.get("Datetime", row.get("datetime", row.name))),
                    "open":      float(row.get("open",  row.get("Open",  0))),
                    "high":      float(row.get("high",  row.get("High",  0))),
                    "low":       float(row.get("low",   row.get("Low",   0))),
                    "close":     float(row.get("close", row.get("Close", 0))),
                    "volume":    float(row.get("volume",row.get("Volume",0))),
                }

                signal = self.strategy.evaluate(bar, symbol)
                if signal is None:
                    continue

                # Position size: risk $ / stop distance in $
                risk_dollars = capital * self.risk_pct
                stop_dist    = abs(signal["entry"] - signal["stop_loss"])
                if stop_dist <= 0:
                    continue
                shares = max(1, int(risk_dollars / stop_dist))

                # Simulate exit on future bars (look-ahead window = 200 bars)
                future = bars.iloc[i + 1 : i + 201]
                result = self._simulate_exit(signal, future, shares)
                if result is None:
                    continue

                commission = self.commission * shares * 2  # round trip
                net_pnl    = result["gross_pnl"] - commission
                capital   += net_pnl

                self._trades.append({
                    "symbol":       symbol,
                    "date":         signal["timestamp"].date(),
                    "entry_time":   signal["timestamp"],
                    "exit_time":    result["exit_time"],
                    "action":       signal["action"],
                    "entry":        signal["entry"],
                    "stop_loss":    signal["stop_loss"],
                    "target":       signal["target"],
                    "range_width":  signal["range_width"],
                    "rr":           signal["rr"],
                    "shares":       shares,
                    "gross_pnl":    round(result["gross_pnl"], 2),
                    "commission":   round(commission, 2),
                    "net_pnl":      round(net_pnl, 2),
                    "exit_reason":  result["exit_reason"],
                    "capital_after":round(capital, 2),
                })

        return self._build_report(capital)

    def _simulate_exit(self, signal: dict, future: pd.DataFrame, shares: int) -> Optional[dict]:
        """
        Walk forward through future bars to find the first SL or TP hit.
        Adds brutal $0.02 slippage per share against the position on stops.
        """
        action = signal["action"]
        sl     = signal["stop_loss"]
        tp     = signal["target"]
        
        # Slippage penalty: assuming we get a worse price on market stop exits
        SLIPPAGE = 0.02 

        for _, row in future.iterrows():
            lo = float(row.get("low",  row.get("Low",  0)))
            hi = float(row.get("high", row.get("High", 0)))
            ts = row.get("timestamp", row.get("Datetime", row.get("datetime", row.name)))

            if action == "LONG":
                if lo <= sl:  # SL hit first
                    actual_exit = sl - SLIPPAGE
                    return {"gross_pnl": (actual_exit - signal["entry"]) * shares,
                            "exit_reason": "stop_loss", "exit_time": ts}
                if hi >= tp:
                    return {"gross_pnl": (tp - signal["entry"]) * shares,
                            "exit_reason": "target",    "exit_time": ts}
            else:  # SHORT
                if hi >= sl:
                    actual_exit = sl + SLIPPAGE
                    return {"gross_pnl": (signal["entry"] - actual_exit) * shares,
                            "exit_reason": "stop_loss", "exit_time": ts}
                if lo <= tp:
                    return {"gross_pnl": (signal["entry"] - tp) * shares,
                            "exit_reason": "target",    "exit_time": ts}

        # Still open at end of look-ahead window — exit at last bar close
        if future.empty:
            return None
        last = future.iloc[-1]
        last_close = float(last.get("close", last.get("Close", signal["entry"])))
        last_ts    = last.get("timestamp", last.get("Datetime", last.get("datetime", last.name)))
        
        # Add slippage to forced market exits too
        if action == "LONG":
            pnl = ((last_close - SLIPPAGE) - signal["entry"]) * shares
        else:
            pnl = (signal["entry"] - (last_close + SLIPPAGE)) * shares
            
        return {"gross_pnl": pnl, "exit_reason": "window_close", "exit_time": last_ts}

    # ── Report generation ─────────────────────────────────────────────────────

    def _build_report(self, final_capital: float) -> dict:
        if not self._trades:
            return {"error": "No trades generated — check symbol data and date range"}

        df        = pd.DataFrame(self._trades).sort_values("entry_time")
        wins      = df[df["net_pnl"] > 0]
        losses    = df[df["net_pnl"] <= 0]
        n         = len(df)

        win_rate      = len(wins) / n
        avg_win       = wins["net_pnl"].mean()  if len(wins)   else 0.0
        avg_loss      = losses["net_pnl"].mean() if len(losses) else 0.0
        total_wins    = wins["net_pnl"].sum()
        total_losses  = abs(losses["net_pnl"].sum())
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")
        expectancy    = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
        net_pnl       = df["net_pnl"].sum()

        # Equity curve & max drawdown
        equity  = self.initial_capital + df["net_pnl"].cumsum()
        peak    = equity.cummax()
        dd      = (equity - peak)
        max_dd  = dd.min()

        # Daily P&L for consistency check
        daily = df.groupby("date")["net_pnl"].sum()
        best_day  = daily.max()
        total_pos = daily[daily > 0].sum()
        consistency_pct = (best_day / total_pos * 100) if total_pos > 0 else 0

        # Per-symbol breakdown
        by_symbol = {}
        for sym, g in df.groupby("symbol"):
            sw = g[g["net_pnl"] > 0]
            by_symbol[sym] = {
                "trades":      len(g),
                "win_rate":    f"{len(sw)/len(g)*100:.1f}%",
                "net_pnl":     f"${g['net_pnl'].sum():,.2f}",
            }

        return {
            "total_trades":      n,
            "wins":              len(wins),
            "losses":            len(losses),
            "win_rate":          win_rate,
            "win_rate_pct":      f"{win_rate*100:.1f}%",
            "profit_factor":     profit_factor,
            "profit_factor_str": f"{profit_factor:.2f}",
            "expectancy":        expectancy,
            "expectancy_str":    f"${expectancy:,.2f}/trade",
            "avg_win":           f"${avg_win:,.2f}",
            "avg_loss":          f"${avg_loss:,.2f}",
            "net_pnl":           net_pnl,
            "net_pnl_str":       f"${net_pnl:,.2f}",
            "max_drawdown":      max_dd,
            "max_drawdown_str":  f"${max_dd:,.2f}",
            "initial_capital":   f"${self.initial_capital:,.0f}",
            "final_capital":     f"${final_capital:,.2f}",
            "best_day":          f"${best_day:,.2f}",
            "consistency_pct":   f"{consistency_pct:.1f}%",
            "by_symbol":         by_symbol,
            "trades_df":         df,
            # Raw values for pass/fail check
            "_win_rate":         win_rate,
            "_pf":               profit_factor,
            "_max_dd":           max_dd,
            "_n_trades":         n,
        }

    def print_report(self, report: dict) -> None:
        """Pretty-print the backtest report to console."""
        if "error" in report:
            print(f"\n❌  {report['error']}\n")
            return

        SEP = "─" * 56

        print(f"\n{'═'*56}")
        print(f"  BACKTEST RESULTS — Opening Range Breakout (ORB)")
        print(f"{'═'*56}")
        print(f"  Capital:  {report['initial_capital']}  →  {report['final_capital']}")
        print(f"  Net P&L:  {report['net_pnl_str']}")
        print(SEP)
        print(f"  Trades:       {report['total_trades']}  ({report['wins']}W / {report['losses']}L)")
        print(f"  Win Rate:     {report['win_rate_pct']}")
        print(f"  Avg Win:      {report['avg_win']}")
        print(f"  Avg Loss:     {report['avg_loss']}")
        print(f"  Profit Factor:{report['profit_factor_str']}")
        print(f"  Expectancy:   {report['expectancy_str']}")
        print(f"  Max Drawdown: {report['max_drawdown_str']}")
        print(f"  Best Day:     {report['best_day']}")
        print(f"  Consistency:  {report['consistency_pct']}  (best day / total wins)")
        print(SEP)
        print("  By Symbol:")
        for sym, d in report["by_symbol"].items():
            print(f"    {sym}: {d['trades']} trades | WR {d['win_rate']} | PnL {d['net_pnl']}")
        print(SEP)

        # Pass/Fail check
        p = self._check_pass(report)
        if p["passed"]:
            print("  ✅  STRATEGY PASSES all criteria — ready to paper trade")
        else:
            print("  ❌  STRATEGY DOES NOT YET PASS:")
            for fail in p["failures"]:
                print(f"       • {fail}")
        print(f"{'═'*56}\n")

    def _check_pass(self, report: dict) -> dict:
        """Check against the defined pass criteria."""
        from bot.config import (PASS_MIN_WIN_RATE, PASS_MIN_PF,
                                PASS_MAX_DRAWDOWN, PASS_MIN_TRADES)
        failures = []
        if report["_win_rate"] < PASS_MIN_WIN_RATE:
            failures.append(f"Win rate {report['win_rate_pct']} < {PASS_MIN_WIN_RATE*100:.0f}% required")
        if report["_pf"] < PASS_MIN_PF:
            failures.append(f"Profit factor {report['profit_factor_str']} < {PASS_MIN_PF} required")
        if report["_max_dd"] < -PASS_MAX_DRAWDOWN:
            failures.append(f"Max drawdown {report['max_drawdown_str']} exceeds -${PASS_MAX_DRAWDOWN:,}")
        if report["_n_trades"] < PASS_MIN_TRADES:
            failures.append(f"Only {report['_n_trades']} trades < {PASS_MIN_TRADES} required for significance")
        return {"passed": len(failures) == 0, "failures": failures}
