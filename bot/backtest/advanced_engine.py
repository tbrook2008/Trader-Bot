"""
bot/backtest/advanced_engine.py — State-Machine Backtester

Supports continuous bar-by-bar evaluation for dynamic exits (like Z-score mean reversion),
as opposed to the bracket-order simulation in the standard engine.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime

class AdvancedBacktestEngine:
    def __init__(self, strategy, capital: float = 100_000, risk_pct: float = 0.01, commission: float = 0.005):
        self.strategy = strategy
        self.initial_capital = capital
        self.risk_pct = risk_pct
        self.commission = commission
        self._trades = []

    def run_single(self, data: Dict[str, pd.DataFrame]) -> dict:
        self._trades = []
        capital = self.initial_capital
        
        for symbol, df in data.items():
            self.strategy.reset_all()
            position = None
            bars = df.reset_index()
            
            for i, row in bars.iterrows():
                bar = {
                    "timestamp": row.get("timestamp", row.get("Datetime", row.get("datetime", row.name))),
                    "open":      float(row.get("open",  0)),
                    "high":      float(row.get("high",  0)),
                    "low":       float(row.get("low",   0)),
                    "close":     float(row.get("close", 0)),
                    "volume":    float(row.get("volume",0)),
                }
                
                signal = self.strategy.evaluate(bar, symbol)
                if signal:
                    if signal["action"] in ["LONG", "SHORT"] and position is None:
                        # Fixed sizing based on risk / 1% move, since we don't have a fixed SL price
                        risk_dollars = capital * self.risk_pct
                        assumed_risk_per_share = bar["close"] * 0.005 # assume 0.5% risk
                        shares = max(1, int(risk_dollars / assumed_risk_per_share))
                        
                        position = {
                            "action": signal["action"],
                            "entry_time": signal["timestamp"],
                            "entry_price": signal["price"],
                            "shares": shares
                        }
                    elif signal["action"] == "EXIT" and position is not None:
                        exit_price = signal["price"]
                        # Apply slippage
                        SLIPPAGE = 0.02
                        if position["action"] == "LONG":
                            exit_price -= SLIPPAGE
                            pnl = (exit_price - position["entry_price"]) * position["shares"]
                        else:
                            exit_price += SLIPPAGE
                            pnl = (position["entry_price"] - exit_price) * position["shares"]
                            
                        commission = self.commission * position["shares"] * 2
                        net_pnl = pnl - commission
                        capital += net_pnl
                        
                        self._trades.append({
                            "symbol": symbol,
                            "date": position["entry_time"].date(),
                            "entry_time": position["entry_time"],
                            "exit_time": signal["timestamp"],
                            "action": position["action"],
                            "entry": position["entry_price"],
                            "shares": position["shares"],
                            "net_pnl": net_pnl,
                            "capital_after": capital,
                            "exit_reason": signal.get("reason", "EXIT")
                        })
                        position = None

            # Close open positions at end of data
            if position is not None:
                last_bar = bars.iloc[-1]
                exit_price = last_bar["close"]
                if position["action"] == "LONG":
                    pnl = (exit_price - position["entry_price"]) * position["shares"]
                else:
                    pnl = (position["entry_price"] - exit_price) * position["shares"]
                capital += (pnl - self.commission * position["shares"] * 2)
                
        return self._build_report(capital, "VWAP Mean Reversion")

    def run_pairs(self, data: Dict[str, pd.DataFrame]) -> dict:
        self._trades = []
        capital = self.initial_capital
        
        y_sym = self.strategy.asset_y
        x_sym = self.strategy.asset_x
        
        if y_sym not in data or x_sym not in data:
            return {"error": "Missing symbols for pairs trading"}
            
        df_y = data[y_sym].copy()
        df_x = data[x_sym].copy()
        
        # Align timestamps exactly
        df_y = df_y[~df_y.index.duplicated()]
        df_x = df_x[~df_x.index.duplicated()]
        common_idx = df_y.index.intersection(df_x.index)
        
        df_y = df_y.loc[common_idx].reset_index()
        df_x = df_x.loc[common_idx].reset_index()
        
        self.strategy.reset_all()
        position = None
        
        for i in range(len(df_y)):
            ry = df_y.iloc[i]
            rx = df_x.iloc[i]
            
            bar_y = {
                "timestamp": ry.get("timestamp", ry.name),
                "open": float(ry.get("open", 0)), "high": float(ry.get("high", 0)),
                "low": float(ry.get("low", 0)), "close": float(ry.get("close", 0)),
                "volume": float(ry.get("volume", 0))
            }
            bar_x = {
                "timestamp": rx.get("timestamp", rx.name),
                "open": float(rx.get("open", 0)), "high": float(rx.get("high", 0)),
                "low": float(rx.get("low", 0)), "close": float(rx.get("close", 0)),
                "volume": float(rx.get("volume", 0))
            }
            
            signal = self.strategy.evaluate_pair(bar_y, bar_x)
            if signal:
                if signal["action"] == "ENTRY" and position is None:
                    # Allocate half risk to each leg
                    risk_dollars = (capital * self.risk_pct) / 2
                    shares_y = max(1, int(risk_dollars / (bar_y["close"] * 0.005)))
                    shares_x = max(1, int(risk_dollars / (bar_x["close"] * 0.005)))
                    
                    position = {
                        "direction": signal["direction"], # 1 = Long Y Short X, -1 = Short Y Long X
                        "entry_time": signal["timestamp"],
                        "entry_y": signal["price_y"],
                        "entry_x": signal["price_x"],
                        "shares_y": shares_y,
                        "shares_x": shares_x
                    }
                elif signal["action"] == "EXIT" and position is not None:
                    exit_y = signal["price_y"]
                    exit_x = signal["price_x"]
                    
                    SLIPPAGE = 0.02
                    
                    if position["direction"] == 1:
                        # Long Y, Short X
                        pnl_y = (exit_y - SLIPPAGE - position["entry_y"]) * position["shares_y"]
                        pnl_x = (position["entry_x"] - (exit_x + SLIPPAGE)) * position["shares_x"]
                    else:
                        # Short Y, Long X
                        pnl_y = (position["entry_y"] - (exit_y + SLIPPAGE)) * position["shares_y"]
                        pnl_x = (exit_x - SLIPPAGE - position["entry_x"]) * position["shares_x"]
                        
                    gross = pnl_y + pnl_x
                    comm = self.commission * (position["shares_y"] + position["shares_x"]) * 2
                    net = gross - comm
                    capital += net
                    
                    self._trades.append({
                        "symbol": f"{y_sym}/{x_sym}",
                        "date": position["entry_time"].date(),
                        "entry_time": position["entry_time"],
                        "exit_time": signal["timestamp"],
                        "action": "LONG_SPREAD" if position["direction"] == 1 else "SHORT_SPREAD",
                        "entry": position["entry_y"] / position["entry_x"],
                        "shares": position["shares_y"] + position["shares_x"],
                        "net_pnl": net,
                        "capital_after": capital,
                        "exit_reason": signal.get("reason", "EXIT")
                    })
                    position = None
                    
        return self._build_report(capital, "Statistical Arbitrage")

    def _build_report(self, final_capital: float, name: str) -> dict:
        if not self._trades:
            return {"error": f"No trades generated for {name}"}
            
        df = pd.DataFrame(self._trades)
        wins = df[df["net_pnl"] > 0]
        losses = df[df["net_pnl"] <= 0]
        n = len(df)
        
        win_rate = len(wins) / n
        avg_win = wins["net_pnl"].mean() if len(wins) else 0.0
        avg_loss = losses["net_pnl"].mean() if len(losses) else 0.0
        profit_factor = wins["net_pnl"].sum() / abs(losses["net_pnl"].sum()) if len(losses) and losses["net_pnl"].sum() != 0 else float('inf')
        
        equity = self.initial_capital + df["net_pnl"].cumsum()
        max_dd = (equity - equity.cummax()).min()
        
        report = {
            "name": name,
            "total_trades": n,
            "win_rate_pct": f"{win_rate*100:.1f}%",
            "profit_factor_str": f"{profit_factor:.2f}",
            "net_pnl_str": f"${df['net_pnl'].sum():,.2f}",
            "max_drawdown_str": f"${max_dd:,.2f}",
            "avg_win": f"${avg_win:,.2f}",
            "avg_loss": f"${avg_loss:,.2f}"
        }
        return report

    def print_report(self, report: dict):
        if "error" in report:
            print(f"❌ {report['error']}")
            return
            
        print(f"\n{'═'*56}")
        print(f"  BACKTEST RESULTS — {report['name']}")
        print(f"{'═'*56}")
        print(f"  Trades:        {report['total_trades']}")
        print(f"  Win Rate:      {report['win_rate_pct']}")
        print(f"  Profit Factor: {report['profit_factor_str']}")
        print(f"  Net P&L:       {report['net_pnl_str']}")
        print(f"  Max Drawdown:  {report['max_drawdown_str']}")
        print(f"  Avg Win:       {report['avg_win']}")
        print(f"  Avg Loss:      {report['avg_loss']}")
        print(f"{'═'*56}\n")
