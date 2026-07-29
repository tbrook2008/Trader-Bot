"""
bot/strategy/stat_arb.py — Statistical Arbitrage (Pairs Trading)

Logic:
  1. Calculate the price ratio (QQQ / SPY) at every minute.
  2. Maintain a rolling window (e.g., 60 minutes) to find the moving average and standard deviation of this ratio.
  3. Calculate the Z-Score: (Current Ratio - Moving Average) / Standard Deviation.
  4. If Z-Score > 2.0: QQQ is overpriced relative to SPY. SHORT QQQ, LONG SPY.
  5. If Z-Score < -2.0: QQQ is underpriced relative to SPY. LONG QQQ, SHORT SPY.
  6. Exit when Z-Score crosses 0 (mean reversion).
  7. Stop loss if Z-Score exceeds 4.0 (correlation breakdown).
"""

import numpy as np
from collections import deque
from typing import Optional, Dict

class StatArbStrategy:
    """Market Neutral Statistical Arbitrage on highly correlated assets."""

    def __init__(self, asset_y: str = "QQQ", asset_x: str = "SPY",
                 window_size: int = 120, entry_z: float = 2.0, exit_z: float = 0.0, stop_z: float = 4.0):
        self.asset_y = asset_y
        self.asset_x = asset_x
        self.window_size = window_size
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.stop_z = stop_z
        
        self.ratio_history = deque(maxlen=window_size)
        
        # State
        self.position = 0  # 1 = LONG Y SHORT X, -1 = SHORT Y LONG X, 0 = FLAT
        self.entry_prices = {}

    def reset_all(self):
        self.ratio_history.clear()
        self.position = 0
        self.entry_prices = {}

    def evaluate_pair(self, bar_y: dict, bar_x: dict) -> Optional[Dict]:
        """
        Evaluates both assets synchronously.
        Expects bar_y (QQQ) and bar_x (SPY) for the exact same minute.
        """
        price_y = bar_y["close"]
        price_x = bar_x["close"]
        ts = bar_y["timestamp"]
        
        ratio = price_y / price_x
        self.ratio_history.append(ratio)
        
        if len(self.ratio_history) < self.window_size:
            return None  # Wait for moving average to build
            
        ratios = np.array(self.ratio_history)
        mean = np.mean(ratios)
        std = np.std(ratios)
        
        if std == 0:
            return None
            
        z_score = (ratio - mean) / std

        # ── EXITS ─────────────────────────────────────────────────────────────
        if self.position == 1: # LONG Y, SHORT X
            if z_score >= self.exit_z or z_score <= -self.stop_z:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Mean Reversion" if z_score >= self.exit_z else "Stop Loss",
                    "timestamp": ts,
                    "price_y": price_y,
                    "price_x": price_x,
                    "z_score": z_score
                }
                
        elif self.position == -1: # SHORT Y, LONG X
            if z_score <= self.exit_z or z_score >= self.stop_z:
                self.position = 0
                return {
                    "action": "EXIT",
                    "reason": "Mean Reversion" if z_score <= self.exit_z else "Stop Loss",
                    "timestamp": ts,
                    "price_y": price_y,
                    "price_x": price_x,
                    "z_score": z_score
                }

        # ── ENTRIES ───────────────────────────────────────────────────────────
        if self.position == 0:
            if z_score < -self.entry_z:
                self.position = 1
                self.entry_prices = {"Y": price_y, "X": price_x}
                return {
                    "action": "ENTRY",
                    "direction": 1, # Long Y, Short X
                    "timestamp": ts,
                    "price_y": price_y,
                    "price_x": price_x,
                    "z_score": z_score
                }
            elif z_score > self.entry_z:
                self.position = -1
                self.entry_prices = {"Y": price_y, "X": price_x}
                return {
                    "action": "ENTRY",
                    "direction": -1, # Short Y, Long X
                    "timestamp": ts,
                    "price_y": price_y,
                    "price_x": price_x,
                    "z_score": z_score
                }
                
        return None
