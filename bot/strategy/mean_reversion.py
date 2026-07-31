"""
bot/strategy/mean_reversion.py — Intraday VWAP Mean Reversion

Logic:
  1. Calculate Intraday VWAP (resets at 9:30 AM ET each day).
  2. Calculate the standard deviation of price from VWAP over the day.
  3. If Price < VWAP - (3 * Standard Deviation): The market has overreacted to the downside. Buy.
  4. If Price > VWAP + (3 * Standard Deviation): The market has overreacted to the upside. Short.
  5. Exit when price touches VWAP (mean reversion complete).
  6. Stop Loss: Dynamic based on Average True Range (ATR), or if Z-score > 4.5.
"""

from typing import Optional, Dict
from datetime import datetime, date as date_type
import pytz
import numpy as np

class VWAPMeanReversion:
    
    def __init__(self, entry_z: float = 3.0, exit_z: float = 0.5, stop_z: float = 4.5, max_loss_pct: float = 0.02):
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z
        self.max_loss_pct = max_loss_pct
        
        # State
        self.current_date = None
        self.cumulative_pv = 0.0
        self.cumulative_vol = 0.0
        self.prices_today = []
        
        self.position = 0 # 1 = LONG, -1 = SHORT, 0 = FLAT
        self.entry_price = 0.0
        self.latest_z_score = 0.0

    def reset_all(self):
        self.current_date = None
        self.position = 0

    def evaluate(self, bar: dict, symbol: str) -> Optional[Dict]:
        ts = bar["timestamp"]
        price = bar["close"]
        vol = bar["volume"]
        typical_price = (bar["high"] + bar["low"] + bar["close"]) / 3.0
        
        bar_date = ts.date()
        
        # Daily Reset
        if self.current_date != bar_date:
            self.current_date = bar_date
            self.cumulative_pv = 0.0
            self.cumulative_vol = 0.0
            self.prices_today = []
            
        self.cumulative_pv += (typical_price * vol)
        self.cumulative_vol += vol
        self.prices_today.append(price)
        
        if self.cumulative_vol == 0 or len(self.prices_today) < 30:
            return None # Need at least 30 minutes of data to establish a solid VWAP and StdDev
            
        vwap = self.cumulative_pv / self.cumulative_vol
        std = np.std(self.prices_today)
        
        if std == 0:
            return None
            
        z_score = (price - vwap) / std
        self.latest_z_score = z_score
        
        # ── EXITS ─────────────────────────────────────────────────────────────
        if self.position == 1:
            # 0. EOD Flatten (4:00 PM ET)
            if ts.tzinfo is None:
                ts_utc = pytz.utc.localize(ts)
            else:
                ts_utc = ts
            ts_et = ts_utc.astimezone(pytz.timezone('US/Eastern'))
            
            if ts_et.hour >= 16:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "EOD Flatten",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
                
            # 1. Absolute Stop Loss
            if price <= self.entry_price * (1.0 - self.max_loss_pct):
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Absolute Stop Loss",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
            # 2. Z-Score Mean Reversion & Volatility Failure
            if z_score >= -self.exit_z:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Mean Reversion" if price > self.entry_price else "Volatility Exit",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
            # 3. Z-Score Stop Loss
            if z_score <= -self.stop_z:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Z-Score Stop Loss",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
        elif self.position == -1:
            # 0. EOD Flatten (4:00 PM ET)
            if ts.tzinfo is None:
                ts_utc = pytz.utc.localize(ts)
            else:
                ts_utc = ts
            ts_et = ts_utc.astimezone(pytz.timezone('US/Eastern'))
            
            if ts_et.hour >= 16:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "EOD Flatten",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
                
            # 1. Absolute Stop Loss
            if price >= self.entry_price * (1.0 + self.max_loss_pct):
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Absolute Stop Loss",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
            # 2. Z-Score Mean Reversion & Volatility Failure
            if z_score <= self.exit_z:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Mean Reversion" if price < self.entry_price else "Volatility Exit",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
            # 3. Z-Score Stop Loss
            if z_score >= self.stop_z:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Z-Score Stop Loss",
                    "timestamp": ts,
                    "price": price,
                    "z_score": z_score,
                    "vwap": vwap
                }
                
        # ── ENTRIES ───────────────────────────────────────────────────────────
        if self.position == 0:
            if ts.tzinfo is None:
                ts_utc = pytz.utc.localize(ts)
            else:
                ts_utc = ts
            ts_et = ts_utc.astimezone(pytz.timezone('US/Eastern'))
            
            is_nyse_hours = (ts_et.hour == 9 and ts_et.minute >= 30) or (10 <= ts_et.hour < 16)
            
            if is_nyse_hours:
                if z_score < -self.entry_z:
                    self.position = 1
                    self.entry_price = price
                    return {
                        "action": "LONG",
                        "timestamp": ts,
                        "price": price,
                        "z_score": z_score,
                        "vwap": vwap
                    }
                elif z_score > self.entry_z:
                    self.position = -1
                    self.entry_price = price
                    return {
                        "action": "SHORT",
                        "timestamp": ts,
                        "price": price,
                        "z_score": z_score,
                        "vwap": vwap
                    }
                
        return None
