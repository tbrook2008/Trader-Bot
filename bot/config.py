"""
bot/config.py — Central configuration for the Trader Bot.
All tunable parameters live here. Edit this file, not the strategy code.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Alpaca Credentials ────────────────────────────────────────────────────────
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
PAPER_TRADING     = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ── Symbols ───────────────────────────────────────────────────────────────────
# SPY = S&P 500 ETF  (proxy for MES/ES futures)
# QQQ = Nasdaq ETF   (proxy for MNQ/NQ futures)
SYMBOLS = ["SPY", "QQQ"]

# ── Strategy: Opening Range Breakout ─────────────────────────────────────────
ORB_RANGE_MINUTES  = 30        # Build opening range for first 30 min (9:30-10:00 AM ET)
ORB_TP_MULTIPLIER  = 2.0       # Take profit = 2x the opening range width
ORB_MAX_RANGE_PCT  = 0.010     # Skip if range > 1.0% of price (extreme gap/news day)
ORB_TRADE_CUTOFF   = "14:30"   # No new entries after 2:30 PM ET

# ── Risk Management ───────────────────────────────────────────────────────────
RISK_PER_TRADE_PCT = 0.01      # Risk 1% of account per trade
MAX_DAILY_LOSS_PCT = 0.02      # Kill switch: stop trading if down 2% on the day
MAX_DAILY_PROFIT_PCT = 0.04    # Stop trading if up 4% (protects consistency rule)
MAX_OPEN_POSITIONS = 2         # Max simultaneous open trades

# ── Backtest Settings ─────────────────────────────────────────────────────────
BACKTEST_DAYS       = 365      # 1 year of historical data
BACKTEST_CAPITAL    = 100_000  # Simulated starting capital

# ── Pass Criteria (before spending any money on a prop firm) ──────────────────
PASS_MIN_WIN_RATE   = 0.55     # Must win ≥ 55% of trades
PASS_MIN_PF         = 1.4      # Profit factor ≥ 1.4
PASS_MAX_DRAWDOWN   = 2000     # Max drawdown ≤ $2,000 on $100k sim account
PASS_MIN_TRADES     = 30       # Need at least 30 trades for statistical significance
